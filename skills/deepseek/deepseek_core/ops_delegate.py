"""The `delegate` and `apply` operations — orchestrates the nested claude run."""

import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

from . import config, guardrails, receipt, runner, workspace

MAX_TURNS = 8
TIMEOUT_S = 900
ALLOWED_TOOLS = ["Read", "Edit", "Write", "Bash"]
COST_NOTE = receipt.ANTHROPIC_COST_NOTE


def _emit(rc_dict: dict) -> None:
    sys.stdout.write(json.dumps(rc_dict, indent=2) + "\n")


def _run_verify(cmd, cwd, files):
    if not cmd:
        return None
    if "{file}" in cmd and not files:
        # No changes were made — running the verify template against a literal
        # "{file}" would be a spurious failure, not a real signal.
        return None
    expanded = cmd.replace("{file}", " ".join(shlex.quote(f) for f in files)) if files else cmd
    proc = subprocess.run(expanded, shell=True, cwd=str(cwd), capture_output=True, text=True)
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
    return receipt.verify_result(expanded, proc.returncode, tail)


def cmd_delegate(args) -> int:
    if guardrails.is_recursive(os.environ):
        sys.stderr.write("deepseek: refusing to recurse (DEEPSEEK_DELEGATE_DEPTH set)\n")
        return 4

    key = runner.resolve_key(os.environ)
    if not key:
        sys.stderr.write(
            "deepseek: no DEEPSEEK_API_KEY — set it, or have a human run:\n"
            "  kdbx set api/deepseek --var DEEPSEEK_API_KEY\n"
        )
        return 3

    repo = pathlib.Path(args.dir).resolve() if args.dir else pathlib.Path.cwd()
    cfg = config.load_config(repo)
    model = args.model or cfg["model"]
    verify_cmd = args.verify if args.verify is not None else cfg.get("verifyDefault")
    isolate = (
        not args.in_place
    )  # auto-mode isolation is enforced by the parent choosing not to pass --in-place

    if args.in_place and workspace.is_dirty(repo):
        sys.stderr.write(
            "deepseek: --in-place requires a clean working tree (commit or stash first)\n"
        )
        return 7

    tag = uuid.uuid4().hex[:8]
    workdir = workspace.create_worktree(repo, tag) if isolate else repo
    settings_dir = pathlib.Path(tempfile.mkdtemp(prefix="deepseek-"))

    try:
        settings = runner.write_child_settings(settings_dir, model)
        argv = runner.build_argv(
            args.task,
            model=model,
            allowed_tools=ALLOWED_TOOLS,
            settings_path=str(settings),
            max_turns=MAX_TURNS,
        )
        # Snapshot the main tree so we can detect a child that escapes isolation and
        # writes into the real repo instead of its worktree (#26).
        main_before = workspace.status_set(repo) if isolate else set()
        env = runner.build_child_env(os.environ, key)
        child = runner.run_child(argv, env, workdir, TIMEOUT_S)

        if not child["ok"]:
            _emit(
                receipt.build_receipt(
                    status="error",
                    workspace="worktree" if isolate else "in_place",
                    files=[],
                    verify=None,
                    patch=None,
                    cost={"reported_usd": None, "note": COST_NOTE},
                    turns=0,
                )
            )
            sys.stderr.write(f"deepseek: child failed — {child['stderr_tail']}\n")
            return 7

        result = child["result"]
        usd, cost_note = receipt.compute_cost(result, cfg.get("deepseekPricing"))
        cost = {"reported_usd": usd, "note": cost_note}
        turns = result.get("num_turns", 0)

        if result.get("is_error"):
            _emit(
                receipt.build_receipt(
                    status="error",
                    workspace="worktree" if isolate else "in_place",
                    files=[],
                    verify=None,
                    patch=None,
                    cost=cost,
                    turns=turns,
                )
            )
            sys.stderr.write("deepseek: child reported is_error — no verify/apply run\n")
            return 7

        ws_label = "worktree" if isolate else "in_place"

        # #26: a child that wrote into the main tree escaped its worktree — refuse to
        # treat that as a normal result. Nothing is applied; surface it for inspection.
        if isolate:
            intruded = workspace.status_set(repo) - main_before
            if intruded:
                _emit(
                    receipt.build_receipt(
                        status="isolation_breach",
                        workspace="worktree",
                        files=[{"path": ln[3:].strip()} for ln in sorted(intruded)],
                        verify=None,
                        patch=None,
                        cost=cost,
                        turns=turns,
                    )
                )
                sys.stderr.write(
                    "deepseek: isolation breach — the child wrote into the main tree "
                    "outside its worktree; nothing applied. Inspect with: git status\n"
                )
                return 7

        files = workspace.numstat(workdir)
        changed = [f["path"] for f in files]

        # #26: nothing changed in the workspace — a genuine no-op. Report it as its own
        # status; an empty patch would not apply, and "applied"/"patch_ready" would lie.
        if not files:
            _emit(
                receipt.build_receipt(
                    status="no_changes",
                    workspace=ws_label,
                    files=[],
                    verify=None,
                    patch=None,
                    cost=cost,
                    turns=turns,
                )
            )
            return 0

        verify = _run_verify(verify_cmd, workdir, changed)

        # guardrails on the resulting change set
        denied = guardrails.denied_paths(changed, cfg["auto"]["denyGlobs"])
        over_budget = not guardrails.within_budget(
            cost["reported_usd"], cfg["auto"]["maxCostUsdPerRun"]
        )

        if verify and not verify["passed"]:
            _emit(
                receipt.build_receipt(
                    status="verify_failed",
                    workspace=ws_label,
                    files=files,
                    verify=verify,
                    patch=None,
                    cost=cost,
                    turns=turns,
                )
            )
            if not isolate:
                workspace.restore(repo)
            return 5
        if denied:
            _emit(
                receipt.build_receipt(
                    status="denied",
                    workspace=ws_label,
                    files=files,
                    verify=verify,
                    patch=None,
                    cost=cost,
                    turns=turns,
                )
            )
            sys.stderr.write(f"deepseek: change touches denied paths: {denied}\n")
            if not isolate:
                workspace.restore(repo)
            return 6
        if over_budget:
            _emit(
                receipt.build_receipt(
                    status="budget_exceeded",
                    workspace=ws_label,
                    files=files,
                    verify=verify,
                    patch=None,
                    cost=cost,
                    turns=turns,
                )
            )
            if not isolate:
                workspace.restore(repo)
            return 6

        if isolate:
            patch_rel = pathlib.Path(".deepseek") / f"edit-{tag}.patch"
            workspace.write_patch(workdir, repo / patch_rel)
            _emit(
                receipt.build_receipt(
                    status="patch_ready",
                    workspace="worktree",
                    files=files,
                    verify=verify,
                    patch=str(patch_rel),
                    cost=cost,
                    turns=turns,
                )
            )
            return 0

        _emit(
            receipt.build_receipt(
                status="applied",
                workspace="in_place",
                files=files,
                verify=verify,
                patch=None,
                cost=cost,
                turns=turns,
            )
        )
        return 0
    finally:
        if isolate and workdir.exists():
            workspace.remove_worktree(repo, workdir)
        shutil.rmtree(settings_dir, ignore_errors=True)


def cmd_apply(args) -> int:
    repo = pathlib.Path.cwd()
    patch = (repo / args.patch).resolve()
    if not patch.is_file():
        sys.stderr.write(f"deepseek: patch not found: {args.patch}\n")
        return 2
    try:
        workspace.apply_patch(repo, patch)
    except subprocess.CalledProcessError as exc:
        stderr_tail = "\n".join((exc.stderr or "").strip().splitlines()[-5:])
        sys.stderr.write(f"deepseek: failed to apply patch {args.patch} — {stderr_tail}\n")
        return 7
    sys.stderr.write(f"applied {args.patch}\n")
    return 0
