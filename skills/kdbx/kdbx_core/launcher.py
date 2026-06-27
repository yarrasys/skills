"""Opt-in PATH launcher: a self-resolving `kdbx` shim (issue #10).

Agent/CLI invocation stays `uv run --locked .../kdbx.py <op>`. This is purely a
human ergonomics affordance, written only on an explicit `kdbx install-launcher`
so a credential tool never adds a binary to PATH on its own.

The shim resolves the skill at *run* time (preferring the stable Skills-CLI
install, falling back to the newest versioned plugin-cache copy), so it survives
plugin updates without being rewritten.
"""

import os
import pathlib

MARKER = "# kdbx-managed-launcher"

SHIM = f"""\
#!/bin/sh
# kdbx launcher — managed by `kdbx install-launcher`. Resolves the skill at run
# time so it survives plugin updates. Regenerate with `kdbx install-launcher --force`.
{MARKER}
set -e

py=""
if [ -f "$HOME/.claude/skills/kdbx/kdbx.py" ]; then
    py="$HOME/.claude/skills/kdbx/kdbx.py"               # 1) stable Skills-CLI install
else                                                     # 2) newest plugin-cache copy
    py=$(ls -d "$HOME"/.claude/plugins/cache/*/kdbx/*/skills/kdbx/kdbx.py 2>/dev/null \\
         | sort -V | tail -n 1)
fi

if [ -z "$py" ] || [ ! -f "$py" ]; then
    echo "kdbx: could not locate kdbx.py. Install the skill with:" >&2
    echo "  npx skills add yarrasys/skills@kdbx -g -y" >&2
    exit 127
fi

exec uv run --locked "$py" "$@"
"""


def install(dest_dir, *, force: bool = False) -> pathlib.Path:
    """Write the `kdbx` shim into dest_dir (0755). Refuses to clobber a file we
    didn't write unless force=True. Returns the launcher path."""
    dest_dir = pathlib.Path(dest_dir).expanduser()
    dest = dest_dir / "kdbx"
    if dest.exists() and not force and MARKER not in dest.read_text(errors="replace"):
        raise FileExistsError(
            f"{dest} exists and is not a kdbx-managed launcher; pass --force to overwrite"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name("kdbx.tmp")
    tmp.write_text(SHIM)
    tmp.chmod(0o755)
    os.replace(tmp, dest)
    return dest


def on_path(dest_dir) -> bool:
    """True if dest_dir is on the current PATH."""
    target = str(pathlib.Path(dest_dir).expanduser())
    return target in os.environ.get("PATH", "").split(os.pathsep)
