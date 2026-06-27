"""CLI dispatch + core operations: init/set/get/list/delete/mv/envs."""

import argparse
import pathlib
import sys

from . import __version__, context, ops_extra, pointer, secretio, vault


def _ctx(args, banner):
    return context.resolve(
        getattr(args, "env", None),
        pathlib.Path.cwd(),
        banner=banner,
    )


def cmd_init(args) -> int:
    c = _ctx(args, banner=True)
    vault.create_vault(c.vault, c.keyfile)
    sys.stderr.write(
        f"created {c.vault}\n"
        f"KEYFILE: {c.keyfile} — back this up; losing it makes the vault unrecoverable.\n"
    )
    return 0


def cmd_set(args) -> int:
    c = _ctx(args, banner=True)
    gp, title, field = pointer.parse_entry_path(args.path)
    value = secretio.read_secret(args)
    vault.set_field(c.vault, c.keyfile, gp, title, field, value)
    if args.var:
        pt = pointer.load_pointer(c.pointer_path)
        pt["envs"].setdefault(c.env, {}).setdefault("vars", {})[args.var] = args.path
        pointer.write_pointer(c.pointer_path, pt)
        sys.stderr.write(f"modified tracked file {c.pointer_path.name} — review and commit\n")
    return 0


def cmd_get(args) -> int:
    c = _ctx(args, banner=False)
    gp, title, field = pointer.parse_entry_path(args.path)
    val = vault.get_field(c.vault, c.keyfile, gp, title, field)
    if args.clip:
        secretio.clipboard_copy(val)
        sys.stderr.write("copied to clipboard (clears shortly)\n")
    elif args.reveal:
        sys.stdout.write(val + "\n")
        sys.stderr.write("WARNING: value printed to stdout (scrollback/CI logs)\n")
    else:
        sys.stdout.write(secretio.MASK + "\n")
    return 0


def cmd_list(args) -> int:
    c = _ctx(args, banner=False)
    for path in vault.list_entries(c.vault, c.keyfile):
        if args.group and not path.startswith(args.group):
            continue
        sys.stdout.write(path + "\n")
    return 0


def cmd_delete(args) -> int:
    c = _ctx(args, banner=True)
    gp, title, _ = pointer.parse_entry_path(args.path)
    if args.purge and not secretio.confirm(
        f"permanently purge '{args.path}'? this cannot be undone"
    ):
        return 4
    (vault.purge if args.purge else vault.trash)(c.vault, c.keyfile, gp, title)
    return 0


def cmd_mv(args) -> int:
    c = _ctx(args, banner=True)
    vault.move(c.vault, c.keyfile, args.src, args.dst)
    return 0


def cmd_envs(args) -> int:
    pp = pointer.find_pointer(pathlib.Path.cwd())
    if pp is None:
        sys.stderr.write("kdbx envs: no .keepassxc.json found\n")
        return 2
    pt = pointer.load_pointer(pp)
    active, source = pointer.select_env(pt, getattr(args, "env", None))
    for e in pt.get("envs", {}):
        sys.stdout.write(f"{'* ' if e == active else '  '}{e}\n")
    sys.stderr.write(f"active: {active} (source: {source})\n")
    return 0


def _common(sp) -> None:
    sp.add_argument("--env")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdbx", description="kdbx — per-project/per-env KeePassXC credentials"
    )
    p.add_argument("--version", action="version", version=f"kdbx {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init")
    _common(sp)
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser("set")
    sp.add_argument("path")
    sp.add_argument("--var")
    sp.add_argument("--from-env", dest="from_env")
    sp.add_argument("--raw", action="store_true")
    _common(sp)
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser("get")
    sp.add_argument("path")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--reveal", action="store_true")
    g.add_argument("--clip", action="store_true")
    _common(sp)
    sp.set_defaults(fn=cmd_get)

    sp = sub.add_parser("list")
    sp.add_argument("group", nargs="?")
    _common(sp)
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("delete")
    sp.add_argument("path")
    sp.add_argument("--purge", action="store_true")
    _common(sp)
    sp.set_defaults(fn=cmd_delete)

    sp = sub.add_parser("mv")
    sp.add_argument("src")
    sp.add_argument("dst")
    _common(sp)
    sp.set_defaults(fn=cmd_mv)

    sp = sub.add_parser("envs")
    _common(sp)
    sp.set_defaults(fn=cmd_envs)

    ops_extra.register(sub, _common)
    return p


def dispatch(argv) -> int:
    args = _build_parser().parse_args(argv)
    wrapped = secretio.scrub_exceptions(args.command)(args.fn)
    rc = wrapped(args)
    return rc if isinstance(rc, int) else 0
