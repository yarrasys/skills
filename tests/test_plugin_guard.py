"""Tests for the kdbx plugin leak-guard (plugins/kdbx/hooks/guard.py)."""

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

_GUARD = pathlib.Path(__file__).resolve().parents[1] / "plugins" / "kdbx" / "hooks" / "guard.py"

_spec = importlib.util.spec_from_file_location("kdbx_guard", _GUARD)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


DENY = [
    "cat dev.keyx",
    "cat ~/.config/keepassxc/proj/dev.kdbx",
    "base64 ~/.config/keepassxc/proj/dev.keyx",
    "cp vault.kdbx /tmp/x",
    "xxd dev.keyx | head",
    "echo $(cat dev.keyx)",  # command substitution
    "cat dev.keyx.bak",  # backup of a keyfile
    "less ./secrets/prod.kdbx",
    "FOO=bar cat dev.keyx",  # leading VAR= assignment, still a leak
]

ALLOW = [
    "uv run --locked kdbx.py get api/openai",
    "uv run skills/kdbx/kdbx.py run -- npm run dev",
    "keepassxc-cli show vault.kdbx entry",  # kdbx's own engine
    "cat README.md",
    "npm run dev",
    "ls ~/.config/keepassxc",  # listing the dir, not reading a file
    "grep TODO src/app.py",
    "",  # empty
]

# Role-guard: writes / value-exposure are a human role — the agent must not run them.
ROLE_DENY = [
    "uv run --locked /p/kdbx.py set api/openai",
    "kdbx set api/openai < secret.txt",
    "kdbx delete api/x --purge",
    "kdbx mv a b",
    "kdbx import .env",
    "kdbx rekey",
    "kdbx export --out .env",
    "uv run kdbx.py export",
    "kdbx get api/x --reveal",
    "kdbx get api/x --clip",
]

ROLE_ALLOW = [
    "kdbx run -- npm run dev",
    "uv run --locked skills/kdbx/kdbx.py run -- ./deploy.sh",
    "kdbx get api/openai",  # masked
    "kdbx list",
    "kdbx check",
    "kdbx envs",
    "kdbx init",  # creates a vault, authors no value (#9: agent may init)
    "kdbx install-launcher",
    "echo kdbx set is a human-only op",  # not an invocation -> not flagged
]


@pytest.mark.parametrize("cmd", DENY)
def test_denies_leaks(cmd):
    reason = guard.decide(cmd)
    assert reason and "leak-guard" in reason, f"expected deny for: {cmd!r}"


@pytest.mark.parametrize("cmd", ALLOW)
def test_allows_safe(cmd):
    assert guard.decide(cmd) is None, f"expected allow for: {cmd!r}"


@pytest.mark.parametrize("cmd", ROLE_DENY)
def test_role_guard_blocks_agent_writes(cmd):
    reason = guard.decide(cmd)
    assert reason and "role-guard" in reason, f"expected role-guard deny for: {cmd!r}"


@pytest.mark.parametrize("cmd", ROLE_ALLOW)
def test_role_guard_allows_reads(cmd):
    assert guard.decide(cmd) is None, f"expected allow for: {cmd!r}"


def test_env_dir_override(monkeypatch):
    monkeypatch.setenv("KEEPASSXC_DIR", "/tmp/kdbx-demo/vaults")
    # A reference inside the overridden dir is caught even without a .keyx/.kdbx suffix.
    assert guard.decide("cat /tmp/kdbx-demo/vaults/demo/notes") is not None
    assert guard.decide("cat /tmp/other/notes") is None


def _run(stdin_text):
    return subprocess.run(
        [sys.executable, str(_GUARD)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def test_subprocess_deny_contract():
    p = _run(json.dumps({"tool_input": {"command": "cat dev.keyx"}}))
    assert p.returncode == 0
    out = json.loads(p.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert "leak-guard" in hso["permissionDecisionReason"]


def test_subprocess_allow_is_silent():
    p = _run(json.dumps({"tool_input": {"command": "cat README.md"}}))
    assert p.returncode == 0
    assert p.stdout.strip() == ""


def test_subprocess_malformed_json_fails_open():
    p = _run("not json at all {")
    assert p.returncode == 0
    assert p.stdout.strip() == ""
