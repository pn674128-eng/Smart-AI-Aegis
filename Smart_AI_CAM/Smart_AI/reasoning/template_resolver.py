# -*- coding: utf-8 -*-
"""
Resolve template display names to CAM library URLs using runtime template maps.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from smart_ai_cam_state.runtime_state import state as runtime_state

from Smart_AI.memory.knowledge_db import canonical_template_name


def _norm_key(label: str) -> str:
    s = canonical_template_name(label).lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)[:120]


def _url_str(url_obj) -> str:
    if url_obj is None:
        return ""
    try:
        return str(url_obj.toString()).strip()
    except Exception:
        return str(url_obj or "").strip()


def _iter_map_items(material: str):
    mat = str(material or "AL6061").upper()
    map_names = (
        "allDrillMap",
        "allChamferMap",
        "allCountersinkMap",
        "allSlotMap",
        "allSlotChamferMap",
        "allTopFaceRoughMap",
        "allTopFaceFinishMap",
        "allProfileRoughMap",
        "allProfileFinishMap",
        "allTopFaceMap",
        "allProfileMap",
    )
    for mn in map_names:
        m = getattr(runtime_state, mn, None) or {}
        lst = m.get(mat) if isinstance(m, dict) else []
        for it in lst or []:
            if isinstance(it, dict):
                yield mn, it


def build_name_url_index(material: str, *, force_refresh: bool = False) -> Dict[str, dict]:
    """
    norm_key -> {name, url, map_name, drillUrl, chamferUrl, ...}
    """
    cache_key = "_template_name_url_index_{}".format(str(material or "AL6061").upper())
    if not force_refresh:
        cached = getattr(runtime_state, cache_key, None)
        if isinstance(cached, dict) and cached:
            return cached

    index: Dict[str, dict] = {}
    for map_name, it in _iter_map_items(material):
        name = str(it.get("name", "") or "").strip()
        if not name or name == "(不使用)":
            continue
        nk = _norm_key(name)
        if not nk:
            continue
        entry = {
            "name": name,
            "map_name": map_name,
            "url": it.get("url"),
            "url_str": _url_str(it.get("url")),
            "drillUrl": it.get("drillUrl"),
            "chamferUrl": it.get("chamferUrl"),
            "slotUrl": it.get("slotUrl"),
        }
        prev = index.get(nk)
        if not prev or len(name) > len(prev.get("name", "")):
            index[nk] = entry
    setattr(runtime_state, cache_key, index)
    return index


def invalidate_name_url_index(material: str = "") -> None:
    if material:
        keys = ["_template_name_url_index_{}".format(str(material).upper())]
    else:
        keys = [k for k in dir(runtime_state) if k.startswith("_template_name_url_index_")]
    for k in keys:
        try:
            delattr(runtime_state, k)
        except Exception:
            pass


def resolve_template_entry(
    material: str,
    template_name: str,
    *,
    feature_hint: str = "",
) -> Optional[dict]:
    """Find best index entry for a display name or .f3dhsm leaf."""
    name = str(template_name or "").strip()
    if not name:
        return None
    index = build_name_url_index(material)
    nk = _norm_key(name)
    if nk in index:
        return dict(index[nk])

    leaf = name
    if leaf.lower().endswith(".f3dhsm-template"):
        leaf = leaf[:-len(".f3dhsm-template")]
    leaf_key = _norm_key(leaf)
    if leaf_key in index:
        return dict(index[leaf_key])

    # 子字串：最長名稱優先
    best = None
    best_len = 0
    for ent in index.values():
        en = _norm_key(ent.get("name", ""))
        if not en:
            continue
        if nk in en or en in nk:
            ln = len(en)
            if ln > best_len:
                best_len = ln
                best = ent
    if best:
        return dict(best)

    if feature_hint:
        hint = feature_hint.lower()
        for ent in index.values():
            mn = str(ent.get("map_name", "")).lower()
            if hint in mn:
                en = ent.get("name", "")
                if _norm_key(name) in _norm_key(en) or _norm_key(en) in nk:
                    return dict(ent)
    return None


def resolve_template_url(
    material: str,
    template_name: str,
    *,
    feature_hint: str = "",
    url_field: str = "url",
):
    ent = resolve_template_entry(material, template_name, feature_hint=feature_hint)
    if not ent:
        return None
    if url_field == "drill" and ent.get("drillUrl"):
        return ent.get("drillUrl")
    if url_field == "chamfer" and ent.get("chamferUrl"):
        return ent.get("chamferUrl")
    return ent.get("url")


def enrich_operation_template_meta(
    meta: dict,
    material: str,
) -> dict:
    """Fill template_path / resolved_url when import only has operation name."""
    if not isinstance(meta, dict):
        return meta
    out = dict(meta)
    used = str(out.get("template_used", "") or "").strip()
    ft = str(out.get("feature_type", "") or "")
    if not used:
        return out
    ent = resolve_template_entry(material, used, feature_hint=ft)
    if not ent:
        return out
    if not out.get("template_path") and ent.get("url_str"):
        try:
            leaf = os.path.basename(ent["url_str"].replace("\\", "/"))
            if leaf.lower().endswith(".f3dhsm-template"):
                out["template_path"] = leaf
        except Exception:
            pass
    out["resolved_url_str"] = ent.get("url_str", "")
    out["resolved_map"] = ent.get("map_name", "")
    if ent.get("name") and out.get("template_used") == out.get("operation_name"):
        out["template_used"] = ent["name"]
    return out
