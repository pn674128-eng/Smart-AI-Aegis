# -*- coding: utf-8 -*-
"""
Apply CAM height / feed tuning after template instantiation (face + profile).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _set_expr(ps, name: str, expr: str) -> bool:
    p = ps.itemByName(name)
    if not p:
        return False
    try:
        p.expression = expr
        return True
    except Exception:
        return False


def apply_height_spec(op, spec: Optional[dict]) -> List[str]:
    if not spec or not op:
        return []
    applied: List[str] = []
    ps = op.parameters

    th_mode = spec.get("topHeight_mode")
    if th_mode:
        if _set_expr(ps, "topHeight_mode", "'{}'".format(th_mode)):
            applied.append("topHeight_mode")
    if "topHeight_offset_mm" in spec:
        if _set_expr(ps, "topHeight_offset", "{}mm".format(spec["topHeight_offset_mm"])):
            applied.append("topHeight_offset")

    bh_mode = spec.get("bottomHeight_mode")
    if bh_mode:
        if _set_expr(ps, "bottomHeight_mode", "'{}'".format(bh_mode)):
            applied.append("bottomHeight_mode")
    if "bottomHeight_offset_mm" in spec:
        off = spec["bottomHeight_offset_mm"]
        expr = "{}mm".format(off)
        if float(off) < 0:
            expr = "({})mm".format(off)
        if _set_expr(ps, "bottomHeight_offset", expr):
            applied.append("bottomHeight_offset")

    max_sd = spec.get("maximum_stepdown_mm")
    if max_sd is not None and float(max_sd) > 0:
        if _set_expr(ps, "doMultipleDepths", "true"):
            applied.append("doMultipleDepths")
        if _set_expr(ps, "maximumStepdown", "{}mm".format(max_sd)):
            applied.append("maximumStepdown")

    vstl = spec.get("vertical_stock_to_leave_mm")
    if vstl is not None:
        if _set_expr(ps, "useStockToLeave", "true" if float(vstl) > 0 else "false"):
            applied.append("useStockToLeave")
        if float(vstl) >= 0 and _set_expr(ps, "verticalStockToLeave", "{}mm".format(vstl)):
            applied.append("verticalStockToLeave")
    return applied


def apply_spindle_feed(op, *, rpm: Optional[float] = None, feed: Optional[float] = None) -> List[str]:
    if not op:
        return []
    applied: List[str] = []
    ps = op.parameters
    if rpm is not None and float(rpm) > 0:
        if _set_expr(ps, "tool_spindleSpeed", str(float(rpm))):
            applied.append("tool_spindleSpeed")
    if feed is not None and float(feed) > 0:
        if _set_expr(ps, "tool_feedCutting", str(float(feed))):
            applied.append("tool_feedCutting")
    return applied


def apply_face_milling_plan(
    op,
    face_depth: Optional[dict],
    tuning: Optional[dict] = None,
) -> List[str]:
    applied = apply_height_spec(op, face_depth)
    if tuning:
        applied.extend(
            apply_spindle_feed(
                op,
                rpm=tuning.get("rpm"),
                feed=tuning.get("feed"),
            )
        )
    return applied


def apply_profile_milling_plan(
    op,
    profile_depth: Optional[dict],
    tuning: Optional[dict] = None,
) -> List[str]:
    applied = apply_height_spec(op, profile_depth)
    if tuning:
        applied.extend(
            apply_spindle_feed(
                op,
                rpm=tuning.get("rpm"),
                feed=tuning.get("feed"),
            )
        )
    return applied


def tuning_for_title(cam_depth_context: Optional[dict], title: str) -> Optional[dict]:
    ctx = cam_depth_context or {}
    tuning_root = ctx.get("tuning") or {}
    if "顶面" in str(title):
        return tuning_root.get("top_face")
    if "外輪廓" in str(title) or "轮廓" in str(title):
        return tuning_root.get("outer_contour")
    return None


def depth_spec_for_2d_apply(
    cam_depth_context: Optional[dict],
    title: str,
    *,
    terrace_spec: Optional[dict] = None,
) -> Optional[dict]:
    if terrace_spec and isinstance(terrace_spec.get("face_depth"), dict):
        return terrace_spec["face_depth"]
    ctx = cam_depth_context or {}
    t = str(title)
    if "顶面" in t:
        if "粗" in t:
            return ctx.get("top_face_rough")
        return ctx.get("top_face_finish")
    if "外輪廓" in t or "轮廓" in t:
        if "粗" in t:
            return ctx.get("profile_rough")
        return ctx.get("profile_finish")
    return None
