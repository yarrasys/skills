"""CLI dispatch: check / init / config / delegate / apply."""

import argparse
import json
import os
import pathlib
import shutil
import sys

from . import __version__, config, runner
from .ops_delegate import cmd_apply, cmd_delegate  # added in Task 8


def cmd_config(args) -> int:
    cfg = config.load_config(pathlib.Path.cwd())
    sys.stdout.write(json.dumps(cfg, indent=2) + "\n")
    return 0


def _ensure_gitignored(cwd: pathlib.Path) -> None:
    gitignore = cwd / ".gitignore"
    entry = ".deepseek/"
    if gitignore.is_file():
        contents = gitignore.read_text()
        if entry in contents.splitlines():
            return
        needs_newline = bool(contents) and not contents.endswith("\n")
        with gitignore.open("a") as f:
            f.write(("\n" if needs_newline else "") + entry + "\n")
        sys.stderr.write(f"appended {entry!r} to .gitignore\n")
    else:
        gitignore.write_text(entry + "\n")
        sys.stderr.write(f"created .gitignore with {entry!r}\n")


def cmd_init(args) -> int:
    dest = pathlib.Path.cwd() / config.CONFIG_NAME
    if dest.exists():
        sys.stderr.write(f"deepseek: {dest.name} already exists — refusing to overwrite\n")
        return 4
    dest.write_text(json.dumps(config.DEFAULTS, indent=2) + "\n")
    sys.stderr.write(f"created {dest.name} — review and commit\n")
    _ensure_gitignored(pathlib.Path.cwd())
    return 0


def cmd_check(args) -> int:
    ok = True
    if shutil.which("claude"):
        sys.stderr.write("ok: claude on PATH\n")
    else:
        sys.stderr.write("MISSING: claude CLI not on PATH — install Claude Code\n")
        ok = False
    if shutil.which("git"):
        sys.stderr.write("ok: git on PATH\n")
    else:
        sys.stderr.write("MISSING: git not on PATH\n")
        ok = False
    if runner.resolve_key(os.environ):
        sys.stderr.write("ok: DEEPSEEK_API_KEY present\n")
    else:
        sys.stderr.write(
            "MISSING: no DEEPSEEK_API_KEY — set it, or have a human run:\n"
            "  kdbx set api/deepseek --var DEEPSEEK_API_KEY\n"
        )
        ok = False
    sys.stderr.write("(offline check — key/endpoint liveness verified on first delegate)\n")
    return 0 if ok else 3


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deepseek", description="deepseek — delegate dev tasks to DeepSeek"
    )
    p.add_argument("--version", action="version", version=f"deepseek {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("config").set_defaults(fn=cmd_config)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("check").set_defaults(fn=cmd_check)

    d = sub.add_parser("delegate")
    d.add_argument("--task", required=True)
    d.add_argument("--file", action="append", default=[], dest="files")
    d.add_argument("--dir", dest="dir")
    d.add_argument("--in-place", action="store_true", dest="in_place")
    d.add_argument("--verify", dest="verify")
    d.add_argument("--model", dest="model")
    d.set_defaults(fn=cmd_delegate)

    a = sub.add_parser("apply")
    a.add_argument("patch")
    a.set_defaults(fn=cmd_apply)
    return p


def dispatch(argv) -> int:
    args = _build_parser().parse_args(argv)
    rc = args.fn(args)
    return rc if isinstance(rc, int) else 0
