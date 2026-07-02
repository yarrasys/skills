import importlib

ops_delegate = importlib.import_module("deepseek_core.ops_delegate")


def test_run_verify_quotes_untrusted_filenames_against_shell_injection(tmp_path):
    """`files` come from the delegated (less-trusted) child's own file creations —
    a filename like `a; touch INJECTED.txt` must not execute as shell syntax when
    interpolated into the verify command."""
    malicious = "a; touch INJECTED.txt"
    ops_delegate._run_verify("echo checked {file}", tmp_path, [malicious])
    assert (tmp_path / "INJECTED.txt").exists() is False


def test_run_verify_empty_files_with_file_placeholder_skips_verification(tmp_path):
    """A no-change delegation (files == []) must not run the verify template against
    a literal '{file}' — that would spuriously fail (e.g. `ruff check {file}`)."""
    result = ops_delegate._run_verify("ruff check {file}", tmp_path, [])
    assert result is None


def test_run_verify_empty_files_without_placeholder_still_runs(tmp_path):
    """A command with no {file} placeholder should still run even with no files."""
    result = ops_delegate._run_verify("true", tmp_path, [])
    assert result is not None
    assert result["passed"] is True
