import importlib

ws = importlib.import_module("deepseek_core.workspace")


def test_numstat_reports_modified(git_repo):
    (git_repo / "a.py").write_text("x = 1\ny = 2\n")
    stats = ws.numstat(git_repo)
    assert stats == [{"path": "a.py", "diffstat": "+1 -0"}]


def test_numstat_reports_untracked(git_repo):
    (git_repo / "new.py").write_text("z = 3\n")
    paths = [s["path"] for s in ws.numstat(git_repo)]
    assert "new.py" in paths


def test_worktree_roundtrip_and_patch(git_repo, tmp_path):
    wt = ws.create_worktree(git_repo, "test")
    assert wt.is_dir()
    (wt / "a.py").write_text("x = 1\ny = 2\n")
    patch = ws.write_patch(wt, tmp_path / "edit.patch")
    assert patch.read_text().strip() != ""
    ws.remove_worktree(git_repo, wt)
    assert not wt.exists()
    # patch applies back onto the main repo
    ws.apply_patch(git_repo, patch)
    assert "y = 2" in (git_repo / "a.py").read_text()


def test_worktree_is_external_and_cleaned_up(git_repo):
    wt = ws.create_worktree(git_repo, "iso")
    assert wt.is_dir()
    # created OUTSIDE the repo tree (#26) — no ancestor is the repo dir
    assert git_repo.resolve() not in wt.resolve().parents
    root = wt.parent
    ws.remove_worktree(git_repo, wt)
    assert not wt.exists()
    assert not root.exists()  # the external temp parent is torn down too


def test_status_set_detects_main_tree_change(git_repo):
    assert ws.status_set(git_repo) == set()
    (git_repo / "a.py").write_text("x = 99\n")
    assert any("a.py" in ln for ln in ws.status_set(git_repo))


def test_numstat_preserves_staged_index(git_repo):
    import subprocess

    (git_repo / "a.py").write_text("x = 1\ny = 2\n")
    subprocess.run(["git", "add", "a.py"], cwd=git_repo, check=True, capture_output=True)
    ws.numstat(git_repo)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    ).stdout
    assert "a.py" in staged  # numstat must leave the pre-staged change staged
