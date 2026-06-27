"""Environment resolution. The active vault is chosen from the committed pointer;
the only real prod boundary is key-file possession, not a name match (see SKILL.md
Roles). Agent vs human is enforced by the plugin hook, not here."""

import pathlib
import sys
from dataclasses import dataclass

from . import pointer

EXIT = {
    "ok": 0,
    "not_found": 2,
    "locked": 3,
    "confirm": 4,  # destructive op not confirmed
    "drift": 5,
    "changed": 6,
    "preflight": 7,
}


@dataclass
class Context:
    env: str
    source: str
    vault: pathlib.Path
    keyfile: pathlib.Path
    vars: dict
    pointer_path: pathlib.Path | None


def resolve(cli_env, start_dir, *, banner: bool = True) -> Context:
    pp = pointer.find_pointer(pathlib.Path(start_dir))
    if pp is None:
        err = FileNotFoundError("no .keepassxc.json found (run from inside a configured repo)")
        err.kdbx_code = 2
        raise err
    pt = pointer.load_pointer(pp)
    env, source = pointer.select_env(pt, cli_env)
    ep = pointer.resolve_env(pt, env, pp.parent)
    if banner:  # tell the human/agent which vault is being touched
        sys.stderr.write(f"ACTIVE ENV: {env}  vault={ep.vault}  (source: {source})\n")
    return Context(env, source, ep.vault, ep.keyfile, ep.vars, pp)
