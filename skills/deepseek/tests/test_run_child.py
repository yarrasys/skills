import importlib
import os

runner = importlib.import_module("deepseek_core.runner")


def test_run_child_parses_json(fake_claude, tmp_path):
    env = dict(os.environ)
    res = runner.run_child(
        ["claude", "-p", "x", "--output-format", "json"], env, tmp_path, timeout=30
    )
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


def test_run_child_resolves_executable_via_which(monkeypatch, tmp_path):
    # Windows can't launch a bare `claude` that is really a claude.bat/.cmd shim
    # (CreateProcess won't resolve the extension), so run_child must resolve argv[0]
    # through shutil.which (which honors PATHEXT) and spawn the full path.
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: "/resolved/claude")
    calls = {}

    def fake_run(argv, **kw):
        calls["argv"] = list(argv)

        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.run_child(["claude", "-p", "x"], {"PATH": "/x"}, tmp_path, timeout=5)
    assert calls["argv"][0] == "/resolved/claude"
    assert calls["argv"][1:] == ["-p", "x"]


def test_run_child_falls_back_when_unresolved(monkeypatch, tmp_path):
    # If which finds nothing, keep the original argv[0] (let subprocess raise as before).
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: None)
    calls = {}

    def fake_run(argv, **kw):
        calls["argv"] = list(argv)

        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.run_child(["claude", "-p", "x"], {"PATH": "/x"}, tmp_path, timeout=5)
    assert calls["argv"][0] == "claude"
