# -*- coding: utf-8 -*-
"""
2D contour (top face / outer profile) feature recognition → template recommendations.

Read-only geometry aggregation; does not execute CAM or alter hole baseline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from smart_ai_cam_state.runtime_state import state as runtime_state


def _pick_template_name(
    names: Sequence[str],
    *,
    keyword: str = "",
    fallback_keyword: str = "",
    unused_label: str = "(不使用)",
) -> str:
    items = [str(n) for n in (names or []) if n]
    if not items:
        return unused_label
    if keyword:
        for n in items:
            if keyword in n:
                return n
    if fallback_keyword:
        for n in items:
            if fallback_keyword in n:
                return n
    return items[0]


def _largest_top_plane(flat_depths: Optional[dict]) -> Optional[dict]:
    planes = (flat_depths or {}).get("planes") or []
    if not planes:
        return None
    top_z = max(float(p.get("z_height_mm", 0) or 0) for p in planes)
    top_tier = [
        p for p in planes
        if abs(float(p.get("z_height_mm", 0) or 0) - top_z) <= 0.15
    ]
    return max(top_tier or planes, key=lambda p: float(p.get("area_mm2", 0) or 0))


def _outer_contour_metrics(
    vision_snapshot: Optional[dict],
    feature_catalog: Optional[dict],
    flat_depths: Optional[dict],
) -> dict:
    contour_count = 0
    perimeter_mm = None
    edge_count = 0

    if vision_snapshot and vision_snapshot.get("ok"):
        feats = vision_snapshot.get("recognized_features") or {}
        contours = feats.get("contours") or []
        contour_count = len(contours)
        profiles = vision_snapshot.get("profiles") or {}
        topview = profiles.get("topview_semantic") or {}
        outer = topview.get("outer_chain") or {}
        if outer.get("exists"):
            try:
                perimeter_mm = float(outer.get("perimeter_mm", 0) or 0)
            except Exception:
                perimeter_mm = None
        for c in contours:
            if isinstance(c, dict):
                edge_count += int(c.get("edge_count", 0) or 0)

    if feature_catalog and int(feature_catalog.get("feature_count", 0) or 0) > 0:
        cat_n = int((feature_catalog.get("counts_by_category") or {}).get("outer_contour", 0) or 0)
        contour_count = max(contour_count, cat_n)

    z_span = float((flat_depths or {}).get("z_span_mm", 0) or 0)
    return {
        "contour_count": contour_count,
        "perimeter_mm": perimeter_mm,
        "edge_count": edge_count,
        "z_span_mm": round(z_span, 3),
    }


def build_contour_2d_recognition(
    *,
    flat_depths: Optional[dict] = None,
    vision_snapshot: Optional[dict] = None,
    feature_catalog: Optional[dict] = None,
    top_face_rough_names: Optional[List[str]] = None,
    top_face_finish_names: Optional[List[str]] = None,
    profile_rough_names: Optional[List[str]] = None,
    profile_finish_names: Optional[List[str]] = None,
    material: str = "AL6061",
    setup_name: str = "",
) -> dict:
    """
    Recognize machinable 2D features and map to panel template names (rough/finish pairs).
    """
    fd = flat_depths or {}
    planes = fd.get("planes") or []
    top_plane = _largest_top_plane(fd)
    oc = _outer_contour_metrics(vision_snapshot, feature_catalog, fd)

    has_top_face = len(planes) > 0 and top_plane is not None
    has_outer_contour = (
        oc.get("contour_count", 0) > 0
        or (oc.get("perimeter_mm") or 0) > 1.0
        or float(oc.get("z_span_mm", 0) or 0) > 0.5
    )

    tf_rough = list(top_face_rough_names or [])
    tf_finish = list(top_face_finish_names or [])
    pf_rough = list(profile_rough_names or [])
    pf_finish = list(profile_finish_names or [])

    rec_templates = {
        "topFaceRough": "(不使用)",
        "topFaceFinish": "(不使用)",
        "profileRough": "(不使用)",
        "profileFinish": "(不使用)",
    }
    reasons = []

    try:
        from . import feature_apply as fap

        terrace = fap.build_terrace_2d_templates(flat_depths, tf_rough, tf_finish)
        if terrace.get("strategy") in ("multi_terrace", "single_terrace"):
            rec_templates["topFaceRough"] = terrace.get("topFaceRough", "(不使用)")
            rec_templates["topFaceFinish"] = terrace.get("topFaceFinish", "(不使用)")
            reasons.append(
                "面銑策略：{}（台面 {} 層）。".format(
                    terrace.get("strategy"),
                    terrace.get("terrace_count", len(planes)),
                )
            )
    except Exception:
        pass

    if has_top_face and rec_templates.get("topFaceRough") == "(不使用)":
        rec_templates["topFaceRough"] = _pick_template_name(tf_rough, keyword="粗")
        rec_templates["topFaceFinish"] = _pick_template_name(tf_finish, keyword="精")
        area = float(top_plane.get("area_mm2", 0) or 0)
        depth_z0 = float(
            top_plane.get("depth_from_z0_mm", top_plane.get("z_height_mm", 0) or 0) or 0
        )
        if "depth_from_z0_mm" not in top_plane:
            depth_z0 = round(-depth_z0, 3)
        reasons.append(
            "頂面：辨識到 {} 個朝上平面，主台面距 Z0 {:.2f} mm、面積 {:.0f} mm² → 面銑粗/精。".format(
                len(planes), max(0.0, depth_z0), area
            )
        )
    else:
        reasons.append("頂面：未辨識到朝上水平平面，面銑維持「不使用」。")

    if has_outer_contour:
        rec_templates["profileRough"] = _pick_template_name(pf_rough, keyword="粗")
        rec_templates["profileFinish"] = _pick_template_name(pf_finish, keyword="精")
        perim = oc.get("perimeter_mm")
        perim_txt = "{:.1f} mm".format(perim) if perim is not None else "—"
        reasons.append(
            "外輪廓：輪廓列 {}、周長 {}、Z 落差 {:.2f} mm → 外輪廓粗/精。".format(
                oc.get("contour_count", 0),
                perim_txt,
                float(oc.get("z_span_mm", 0) or 0),
            )
        )
    else:
        reasons.append("外輪廓：特徵不足，外輪廓維持「不使用」。")

    return {
        "version": "1.0",
        "material": material,
        "setup_name": setup_name,
        "recognized": {
            "top_face": has_top_face,
            "outer_contour": has_outer_contour,
        },
        "top_face": {
            "plane_count": len(planes),
            "primary_z_mm": (
                max(0.0, float(top_plane.get("depth_from_z0_mm", 0) or 0))
                if top_plane
                else None
            ),
            "primary_depth_from_z0_mm": (
                max(0.0, float(top_plane.get("depth_from_z0_mm", 0) or 0))
                if top_plane
                else None
            ),
            "z0_to_part_bottom_mm": float(fd.get("z0_to_part_bottom_mm", 0) or 0),
            "job_stock_fixed_z_offset_mm": float(
                fd.get("job_stock_fixed_z_offset_mm", fd.get("stock_to_part_top_mm", 0)) or 0
            ),
            "stock_to_part_top_mm": float(fd.get("stock_to_part_top_mm", 0) or 0),
            "part_thickness_mm": float(fd.get("part_thickness_mm", fd.get("z_span_mm", 0)) or 0),
            "stock_remaining_thickness_mm": (
                float(fd["stock_remaining_thickness_mm"])
                if fd.get("stock_remaining_thickness_mm") is not None
                else None
            ),
            "primary_area_mm2": float(top_plane.get("area_mm2", 0) or 0) if top_plane else None,
            "top_face_stock_remove_volume_mm3": (
                round(
                    float(top_plane.get("area_mm2", 0) or 0)
                    * float(
                        fd.get("job_stock_fixed_z_offset_mm", fd.get("stock_to_part_top_mm", 0))
                        or 0
                    ),
                    1,
                )
                if top_plane
                and float(top_plane.get("area_mm2", 0) or 0) > 0
                and float(
                    fd.get("job_stock_fixed_z_offset_mm", fd.get("stock_to_part_top_mm", 0)) or 0
                )
                > 0.001
                else None
            ),
            "z_span_mm": float(fd.get("z_span_mm", 0) or 0),
        },
        "outer_contour": oc,
        "recommended_templates": rec_templates,
        "cam_operations": {
            "top_face": "face" if has_top_face else "",
            "outer_contour": "contour2d" if has_outer_contour else "",
        },
        "summary_lines": reasons,
        "summary_text": "\n".join(reasons),
    }


def run_recognize_contour_2d_flow(
    material: str,
    ctx: dict,
    *,
    rescan_holes: bool = False,
) -> dict:
    """
    Refresh vision → catalog → contour_2d, merge chamfer_bevel → contourChamfer template.
    Shared by MCP recognize_contour_2d and panel「特徵辨識並帶入工序」.
    """
    mat = str(material or "AL6061").upper()
    if rescan_holes:
        rebuild = ctx.get("rebuild_holes")
        if callable(rebuild):
            try:
                rebuild(force=True)
            except Exception:
                pass
    for key in ("refresh_vision", "refresh_feature_catalog", "refresh_contour_2d"):
        fn = ctx.get(key)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    c2d = getattr(runtime_state, "contour_2d_recognition", None) or {}
    rec = dict(c2d.get("recommended_templates") or {})
    feat_cat = getattr(runtime_state, "feature_catalog", None)
    chamfer_n = int((feat_cat or {}).get("counts_by_category", {}).get("chamfer_bevel", 0) or 0)
    chamfer_fn = ctx.get("contour_chamfer_names")
    chamfer_names = chamfer_fn(mat) if callable(chamfer_fn) else []

    try:
        from . import feature_apply as fap

        rec = fap.merge_contour_chamfer_template(
            rec,
            chamfer_bevel_count=chamfer_n,
            contour_chamfer_names=chamfer_names,
        )
    except Exception:
        pass

    summary = recognition_summary_for_init(c2d if isinstance(c2d, dict) else None)
    if rec:
        summary["recommended_templates"] = dict(rec)

    feat_summary = {}
    try:
        from .machining_feature_catalog import catalog_summary_for_init

        feat_summary = catalog_summary_for_init(feat_cat)
    except Exception:
        pass

    return {
        "material": mat,
        "contour_2d_recognition": c2d,
        "contour2dRecognition": summary,
        "recommended_templates": rec,
        "feature_catalog_summary": feat_summary,
        "chamfer_bevel_count": chamfer_n,
    }


def recognition_summary_for_init(recognition: Optional[dict]) -> dict:
    if not recognition or not isinstance(recognition, dict):
        return {"ok": False}
    rec = recognition.get("recognized") or {}
    tf = recognition.get("top_face") or {}
    oc = recognition.get("outer_contour") or {}
    return {
        "ok": True,
        "top_face": bool(rec.get("top_face")),
        "outer_contour": bool(rec.get("outer_contour")),
        "plane_count": int(tf.get("plane_count", 0) or 0),
        "primary_z_mm": tf.get("primary_z_mm"),
        "primary_depth_from_z0_mm": tf.get("primary_depth_from_z0_mm"),
        "primary_area_mm2": tf.get("primary_area_mm2"),
        "top_face_stock_remove_volume_mm3": tf.get("top_face_stock_remove_volume_mm3"),
        "job_stock_fixed_z_offset_mm": tf.get("job_stock_fixed_z_offset_mm"),
        "stock_to_part_top_mm": tf.get("stock_to_part_top_mm"),
        "part_thickness_mm": tf.get("part_thickness_mm"),
        "stock_remaining_thickness_mm": tf.get("stock_remaining_thickness_mm"),
        "contour_count": int(oc.get("contour_count", 0) or 0),
        "perimeter_mm": oc.get("perimeter_mm"),
        "z_span_mm": oc.get("z_span_mm"),
        "recommended_templates": dict(recognition.get("recommended_templates") or {}),
        "summary_text": str(recognition.get("summary_text", "") or ""),
    }
