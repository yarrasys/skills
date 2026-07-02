import importlib
import json
import subprocess
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


def test_delegate_empty_verify_disables_verification(git_repo, fake_claude, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("FAKE_EDIT_FILE", "a.py")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)

    rc = ops_delegate.cmd_delegate(_args(verify=""))
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "patch_ready"  # worktree default
    assert receipt["verify"] is None  # verification was skipped, not run
    assert rc == 0


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


def test_delegate_in_place_verify_failure_rolls_back(git_repo, fake_claude, monkeypatch, capsys):
    """A withheld (`verify_failed`) --in-place gate must not leave the child's edit on
    the real tree — SKILL.md promises 'nothing applied' for this status in every mode."""
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("FAKE_EDIT_FILE", "a.py")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)
    original = (git_repo / "a.py").read_text()

    rc = ops_delegate.cmd_delegate(_args(in_place=True, verify="false"))  # `false` always fails
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["status"] == "verify_failed"
    assert rc == 5
    assert (git_repo / "a.py").read_text() == original  # rolled back
    status = subprocess.run(
        ["git", "-C", str(git_repo), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""  # no leftover untracked/modified files


def test_delegate_child_is_error_treated_as_failure(git_repo, fake_claude, monkeypatch, capsys):
    """A real `claude` child can exit 0 while still reporting `is_error: true` in its JSON —
    that must be treated as a failed delegation, not run through verify/apply."""
    monkeypatch.chdir(git_repo)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("FAKE_EDIT_FILE", "a.py")
    monkeypatch.setenv("FAKE_IS_ERROR", "1")
    monkeypatch.delenv("DEEPSEEK_DELEGATE_DEPTH", raising=False)

    rc = ops_delegate.cmd_delegate(_args(verify="true"))
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["status"] == "error"
    assert rc == 7
