# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.0,<2"]
# ///
"""kdbx MCP server — exposes the SAFE kdbx operations as typed tools.

Trust boundary (mirrors skills/kdbx/SKILL.md): this server NEVER returns a
plaintext secret. It intentionally omits `set`, `get --reveal`, and `export`,
which would push secret material through the tool call / transcript. Secret
values reach tools only via `run` — injected into a child process and never
printed.

The op_* functions are plain and dependency-free (testable without `mcp`
installed); only build_server()/__main__ import the MCP SDK.
"""

import os
import pathlib
import shlex
import subprocess

# The bundled skill CLI: <plugin_root>/skills/kdbx/kdbx.py (resolved through the
# symlink in-repo, or the dereferenced copy in the installed plugin cache).
KDBX = pathlib.Path(__file__).resolve().parent.parent / "skills" / "kdbx" / "kdbx.py"

# Safe operations exposed as MCP tools. Value-crossing ops are deliberately absent.
SAFE_OPS = ("kdbx_list", "kdbx_envs", "kdbx_check", "kdbx_get", "kdbx_run")
FORBIDDEN_OPS = ("set", "export", "reveal")  # never exposed — would leak plaintext


def _kdbx(args, cwd=None):
    """Run the kdbx skill CLI; return (combined_output, returncode)."""
    proc = subprocess.run(
        ["uv", "run", "--locked", str(KDBX), *args],
        cwd=cwd or os.getcwd(),
        capture_output=True,
        text=True,
    )
    return ((proc.stdout or "") + (proc.stderr or "")).strip(), proc.returncode


def op_list(group: str = "") -> str:
    """List entry paths for the active env (never values)."""
    out, _ = _kdbx(["list", group] if group else ["list"])
    return out


def op_envs() -> str:
    """List configured environments; mark the active one."""
    out, _ = _kdbx(["envs"])
    return out


def op_check() -> str:
    """Verify every mapped variable resolves; report drift."""
    out, code = _kdbx(["check"])
    return ("ok" if code == 0 else "drift (exit %d)" % code) + (("\n" + out) if out else "")


def op_get(path: str) -> str:
    """Show an entry, masked as '(set, hidden)'. Never reveals the value."""
    out, _ = _kdbx(["get", path])  # masked by default — never --reveal
    return out


def op_run(command: str) -> str:
    """Run a command with the active env's secrets injected; value never printed."""
    out, code = _kdbx(["run", "--", *shlex.split(command)])
    return ("(exit %d)" % code) + (("\n" + out) if out else "")


def build_server():
    """Construct the FastMCP server with the safe tools registered."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("kdbx")
    tools = [
        (op_list, "kdbx_list", "List kdbx entry paths (never values)."),
        (op_envs, "kdbx_envs", "List configured envs; mark the active one."),
        (op_check, "kdbx_check", "Verify every mapped variable resolves; report drift."),
        (op_get, "kdbx_get", "Show an entry, masked — never the value."),
        (op_run, "kdbx_run", "Run a command with secrets injected into its env; never printed."),
    ]
    for fn, name, desc in tools:
        server.tool(name=name, description=desc)(fn)
    return server


if __name__ == "__main__":
    build_server().run()
