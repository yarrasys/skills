---
name: deepseek
description: Delegate a bounded, simple dev task (docstrings, formatting, boilerplate, tests, comments, rename) to a nested headless `claude` running on DeepSeek's Anthropic-compatible endpoint instead of burning the parent's own tokens — worktree-isolated by default, verified before it's ever surfaced, and reported back as a compact receipt. Operations: delegate, apply, init, check, config. Use when a task is simple/mechanical enough to offload for token efficiency, not for anything requiring judgment, architecture decisions, or touching sensitive paths.
---

# deepseek — offload simple dev tasks to DeepSeek

Runs a nested, headless `claude` process pointed at DeepSeek's Anthropic-compatible endpoint
(`ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`) to do a bounded, mechanical edit —
so the parent session's own context/tokens aren't spent on it. The child works in an isolated
git worktree by default; its diff is written back as a `.patch` file, never applied directly
unless you opt in. Every run ends in a JSON **receipt** on stdout, not prose.

## When to use

- The task is simple and mechanical: add docstrings, reformat, fill boilerplate, write/extend
  tests, add comments, rename a symbol. Good token-efficiency win.
- **Not** for anything needing judgment, architectural decisions, multi-file design, or touching
  `.github/**`, secrets, or `infra/**` (denied by default — see `.deepseek.json`).
- You want the change **reviewed** before it lands: default mode produces a patch, not a commit.

## Invocation

```
uv run --locked <SKILL_DIR>/deepseek.py <op> [args]
```

`<SKILL_DIR>` is this skill's directory (where this SKILL.md lives). Requires `uv`, `git`, and the
`claude` CLI on `PATH`; `deepseek check` verifies all three plus the API key.

## Operations

| Op | Use |
|----|-----|
| `init` | write a starter `.deepseek.json` to cwd (refuses to overwrite) |
| `check` | offline preflight: `claude`/`git` on PATH, `DEEPSEEK_API_KEY` resolvable; exit 0/3 |
| `config` | print the merged effective config (defaults + `.deepseek.json`) as JSON |
| `delegate --task "…" [--file F ...] [--dir D] [--in-place] [--verify CMD] [--model M]` | run the child, verify, guardrail-check, and either write a patch or apply in place. ⚠️ `--file` is accepted but **not yet enforced** in v1 — see below. |
| `apply PATCH` | `git apply` a `.deepseek/edit-*.patch` produced by a prior `delegate` |

`delegate` defaults to **worktree + patch**: the child edits a disposable worktree, the diff is
written to `.deepseek/edit-<tag>.patch` in the real repo, and nothing in your working tree changes
until you review and run `apply`. Pass `--in-place` to skip isolation and let `delegate` apply
directly to the current tree — it refuses if the tree is dirty (commit or stash first).

⚠️ **`--file` does not scope the edit.** It's accepted by the CLI but not yet read by `delegate` in
v1 — the delegated child always sees the whole repo (within `ALLOWED_TOOLS`), not just the named
file(s). To actually scope what the child touches, be specific in `--task`'s description and/or
rely on `auto.denyGlobs` in `.deepseek.json` — don't count on `--file` to fence the edit.

## Autonomy modes (`.deepseek.json` → `mode`)

`deepseek` itself doesn't read `mode` to change its own behavior — `delegate`/`apply` always run
the same way. `mode` is a **contract for the parent agent/orchestrator** driving `deepseek`:

| Mode | Parent behavior |
|------|------|
| `explicit` | Only delegate when the user explicitly asks to offload this task. |
| `suggest` | Parent may propose delegating (e.g. "this looks delegable — offload it?") but waits for user confirmation before running `delegate`. |
| `auto` | Parent may delegate without asking, **but only** for tasks in `auto.allowTasks`, touching only `auto.allowGlobs` and none of `auto.denyGlobs`, under `auto.maxCostUsdPerRun`. `auto.isolate` is forced `True` in this mode (non-overridable) — auto-mode delegations are never `--in-place`. |

## Reading a receipt

Every `delegate` prints one JSON object to stdout: `{status, workspace, files, verify, cost,
turns}` are **always present**. A `patch` key (path to the withheld patch, under `.deepseek/`) is
added **only when `status == "patch_ready"`** — every other status omits it entirely (don't index
`receipt["patch"]` unconditionally). Act on `status`:

