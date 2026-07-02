# Design — `deepseek` delegation skill

**Date:** 2026-07-02
**Status:** Approved (brainstorm) → ready for implementation planning
**Repo:** `yarrasys/extensions`

## Summary

A new skill, `deepseek`, that lets the orchestrating Claude Code session hand a bounded,
"simple" development task to a **nested headless `claude` process running on DeepSeek's
Anthropic-compatible endpoint**. The child does the read → edit → verify loop using Claude
Code's own harness; the parent session gets back only a compact JSON **receipt**. Ships as a
portable skill first; a Claude Code plugin wrapper (enforcing hooks + `/deepseek:*` commands)
is a documented follow-up.

**Intent:** efficient token utilisation — offload simple dev work to a cheaper model so the
main (expensive) session spends tokens only on orchestration and hard problems.

## Why this architecture

Delegation only saves tokens if we control *what returns to the parent's context*. The chosen
model is **offload-and-write**: the delegate does the task and writes to disk itself; the parent
gets a receipt, not the artifact.

We reach offload-and-write via a **nested headless `claude` pointed at DeepSeek**, chosen over
the alternatives considered during brainstorming:

| Approach | Verdict |
|----------|---------|
| Constrained single-shot via raw DeepSeek API | We'd hand-build the read/edit/verify loop; single call, no real agency, scales poorly to multi-file/iteration. |
| Wrap `aider` / `opencode` | Heavy deps or external binary; we inherit their loop and must suppress their verbose output; clashes with the repo's self-contained-script ethos. |
| External orchestrator / model router (OpenClaw, claude-code-router) | Different topology (an external layer routes above Claude Code); not a shippable artifact in this repo; routing is semantically blind to "simple"; abandons the subscription for the main session. |
| **Nested headless `claude` → DeepSeek** (chosen) | Reuses Claude Code's battle-tested agent loop; DeepSeek speaks the Anthropic wire format **natively** (no translation proxy); structured JSON receipt by construction; blast radius controlled via `--allowedTools` / `--permission-mode` / worktree; thin `uv` wrapper — fits the repo. |

### Enabling facts (verified 2026-07-02)

- **DeepSeek native Anthropic endpoint:** `https://api.deepseek.com/anthropic`, auth via
  `ANTHROPIC_AUTH_TOKEN=<deepseek key>`. No `claude-code-router` / translation layer required.
  Model mapping: `claude-opus-*` → `deepseek-v4-pro`; `claude-sonnet/haiku-*` → `deepseek-v4-flash`.
  We pin `--model` explicitly rather than rely on mapping.
- **Claude Code CLI** honors `-p` (headless), `--output-format json`, `--settings`, `--model`,
  `--allowedTools`, `--permission-mode`, and an `env` block in settings. It marks nested sessions
  on its own spawn path and auto-excludes them from `--resume`/`--continue`/history, so a child
  won't clobber the parent session.

Sources: Claude Code env-vars docs (`code.claude.com/docs/en/env-vars`); DeepSeek Anthropic API
(`api-docs.deepseek.com/guides/anthropic_api`) and Claude Code integration guide.

## Token-savings honesty

Launching the child and reading its receipt still costs the parent a little (task string in,
~10 lines of JSON out). The win is that all file-reading, generation, and iteration run on
DeepSeek's tokens. **Net positive only for simple, self-contained tasks** that would otherwise
cost the parent many read + generate tokens. The skill is scoped accordingly.

## Components (each independently testable)

```
skills/deepseek/
  SKILL.md              # orchestrator guidance: when to delegate, modes, receipt reading
  deepseek.py           # PEP-723 uv entrypoint (CLI)
  deepseek_core/
    config.py           # .deepseek.json discovery (walk-up) + schema + merge + defaults
    runner.py           # build child env + argv, spawn nested claude, capture JSON
    guardrails.py       # denyGlobs, cost cap, recursion guard, worktree lifecycle, timeout
    receipt.py          # shape the compact receipt
  tests/                # unit + integration (fake `claude` on PATH)
  CHANGELOG.md · NOTICE · AGENTS.md
.deepseek.json          # per-project config (committed; secrets never here)
```

Unit boundaries: `config` (pure — discovery/merge), `guardrails` (pure predicates + worktree
side-effects behind a small interface), `runner` (subprocess orchestration), `receipt` (pure
shaping). `deepseek.py` is the thin CLI that wires them.

## Configuration — `.deepseek.json`

Committed at the repo root; discovered by walking up from cwd (same pattern as kdbx's
`.keepassxc.json`). Secrets never live here.

```jsonc
{
  "mode": "suggest",              // "explicit" | "suggest" | "auto"   (default: suggest)
  "model": "deepseek-v4-flash",
  "verifyDefault": "ruff check {file}",
  "auto": {                        // consulted in auto/suggest
    "allowTasks": ["docstrings", "formatting", "boilerplate", "tests", "comments", "rename"],
    "allowGlobs": ["**/*.py"],
    "denyGlobs":  [".github/**", "**/*secret*", "infra/**"],
    "maxCostUsdPerRun": 0.25,
    "maxCostUsdPerSession": 2.00,
    "isolate": true               // auto always works in a throwaway worktree (non-overridable in auto)
  }
}
```

### Autonomy modes (govern the parent's *initiative* only)

- `explicit` — delegate only when the user says so (or via a future `/deepseek:delegate`). Never self-initiate.
- `suggest` — **default.** Propose "this looks delegatable — offload to DeepSeek?" and wait for confirmation.
- `auto` — offload tasks matching `allowTasks` + `allowGlobs`, within caps, always isolated. Receipts still surface.

## Guardrails — hard vs soft

