# -*- coding: utf-8 -*-
"""
Unified machining feature catalog: Design B-rep recognition → CAM operation mapping.

Read-only aggregation; does not replace hole baseline or execute paths.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import adsk.core
import adsk.fusion

CATALOG_VERSION = "1.0"

# category → primary Fusion CAM operation strategy (template-driven in this add-in)
CAM_OPERATION_MAP = {
    "official_pocket": {
        "primary": "pocket2d",
        "alternates": ["adaptive"],
        "template_keys": ["slotHole"],
    },
    "hole": {
        "primary": "drill",
        "alternates": ["ream", "tap", "bore"],
        "template_keys": ["generalHole", "tapHole", "locatingHole", "countersinkHole"],
    },
    "slot": {
        "primary": "pocket2d",
        "alternates": ["adaptive"],
        "template_keys": ["slotHole"],
    },
    "pocket_corner_r": {
        "primary": "drill",
        "alternates": [],
        "template_keys": ["generalHole"],
    },
    "face_plane": {
        "primary": "face",
        "alternates": [],
        "template_keys": ["topFaceRough", "topFaceFinish", "topFaceLegacy"],
    },
    "outer_contour": {
        "primary": "contour2d",
        "alternates": ["pocket2d"],
        "template_keys": ["profileRough", "profileFinish", "profileLegacy"],
    },
    "chamfer_bevel": {
        "primary": "chamfer",
        "alternates": ["contour2d"],
        "template_keys": ["holeChamfer", "contourChamfer"],
    },
    "t_slot": {
        "primary": "pocket2d",
        "alternates": ["contour2d"],
        "template_keys": ["slotHole"],
    },
    "undercut": {
        "primary": "pocket2d",
        "alternates": ["contour2d"],
        "template_keys": ["profileRough"],
    },
}


def _feature(
    feature_id: str,
    category: str,
    *,
    cam_operation: str = "",
    geometry: Optional[dict] = None,
    active: bool = True,
    source: str = "",
) -> dict:
    cat = CAM_OPERATION_MAP.get(category, {})
    return {
        "feature_id": feature_id,
        "category": category,
        "cam_operation": cam_operation or cat.get("primary", ""),
        "cam_operation_alternates": list(cat.get("alternates", [])),
        "template_keys": list(cat.get("template_keys", [])),
        "active": bool(active),
        "source": source,
        "geometry": dict(geometry or {}),
    }


def _holes_to_features(holes: List[dict]) -> List[dict]:
    out = []
    for idx, h in enumerate(holes or []):
        if not isinstance(h, dict):
            continue
        dia = h.get("dia", h.get("diameter", h.get("diameter_mm", 0)))
        out.append(
            _feature(
                "hole_{}".format(idx),
                "hole",
                geometry={
                    "diameter_mm": float(dia or 0),
                    "depth_mm": float(h.get("depth", h.get("depth_mm", 0)) or 0),
                    "through": bool(h.get("through", False)),
                    "direction": str(h.get("dir", "")),
                    "is_counterbore": bool(h.get("isCBLarge", h.get("isCBSmall", False))),
                    "label": str(h.get("label", "")),
                },
                active=bool(h.get("active", True)),
                source="hole_recognizer",
            )
        )
    return out


def _slots_to_features(slots: List[dict]) -> List[dict]:
    out = []
    for idx, s in enumerate(slots or []):
        if not isinstance(s, dict):
            continue
        out.append(
            _feature(
                "slot_{}".format(idx),
                "slot",
                geometry={
                    "width_mm": float(s.get("width_mm", s.get("width", 0)) or 0),
                    "length_mm": float(s.get("length_mm", s.get("length", 0)) or 0),
                    "depth_mm": float(s.get("depth_mm", s.get("depth", 0)) or 0),
                    "through": bool(s.get("through", False)),
                    "angle_deg": float(s.get("angle_deg", 0) or 0),
                    "has_loop_edges": bool(s.get("loop_edges")),
                },
                active=bool(s.get("active", s.get("active_for_machining", False))),
                source="slot_recognizer",
            )
        )
    return out


def _pocket_corner_r_to_features(rows: List[dict]) -> List[dict]:
    out = []
    for idx, r in enumerate(rows or []):
        if not isinstance(r, dict):
            continue
        out.append(
            _feature(
                "pocket_corner_r_{}".format(idx),
                "pocket_corner_r",
                geometry={
                    "radius_mm": float(r.get("r_mm", r.get("radius_mm", 0)) or 0),
                    "depth_mm": float(r.get("depth_mm", 0) or 0),
                    "label": str(r.get("label", "")),
                },
                active=bool(r.get("active", False)),
                source="pocket_corner_r",
            )
        )
    return out


def _face_planes_to_features(flat_depths: Optional[dict]) -> List[dict]:
    fd = flat_depths or {}
    planes = fd.get("planes") or []
    out = []
    for idx, p in enumerate(planes):
        if not isinstance(p, dict):
            continue
        area = float(p.get("area_mm2", 0) or 0)
        if area < 1.0:
            continue
        out.append(
            _feature(
                "face_plane_{}".format(idx),
                "face_plane",
                geometry={
                    "z_height_mm": float(p.get("z_height_mm", 0) or 0),
                    "depth_from_z0_mm": float(p.get("depth_from_z0_mm", 0) or 0),
                    "area_mm2": area,
                    "relative_depth_mm": float(p.get("relative_depth_mm", 0) or 0),
                },
                active=True,
                source="flat_depth_scan",
            )
        )
    if fd.get("z_span_mm"):
        out.insert(
            0,
            _feature(
                "face_plane_summary",
                "face_plane",
                geometry={
                    "z_span_mm": float(fd.get("z_span_mm", 0) or 0),
                    "max_z_mm": 0.0,
                    "z0_to_part_bottom_mm": float(fd.get("z0_to_part_bottom_mm", 0) or 0),
                    "job_stock_fixed_z_offset_mm": float(fd.get("job_stock_fixed_z_offset_mm", 0) or 0),
                    "stock_to_part_top_mm": float(fd.get("stock_to_part_top_mm", 0) or 0),
                    "part_thickness_mm": float(fd.get("part_thickness_mm", fd.get("z_span_mm", 0)) or 0),
                    "stock_remaining_thickness_mm": (
                        float(fd["stock_remaining_thickness_mm"])
                        if fd.get("stock_remaining_thickness_mm") is not None
                        else None
                    ),
                    "job_stock_fixed_z_mm": float((fd.get("stock") or {}).get("fixed_z_mm", 0) or 0),
                    "stock_fixed_x_mm": float((fd.get("stock") or {}).get("fixed_x_mm", 0) or 0),
                    "stock_fixed_y_mm": float((fd.get("stock") or {}).get("fixed_y_mm", 0) or 0),
                    "stock_fixed_z_mm": float((fd.get("stock") or {}).get("fixed_z_mm", 0) or 0),
                    "plane_tier_count": len(planes),
                },
                active=True,
                source="flat_depth_scan",
            ),
        )
    return out


def _contours_to_features(contour_rows: List[dict]) -> List[dict]:
    out = []
    for idx, c in enumerate(contour_rows or []):
        if not isinstance(c, dict):
            continue
        out.append(
            _feature(
                str(c.get("feature_id", "contour_{}".format(idx))),
                "outer_contour",
                geometry={
                    "body_index": int(c.get("body_index", 0)),
                    "top_face_index": int(c.get("top_face_index", 0)),
                    "perimeter_mm": float(c.get("perimeter_mm", 0) or 0),
                    "edge_count": int(c.get("edge_count", 0) or 0),
                },
                active=True,
                source="contour_recognizer",
            )
        )
    return out


def _chamfer_bevel_to_features(design, setup) -> List[dict]:
    if not design or not setup:
        return []
    try:
        from Smart_AI.perception import contour_recognizer as cr
        from smart_ai_cam_vision.snapshot import _get_setup_target_bodies
    except Exception:
        return []

    origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()
    root = design.rootComponent
    bodies = _get_setup_target_bodies(setup, root)
    out = []
    idx = 0
    for body in bodies:
        for edge in cr.get_chamfer_bevel_edges_wcs(body, origin, x_axis, y_axis, z_axis):
            try:
                length_mm = round(float(edge.length) * 10.0, 3)
            except Exception:
                length_mm = 0.0
            out.append(
                _feature(
                    "chamfer_{}".format(idx),
                    "chamfer_bevel",
                    geometry={"edge_length_mm": length_mm},
                    active=True,
                    source="contour_chamfer_scan",
                )
            )
            idx += 1
    return out


def _fusion_pockets_to_features(fusion_rec: Optional[dict]) -> List[dict]:
    out = []
    for idx, p in enumerate((fusion_rec or {}).get("pockets") or []):
        if not isinstance(p, dict):
            continue
        out.append(
            _feature(
                "fusion_pocket_{}".format(idx),
                "official_pocket",
                geometry=dict(p),
                active=True,
                source="RecognizedPocket",
            )
        )
    return out


def _fusion_hole_groups_to_features(fusion_rec: Optional[dict]) -> List[dict]:
    out = []
    for idx, g in enumerate((fusion_rec or {}).get("hole_groups") or []):
        if not isinstance(g, dict):
            continue
        out.append(
            _feature(
                "fusion_hole_{}".format(idx),
                "hole",
                geometry=dict(g),
                active=True,
                source="RecognizedHoleGroup",
            )
        )
    return out


def build_feature_catalog(
    *,
    design=None,
    setup=None,
    holes: Optional[List[dict]] = None,
    slots: Optional[List[dict]] = None,
    pocket_corner_r: Optional[List[dict]] = None,
    flat_depths: Optional[dict] = None,
    vision_snapshot: Optional[dict] = None,
    fusion_recognition: Optional[dict] = None,
    include_chamfer_scan: bool = True,
) -> dict:
    """
    Full recognition scope envelope for AI / MCP / panel init.
    """
    features: List[dict] = []
    features.extend(_holes_to_features(holes or []))
    features.extend(_slots_to_features(slots or []))
    features.extend(_pocket_corner_r_to_features(pocket_corner_r or []))
    features.extend(_face_planes_to_features(flat_depths))

    contour_rows = []
    if vision_snapshot and vision_snapshot.get("ok"):
        contour_rows = (vision_snapshot.get("recognized_features") or {}).get("contours") or []
    elif design and setup:
        try:
            from smart_ai_cam_vision.snapshot import _scan_contours

            contour_rows = _scan_contours(design, setup)
        except Exception:
            contour_rows = []
    features.extend(_contours_to_features(contour_rows))
    
    # Extract T-slots and undercuts from vision_snapshot
    if vision_snapshot and vision_snapshot.get("ok"):
        try:
            feats_dict = vision_snapshot.get("recognized_features") or {}
            special_profiles = feats_dict.get("special_profiles") or []
            for sp_idx, sp in enumerate(special_profiles):
                kind = sp.get("kind", "undercut")
                features.append(
                    _feature(
                        "{}_profile_{}".format(kind, sp_idx),
                        kind,
                        geometry={
                            "z_ceiling_mm": sp.get("z_ceiling_mm"),
                            "z_floor_mm": sp.get("z_floor_mm"),
                            "height_mm": sp.get("height_mm"),
                            "area_sqmm": sp.get("area_sqmm"),
                            "cx_mm": sp.get("cx_mm"),
                            "cy_mm": sp.get("cy_mm"),
                            "cz_mm": sp.get("cz_mm"),
                        },
                        active=True,
                        source="contour_extension_recognizer",
                    )
                )
        except Exception:
            pass

    if include_chamfer_scan and design and setup:
        features.extend(_chamfer_bevel_to_features(design, setup))

    if fusion_recognition:
        features.extend(_fusion_hole_groups_to_features(fusion_recognition))
        features.extend(_fusion_pockets_to_features(fusion_recognition))

    counts = {}
    cam_ops = {}
    for f in features:
        cat = f.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
        op = f.get("cam_operation", "")
        if op:
            cam_ops[op] = cam_ops.get(op, 0) + 1

    setup_name = ""
    try:
        setup_name = setup.name if setup else ""
    except Exception:
        pass

    return {
        "catalog_version": CATALOG_VERSION,
        "setup_name": setup_name,
        "feature_count": len(features),
        "counts_by_category": counts,
        "counts_by_cam_operation": cam_ops,
        "cam_operation_map": CAM_OPERATION_MAP,
        "features": features,
    }


def catalog_summary_for_init(catalog: Optional[dict]) -> dict:
    if not catalog or not isinstance(catalog, dict):
        return {"ok": False, "feature_count": 0}
    return {
        "ok": True,
        "catalog_version": catalog.get("catalog_version", CATALOG_VERSION),
        "setup_name": catalog.get("setup_name", ""),
        "feature_count": int(catalog.get("feature_count", 0)),
        "counts_by_category": dict(catalog.get("counts_by_category") or {}),
        "counts_by_cam_operation": dict(catalog.get("counts_by_cam_operation") or {}),
    }
