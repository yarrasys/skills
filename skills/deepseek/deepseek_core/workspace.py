"""Git worktree lifecycle + diff/patch helpers (all git side-effects live here)."""

import pathlib
import shutil
import subprocess
import tempfile

_WT_PREFIX = "deepseek-wt-"


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def is_dirty(repo: pathlib.Path) -> bool:
    return bool(_git(repo, "status", "--porcelain").strip())


def status_set(repo: pathlib.Path) -> set:
    """Working-tree status as a set of porcelain lines — used to detect changes a
    delegated child made to the *main* tree despite worktree isolation (#26)."""
    return {ln for ln in _git(repo, "status", "--porcelain").splitlines() if ln.strip()}


def numstat(repo: pathlib.Path) -> list[dict]:
    # Snapshot the index, stage everything (incl. untracked) to read numstat, then
    # restore the index exactly — never clobber a caller's pre-existing staged state.
    saved = _git(repo, "write-tree").strip()
    _git(repo, "add", "-A")
    out = _git(repo, "diff", "--cached", "--numstat", "--no-renames")
    _git(repo, "read-tree", saved)
    stats = []
    for line in out.splitlines():
        added, deleted, path = line.split("\t")
        stats.append({"path": path, "diffstat": f"+{added} -{deleted}"})
    return stats


def create_worktree(repo: pathlib.Path, tag: str) -> pathlib.Path:
    # Create the worktree OUTSIDE the repo tree (a fresh temp dir), not nested under
    # `repo/.deepseek/`. A delegated child that resolves file paths against a repo
    # root can otherwise land edits in the real tree; keeping the worktree external
    # removes that neighbourhood (#26). `remove_worktree` tears down the temp parent.
    root = pathlib.Path(tempfile.mkdtemp(prefix=_WT_PREFIX))
    wt = root / f"wt-{tag}"
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    return wt


def write_patch(worktree: pathlib.Path, out: pathlib.Path) -> pathlib.Path:
    _git(worktree, "add", "-A")
    diff = _git(worktree, "diff", "--cached")
    _git(worktree, "reset", "-q")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(diff)
    return out


def remove_worktree(repo: pathlib.Path, worktree: pathlib.Path) -> None:
    _git(repo, "worktree", "remove", "--force", str(worktree))
    # Also remove the external temp parent we created in create_worktree.
    if worktree.parent.name.startswith(_WT_PREFIX):
        shutil.rmtree(worktree.parent, ignore_errors=True)


def restore(repo: pathlib.Path) -> None:
    """Discard uncommitted changes in `repo` — tracked modifications and untracked files.

    Used to roll back an `--in-place` delegation whose gate (verify/deny/budget) withheld
    the result: since `--in-place` refuses a dirty tree up front, the only uncommitted state
    at gate time is the child's own edit, so this is safe to blow away wholesale.
    """
    _git(repo, "checkout", "--", ".")
    _git(repo, "clean", "-fd")


def apply_patch(repo: pathlib.Path, patch: pathlib.Path) -> None:
    _git(repo, "apply", str(patch))
