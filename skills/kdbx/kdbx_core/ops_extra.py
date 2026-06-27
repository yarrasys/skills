"""Operations: run / export / import / check / rekey / install-launcher."""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

from . import context, launcher, pointer, secretio, vault


def _ctx(args, banner):
    return context.resolve(
        getattr(args, "env", None),
        pathlib.Path.cwd(),
        banner=banner,
    )


def resolve_vars(c, allow_missing=False) -> dict:
    out = {}
    for var, path in c.vars.items():
        gp, title, field = pointer.parse_entry_path(path)
        try:
            out[var] = vault.get_field(c.vault, c.keyfile, gp, title, field)
        except KeyError:
            if not allow_missing:
                e = KeyError(f"unresolved var {var} -> {path}")
                e.kdbx_code = 5
                raise e
    return out


def cmd_run(args) -> int:
    c = _ctx(args, banner=True)
    cmd = list(args.argv)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.stderr.write("kdbx run: no command given (use: run -- <cmd> ...)\n")
        return 2
    env = dict(os.environ)
    env.update(resolve_vars(c, args.allow_missing))
    exe = shutil.which(cmd[0]) or cmd[0]
    return subprocess.run([exe, *cmd[1:]], env=env).returncode


def cmd_export(args) -> int:
    c = _ctx(args, banner=True)
    items = resolve_vars(c, args.allow_missing)
    text = secretio.render_dotenv(items)
    if args.out:
        _gitignore_notice(pathlib.Path(args.out))
        secretio.atomic_write_secret(args.out, text)
        sys.stderr.write(f"wrote {len(items)} vars to {args.out} (0600)\n")
    else:
        sys.stdout.write(text)
    return 0


def cmd_import(args) -> int:
    c = _ctx(args, banner=True)
    items = secretio.parse_dotenv(pathlib.Path(args.file).read_text())
    pt = pointer.load_pointer(c.pointer_path)
    vars_map = pt["envs"].setdefault(c.env, {}).setdefault("vars", {})
    for k, v in items.items():
        path = f"imported/{k}:password"
        gp, title, field = pointer.parse_entry_path(path)
        vault.set_field(c.vault, c.keyfile, gp, title, field, v)
        vars_map[k] = path
    pointer.write_pointer(c.pointer_path, pt)
    sys.stderr.write(
        f"imported {len(items)} vars. Reminder: remove/gitignore the source .env; "
        "rotate anything ever committed.\n"
    )
    return 0


def cmd_check(args) -> int:
    c = _ctx(args, banner=False)
    missing = []
    for var, path in c.vars.items():
        gp, title, field = pointer.parse_entry_path(path)
        try:
            vault.get_field(c.vault, c.keyfile, gp, title, field)
        except KeyError:
            missing.append(f"{var} -> {path}")
    for m in missing:
        sys.stdout.write(f"MISSING {m}\n")
    return 0 if not missing else 5


def cmd_rekey(args) -> int:
    c = _ctx(args, banner=True)
    if not secretio.confirm(f"rotate the key file for env '{c.env}'? the old key file is deleted"):
        return 4
    newkf = pathlib.Path(str(c.keyfile) + ".new")
    vault.rekey(c.vault, c.keyfile, newkf)
    os.replace(newkf, c.keyfile)
    sys.stderr.write(
        "rekeyed. A prior keyfile+vault leak means secrets are already exposed — "
        "rotate at source.\n"
    )
    return 0


def cmd_install_launcher(args) -> int:
    try:
        dest = launcher.install(args.dir, force=args.force)
    except FileExistsError as e:
        sys.stderr.write(f"kdbx install-launcher: {e}\n")
        return 4
    sys.stderr.write(f"wrote launcher {dest} (0755)\n")
    if not launcher.on_path(dest.parent):
        sys.stderr.write(f"NOTE: {dest.parent} is not on your PATH — add it so `kdbx` resolves.\n")
    sys.stderr.write(
        "Requires `uv` on PATH. Agent invocation is unchanged (uv run --locked kdbx.py).\n"
    )
    return 0


def _gitignore_notice(path: pathlib.Path) -> None:
    sys.stderr.write(f"NOTE: ensure {path.name} is gitignored (it holds plaintext secrets)\n")


def register(sub, common) -> None:
    sp = sub.add_parser("run")
    sp.add_argument("--allow-missing", dest="allow_missing", action="store_true")
    sp.add_argument("argv", nargs=argparse.REMAINDER)
    common(sp)
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("export")
    sp.add_argument("--out")
    sp.add_argument("--allow-missing", dest="allow_missing", action="store_true")
    common(sp)
    sp.set_defaults(fn=cmd_export)

    sp = sub.add_parser("import")
    sp.add_argument("file")
    common(sp)
    sp.set_defaults(fn=cmd_import)

    sp = sub.add_parser("check")
    common(sp)
    sp.set_defaults(fn=cmd_check)

    sp = sub.add_parser("rekey")
    common(sp)
    sp.set_defaults(fn=cmd_rekey)

    # Opt-in human ergonomics: no vault/pointer needed, so no --env/--yes.
    sp = sub.add_parser("install-launcher")
    sp.add_argument("--dir", default="~/.local/bin")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_install_launcher)
