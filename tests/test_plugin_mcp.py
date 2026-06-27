"""Tests for the kdbx plugin MCP server (plugins/kdbx/mcp/server.py).

Hermetic: the op_* functions are exercised with the kdbx CLI runner stubbed out,
so no vault, uv, or MCP transport is needed. The key invariant under test is the
trust boundary — no tool ever crosses a plaintext secret.
"""

import importlib.util
import pathlib

import pytest

_SERVER = pathlib.Path(__file__).resolve().parents[1] / "plugins" / "kdbx" / "mcp" / "server.py"

_spec = importlib.util.spec_from_file_location("kdbx_mcp_server", _SERVER)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


@pytest.fixture
def captured(monkeypatch):
    """Capture the argv passed to the kdbx CLI and return a canned result."""
    calls = []

    def fake(args, cwd=None):
        calls.append(list(args))
        return "OUTPUT", 0

    monkeypatch.setattr(server, "_kdbx", fake)
    return calls


def test_get_is_masked_never_reveals(captured):
    server.op_get("api/openai")
    assert captured[0] == ["get", "api/openai"]
    assert "--reveal" not in captured[0]


def test_run_injects_via_run_dashdash(captured):
    server.op_run("npm run dev")
    assert captured[0] == ["run", "--", "npm", "run", "dev"]


def test_list_and_envs(captured):
    server.op_list()
    server.op_list("api")
    server.op_envs()
    assert captured == [["list"], ["list", "api"], ["envs"]]


def test_check_reports_status(monkeypatch):
    monkeypatch.setattr(server, "_kdbx", lambda a, cwd=None: ("", 5))
    assert server.op_check().startswith("drift (exit 5)")
    monkeypatch.setattr(server, "_kdbx", lambda a, cwd=None: ("", 0))
    assert server.op_check().startswith("ok")


def test_no_value_crossing_ops_exist():
    # The server must NOT expose set / export / reveal in any form.
    for forbidden in ("op_set", "op_export", "op_reveal"):
        assert not hasattr(server, forbidden), f"{forbidden} must not exist"
    assert set(server.FORBIDDEN_OPS) == {"set", "export", "reveal"}


def test_registered_tools_are_safe_only():
    mcp = pytest.importorskip("mcp")  # noqa: F841 — only run if SDK installed
    srv = server.build_server()
    import asyncio

    tools = {t.name for t in asyncio.run(srv.list_tools())}
    assert tools == set(server.SAFE_OPS)
    assert not any(bad in t for t in tools for bad in server.FORBIDDEN_OPS)
