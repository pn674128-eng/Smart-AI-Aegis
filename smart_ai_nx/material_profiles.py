# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .config import PKG_DIR

_BUILTIN: Dict[str, Any] = {
    "carbon_steel": {
        "id": "carbon_steel",
        "label_zh": "碳鋼",
        "nx_part_material_hint": "碳鋼模板",
        "resolver_material": "S50C",
        "cut_method_defaults": {"rough": "HSM_ROUGH", "semi": "HSM_SEMI", "finish": "HSM_FINISH"},
    },
    "aluminum": {
        "id": "aluminum",
        "label_zh": "鋁材",
        "nx_part_material_hint": "鋁模板",
        "resolver_material": "AL6061",
        "cut_method_defaults": {"rough": "HSM_ROUGH", "semi": "HSM_SEMI", "finish": "HSM_FINISH"},
    },
    "high_hardness": {
        "id": "high_hardness",
        "label_zh": "高硬度",
        "nx_part_material_hint": "硬料模板",
        "resolver_material": "SKD11_hardened",
        "cut_method_defaults": {"rough": "HSM_ROUGH", "semi": "HSM_SEMI", "finish": "HSM_FINISH"},
    },
}


def _load_yaml() -> Dict[str, Any]:
    path = PKG_DIR / "material_profiles.yaml"
    if not path.is_file():
        return dict(_BUILTIN)
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or dict(_BUILTIN)
    except Exception:
        return dict(_BUILTIN)


_CACHE: Dict[str, Any] | None = None


def _data() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load_yaml()
    return _CACHE


def list_profiles() -> List[Dict[str, Any]]:
    return [{"key": k, **v} for k, v in _data().items() if isinstance(v, dict)]


def get_profile(key: str) -> Dict[str, Any]:
    data = _data()
    if key not in data:
        raise KeyError(f"unknown material_profile: {key} (use carbon_steel | aluminum | high_hardness)")
    return {"key": key, **data[key]}
