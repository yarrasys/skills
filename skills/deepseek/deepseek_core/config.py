"""`.deepseek.json` discovery, defaults, and merge."""

import copy
import json
import pathlib

CONFIG_NAME = ".deepseek.json"

DEFAULTS = {
    "mode": "suggest",  # explicit | suggest | auto
    "model": "deepseek-v4-flash",
    "verifyDefault": "ruff check {file}",
    "auto": {
        "allowTasks": ["docstrings", "formatting", "boilerplate", "tests", "comments", "rename"],
        "allowGlobs": ["**/*.py"],
        "denyGlobs": [".github/**", "**/*secret*", "infra/**"],
        "maxCostUsdPerRun": 0.25,
        "maxCostUsdPerSession": 2.00,
        "isolate": True,
    },
}


def find_config(start: pathlib.Path) -> pathlib.Path | None:
    start = start.resolve()
    for d in (start, *start.parents):
        candidate = d / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(start: pathlib.Path) -> dict:
    path = find_config(start)
    user = json.loads(path.read_text()) if path else {}
    cfg = _deep_merge(DEFAULTS, user)
    if cfg["mode"] == "auto":
        cfg["auto"]["isolate"] = True  # non-overridable in auto
    return cfg
