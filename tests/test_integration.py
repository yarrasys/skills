"""End-to-end lifecycle, secret-leak, and cross-engine interop (spec §13)."""

import importlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

ops = importlib.import_module("kdbx_core.ops")


def _stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    monkeypatch.delenv("KDBX_DEBUG", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / ".keepassxc.json").write_text(
        json.dumps(
            {
                "project": "ideas",
                "defaultEnv": "dev",
                "envs": {"dev": {"vars": {"OPENAI_API_KEY": "api/openai:password"}}},
            }
        )
    )
    return tmp_path


def _vault_path(repo):
    return repo / "kx" / "ideas" / "dev.kdbx"


def test_full_lifecycle(repo, monkeypatch, capsys):
    SECRET = "sk-lifecycle-9f8e7d"
    assert ops.dispatch(["init", "--env", "dev"]) == 0

    _stdin(monkeypatch, SECRET + "\n")
    assert ops.dispatch(["set", "api/openai", "--env", "dev"]) == 0

    # masked by default; secret only under --reveal
    assert ops.dispatch(["get", "api/openai", "--env", "dev"]) == 0
    out = capsys.readouterr().out
    assert SECRET not in out and "(set, hidden)" in out

    assert ops.dispatch(["get", "api/openai", "--reveal", "--env", "dev"]) == 0
    assert SECRET in capsys.readouterr().out

    assert ops.dispatch(["list", "--env", "dev"]) == 0
    assert "api/openai" in capsys.readouterr().out

    assert ops.dispatch(["check", "--env", "dev"]) == 0  # no drift

    # export -> 0600 dotenv, value present in file (expected) but not in stdout
    envf = repo / ".env"
    assert ops.dispatch(["export", "--out", str(envf), "--env", "dev"]) == 0
    assert stat.S_IMODE(envf.stat().st_mode) == 0o600
    from kdbx_core import secretio

    assert secretio.parse_dotenv(envf.read_text())["OPENAI_API_KEY"] == SECRET

    # run injects into a child without printing
    got = repo / "child.txt"
    rc = ops.dispatch(
        [
            "run",
            "--env",
            "dev",
            "--",
            sys.executable,
            "-c",
            f"import os,pathlib;pathlib.Path(r'{got}').write_text(os.environ['OPENAI_API_KEY'])",
        ]
    )
    assert rc == 0 and got.read_text() == SECRET

    # mv then delete(soft) then verify recoverable, then purge
    assert ops.dispatch(["mv", "api/openai", "api/oai", "--env", "dev"]) == 0
    assert ops.dispatch(["delete", "api/oai", "--env", "dev"]) == 0
    assert ops.dispatch(["get", "api/oai", "--env", "dev"]) == 2  # gone from live view

    from kdbx_core import vault

    kp = vault._open(_vault_path(repo), repo / "kx" / "ideas" / "dev.keyx")
    assert any(e.title == "oai" for e in kp.entries if vault._in_recyclebin(kp, e))  # in bin

    monkeypatch.setattr(secretio, "confirm", lambda prompt: True)  # purge is destructive
    assert ops.dispatch(["delete", "api/oai", "--purge", "--env", "dev"]) == 0

    # perms stayed 0600 across all the saves above (POSIX; Windows uses ACLs)
    if os.name != "nt":
        assert stat.S_IMODE(_vault_path(repo).stat().st_mode) == 0o600

    # the secret never leaked to stdout/stderr across the masked/safe ops
    captured = capsys.readouterr()
    assert SECRET not in captured.err


def test_set_never_puts_secret_in_argv(repo, monkeypatch):
    """The value is read from stdin; it must never appear in the process argv."""
    ops.dispatch(["init", "--env", "dev"])
    argv = ["set", "api/openai", "--env", "dev"]  # the only args we ever pass
    _stdin(monkeypatch, "argv-leak-canary\n")
    assert ops.dispatch(argv) == 0
    assert all("argv-leak-canary" not in a for a in argv)


def test_cli_help_via_uv():
    import pathlib

    skill_dir = pathlib.Path(__file__).resolve().parent.parent / "skills" / "kdbx"
    r = subprocess.run(
        ["uv", "run", "kdbx.py", "--help"], capture_output=True, text=True, cwd=skill_dir
    )
    assert r.returncode == 0
    assert "kdbx" in (r.stdout + r.stderr).lower()


@pytest.mark.skipif(not shutil.which("keepassxc-cli"), reason="no keepassxc-cli")
def test_keepassxc_cli_can_read(built_vault):
    vp, kf = built_vault
    r = subprocess.run(
        ["keepassxc-cli", "ls", "--no-password", "-k", str(kf), str(vp)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
