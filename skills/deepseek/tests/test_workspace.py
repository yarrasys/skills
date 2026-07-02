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
