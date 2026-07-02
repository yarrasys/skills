"""Git worktree lifecycle + diff/patch helpers (all git side-effects live here)."""

import pathlib
import subprocess


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def numstat(repo: pathlib.Path) -> list[dict]:
    # stage everything (incl. untracked) into the index without committing, read numstat,
    # then reset the index so we leave the working tree untouched.
    _git(repo, "add", "-A")
    out = _git(repo, "diff", "--cached", "--numstat")
    _git(repo, "reset", "-q")
    stats = []
    for line in out.splitlines():
        added, deleted, path = line.split("\t")
        stats.append({"path": path, "diffstat": f"+{added} -{deleted}"})
    return stats


def create_worktree(repo: pathlib.Path, tag: str) -> pathlib.Path:
    wt = repo / ".deepseek" / f"wt-{tag}"
    wt.parent.mkdir(exist_ok=True)
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


def apply_patch(repo: pathlib.Path, patch: pathlib.Path) -> None:
    _git(repo, "apply", str(patch))
