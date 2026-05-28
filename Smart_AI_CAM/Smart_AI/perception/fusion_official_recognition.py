# -*- coding: utf-8 -*-
"""
Autodesk Fusion official CAM feature recognition (Manufacturing Extension).

Primary APIs:
  - RecognizedHoleGroup.recognizeHoleGroupsWithInput
  - RecognizedPocket.recognizePockets

Falls back gracefully when extension/API unavailable; does not replace hole baseline scan.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import adsk.cam
import adsk.core
import adsk.fusion


def _setup_pocket_search_vector(setup) -> adsk.core.Vector3D:
    """Machinable from setup WCS +Z → search along -Z in model space."""
    try:
        wcs = setup.workCoordinateSystem
        origin, _x, _y, z_axis = wcs.getAsCoordinateSystem()
        return adsk.core.Vector3D.create(-z_axis.x, -z_axis.y, -z_axis.z)
    except Exception:
        return adsk.core.Vector3D.create(0, 0, -1)


def _classify_recognized_hole(hole: adsk.cam.RecognizedHole) -> dict:
    """Map RecognizedHole segments → semantic type (official geometry)."""
    out = {
        "segment_count": 0,
        "hole_kind": "unknown",
        "is_simple_cylinder": False,
        "is_counterbore_style": False,
        "has_top_chamfer_segment": False,
        "bottom_diameter_mm": 0.0,
        "depth_mm": 0.0,
        "count": 1,
    }
    try:
        sc = int(hole.segmentCount)
    except Exception:
        sc = 0
    out["segment_count"] = sc
    if sc <= 0:
        return out

    try:
        seg0 = hole.segment(0)
        st0 = seg0.holeSegmentType
        if sc == 1 and st0 == adsk.cam.HoleSegmentType.HoleSegmentTypeCylinder:
            out["hole_kind"] = "simple"
            out["is_simple_cylinder"] = True
            out["bottom_diameter_mm"] = round(float(seg0.bottomDiameter) * 10.0, 3)
            out["depth_mm"] = round(float(seg0.height) * 10.0, 3)
            return out

        if sc >= 4:
            segs = [hole.segment(i) for i in range(min(sc, 6))]
            types = [s.holeSegmentType for s in segs]
            if (
                types[0] == adsk.cam.HoleSegmentType.HoleSegmentTypeCone
                and types[1] == adsk.cam.HoleSegmentType.HoleSegmentTypeCylinder
                and len(types) > 3
                and types[3] == adsk.cam.HoleSegmentType.HoleSegmentTypeCylinder
            ):
                out["hole_kind"] = "counterbore_chamfer"
                out["is_counterbore_style"] = True
                out["has_top_chamfer_segment"] = True
                out["bottom_diameter_mm"] = round(float(segs[3].bottomDiameter) * 10.0, 3)
                h_sum = 0.0
                for si in (0, 1, 3):
                    try:
                        h_sum += float(segs[si].height)
                    except Exception:
                        pass
                out["depth_mm"] = round(h_sum * 10.0, 3)
                return out

        out["hole_kind"] = "compound_{}seg".format(sc)
    except Exception:
        pass
    return out


def _pocket_is_circular(pocket: adsk.cam.RecognizedPocket) -> bool:
    try:
        if hasattr(pocket, "isCircular"):
            return bool(pocket.isCircular)
    except Exception:
        pass
    return False


def scan_official_holes(bodies: List[adsk.fusion.BRepBody]) -> Tuple[List[dict], str]:
    groups_out: List[dict] = []
    err = ""
    if not bodies:
        return groups_out, "no_bodies"
    try:
        inp = adsk.cam.RecognizedHolesInput.create()
        hole_groups = adsk.cam.RecognizedHoleGroup.recognizeHoleGroupsWithInput(bodies, inp)
    except Exception as ex:
        return [], "RecognizedHoleGroup failed: {}".format(ex)

    try:
        n_grp = hole_groups.count
    except Exception:
        n_grp = 0

    for gi in range(n_grp):
        try:
            grp = hole_groups.item(gi)
            n_h = grp.count
        except Exception:
            continue
        if n_h <= 0:
            continue
        try:
            sample = grp.item(0)
            geo = _classify_recognized_hole(sample)
        except Exception:
            geo = {"hole_kind": "unknown"}
        geo["group_index"] = gi
        geo["count"] = n_h
        groups_out.append(geo)
    return groups_out, err


def scan_official_pockets(
    bodies: List[adsk.fusion.BRepBody],
    setup,
    *,
    skip_circular: bool = True,
) -> Tuple[List[dict], str, int]:
    try:
        import importlib
        import Smart_AI.perception.official_pocket_execute as _ope

        _ope = importlib.reload(_ope)
        classify_recognized_pocket_kind = _ope.classify_recognized_pocket_kind
        pocket_display_spec_mm = _ope.pocket_display_spec_mm
        should_exclude_recognized_pocket_from_panel = (
            _ope.should_exclude_recognized_pocket_from_panel
        )
    except ImportError:
        try:
            from . import official_pocket_execute as _ope

            import importlib

            _ope = importlib.reload(_ope)
            classify_recognized_pocket_kind = _ope.classify_recognized_pocket_kind
            pocket_display_spec_mm = _ope.pocket_display_spec_mm
            should_exclude_recognized_pocket_from_panel = (
                _ope.should_exclude_recognized_pocket_from_panel
            )
        except ImportError as _imp_ex:
            raise ImportError(
                "official_pocket_execute 未就緒（請重載外掛）: {}".format(_imp_ex)
            ) from _imp_ex
    pockets_out: List[dict] = []
    excluded_as_holes = 0
    if not setup:
        return [], "no_setup", 0
    search_vec = _setup_pocket_search_vector(setup)
    for body in bodies or []:
        try:
            pockets = adsk.cam.RecognizedPocket.recognizePockets(body, search_vec)
        except Exception as ex:
            return pockets_out, "RecognizedPocket failed: {}".format(ex), excluded_as_holes
        try:
            n = pockets.count
        except Exception:
            n = 0
        for pi in range(n):
            try:
                pocket = pockets.item(pi)
            except Exception:
                continue
            if skip_circular and _pocket_is_circular(pocket):
                excluded_as_holes += 1
                continue
            if should_exclude_recognized_pocket_from_panel(pocket, setup):
                excluded_as_holes += 1
                continue
            pocket_kind = classify_recognized_pocket_kind(pocket, setup)
            spec = pocket_display_spec_mm(pocket, setup, pocket_kind)
            row = {
                "body_token": str(getattr(body, "entityToken", "") or ""),
                "pocket_index": pi,
                "is_through": bool(getattr(pocket, "isThrough", False)),
                "is_closed": bool(getattr(pocket, "isClosed", True)),
                "is_circular": _pocket_is_circular(pocket),
                "pocket_kind": pocket_kind,
                "width_mm": spec.get("width_mm"),
                "length_mm": spec.get("length_mm"),
                "depth_mm": spec.get("depth_mm"),
                "source": "RecognizedPocket",
            }
            try:
                bounds = pocket.boundaries
                bc = bounds.count if hasattr(bounds, "count") else 0
                row["boundary_count"] = bc
            except Exception:
                row["boundary_count"] = 0
            pockets_out.append(row)
    return pockets_out, "", excluded_as_holes


def scan_design_threads(design: adsk.fusion.Design) -> List[dict]:
    """Fusion design timeline Hole features with thread info (supplement official holes)."""
    rows = []
    if not design:
        return rows
    try:
        root = design.rootComponent
        for fi in range(root.features.count):
            feat = root.features.item(fi)
            try:
                if feat.objectType != adsk.fusion.HoleFeature.classType():
                    continue
                hf = adsk.fusion.HoleFeature.cast(feat)
            except Exception:
                continue
            threaded = False
            pitch_mm = None
            try:
                if hasattr(hf, "isTapped") and hf.isTapped:
                    threaded = True
            except Exception:
                pass
            try:
                ti = hf.threadInfo
                if ti:
                    threaded = True
                    if hasattr(ti, "threadPitch"):
                        pitch_mm = round(float(ti.threadPitch) * 10.0, 4)
            except Exception:
                pass
            dia_mm = None
            try:
                if hf.holeDiameter:
                    dia_mm = round(float(hf.holeDiameter.value) * 10.0, 3)
            except Exception:
                pass
            rows.append(
                {
                    "feature_name": feat.name,
                    "threaded": threaded,
                    "pitch_mm": pitch_mm,
                    "diameter_mm": dia_mm,
                    "source": "HoleFeature",
                }
            )
    except Exception:
        pass
    return rows


def run_official_recognition(
    *,
    design: adsk.fusion.Design,
    setup,
    bodies: Optional[List[adsk.fusion.BRepBody]] = None,
) -> dict:
    """
    Full official recognition pass for current setup bodies.
    """
    result = {
        "ok": False,
        "reason": "",
        "hole_groups": [],
        "pockets": [],
        "pockets_excluded_as_holes": 0,
        "design_threads": [],
        "body_count": 0,
    }
    if not design or not setup:
        result["reason"] = "missing_design_or_setup"
        return result

    if bodies is None:
        bodies = []
        try:
            from smart_ai_cam_vision.snapshot import _get_setup_target_bodies

            bodies = list(_get_setup_target_bodies(setup, design.rootComponent) or [])
        except Exception:
            pass

    result["body_count"] = len(bodies or [])
    if not bodies:
        result["reason"] = "no_target_bodies"
        return result

    hole_groups, hole_err = scan_official_holes(bodies)
    pockets, pocket_err, pockets_excluded = scan_official_pockets(bodies, setup)
    threads = scan_design_threads(design)

    result["hole_groups"] = hole_groups
    result["pockets"] = pockets
    result["pockets_excluded_as_holes"] = int(pockets_excluded or 0)
    result["design_threads"] = threads
    result["ok"] = bool(hole_groups or pockets or threads)
    if hole_err:
        result["reason"] = hole_err
    elif pocket_err:
        result["reason"] = pocket_err
    else:
        result["reason"] = "ok" if result["ok"] else "empty"
    return result


def match_hole_rows_to_official(
    panel_holes: List[dict],
    hole_groups: List[dict],
    design_threads: Optional[List[dict]] = None,
) -> List[dict]:
    """
    Per panel hole row index: official hint for template apply (by diameter mm).
    Does not change hole recognizer output.
    """
    by_dia = {}
    for g in hole_groups or []:
        d = float(g.get("bottom_diameter_mm", 0) or 0)
        if d <= 0:
            continue
        key = round(d, 1)
        by_dia.setdefault(key, []).append(g)

    thread_by_dia = {}
    for t in design_threads or []:
        d = t.get("diameter_mm")
        if d is None:
            continue
        thread_by_dia[round(float(d), 1)] = t

    hints = []
    for idx, h in enumerate(panel_holes or []):
        if not isinstance(h, dict):
            continue
        try:
            dia = round(float(h.get("dia", 0)), 1)
        except Exception:
            dia = 0.0
        grp_list = by_dia.get(dia) or []
        grp = grp_list[0] if grp_list else {}
        th = thread_by_dia.get(dia) or {}
        hint = {
            "idx": idx,
            "dia_mm": dia,
            "official_hole_kind": grp.get("hole_kind", ""),
            "official_is_counterbore": bool(grp.get("is_counterbore_style", False)),
            "official_has_chamfer_seg": bool(grp.get("has_top_chamfer_segment", False)),
            "is_threaded": bool(th.get("threaded", False)),
            "thread_pitch_mm": th.get("pitch_mm"),
            "prefer_countersink": bool(h.get("isCBLarge")) or bool(grp.get("is_counterbore_style")),
            "prefer_tap": bool(th.get("threaded", False)),
            "prefer_drill_chamfer_combo": bool(grp.get("has_top_chamfer_segment")),
        }
        hints.append(hint)
    return hints
