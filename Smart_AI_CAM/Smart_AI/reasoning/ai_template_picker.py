# -*- coding: utf-8 -*-
"""
Template picking for AI: knowledge DB + scored keyword match + fuzzy label match.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ai_panel_apply import find_tmpl_idx_by_keywords
from Smart_AI.memory.knowledge_db import get_db

KNOWLEDGE_MIN_CONFIDENCE = 0.35  # 與 ai_training.KNOWLEDGE_MIN_CONFIDENCE 同步

# 2D 角色關鍵字（中英、常見檔名片段）
_ROLE_KEYWORDS = {
    "rough": (
        "粗",
        "rough",
        "粗加工",
        "面粗",
        "輪廓粗",
        "開粗",
        "残量",
        "残",
    ),
    "finish": (
        "精",
        "finish",
        "精加工",
        "面精",
        "輪廓精",
        "精修",
        "光刀",
    ),
}
_FEATURE_KEYWORDS = {
    "face": ("面", "face", "平面", "顶", "頂", "底平面"),
    "profile": ("輪廓", "轮廓", "profile", "外形", "侧壁", "2d", "cad"),
}


def _norm_label_key(label: str) -> str:
    s = str(label or "").strip()
    if not s:
        return ""
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)[:96]


def _collapse_label(s: str) -> str:
    try:
        t = unicodedata.normalize("NFKC", str(s or ""))
    except Exception:
        t = str(s or "")
    return re.sub(r"\s+", "", t, flags=re.UNICODE).lower()


def _label_has_any(label: str, keywords: Sequence[str]) -> bool:
    lab = _collapse_label(label)
    for kw in keywords:
        if kw and _collapse_label(kw) in lab:
            return True
    return False


def _name_matches_2d_role(name: str, role: str, feature_type: str) -> bool:
    role_kws = _ROLE_KEYWORDS.get(role, ())
    feat_kws = _FEATURE_KEYWORDS.get(feature_type, ())
    if not _label_has_any(name, role_kws):
        return False
    # 面／輪廓：有明確特徵字則需匹配；否則僅看粗精
    if any(_label_has_any(name, kws) for kws in _FEATURE_KEYWORDS.values()):
        return _label_has_any(name, feat_kws)
    return True


def _score_2d_candidate(name: str, role: str, feature_type: str) -> float:
    if not name or name == "(不使用)":
        return -1.0
    if not _name_matches_2d_role(name, role, feature_type):
        return -1.0
    score = 1.0
    if _label_has_any(name, _ROLE_KEYWORDS.get(role, ())):
        score += 3.0
    if _label_has_any(name, _FEATURE_KEYWORDS.get(feature_type, ())):
        score += 2.0
    # 避免把「精」誤配到「粗」：雙向排斥
    other = "finish" if role == "rough" else "rough"
    if _label_has_any(name, _ROLE_KEYWORDS.get(other, ())):
        score -= 5.0
    return score


def _find_tmpl_idx_by_label(drop_items: List[dict], template_name: str) -> int:
    name = str(template_name or "").strip()
    if not name:
        return -1
    name_l = name.lower()
    best = -1
    best_len = 0
    for i, it in enumerate(drop_items or []):
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "") or "")
        if label == "(不使用)":
            continue
        lab_l = label.lower()
        if name_l in lab_l or lab_l in name_l:
            if len(label) > best_len:
                best_len = len(label)
                best = i
    return best


def find_tmpl_idx_fuzzy(drop_items: List[dict], template_name: str) -> int:
    """Match dropItems by exact / normalized / keyword fallback."""
    name = str(template_name or "").strip()
    if not name:
        return -1
    idx = _find_tmpl_idx_by_label(drop_items, name)
    if idx >= 0:
        return idx
    key = _norm_label_key(name)
    if not key:
        return -1
    best_i = -1
    best_len = 0
    for i, it in enumerate(drop_items or []):
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "") or "")
        if label == "(不使用)":
            continue
        lk = _norm_label_key(label)
        if lk == key or (key in lk) or (lk in key):
            if len(label) > best_len:
                best_len = len(label)
                best_i = i
    if best_i >= 0:
        return best_i
    return find_tmpl_idx_by_keywords(
        drop_items,
        include_keywords=tuple(x for x in (name[:12],) if len(x) >= 2),
    )


def pick_2d_template_name(
    tmpl_list: List[dict],
    *,
    material: str,
    feature_type: str,
    role: str,
) -> Tuple[str, Optional[dict]]:
    """
    Pick best 2D template display name.

    Returns (name, meta) where meta may include knowledge basis.
    """
    mat = str(material or "AL6061").upper()
    ft = str(feature_type or "face").lower()
    role = str(role or "rough").lower()
    items = [x for x in (tmpl_list or []) if isinstance(x, dict)]

    db = get_db()
    kb = db.query_best_template(ft, mat, {})
    if kb and float(kb.get("confidence", 0) or 0) >= KNOWLEDGE_MIN_CONFIDENCE:
        kn = str(kb.get("template_name", "") or "").strip()
        if kn and _name_matches_2d_role(kn, role, ft):
            for it in items:
                if str(it.get("name", "")) == kn:
                    return kn, {**kb, "source": "knowledge"}
            # 學習名在清單中模糊找
            for it in items:
                if _norm_label_key(it.get("name", "")) == _norm_label_key(kn):
                    return str(it.get("name", kn)), {**kb, "source": "knowledge_fuzzy"}

    best_name = "(不使用)"
    best_score = -1.0
    for it in items:
        nm = str(it.get("name", "") or "").strip()
        sc = _score_2d_candidate(nm, role, ft)
        if sc > best_score:
            best_score = sc
            best_name = nm
    if best_score >= 0 and best_name != "(不使用)":
        return best_name, {"source": "keyword_score", "score": best_score}
    if items:
        nm = str(items[0].get("name", "(不使用)"))
        return nm, {"source": "first_available"}
    return "(不使用)", None


def build_recommended_2d_templates(
    material: str,
    *,
    top_face_rough_map: Optional[List[dict]] = None,
    top_face_finish_map: Optional[List[dict]] = None,
    profile_rough_map: Optional[List[dict]] = None,
    profile_finish_map: Optional[List[dict]] = None,
    contour_2d_recognition: Optional[dict] = None,
) -> Dict[str, Any]:
    """Build recommended_templates dict with knowledge + scored picks."""
    mat = str(material or "AL6061").upper()
    out: Dict[str, Any] = {}
    meta: Dict[str, Any] = {}

    recognized = {}
    c2d_tmpl = {}
    if isinstance(contour_2d_recognition, dict):
        recognized = contour_2d_recognition.get("recognized") or {}
        c2d_tmpl = contour_2d_recognition.get("recommended_templates") or {}

    specs = (
        ("topFaceRough", "face", "rough", top_face_rough_map or [], "top_face"),
        ("topFaceFinish", "face", "finish", top_face_finish_map or [], "top_face"),
        ("profileRough", "profile", "rough", profile_rough_map or [], "outer_contour"),
        ("profileFinish", "profile", "finish", profile_finish_map or [], "outer_contour"),
    )
    for key, ft, role, lst, rec_flag in specs:
        if contour_2d_recognition is not None and not recognized.get(rec_flag):
            out[key] = "(不使用)"
            meta[key] = {"source": "contour_2d_skip", "reason": "not_recognized"}
            continue
        c2d_name = str(c2d_tmpl.get(key, "") or "").strip()
        if c2d_name and c2d_name != "(不使用)":
            out[key] = c2d_name
            meta[key] = {"source": "contour_2d_recognition"}
            continue
        name, m = pick_2d_template_name(lst, material=mat, feature_type=ft, role=role)
        out[key] = name
        if m:
            meta[key] = m
    return {"templates": out, "picker_meta": meta}


def enrich_plan_with_template_params(
    ai_plan: dict,
    material: str,
    *,
    top_face_rough_map: Optional[List[dict]] = None,
    top_face_finish_map: Optional[List[dict]] = None,
    profile_rough_map: Optional[List[dict]] = None,
    profile_finish_map: Optional[List[dict]] = None,
) -> None:
    """Attach sampled CAM template parameters (pitch, bottom height, etc.) to AI decisions."""
    if not ai_plan:
        return
    try:
        from smart_ai_cam_machining.operation_builder import getTemplateParams
        from .template_resolver import resolve_template_url
    except Exception:
        return

    mat = str(material or "AL6061").upper()
    rec = ai_plan.get("recommended_templates") or {}
    hints: Dict[str, Any] = {}

    specs = (
        ("topFaceRough", "face", "rough", top_face_rough_map or [], "top_face"),
        ("topFaceFinish", "face", "finish", top_face_finish_map or [], "top_face"),
        ("profileRough", "profile", "rough", profile_rough_map or [], "outer_contour"),
        ("profileFinish", "profile", "finish", profile_finish_map or [], "outer_contour"),
    )
    for key, ft, role, lst, decision_key in specs:
        name = str(rec.get(key, "") or "").strip()
        if not name or name == "(不使用)":
            continue
        url = resolve_template_url(mat, name, feature_hint=ft)
        if not url:
            picked, _ = pick_2d_template_name(lst, material=mat, feature_type=ft, role=role)
            if picked and picked != "(不使用)":
                url = resolve_template_url(mat, picked, feature_hint=ft)
        if not url:
            continue
        params = getTemplateParams(url) or {}
        if not params:
            continue
        hints[key] = {"template_name": name, "params": params}
        dec = (ai_plan.get("decisions") or {}).get(decision_key)
        if isinstance(dec, dict):
            dec["template_params_hint"] = dict(params)
            dec["template_source"] = name

    if hints:
        ai_plan["template_params_hints"] = hints


def enhance_recommended_templates_with_knowledge(
    recommended: dict,
    material: str,
    *,
    top_face_rough_map: Optional[List[dict]] = None,
    top_face_finish_map: Optional[List[dict]] = None,
    profile_rough_map: Optional[List[dict]] = None,
    profile_finish_map: Optional[List[dict]] = None,
) -> dict:
    """Merge knowledge-aware 2D picks into recommended_templates (in place)."""
    if recommended is None:
        recommended = {}
    built = build_recommended_2d_templates(
        material,
        top_face_rough_map=top_face_rough_map,
        top_face_finish_map=top_face_finish_map,
        profile_rough_map=profile_rough_map,
        profile_finish_map=profile_finish_map,
    )
    picks = built.get("templates") or {}
    for k, v in picks.items():
        if v and v != "(不使用)":
            recommended[k] = v
    recommended["_picker_meta"] = built.get("picker_meta")
    return recommended
