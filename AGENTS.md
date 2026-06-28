# AGENTS.md

> Canonical guidance for AI coding agents working **in this repository** — an umbrella monorepo of
> agent skills. [`CLAUDE.md`](CLAUDE.md) (and any `GEMINI.md` / `copilot-instructions`) point here, so
> there is **one source of truth** across assistants.
>
> 🔑 Before working **on** a skill, also read that skill's own `AGENTS.md` (e.g.
> [`skills/kdbx/AGENTS.md`](skills/kdbx/AGENTS.md)) — it carries the skill-specific golden rules,
> build/test commands, and engine boundaries. This file is the thin repo-wide layer; deep detail lives
> per skill.

## What this repo is

`yarrasys/extensions` — a collection of self-contained **agent skills** (Python 3.10+, `uv`-driven),
each installable on its own (`npx skills add yarrasys/extensions@<name>`). The repo also doubles as a
Claude Code **plugin marketplace** ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)).

**Mental model — skill vs plugin:**
- A **skill** (`skills/<name>/`) is portable, agent-agnostic guidance + code that *recommends* a contract.
- A **plugin** (`plugins/<name>/`) is the Claude Code flavor of that same skill that can *enforce* the
  contract — via `PreToolUse` hooks, an MCP server, and `/<name>:*` commands. It bundles the skill
  through a **symlink**, so the skill body has a single source.

## Two modes — read the right doc

