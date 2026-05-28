# -*- coding: utf-8 -*-
"""
Semantic feature → panel template apply (supplements Fusion official hints).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .ai_panel_apply import find_tmpl_idx_by_keywords


def _chamfer_bucket_pref() -> str:
    """Default when UI prefs unavailable server-side."""
    return "C0.2"


def apply_hole_row_with_hints(
    h: dict,
    items: List[dict],
    *,
    fusion_hint: Optional[dict] = None,
    ai_h: Optional[dict] = None,
) -> tuple:
    fusion_hint = fusion_hint or {}
    ai_h = ai_h or {}
    reason = ""
    tmpl_idx = -1

    prefer_tap = bool(fusion_hint.get("prefer_tap")) or bool(ai_h.get("is_threaded"))
    prefer_ream = bool(ai_h.get("semantic_type") == "pin_position_hole")
    prefer_cs = bool(h.get("isCBLarge")) or bool(fusion_hint.get("prefer_countersink")) or bool(
        fusion_hint.get("official_is_counterbore")
    )
    prefer_combo = bool(fusion_hint.get("prefer_drill_chamfer_combo"))

    if prefer_cs:
        tmpl_idx = find_tmpl_idx_by_keywords(
            items,
            include_keywords=("沉", "counter", "countersink", "埋頭"),
            prefer_has_drill=True,
        )
        reason = "Fusion/沉頭：沉頭或 counterbore 類孔"
    elif prefer_tap:
        tmpl_idx = find_tmpl_idx_by_keywords(
            items,
            include_keywords=("攻牙", "tap", "螺紋", "齒", "thread"),
        )
        if ai_h.get("semantic_type") == "thread_bottom_hole":
            reason = f"幾何自適應反推：螺紋底孔 {h.get('dia', h.get('diameter_mm', ''))}mm → 攻牙模板"
        else:
            reason = "Fusion 螺紋/攻牙孔"
    elif prefer_ream:
        tmpl_idx = find_tmpl_idx_by_keywords(
            items,
            include_keywords=("鉸", "ream", "locating", "銷"),
            prefer_has_drill=True,
        )
        reason = f"幾何自適應反推：定位銷孔 {h.get('dia', h.get('diameter_mm', ''))}mm → 鉸孔/銷孔模板"

    elif prefer_combo:
        bucket = _chamfer_bucket_pref()
        tmpl_idx = find_tmpl_idx_by_keywords(
            items,
            include_keywords=(bucket.lower(), "倒角"),
            prefer_has_drill=True,
            prefer_has_chamfer=True,
        )
        if tmpl_idx < 0:
            tmpl_idx = find_tmpl_idx_by_keywords(
                items, prefer_has_drill=True, prefer_has_chamfer=True
            )
        reason = "Fusion 孔頂倒角段 + 鑽孔"
    else:
        kind = str(fusion_hint.get("official_hole_kind", "") or "")
        if kind == "simple":
            tmpl_idx = find_tmpl_idx_by_keywords(
                items,
                include_keywords=("鑽", "drill"),
                exclude_keywords=("攻牙", "tap"),
                prefer_has_drill=True,
            )
            reason = "Fusion 簡單圓柱孔"
        else:
            tmpl_idx = find_tmpl_idx_by_keywords(
                items,
                include_keywords=("鑽", "drill"),
                exclude_keywords=("攻牙", "tap", "螺紋"),
                prefer_has_drill=True,
            )
            reason = "語意：一般鑽孔" if not kind else "Fusion {}".format(kind)

    if tmpl_idx < 0:
        tmpl_idx = 0
        reason += "；未匹配，用首項"
    return tmpl_idx, reason


def apply_slot_row_with_chamfer(
    items: List[dict],
    *,
    chamfer_bucket: str = "C0.2",
    rec_dia: Optional[float] = None,
) -> tuple:
    bucket = (chamfer_bucket or "C0.2").upper()
    tmpl_idx = find_tmpl_idx_by_keywords(
        items,
        include_keywords=(bucket, "C0.2", "C0.3", "倒角"),
        prefer_has_slot=True,
        prefer_has_chamfer=True,
        target_tool_dia_mm=rec_dia,
    )
    if tmpl_idx < 0:
        tmpl_idx = find_tmpl_idx_by_keywords(
            items,
            include_keywords=("槽", "slot"),
            prefer_has_slot=True,
            target_tool_dia_mm=rec_dia,
        )
    return max(0, tmpl_idx), "槽：優先 {} 倒角組合模板".format(bucket)


def pick_contour_chamfer_template_name(
    contour_chamfer_names: Optional[List[str]],
    *,
    chamfer_bucket: str = "C0.2",
    unused_label: str = "(不使用)",
) -> str:
    """Pick contourChamfer template from configured folder names (C0.2/C0.3 bucket)."""
    names = [str(n) for n in (contour_chamfer_names or []) if n]
    if not names:
        return unused_label
    bucket = (chamfer_bucket or "C0.2").upper()
    for alt in (bucket, "C0.2", "C0.3"):
        for name in names:
            if alt in name.upper():
                return name
    for name in names:
        low = name.lower()
        if "倒角" in name or "chamfer" in low:
            return name
    return names[0]


def merge_contour_chamfer_template(
    rec_templates: dict,
    *,
    chamfer_bevel_count: int = 0,
    contour_chamfer_names: Optional[List[str]] = None,
    chamfer_bucket: str = "C0.2",
) -> dict:
    """Map chamfer_bevel catalog count → contourChamfer template name (§8 contourChamfer key)."""
    out = dict(rec_templates or {})
    if chamfer_bevel_count <= 0 or not contour_chamfer_names:
        return out
    cc = pick_contour_chamfer_template_name(
        contour_chamfer_names, chamfer_bucket=chamfer_bucket
    )
    if cc and cc != "(不使用)":
        out["contourChamfer"] = cc
    return out


def build_terrace_2d_templates(
    flat_depths: Optional[dict],
    top_face_rough_names: List[str],
    top_face_finish_names: List[str],
) -> dict:
    """
    Multi-terrace: rough only highest terrace; finish on terraces above area threshold.
    """
    from Smart_AI.perception.contour_2d_recognizer import _pick_template_name

    fd = flat_depths or {}
    planes = list(fd.get("planes") or [])
    rec = {
        "topFaceRough": "(不使用)",
        "topFaceFinish": "(不使用)",
        "terrace_count": len(planes),
        "strategy": "none",
    }
    if not planes:
        return rec

    planes_sorted = sorted(
        planes, key=lambda p: float(p.get("z_height_mm", 0) or 0), reverse=True
    )
    top = planes_sorted[0]
    top_area = float(top.get("area_mm2", 0) or 0)
    significant = [p for p in planes_sorted if float(p.get("area_mm2", 0) or 0) >= top_area * 0.15]

    if len(planes_sorted) >= 2:
        rec["strategy"] = "multi_terrace"
        rough_name = _pick_template_name(top_face_rough_names, keyword="粗")
        finish_name = _pick_template_name(top_face_finish_names, keyword="精")
        rec["topFaceRough"] = rough_name
        rec["topFaceFinish"] = finish_name
        rec["terrace_planes"] = [
            {
                "z_height_mm": p.get("z_height_mm"),
                "area_mm2": p.get("area_mm2"),
                "relative_depth_mm": p.get("relative_depth_mm"),
            }
            for p in significant
        ]
        terrace_face_ops: List[dict] = []
        for ti, p in enumerate(significant):
            z_h = float(p.get("z_height_mm", 0) or 0)
            base = {
                "z_height_mm": z_h,
                "area_mm2": float(p.get("area_mm2", 0) or 0),
                "relative_depth_mm": p.get("relative_depth_mm"),
            }
            if ti == 0 and rough_name and rough_name != "(不使用)":
                terrace_face_ops.append(
                    dict(base, op_kind="rough", template_name=rough_name)
                )
            if finish_name and finish_name != "(不使用)":
                terrace_face_ops.append(
                    dict(base, op_kind="finish", template_name=finish_name)
                )
        rec["terrace_face_ops"] = terrace_face_ops
    else:
        rec["strategy"] = "single_terrace"
        rec["topFaceRough"] = _pick_template_name(top_face_rough_names, keyword="粗")
        rec["topFaceFinish"] = _pick_template_name(top_face_finish_names, keyword="精")
        rec["terrace_face_ops"] = []
    return rec


def apply_official_pocket_row(
    row: dict,
    drop2d: List[dict],
    drop3d: List[dict],
) -> tuple:
    """Pick 2D/3D template indices + bindMode for Fusion RecognizedPocket row."""
    through = bool(row.get("through"))
    width = row.get("width_mm")
    target_d = None
    if width is not None:
        try:
            target_d = max(1.0, float(width) * 0.4)
        except Exception:
            target_d = None

    tmpl2d = find_tmpl_idx_by_keywords(
        drop2d,
        include_keywords=("槽", "slot", "pocket", "2d"),
        prefer_has_slot=True,
        target_tool_dia_mm=target_d,
    )
    tmpl3d = find_tmpl_idx_by_keywords(
        drop3d,
        include_keywords=("adaptive", "3d", "rough", "粗"),
        prefer_has_slot=True,
        target_tool_dia_mm=target_d,
    )
    if tmpl2d < 0:
        tmpl2d = find_tmpl_idx_by_keywords(drop2d, prefer_has_slot=True)
    if tmpl3d < 0:
        tmpl3d = find_tmpl_idx_by_keywords(drop3d, prefer_has_slot=True)

    ch2 = drop2d[tmpl2d] if 0 <= tmpl2d < len(drop2d) else {}
    ch3 = drop3d[tmpl3d] if 0 <= tmpl3d < len(drop3d) else {}
    has2d = bool(str(ch2.get("slotUrl", "") or "").strip())
    has3d = bool(str(ch3.get("slotUrl", "") or "").strip())

    if through or (has2d and not has3d):
        bind_mode = "2d_only"
        reason = "通孔／長條：2D 邊鏈"
    elif has2d and has3d:
        bind_mode = "2d_then_3d"
        reason = "盲口袋：2D→3D"
    elif has3d:
        bind_mode = "3d_only"
        reason = "僅 3D 模板可用"
    else:
        bind_mode = "auto"
        reason = "官方口袋：自動綁定"

    return max(0, tmpl2d), max(0, tmpl3d), bind_mode, reason
