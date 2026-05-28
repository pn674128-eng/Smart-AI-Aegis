# -*- coding: utf-8 -*-
"""Dispatch MCP actions — Fusion-parity + NX-specific."""
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from . import aegis_store, bridge_resolver, hole_cam, nx_cam_library, nx_session, semi_auto
from .config import PLUGIN_CONFIG_PATH
from .material_profiles import get_profile, list_profiles
from .nx_agent_manifest import build_agent_manifest


def process_mcp_request(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params = params or {}
    try:
        return _dispatch(action, params)
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}


def _dispatch(action: str, p: Dict[str, Any]) -> Dict[str, Any]:
    if action in ("get_cam_agent_manifest", "get_nx_agent_manifest"):
        return {"success": True, "data": build_agent_manifest()}

    if action == "get_addin_info":
        return nx_session.get_addin_info()

    if action == "nx_library_status":
        return {"success": True, "data": nx_cam_library.library_status()}

    if action == "list_material_profiles":
        return {"success": True, "data": list_profiles()}

    if action == "nx_recommend_cut_method":
        mp = p.get("material_profile", "carbon_steel")
        stage = p.get("stage", "rough")
        td = p.get("tool_diameter_mm")
        return {"success": True, "data": nx_cam_library.recommend_cut_method(mp, stage=stage, tool_diameter_mm=td)}

    if action == "query_smart_cutting":
        return bridge_resolver.query_smart_cutting(p)

    if action == "query_regular_milling":
        return bridge_resolver.query_regular_milling(p)

    if action == "query_gold_cobra":
        return bridge_resolver.query_gold_cobra(p)

    if action == "query_general_catalog":
        return bridge_resolver.query_general_catalog(p)

    if action == "query_heuristics":
        return bridge_resolver.query_heuristics(p)

    if action == "query_tool_holders":
        return bridge_resolver.query_tool_holders(p)

    if action == "cad_submit_features":
        feats = p.get("features") or []
        r = aegis_store.submit_cad_features(
            p.get("drawing_no", ""),
            feats,
            hole_id=p.get("hole_id"),
            geo_id=p.get("geo_id"),
            meta=p.get("meta"),
        )
        return {"success": True, "data": r}

    if action == "cam_get_features":
        r = aegis_store.get_cad_features(geo_id=p.get("geo_id"), drawing_no=p.get("drawing_no"))
        return r if "success" in r else {"success": True, "data": r}

    if action == "cam_submit_machining":
        gid = p.get("geo_id")
        if not gid:
            return {"success": False, "error": "geo_id required"}
        return {"success": True, "data": aegis_store.submit_cam_machining(gid, p.get("payload") or p)}

    if action == "cad_get_machining":
        r = aegis_store.get_cam_machining(geo_id=p.get("geo_id"), drawing_no=p.get("drawing_no"))
        return r if "success" in r else {"success": True, "data": r}

    if action == "check_semi_auto_eligibility":
        feats = p.get("features") or []
        mp = p.get("material_profile", "carbon_steel")
        return {"success": True, "data": semi_auto.check_semi_auto_eligibility(feats, mp)}

    if action == "get_semi_auto_plan":
        feats = p.get("features") or []
        mp = p.get("material_profile", "carbon_steel")
        return {"success": True, "data": semi_auto.build_semi_auto_plan(
            feats, mp,
            drawing_no=p.get("drawing_no"),
            scheme_id=p.get("scheme_id", "default_part_milling"),
        )}

    if action == "nx_hole_cam_catalog":
        return {"success": True, "data": hole_cam.catalog_summary()}

    if action == "nx_match_feature_cam":
        feat = p.get("feature") or {}
        mp = p.get("material_profile", "carbon_steel")
        return {"success": True, "data": hole_cam.plan_feature_operations(
            feat, material_profile=mp, scheme_id=p.get("scheme_id"))}

    if action == "get_plugin_config":
        from .yaml_util import safe_load_file
        if not PLUGIN_CONFIG_PATH.is_file():
            return {"success": False, "error": "plugin_config.yaml missing"}
        return {"success": True, "data": safe_load_file(PLUGIN_CONFIG_PATH)}

    if action in ("run_semi_auto_programming", "run_intuitive_programming"):
        plan = semi_auto.build_semi_auto_plan(
            p.get("features") or [],
            p.get("material_profile", "carbon_steel"),
            drawing_no=p.get("drawing_no"),
        )
        if not p.get("execute"):
            return {"success": True, "data": plan, "note": "execute=false — 僅輸出劇本"}
        br = nx_session.post_nx_bridge_request(action, p, timeout_sec=3.0)
        return {"success": br.get("success", False), "data": {"plan": plan, "nx_bridge": br}}

    if action == "scan_machining_features":
        if p.get("features"):
            from .feature_identity import enrich_features, hole_counts_from_features, hole_id_from_counts
            feats = enrich_features(p["features"])
            return {
                "success": True,
                "data": {
                    "features": feats,
                    "hole_id": hole_id_from_counts(hole_counts_from_features(feats)),
                    "source": "params.features",
                },
            }
        return nx_session.post_nx_bridge_request("scan_machining_features", p, timeout_sec=5.0)

    if action == "nx_bridge_status":
        return {"success": True, "data": nx_session.nx_bridge_status()}

    if action == "run_thinking_programming":
        return {
            "success": False,
            "error": "thinking L0/L1/L2 — 下一階段；請先用 get_semi_auto_plan",
            "data": {"material_profile": p.get("material_profile")},
        }

    return {"success": False, "error": f"unknown action: {action}"}
