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
    _write(
        tmp_path / ".deepseek.json", {"model": "deepseek-v4-pro", "auto": {"maxCostUsdPerRun": 0.5}}
    )
    cfg = config.load_config(tmp_path)
    assert cfg["model"] == "deepseek-v4-pro"  # overridden
    assert cfg["mode"] == "suggest"  # default preserved
    assert cfg["auto"]["maxCostUsdPerRun"] == 0.5  # nested override
    assert "docstrings" in cfg["auto"]["allowTasks"]  # nested default preserved


def test_auto_mode_forces_isolate(tmp_path):
    _write(tmp_path / ".deepseek.json", {"mode": "auto", "auto": {"isolate": False}})
    cfg = config.load_config(tmp_path)
    assert cfg["auto"]["isolate"] is True
