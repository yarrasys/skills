#!/usr/bin/env python3
"""kdbx leak-guard — a PreToolUse hook that blocks Bash commands which would
read or print a KeePassXC vault/keyfile via a tool other than kdbx itself.

Runs once per Bash tool call, so it is deliberately cheap and dependency-free
(stdlib only, no `uv`, Python 3.8+). It fails OPEN: anything that is not a clear
leak — including parse errors or a missing interpreter — allows the command. A
guard must never brick the user's shell.

Decision contract (see https://code.claude.com/docs/en/hooks):
  stdin  = PreToolUse JSON with tool_input.command
  deny   = print hookSpecificOutput JSON with permissionDecision "deny", exit 0
  allow  = no output, exit 0
"""

import json
import os
import re
import shlex
import sys

# Programs allowed to touch vault/keyfile paths: kdbx itself or the underlying
# KeePassXC CLI, neither of which prints a secret value by default.
_ALLOW = {"kdbx", "kdbx.py", "keepassxc-cli", "keepassxc"}

# A path that ends in a vault/keyfile extension (\b so trailing quotes/parens
# from substitutions like `$(cat dev.keyx)` still match).
_SECRET_RE = re.compile(r"\.(kdbx|keyx)\b", re.IGNORECASE)

# Shell operators separating independent command segments.
_SEG_SPLIT = re.compile(r"\|\||&&|[;|\n]")

# kdbx subcommands the agent must NOT run — writes are a human role (vault
# mutation) and these expose values. Reads/use (run, get-masked, list, check,
# envs, init, install-launcher) stay allowed.
_BLOCKED_OPS = {"set", "delete", "mv", "import", "rekey", "export"}


def _keepassxc_dir_fragments():
    """Lowercased, forward-slashed path fragments that mark the KeePassXC config
    dir, per skills/kdbx/kdbx_core/paths.py (KEEPASSXC_DIR is the dir itself;
    XDG_CONFIG_HOME / LOCALAPPDATA are its parent)."""
    frags = [".config/keepassxc/", "appdata/local/keepassxc/"]
    for var in ("KEEPASSXC_DIR", "XDG_CONFIG_HOME", "LOCALAPPDATA"):
        v = os.environ.get(var)
        if not v:
            continue
        frag = v.rstrip("/\\").lower().replace("\\", "/")
        frag += "/keepassxc/" if var in ("XDG_CONFIG_HOME", "LOCALAPPDATA") else "/"
        frags.append(frag)
    return frags


def _program(tokens):
    """First non-(VAR=val) token of a segment = the invoked program (basename)."""
    for tok in tokens:
        head = tok.split("=", 1)[0]
        if "=" in tok and not tok.startswith("-") and "/" not in head:
            continue  # leading VAR=value assignment
        return os.path.basename(tok)
    return ""


def _kdbx_op(tokens):
    """If a segment invokes the kdbx CLI (as the program, or via `uv run`), return
    its subcommand string; else None. The program check avoids false positives like
    `echo kdbx set ...`."""
    if not tokens:
        return None
    prog = _program(tokens)
    for i, tok in enumerate(tokens):
        if os.path.basename(tok) in ("kdbx", "kdbx.py"):
            if os.path.basename(tok) == prog or prog in ("uv", "uvx"):
                for nxt in tokens[i + 1 :]:
                    if not nxt.startswith("-"):
                        return nxt
                return ""
            return None
    return None


def _blocked_kdbx_op(tokens):
    """Return the offending op if this is an agent-issued write/expose kdbx call."""
    op = _kdbx_op(tokens)
    if op is None:
        return None
    if op in _BLOCKED_OPS:
        return op
    if op == "get" and ("--reveal" in tokens or "--clip" in tokens):
        return "get --reveal/--clip"
    return None


def decide(command):
    """Return a human-readable deny reason if `command` (a) issues an agent
    write/expose kdbx op, or (b) reads a KeePassXC vault/keyfile via a non-kdbx
    tool; else None (allow)."""
    if not command or not command.strip():
        return None
    for raw_seg in _SEG_SPLIT.split(command):
        seg = raw_seg.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()

        # (a) writes / value-exposure are a human role — the agent must not run them.
        op = _blocked_kdbx_op(tokens)
        if op:
            return (
                "kdbx role-guard: '%s' is a human-only operation (it mutates the vault "
                "or exposes a secret value). Don't run it as the agent — give the command "
                "to the human to run in their own terminal (or via `!kdbx ...`)." % op
            )

        # (b) the agent must not read a vault/keyfile via a non-kdbx tool.
        norm = seg.replace("\\", "/")
        m = _SECRET_RE.search(norm)
        frag = next((f for f in _keepassxc_dir_fragments() if f in norm.lower()), None)
        if not m and not frag:
            continue
        prog = _program(tokens) if tokens else ""
        allowed = prog in _ALLOW or (prog in {"uv", "uvx"} and "kdbx" in seg.lower())
        if not allowed:
            hint = m.group(0) if m else "a KeePassXC config path"
            return (
                "kdbx leak-guard: '%s' would read a KeePassXC vault/keyfile (%s). "
                "Use `kdbx run -- ...` to inject secrets without printing them."
                % (prog or "command", hint)
            )
    return None


def main():
    try:
        data = json.load(sys.stdin)
        command = (data.get("tool_input") or {}).get("command", "")
        reason = decide(command)
    except Exception:
        return 0  # fail open — never break the shell
    if reason:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
