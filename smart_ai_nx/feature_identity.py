# -*- coding: utf-8 -*-
"""Feature identity + hole_id fast screen (UG-style detailed features)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple


def hole_id_from_counts(diameter_counts: Dict[str, int]) -> str:
    """e.g. {'5.5': 4, '5.0': 2} -> '5.0x2_5.5x4'"""
    parts = []
    for d in sorted(diameter_counts.keys(), key=lambda x: float(x)):
        parts.append(f"{d}x{diameter_counts[d]}")
    return "_".join(parts)


def assign_hole_identity(diameter_mm: float, *, through: bool = True,
                         tolerance: Optional[str] = None,
                         thread: Optional[str] = None) -> str:
    d = round(float(diameter_mm), 1)
    if thread:
        return f"HOLE_TAP_{thread.upper()}"
    if tolerance and re.search(r"H[67]|h[67]|Ream|鉸", str(tolerance), re.I):
        return f"HOLE_REAM_D{d}_{tolerance.replace(' ', '')}"
    if through:
        return f"HOLE_THROUGH_D{d}"
    return f"HOLE_BLIND_D{d}"


def assign_slot_identity(width_mm: float, length_mm: Optional[float] = None) -> str:
    w = round(float(width_mm), 1)
    if length_mm is not None:
        return f"SLOT_OPEN_W{w}_L{round(float(length_mm), 1)}"
    return f"SLOT_OPEN_W{w}"


def assign_face_identity(kind: str = "TOP_PLANAR") -> str:
    return f"FACE_{kind.upper()}"


def compute_geo_id(canonical: Dict[str, Any]) -> str:
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def enrich_features(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for f in features:
        row = dict(f)
        cat = (row.get("category") or row.get("type") or "").lower()
        if cat == "hole" or row.get("type") == "hole":
            row["feature_identity"] = assign_hole_identity(
                row.get("diameter_mm", row.get("diameter", 0)),
                through=bool(row.get("through", True)),
                tolerance=row.get("tolerance"),
                thread=row.get("thread"),
            )
        elif cat in ("slot", "groove"):
            row["feature_identity"] = assign_slot_identity(
                row.get("width_mm", row.get("width", 0)),
                row.get("length_mm"),
            )
        elif cat in ("face", "face_plane", "plane"):
            row["feature_identity"] = assign_face_identity(
                row.get("kind", "TOP_PLANAR"),
            )
        else:
            row["feature_identity"] = row.get("feature_identity") or f"FEATURE_{cat.upper() or 'UNKNOWN'}"
        out.append(row)
    return out


def hole_counts_from_features(features: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for f in features:
        if (f.get("category") or f.get("type")) != "hole":
            continue
        d = f.get("diameter_mm", f.get("diameter"))
        if d is None:
            continue
        key = str(round(float(d), 1))
        counts[key] = counts.get(key, 0) + 1
    return counts
