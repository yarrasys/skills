# DeepSeek Delegation Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `deepseek` skill that delegates a bounded dev task to a nested headless `claude` process running on DeepSeek's Anthropic-compatible endpoint, returning a compact receipt to the parent session.

**Architecture:** A PEP-723 `uv`-run CLI (`deepseek.py`) over a `deepseek_core/` package. The core resolves a per-project `.deepseek.json` config, resolves the DeepSeek key (kdbx → env), spawns `claude -p … --output-format json` with `ANTHROPIC_BASE_URL` pointed at DeepSeek inside a throwaway git worktree (default) or in-place, runs a verify gate, and shapes a compact JSON receipt. Pure logic (config, guardrails, receipt, arg/env builders) is isolated from side-effects (subprocess spawn, git worktree) for deterministic unit tests; a fake `claude` binary on `PATH` drives integration tests with no network.

**Tech Stack:** Python ≥3.10 (stdlib only — `subprocess`, `json`, `pathlib`, `fnmatch`, `argparse`, `uuid`), `uv` toolchain, `git`, `pytest`. External runtime prereqs (not Python deps): `claude` CLI, `git`.

## Global Constraints

- **Toolchain:** `uv` only — ✅ `uv run`/`uvx`, ❌ `pip`/`venv`/system `python`. Python `>=3.10`.
- **Form:** single-file PEP-723 entry `skills/deepseek/deepseek.py` + a `deepseek_core/` package. Mirror kdbx's `_preflight()`/`main()`/`dispatch()` shape.
- **No third-party Python deps** in v1 (stdlib only). PEP-723 `dependencies = []`. Still run `uv lock --script skills/deepseek/deepseek.py` and commit `deepseek.py.lock`.
- **Secrets:** the DeepSeek key is NEVER printed to stdout/stderr, written into `.deepseek.json`, or committed. On a missing key, emit the exact kdbx `set` command for the human — never author or observe the value.
- **Constants (verbatim):** endpoint `https://api.deepseek.com/anthropic`; default model `deepseek-v4-flash`; child env var names `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `DEEPSEEK_DELEGATE_DEPTH`.
- **Exit codes:** `0` ok · `2` config-required-but-missing · `3` key missing · `4` recursion refused · `5` verify failed · `6` budget/deny withheld · `7` runtime (`claude`/`git` missing, child crash).
- **Isolation:** worktree+patch is the default; `--in-place` opts into direct edits; `auto` mode forces isolation regardless of flag.
- **v1 scope note:** `maxCostUsdPerRun` is enforced (from the single receipt); `maxCostUsdPerSession` is parsed but NOT enforced in v1 (needs a session ledger — deferred). Document this in SKILL.md.
- **TDD:** failing test first. Keep suite green. `ruff format` + `ruff check` clean. CHANGELOG under `## [Unreleased]`. Add a `pytest.ini` line for the new test dir. Update README + `llms.txt`.
- **Test command (repo current):**
  ```bash
  uv run --with pytest python -m pytest skills/deepseek/tests -v
  ```
  (deepseek has no third-party deps, so only `--with pytest` is needed for its tests.)

---

## File Structure

```
skills/deepseek/
  deepseek.py               # PEP-723 entry: umask, _preflight (claude+git on PATH), main → dispatch
  deepseek_core/
    __init__.py             # __version__
    config.py               # DEFAULTS, find_config, load_config (walk-up + merge + auto-isolate)
    guardrails.py           # is_recursive, denied_paths, within_budget  (pure predicates)
    workspace.py            # git worktree create/diff/numstat/patch/apply/remove  (git side-effects)
    runner.py               # resolve_key, build_child_env, build_argv, write_child_settings, run_child
    receipt.py              # build_receipt, verify_result  (pure shaping)
    ops.py                  # cmd_check/init/config/delegate/apply, _build_parser, dispatch
  tests/
    conftest.py             # sys.path shim + fixtures (git_repo, fake_claude)
    test_config.py
    test_guardrails.py
    test_receipt.py
    test_runner_builders.py
    test_workspace.py
    test_run_child.py
    test_ops_cli.py
    test_delegate_integration.py
  SKILL.md · AGENTS.md · CHANGELOG.md · NOTICE
.deepseek.json              # (created by `init`; committed by the human — not part of the skill package)
```

---

## Task 1: Scaffold + config module

**Files:**
- Create: `skills/deepseek/deepseek_core/__init__.py`
- Create: `skills/deepseek/deepseek_core/config.py`
- Create: `skills/deepseek/tests/conftest.py`
- Test: `skills/deepseek/tests/test_config.py`

**Interfaces:**
- Produces:
  - `deepseek_core.__version__: str` (`"0.1.0"`)
  - `config.DEFAULTS: dict`
  - `config.find_config(start: pathlib.Path) -> pathlib.Path | None`
  - `config.load_config(start: pathlib.Path) -> dict` — deep-merges the found `.deepseek.json` onto `DEFAULTS`; forces `auto.isolate=True` when `mode=="auto"`.

- [ ] **Step 1: Write conftest (path shim)**

```python
# skills/deepseek/tests/conftest.py
import pathlib
import sys

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))
```

- [ ] **Step 2: Write the failing tests**