| `status` | Exit | Meaning / what to do next |
|----------|------|----------------------------|
| `patch_ready` | 0 | Success, isolated. Receipt includes `patch` (a path under `.deepseek/`). Review it, then `deepseek apply <patch>` to land it. |
| `applied` | 0 | Success, `--in-place`. No `patch` key — the change is already in the working tree, review with `git diff`. |
| `verify_failed` | 5 | The child's edit failed `verify` (default `ruff check {file}`, or `--verify`/`verifyDefault`). No `patch` key; nothing was applied; `receipt.verify.tail` has the last lines of output. |
| `budget_exceeded` | 6 | Child-reported cost exceeded `auto.maxCostUsdPerRun`. No `patch` key; nothing applied. |
| `denied` | 6 | The change touched a path matching `auto.denyGlobs`. No `patch` key; nothing applied; `receipt.files` shows what changed. |

For these three withheld statuses, "nothing applied" holds in **both** modes: in worktree mode
the edit only ever existed in the disposable worktree, which is discarded; in `--in-place` mode
`delegate` restores the working tree to `HEAD` (`git checkout -- .` + `git clean -fd`) before
returning, undoing the child's edit and removing anything it created.
| `error` | 7 | The child process itself failed or produced unparseable output. No `patch` key; no receipt fields beyond the shell (`files: []`, `cost.reported_usd: null`). |

Other exit codes: `2` `apply` given a patch that doesn't exist · `3` `check` failed, or `delegate`
found no `DEEPSEEK_API_KEY` · `4` `delegate` refused to recurse (see below), or `init` refused to
overwrite an existing `.deepseek.json` · `7` also covers `--in-place` on a dirty tree, and any
other runtime/preflight failure (missing `git`, wrong Python).

🔑 **Recursion guard:** `delegate` refuses (exit 4) if `DEEPSEEK_DELEGATE_DEPTH` is already set in
its environment. The child is launched with that var set and with the `deepseek` skill disabled in
its own settings — this is what stops a delegated `claude` from delegating again.

## v1 limitations

- `auto.maxCostUsdPerSession` is **parsed but not enforced** — only `maxCostUsdPerRun` is checked
  per delegation. There's no session-level cost ledger yet; don't rely on the session cap.
- `cost.reported_usd` is child-reported and **Anthropic-priced** (the `claude` CLI's own cost
  accounting), not recomputed against DeepSeek's actual pricing — treat it as approximate.
- `check` is fully offline: it confirms the key/binaries are *present*, not that the DeepSeek
  endpoint is reachable or the key is valid. That's only verified on the first real `delegate`.

## Verify prerequisite

The default `verifyDefault` is `ruff check {file}` — it assumes `ruff` is on `PATH` in the
environment `delegate` runs in. If your project doesn't use `ruff` (or it isn't installed), every
delegation will spuriously report `verify_failed`. Either set `verifyDefault` in `.deepseek.json`
to a command that fits your project, or pass `--verify <cmd>` per call (use `{file}` as a
placeholder for the changed files; an empty string via `--verify ""` disables verification).

## Security — what isolation actually covers

The delegated child runs with `Bash` in `ALLOWED_TOOLS` and `--permission-mode acceptEdits`
(auto-approved, no per-tool confirmation). Worktree isolation only contains the child's
**git-tracked file diffs** — it does **not** sandbox the child's process. From inside the
worktree the child can still run arbitrary shell commands, write to absolute paths outside the
worktree, read/exfiltrate repo contents over the network, or otherwise act outside git's view.
Only delegate to a DeepSeek endpoint/key you trust with shell access. `--in-place` skips even
that file-diff isolation and lets the child's edits land straight on your real tree (rolled back
automatically if a gate withholds — see the receipt table above), so treat it as running
untrusted edits directly on your working copy.

## Security — the key is never yours to see

`delegate` resolves `DEEPSEEK_API_KEY` from the environment. Store it the same way you'd store any
other secret — via the [kdbx](../kdbx) skill (`kdbx set api/deepseek --var DEEPSEEK_API_KEY`,
run by a **human**, then `kdbx run -- uv run --locked deepseek.py delegate …`) — or export it in
an env `deepseek` inherits. Either way, **the agent driving `deepseek` never authors or observes
the key value**; it only ever sees whether `check`/`delegate` succeeded or failed to find one.
