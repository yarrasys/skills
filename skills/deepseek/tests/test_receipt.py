import importlib

r = importlib.import_module("deepseek_core.receipt")


def test_verify_result_none_when_no_cmd():
    assert r.verify_result(None, None) is None


def test_verify_result_pass():
    assert r.verify_result("ruff check x.py", 0) == {
        "cmd": "ruff check x.py",
        "exit": 0,
        "passed": True,
    }


def test_verify_result_fail_includes_tail():
    res = r.verify_result("pytest", 1, tail="E   assert 1 == 2")
    assert res["passed"] is False
    assert res["tail"] == "E   assert 1 == 2"


def test_build_receipt_omits_patch_when_none():
    rc = r.build_receipt(
        status="applied",
        workspace="in_place",
        files=[{"path": "x.py", "diffstat": "+1 -0"}],
        verify=None,
        patch=None,
        cost={"reported_usd": None, "note": "n/a"},
        turns=1,
    )
    assert "patch" not in rc
    assert rc["status"] == "applied"
    assert rc["files"][0]["path"] == "x.py"


def test_build_receipt_includes_patch():
    rc = r.build_receipt(
        status="patch_ready",
        workspace="worktree",
        files=[],
        verify={"cmd": "ruff", "exit": 0, "passed": True},
        patch=".deepseek/edit-abc.patch",
        cost={"reported_usd": 0.001, "note": "approx"},
        turns=2,
    )
    assert rc["patch"] == ".deepseek/edit-abc.patch"


def test_compute_cost_falls_back_to_anthropic_without_pricing():
    result = {"total_cost_usd": 0.30, "usage": {"input_tokens": 1000, "output_tokens": 500}}
    usd, note = r.compute_cost(result, None)
    assert usd == 0.30
    assert note == r.ANTHROPIC_COST_NOTE


def test_compute_cost_uses_deepseek_pricing_when_configured():
    result = {
        "total_cost_usd": 0.30,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 500_000},
    }
    usd, note = r.compute_cost(result, {"inputPerMTok": 0.27, "outputPerMTok": 1.10})
    # 1M input @ 0.27 + 0.5M output @ 1.10 = 0.27 + 0.55 = 0.82
    assert abs(usd - 0.82) < 1e-9
    assert note == r.DEEPSEEK_COST_NOTE


def test_compute_cost_counts_cache_tokens_as_input():
    result = {
        "usage": {"input_tokens": 0, "cache_read_input_tokens": 2_000_000, "output_tokens": 0}
    }
    usd, _ = r.compute_cost(result, {"inputPerMTok": 0.10, "outputPerMTok": 1.00})
    assert abs(usd - 0.20) < 1e-9  # 2M cache-read input @ 0.10


def test_compute_cost_falls_back_when_no_usage():
    result = {"total_cost_usd": 0.05}  # no usage block
    usd, note = r.compute_cost(result, {"inputPerMTok": 0.27, "outputPerMTok": 1.10})
    assert usd == 0.05
    assert note == r.ANTHROPIC_COST_NOTE


def test_compute_cost_falls_back_when_pricing_incomplete():
    result = {"total_cost_usd": 0.05, "usage": {"input_tokens": 1000, "output_tokens": 500}}
    usd, note = r.compute_cost(result, {"inputPerMTok": 0.27})  # missing outputPerMTok
    assert usd == 0.05
    assert note == r.ANTHROPIC_COST_NOTE