```python
# skills/deepseek/tests/test_config.py
import importlib
import json

config = importlib.import_module("deepseek_core.config")


def _write(p, obj):
    p.write_text(json.dumps(obj))


def test_find_walks_up(tmp_path):
    root = tmp_path / "repo"
    (root / "a" / "b").mkdir(parents=True)
    _write(root / ".deepseek.json", {"mode": "explicit"})
    assert config.find_config(root / "a" / "b") == root / ".deepseek.json"


def test_find_returns_none_when_absent(tmp_path):
    assert config.find_config(tmp_path) is None


def test_load_defaults_when_absent(tmp_path):
    cfg = config.load_config(tmp_path)
    assert cfg["mode"] == "suggest"
    assert cfg["model"] == "deepseek-v4-flash"
    assert cfg["auto"]["isolate"] is True


def test_load_merges_over_defaults(tmp_path):
    _write(tmp_path / ".deepseek.json", {"model": "deepseek-v4-pro", "auto": {"maxCostUsdPerRun": 0.5}})
    cfg = config.load_config(tmp_path)
    assert cfg["model"] == "deepseek-v4-pro"          # overridden
    assert cfg["mode"] == "suggest"                    # default preserved
    assert cfg["auto"]["maxCostUsdPerRun"] == 0.5      # nested override
    assert "docstrings" in cfg["auto"]["allowTasks"]   # nested default preserved


def test_auto_mode_forces_isolate(tmp_path):
    _write(tmp_path / ".deepseek.json", {"mode": "auto", "auto": {"isolate": False}})
    cfg = config.load_config(tmp_path)
    assert cfg["auto"]["isolate"] is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deepseek_core.config'`

- [ ] **Step 4: Implement `__init__.py` and `config.py`**

```python
# skills/deepseek/deepseek_core/__init__.py
__version__ = "0.1.0"
```

```python
# skills/deepseek/deepseek_core/config.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_config.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add skills/deepseek/deepseek_core/__init__.py skills/deepseek/deepseek_core/config.py skills/deepseek/tests/conftest.py skills/deepseek/tests/test_config.py
git commit -m "feat(deepseek): config discovery, defaults, and merge"
```

---

## Task 2: Guardrails (pure predicates)

**Files:**
- Create: `skills/deepseek/deepseek_core/guardrails.py`
- Test: `skills/deepseek/tests/test_guardrails.py`

**Interfaces:**
- Produces:
  - `guardrails.is_recursive(environ: Mapping[str, str]) -> bool` — True iff `DEEPSEEK_DELEGATE_DEPTH` present.
  - `guardrails.denied_paths(changed: list[str], deny_globs: list[str]) -> list[str]` — subset of `changed` matching any deny glob (recursive `**` supported).
  - `guardrails.within_budget(reported_usd: float | None, cap_usd: float) -> bool` — True if `reported_usd is None` or `<= cap_usd`.

- [ ] **Step 1: Write the failing tests**

```python
# skills/deepseek/tests/test_guardrails.py
import importlib

g = importlib.import_module("deepseek_core.guardrails")


def test_is_recursive():
    assert g.is_recursive({"DEEPSEEK_DELEGATE_DEPTH": "1"}) is True
    assert g.is_recursive({}) is False


def test_denied_paths_matches_recursive_globs():
    changed = ["src/app.py", ".github/workflows/ci.yml", "infra/main.tf", "docs/x.md"]
    deny = [".github/**", "infra/**", "**/*secret*"]
    assert g.denied_paths(changed, deny) == [".github/workflows/ci.yml", "infra/main.tf"]


def test_denied_paths_matches_secret_substring_glob():
    assert g.denied_paths(["config/my_secret.json"], ["**/*secret*"]) == ["config/my_secret.json"]


def test_denied_paths_empty_when_clean():
    assert g.denied_paths(["src/app.py"], [".github/**"]) == []


def test_within_budget():
    assert g.within_budget(0.10, 0.25) is True
    assert g.within_budget(0.30, 0.25) is False
    assert g.within_budget(None, 0.25) is True  # unknown cost never blocks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_guardrails.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deepseek_core.guardrails'`

- [ ] **Step 3: Implement `guardrails.py`**

```python
# skills/deepseek/deepseek_core/guardrails.py
"""Pure guardrail predicates: recursion, deny-globs, budget."""

from collections.abc import Mapping
from fnmatch import fnmatch

DEPTH_ENV = "DEEPSEEK_DELEGATE_DEPTH"


def is_recursive(environ: Mapping) -> bool:
    return DEPTH_ENV in environ


def _match(path: str, pattern: str) -> bool:
    # fnmatch treats "*" as crossing "/", so "**/" and "/**" behave recursively enough
    # for our globs; normalise "**/" to "*" for a leading recursive match.
    if fnmatch(path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch(path, pattern[3:]):
        return True
    if pattern.endswith("/**") and (path == pattern[:-3] or path.startswith(pattern[:-2])):
        return True
    return False


def denied_paths(changed: list[str], deny_globs: list[str]) -> list[str]:
    return [p for p in changed if any(_match(p, g) for g in deny_globs)]


def within_budget(reported_usd, cap_usd: float) -> bool:
    if reported_usd is None:
        return True
    return reported_usd <= cap_usd
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_guardrails.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add skills/deepseek/deepseek_core/guardrails.py skills/deepseek/tests/test_guardrails.py
git commit -m "feat(deepseek): guardrail predicates (recursion, deny-globs, budget)"
```

---

## Task 3: Receipt shaping (pure)

**Files:**
- Create: `skills/deepseek/deepseek_core/receipt.py`
- Test: `skills/deepseek/tests/test_receipt.py`

**Interfaces:**
- Produces:
  - `receipt.verify_result(cmd: str | None, exit_code: int | None, tail: str = "") -> dict | None` — `None` when `cmd is None`; else `{"cmd", "exit", "passed", ...("tail" if failed)}`.
  - `receipt.build_receipt(*, status, workspace, files, verify, patch, cost, turns) -> dict` — assembles the receipt dict, omitting `patch` when `None`.
  - `cost` is `{"reported_usd": float | None, "note": str}`.

