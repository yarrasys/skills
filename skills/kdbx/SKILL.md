---
name: kdbx
description: Read/write KeePassXC .kdbx vaults to manage per-project/per-env credentials (init/get/set/list/delete/run/export/import/check/envs/mv/rekey). Replaces .env as the source of truth; injects secrets into commands without printing them. Use when a project needs to store, retrieve, or run commands with secrets/API keys/tokens.
---

# kdbx — KeePassXC credentials skill

Manage a project's secrets in **per-project, per-env** KeePassXC vaults
(`<keepassxc-dir>/<project>/<env>.kdbx`, key-file-only, KDBX4+Argon2) and get them
into tools **without printing them into the transcript, logs, or shell history**.

## When to use

- A project needs to store / retrieve / rotate secrets, API keys, or tokens.
- You need to run a command that requires secrets in its env (`kdbx run -- …`).
- You're replacing a `.env` file with a managed source of truth.

Discovery is automatic: kdbx walks up from the cwd to a committed `.keepassxc.json`
(see `references/schema.md`). Active env = `--env` › `$KDBX_ENV` › the pointer's `defaultEnv`.

## Invocation

The skill is a single uv-run script. From the project dir:

```
uv run --locked <SKILL_DIR>/kdbx.py <op> [args]
```

`<SKILL_DIR>` is this skill's directory (where this SKILL.md lives). uv is required;
if it's missing, install it (`curl -LsSf https://astral.sh/uv/install.sh | sh`) — do not
fall back to system Python. First run provisions a Python + deps and caches them.

## Operations

| Op | Use |
|----|-----|
| `init [--env E]` | create the vault + keyfile for an env (refuses to overwrite; 0600) |
| `set PATH [--var NAME] [--from-env VAR] [--raw]` | store a secret (value via stdin/`--from-env`, never argv); optionally register a var mapping |
| `get PATH [--reveal\|--clip]` | masked by default; `--reveal` prints; `--clip` copies (auto-clears) |
| `list [GROUP]` | list entry paths (never values; excludes Recycle Bin) |
| `delete PATH [--purge]` | soft-delete to Recycle Bin; `--purge` removes permanently |
| `mv OLD NEW` | rename/move an entry; rewrites affected var mappings |
| `run [--env E] -- CMD…` | inject the env's mapped vars into a child process and exec it |
| `export [--out F]` | render mapped vars as a 0600 dotenv (for tools that need a file) |
| `import FILE` | read an existing `.env` into the vault + var map |
| `check` | verify every mapped var resolves (non-zero exit on drift) |
| `envs` | list configured envs; mark the active one |
| `rekey [--env E]` | rotate the keyfile |
| `install-launcher [--dir D] [--force]` | write an opt-in `kdbx` PATH shim (default `~/.local/bin`); no vault needed |

Exit codes: `0` ok · `2` not-found · `3` locked/keyfile-missing · `4` destructive op not confirmed
(`delete --purge` / `rekey` without an interactive `y`; also `install-launcher` over a foreign file
without `--force`) · `5` drift · `6` vault-changed · `7` runtime.

## Roles — who runs what

🔑 **The agent reads and uses secrets; the human performs writes.**

- **Agent (you, in this session):** `run`, `get` (masked), `list`, `check`, `envs`, `init`.
  For anything that mutates the vault (`set` / `delete` / `mv` / `import` / `rekey`) or exposes a
  value (`get --reveal` / `--clip`, `export`), **emit the exact command for the human** to run in
  their own terminal (or via `!kdbx …` in this prompt) — do not run it yourself.
- **Human:** runs those write/expose commands; irreversible ones (`delete --purge`, `rekey`) ask
  for an interactive `y/N`.
- The kdbx **plugin enforces** this with a `PreToolUse` hook (your write commands are blocked; the
  human's `!` commands pass through untouched). The bare skill states it as a contract.
- The real **prod** boundary is **key-file possession**, not a name match — you can only reach an
  env's secrets if its key file exists on this machine.

## Security — do / don't (read before using)

- 🔑 **Never author or observe a secret value.** Your job is the entry **PATH / var-name only**.
  To store a value, the **human** runs `set` and pipes the secret on their terminal
  (`kdbx set api/openai < secret.txt`, or types it at the `getpass` prompt).
- ❌ **Never** do `echo SECRET | kdbx set …` or `export SECRET=…; kdbx set --from-env SECRET`
  inside this session — that puts the plaintext in the transcript. Both are forbidden.
- Prefer `kdbx run -- <cmd>` (inject, never print) over `export`/`get --reveal`.
- The **keyfile is the sole secret**; losing it makes the vault unrecoverable. Back it up
  out-of-band.

## References

- `references/schema.md` — the full `.keepassxc.json` schema + path grammar.
- `references/fallback.md` — read-only `keepassxc-cli` commands (per-OS binary locations).
- `references/security.md` — threat model, trust boundary, rotation / leak runbook.
