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
