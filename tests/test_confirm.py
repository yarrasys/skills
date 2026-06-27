"""Destructive-op confirmation (delete --purge, rekey) — no --yes (#9)."""

import importlib
import io
import json

import pytest

ops = importlib.import_module("kdbx_core.ops")
secretio = importlib.import_module("kdbx_core.secretio")


class _TTY(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keepassxc.json").write_text(
        json.dumps({"project": "p", "defaultEnv": "dev", "envs": {"dev": {"vars": {}}}})
    )
    return tmp_path


def _seed_entry(monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    monkeypatch.setattr("sys.stdin", io.StringIO("v\n"))
    ops.dispatch(["set", "g/t", "--env", "dev"])


# --- the confirm() helper itself ---------------------------------------------


def test_confirm_refuses_without_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # not a TTY
    assert secretio.confirm("do it?") is False


def test_confirm_reads_tty_answer(monkeypatch):
    monkeypatch.setattr("sys.stdin", _TTY())
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    assert secretio.confirm("do it?") is True
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert secretio.confirm("do it?") is False


# --- destructive ops gate on it ----------------------------------------------


def test_purge_proceeds_when_confirmed(repo, monkeypatch, capsys):
    _seed_entry(monkeypatch)
    monkeypatch.setattr(secretio, "confirm", lambda prompt: True)
    assert ops.dispatch(["delete", "g/t", "--purge", "--env", "dev"]) == 0
    ops.dispatch(["list", "--env", "dev"])
    assert "g/t" not in capsys.readouterr().out


def test_purge_refused_leaves_entry(repo, monkeypatch, capsys):
    _seed_entry(monkeypatch)
    monkeypatch.setattr(secretio, "confirm", lambda prompt: False)
    assert ops.dispatch(["delete", "g/t", "--purge", "--env", "dev"]) == 4
    ops.dispatch(["list", "--env", "dev"])
    assert "g/t" in capsys.readouterr().out  # intact


def test_soft_delete_needs_no_confirm(repo, monkeypatch):
    _seed_entry(monkeypatch)
    # soft delete (recycle bin, recoverable) is not gated
    assert ops.dispatch(["delete", "g/t", "--env", "dev"]) == 0


def test_rekey_proceeds_when_confirmed(repo, monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    monkeypatch.setattr(secretio, "confirm", lambda prompt: True)
    assert ops.dispatch(["rekey", "--env", "dev"]) == 0


def test_rekey_refused(repo, monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    monkeypatch.setattr(secretio, "confirm", lambda prompt: False)
    assert ops.dispatch(["rekey", "--env", "dev"]) == 4
