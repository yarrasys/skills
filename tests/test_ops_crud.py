import importlib
import io
import json

import pytest

ops = importlib.import_module("kdbx_core.ops")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keepassxc.json").write_text(
        json.dumps({"project": "ideas", "defaultEnv": "dev", "envs": {"dev": {"vars": {}}}})
    )
    return tmp_path


def _stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_init_then_set_get(repo, monkeypatch, capsys):
    assert ops.dispatch(["init", "--env", "dev"]) == 0
    _stdin(monkeypatch, "sk-123\n")
    assert ops.dispatch(["set", "api/openai", "--env", "dev"]) == 0
    assert ops.dispatch(["get", "api/openai", "--env", "dev"]) == 0
    out = capsys.readouterr().out
    assert "sk-123" not in out and "(set, hidden)" in out


def test_get_reveal(repo, monkeypatch, capsys):
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "sk-123\n")
    ops.dispatch(["set", "api/openai", "--env", "dev"])
    assert ops.dispatch(["get", "api/openai", "--reveal", "--env", "dev"]) == 0
    assert "sk-123" in capsys.readouterr().out


def test_delete_then_list(repo, monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "v\n")
    ops.dispatch(["set", "g/t", "--env", "dev"])
    assert ops.dispatch(["delete", "g/t", "--env", "dev"]) == 0


def test_set_var_writes_pointer(repo, monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "sk\n")
    ops.dispatch(["set", "api/openai", "--var", "OPENAI_API_KEY", "--env", "dev"])
    pt = json.loads((repo / ".keepassxc.json").read_text())
    assert pt["envs"]["dev"]["vars"]["OPENAI_API_KEY"] == "api/openai"


def test_envs_marks_active(repo, capsys):
    ops.dispatch(["envs", "--env", "dev"])
    assert "* dev" in capsys.readouterr().out


def test_mv_repoints_var_mapping(repo, monkeypatch):
    # mv must update the var map it's supposed to maintain (else check drifts).
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "sk\n")
    ops.dispatch(["set", "api/openai", "--var", "OPENAI_API_KEY", "--env", "dev"])
    assert ops.dispatch(["mv", "api/openai", "api/oai", "--env", "dev"]) == 0
    pt = json.loads((repo / ".keepassxc.json").read_text())
    assert pt["envs"]["dev"]["vars"]["OPENAI_API_KEY"] == "api/oai"
    assert ops.dispatch(["check", "--env", "dev"]) == 0  # no drift after mv


def test_mv_preserves_field_suffix(repo, monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "sk\n")
    # store under an explicit field and map the var to "path:field"
    ops.dispatch(["set", "api/openai:token", "--var", "TOK", "--env", "dev"])
    ops.dispatch(["mv", "api/openai", "api/oai", "--env", "dev"])
    pt = json.loads((repo / ".keepassxc.json").read_text())
    assert pt["envs"]["dev"]["vars"]["TOK"] == "api/oai:token"


def test_mv_leaves_unrelated_mappings(repo, monkeypatch):
    ops.dispatch(["init", "--env", "dev"])
    _stdin(monkeypatch, "a\n")
    ops.dispatch(["set", "api/openai", "--var", "A", "--env", "dev"])
    _stdin(monkeypatch, "b\n")
    ops.dispatch(["set", "api/other", "--var", "B", "--env", "dev"])
    ops.dispatch(["mv", "api/openai", "api/oai", "--env", "dev"])
    pt = json.loads((repo / ".keepassxc.json").read_text())["envs"]["dev"]["vars"]
    assert pt["A"] == "api/oai" and pt["B"] == "api/other"  # only the moved one changes
