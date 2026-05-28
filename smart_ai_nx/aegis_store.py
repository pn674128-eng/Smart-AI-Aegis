# -*- coding: utf-8 -*-
"""Local store under Ollama tree — CAD/CAM upload only via Aegis (no cloud)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import STORE_DIR


def _geo_dir(geo_id: str) -> Path:
    p = STORE_DIR / "geo" / geo_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _aliases_path(geo_id: str) -> Path:
    return _geo_dir(geo_id) / "aliases.json"


def submit_cad_features(
    drawing_no: str,
    features: List[Dict[str, Any]],
    *,
    hole_id: Optional[str] = None,
    geo_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from .feature_identity import compute_geo_id, enrich_features, hole_counts_from_features, hole_id_from_counts

    feats = enrich_features(features)
    hid = hole_id or hole_id_from_counts(hole_counts_from_features(feats))
    canonical = {"hole_id": hid, "features": feats}
    gid = geo_id or compute_geo_id(canonical)
    gdir = _geo_dir(gid)
    (gdir / "cad_features.json").write_text(
        json.dumps({"drawing_no": drawing_no, "features": feats, "hole_id": hid, "meta": meta or {}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    aliases: List[str] = []
    ap = _aliases_path(gid)
    if ap.is_file():
        aliases = json.loads(ap.read_text(encoding="utf-8"))
    if drawing_no and drawing_no not in aliases:
        aliases.append(drawing_no)
        ap.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    idx_dir = STORE_DIR / "index" / "by_hole_id"
    idx_dir.mkdir(parents=True, exist_ok=True)
    idx_file = idx_dir / f"{hid}.json"
    candidates: List[str] = []
    if idx_file.is_file():
        candidates = json.loads(idx_file.read_text(encoding="utf-8"))
    if gid not in candidates:
        candidates.append(gid)
        idx_file.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"geo_id": gid, "hole_id": hid, "drawing_no": drawing_no, "feature_count": len(feats)}


def submit_cam_machining(geo_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    gdir = _geo_dir(geo_id)
    payload = dict(payload)
    payload["updated_at"] = time.time()
    (gdir / "cam_machining.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"geo_id": geo_id, "saved": True}


def get_cad_features(*, geo_id: Optional[str] = None, drawing_no: Optional[str] = None) -> Dict[str, Any]:
    gid = geo_id
    if not gid and drawing_no:
        gid = resolve_drawing_no(drawing_no)
    if not gid:
        return {"success": False, "error": "geo_id or drawing_no required"}
    path = _geo_dir(gid) / "cad_features.json"
    if not path.is_file():
        return {"success": False, "error": f"no cad features for geo_id={gid}"}
    return {"success": True, "geo_id": gid, "data": json.loads(path.read_text(encoding="utf-8"))}


def get_cam_machining(*, geo_id: Optional[str] = None, drawing_no: Optional[str] = None) -> Dict[str, Any]:
    gid = geo_id or (drawing_no and resolve_drawing_no(drawing_no))
    if not gid:
        return {"success": False, "error": "geo_id or drawing_no required"}
    path = _geo_dir(gid) / "cam_machining.json"
    if not path.is_file():
        return {"success": False, "error": f"no cam data for geo_id={gid}"}
    return {"success": True, "geo_id": gid, "data": json.loads(path.read_text(encoding="utf-8"))}


def resolve_drawing_no(drawing_no: str) -> Optional[str]:
    for ap in (STORE_DIR / "geo").glob("*/aliases.json"):
        try:
            aliases = json.loads(ap.read_text(encoding="utf-8"))
        except Exception:
            continue
        if drawing_no in aliases:
            return ap.parent.name
    return None
