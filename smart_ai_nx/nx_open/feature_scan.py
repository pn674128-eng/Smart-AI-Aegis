# -*- coding: utf-8 -*-
"""NX Open 特徵掃描（Journal / bridge 共用）。需在 NX 內執行。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def scan_work_part_features(work) -> List[Dict[str, Any]]:
    """從當前 Work Part 掃描孔/槽等（初版：建模特徵 + 圓柱面啟發）。"""
    import NXOpen

    features: List[Dict[str, Any]] = []
    seq = 0

    def add(row: Dict[str, Any]) -> None:
        nonlocal seq
        seq += 1
        row.setdefault("feature_id", f"NX{seq:04d}")
        features.append(row)

    # 1) 建模孔特徵（Hole / 舊版 HolePackage）
    for feat in work.Features:
        try:
            type_name = feat.GetType().Name
        except Exception:
            continue
        tl = type_name.lower()
        if "hole" not in tl:
            continue
        dia = None
        through = True
        try:
            if hasattr(feat, "GetHoleDiameter"):
                dia = _safe_float(feat.GetHoleDiameter())
        except Exception:
            pass
        try:
            if hasattr(feat, "GetHoleDepth"):
                depth = _safe_float(feat.GetHoleDepth())
                if depth is not None and depth > 0:
                    through = False
        except Exception:
            pass
        add({
            "category": "hole",
            "source": "nx_feature",
            "nx_feature_name": feat.Name,
            "nx_feature_type": type_name,
            "diameter_mm": dia,
            "through": through,
        })

    # 2) 圓柱面啟發（無孔特徵時補強）
    if not features:
        try:
            for body in work.Bodies:
                for face in body.GetFaces():
                    try:
                        if face.SolidFaceType != NXOpen.Face.FaceType.Cylindrical:
                            continue
                    except Exception:
                        continue
                    dia = None
                    try:
                        geom = NXOpen.FaceGeometry.Cylindrical(face)
                        dia = _safe_float(geom.Diameter) if geom else None
                    except Exception:
                        pass
                    if dia is None or dia < 0.3:
                        continue
                    add({
                        "category": "hole",
                        "source": "nx_cylindrical_face",
                        "diameter_mm": round(dia, 3),
                        "through": True,
                    })
        except Exception:
            pass

    # 去重：相同直徑+來源合併計數提示
    return features


def scan_summary(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    holes = [f for f in features if f.get("category") == "hole"]
    dias: Dict[str, int] = {}
    for h in holes:
        d = h.get("diameter_mm")
        if d is None:
            continue
        k = str(round(float(d), 2))
        dias[k] = dias.get(k, 0) + 1
    return {
        "total": len(features),
        "holes": len(holes),
        "diameter_counts": dias,
    }
