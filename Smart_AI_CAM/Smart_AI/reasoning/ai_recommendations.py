# -*- coding: utf-8 -*-
"""
Internal AI recommendations for palette / MCP (get_ai_recommendations).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from smart_ai_cam_state.runtime_state import state as runtime_state

from . import ai_brain
from . import ai_decision_engine
from . import ai_panel_apply as aipa
from . import ai_training
from Smart_AI.perception import contour_2d_recognizer as c2d


def _collect_cam_tools(cam_obj) -> List[dict]:
    tools: List[dict] = []
    if not cam_obj:
        return tools
    try:
        doc_library = cam_obj.documentToolLibrary
        for i in range(doc_library.count):
            tool = doc_library.item(i)
            t_info = {
                "index": i,
                "number": -1,
                "diameter_mm": 0.0,
                "flute_length_mm": 0.0,
                "type": "Unknown",
                "label": "",
            }
            try:
                t_info["number"] = int(tool.number)
            except Exception:
                try:
                    t_info["number"] = int(tool.parameters.itemByName("tool_number").value.value)
                except Exception:
                    pass
            try:
                t_info["diameter_mm"] = float(tool.parameters.itemByName("tool_diameter").value.value) * 10.0
            except Exception:
                try:
                    t_info["diameter_mm"] = float(tool.diameter) * 10.0
                except Exception:
                    pass
            try:
                t_info["flute_length_mm"] = float(tool.parameters.itemByName("tool_fluteLength").value.value) * 10.0
            except Exception:
                pass
            try:
                t_info["type"] = str(tool.parameters.itemByName("tool_type").value.value)
            except Exception:
                try:
                    t_info["type"] = str(tool.type)
                except Exception:
                    pass
            try:
                t_info["label"] = str(tool.parameters.itemByName("tool_description").value.value)
            except Exception:
                try:
                    t_info["label"] = str(tool.description)
                except Exception:
                    pass
            tools.append(t_info)
    except Exception:
        pass
    return tools


def run_get_ai_recommendations(
    params: dict,
    ctx: Dict[str, Any],
) -> dict:
    """
    Build full AI plan for palette / MCP.

    ctx keys (from Smart_AI_CAM):
      rebuild_holes, build_hole_data, build_slot_data, build_pocket_corner_r_data,
      scan_flat_depths, refresh_fusion_official, refresh_feature_catalog,
      refresh_contour_2d, build_official_pocket_data, contour_chamfer_names,
      top_face_rough_map, top_face_finish_map, profile_rough_map, profile_finish_map,
      cam_obj, des_obj, cam_setup
    """
    material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
    runtime_state.current_material = material

    cam_obj = ctx.get("cam_obj")
    des_obj = ctx.get("des_obj")
    cam_setup = ctx.get("cam_setup")

    tools = _collect_cam_tools(cam_obj)

    rebuild = ctx.get("rebuild_holes")
    if callable(rebuild):
        rebuild(force=True)

    holes_data = ctx["build_hole_data"](material)
    slots_data = ctx["build_slot_data"](material)
    pocket_corner_r_data = ctx["build_pocket_corner_r_data"](material)

    refresh_vision = ctx.get("refresh_vision")
    if callable(refresh_vision):
        try:
            refresh_vision()
        except Exception:
            pass

    flat_depths = ctx["scan_flat_depths"]()

    vision_snap = getattr(runtime_state, "vision_snapshot", None)
    if not getattr(runtime_state, "fusion_official_recognition", None):
        refresh_fusion = ctx.get("refresh_fusion_official")
        if callable(refresh_fusion):
            refresh_fusion()

    feat_cat = getattr(runtime_state, "feature_catalog", None)
    if not feat_cat or not int(feat_cat.get("feature_count", 0) or 0):
        refresh_cat = ctx.get("refresh_feature_catalog")
        if callable(refresh_cat):
            refresh_cat()
        feat_cat = getattr(runtime_state, "feature_catalog", None)

    geom_features = ai_brain.build_geom_features_for_ai(
        holes_data=holes_data,
        slots_data=slots_data,
        pocket_corner_r_data=pocket_corner_r_data,
        flat_depths=flat_depths,
        vision_snapshot=vision_snap,
        feature_catalog=feat_cat,
        design=des_obj,
        setup=cam_setup,
        build_catalog_if_missing=False,
    )

    engine = ai_decision_engine.AIDecisionEngine(current_tools=tools)
    ai_plan = engine.make_machining_plan(material, geom_features)

    tf_rough_map = ctx.get("top_face_rough_map") or {}
    tf_finish_map = ctx.get("top_face_finish_map") or {}
    pf_rough_map = ctx.get("profile_rough_map") or {}
    pf_finish_map = ctx.get("profile_finish_map") or {}

    try:
        from .ai_template_picker import build_recommended_2d_templates

        refresh_c2d = ctx.get("refresh_contour_2d")
        if callable(refresh_c2d):
            try:
                refresh_c2d()
            except Exception:
                pass
        c2d_rec = getattr(runtime_state, "contour_2d_recognition", None)

        _2d = build_recommended_2d_templates(
            material,
            top_face_rough_map=tf_rough_map.get(material, []),
            top_face_finish_map=tf_finish_map.get(material, []),
            profile_rough_map=pf_rough_map.get(material, []),
            profile_finish_map=pf_finish_map.get(material, []),
            contour_2d_recognition=c2d_rec if isinstance(c2d_rec, dict) else None,
        )
        ai_plan["recommended_templates"] = _2d.get("templates") or {}
        ai_plan["template_picker_meta"] = _2d.get("picker_meta") or {}
    except Exception:
        ai_plan["recommended_templates"] = {
            "topFaceRough": "(不使用)",
            "topFaceFinish": "(不使用)",
            "profileRough": "(不使用)",
            "profileFinish": "(不使用)",
        }
        ai_plan["template_picker_meta"] = {}

    try:
        from .machining_feature_catalog import catalog_summary_for_init

        ai_plan["feature_catalog_summary"] = catalog_summary_for_init(
            geom_features.get("feature_catalog") or feat_cat
        )
    except Exception:
        ai_plan["feature_catalog_summary"] = {}

    ai_plan["contour_2d_recognition"] = getattr(runtime_state, "contour_2d_recognition", None)
    try:
        ai_plan["contour2dRecognition"] = c2d.recognition_summary_for_init(
            ai_plan.get("contour_2d_recognition")
        )
    except Exception:
        ai_plan["contour2dRecognition"] = {"ok": False}

    fusion_rec = getattr(runtime_state, "fusion_official_recognition", None) or {}
    fusion_hints: List[dict] = []
    try:
        from Smart_AI.perception.fusion_official_recognition import match_hole_rows_to_official

        fusion_hints = match_hole_rows_to_official(
            holes_data,
            fusion_rec.get("hole_groups") or [],
            fusion_rec.get("design_threads") or [],
        )
    except Exception:
        pass

    ai_plan["fusion_official_recognition"] = fusion_rec
    ai_plan["flat_depths"] = flat_depths
    build_pockets = ctx.get("build_official_pocket_data")
    if callable(build_pockets):
        ai_plan["official_pockets"] = build_pockets(material)

    chamfer_names_fn = ctx.get("contour_chamfer_names")
    chamfer_names = chamfer_names_fn(material) if callable(chamfer_names_fn) else []

    ai_plan["panel_apply"] = aipa.build_panel_apply_patch(
        ai_plan,
        holes_data,
        slots_data,
        pocket_corner_r_data,
        fusion_hole_hints=fusion_hints,
        flat_depths=flat_depths,
        feature_catalog=feat_cat,
        contour_chamfer_names=chamfer_names,
        top_face_rough_names=[
            x.get("name", x) if isinstance(x, dict) else x
            for x in tf_rough_map.get(material, [])
        ],
        top_face_finish_names=[
            x.get("name", x) if isinstance(x, dict) else x
            for x in tf_finish_map.get(material, [])
        ],
        thinking_layer=str(params.get("thinking_layer") or "").strip(),
        official_slot_pocket_panel=(
            ctx["build_official_slot_pocket_data"](material)
            if str(params.get("thinking_layer") or "").strip() == "L1_extended_features"
            and callable(ctx.get("build_official_slot_pocket_data"))
            else None
        ),
        official_pocket_slot_panel=(
            ctx["build_official_pocket_slot_data"](material)
            if str(params.get("thinking_layer") or "").strip() == "L1_extended_features"
            and callable(ctx.get("build_official_pocket_slot_data"))
            else None
        ),
    )

    ai_training.enhance_panel_apply_with_knowledge(
        ai_plan["panel_apply"],
        holes_data,
        slots_data,
        pocket_corner_r_data,
        material,
        top_face_rough_map=tf_rough_map.get(material, []),
        top_face_finish_map=tf_finish_map.get(material, []),
        profile_rough_map=pf_rough_map.get(material, []),
        profile_finish_map=pf_finish_map.get(material, []),
    )
    # 同步 2D 建議到 ai_plan（含學習庫覆寫後）
    pa_rec = (ai_plan.get("panel_apply") or {}).get("recommended_templates")
    if isinstance(pa_rec, dict):
        for k in (
            "topFaceRough",
            "topFaceFinish",
            "profileRough",
            "profileFinish",
            "contourChamfer",
            "terrace_face_ops",
        ):
            if pa_rec.get(k):
                ai_plan.setdefault("recommended_templates", {})[k] = pa_rec[k]
    ai_training.append_knowledge_report(ai_plan)

    try:
        from .ai_template_picker import enrich_plan_with_template_params

        enrich_plan_with_template_params(
            ai_plan,
            material,
            top_face_rough_map=tf_rough_map.get(material, []),
            top_face_finish_map=tf_finish_map.get(material, []),
            profile_rough_map=pf_rough_map.get(material, []),
            profile_finish_map=pf_finish_map.get(material, []),
        )
    except Exception:
        pass

    pa = ai_plan.get("panel_apply") or {}
    if pa.get("row_intelligence"):
        ai_plan["row_intelligence"] = pa["row_intelligence"]
    if pa.get("terrace_face_ops"):
        ai_plan.setdefault("recommended_templates", {})["terrace_face_ops"] = pa["terrace_face_ops"]

    try:
        runtime_state.last_ai_plan = ai_plan
    except Exception:
        pass

    try:
        from Smart_AI.reasoning.cam_depth_plan import (
            build_cam_depth_context,
            enrich_terrace_face_ops,
        )

        cam_ctx = build_cam_depth_context(flat_depths, ai_decisions=ai_plan.get("decisions"))
        ai_plan["cam_depth_context"] = cam_ctx
        pa = ai_plan.get("panel_apply") or {}
        pa["cam_depth_context"] = cam_ctx
        if pa.get("terrace_face_ops"):
            pa["terrace_face_ops"] = enrich_terrace_face_ops(pa["terrace_face_ops"], flat_depths)
            ai_plan.setdefault("recommended_templates", {})["terrace_face_ops"] = pa["terrace_face_ops"]
        ai_plan["panel_apply"] = pa
    except Exception:
        pass

    return {"success": True, "data": ai_plan}
