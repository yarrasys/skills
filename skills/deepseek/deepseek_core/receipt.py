"""Pure shaping of the compact delegation receipt."""

ANTHROPIC_COST_NOTE = "child-reported, Anthropic-priced — approximate"
DEEPSEEK_COST_NOTE = "DeepSeek-priced from .deepseek.json deepseekPricing rates"


def compute_cost(result, pricing):
    """Return (reported_usd, note) for a child result.

    When `pricing` (a dict with `inputPerMTok`/`outputPerMTok`) is configured and the
    child reported token usage, price the run at DeepSeek's rates — the child's own
    `total_cost_usd` is Anthropic-priced and overstates DeepSeek spend. Otherwise fall
    back to the Anthropic figure, labelled as approximate.
    """
    usage = result.get("usage") or {}
    in_tok = (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )
    out_tok = usage.get("output_tokens", 0)
    in_rate = (pricing or {}).get("inputPerMTok")
    out_rate = (pricing or {}).get("outputPerMTok")
    if in_rate is not None and out_rate is not None and (in_tok or out_tok):
        usd = in_tok / 1_000_000 * in_rate + out_tok / 1_000_000 * out_rate
        return usd, DEEPSEEK_COST_NOTE
    return result.get("total_cost_usd"), ANTHROPIC_COST_NOTE


def verify_result(cmd, exit_code, tail: str = ""):
    if cmd is None:
        return None
    passed = exit_code == 0
    res = {"cmd": cmd, "exit": exit_code, "passed": passed}
    if not passed and tail:
        res["tail"] = tail
    return res


def build_receipt(*, status, workspace, files, verify, patch, cost, turns) -> dict:
    rc = {
        "status": status,
        "workspace": workspace,
        "files": files,
        "verify": verify,
        "cost": cost,
        "turns": turns,
    }
    if patch is not None:
        rc["patch"] = patch
    return rc