- **Hard (script-enforced, always, regardless of mode):** recursion refusal
  (`DEEPSEEK_DELEGATE_DEPTH` present → exit), `denyGlobs` on changed files (refuse to apply),
  `maxCostUsdPerRun` check before applying a patch, `--max-turns` ceiling, worktree isolation,
  subprocess timeout.
- **Soft (behavioral):** `mode` governs the parent's initiative. `auto` trusts the parent to
  honor it; the future plugin `PreToolUse` hook can harden this. Documented as such — no false
  guarantee that the skill alone enforces autonomy.

## Command surface

```bash
uv run --locked skills/deepseek/deepseek.py <op>
```

| Op | Use |
|----|-----|
| `delegate --task T [--file F…] [--dir D] [--in-place] [--verify CMD] [--model M]` | core: spawn child, return receipt (+ patch path if isolated) |
| `apply PATCH` | apply a returned worktree patch to the real tree |
| `init` | scaffold `.deepseek.json` with safe defaults |
| `check` | **offline** preflight: `claude` on PATH? key resolves? git available? (no live API ping) |
| `config` | print the effective merged config |

Isolation default: **worktree + patch (review-first)**; `--in-place` opts into direct edits.
`auto` mode forces isolation regardless of flag.

## Data flow — `delegate`

1. Parent decides to delegate (per `mode`); builds the task string + optional `--file` scope.
2. `runner` resolves the key — **kdbx `get` → else `$DEEPSEEK_API_KEY`** — and builds child env:
   `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`, `ANTHROPIC_AUTH_TOKEN=<key>`,
   `DEEPSEEK_DELEGATE_DEPTH=1`.
3. `guardrails` sets the workspace: new `git worktree` (default) or cwd (`--in-place`).
4. Generate an ephemeral child `settings.json`: pin `--model`, set `--allowedTools`, and
   **disable this skill in the child** (belt-and-suspenders with the depth guard).
5. Spawn `claude -p "<task>" --output-format json --permission-mode acceptEdits --max-turns N …`
   in the workspace.
6. Capture JSON. Run the `--verify` gate inside the workspace.
7. `receipt` shapes compact output → parent stdout. Patch applied/withheld per mode + verify +
   guardrail results.

## Receipt (the only thing that hits the parent's context)

```json
{
  "status": "patch_ready",              // applied | patch_ready | verify_failed | budget_exceeded | denied | error
  "workspace": "worktree",
  "files": [{"path": "utils.py", "diffstat": "+18 -2"}],
  "verify": {"cmd": "ruff check utils.py", "exit": 0, "passed": true},
  "patch": ".deepseek/edit-8f3a.patch",
  "cost": {"reported_usd": 0.0009, "note": "child-reported, Anthropic-priced — approximate"},
  "turns": 3
}
```

Cost note: Claude Code computes `total_cost_usd` from Anthropic pricing; against DeepSeek's
endpoint that figure is approximate. Labelled as such; optionally recomputed from token counts ×
DeepSeek rates in a later iteration.

## Error handling

| Case | Behavior |
|------|----------|
| `claude` not on PATH | exit 7, message: install Claude Code |
| key missing | exit 3, emit the **kdbx `set` command for the human** (never author the secret) |
| child nonzero / verify fail | `verify_failed`; patch **not** applied; error tail in receipt |
| cost cap exceeded | `budget_exceeded`; patch withheld |
| changed file matches `denyGlobs` | `denied`; patch withheld |
| recursion detected | refuse, exit 4 |
| child auth/endpoint error | surface child's stderr tail |

## Testing (TDD; per repo rules)

- **Unit:** config discovery/merge + defaults; `denyGlobs`; recursion guard; receipt shaping;
  argv/env construction (assert the command + env are built correctly **without spawning**).
- **Integration:** a **fake `claude` binary** placed on `PATH` (a tiny script emitting canned
  JSON and touching files) drives the full spawn → capture → verify → receipt path
  deterministically. **No network, no real DeepSeek** in tests.
- Register `skills/deepseek/tests` in `pytest.ini` (own line — the plugin symlink would otherwise
  re-collect). Lock `deepseek.py.lock`. Update README "Available skills" + `llms.txt`.

## Prerequisites

`claude` CLI on PATH · a DeepSeek API key (via kdbx or `$DEEPSEEK_API_KEY`) · `uv` · `git`.

## Security / licensing

- Key handled like all secrets: resolved via kdbx or env, **never printed** into transcript,
  logs, or `.deepseek.json`. On a missing key, the skill emits the `set` command for the human to
  run — it never authors or observes the secret value (consistent with kdbx's role boundary).
- No copyleft runtime deps anticipated; record any in `NOTICE`. Repo source stays MIT.

## Out of scope (v1) / YAGNI

- Plugin wrapper (hooks + MCP + slash commands) — **follow-up** once the core proves out.
- Diff/patch *return mode* from the child (vs. full file writes) — the child already edits via
  Claude Code tools, so N/A here; the parent-side patch is produced by `git diff` on the worktree.
- Recomputing cost from DeepSeek pricing — later.
- Live endpoint ping in `check` — deferred to the first real `delegate`.

## Open items (fine-tune during build)

- **Defining "simple".** Acknowledged as genuinely hard. v1 proxy = the `allowTasks` allowlist +
  `allowGlobs`/`denyGlobs` + cost caps. Expect to tune these (and the SKILL.md guidance the parent
  reads) empirically as we build and dogfood. Not a blocker.
- Exact `--max-turns` default and subprocess timeout — pick conservative values, tune with real runs.
- Whether `suggest` should also respect `allowTasks` (only suggest for allowlisted task types) or
  suggest more broadly — decide during implementation.
