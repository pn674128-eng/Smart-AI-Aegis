# -*- coding: utf-8 -*-
"""Semi-automatic programming plan (mirror Fusion intuitive / thinking stubs)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import aegis_store
from .feature_identity import enrich_features
from .material_profiles import get_profile
from . import hole_cam
from .nx_cam_library import recommend_cut_method


# NX detailed feature categories (UG advantage) vs Fusion baseline
NX_FEATURE_CATEGORIES = [
    "hole", "threaded_hole", "reamed_hole", "counterbore", "countersink",
    "slot", "groove", "pocket", "face_plane", "outer_contour", "chamfer_bevel",
    "boss", "rib", "surface_shoe", "surface_freeform",
]


def check_semi_auto_eligibility(
    features: List[Dict[str, Any]],
    material_profile: str,
) -> Dict[str, Any]:
    prof = get_profile(material_profile)
    feats = enrich_features(features)
    holes = [f for f in feats if (f.get("category") or f.get("type")) == "hole"]
    slots = [f for f in feats if (f.get("category") or "") in ("slot", "groove")]
    faces = [f for f in feats if (f.get("category") or "") in ("face", "face_plane", "plane")]
    surfaces = [f for f in feats if "surface" in (f.get("category") or "")]

    reasons: List[str] = []
    eligible = True
    if not feats:
        eligible = False
        reasons.append("無特徵資料")
    if surfaces:
        reasons.append("含曲面/鞋面類特徵：建議人工確認 UG 工法後再執行")
    if len(feats) > 80:
        eligible = False
        reasons.append("特徵數 > 80，請分批或手動")

    return {
        "eligible": eligible,
        "material_profile": material_profile,
        "nx_part_material_hint": prof.get("nx_part_material_hint"),
        "summary": {
            "total": len(feats),
            "holes": len(holes),
            "slots": len(slots),
            "faces": len(faces),
            "surfaces": len(surfaces),
        },
        "reasons": reasons,
        "supported_categories": NX_FEATURE_CATEGORIES,
    }


def build_semi_auto_plan(
    features: List[Dict[str, Any]],
    material_profile: str,
    *,
    drawing_no: Optional[str] = None,
    scheme_id: Optional[str] = "default_part_milling",
) -> Dict[str, Any]:
    elig = check_semi_auto_eligibility(features, material_profile)
    prof = get_profile(material_profile)
    feats = enrich_features(features)
    steps: List[Dict[str, Any]] = []
    scheme = scheme_id or "default_part_milling"

    for f in feats:
        fid = f.get("feature_id") or f.get("id") or f"F{len(steps)+1:03d}"
        identity = f.get("feature_identity", "UNKNOWN")
        cam_plan = hole_cam.plan_feature_operations(
            f, material_profile=material_profile, scheme_id=scheme,
        )
        steps.append({
            "feature_id": fid,
            "feature_identity": identity,
            "diameter_mm": f.get("diameter_mm"),
            "matched_rule": cam_plan.get("matched_rule"),
            "nx_operations": cam_plan.get("nx_operations"),
            "nx_operation_intent": _intent_from_operations(cam_plan.get("nx_operations") or []),
            "cut_method_hint": recommend_cut_method(material_profile, stage="semi"),
        })

    plan = {
        "platform": "NX1953",
        "drawing_no": drawing_no,
        "material_profile": material_profile,
        "scheme_id": scheme,
        "resolver_material": prof.get("resolver_material"),
        "eligibility": elig,
        "steps": steps,
        "human_gates": ["before_create_operations", "before_generate_toolpath"],
        "implementation": "plan_only — YAML hole_cam → NX Open create ops (phase 2)",
        "data_reference": "StarCAM-style hole_rules + oper_templates (own format)",
    }
    if drawing_no:
        stored = aegis_store.submit_cad_features(drawing_no, feats)
        plan["geo_id"] = stored.get("geo_id")
        plan["hole_id"] = stored.get("hole_id")
    return plan


def _intent_from_operations(nx_ops: List[Dict[str, Any]]) -> str:
    names = [o.get("template_name") for o in nx_ops if o.get("template_name")]
    if not names:
        return "NX_MANUAL_REVIEW"
    return " → ".join(names)
