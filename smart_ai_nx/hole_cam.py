# -*- coding: utf-8 -*-
"""
Hole/slot/face CAM rule engine — inspired by StarCAM hole_type + oper_type_new,
implemented as open YAML (Smart AI CAM-NX).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import PKG_DIR
from .nx_cam_library import recommend_cut_method

DATA_DIR = PKG_DIR / "data"
SCHEMES_DIR = DATA_DIR / "schemes"


def _load_yaml(path: Path) -> Dict[str, Any]:
    from .yaml_util import safe_load_file

    if not path.is_file():
        return {}
    return safe_load_file(path) or {}


def _data_path(stem: str, subdir: str = "hole_cam") -> Path:
    base = DATA_DIR / subdir / stem
    if base.with_suffix(".yaml").is_file():
        return base.with_suffix(".yaml")
    return base.with_suffix(".json")


@lru_cache(maxsize=1)
def load_oper_templates() -> Dict[str, Dict[str, Any]]:
    raw = _load_yaml(_data_path("oper_templates"))
    return dict(raw.get("templates") or {})


@lru_cache(maxsize=1)
def load_hole_rules() -> List[Dict[str, Any]]:
    raw = _load_yaml(_data_path("hole_rules"))
    rules = list(raw.get("rules") or [])
    return sorted(rules, key=lambda r: int(r.get("priority", 9999)))


def list_schemes() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set = set()
    if not SCHEMES_DIR.is_dir():
        return out
    for p in sorted(list(SCHEMES_DIR.glob("*.yaml")) + list(SCHEMES_DIR.glob("*.json"))):
        if p.stem in seen:
            continue
        seen.add(p.stem)
        doc = _load_yaml(p)
        out.append({
            "id": doc.get("id") or p.stem,
            "name_zh": doc.get("name_zh", p.stem),
            "path": str(p),
        })
    return out


def get_scheme(scheme_id: str) -> Dict[str, Any]:
    for ext in (".yaml", ".json"):
        path = SCHEMES_DIR / f"{scheme_id}{ext}"
        if path.is_file():
            return _load_yaml(path)
    raise FileNotFoundError(f"scheme not found: {scheme_id}")


def _feature_type(feature: Dict[str, Any]) -> str:
    cat = (feature.get("category") or feature.get("type") or "").lower()
    if cat in ("threaded_hole",):
        return "hole"
    if cat in ("counterbore", "countersink", "reamed_hole"):
        return "hole"
    if cat == "hole":
        return "hole"
    if cat in ("slot", "groove"):
        return "slot"
    if cat in ("pocket",):
        return "pocket"
    if cat in ("face", "face_plane", "plane"):
        return "face_plane"
    if cat in ("surface_shoe", "surface_freeform"):
        return "surface_shoe"
    return cat or "unknown"


def _boolish(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val in (0, "0", None, ""):
        return False
    return bool(val)


def _tolerance_is_ream(tolerance: Optional[str]) -> bool:
    if not tolerance:
        return False
    return bool(re.search(r"H[67]|h[67]|Ream|鉸", str(tolerance), re.I))


def match_rule(feature: Dict[str, Any]) -> Dict[str, Any]:
    """Return first matching rule (lowest priority number wins)."""
    ft = _feature_type(feature)
    fallback: Optional[Dict[str, Any]] = None
    for rule in load_hole_rules():
        if rule.get("id") == "fallback":
            fallback = rule
            continue
        spec = rule.get("match") or {}
        if spec.get("feature_type") and spec["feature_type"] != ft:
            continue
        if "through" in spec and bool(feature.get("through", True)) != bool(spec["through"]):
            continue
        if "thread" in spec:
            has = bool(feature.get("thread")) or (feature.get("category") == "threaded_hole")
            if bool(spec["thread"]) != has:
                continue
        if "tolerance_ream" in spec:
            ream = _tolerance_is_ream(feature.get("tolerance")) or feature.get("category") == "reamed_hole"
            if ream != bool(spec["tolerance_ream"]):
                continue
        if "countersink" in spec:
            cs = _boolish(feature.get("countersink")) or feature.get("category") in (
                "countersink", "counterbore",
            )
            if bool(spec["countersink"]) != cs:
                continue
        if "angled" in spec:
            ang = _boolish(feature.get("angled")) or _boolish(feature.get("slope"))
            if bool(spec["angled"]) != ang:
                continue
        if "slotted" in spec:
            sl = _boolish(feature.get("slotted")) or feature.get("kind") == "slotted"
            if bool(spec["slotted"]) != sl:
                continue
        if "color_id" in spec:
            fc = feature.get("color_id")
            if fc is None:
                continue
            if int(spec["color_id"]) != int(fc):
                continue
        if "slot_subtype" in spec:
            st = feature.get("slot_subtype")
            if st is None:
                continue
            if int(spec["slot_subtype"]) != int(st):
                continue
        dia = feature.get("diameter_mm", feature.get("diameter"))
        dr = spec.get("diameter_mm")
        if dr and dia is not None:
            d = float(dia)
            if "min" in dr and d < float(dr["min"]):
                continue
            if "max" in dr and d > float(dr["max"]):
                continue
        return rule
    return fallback or {"id": "fallback", "operations": ["manual_review"], "name_zh": "未匹配"}


def _resolve_tool_hint(feature: Dict[str, Any], template: Dict[str, Any]) -> Optional[str]:
    pat = template.get("tool_name_pattern")
    if not pat:
        return None
    dia = feature.get("diameter_mm", feature.get("diameter"))
    thread = feature.get("thread")
    if thread and "{thread}" in pat:
        return pat.format(thread=str(thread).upper())
    if dia is not None:
        d = float(dia)
        if "{diameter}" in pat:
            return pat.format(diameter=d)
        if "{diameter_ceiling}" in pat:
            import math
            return pat.format(diameter_ceiling=int(math.ceil(d)))
    return pat


def expand_operations(
    feature: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    material_profile: str,
) -> List[Dict[str, Any]]:
    templates = load_oper_templates()
    ops: List[Dict[str, Any]] = []
    for key in rule.get("operations") or []:
        tpl = templates.get(key)
        if not tpl:
            ops.append({"oper_key": key, "error": "unknown template key"})
            continue
        stage = tpl.get("cut_method_stage")
        cut = None
        if stage:
            cut = recommend_cut_method(material_profile, stage=stage)
        row = {
            "oper_key": key,
            "gy_name_zh": tpl.get("gy_name_zh"),
            "template_name": tpl.get("template_name"),
            "tool_type": tpl.get("tool_type"),
            "tool_name_hint": _resolve_tool_hint(feature, tpl),
            "cut_method_hint": cut,
            "depth_type": tpl.get("depth_type"),
            "oper_sort": tpl.get("oper_sort"),
            "status": "plan_only",
        }
        ops.append(row)
    return ops


def plan_feature_operations(
    feature: Dict[str, Any],
    *,
    material_profile: str,
    scheme_id: Optional[str] = None,
) -> Dict[str, Any]:
    scheme = get_scheme(scheme_id) if scheme_id else {}
    mp = material_profile or (scheme.get("defaults") or {}).get("material_profile", "carbon_steel")
    rule = match_rule(feature)
    nx_ops = expand_operations(feature, rule, material_profile=mp)
    return {
        "feature_id": feature.get("feature_id") or feature.get("id"),
        "feature_type": _feature_type(feature),
        "feature_identity": feature.get("feature_identity"),
        "matched_rule": {
            "id": rule.get("id"),
            "name_zh": rule.get("name_zh"),
        },
        "scheme_id": scheme_id or "default_part_milling",
        "material_profile": mp,
        "nx_operations": nx_ops,
    }


def catalog_summary() -> Dict[str, Any]:
    return {
        "hole_rules": [
            {"id": r.get("id"), "name_zh": r.get("name_zh"), "operations": r.get("operations")}
            for r in load_hole_rules()
        ],
        "oper_template_keys": sorted(load_oper_templates().keys()),
        "schemes": list_schemes(),
        "data_dir": str(DATA_DIR),
    }
