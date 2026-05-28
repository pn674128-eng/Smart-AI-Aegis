# -*- coding: utf-8 -*-
"""
CAM depth / height plan from Setup WCS flat_depths (Phase 1 face + profile).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _f(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def stock_remove_mm(flat_depths: Optional[dict]) -> float:
    fd = flat_depths or {}
    v = fd.get("job_stock_fixed_z_offset_mm")
    if v is None:
        v = fd.get("stock_to_part_top_mm")
    return max(0.0, _f(v, 0.0))


def part_thickness_mm(flat_depths: Optional[dict]) -> float:
    fd = flat_depths or {}
    t = fd.get("part_thickness_mm")
    if t is None:
        t = fd.get("z_span_mm")
    if t is None:
        t = fd.get("z0_to_part_bottom_mm")
    return max(0.0, _f(t, 0.0))


def top_face_rough_depth_spec(flat_depths: Optional[dict]) -> dict:
    """除顶面坯料：stock top -> part top (Setup WCS semantics)."""
    remove = stock_remove_mm(flat_depths)
    step = min(max(remove, 0.1), 2.0) if remove > 0 else 0.5
    return {
        "topHeight_mode": "from stock top",
        "topHeight_offset_mm": 0.0,
        "bottomHeight_mode": "from surface top",
        "bottomHeight_offset_mm": 0.0,
        "maximum_stepdown_mm": step,
        "vertical_stock_to_leave_mm": 0.1 if remove > 0 else 0.0,
        "stock_remove_mm": remove,
    }


def top_face_finish_depth_spec(flat_depths: Optional[dict]) -> dict:
    return {
        "topHeight_mode": "from surface top",
        "topHeight_offset_mm": 0.0,
        "bottomHeight_mode": "from surface top",
        "bottomHeight_offset_mm": 0.0,
        "maximum_stepdown_mm": 0.2,
        "vertical_stock_to_leave_mm": 0.0,
        "stock_remove_mm": 0.0,
    }


def profile_depth_spec(flat_depths: Optional[dict], *, op_kind: str = "rough") -> dict:
    depth = part_thickness_mm(flat_depths)
    vstl = 0.2 if op_kind == "rough" else 0.0
    return {
        "topHeight_mode": "from surface top",
        "topHeight_offset_mm": 0.0,
        "bottomHeight_mode": "from surface bottom",
        "bottomHeight_offset_mm": -vstl,
        "profile_depth_mm": depth,
        "vertical_stock_to_leave_mm": vstl,
    }


def face_depth_for_terrace(
    flat_depths: Optional[dict],
    z_height_mm: Optional[float],
    op_kind: str,
) -> dict:
    fd = flat_depths or {}
    planes = list(fd.get("planes") or [])
    top_z = max((_f(p.get("z_height_mm"), 0.0) for p in planes), default=0.0)
    z_h = _f(z_height_mm, top_z)
    rel = max(0.0, top_z - z_h)
    kind = str(op_kind or "finish").lower()

    if kind == "rough":
        spec = top_face_rough_depth_spec(fd)
        spec["terrace_z_height_mm"] = z_h
        spec["terrace_relative_depth_mm"] = rel
        return spec

    spec = top_face_finish_depth_spec(fd)
    spec["terrace_z_height_mm"] = z_h
    spec["terrace_relative_depth_mm"] = rel
    if rel > 0.001:
        spec["bottomHeight_offset_mm"] = -rel
    return spec


def enrich_terrace_face_ops(
    terrace_ops: Optional[List[dict]],
    flat_depths: Optional[dict],
) -> List[dict]:
    out: List[dict] = []
    for spec in terrace_ops or []:
        if not isinstance(spec, dict):
            continue
        row = dict(spec)
        row["face_depth"] = face_depth_for_terrace(
            flat_depths,
            row.get("z_height_mm"),
            str(row.get("op_kind", "finish") or "finish"),
        )
        out.append(row)
    return out


def build_cam_depth_context(
    flat_depths: Optional[dict],
    *,
    ai_decisions: Optional[dict] = None,
) -> dict:
    fd = flat_depths or {}
    decisions = ai_decisions or {}
    tf = decisions.get("top_face") or {}
    oc = decisions.get("outer_contour") or {}
    remove = stock_remove_mm(fd)
    thickness = part_thickness_mm(fd)
    planes = list(fd.get("planes") or [])

    ctx = {
        "version": "1.0",
        "z_reference": fd.get("z_reference", "setup_wcs_z0"),
        "stock_remove_mm": remove,
        "part_thickness_mm": thickness,
        "z0_to_part_bottom_mm": _f(fd.get("z0_to_part_bottom_mm"), 0.0),
        "plane_count": len(planes),
        "top_face_rough": top_face_rough_depth_spec(fd),
        "top_face_finish": top_face_finish_depth_spec(fd),
        "profile_rough": profile_depth_spec(fd, op_kind="rough"),
        "profile_finish": profile_depth_spec(fd, op_kind="finish"),
        "tuning": {
            "top_face": {
                "rpm": tf.get("rpm"),
                "feed": tf.get("feed"),
            },
            "outer_contour": {
                "rpm": oc.get("rpm"),
                "feed": oc.get("feed"),
            },
        },
    }
    if remove > 0 and planes:
        top_area = max((_f(p.get("area_mm2"), 0.0) for p in planes), default=0.0)
        ctx["top_face_stock_remove_volume_mm3"] = round(top_area * remove, 3)
    return ctx


def attach_cam_depth_to_execute_plan(plan: dict, flat_depths: Optional[dict] = None) -> dict:
    """Merge cam depth context into palette execute payload."""
    out = dict(plan or {})
    fd = flat_depths
    if fd is None:
        fd = out.get("flat_depths")
    existing = out.get("camDepthContext") or out.get("cam_depth_context")
    if isinstance(existing, dict) and existing.get("top_face_rough"):
        ctx = dict(existing)
    else:
        tuning_src = existing if isinstance(existing, dict) else {}
        decisions = tuning_src.get("decisions") or out.get("ai_decisions") or {}
        ctx = build_cam_depth_context(fd, ai_decisions=decisions)

    terrace = list(out.get("terraceFaceOps") or out.get("terrace_face_ops") or [])
    if terrace:
        out["terraceFaceOps"] = enrich_terrace_face_ops(terrace, fd)
    out["camDepthContext"] = ctx
    out["flat_depths"] = fd
    out["topFaceRoughDepthMm"] = ctx.get("stock_remove_mm")
    return out
