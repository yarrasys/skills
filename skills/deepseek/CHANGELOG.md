# Changelog — deepseek

All notable changes to the **deepseek** skill. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [SemVer](https://semver.org/spec/v2.0.0.html).
Releases are tagged `deepseek/v<version>`.

## [Unreleased]

### Added

- Initial `deepseek` skill: `delegate` a bounded dev task to a nested headless `claude`
  running on DeepSeek's Anthropic-compatible endpoint; `init`, `check`, `config`, `apply`.
- Worktree+patch isolation by default; `--in-place` opt-in. Per-project `.deepseek.json`
  with autonomy modes (explicit/suggest/auto) and guardrails (deny-globs, per-run cost cap,
  recursion guard).

### Fixed

- **Windows child spawn:** `run_child` now resolves `claude` via `shutil.which` (honoring
  `PATHEXT`) before spawning, so the Windows `.bat`/`.cmd` shim launches. Previously a bare
  `claude` argv[0] with `shell=False` failed with `WinError 2` on Windows — the delegate
  integration tests were red on `windows-latest` and real Windows delegations would have failed too.
- `--verify ""` now actually disables verification instead of silently falling back to
  `verifyDefault` (the empty string was previously treated as falsy).
- **Shell-injection guardrail:** `_run_verify` now `shlex.quote`s each filename interpolated
  into the verify command via `{file}`. Those filenames come from the delegated (less-trusted)
  child, so a filename like `a; touch pwned` could previously inject arbitrary shell syntax
  into the parent's verify run.
- A no-change delegation (`files == []`) with a `{file}`-templated verify command no longer
  runs the command against a literal `"{file}"` (which spuriously failed, e.g. `ruff check {file}`)
  — verification is now skipped, matching the "no verify" behavior of an empty command.
- `--in-place` delegations that hit a withheld gate (`verify_failed`, `denied`,
  `budget_exceeded`) now roll the working tree back to `HEAD` (`git checkout -- .` +
  `git clean -fd`) before returning, so "nothing applied" is actually true in that mode too,
  not just in worktree mode.
- A real `claude` child can exit `0` while its JSON result reports `is_error: true`; `delegate`
  now treats that as a failed delegation (`error` receipt, exit 7) instead of proceeding to
  verify/apply a result the child itself flagged as an error.
- `init` now ensures `.deepseek/` is git-ignored in the target project — appends it to an
  existing `.gitignore` (or creates one) so worktrees/patches don't show up in `git status`.

### Documentation

- SKILL.md receipt shape corrected: `patch` is present only when `status == "patch_ready"`,
  not on every receipt.
- SKILL.md now documents that `--file` is accepted but not yet enforced in v1 (the child
  sees the whole repo; scope via `--task` wording or `denyGlobs`).
- SKILL.md now has a **Security** note on the real isolation posture: the child runs with
  `Bash` + `--permission-mode acceptEdits`, so worktree isolation only contains git-tracked
  file diffs, not arbitrary shell/network side effects — only delegate to a trusted
  endpoint/key, and treat `--in-place` as running untrusted edits directly on your tree.
