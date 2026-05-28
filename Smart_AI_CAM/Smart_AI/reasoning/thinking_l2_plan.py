# -*- coding: utf-8 -*-
"""Thinking L2 - multi-Setup plan builder."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Set

from smart_ai_cam_state.runtime_state import state as runtime_state

from . import intuitive_programming as ip

LAYER_L2 = "L2_deeper_plan"
THINKING_L2_MAX_SETUPS = 2
THINKING_L2_REQUIRE_MANUAL_FLIP = True
DEFAULT_TOP_SETUP = "AI_Auto_Setup"
DEFAULT_BOTTOM_SETUP = "AI_Setup_Bottom"

_L2_PLANS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "memory",
    "data",
    "l2_plans",
)
L2_PLANS_DIR = _L2_PLANS_DIR


def _document_storage_key() -> str:
    try:
        import adsk.core

        app = adsk.core.Application.get()
        doc = app.activeDocument if app else None
        if doc and doc.name:
            return re.sub(r"[^\w\-]+", "_", str(doc.name))[:80]
    except Exception:
        pass
    return "unknown_doc"


def hole_identity_key(hole_row: Optional[dict]) -> str:
    """Stable fingerprint for a hole panel row (survives resort/rescan when geometry unchanged)."""
    if not isinstance(hole_row, dict):
        return ""
    dia = str(hole_row.get("dia", hole_row.get("diameter_mm", "")) or "").strip()
    direction = str(hole_row.get("dir", "Z+") or "Z+").strip()
    through = "1" if bool(hole_row.get("through")) else "0"
    depth = str(hole_row.get("depth", hole_row.get("depth_mm", "")) or "").strip()
    count = str(hole_row.get("count", 1) or 1)
    cb = str(hole_row.get("cbTopDia", "") or "").strip()
    return "dia:{}|dir:{}|th:{}|depth:{}|n:{}|cb:{}".format(
        dia, direction, through, depth, count, cb
    )


def _hole_bindings_for_indices(
    holes_panel: Optional[List[dict]],
    indices: Set[int],
    base_plan_rows: Optional[List[dict]],
) -> List[dict]:
    rows_by_idx = {}
    for r in base_plan_rows or []:
        if not isinstance(r, dict) or "idx" not in r:
            continue
        rows_by_idx[int(r["idx"])] = r
    bindings: List[dict] = []
    for idx in sorted(indices):
        hole = {}
        if holes_panel and 0 <= idx < len(holes_panel):
            hole = holes_panel[idx] or {}
        row = rows_by_idx.get(idx, {})
        bindings.append(
            {
                "original_idx": int(idx),
                "identity": hole_identity_key(hole),
                "tmplIdx": int(row.get("tmplIdx", 0)),
            }
        )
    return bindings


def rebuild_execute_rows_from_bindings(
    holes_panel: Optional[List[dict]],
    bindings: Optional[List[dict]],
) -> List[dict]:
    """Remap execute hole rows after rescan using stored identity keys."""
    panel = list(holes_panel or [])
    used: Set[int] = set()
    rows: List[dict] = []
    for b in bindings or []:
        if not isinstance(b, dict):
            continue
        ident = str(b.get("identity") or "").strip()
        tmpl_idx = int(b.get("tmplIdx", 0))
        found = -1
        if ident:
            for idx, h in enumerate(panel):
                if idx in used:
                    continue
                if hole_identity_key(h) == ident:
                    found = idx
                    used.add(idx)
                    break
        if found < 0:
            orig = int(b.get("original_idx", -1))
            if 0 <= orig < len(panel) and orig not in used:
                found = orig
                used.add(found)
        if found >= 0:
            rows.append({"idx": found, "tmplIdx": tmpl_idx})
    return rows


def analyze_hole_sides(holes_panel: Optional[List[dict]]) -> dict:
    top_indices: List[int] = []
    bottom_through_indices: List[int] = []
    skipped_back_cs: List[int] = []
    for idx, h in enumerate(holes_panel or []):
        if not isinstance(h, dict):
            continue
        d = str(h.get("dir", "Z+") or "Z+")
        through = bool(h.get("through"))
        is_back_cs = d == "Z-(CB)" or (
            d == "Z-" and bool(h.get("isCBLarge") or h.get("isCBSmall"))
        )
        if is_back_cs:
            skipped_back_cs.append(idx)
            continue
        if d.startswith("Z+"):
            top_indices.append(idx)
        elif d == "Z-" and through:
            bottom_through_indices.append(idx)
    return {
        "top_hole_indices": top_indices,
        "bottom_through_hole_indices": bottom_through_indices,
        "skipped_back_countersink_indices": skipped_back_cs,
        "has_dual_side_through": len(bottom_through_indices) > 0,
        "top_count": len(top_indices),
        "bottom_through_count": len(bottom_through_indices),
    }


def enrich_snapshot_with_hole_sides(snapshot: dict, holes_panel: Optional[List[dict]]) -> dict:
    out = dict(snapshot or {})
    sides = analyze_hole_sides(holes_panel)
    out["hole_sides"] = sides
    out["has_dual_side_through"] = bool(sides.get("has_dual_side_through"))
    return out


def evaluate_l2_eligibility(snapshot: dict, *, material: Optional[str] = None, ctx: Optional[dict] = None) -> dict:
    checks: List[dict] = []
    l0 = ip.evaluate_intuitive_eligibility(snapshot, material=material, ctx=ctx, limits_profile="intuitive")
    checks.append({"id": "l0_baseline", "ok": bool(l0.get("eligible")), "message": "L0 baseline"})
    l1 = ip.evaluate_intuitive_eligibility(snapshot, material=material, ctx=ctx, limits_profile="thinking_l1")
    checks.append(
        {
            "id": "l1_extended",
            "ok": bool(l1.get("eligible")),
            "message": "L1 extended (L2 plan uses L1 recommendations)",
        }
    )
    sides = snapshot.get("hole_sides") or {}
    has_dual = bool(snapshot.get("has_dual_side_through") or sides.get("has_dual_side_through"))
    bottom_n = int(sides.get("bottom_through_count", 0) or 0)
    top_n = int(sides.get("top_count", 0) or 0)
    all_ok = bool(l0.get("eligible")) and bool(l1.get("eligible")) and has_dual
    checks.append({"id": "dual_side_signal", "ok": has_dual, "message": "dual-side through holes", "detail": sides})
    summary = "[L2] OK top {} bottom {}".format(top_n, bottom_n) if all_ok else "[L2] FAIL"
    return {
        "programming_mode": "thinking",
        "thinking_layer": LAYER_L2,
        "eligible": bool(all_ok),
        "l0_eligible": bool(l0.get("eligible")),
        "l1_eligible": bool(l1.get("eligible")),
        "checks": checks,
        "summary": summary,
        "snapshot": snapshot,
        "hole_sides": sides,
        "limits": {"max_setups": THINKING_L2_MAX_SETUPS, "require_manual_flip": THINKING_L2_REQUIRE_MANUAL_FLIP},
        "l0_eligibility": l0,
        "l1_eligibility": l1,
    }


def filter_execute_plan_for_side(
    base_plan: dict,
    hole_indices: Set[int],
    *,
    include_2d: bool = True,
    include_3d: bool = True,
    setup_name: str = "",
    hole_bindings: Optional[List[dict]] = None,
) -> dict:
    plan = copy.deepcopy(base_plan or {})
    if setup_name:
        plan["setup"] = setup_name
    rows = []
    bindings_by_idx = {
        int(b.get("original_idx", -1)): b for b in (hole_bindings or []) if isinstance(b, dict)
    }
    for r in plan.get("rows") or []:
        if not isinstance(r, dict):
            continue
        idx = int(r.get("idx", -1))
        if idx in hole_indices:
            row = {"idx": idx, "tmplIdx": r.get("tmplIdx", 0)}
            if idx in bindings_by_idx:
                row["hole_identity"] = bindings_by_idx[idx].get("identity")
            rows.append(row)
    plan["rows"] = rows
    if not include_2d:
        for k in ("topFaceRough", "topFaceFinish", "profileRough", "profileFinish", "contourChamfer", "topFace", "profile"):
            plan[k] = "(不使用)"
        plan["terraceFaceOps"] = []
    if not include_3d:
        plan["slotRows"] = []
        plan["pocketCornerRRows"] = []
        plan["officialSlotPocketRows"] = []
        plan["officialPocketSlotRows"] = []
        plan["officialPocketRows"] = []
    plan["programming_mode"] = plan.get("programming_mode") or "thinking"
    plan["thinking_layer"] = LAYER_L2
    plan["seed_mode"] = ip.PROGRAMMING_MODE
    return plan


def build_l2_multi_setup_plan(
    base_execute_plan: dict,
    *,
    snapshot: dict,
    material: str,
    top_setup_name: str,
    bottom_setup_name: str,
    plan_id: Optional[str] = None,
    holes_panel: Optional[List[dict]] = None,
) -> dict:
    sides = snapshot.get("hole_sides") or analyze_hole_sides(holes_panel or [])
    top_set = set(sides.get("top_hole_indices") or [])
    bottom_set = set(sides.get("bottom_through_hole_indices") or [])
    base_rows = list((base_execute_plan or {}).get("rows") or [])
    top_bindings = _hole_bindings_for_indices(holes_panel, top_set, base_rows)
    bottom_bindings = _hole_bindings_for_indices(holes_panel, bottom_set, base_rows)
    plan1 = filter_execute_plan_for_side(
        base_execute_plan,
        top_set,
        include_2d=True,
        include_3d=True,
        setup_name=top_setup_name,
        hole_bindings=top_bindings,
    )
    plan2 = filter_execute_plan_for_side(
        base_execute_plan,
        bottom_set,
        include_2d=False,
        include_3d=False,
        setup_name=bottom_setup_name,
        hole_bindings=bottom_bindings,
    )
    pid = plan_id or str(uuid.uuid4())
    return {
        "version": "1.1",
        "plan_id": pid,
        "programming_mode": "thinking",
        "thinking_layer": LAYER_L2,
        "seed_mode": ip.PROGRAMMING_MODE,
        "material": material,
        "document_key": _document_storage_key(),
        "metadata": {
            "reason": "dual_side_through_holes",
            "top_hole_count": len(top_set),
            "bottom_hole_count": len(bottom_set),
            "hole_sides": sides,
            "hole_row_bindings": {
                "top": top_bindings,
                "bottom": bottom_bindings,
            },
        },
        "setups": [
            {
                "sequence": 1,
                "side": "top",
                "setup_name": top_setup_name,
                "wcs_action": "use_active",
                "execute_plan": plan1,
                "hole_bindings": top_bindings,
                "feature_summary": {"holes": len(top_set), "include_2d": True, "include_3d": True},
            },
            {
                "sequence": 2,
                "side": "bottom",
                "setup_name": bottom_setup_name,
                "wcs_action": "manual_flip_wcs",
                "execute_plan": plan2,
                "hole_bindings": bottom_bindings,
                "feature_summary": {"holes": len(bottom_set), "include_2d": False, "include_3d": False},
            },
        ],
        "checkpoints": [
            {
                "after_sequence": 1,
                "type": "manual_flip",
                "message": "Flip part; orient WCS on {}; resume sequence 2".format(bottom_setup_name),
                "wcs_action": "manual_flip_wcs",
                "requires_confirm": True,
            }
        ],
    }


def refresh_setup_execute_plan(
    setup_entry: dict,
    holes_panel: Optional[List[dict]],
) -> dict:
    """Refresh hole row indices in one setup entry after rescan (Setup2 resume path)."""
    entry = dict(setup_entry or {})
    bindings = list(entry.get("hole_bindings") or [])
    plan = dict(entry.get("execute_plan") or {})
    plan["rows"] = rebuild_execute_rows_from_bindings(holes_panel, bindings)
    entry["execute_plan"] = plan
    entry["feature_summary"] = dict(entry.get("feature_summary") or {})
    entry["feature_summary"]["holes"] = len(plan.get("rows") or [])
    entry["hole_remap_count"] = len(plan.get("rows") or [])
    return entry


def refresh_multi_setup_plan_holes(multi_plan: dict, holes_panel: Optional[List[dict]]) -> dict:
    """Refresh all setup execute plans using stored hole identity bindings."""
    plan = copy.deepcopy(multi_plan or {})
    setups = []
    for entry in plan.get("setups") or []:
        setups.append(refresh_setup_execute_plan(entry, holes_panel))
    plan["setups"] = setups
    return plan


def _plan_persist_path(plan_id: str, document_key: Optional[str] = None) -> str:
    doc_key = str(document_key or _document_storage_key() or "unknown_doc")
    safe_pid = re.sub(r"[^\w\-]+", "_", str(plan_id or ""))[:64]
    return os.path.join(_L2_PLANS_DIR, "{}__{}.json".format(doc_key, safe_pid))


def persist_multi_setup_plan(plan: dict) -> str:
    pid = str(plan.get("plan_id") or uuid.uuid4())
    plan = dict(plan)
    plan["plan_id"] = pid
    try:
        os.makedirs(_L2_PLANS_DIR, exist_ok=True)
        path = _plan_persist_path(pid, plan.get("document_key"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2)
        plan["persist_path"] = path
    except Exception:
        pass
    return pid


def load_persisted_multi_setup_plan(plan_id: str, document_key: Optional[str] = None) -> Optional[dict]:
    pid = str(plan_id or "").strip()
    if not pid:
        return None
    path = _plan_persist_path(pid, document_key)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def cache_multi_setup_plan(plan: dict) -> str:
    pid = persist_multi_setup_plan(plan)
    plan = dict(plan)
    plan["plan_id"] = pid
    runtime_state.l2_pending_multi_setup_plan = plan
    runtime_state.last_l2_multi_setup_plan = plan
    return pid


def get_cached_multi_setup_plan(plan_id: Optional[str] = None) -> Optional[dict]:
    pending = getattr(runtime_state, "l2_pending_multi_setup_plan", None)
    if not isinstance(pending, dict):
        pending = getattr(runtime_state, "last_l2_multi_setup_plan", None)
    if isinstance(pending, dict):
        if not plan_id or str(pending.get("plan_id")) == str(plan_id):
            return pending
    if plan_id:
        disk = load_persisted_multi_setup_plan(plan_id)
        if isinstance(disk, dict):
            runtime_state.last_l2_multi_setup_plan = disk
            if getattr(runtime_state, "l2_pending_multi_setup_plan", None) is None:
                runtime_state.l2_pending_multi_setup_plan = disk
            return disk
        last = getattr(runtime_state, "last_l2_multi_setup_plan", None)
        if isinstance(last, dict) and str(last.get("plan_id")) == str(plan_id):
            return last
    return None


def clear_pending_multi_setup_plan() -> None:
    runtime_state.l2_pending_multi_setup_plan = None


def setup_entry_by_sequence(plan: dict, sequence: int) -> Optional[dict]:
    for entry in plan.get("setups") or []:
        if int(entry.get("sequence", 0) or 0) == int(sequence):
            return entry
    return None


def format_l2_report(multi_plan: dict, *, executed_sequences: Optional[List[int]] = None) -> str:
    executed_sequences = executed_sequences or []
    lines = ["[L2 multi-Setup]", "plan_id: {}".format(multi_plan.get("plan_id", "")), ""]
    for entry in multi_plan.get("setups") or []:
        seq = int(entry.get("sequence", 0) or 0)
        mark = "done" if seq in executed_sequences else "pending"
        fs = entry.get("feature_summary") or {}
        wcs = entry.get("wcs_action", "")
        lines.append(
            "{} Setup{} {} holes={} wcs={}".format(
                mark, seq, entry.get("setup_name", ""), fs.get("holes", 0), wcs
            )
        )
    for cp in multi_plan.get("checkpoints") or []:
        lines.append("checkpoint: {}".format(cp.get("message", "")))
    return "\n".join(lines)
