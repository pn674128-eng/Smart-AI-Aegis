# -*- coding: utf-8 -*-
"""
Thinking Programming - L0/L1/L2 layers on intuitive baseline.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from smart_ai_cam_state.runtime_state import state as runtime_state

from . import intuitive_programming as ip
from . import thinking_l2_plan as l2
from .programming_modes import MODE_INTUITIVE, MODE_THINKING, mode_display_name, usage_tier_for_mode

LAYER_L0 = "L0_intuitive_baseline"
LAYER_L1 = "L1_extended_features"
LAYER_L2 = l2.LAYER_L2

DEFAULT_LAYER = LAYER_L0
IMPLEMENTED_LAYERS = (LAYER_L0, LAYER_L1, LAYER_L2)

_LAYER_DOC = {
    LAYER_L0: "Same as intuitive: templates + execute, tagged thinking",
    LAYER_L1: "Extended: pocket R, official pockets, multi-terrace Z bind",
    LAYER_L2: "Multi-Setup: top side then flip checkpoint then bottom through holes",
}


def resolve_thinking_layer(params: dict) -> str:
    layer = str(params.get("thinking_layer") or params.get("layer") or DEFAULT_LAYER).strip()
    if layer not in _LAYER_DOC:
        return DEFAULT_LAYER
    return layer


def _limits_profile_for_layer(layer: str) -> str:
    if layer == LAYER_L1:
        return "thinking_l1"
    return "intuitive"


def format_thinking_eligibility_report(eligibility: dict, layer: str) -> str:
    banner = (
        "[Thinking {}]\n"
        "Seed: intuitive baseline first, then extend.\n"
        "{}\n"
    ).format(layer, _LAYER_DOC.get(layer, ""))
    if layer == LAYER_L2:
        base = eligibility.get("summary") or ""
        l0 = eligibility.get("l0_eligibility") or {}
        l1 = eligibility.get("l1_eligibility") or {}
        if l0.get("report_text"):
            base = l0.get("report_text") + "\n\n" + base
        if l1.get("summary"):
            base += "\n\n[L1 extended]\n" + str(l1.get("summary"))
        return banner + "\n" + base
    base = eligibility.get("report_text") or ip.format_eligibility_report(eligibility)
    if not eligibility.get("eligible"):
        base += "\n\nHint: L0 needs intuitive whitelist; L1 relaxes pocket R / official."
    return banner + "\n" + base


def run_check_thinking_eligibility(params: dict, ctx: dict) -> dict:
    layer = resolve_thinking_layer(params)
    material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
    runtime_state.current_material = material

    if layer not in IMPLEMENTED_LAYERS:
        return {
            "success": False,
            "error": "Layer not implemented: {}".format(layer),
            "data": {
                "programming_mode": MODE_THINKING,
                "thinking_layer": layer,
                "implemented_layers": list(IMPLEMENTED_LAYERS),
            },
        }

    try:
        snapshot = ip.collect_part_snapshot(material, ctx)
        if layer == LAYER_L2:
            eligibility = l2.evaluate_l2_eligibility(snapshot, material=material, ctx=ctx)
            eligibility["report_text"] = format_thinking_eligibility_report(eligibility, layer)
        else:
            profile = _limits_profile_for_layer(layer)
            eligibility = ip.evaluate_intuitive_eligibility(
                snapshot, material=material, ctx=ctx, limits_profile=profile
            )
            eligibility["programming_mode"] = MODE_THINKING
            eligibility["usage_tier"] = usage_tier_for_mode(MODE_THINKING)
            eligibility["thinking_layer"] = layer
            eligibility["seed_mode"] = MODE_INTUITIVE
            eligibility["intuitive_baseline_eligible"] = bool(eligibility.get("eligible"))
            eligibility["report_text"] = format_thinking_eligibility_report(eligibility, layer)
        return {"success": True, "data": eligibility}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_l2_sequence(
    params: dict,
    ctx: dict,
    *,
    get_recommendations: Callable[[dict, dict], dict],
    execute_from_palette: Optional[Callable[[dict], None]],
    ensure_cam_setup: Optional[Callable[[], dict]],
    full_rescan: Optional[Callable[[str], None]] = None,
    ensure_setup: Optional[Callable[..., dict]] = None,
) -> dict:
    from smart_ai_cam_machining import setup_service as ss

    material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
    do_execute = bool(params.get("execute", True))
    resume_seq = int(params.get("resume_from_sequence", 0) or 0)
    plan_id = str(params.get("multi_setup_plan_id") or params.get("plan_id") or "").strip()
    top_name = str(params.get("top_setup_name") or ss.resolve_top_setup_name()).strip()
    bottom_name = str(
        params.get("bottom_setup_name") or ss.resolve_bottom_setup_name()
    ).strip()

    ensure_fn = ensure_setup or ss.ensure_setup
    rescan_fn = full_rescan

    multi_plan = None
    if resume_seq >= 2:
        multi_plan = l2.get_cached_multi_setup_plan(plan_id or None)
        if not multi_plan:
            return {
                "success": False,
                "error": "No cached L2 plan. Run L2 Setup1 first or pass multi_setup_plan_id.",
            }
    else:
        snapshot = ip.collect_part_snapshot(material, ctx)
        eligibility = l2.evaluate_l2_eligibility(snapshot, material=material, ctx=ctx)
        if not eligibility.get("eligible"):
            return {
                "success": False,
                "error": eligibility.get("summary", "L2 eligibility failed"),
                "data": {"eligibility": eligibility, "executed": False},
            }

        if callable(ensure_cam_setup):
            setup_res = ensure_cam_setup()
            if not setup_res.get("success"):
                return {"success": False, "error": setup_res.get("error", "Setup failed")}

        run_params = dict(params)
        run_params["thinking_layer"] = LAYER_L1
        run_params["limits_profile"] = "thinking_l1"
        run_params["material"] = material

        rec_res = get_recommendations(run_params, ctx)
        if not rec_res.get("success"):
            return rec_res
        ai_data = rec_res.get("data") or {}

        plan_validation = ip.validate_ai_recommendations_for_execute(ai_data, ctx, material)
        if not plan_validation.get("ok"):
            return {
                "success": False,
                "error": "L2 plan validation failed: "
                + "；".join(plan_validation.get("issues") or []),
                "data": {
                    "validation": plan_validation.get("validation"),
                    "validation_2d": plan_validation.get("validation_2d"),
                    "executed": False,
                },
            }

        holes_panel = ctx["build_hole_data"](material)
        setup_name = top_name
        try:
            cam_setup = ctx.get("cam_setup")
            if cam_setup is not None:
                setup_name = str(cam_setup.name)
        except Exception:
            pass

        base_plan = ip.build_execute_plan_from_ai(
            ai_data,
            setup_name=setup_name,
            material=material,
            programming_mode=MODE_THINKING,
            thinking_layer=LAYER_L1,
        )
        multi_plan = l2.build_l2_multi_setup_plan(
            base_plan,
            snapshot=snapshot,
            material=material,
            top_setup_name=top_name,
            bottom_setup_name=bottom_name,
            plan_id=plan_id or None,
            holes_panel=holes_panel,
        )
        l2.cache_multi_setup_plan(multi_plan)

    executed_sequences: List[int] = []
    messages: List[str] = []
    checkpoint = None
    wcs_gate = None

    if resume_seq >= 2:
        sequences = [2]
    else:
        sequences = [1]
        if not do_execute or not l2.THINKING_L2_REQUIRE_MANUAL_FLIP:
            sequences.append(2)

    for seq in sequences:
        entry = l2.setup_entry_by_sequence(multi_plan, seq)
        if not entry:
            continue
        sname = str(entry.get("setup_name") or "")
        wcs_action = str(entry.get("wcs_action") or "")

        if (
            seq == 2
            and wcs_action == "manual_flip_wcs"
            and not bool(params.get("confirm_flip") or params.get("wcs_confirmed"))
        ):
            cps = multi_plan.get("checkpoints") or []
            checkpoint = cps[0] if cps else None
            wcs_gate = {
                "setup_name": sname,
                "wcs_action": wcs_action,
                "message": "Confirm flip/WCS on {} then resume with confirm_flip=true".format(sname),
            }
            break

        ensure_res = ensure_fn(sname, create_if_missing=True)
        if not ensure_res.get("success"):
            return {
                "success": False,
                "error": ensure_res.get("error", "Setup ensure failed"),
                "data": {
                    "multi_setup_plan": multi_plan,
                    "failed_sequence": seq,
                    "executed_sequences": executed_sequences,
                },
            }
        if callable(rescan_fn):
            try:
                rescan_fn(sname)
            except Exception as ex:
                try:
                    from smart_ai_cam_ui.diagnostics import send_diag_log

                    send_diag_log("[L2] rescan failed on {}: {}".format(sname, ex))
                except Exception:
                    pass

        if seq == 2:
            try:
                holes_panel = ctx["build_hole_data"](material)
                refreshed = l2.refresh_setup_execute_plan(entry, holes_panel)
                entry = refreshed
                multi_plan = dict(multi_plan or {})
                setups = []
                for st in multi_plan.get("setups") or []:
                    if int(st.get("sequence", 0) or 0) == 2:
                        setups.append(refreshed)
                    else:
                        setups.append(st)
                multi_plan["setups"] = setups
                l2.cache_multi_setup_plan(multi_plan)
                n_rows = len((refreshed.get("execute_plan") or {}).get("rows") or [])
                messages.append("Setup2 hole rows remapped: {}".format(n_rows))
            except Exception as ex:
                try:
                    from smart_ai_cam_ui.diagnostics import send_diag_log

                    send_diag_log("[L2] hole remap failed: {}".format(ex))
                except Exception:
                    pass

        exec_plan = dict(entry.get("execute_plan") or {})
        exec_plan["setup"] = sname
        exec_plan["thinking_layer"] = LAYER_L2
        exec_plan["multi_setup_plan_id"] = multi_plan.get("plan_id")
        exec_plan["setup_sequence"] = seq
        exec_plan["wcs_action"] = wcs_action

        if do_execute and callable(execute_from_palette):
            execute_from_palette(exec_plan)
            executed_sequences.append(seq)
            messages.append("Setup{} executed on {}".format(seq, sname))

        if seq == 1 and l2.THINKING_L2_REQUIRE_MANUAL_FLIP and resume_seq < 2:
            cps = multi_plan.get("checkpoints") or []
            checkpoint = cps[0] if cps else None
            break

    if resume_seq >= 2 and executed_sequences:
        l2.clear_pending_multi_setup_plan()

    report = l2.format_l2_report(multi_plan, executed_sequences=executed_sequences)
    done_all = set(executed_sequences) >= {1, 2}
    awaiting_flip = 1 in executed_sequences and 2 not in executed_sequences
    awaiting_wcs = bool(wcs_gate)

    return {
        "success": True,
        "message": "; ".join(messages) if messages else (
            wcs_gate.get("message") if wcs_gate else "L2 plan ready"
        ),
        "data": {
            "programming_mode": MODE_THINKING,
            "thinking_layer": LAYER_L2,
            "seed_mode": MODE_INTUITIVE,
            "multi_setup_plan": multi_plan,
            "executed_sequences": executed_sequences,
            "executed": bool(executed_sequences) and do_execute,
            "awaiting_flip_checkpoint": awaiting_flip,
            "awaiting_wcs_confirm": awaiting_wcs,
            "wcs_gate": wcs_gate,
            "checkpoint": checkpoint,
            "completed": done_all,
            "report_text": report,
            "persist_path": (multi_plan or {}).get("persist_path"),
        },
    }


def run_thinking_programming(
    params: dict,
    ctx: dict,
    *,
    get_recommendations: Callable[[dict, dict], dict],
    execute_from_palette: Optional[Callable[[dict], None]] = None,
    ensure_cam_setup: Optional[Callable[[], dict]] = None,
    full_rescan: Optional[Callable[[str], None]] = None,
    ensure_setup: Optional[Callable[..., dict]] = None,
) -> dict:
    layer = resolve_thinking_layer(params)

    if layer not in IMPLEMENTED_LAYERS:
        return {
            "success": False,
            "error": "Layer not implemented: {}; have {}".format(
                layer, ", ".join(IMPLEMENTED_LAYERS)
            ),
            "data": {
                "programming_mode": MODE_THINKING,
                "thinking_layer": layer,
                "implemented_layers": list(IMPLEMENTED_LAYERS),
            },
        }

    if layer == LAYER_L2:
        return _run_l2_sequence(
            params,
            ctx,
            get_recommendations=get_recommendations,
            execute_from_palette=execute_from_palette,
            ensure_cam_setup=ensure_cam_setup,
            full_rescan=full_rescan,
            ensure_setup=ensure_setup,
        )

    if layer == LAYER_L1:
        banner = (
            "[Thinking L1] Extended features on intuitive chain: "
            "multi-terrace, pocket R, official pockets if ME recognized."
        )
    else:
        banner = (
            "[Thinking L0] Same path as intuitive (2D then 3D), tagged thinking."
        )

    run_params = dict(params)
    run_params["thinking_layer"] = layer
    run_params["limits_profile"] = _limits_profile_for_layer(layer)

    res = ip.run_intuitive_programming(
        run_params,
        ctx,
        get_recommendations=get_recommendations,
        execute_from_palette=execute_from_palette,
        ensure_cam_setup=ensure_cam_setup,
        programming_mode=MODE_THINKING,
        report_banner=banner,
        thinking_layer=layer,
    )

    data = dict(res.get("data") or {})
    data["thinking_layer"] = layer
    data["seed_mode"] = MODE_INTUITIVE
    data["philosophy"] = "intuitive_first" if layer == LAYER_L0 else "l1_extended"
    res["data"] = data
    if res.get("success"):
        label = "L1 extended" if layer == LAYER_L1 else "intuitive baseline"
        res["message"] = "Thinking {} ({})".format(layer, label) + (
            " executed" if data.get("executed") else " plan ready"
        )
    return res


def describe_layers() -> Dict[str, Any]:
    return {
        "default": DEFAULT_LAYER,
        "implemented": list(IMPLEMENTED_LAYERS),
        "layers": {k: v for k, v in _LAYER_DOC.items()},
        "seed_mode": MODE_INTUITIVE,
        "display_name": mode_display_name(MODE_THINKING),
        "l2": {
            "max_setups": l2.THINKING_L2_MAX_SETUPS,
            "require_manual_flip": l2.THINKING_L2_REQUIRE_MANUAL_FLIP,
            "default_bottom_setup": l2.DEFAULT_BOTTOM_SETUP,
            "plan_persist_dir": l2.L2_PLANS_DIR,
            "requires_l1_eligible": True,
        },
    }
