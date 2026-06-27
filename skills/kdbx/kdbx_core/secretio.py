"""Secret I/O: masked output, transcript-safe input, perms, dotenv, clipboard, error scrub."""

import functools
import getpass
import io as _io
import os
import pathlib
import subprocess
import sys

from dotenv import dotenv_values

MASK = "(set, hidden)"  # constant sentinel — encodes no length/prefix


def read_secret(args) -> str:
    """Read a secret value WITHOUT it ever crossing argv.

    Source: --from-env VAR, else getpass (TTY, with confirm), else stdin.
    Strips one trailing newline unless args.raw is set.
    """
    raw = getattr(args, "raw", False)
    src = getattr(args, "from_env", None)
    if src:
        if src not in os.environ:
            raise KeyError(f"--from-env {src} is not set")
        val = os.environ[src]
    elif sys.stdin.isatty():
        val = getpass.getpass("value: ")
        if getpass.getpass("confirm: ") != val:
            raise ValueError("values did not match")
        return val
    else:
        val = sys.stdin.read()
    if not raw and val.endswith("\n"):
        val = val[:-1]
        if val.endswith("\r"):
            val = val[:-1]
    return val


def confirm(prompt: str) -> bool:
    """Interactive y/N for an irreversible op. Refuses (returns False) when stdin
    is not a TTY — there is no non-interactive override (writes are a human role)."""
    if not sys.stdin.isatty():
        sys.stderr.write(f"{prompt}: refused — needs an interactive terminal to confirm\n")
        return False
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def restrict_perms(path) -> None:
    """0600 on POSIX; inheritance-stripped owner-only ACL on Windows."""
    path = str(path)
    if os.name == "nt":
        user = os.environ.get("USERNAME", "")
        subprocess.run(
            ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
            check=False,
            capture_output=True,
        )
    else:
        os.chmod(path, 0o600)


def atomic_write_secret(path, data: str, *, restrict: bool = True) -> None:
    path = pathlib.Path(path)
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    if restrict:
        restrict_perms(path)


def _q(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def render_dotenv(items: dict) -> str:
    return "".join(f"{k}={_q(v)}\n" for k, v in items.items())


def parse_dotenv(text: str) -> dict:
    parsed = dotenv_values(stream=_io.StringIO(text), interpolate=False)
    return {k: v for k, v in parsed.items() if v is not None}


def _clipboard_cmd():
    if sys.platform == "darwin":
        return ["pbcopy"]
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-Command", "Set-Clipboard"]
    if os.environ.get("WAYLAND_DISPLAY"):
        return ["wl-copy"]
    if os.environ.get("DISPLAY"):
        return ["xclip", "-selection", "clipboard"]
    return None


def clipboard_copy(value: str, *, clear_after: int = 15) -> None:
    cmd = _clipboard_cmd()
    if cmd is None:
        raise RuntimeError("no clipboard backend available")
    subprocess.run(cmd, input=value.encode("utf-8"), check=True)
    clear = _clipboard_cmd()
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import time,subprocess;time.sleep({int(clear_after)});"
            f"subprocess.run({clear!r}, input=b'')",
        ],
        start_new_session=True,
    )


def scrub_exceptions(op: str):
    """Wrap an op so values never leak via tracebacks; map kdbx_code to exit code."""

    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            try:
                return fn(*a, **k)
            except SystemExit:
                raise
            except BaseException as e:  # noqa: BLE001
                if os.environ.get("KDBX_DEBUG"):
                    import traceback

                    traceback.print_exc()
                sys.stderr.write(f"kdbx: {op} failed: {type(e).__name__}\n")
                return getattr(e, "kdbx_code", 1)

        return wrap

    return deco
