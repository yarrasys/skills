# kdbx — Claude Code plugin

A thin **plugin wrapper** around the [`kdbx` skill](../../skills/kdbx) that adds
capabilities a skill alone cannot provide. The skill stays the portable source
of truth; this plugin shares it by symlink (no duplication) and layers on:

- 🔒 **An enforced secret-leak guard** (`PreToolUse` hook) — a skill can only
  *advise* "never print a secret"; this hook *enforces* it.
- 🧰 **A safe MCP server** — typed tools for the non-value-crossing operations.
- ⌨️ **`/kdbx:*` slash commands** — ergonomic entry points.

The standalone skill remains available and portable (Agent SDK / claude.ai);
the plugin is **additive and Claude Code-only**. Use the skill if you just want
the model-invoked capability; add the plugin when you want enforcement,
slash commands, or MCP tools.

## Install

This repository doubles as a plugin marketplace.

```text
/plugin marketplace add yarrasys/skills
/plugin install kdbx@yarrasys-skills
```

(`uv` is required at runtime, as for the skill.)

## What it adds

### Guard hook (`hooks/`)

A `PreToolUse` hook on `Bash` that **enforces the agent/human boundary**, denying two classes of
*agent-issued* command (it fires only for model tool calls — your own `!`-prefixed commands pass
through untouched, so you can write in the same window):

| Denied (agent) | Why | Allowed (agent) |
|----------------|-----|-----------------|
| `kdbx set …`, `kdbx delete …`, `kdbx mv …`, `kdbx import …`, `kdbx rekey` | vault writes are a human role | `kdbx run -- …`, `kdbx get api/x` (masked) |
| `kdbx get … --reveal`/`--clip`, `kdbx export …` | expose a secret value | `kdbx list` / `check` / `envs` / `init` |
| `cat dev.keyx`, `base64 …/dev.keyx`, `cp vault.kdbx /tmp` | read a vault/key file directly | `keepassxc-cli show …`, `cat README.md` |

Design notes:
- **Two checks.** A *role-guard* (writes/value-exposure via `kdbx` are human-only) and a *leak-guard*
  (reading a `*.kdbx`/`*.keyx` file or a KeePassXC config-dir path via a non-`kdbx` tool).
- **Precise, not broad.** It does **not** block `.env` reads — `.env` is ubiquitous and legitimately
  read, and kdbx's premise is that secrets shouldn't live there.
- **Fails open.** Any parse error, ambiguity, or missing `python3` allows the command — a guard must
  never brick your shell.
- For a blocked write, the agent **emits the command for you to run** (`!kdbx set …` or your terminal).

Disable it by removing `hooks/hooks.json` (or uninstall the plugin) and keep using the standalone
skill — which then states the boundary as a contract rather than enforcing it.

### MCP server (`mcp/server.py`)

Exposes the **safe** operations as typed tools: `kdbx_list`, `kdbx_envs`,
`kdbx_check`, `kdbx_get` (masked), and `kdbx_run` (injects secrets into a child
process; the value is never printed).

🔑 **Trust boundary:** the server intentionally **omits `set`, `get --reveal`,
and `export`** — those would push plaintext through the tool call / transcript,
breaking the skill's "the agent never authors or observes a secret value" rule.
To store a secret, a human runs `kdbx set` on their own terminal (see
[`/kdbx:set`](commands/set.md)).

### Slash commands (`commands/`)

`/kdbx:run`, `/kdbx:check`, `/kdbx:list`, `/kdbx:init`, `/kdbx:set` — thin
wrappers over the skill CLI. `/kdbx:set` guides the human to provide the value
on their own terminal, never through the model.

## Layout

```text
plugins/kdbx/
├── .claude-plugin/plugin.json
├── skills/kdbx -> ../../../skills/kdbx   # symlink: shared skill (dereferenced + copied on install)
├── hooks/{hooks.json, guard.py}          # PreToolUse leak-guard (stdlib-only, fails open)
├── commands/*.md                         # /kdbx:* slash commands
├── mcp/{server.py, server.py.lock}       # safe MCP tools
└── .mcp.json
```

Tests live in the repo's top-level `tests/` (`test_plugin_guard.py`,
`test_plugin_mcp.py`) and run in CI alongside the skill's suite.
