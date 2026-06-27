import importlib
import io
import json
import sys

import pytest

ops = importlib.import_module("kdbx_core.ops")


def _stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


@pytest.fixture
def repo_with_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keepassxc.json").write_text(
        json.dumps(
            {
                "project": "ideas",
                "defaultEnv": "dev",
                "envs": {"dev": {"vars": {"OPENAI_API_KEY": "api/openai:password"}}},
            }
        )
    )
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "sk-secret\n")
    ops.dispatch(["set", "api/openai", "--env", "dev"])
    return tmp_path


def test_run_injects_env(repo_with_secret, tmp_path):
    out = tmp_path / "got.txt"
    rc = ops.dispatch(
        [
            "run",
            "--env",
            "dev",
            "--",
            sys.executable,
            "-c",
            f"import os,pathlib;pathlib.Path(r'{out}').write_text(os.environ['OPENAI_API_KEY'])",
        ]
    )
    assert rc == 0 and out.read_text() == "sk-secret"


def test_run_propagates_exit(repo_with_secret):
    rc = ops.dispatch(["run", "--env", "dev", "--", sys.executable, "-c", "import sys;sys.exit(7)"])
    assert rc == 7


def test_check_reports_drift(repo_with_secret, monkeypatch):
    # add a var with no backing entry -> drift -> exit 5
    pt = json.loads((repo_with_secret / ".keepassxc.json").read_text())
    pt["envs"]["dev"]["vars"]["MISSING"] = "no/entry:password"
    (repo_with_secret / ".keepassxc.json").write_text(json.dumps(pt))
    assert ops.dispatch(["check", "--env", "dev"]) == 5


def test_export_roundtrip_multiline(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / ".keepassxc.json").write_text(
        json.dumps(
            {
                "project": "p",
                "defaultEnv": "dev",
                "envs": {"dev": {"vars": {"PEM": "k/pem:password"}}},
            }
        )
    )
    ops.dispatch(["init", "--env", "dev"])
    pem = "-----BEGIN-----\nl1\nl2\n-----END-----"
    _stdin(monkeypatch, pem)
    ops.dispatch(["set", "k/pem", "--raw", "--env", "dev"])
    out = tmp_path / ".env"
    assert ops.dispatch(["export", "--out", str(out), "--env", "dev"]) == 0
    from kdbx_core import secretio

    back = secretio.parse_dotenv(out.read_text())
    assert back["PEM"] == pem
    assert ops.dispatch(["check", "--env", "dev"]) == 0
