<div align="center">

# 🔐 kdbx — KeePassXC credentials skill for Claude Code

**Manage per-project, per-environment secrets in key-file-only KeePassXC vaults — and inject them into commands without ever printing them.**

A [Claude Code](https://claude.com/claude-code) skill (and standalone CLI) that replaces `.env`
as the source of truth for secrets, API keys, and tokens.

[![CI](https://github.com/yarrasys/skills/actions/workflows/ci.yml/badge.svg)](https://github.com/yarrasys/skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/yarrasys/skills/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Claude Code skill](https://img.shields.io/badge/Claude%20Code-skill-8A2BE2.svg)](SKILL.md)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

</div>

---

`kdbx` is a small, self-contained tool for **secrets management** in development: one
[KeePassXC](https://keepassxc.org/) `.kdbx` vault **per project, per environment**, unlocked by a
**key file only** (no master password, fully scriptable), using **KDBX4 + Argon2**. A committed
`.keepassxc.json` pointer maps environment-variable names to vault entries, so a repository
documents its own secret contract — without exposing any values.

It's built for **AI coding agents**: the agent handles entry paths and variable names only and
**never authors or observes a secret value**. Secrets reach your tools via `kdbx run -- <cmd>`
(injected into the child process, never printed) or an explicit, gitignored `kdbx export`.

## Install

With the [Skills CLI](https://skills.sh/) (recommended):

```bash
npx skills add yarrasys/skills@kdbx          # add -g -y for a global, non-interactive install
```

It installs into your agent's skills directory and is discovered via `SKILL.md`. Invoke the CLI as
`uv run --locked <SKILL_DIR>/kdbx.py <op>` (the skill's `SKILL.md` documents the exact path).

<details>
<summary>Manual install</summary>

```bash
git clone https://github.com/yarrasys/skills
ln -s "$PWD/skills/skills/kdbx" ~/.claude/skills/kdbx
```
</details>

> **Plugin (optional).** For an *enforced* secret-leak guard hook, `/kdbx:*` commands, and safe MCP
> tools on top of this skill, install the [kdbx plugin](../../plugins/kdbx):
> `/plugin marketplace add yarrasys/skills` then `/plugin install kdbx@yarrasys-skills`.

## Quickstart

![kdbx in action: init → set → get → run → check, with the secret never printed](docs/demo.gif)

<sub>Demo recorded with [VHS](https://github.com/charmbracelet/vhs) — regenerate with `vhs skills/kdbx/docs/demo.tape` from the repo root (see [`docs/demo.tape`](docs/demo.tape)).</sub>

```bash
# A pointer at your repo root (committed; contains no secrets)
cat > .keepassxc.json <<'JSON'
{ "project": "ideas", "defaultEnv": "dev",
  "envs": { "dev": { "vars": { "OPENAI_API_KEY": "api/openai:password" } } } }
JSON

KDBX=~/.claude/skills/kdbx/kdbx.py
uv run --locked "$KDBX" init                       # create the dev vault + key file (0600)
uv run --locked "$KDBX" set api/openai < key.txt   # store a secret from a file (never on argv)
uv run --locked "$KDBX" get api/openai             # -> (set, hidden)
uv run --locked "$KDBX" run -- npm run dev         # OPENAI_API_KEY is in the child env, never printed
```

## Operations

| Op | Use |
|----|-----|
| `init [--env E]` | create the vault + key file for an env (refuses to overwrite; 0600) |
| `set PATH [--var NAME] [--from-env VAR] [--raw]` | store a secret (value via stdin/`--from-env`, never argv); optionally register a var mapping |
| `get PATH [--reveal\|--clip]` | masked by default; `--reveal` prints; `--clip` copies (auto-clears) |
| `list [GROUP]` | list entry paths (never values; excludes Recycle Bin) |
| `delete PATH [--purge]` | soft-delete to Recycle Bin; `--purge` removes permanently |
| `mv OLD NEW` | rename/move an entry; rewrites affected var mappings |
| `run [--env E] -- CMD…` | inject the env's mapped vars into a child process and run it |
| `export [--out F]` | render mapped vars as a 0600 dotenv (for tools that need a file) |
| `import FILE` | read an existing `.env` into the vault + var map |
| `check` | verify every mapped var resolves (non-zero exit on drift) |
| `envs` | list configured envs; mark the active one |
| `rekey [--env E]` | rotate the key file |

Exit codes: `0` ok · `2` not-found · `3` locked/key-file-missing · `4` confirmation-required
(prod or `$KDBX_ENV`-inherited mutating op without `--yes`) · `5` drift · `6` vault-changed · `7` runtime.

## How it works

- **Discovery.** kdbx walks up from the current directory to the nearest committed
  `.keepassxc.json`. The active environment is `--env` › `$KDBX_ENV` › the pointer's `defaultEnv`.
- **The pointer** declares each env's `vault`/`keyFile` (or omits them to derive default paths)
  and a `vars` map of `ENV_VAR → "group/Title:field"`. See [`references/schema.md`](references/schema.md).
- **The vault** is a standard KDBX4 + Argon2 file unlocked by its key file. The key file is the
  sole secret — back it up; losing it makes the vault unrecoverable.

## Security

- **The agent never authors or observes a secret value** — it handles paths and variable names
  only. Store values by piping on your own terminal (`kdbx set PATH < secret.txt`) or via an outer
  orchestrator's `--from-env VAR`. Never `echo SECRET | kdbx set …`.
- Vault, key file, and exported `.env` are `0600` (POSIX) / owner-only ACL (Windows).
- Full threat model, `run` trust boundary, and rotation/leak runbooks: [`references/security.md`](references/security.md).
- Reporting vulnerabilities: [SECURITY.md](https://github.com/yarrasys/skills/blob/main/SECURITY.md).

## Requirements

- [**uv**](https://docs.astral.sh/uv/) — the only prerequisite. It provides a compatible Python
  (≥3.10) and the locked dependencies on first run, then caches them.
- The engine [`pykeepass`](https://github.com/libkeepass/pykeepass) (**GPL-3.0**) is fetched at
  runtime and **never bundled** by this MIT-licensed project — see
  [NOTICE](https://github.com/yarrasys/skills/blob/main/NOTICE).

## How it compares

- **vs. a `.env` file** — encrypted at rest, out of the repo, injected without writing plaintext;
  a reviewable contract instead of an untracked file that drifts.
- **vs. raw `keepassxc-cli`** — adds the per-project/per-env convention, the `vars` map,
  `run`/`export`/`import`/`check`, and agent-transcript safety. (`keepassxc-cli` remains a
  read-only fallback — see [`references/fallback.md`](references/fallback.md).)
- **vs. cloud secret managers** — no network, no telemetry, no account; local files only.

## Development & contributing

See [CONTRIBUTING.md](https://github.com/yarrasys/skills/blob/main/CONTRIBUTING.md) and
[AGENTS.md](https://github.com/yarrasys/skills/blob/main/AGENTS.md). The design spec and TDD plan
live under [`docs/superpowers/`](https://github.com/yarrasys/skills/tree/main/docs/superpowers).
Windows verification is tracked in [issues](https://github.com/yarrasys/skills/issues?q=is%3Aissue+label%3A%22skill%3A+kdbx%22).

## License

[MIT](https://github.com/yarrasys/skills/blob/main/LICENSE). The engine `pykeepass` is GPL-3.0,
fetched at runtime and never redistributed here — see
[NOTICE](https://github.com/yarrasys/skills/blob/main/NOTICE). *(Not legal advice.)*
