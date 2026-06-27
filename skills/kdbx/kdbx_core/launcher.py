"""Opt-in PATH launcher: a self-resolving `kdbx` shim (issue #10).

Agent/CLI invocation stays `uv run --locked .../kdbx.py <op>`. This is purely a
human ergonomics affordance, written only on an explicit `kdbx install-launcher`
so a credential tool never adds a binary to PATH on its own.

The shim resolves the skill at *run* time and picks the **newest version** across
*all* install channels — the Skills-CLI install (`~/.claude/skills/kdbx`, updated by
`npx skills add`) and every plugin-cache copy (updated by `/plugin update`). Picking
by version, not location, means an update from either channel takes effect and a
stale copy in the other channel can never silently shadow it (issue #14).
"""

import os
import pathlib

MARKER = "# kdbx-managed-launcher"

SHIM = f"""\
#!/bin/sh
# kdbx launcher — managed by `kdbx install-launcher`. Resolves the NEWEST installed
# kdbx at run time across the Skills-CLI install and all plugin-cache copies, so an
# update from either channel wins. Regenerate with `kdbx install-launcher --force`.
{MARKER}
set -e

# Pick the highest-versioned kdbx.py among every install channel. Each candidate's
# version is read from its sibling kdbx_core/__init__.py (works for both layouts).
best_ver=""; py=""; first=""
for cand in "$HOME/.claude/skills/kdbx/kdbx.py" \\
            "$HOME"/.claude/plugins/cache/*/kdbx/*/skills/kdbx/kdbx.py; do
    [ -f "$cand" ] || continue
    [ -z "$first" ] && first="$cand"
    ver=$(grep __version__ "$(dirname "$cand")/kdbx_core/__init__.py" 2>/dev/null \\
          | head -n 1 | tr -dc '0-9.')
    [ -n "$ver" ] || continue
    if [ -z "$best_ver" ] || \\
       [ "$(printf '%s\\n%s\\n' "$best_ver" "$ver" | sort -V | tail -n 1)" = "$ver" ]; then
        best_ver="$ver"; py="$cand"
    fi
done
[ -z "$py" ] && py="$first"   # fallback: a runnable copy we just could not version

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