| You are… | Read |
|----------|------|
| **Developing / maintaining** a skill (writing code & tests) | this file + `skills/<name>/AGENTS.md` |
| **Invoking** a skill at runtime (using its capability) | `skills/<name>/SKILL.md` |
| **Adding** a brand-new skill or plugin | the [scaffold below](#adding-a-new-skill) |

## Repository map

| Path | Purpose |
|------|---------|
| `skills/<name>/` | a self-contained skill — `SKILL.md`, code, `tests/`, `CHANGELOG.md`, `NOTICE`, `AGENTS.md` |
| `plugins/<name>/` | optional plugin wrapper — `hooks/`, `mcp/`, `commands/`, manifests, **+ a symlink to the bundled skill** |
| `.claude-plugin/marketplace.json` | the marketplace manifest (lists installable plugins) |
| `.github/workflows/ci.yml` | CI: pytest on Linux/macOS/Windows + ruff + manifest/symlink/lockfile checks |
| `pytest.ini` | explicit per-skill/plugin test paths |
| `README.md` · `llms.txt` | human + machine indexes of the collection |

**WHERE TO LOOK**

| To… | Go to |
|-----|-------|
| understand a skill's design / rules | `skills/<name>/AGENTS.md` |
| change skill behavior or code | `skills/<name>/` — **never** the `plugins/<name>/skills/<name>` mirror |
| change a plugin's hook / MCP / commands | `plugins/<name>/{hooks,mcp,commands}/` |
| add/remove a plugin in the marketplace | `.claude-plugin/marketplace.json` |
| change what tests run | `pytest.ini` |
| change CI | `.github/workflows/ci.yml` |

## Available skills

| Skill | One-liner |
|-------|-----------|
| [**kdbx**](skills/kdbx) | Per-project/per-env credentials in key-file-only KeePassXC vaults — replaces `.env`, injects secrets into commands without printing them, enforces an agent/human role boundary. |

(See the [README](README.md) for install commands.)

## Adding a new skill

TDD throughout — failing test first.

1. **Create `skills/<name>/`** with:
   - `SKILL.md` — frontmatter (`name`, `description`) + when-to-use + invocation + operations. *This is what agents load.*
   - your code (a PEP-723 single-file `<name>.py`, or a package);
   - `tests/`, a `CHANGELOG.md` with `## [Unreleased]`, a `NOTICE` (license notes), and an `AGENTS.md` (skill-specific golden rules, build/test, boundaries).
2. **Register tests:** add `skills/<name>/tests` to `testpaths` in [`pytest.ini`](pytest.ini) — one line per skill (see [Testing](#testing--ci) for why a bare glob breaks).
3. **Lock deps** (PEP-723 script): `uv lock --script skills/<name>/<name>.py`, commit `<name>.py.lock`.
4. **Index it:** add a row to the README "Available skills" table and an entry to `llms.txt`.
5. *(Optional)* wrap it as a plugin ↓.

### Adding a plugin wrapper

1. **Create `plugins/<name>/`** with `.claude-plugin/plugin.json` (`name`, `version`, `description`) and any of: `hooks/` (+ `hooks.json`), `mcp/` (+ `.mcp.json` and a locked `server.py`), `commands/*.md`.
2. **Bundle the skill by symlink** (single source of truth):
   `ln -s ../../../skills/<name> plugins/<name>/skills/<name>`
   ✅ edit `skills/<name>/…`  ·  ❌ never edit the `plugins/<name>/skills/<name>` mirror (CI asserts its `SKILL.md` resolves).
3. **List it** in `.claude-plugin/marketplace.json` (`name`, `source: ./plugins/<name>`, `description`, `version`) — keep `version` in sync with `plugin.json`.
4. **Register tests:** add `plugins/<name>/tests` to `pytest.ini`.

## Commands

Prerequisite: [`uv`](https://docs.astral.sh/uv/) — the *only* one; it provides Python + deps and caches
them. Never fall back to system Python or `pip`.

```bash
# format → lint → test   (run in this order before every commit)
uvx ruff format .
uvx ruff check .
uv run --with pytest --with pykeepass --with python-dotenv --with filelock \
  --with platformdirs --with "mcp>=1.0,<2" python -m pytest

uv run --locked skills/kdbx/kdbx.py --version    # smoke a skill's locked entrypoint
uv lock --script skills/kdbx/kdbx.py             # re-lock after changing a script's deps
```

(The `--with` set is the *current* suite's deps; a new skill may add its own.)

## Testing & CI

- Tests are pinned **per-skill/plugin** in `pytest.ini` (`skills/<name>/tests`, `plugins/<name>/tests`)
  — *not* a bare `skills plugins` glob, because the plugin's bundled-skill **symlink would re-collect
  the same tests twice**. Add a line per new skill.
- **Layout:** per-skill unit + integration tests under `skills/<name>/tests`; plugin hook/MCP tests
  under `plugins/<name>/tests`.
- **CI** runs the suite on **Linux/macOS/Windows**, plus: ruff (lint + format check), JSON-validates
  every plugin manifest, asserts the bundled-skill symlink resolves, and checks every `*.lock` is current.

**Pre-submit checklist**

- [ ] TDD: failing test first; full suite green
- [ ] `ruff check` + `ruff format` clean
- [ ] affected skill's `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] lockfiles re-locked if a script's deps changed
- [ ] `pytest.ini` has a line for any new test dir
- [ ] no vault / key file / `.env` / secret committed

## Conventions & guardrails (hard rules)

- **TDD always**; keep the suite green — CI is the gate.
- **`uv` is the toolchain.** ✅ `uv run` / `uvx`  ·  ❌ `pip`, `venv`, system `python`.
- **Never commit a real secret.** `*.kdbx`, `*.keyx`, `*.key`, `.env*` are gitignored; tests use
  throwaway fixtures in temp dirs.
- **Edit the source, not the mirror.** ✅ `skills/<name>/`  ·  ❌ `plugins/<name>/skills/<name>/` (symlink).
- **Agents read, humans write (kdbx).** An agent never authors or observes a secret *value* — full
  do/don'ts in [`skills/kdbx/AGENTS.md`](skills/kdbx/AGENTS.md) + [`SKILL.md`](skills/kdbx/SKILL.md).
- **Respect engine boundaries.** e.g. only `kdbx_core/vault.py` may import `pykeepass`; keep that
  interface engine-agnostic (per-skill rule — see the skill's `AGENTS.md`).
- **Lockfiles stay current.** Change a script's deps → `uv lock --script <file>`, commit the `*.lock`.
- **License hygiene.** Repo source is MIT; a runtime-only dependency under a copyleft license (e.g.
  kdbx's `pykeepass`, GPL-3.0) is fetched at runtime, **never bundled** — record it in the skill's `NOTICE`.

## Releasing & the marketplace

- Skills version **independently**. Tag releases `<skill>/v<version>` (e.g. `kdbx/v0.2.1`).
- Record changes in the affected skill's `CHANGELOG.md` under `## [Unreleased]`; on release, promote
  them to a version heading.
- **Skills** distribute straight from this repo via the Skills CLI
  (`npx skills add yarrasys/extensions@<name>`) — no separate publish step; the repo *is* the distribution.
- **Plugins** distribute via the marketplace: bump `version` in both
  `plugins/<name>/.claude-plugin/plugin.json` **and** `.claude-plugin/marketplace.json` (CI validates both).

## Per-skill deep dives

- **kdbx** — [`AGENTS.md`](skills/kdbx/AGENTS.md) (golden rules · engine boundary · lockfiles) ·
  [`SKILL.md`](skills/kdbx/SKILL.md) (operations · roles) ·
  [`references/`](skills/kdbx/references) (schema · security · fallback).

## Tracking

Bugs and ideas → [GitHub Issues](https://github.com/yarrasys/extensions/issues), each labelled with the
skill it concerns (e.g. `skill: kdbx`). Vulnerabilities → [SECURITY.md](SECURITY.md) (do not open public
issues). See also [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).
