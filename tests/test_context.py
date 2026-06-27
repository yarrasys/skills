import importlib
import json

ctx = importlib.import_module("kdbx_core.context")


def _ptr(tmp, envs, default="dev"):
    p = tmp / ".keepassxc.json"
    p.write_text(json.dumps({"project": "p", "defaultEnv": default, "envs": envs}))
    return p


def test_banner_to_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    _ptr(tmp_path, {"dev": {}})
    ctx.resolve("dev", tmp_path, banner=True)
    assert "ACTIVE ENV: dev" in capsys.readouterr().err


def test_banner_suppressed_for_reads(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    _ptr(tmp_path, {"dev": {}})
    ctx.resolve("dev", tmp_path, banner=False)
    assert capsys.readouterr().err == ""


def test_prod_is_not_gated(tmp_path, monkeypatch):
    # prod is no longer special: resolve() never refuses. The real boundary is
    # key-file possession, not a name match. (See #9.)
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.delenv("KDBX_ENV", raising=False)
    _ptr(tmp_path, {"prod": {}})
    c = ctx.resolve("prod", tmp_path, banner=True)
    assert c.env == "prod"


def test_kdbx_env_inherited_is_not_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", str(tmp_path / "kx"))
    monkeypatch.setenv("KDBX_ENV", "dev")
    _ptr(tmp_path, {"dev": {}})
    c = ctx.resolve(None, tmp_path, banner=True)
    assert c.source == "$KDBX_ENV"
