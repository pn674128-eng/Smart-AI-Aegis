# -*- coding: utf-8 -*-
"""
Brain layer: merge Law (scan rows) + Eye (vision_snapshot) into AI decision inputs.

Does not change hole baseline or execute semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _vision_summary_block(snapshot: Optional[dict]) -> dict:
    if not snapshot or not isinstance(snapshot, dict) or not snapshot.get("ok"):
        return {
            "enabled": False,
            "ok": False,
            "reason": str((snapshot or {}).get("reason", "no_snapshot")),
        }
    feats = snapshot.get("recognized_features") or {}
    profiles = snapshot.get("profiles") or {}
    topview = profiles.get("topview_semantic") or {}
    outer = topview.get("outer_chain") or {}
    mb = snapshot.get("machining_basis") or {}
    contours = feats.get("contours") or []
    return {
        "enabled": True,
        "ok": True,
        "vision_mode": str(snapshot.get("vision_mode", "FAST_2D")),
        "setup_name": str(mb.get("setup_name", "")),
        "contour_face_rows": len(contours),
        "outer_perimeter_mm": float(outer.get("perimeter_mm", 0.0)) if outer.get("exists") else None,
        "hole_instances": len(feats.get("hole_instances") or []),
        "slots_total": len(feats.get("slots") or []),
        "slots_active": sum(
            1 for s in (feats.get("slots") or []) if isinstance(s, dict) and s.get("active_for_machining")
        ),
    }


def _slots_for_ai(slots_panel: List[dict], vision_snapshot: Optional[dict]) -> List[dict]:
    """Prefer panel slot rows; enrich with vision snapshot loop_edges flag."""
    out: List[dict] = []
    vision_slots = []
    if vision_snapshot and vision_snapshot.get("ok"):
        vision_slots = (vision_snapshot.get("recognized_features") or {}).get("slots") or []

    for idx, s in enumerate(slots_panel or []):
        if not isinstance(s, dict):
            continue
        row = {
            "idx": idx,
            "width_mm": float(s.get("width_mm", s.get("width", 0.0)) or 0.0),
            "length_mm": float(s.get("length_mm", s.get("length", 0.0)) or 0.0),
            "depth_mm": float(s.get("depth_mm", s.get("depth", 0.0)) or 0.0),
            "through": bool(s.get("through", False)),
            "active": bool(s.get("active", s.get("active_for_machining", True))),
            "has_loop_edges": bool(s.get("loop_edges")),
            "angle_deg": float(s.get("angle_deg", 0.0) or 0.0),
        }
        if idx < len(vision_slots) and isinstance(vision_slots[idx], dict):
            vs = vision_slots[idx]
            row["has_loop_edges"] = row["has_loop_edges"] or bool(vs.get("loop_edges"))
            if not row["width_mm"]:
                row["width_mm"] = float(vs.get("width_mm", 0.0) or 0.0)
        out.append(row)
    return out


def build_geom_features_for_ai(
    *,
    holes_data: List[dict],
    slots_data: List[dict],
    pocket_corner_r_data: Optional[List[dict]] = None,
    flat_depths: Optional[dict] = None,
    vision_snapshot: Optional[dict] = None,
    feature_catalog: Optional[dict] = None,
    design=None,
    setup=None,
    build_catalog_if_missing: bool = True,
) -> dict:
    """
    Unified geometry feature dict for AIDecisionEngine.make_machining_plan.
    """
    catalog = feature_catalog
    if catalog is None and build_catalog_if_missing:
        try:
            from . import machining_feature_catalog as mfc

            catalog = mfc.build_feature_catalog(
                design=design,
                setup=setup,
                holes=holes_data,
                slots=slots_data,
                pocket_corner_r=pocket_corner_r_data,
                flat_depths=flat_depths,
                vision_snapshot=vision_snapshot,
            )
        except Exception:
            catalog = None

    try:
        from smart_ai_cam_state.runtime_state import state as runtime_state
        deps = list(getattr(runtime_state, "machining_dependencies", []) or [])
    except Exception:
        deps = []

    geom = {
        "holes": list(holes_data or []),
        "slots": _slots_for_ai(slots_data, vision_snapshot),
        "pocket_corner_r": list(pocket_corner_r_data or []),
        "flat_depths": dict(flat_depths or {}),
        "vision": _vision_summary_block(vision_snapshot),
        "feature_catalog": catalog,
        "machining_dependencies": deps,
    }
    if vision_snapshot and vision_snapshot.get("ok"):
        feats = vision_snapshot.get("recognized_features") or {}
        geom["vision_contours"] = feats.get("contours") or []
        geom["vision_hole_instances"] = feats.get("hole_instances") or []
    return geom
