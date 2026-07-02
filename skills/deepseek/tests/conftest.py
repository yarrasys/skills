import os
import pathlib
import subprocess
import sys

import pytest

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))


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


_CLAUDE_IMPL = (
    "import json, os, sys\n"
    "edit = os.environ.get('FAKE_EDIT_FILE')\n"
    "if edit:\n"
    "    open(edit, 'a').write('# edited by fake claude\\n')\n"
    "rc = int(os.environ.get('FAKE_RC', '0'))\n"
    "if rc == 0:\n"
    "    payload = {'result': 'done', 'num_turns': 2, 'total_cost_usd': 0.0012,\n"
    "               'usage': {'input_tokens': 1000, 'output_tokens': 500}}\n"
    "    if os.environ.get('FAKE_IS_ERROR'):\n"
    "        payload['is_error'] = True\n"
    "    print(json.dumps(payload))\n"
    "else:\n"
    "    sys.stderr.write('boom\\n')\n"
    "sys.exit(rc)\n"
)


@pytest.fixture
def fake_claude(tmp_path_factory, monkeypatch):
    """Put a fake `claude` on PATH. It writes canned JSON to stdout and, if asked,
    touches a file in cwd to simulate an edit. Controlled via env the test sets.

    Lives in its own tmp dir (not the `git_repo` fixture's tmp_path) so its PATH
    shim never lands inside a test repo's working tree. Cross-platform: a POSIX
    shebang launcher plus a Windows `.bat` launcher both delegate to the same
    `_claude_impl.py`, so this resolves on windows-latest CI too.
    """
    bin_dir = tmp_path_factory.mktemp("fakebin")
    impl = bin_dir / "_claude_impl.py"
    impl.write_text(_CLAUDE_IMPL)

    script = bin_dir / "claude"
    script.write_text(f'#!/bin/sh\nexec python3 "{impl}" "$@"\n')
    script.chmod(0o755)

    if os.name == "nt":
        bat = bin_dir / "claude.bat"
        bat.write_text(f'@echo off\r\npython "{impl}" %*\r\n')

    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return script