- [ ] **Step 1: Write the failing tests**

```python
# skills/deepseek/tests/test_receipt.py
import importlib

r = importlib.import_module("deepseek_core.receipt")


def test_verify_result_none_when_no_cmd():
    assert r.verify_result(None, None) is None


def test_verify_result_pass():
    assert r.verify_result("ruff check x.py", 0) == {
        "cmd": "ruff check x.py", "exit": 0, "passed": True
    }


def test_verify_result_fail_includes_tail():
    res = r.verify_result("pytest", 1, tail="E   assert 1 == 2")
    assert res["passed"] is False
    assert res["tail"] == "E   assert 1 == 2"


def test_build_receipt_omits_patch_when_none():
    rc = r.build_receipt(
        status="applied", workspace="in_place",
        files=[{"path": "x.py", "diffstat": "+1 -0"}],
        verify=None, patch=None,
        cost={"reported_usd": None, "note": "n/a"}, turns=1,
    )
    assert "patch" not in rc
    assert rc["status"] == "applied"
    assert rc["files"][0]["path"] == "x.py"


def test_build_receipt_includes_patch():
    rc = r.build_receipt(
        status="patch_ready", workspace="worktree", files=[],
        verify={"cmd": "ruff", "exit": 0, "passed": True},
        patch=".deepseek/edit-abc.patch",
        cost={"reported_usd": 0.001, "note": "approx"}, turns=2,
    )
    assert rc["patch"] == ".deepseek/edit-abc.patch"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_receipt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deepseek_core.receipt'`

- [ ] **Step 3: Implement `receipt.py`**

```python
# skills/deepseek/deepseek_core/receipt.py
"""Pure shaping of the compact delegation receipt."""


def verify_result(cmd, exit_code, tail: str = ""):
    if cmd is None:
        return None
    passed = exit_code == 0
    res = {"cmd": cmd, "exit": exit_code, "passed": passed}
    if not passed and tail:
        res["tail"] = tail
    return res


def build_receipt(*, status, workspace, files, verify, patch, cost, turns) -> dict:
    rc = {
        "status": status,
        "workspace": workspace,
        "files": files,
        "verify": verify,
        "cost": cost,
        "turns": turns,
    }
    if patch is not None:
        rc["patch"] = patch
    return rc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_receipt.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add skills/deepseek/deepseek_core/receipt.py skills/deepseek/tests/test_receipt.py
git commit -m "feat(deepseek): compact receipt shaping"
```

---

## Task 4: Runner builders (pure env/argv/settings + key resolution)

**Files:**
- Create: `skills/deepseek/deepseek_core/runner.py` (builders only; `run_child` added in Task 6)
- Test: `skills/deepseek/tests/test_runner_builders.py`

**Interfaces:**
- Produces:
  - `runner.ENDPOINT = "https://api.deepseek.com/anthropic"`
  - `runner.build_child_env(base_env: Mapping, key: str) -> dict` — copies `base_env`, sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN=key`, `DEEPSEEK_DELEGATE_DEPTH="1"`.
  - `runner.build_argv(task: str, *, model: str, allowed_tools: list[str], settings_path: str, max_turns: int) -> list[str]`
  - `runner.write_child_settings(dir_: pathlib.Path, model: str) -> pathlib.Path` — writes `settings.json` disabling the `deepseek` skill in the child.
  - `runner.resolve_key(environ: Mapping) -> str | None` — returns `$DEEPSEEK_API_KEY` or `None` (kdbx path added later; env is the testable primary).

- [ ] **Step 1: Write the failing tests**

```python
# skills/deepseek/tests/test_runner_builders.py
import importlib
import json

runner = importlib.import_module("deepseek_core.runner")


def test_build_child_env_sets_endpoint_and_key():
    env = runner.build_child_env({"PATH": "/usr/bin", "HOME": "/h"}, "sk-test")
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert env["DEEPSEEK_DELEGATE_DEPTH"] == "1"
    assert env["PATH"] == "/usr/bin"  # base preserved


def test_build_argv_shape():
    argv = runner.build_argv(
        "add docstrings", model="deepseek-v4-flash",
        allowed_tools=["Read", "Edit", "Write", "Bash"],
        settings_path="/tmp/s.json", max_turns=8,
    )
    assert argv[0] == "claude"
    assert "-p" in argv and "add docstrings" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "deepseek-v4-flash" in argv
    assert "--permission-mode" in argv and "acceptEdits" in argv
    assert "--allowedTools" in argv and "Read,Edit,Write,Bash" in argv
    assert "--settings" in argv and "/tmp/s.json" in argv
    assert "--max-turns" in argv and "8" in argv


def test_write_child_settings_disables_skill(tmp_path):
    p = runner.write_child_settings(tmp_path, "deepseek-v4-flash")
    data = json.loads(p.read_text())
    assert "deepseek" in data.get("disabledSkills", []) or data["env"]["DEEPSEEK_DELEGATE_DEPTH"] == "1"


