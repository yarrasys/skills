import importlib
import json
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

    rc = ops_delegate.cmd_delegate(_args(verify="true"))  # hermetic: shell builtin, no ambient ruff
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "patch_ready"
    assert receipt["workspace"] == "worktree"
    assert receipt["patch"].endswith(".patch")
    assert (git_repo / receipt["patch"]).is_file()
    assert receipt["verify"]["passed"] is True
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


def test_delegate_in_place_applies_and_leaves_no_settings_litter(
    git_repo, fake_claude, monkeypatch, capsys
):
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("FAKE_EDIT_FILE", "a.py")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)
    # fake_claude shares git_repo's tmp_path, so its fakebin/ PATH shim lands
    # untracked inside the repo root — exclude it so the tree is genuinely
    # clean for the in-place dirty-tree check, matching a real user's repo.
    (git_repo / ".git" / "info" / "exclude").write_text("/fakebin/\n")

    rc = ops_delegate.cmd_delegate(_args(in_place=True, verify="true"))
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "applied"
    assert rc == 0
    assert not (git_repo / "deepseek-child-settings.json").exists()


def test_delegate_in_place_refuses_dirty_tree(git_repo, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)
    (git_repo / "a.py").write_text("x = 2\n")  # uncommitted, dirty tree

    rc = ops_delegate.cmd_delegate(_args(in_place=True, verify="true"))
    assert rc == 7
    captured = capsys.readouterr()
    assert captured.out == ""  # no receipt emitted — refused before spawning the child
    # untouched by any delegate/fake-claude activity — still just the dirty edit we made
    assert (git_repo / "a.py").read_text() == "x = 2\n"
