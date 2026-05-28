# -*- coding: utf-8 -*-
"""Read-only bridge to Fusion smart_ai_cam_mcp (6-layer resolver)."""
from __future__ import annotations

import sys
import traceback
from typing import Any, Dict

from .config import FUSION_ADDIN_DIR


def _ensure_fusion_path() -> bool:
    p = str(FUSION_ADDIN_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    return FUSION_ADDIN_DIR.is_dir()


def query_smart_cutting(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _ensure_fusion_path():
        return {
            "success": False,
            "error": f"Smart AI CAM Fusion add-in not found: {FUSION_ADDIN_DIR}",
        }
    try:
        from smart_ai_cam_mcp.cutting_resolver import dispatch

        result = dispatch(_resolver_kwargs(params))
        if isinstance(result, dict) and result.get("success") is False and result.get("error"):
            return {
                "success": False,
                "error": result.get("error"),
                "data": result,
                "source": "fusion_cutting_resolver_readonly",
            }
        return {"success": True, "data": result, "source": "fusion_cutting_resolver_readonly"}
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


def query_regular_milling(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _ensure_fusion_path():
        return {"success": False, "error": "Fusion add-in path missing"}
    try:
        from smart_ai_cam_mcp import regular_milling

        return {"success": True, "data": regular_milling.dispatch(params), "source": "regular_milling"}
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


def query_gold_cobra(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _ensure_fusion_path():
        return {"success": False, "error": "Fusion add-in path missing"}
    try:
        from smart_ai_cam_mcp import gold_cobra_catalog

        return {"success": True, "data": gold_cobra_catalog.dispatch(params), "source": "gold_cobra"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def query_general_catalog(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _ensure_fusion_path():
        return {"success": False, "error": "Fusion add-in path missing"}
    try:
        from smart_ai_cam_mcp import general_catalog

        return {"success": True, "data": general_catalog.dispatch(params), "source": "general_catalog"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def query_heuristics(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _ensure_fusion_path():
        return {"success": False, "error": "Fusion add-in path missing"}
    try:
        from smart_ai_cam_mcp import machining_heuristics

        return {"success": True, "data": machining_heuristics.dispatch(params), "source": "heuristics"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def query_tool_holders(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _ensure_fusion_path():
        return {"success": False, "error": "Fusion add-in path missing"}
    try:
        from smart_ai_cam_mcp import tool_holders

        return {"success": True, "data": tool_holders.dispatch(params), "source": "tool_holders"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _resolver_kwargs(params: Dict[str, Any]) -> Dict[str, Any]:
    """Map NX fields → Fusion resolver dispatch params (strip NX-only keys)."""
    from .material_profiles import get_profile

    p = dict(params)
    mp = p.pop("material_profile", None)
    # NX 加工方案 / 半自動欄位，非 cutting_resolver 參數
    for nx_only in (
        "scheme_id",
        "features",
        "drawing_no",
        "feature",
        "feature_id",
        "execute",
        "semi_auto",
    ):
        p.pop(nx_only, None)
    if mp and "material" not in p:
        try:
            p["material"] = get_profile(mp)["resolver_material"]
        except KeyError:
            pass
    return p