def test_resolve_key_from_env():
    assert runner.resolve_key({"DEEPSEEK_API_KEY": "sk-x"}) == "sk-x"
    assert runner.resolve_key({}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_runner_builders.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deepseek_core.runner'`

- [ ] **Step 3: Implement builders in `runner.py`**

```python
# skills/deepseek/deepseek_core/runner.py
"""Build the child `claude` invocation and resolve the DeepSeek key."""

import json
import pathlib
from collections.abc import Mapping

ENDPOINT = "https://api.deepseek.com/anthropic"
DEPTH_ENV = "DEEPSEEK_DELEGATE_DEPTH"


def resolve_key(environ: Mapping):
    # v1: env only. kdbx resolution is wired in ops.cmd_delegate (subprocess) so this
    # stays pure and testable.
    return environ.get("DEEPSEEK_API_KEY") or None


def build_child_env(base_env: Mapping, key: str) -> dict:
    env = dict(base_env)
    env["ANTHROPIC_BASE_URL"] = ENDPOINT
    env["ANTHROPIC_AUTH_TOKEN"] = key
    env[DEPTH_ENV] = "1"
    return env


def build_argv(task: str, *, model: str, allowed_tools, settings_path: str, max_turns: int):
    return [
        "claude", "-p", task,
        "--output-format", "json",
        "--model", model,
        "--permission-mode", "acceptEdits",
        "--allowedTools", ",".join(allowed_tools),
        "--settings", settings_path,
        "--max-turns", str(max_turns),
    ]


def write_child_settings(dir_: pathlib.Path, model: str) -> pathlib.Path:
    settings = {
        "env": {DEPTH_ENV: "1"},
        "disabledSkills": ["deepseek"],
        "model": model,
    }
    p = dir_ / "deepseek-child-settings.json"
    p.write_text(json.dumps(settings, indent=2))
    return p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_runner_builders.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add skills/deepseek/deepseek_core/runner.py skills/deepseek/tests/test_runner_builders.py
git commit -m "feat(deepseek): child env/argv/settings builders + key resolution"
```

---

## Task 5: Workspace (git worktree + diff/patch/apply)

**Files:**
- Create: `skills/deepseek/deepseek_core/workspace.py`
- Test: `skills/deepseek/tests/test_workspace.py`
- Modify: `skills/deepseek/tests/conftest.py` (add `git_repo` fixture)

**Interfaces:**
- Produces:
  - `workspace.numstat(repo: pathlib.Path) -> list[dict]` — `[{"path", "diffstat": "+A -D"}]` for unstaged+untracked changes.
  - `workspace.create_worktree(repo: pathlib.Path, tag: str) -> pathlib.Path`
  - `workspace.write_patch(worktree: pathlib.Path, out: pathlib.Path) -> pathlib.Path`
  - `workspace.remove_worktree(repo: pathlib.Path, worktree: pathlib.Path) -> None`
  - `workspace.apply_patch(repo: pathlib.Path, patch: pathlib.Path) -> None`
- Consumes: nothing from prior tasks.

- [ ] **Step 1: Add `git_repo` fixture to conftest**

```python
# append to skills/deepseek/tests/conftest.py
import subprocess

import pytest


@pytest.fixture
def git_repo(tmp_path):
    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    run("add", "-A")
    run("commit", "-qm", "init")
    return tmp_path
```

- [ ] **Step 2: Write the failing tests**

```python
# skills/deepseek/tests/test_workspace.py
import importlib

ws = importlib.import_module("deepseek_core.workspace")


def test_numstat_reports_modified(git_repo):
    (git_repo / "a.py").write_text("x = 1\ny = 2\n")
    stats = ws.numstat(git_repo)
    assert stats == [{"path": "a.py", "diffstat": "+1 -0"}]


def test_numstat_reports_untracked(git_repo):
    (git_repo / "new.py").write_text("z = 3\n")
    paths = [s["path"] for s in ws.numstat(git_repo)]
    assert "new.py" in paths


def test_worktree_roundtrip_and_patch(git_repo, tmp_path):
    wt = ws.create_worktree(git_repo, "test")
    assert wt.is_dir()
    (wt / "a.py").write_text("x = 1\ny = 2\n")
    patch = ws.write_patch(wt, tmp_path / "edit.patch")
    assert patch.read_text().strip() != ""
    ws.remove_worktree(git_repo, wt)
    assert not wt.exists()
    # patch applies back onto the main repo
    ws.apply_patch(git_repo, patch)
    assert "y = 2" in (git_repo / "a.py").read_text()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deepseek_core.workspace'`

- [ ] **Step 4: Implement `workspace.py`**

```python
# skills/deepseek/deepseek_core/workspace.py
"""Git worktree lifecycle + diff/patch helpers (all git side-effects live here)."""

import pathlib
import subprocess


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def numstat(repo: pathlib.Path) -> list[dict]:
    # stage everything (incl. untracked) into the index without committing, read numstat,
    # then reset the index so we leave the working tree untouched.
    _git(repo, "add", "-A")
    out = _git(repo, "diff", "--cached", "--numstat")
    _git(repo, "reset", "-q")
    stats = []
    for line in out.splitlines():
        added, deleted, path = line.split("\t")
        stats.append({"path": path, "diffstat": f"+{added} -{deleted}"})
    return stats


def create_worktree(repo: pathlib.Path, tag: str) -> pathlib.Path:
    wt = repo / ".deepseek" / f"wt-{tag}"
    wt.parent.mkdir(exist_ok=True)
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    return wt


def write_patch(worktree: pathlib.Path, out: pathlib.Path) -> pathlib.Path:
    _git(worktree, "add", "-A")
    diff = _git(worktree, "diff", "--cached")
    _git(worktree, "reset", "-q")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(diff)
    return out


def remove_worktree(repo: pathlib.Path, worktree: pathlib.Path) -> None:
    _git(repo, "worktree", "remove", "--force", str(worktree))


def apply_patch(repo: pathlib.Path, patch: pathlib.Path) -> None:
    _git(repo, "apply", str(patch))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_workspace.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add skills/deepseek/deepseek_core/workspace.py skills/deepseek/tests/conftest.py skills/deepseek/tests/test_workspace.py
git commit -m "feat(deepseek): git worktree lifecycle + diff/patch helpers"
```

---

## Task 6: `run_child` (spawn + capture, driven by a fake `claude`)

**Files:**
- Modify: `skills/deepseek/deepseek_core/runner.py` (add `run_child`)
- Test: `skills/deepseek/tests/test_run_child.py`
- Modify: `skills/deepseek/tests/conftest.py` (add `fake_claude` fixture)

**Interfaces:**
- Produces:
  - `runner.run_child(argv: list[str], env: Mapping, cwd: pathlib.Path, timeout: int) -> dict` — runs the process, parses stdout as JSON, returns `{"ok": bool, "result": dict | None, "returncode": int, "stderr_tail": str}`. `ok` is False on non-zero exit, JSON parse failure, or timeout (never raises for those).

- [ ] **Step 1: Add `fake_claude` fixture to conftest**

```python
# append to skills/deepseek/tests/conftest.py
@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Put a fake `claude` on PATH. It writes canned JSON to stdout and, if asked,
    touches a file in cwd to simulate an edit. Controlled via env the test sets."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "edit = os.environ.get('FAKE_EDIT_FILE')\n"
        "if edit:\n"
        "    open(edit, 'a').write('# edited by fake claude\\n')\n"
        "rc = int(os.environ.get('FAKE_RC', '0'))\n"
        "if rc == 0:\n"
        "    print(json.dumps({'result': 'done', 'num_turns': 2, 'total_cost_usd': 0.0012}))\n"
        "else:\n"
        "    sys.stderr.write('boom\\n')\n"
        "sys.exit(rc)\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return script


import os  # noqa: E402  (fixture above uses os)
```

- [ ] **Step 2: Write the failing tests**

```python
# skills/deepseek/tests/test_run_child.py
import importlib
import os

runner = importlib.import_module("deepseek_core.runner")


def test_run_child_parses_json(fake_claude, tmp_path):
    env = dict(os.environ)
    res = runner.run_child(["claude", "-p", "x", "--output-format", "json"], env, tmp_path, timeout=30)
    assert res["ok"] is True
    assert res["result"]["num_turns"] == 2
    assert res["result"]["total_cost_usd"] == 0.0012


def test_run_child_nonzero_is_not_ok(fake_claude, tmp_path):
    env = dict(os.environ, FAKE_RC="1")
    res = runner.run_child(["claude", "-p", "x"], env, tmp_path, timeout=30)
    assert res["ok"] is False
    assert res["returncode"] == 1
    assert "boom" in res["stderr_tail"]


def test_run_child_actually_edits_file(fake_claude, tmp_path):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    env = dict(os.environ, FAKE_EDIT_FILE=str(target))
    runner.run_child(["claude", "-p", "x"], env, tmp_path, timeout=30)
    assert "edited by fake claude" in target.read_text()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_run_child.py -v`
Expected: FAIL — `AttributeError: module 'deepseek_core.runner' has no attribute 'run_child'`

- [ ] **Step 4: Implement `run_child` in `runner.py`**

```python
# append to skills/deepseek/deepseek_core/runner.py
import subprocess


def run_child(argv, env, cwd, timeout: int) -> dict:
    try:
        proc = subprocess.run(
            argv, env=dict(env), cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "result": None, "returncode": -1, "stderr_tail": "timeout"}
    stderr_tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
    if proc.returncode != 0:
        return {"ok": False, "result": None, "returncode": proc.returncode, "stderr_tail": stderr_tail}
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "result": None, "returncode": 0,
                "stderr_tail": "unparseable child output"}
    return {"ok": True, "result": result, "returncode": 0, "stderr_tail": stderr_tail}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_run_child.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add skills/deepseek/deepseek_core/runner.py skills/deepseek/tests/conftest.py skills/deepseek/tests/test_run_child.py
git commit -m "feat(deepseek): run_child spawn+capture with fake-claude tests"
```

---

## Task 7: CLI dispatch + entrypoint (`check`, `init`, `config`)

**Files:**
- Create: `skills/deepseek/deepseek_core/ops.py`
- Create: `skills/deepseek/deepseek.py`
- Test: `skills/deepseek/tests/test_ops_cli.py`

**Interfaces:**
- Produces:
  - `ops.dispatch(argv: list[str]) -> int`
  - `ops.cmd_check(args) -> int` — offline preflight (claude on PATH? git? key present?); prints human-readable lines to stderr; exit `0` if all present, else non-zero.
  - `ops.cmd_init(args) -> int` — writes `.deepseek.json` (refuses to overwrite; exit `4` if exists).
  - `ops.cmd_config(args) -> int` — prints effective merged config JSON to stdout.
  - `deepseek.main(argv=None) -> int` with `_preflight()`.
- Consumes: `config.load_config`, `config.DEFAULTS`, `runner.resolve_key`.

- [ ] **Step 1: Write the failing tests**

```python
# skills/deepseek/tests/test_ops_cli.py
import importlib
import json

ops = importlib.import_module("deepseek_core.ops")


def test_config_prints_effective(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert ops.dispatch(["config"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["model"] == "deepseek-v4-flash"


def test_init_creates_then_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ops.dispatch(["init"]) == 0
    assert (tmp_path / ".deepseek.json").is_file()
    data = json.loads((tmp_path / ".deepseek.json").read_text())
    assert data["mode"] == "suggest"
    assert ops.dispatch(["init"]) == 4  # refuses to clobber


def test_check_reports_missing_key(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    rc = ops.dispatch(["check"])
    err = capsys.readouterr().err
    assert "DEEPSEEK_API_KEY" in err
    assert rc != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_ops_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deepseek_core.ops'`

- [ ] **Step 3: Implement `ops.py`**

```python
# skills/deepseek/deepseek_core/ops.py
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


def cmd_init(args) -> int:
    dest = pathlib.Path.cwd() / config.CONFIG_NAME
    if dest.exists():
        sys.stderr.write(f"deepseek: {dest.name} already exists — refusing to overwrite\n")
        return 4
    dest.write_text(json.dumps(config.DEFAULTS, indent=2) + "\n")
    sys.stderr.write(f"created {dest.name} — review and commit\n")
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
    p = argparse.ArgumentParser(prog="deepseek", description="deepseek — delegate dev tasks to DeepSeek")
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
```

- [ ] **Step 4: Create the entrypoint `deepseek.py`**

```python
# skills/deepseek/deepseek.py
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""deepseek — delegate simple dev tasks to a nested claude on DeepSeek. See SKILL.md."""

import os
import shutil
import sys

os.umask(0o077)


def _preflight() -> None:
    if sys.version_info < (3, 10):
        sys.stderr.write("deepseek: requires Python >=3.10 (run via `uv run`)\n")
        raise SystemExit(7)
    if shutil.which("git") is None:
        sys.stderr.write("deepseek: git not on PATH\n")
        raise SystemExit(7)


def main(argv=None) -> int:
    _preflight()
    from deepseek_core.ops import dispatch

    return dispatch(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
```

> Note: `ops.py` imports `ops_delegate` (Task 8). To keep this task's tests green before Task 8 exists, create a **temporary stub** `skills/deepseek/deepseek_core/ops_delegate.py` with `def cmd_delegate(a): return 0` and `def cmd_apply(a): return 0`, then replace it in Task 8. Commit the stub in this task.

- [ ] **Step 5: Create the delegate stub**

```python
# skills/deepseek/deepseek_core/ops_delegate.py  (TEMPORARY stub — replaced in Task 8)
def cmd_delegate(args) -> int:
    return 0


def cmd_apply(args) -> int:
    return 0
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_ops_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Smoke the entrypoint**

Run: `uv run --with pytest python -c "import sys; sys.argv=['deepseek','--version']; sys.path.insert(0,'skills/deepseek'); import deepseek; print(deepseek.main())"`
Expected: prints `deepseek 0.1.0` then `0`

- [ ] **Step 8: Commit**

```bash
git add skills/deepseek/deepseek_core/ops.py skills/deepseek/deepseek_core/ops_delegate.py skills/deepseek/deepseek.py skills/deepseek/tests/test_ops_cli.py
git commit -m "feat(deepseek): CLI dispatch + entrypoint (check/init/config)"
```

---

## Task 8: `delegate` orchestration + end-to-end integration

**Files:**
- Replace: `skills/deepseek/deepseek_core/ops_delegate.py` (real implementation)
- Test: `skills/deepseek/tests/test_delegate_integration.py`

**Interfaces:**
- Consumes: `config.load_config`, `runner.{resolve_key,build_child_env,build_argv,write_child_settings,run_child}`, `workspace.{create_worktree,numstat,write_patch,remove_worktree,apply_patch}`, `guardrails.{is_recursive,denied_paths,within_budget}`, `receipt.{verify_result,build_receipt}`.
- Produces: `cmd_delegate(args) -> int`, `cmd_apply(args) -> int`. `cmd_delegate` prints the receipt JSON to stdout and returns the exit code matching `status` (see Global Constraints).

- [ ] **Step 1: Write the failing integration tests**

```python
# skills/deepseek/tests/test_delegate_integration.py
import importlib
import json
import os
import types

ops_delegate = importlib.import_module("deepseek_core.ops_delegate")


def _args(**kw):
    base = dict(task="add docstrings", files=[], dir=None, in_place=False, verify=None, model=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_delegate_worktree_produces_patch(git_repo, fake_claude, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    # fake claude edits a.py inside whatever cwd it's run in (the worktree)
    monkeypatch.setenv("FAKE_EDIT_FILE", "a.py")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)

    rc = ops_delegate.cmd_delegate(_args())
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "patch_ready"
    assert receipt["workspace"] == "worktree"
    assert receipt["patch"].endswith(".patch")
    assert (git_repo / receipt["patch"]).is_file()
    assert rc == 0
    # main tree untouched until apply
    assert "fake claude" not in (git_repo / "a.py").read_text()


def test_delegate_refuses_recursion(git_repo, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_DELEGATE_DEPTH", "1")
    assert ops_delegate.cmd_delegate(_args()) == 4


def test_delegate_missing_key_returns_3(git_repo, fake_claude, monkeypatch):
    monkeypatch.chdir(git_repo)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)
    assert ops_delegate.cmd_delegate(_args()) == 3


def test_delegate_verify_failure_withholds(git_repo, fake_claude, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("FAKE_EDIT_FILE", "a.py")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)
    rc = ops_delegate.cmd_delegate(_args(verify="false"))  # `false` always exits 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "verify_failed"
    assert receipt["verify"]["passed"] is False
    assert rc == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_delegate_integration.py -v`
Expected: FAIL — stub returns 0, assertions on `status`/exit codes fail.

- [ ] **Step 3: Implement the real `ops_delegate.py`**

```python
# skills/deepseek/deepseek_core/ops_delegate.py
"""The `delegate` and `apply` operations — orchestrates the nested claude run."""

import json
import os
import pathlib
import subprocess
import sys
import uuid

from . import config, guardrails, receipt, runner, workspace

MAX_TURNS = 8
TIMEOUT_S = 900
ALLOWED_TOOLS = ["Read", "Edit", "Write", "Bash"]
COST_NOTE = "child-reported, Anthropic-priced — approximate"


def _emit(rc_dict: dict) -> None:
    sys.stdout.write(json.dumps(rc_dict, indent=2) + "\n")


def _run_verify(cmd, cwd, files):
    if not cmd:
        return None, 0
    expanded = cmd.replace("{file}", " ".join(files)) if files else cmd
    proc = subprocess.run(expanded, shell=True, cwd=str(cwd), capture_output=True, text=True)
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
    return receipt.verify_result(expanded, proc.returncode, tail), proc.returncode


def cmd_delegate(args) -> int:
    if guardrails.is_recursive(os.environ):
        sys.stderr.write("deepseek: refusing to recurse (DEEPSEEK_DELEGATE_DEPTH set)\n")
        return 4

    key = runner.resolve_key(os.environ)
    if not key:
        sys.stderr.write(
            "deepseek: no DEEPSEEK_API_KEY — set it, or have a human run:\n"
            "  kdbx set api/deepseek --var DEEPSEEK_API_KEY\n"
        )
        return 3

    repo = pathlib.Path(args.dir).resolve() if args.dir else pathlib.Path.cwd()
    cfg = config.load_config(repo)
    model = args.model or cfg["model"]
    verify_cmd = args.verify or cfg.get("verifyDefault")
    isolate = not args.in_place  # auto-mode isolation is enforced by the parent choosing not to pass --in-place

    tag = uuid.uuid4().hex[:8]
    workdir = workspace.create_worktree(repo, tag) if isolate else repo

    try:
        settings = runner.write_child_settings(workdir, model)
        argv = runner.build_argv(
            args.task, model=model, allowed_tools=ALLOWED_TOOLS,
            settings_path=str(settings), max_turns=MAX_TURNS,
        )
        env = runner.build_child_env(os.environ, key)
        child = runner.run_child(argv, env, workdir, TIMEOUT_S)

        if not child["ok"]:
            _emit(receipt.build_receipt(
                status="error", workspace="worktree" if isolate else "in_place",
                files=[], verify=None, patch=None,
                cost={"reported_usd": None, "note": COST_NOTE}, turns=0,
            ))
            sys.stderr.write(f"deepseek: child failed — {child['stderr_tail']}\n")
            return 7

        result = child["result"]
        cost = {"reported_usd": result.get("total_cost_usd"), "note": COST_NOTE}
        turns = result.get("num_turns", 0)
        files = workspace.numstat(workdir)
        changed = [f["path"] for f in files]

        verify, verify_rc = _run_verify(verify_cmd, workdir, changed)

        # guardrails on the resulting change set
        denied = guardrails.denied_paths(changed, cfg["auto"]["denyGlobs"])
        over_budget = not guardrails.within_budget(cost["reported_usd"], cfg["auto"]["maxCostUsdPerRun"])

        ws_label = "worktree" if isolate else "in_place"

        if verify and not verify["passed"]:
            _emit(receipt.build_receipt(status="verify_failed", workspace=ws_label, files=files,
                                        verify=verify, patch=None, cost=cost, turns=turns))
            return 5
        if denied:
            _emit(receipt.build_receipt(status="denied", workspace=ws_label, files=files,
                                        verify=verify, patch=None, cost=cost, turns=turns))
            sys.stderr.write(f"deepseek: change touches denied paths: {denied}\n")
            return 6
        if over_budget:
            _emit(receipt.build_receipt(status="budget_exceeded", workspace=ws_label, files=files,
                                        verify=verify, patch=None, cost=cost, turns=turns))
            return 6

        if isolate:
            patch_rel = pathlib.Path(".deepseek") / f"edit-{tag}.patch"
            workspace.write_patch(workdir, repo / patch_rel)
            _emit(receipt.build_receipt(status="patch_ready", workspace="worktree", files=files,
                                        verify=verify, patch=str(patch_rel), cost=cost, turns=turns))
            return 0

        _emit(receipt.build_receipt(status="applied", workspace="in_place", files=files,
                                    verify=verify, patch=None, cost=cost, turns=turns))
        return 0
    finally:
        if isolate and workdir.exists():
            workspace.remove_worktree(repo, workdir)


def cmd_apply(args) -> int:
    repo = pathlib.Path.cwd()
    patch = (repo / args.patch).resolve()
    if not patch.is_file():
        sys.stderr.write(f"deepseek: patch not found: {args.patch}\n")
        return 2
    workspace.apply_patch(repo, patch)
    sys.stderr.write(f"applied {args.patch}\n")
    return 0
```

- [ ] **Step 4: Run the integration tests**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests/test_delegate_integration.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full skill suite**

Run: `uv run --with pytest python -m pytest skills/deepseek/tests -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 6: Commit**

```bash
git add skills/deepseek/deepseek_core/ops_delegate.py skills/deepseek/tests/test_delegate_integration.py
git commit -m "feat(deepseek): delegate orchestration + end-to-end integration tests"
```

---

## Task 9: Skill docs, registration, lockfile, lint

**Files:**
- Create: `skills/deepseek/SKILL.md`, `skills/deepseek/AGENTS.md`, `skills/deepseek/CHANGELOG.md`, `skills/deepseek/NOTICE`
- Modify: `pytest.ini`, `README.md`, `llms.txt`
- Create: `skills/deepseek/deepseek.py.lock`

- [ ] **Step 1: Register tests in `pytest.ini`**

Change the `testpaths` line to append the new dir:

```ini
testpaths = skills/kdbx/tests plugins/kdbx/tests skills/deepseek/tests
```

- [ ] **Step 2: Write `SKILL.md`**

Frontmatter + body. Must include: `name: deepseek`; a `description:` covering delegate/init/check/config/apply and the token-efficiency intent; When-to-use; Invocation (`uv run --locked <SKILL_DIR>/deepseek.py <op>`); an operations table; the three autonomy modes and how the parent should behave in each; how to read a receipt (each `status` value and what to do next); the v1 limitation that `maxCostUsdPerSession` is not enforced; the security note that the key is resolved via kdbx/env and never authored by the agent. Use `skills/kdbx/SKILL.md` as the structural template.

- [ ] **Step 3: Write `AGENTS.md`**

Skill-specific golden rules: edit the source not the (future) plugin mirror; the recursion guard is load-bearing (never unset `DEEPSEEK_DELEGATE_DEPTH`); pure-vs-side-effect module boundary (`config`/`guardrails`/`receipt`/runner-builders are pure and unit-tested; `workspace`/`run_child` are side-effecting and tested via git tmp repos + the fake `claude`); build/test commands; the "defining simple" open item. Use `skills/kdbx/AGENTS.md` as the template.

- [ ] **Step 4: Write `CHANGELOG.md` and `NOTICE`**

```markdown
# Changelog

## [Unreleased]

### Added
- Initial `deepseek` skill: `delegate` a bounded dev task to a nested headless `claude`
  running on DeepSeek's Anthropic-compatible endpoint; `init`, `check`, `config`, `apply`.
- Worktree+patch isolation by default; `--in-place` opt-in. Per-project `.deepseek.json`
  with autonomy modes (explicit/suggest/auto) and guardrails (deny-globs, per-run cost cap,
  recursion guard).
```

```
# NOTICE — deepseek skill

This skill shells out to the `claude` CLI (Claude Code) and the DeepSeek API via its
Anthropic-compatible endpoint. It bundles no third-party Python dependencies. Repo source is MIT.
Runtime prerequisites (`claude`, `git`, `uv`) are provided by the user's environment.
```

- [ ] **Step 5: Add rows to `README.md` and `llms.txt`**

README "Available skills" table — add:

```markdown
| [**deepseek**](skills/deepseek) | Delegate simple dev tasks to a nested `claude` running on DeepSeek's Anthropic-compatible endpoint — offload-and-write for token efficiency; worktree-isolated, verified, receipt-only. |
```

`llms.txt` — add a `### deepseek` section mirroring the kdbx entry (SKILL.md link, operations list, install command `npx skills add yarrasys/extensions@deepseek`, prereqs).

- [ ] **Step 6: Lock the script deps**

Run: `uv lock --script skills/deepseek/deepseek.py`
Expected: creates `skills/deepseek/deepseek.py.lock` (empty dep set is fine).

- [ ] **Step 7: Format, lint, and run the full repo suite**

```bash
uvx ruff format .
uvx ruff check .
uv run --with pytest --with pykeepass --with python-dotenv --with filelock \
  --with platformdirs --with "mcp>=1.0,<2" python -m pytest
```
Expected: ruff clean; all tests pass (kdbx + deepseek).

- [ ] **Step 8: Commit**

```bash
git add skills/deepseek/SKILL.md skills/deepseek/AGENTS.md skills/deepseek/CHANGELOG.md skills/deepseek/NOTICE skills/deepseek/deepseek.py.lock pytest.ini README.md llms.txt
git commit -m "docs(deepseek): SKILL.md, AGENTS.md, registration, lockfile"
```

---

## Self-Review (completed against the spec)

- **Spec coverage:** nested-claude-on-DeepSeek architecture (Tasks 4–8) · offload-and-write receipt (Tasks 3, 8) · `.deepseek.json` config + modes (Task 1) · hard guardrails recursion/deny/budget (Tasks 2, 8) · worktree+patch default / in-place opt-in (Tasks 5, 8) · kdbx-or-env key (Task 4 env; kdbx `set` guidance surfaced in `check`/`delegate`, Tasks 7–8) · offline `check` (Task 7) · command surface delegate/apply/init/check/config (Tasks 7–8) · receipt statuses + exit codes (Task 8 / Global Constraints) · fake-`claude` test strategy (Task 6) · registration/lockfile/NOTICE/CHANGELOG (Task 9). **Deviation flagged:** spec's single `guardrails.py` split into `guardrails.py` (pure) + `workspace.py` (git side-effects) for testability.
- **Deferred (documented, not gaps):** `maxCostUsdPerSession` enforcement (needs a session ledger — v2); live endpoint ping in `check` (spec deferred it); DeepSeek-priced cost recompute (spec §Out of scope); plugin wrapper (spec follow-up).
- **Placeholder scan:** none — every code/test step has concrete content; Task 2/8 SKILL/AGENTS prose steps point at a concrete template file and enumerate required content.
- **Type consistency:** `run_child` returns `{ok,result,returncode,stderr_tail}` (Task 6) consumed identically in Task 8; `numstat` returns `{path,diffstat}` used unchanged in receipt `files`; `build_receipt` kwargs match every call site; `verify_result` shape matches assertions.
