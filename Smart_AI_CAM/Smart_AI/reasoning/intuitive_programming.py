# -*- coding: utf-8 -*-
"""
直覺式編程（Intuitive Programming）— 短期產品路線。

在限定範圍內：掃描／看懂零件 → 僅從已設定之頂面／外輪廓／孔等模板選用 →
經既有 execute 契約綁定並可觸發刀路。不發明新工序、不覆寫孔 baseline。

使用層分「直覺式／思考式」；學習層（概念、KnowledgeDB）兩者共用且持續運作。
見 docs/PROGRAMMING_MODES.md、docs/AI_SYSTEM_ARCHITECTURE.md §7。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from smart_ai_cam_state.runtime_state import state as runtime_state

from .programming_modes import MODE_INTUITIVE, mode_display_name, usage_tier_for_mode

PROGRAMMING_MODE = MODE_INTUITIVE

# 簡單雙面件白名單（可隨店規調整）
INTUITIVE_MAX_OFFICIAL_SLOT = 0
INTUITIVE_MAX_OFFICIAL_POCKET_SLOT = 0
INTUITIVE_MAX_POCKET_CORNER_R = 0
INTUITIVE_MAX_SLOTS = 24
INTUITIVE_MAX_HOLES = 256
INTUITIVE_MAX_FLAT_PLANES = 4

THINKING_L1_MAX_POCKET_CORNER_R = 8
THINKING_L1_MAX_OFFICIAL_SLOT = 6
THINKING_L1_MAX_OFFICIAL_POCKET_SLOT = 6


def _limits_for_profile(profile: str) -> dict:
    p = str(profile or "intuitive").strip().lower()
    if p in ("thinking_l1", "l1", "l1_extended_features"):
        return {
            "max_official_slot": THINKING_L1_MAX_OFFICIAL_SLOT,
            "max_official_pocket_slot": THINKING_L1_MAX_OFFICIAL_POCKET_SLOT,
            "max_pocket_corner_r": THINKING_L1_MAX_POCKET_CORNER_R,
            "max_slots": INTUITIVE_MAX_SLOTS,
            "max_holes": INTUITIVE_MAX_HOLES,
            "max_flat_planes": INTUITIVE_MAX_FLAT_PLANES,
            "allow_catalog_official_pocket": True,
        }
    return {
        "max_official_slot": INTUITIVE_MAX_OFFICIAL_SLOT,
        "max_official_pocket_slot": INTUITIVE_MAX_OFFICIAL_POCKET_SLOT,
        "max_pocket_corner_r": INTUITIVE_MAX_POCKET_CORNER_R,
        "max_slots": INTUITIVE_MAX_SLOTS,
        "max_holes": INTUITIVE_MAX_HOLES,
        "max_flat_planes": INTUITIVE_MAX_FLAT_PLANES,
        "allow_catalog_official_pocket": False,
    }


def _check(
    checks: List[dict],
    check_id: str,
    ok: bool,
    message: str,
    *,
    detail: Optional[dict] = None,
) -> bool:
    entry = {"id": check_id, "ok": bool(ok), "message": message}
    if detail:
        entry["detail"] = detail
    checks.append(entry)
    return bool(ok)


def _template_lists_configured(material: str, ctx: dict) -> bool:
    tf_r = (ctx.get("top_face_rough_map") or {}).get(material) or []
    tf_f = (ctx.get("top_face_finish_map") or {}).get(material) or []
    pf_r = (ctx.get("profile_rough_map") or {}).get(material) or []
    pf_f = (ctx.get("profile_finish_map") or {}).get(material) or []
    has_top = bool(tf_r or tf_f)
    has_profile = bool(pf_r or pf_f)
    return has_top or has_profile


def _refresh_2d_scan_pipeline(ctx: dict) -> None:
    """階段 A：直覺式／AI 建議前刷新 2D 辨識鏈（視線 → 特徵目錄 → 2D 輪廓）。"""
    refresh_vision = ctx.get("refresh_vision")
    if callable(refresh_vision):
        try:
            refresh_vision()
        except Exception:
            pass
    refresh_cat = ctx.get("refresh_feature_catalog")
    if callable(refresh_cat):
        try:
            refresh_cat()
        except Exception:
            pass
    refresh_c2d = ctx.get("refresh_contour_2d")
    if callable(refresh_c2d):
        try:
            refresh_c2d()
        except Exception:
            pass


def _template_map_names(items: List[Any]) -> List[str]:
    out: List[str] = []
    for x in items or []:
        if isinstance(x, dict):
            nm = str(x.get("name", "") or "").strip()
        else:
            nm = str(x or "").strip()
        if nm:
            out.append(nm)
    return out


def _template_name_in_map(name: str, items: List[Any]) -> bool:
    key = str(name or "").strip()
    if not key or key == "(不使用)":
        return True
    key_l = key.lower()
    for nm in _template_map_names(items):
        nl = nm.lower()
        if key_l == nl or key_l in nl or nl in key_l:
            return True
    return False


def _contour_2d_summary_from_state() -> dict:
    c2d = getattr(runtime_state, "contour_2d_recognition", None) or {}
    if not isinstance(c2d, dict):
        return {"ok": False}
    try:
        from Smart_AI.perception import contour_2d_recognizer as c2d_mod

        return c2d_mod.recognition_summary_for_init(c2d)
    except Exception:
        rec = c2d.get("recognized") or {}
        return {
            "ok": True,
            "top_face": bool(rec.get("top_face")),
            "outer_contour": bool(rec.get("outer_contour")),
            "recommended_templates": dict(c2d.get("recommended_templates") or {}),
            "summary_text": str(c2d.get("summary_text", "") or ""),
        }


def collect_part_snapshot(material: str, ctx: dict) -> dict:
    """Read-only scan snapshot for eligibility (no AI)."""
    rebuild = ctx.get("rebuild_holes")
    if callable(rebuild):
        rebuild(force=True)

    _refresh_2d_scan_pipeline(ctx)

    holes = ctx["build_hole_data"](material)
    slots = ctx["build_slot_data"](material)
    pcr = ctx["build_pocket_corner_r_data"](material)

    refresh_fusion = ctx.get("refresh_fusion_official")
    if callable(refresh_fusion):
        try:
            refresh_fusion()
        except Exception:
            pass

    official_slots: List[dict] = []
    official_pockets: List[dict] = []
    build_slot = ctx.get("build_official_slot_pocket_data")
    build_pocket = ctx.get("build_official_pocket_slot_data")
    if callable(build_slot):
        try:
            official_slots = list(build_slot(material) or [])
        except Exception:
            official_slots = []
    if callable(build_pocket):
        try:
            official_pockets = list(build_pocket(material) or [])
        except Exception:
            official_pockets = []

    fusion_rec = getattr(runtime_state, "fusion_official_recognition", None) or {}
    feat_cat = getattr(runtime_state, "feature_catalog", None) or {}
    scan_flat = ctx.get("scan_flat_depths")
    flat_depths = {}
    if callable(scan_flat):
        try:
            flat_depths = scan_flat()
        except Exception:
            flat_depths = {}
    planes = list((flat_depths or {}).get("planes") or [])
    c2d_summary = _contour_2d_summary_from_state()

    try:
        from . import thinking_l2_plan as l2

        snapshot_base = {
            "material": material,
            "hole_count": len(holes or []),
            "slot_count": len(slots or []),
            "pocket_corner_r_count": len(pcr or []),
            "official_slot_count": len(official_slots),
            "official_pocket_slot_count": len(official_pockets),
            "flat_plane_count": len(planes),
            "fusion_official": fusion_rec,
            "feature_catalog": feat_cat,
            "flat_depths": flat_depths,
            "contour_2d": c2d_summary,
            "templates_configured": _template_lists_configured(material, ctx),
        }
        return l2.enrich_snapshot_with_hole_sides(snapshot_base, holes)
    except Exception:
        pass

    return {
        "material": material,
        "hole_count": len(holes or []),
        "slot_count": len(slots or []),
        "pocket_corner_r_count": len(pcr or []),
        "official_slot_count": len(official_slots),
        "official_pocket_slot_count": len(official_pockets),
        "flat_plane_count": len(planes),
        "fusion_official": fusion_rec,
        "feature_catalog": feat_cat,
        "flat_depths": flat_depths,
        "contour_2d": c2d_summary,
        "templates_configured": _template_lists_configured(material, ctx),
    }


def evaluate_intuitive_eligibility(
    snapshot: dict,
    *,
    material: Optional[str] = None,
    ctx: Optional[dict] = None,
    limits_profile: str = "intuitive",
) -> dict:
    """
    Returns eligibility dict: eligible, programming_mode, checks[], summary, snapshot.
    """
    checks: List[dict] = []
    mat = material or snapshot.get("material") or "AL6061"
    lim = _limits_for_profile(limits_profile)

    all_ok = True
    all_ok &= _check(
        checks,
        "templates_configured",
        bool(snapshot.get("templates_configured")),
        "材質「{}」已設定頂面或外輪廓模板路徑（設定頁）".format(mat)
        if snapshot.get("templates_configured")
        else "材質「{}」缺少頂面／外輪廓模板（請於設定指定資料夾）".format(mat),
    )

    n_holes = int(snapshot.get("hole_count", 0) or 0)
    max_holes = int(lim["max_holes"])
    all_ok &= _check(
        checks,
        "hole_count",
        0 < n_holes <= max_holes,
        "圓孔列 {} 筆（允許 1～{}）".format(n_holes, max_holes),
        detail={"count": n_holes},
    )

    n_slot = int(snapshot.get("slot_count", 0) or 0)
    max_slots = int(lim["max_slots"])
    all_ok &= _check(
        checks,
        "slot_count",
        n_slot <= max_slots,
        "槽列 {} 筆（上限 {}）".format(n_slot, max_slots),
        detail={"count": n_slot},
    )

    n_pcr = int(snapshot.get("pocket_corner_r_count", 0) or 0)
    max_pcr = int(lim["max_pocket_corner_r"])
    all_ok &= _check(
        checks,
        "pocket_corner_r",
        n_pcr <= max_pcr,
        "口袋 R 列 {} 筆（上限 {}）".format(n_pcr, max_pcr),
        detail={"count": n_pcr},
    )

    n_os = int(snapshot.get("official_slot_count", 0) or 0)
    max_os = int(lim["max_official_slot"])
    all_ok &= _check(
        checks,
        "official_slot",
        n_os <= max_os,
        "官方長條孔 {} 筆（上限 {}）".format(n_os, max_os),
        detail={"count": n_os},
    )

    n_op = int(snapshot.get("official_pocket_slot_count", 0) or 0)
    max_op = int(lim["max_official_pocket_slot"])
    all_ok &= _check(
        checks,
        "official_pocket_slot",
        n_op <= max_op,
        "官方口袋槽 {} 筆（上限 {}）".format(n_op, max_op),
        detail={"count": n_op},
    )

    n_planes = int(snapshot.get("flat_plane_count", 0) or 0)
    max_planes = int(lim["max_flat_planes"])
    all_ok &= _check(
        checks,
        "flat_planes",
        n_planes <= max_planes,
        "朝上平面 {} 層（上限 {}，過多階台請改用手動面板）".format(
            n_planes, max_planes
        ),
        detail={"count": n_planes},
    )

    cat = snapshot.get("feature_catalog") or {}
    counts = dict(cat.get("counts_by_category") or {})
    off_pocket_cat = int(counts.get("official_pocket", 0) or 0)
    if off_pocket_cat > 0 and not lim.get("allow_catalog_official_pocket"):
        all_ok &= _check(
            checks,
            "catalog_official_pocket",
            False,
            "特徵目錄含官方口袋 {} 件（超出直覺式範圍）".format(off_pocket_cat),
        )
    elif off_pocket_cat > 0:
        _check(
            checks,
            "catalog_official_pocket",
            True,
            "特徵目錄含官方口袋 {} 件（思考式 L1 允許）".format(off_pocket_cat),
        )
    else:
        _check(checks, "catalog_official_pocket", True, "特徵目錄無額外官方口袋項")

    c2d = snapshot.get("contour_2d") or {}
    rec2d = c2d if c2d.get("ok") else {}
    has_top_rec = bool(rec2d.get("top_face"))
    has_prof_rec = bool(rec2d.get("outer_contour"))
    c2d_tmpl = dict(rec2d.get("recommended_templates") or {})

    if has_top_rec and ctx:
        tf_r = (ctx.get("top_face_rough_map") or {}).get(mat) or []
        tf_f = (ctx.get("top_face_finish_map") or {}).get(mat) or []
        rough_nm = c2d_tmpl.get("topFaceRough", "(不使用)")
        finish_nm = c2d_tmpl.get("topFaceFinish", "(不使用)")
        top_ok = True
        if rough_nm and rough_nm != "(不使用)":
            top_ok &= _template_name_in_map(rough_nm, tf_r)
        if finish_nm and finish_nm != "(不使用)":
            top_ok &= _template_name_in_map(finish_nm, tf_f)
        all_ok &= _check(
            checks,
            "top_face_2d_templates",
            top_ok,
            "面銑：辨識到頂面，模板「{}／{}」可在本機庫解析".format(rough_nm, finish_nm)
            if top_ok
            else "面銑：辨識到頂面，但建議模板不在 topFace 映射中（請檢查設定路徑）",
            detail={"rough": rough_nm, "finish": finish_nm},
        )
    elif has_top_rec:
        _check(
            checks,
            "top_face_2d_templates",
            True,
            "面銑：已辨識頂面（略過模板解析細檢，無映射上下文）",
        )
    else:
        _check(checks, "top_face_2d_templates", True, "面銑：未辨識到需面銑的頂面（略過 2D 面銑檢查）")

    if has_prof_rec and ctx:
        pf_r = (ctx.get("profile_rough_map") or {}).get(mat) or []
        pf_f = (ctx.get("profile_finish_map") or {}).get(mat) or []
        rough_nm = c2d_tmpl.get("profileRough", "(不使用)")
        finish_nm = c2d_tmpl.get("profileFinish", "(不使用)")
        prof_ok = True
        if rough_nm and rough_nm != "(不使用)":
            prof_ok &= _template_name_in_map(rough_nm, pf_r)
        if finish_nm and finish_nm != "(不使用)":
            prof_ok &= _template_name_in_map(finish_nm, pf_f)
        all_ok &= _check(
            checks,
            "outer_contour_2d_templates",
            prof_ok,
            "外輪廓：辨識到輪廓，模板「{}／{}」可在本機庫解析".format(rough_nm, finish_nm)
            if prof_ok
            else "外輪廓：辨識到輪廓，但建議模板不在 profile 映射中（請檢查設定路徑）",
            detail={"rough": rough_nm, "finish": finish_nm},
        )
    elif has_prof_rec:
        _check(
            checks,
            "outer_contour_2d_templates",
            True,
            "外輪廓：已辨識輪廓（略過模板解析細檢，無映射上下文）",
        )
    else:
        _check(
            checks,
            "outer_contour_2d_templates",
            True,
            "外輪廓：特徵不足或未啟用視線法（略過 2D 外輪廓檢查）",
        )

    if all_ok:
        extra_2d = ""
        if has_top_rec or has_prof_rec:
            parts = []
            if has_top_rec:
                parts.append("面銑")
            if has_prof_rec:
                parts.append("外輪廓")
            extra_2d = "；2D：" + "＋".join(parts)
        summary = (
            "【直覺式編程】資格通過：{} 孔、{} 槽{}；將使用已定製模板（先2D後3D）。"
        ).format(n_holes, n_slot, extra_2d)
    else:
        failed = [c["message"] for c in checks if not c.get("ok")]
        summary = "【直覺式編程】資格未通過：" + "；".join(failed[:4])
        if len(failed) > 4:
            summary += "…（共 {} 項）".format(len(failed))

    return {
        "programming_mode": PROGRAMMING_MODE,
        "usage_tier": usage_tier_for_mode(PROGRAMMING_MODE),
        "mode_display": mode_display_name(PROGRAMMING_MODE),
        "eligible": bool(all_ok),
        "checks": checks,
        "summary": summary,
        "snapshot": snapshot,
        "limits": dict(lim),
        "limits_profile": str(limits_profile or "intuitive"),
    }


def validate_panel_apply_for_intuitive(
    panel_apply: dict,
    holes_panel: List[dict],
    slots_panel: List[dict],
    pocket_corner_r_panel: Optional[List[dict]] = None,
) -> dict:
    """Ensure every suggested row maps to a real template index."""
    issues: List[str] = []
    panel_apply = panel_apply or {}
    pocket_corner_r_panel = pocket_corner_r_panel or []

    for pr in panel_apply.get("hole_rows") or []:
        if not isinstance(pr, dict) or "idx" not in pr:
            continue
        idx = int(pr["idx"])
        tmpl_idx = int(pr.get("tmplIdx", -1))
        if idx < 0 or idx >= len(holes_panel):
            issues.append("孔列 idx={} 超出範圍".format(idx))
            continue
        items = (holes_panel[idx] or {}).get("dropItems") or []
        if tmpl_idx < 0 or tmpl_idx >= len(items):
            issues.append("孔列 #{} 無可用模板（tmplIdx={}）".format(idx + 1, tmpl_idx))

    for pr in panel_apply.get("slot_rows") or []:
        if not isinstance(pr, dict) or "idx" not in pr:
            continue
        idx = int(pr["idx"])
        tmpl_idx = int(pr.get("tmplIdx", -1))
        if idx < 0 or idx >= len(slots_panel):
            issues.append("槽列 idx={} 超出範圍".format(idx))
            continue
        items = (slots_panel[idx] or {}).get("dropItems") or []
        if tmpl_idx < 0 or tmpl_idx >= len(items):
            issues.append("槽列 #{} 無可用模板（tmplIdx={}）".format(idx + 1, tmpl_idx))

    for pr in panel_apply.get("pocket_corner_r_rows") or []:
        if not isinstance(pr, dict) or "idx" not in pr:
            continue
        idx = int(pr["idx"])
        tmpl_idx = int(pr.get("tmplIdx", -1))
        if idx < 0 or idx >= len(pocket_corner_r_panel):
            issues.append("口袋 R idx={} 超出範圍".format(idx))
            continue
        items = (pocket_corner_r_panel[idx] or {}).get("dropItems") or []
        if tmpl_idx < 0 or tmpl_idx >= len(items):
            issues.append("口袋 R #{} 無可用模板".format(idx + 1))

    return {"ok": len(issues) == 0, "issues": issues}


def validate_ai_recommendations_for_execute(
    ai_data: dict,
    ctx: dict,
    material: str,
) -> dict:
    """Panel + 2D template validation shared by intuitive and L2 execute paths."""
    holes_panel = ctx["build_hole_data"](material)
    slots_panel = ctx["build_slot_data"](material)
    pcr_panel = ctx["build_pocket_corner_r_data"](material)
    panel_apply = ai_data.get("panel_apply") or {}
    validation = validate_panel_apply_for_intuitive(
        panel_apply, holes_panel, slots_panel, pcr_panel
    )
    validation_2d = validate_2d_templates_for_intuitive(ai_data, ctx, material)
    issues = list(validation.get("issues") or []) + list(validation_2d.get("issues") or [])
    ok = bool(validation.get("ok")) and bool(validation_2d.get("ok"))
    return {
        "ok": ok,
        "issues": issues,
        "validation": validation,
        "validation_2d": validation_2d,
    }


def validate_2d_templates_for_intuitive(
    ai_data: dict,
    ctx: dict,
    material: str,
) -> dict:
    """Ensure recommended 2D template names resolve in loaded maps before execute."""
    issues: List[str] = []
    mat = str(material or "AL6061")
    rec = dict(ai_data.get("recommended_templates") or {})
    c2d = ai_data.get("contour_2d_recognition") or {}
    recognized = (c2d.get("recognized") or {}) if isinstance(c2d, dict) else {}

    tf_r = (ctx.get("top_face_rough_map") or {}).get(mat) or []
    tf_f = (ctx.get("top_face_finish_map") or {}).get(mat) or []
    pf_r = (ctx.get("profile_rough_map") or {}).get(mat) or []
    pf_f = (ctx.get("profile_finish_map") or {}).get(mat) or []

    pairs = (
        ("topFaceRough", tf_r, "top_face", "面銑粗"),
        ("topFaceFinish", tf_f, "top_face", "面銑精"),
        ("profileRough", pf_r, "outer_contour", "外輪廓粗"),
        ("profileFinish", pf_f, "outer_contour", "外輪廓精"),
    )
    for key, items, rec_flag, label in pairs:
        nm = str(rec.get(key, "(不使用)") or "(不使用)").strip()
        if nm == "(不使用)" or not nm:
            continue
        if recognized and not recognized.get(rec_flag):
            continue
        if not _template_name_in_map(nm, items):
            issues.append("{}：建議模板「{}」不在本機映射中".format(label, nm))

    cc_nm = str(rec.get("contourChamfer", "(不使用)") or "(不使用)").strip()
    if cc_nm and cc_nm != "(不使用)":
        chamfer_fn = ctx.get("contour_chamfer_names")
        cc_names = chamfer_fn(mat) if callable(chamfer_fn) else []
        cc_items = [{"name": n} for n in cc_names]
        chamfer_n = int(
            ((ai_data.get("feature_catalog_summary") or {}).get("counts_by_category") or {}).get(
                "chamfer_bevel", 0
            )
            or 0
        )
        if not chamfer_n:
            chamfer_n = int((ai_data.get("decisions") or {}).get("chamfer_bevel", {}).get("count", 0) or 0)
        if chamfer_n > 0 and cc_items and not _template_name_in_map(cc_nm, cc_items):
            issues.append("輪廓倒角：建議模板「{}」不在 contourChamfer 映射中".format(cc_nm))

    return {"ok": len(issues) == 0, "issues": issues}


def build_execute_plan_from_ai(
    ai_data: dict,
    *,
    setup_name: str,
    material: str,
    programming_mode: Optional[str] = None,
    thinking_layer: str = "",
) -> dict:
    """Palette execute payload — same contract as run_internal_ai_autopilot."""
    mode = str(programming_mode or PROGRAMMING_MODE).strip().lower() or PROGRAMMING_MODE
    panel = ai_data.get("panel_apply") or {}
    rec = ai_data.get("recommended_templates") or {}
    hole_rows = []
    for pr in panel.get("hole_rows") or []:
        if isinstance(pr, dict):
            hole_rows.append({"idx": pr.get("idx"), "tmplIdx": pr.get("tmplIdx", 0)})

    slot_rows = [
        r for r in (panel.get("slot_rows") or [])
        if isinstance(r, dict) and not r.get("skip_execute")
    ]
    pcr_rows = [
        r for r in (panel.get("pocket_corner_r_rows") or [])
        if isinstance(r, dict)
        and not r.get("skip_execute")
        and int(r.get("tmplIdx", -1)) >= 0
    ]
    terrace_ops = panel.get("terrace_face_ops") or rec.get("terrace_face_ops") or []

    plan = {
        "setup": setup_name or "",
        "material": material,
        "topFaceRough": rec.get("topFaceRough", "(不使用)"),
        "topFaceFinish": rec.get("topFaceFinish", "(不使用)"),
        "profileRough": rec.get("profileRough", "(不使用)"),
        "profileFinish": rec.get("profileFinish", "(不使用)"),
        "contourChamfer": rec.get("contourChamfer", "(不使用)"),
        "terraceFaceOps": terrace_ops,
        "rows": hole_rows,
        "slotRows": slot_rows,
        "pocketCornerRRows": pcr_rows,
        "mode": "all",
        "programming_mode": mode,
        "usage_tier": usage_tier_for_mode(mode),
    }
    try:
        from Smart_AI.reasoning.cam_depth_plan import attach_cam_depth_to_execute_plan

        flat_depths = ai_data.get("flat_depths")
        if not flat_depths:
            snap = ai_data.get("snapshot") or {}
            flat_depths = snap.get("flat_depths")
        if ai_data.get("cam_depth_context"):
            plan["camDepthContext"] = ai_data["cam_depth_context"]
        elif panel.get("cam_depth_context"):
            plan["camDepthContext"] = panel["cam_depth_context"]
        plan = attach_cam_depth_to_execute_plan(plan, flat_depths=flat_depths)
    except Exception:
        pass
    if thinking_layer:
        plan["thinking_layer"] = thinking_layer
        plan["seed_mode"] = PROGRAMMING_MODE
        if thinking_layer == "L1_extended_features":
            plan["officialSlotPocketRows"] = panel.get("official_slot_pocket_rows") or []
            plan["officialPocketSlotRows"] = panel.get("official_pocket_slot_rows") or []
    return plan


def format_eligibility_report(eligibility: dict) -> str:
    lines = [eligibility.get("summary") or "", ""]
    for c in eligibility.get("checks") or []:
        mark = "✓" if c.get("ok") else "✗"
        lines.append("{} {}".format(mark, c.get("message", "")))
    lines.append("")
    lines.append(
        "說明：直覺式＝使用層「有限制的編程」；掃描與執行仍會寫入學習庫（編程概念持續累積）。"
        "思考式＝開放式編程（長期產品線）。翻面仍須人工。詳見 docs/PROGRAMMING_MODES.md。"
    )
    return "\n".join(lines)


def run_intuitive_one_click(
    params: dict,
    ctx: dict,
    *,
    get_recommendations: Callable[[dict, dict], dict],
    execute_from_palette: Optional[Callable[[dict], None]] = None,
    ensure_cam_setup: Optional[Callable[[], dict]] = None,
    ensure_template_maps: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    P0 一鍵直覺式：模板就緒 → 重建掃描 → 資格 → 建議 → 驗證 → 執行（單一入口）。
    """
    if callable(ensure_template_maps):
        try:
            ensure_template_maps()
        except Exception:
            pass

    banner = (
        "【一鍵直覺式編程】\n"
        "步驟：模板檢查 → 掃描孔／槽／輪廓 → 直覺式資格 → 套用已定模板 → 執行（先2D後3D）。\n"
        "不通過資格將不執行。詳見 docs/INTUITIVE_VALIDATION_PARTS.md。"
    )
    return run_intuitive_programming(
        params,
        ctx,
        get_recommendations=get_recommendations,
        execute_from_palette=execute_from_palette,
        ensure_cam_setup=ensure_cam_setup,
        programming_mode=PROGRAMMING_MODE,
        report_banner=banner,
    )


def run_check_intuitive_eligibility(params: dict, ctx: dict) -> dict:
    material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
    runtime_state.current_material = material
    try:
        snapshot = collect_part_snapshot(material, ctx)
        eligibility = evaluate_intuitive_eligibility(snapshot, material=material, ctx=ctx)
        eligibility["report_text"] = format_eligibility_report(eligibility)
        return {"success": True, "data": eligibility}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_intuitive_programming(
    params: dict,
    ctx: dict,
    *,
    get_recommendations: Callable[[dict, dict], dict],
    execute_from_palette: Optional[Callable[[dict], None]] = None,
    ensure_cam_setup: Optional[Callable[[], dict]] = None,
    programming_mode: Optional[str] = None,
    report_banner: str = "",
    thinking_layer: str = "",
) -> dict:
    """
    Eligibility gate → get_ai_recommendations → validate panel_apply → optional execute.

    Shared pipeline for intuitive mode; thinking L0 calls this with programming_mode=thinking.
    """
    mode = str(programming_mode or PROGRAMMING_MODE).strip().lower() or PROGRAMMING_MODE
    material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
    do_execute = bool(params.get("execute", True))
    runtime_state.current_material = material

    limits_profile = str(
        params.get("limits_profile")
        or ("thinking_l1" if thinking_layer == "L1_extended_features" else "intuitive")
    ).strip()

    snapshot = collect_part_snapshot(material, ctx)
    eligibility = evaluate_intuitive_eligibility(
        snapshot, material=material, ctx=ctx, limits_profile=limits_profile
    )
    eligibility["programming_mode"] = mode
    eligibility["usage_tier"] = usage_tier_for_mode(mode)
    if thinking_layer:
        eligibility["thinking_layer"] = thinking_layer
        eligibility["seed_mode"] = PROGRAMMING_MODE
    eligibility["report_text"] = format_eligibility_report(eligibility)
    if report_banner:
        eligibility["report_text"] = report_banner + "\n\n" + eligibility["report_text"]

    if not eligibility.get("eligible"):
        return {
            "success": False,
            "error": eligibility.get("summary", "直覺式編程資格未通過"),
            "data": {
                "programming_mode": mode,
                "thinking_layer": thinking_layer or None,
                "seed_mode": PROGRAMMING_MODE if thinking_layer else None,
                "eligibility": eligibility,
                "executed": False,
            },
        }

    if do_execute and callable(ensure_cam_setup):
        setup_res = ensure_cam_setup()
        if not setup_res.get("success"):
            return {
                "success": False,
                "error": setup_res.get("error", "無法建立 CAM Setup"),
                "data": {"eligibility": eligibility, "executed": False},
            }

    rec_res = get_recommendations(
        {**params, "material": material, "thinking_layer": thinking_layer or params.get("thinking_layer", "")},
        ctx,
    )
    if not rec_res.get("success"):
        return rec_res

    ai_data = rec_res.get("data") or {}
    combined_validation = validate_ai_recommendations_for_execute(ai_data, ctx, material)
    validation = combined_validation.get("validation") or {}
    validation_2d = combined_validation.get("validation_2d") or {}
    if not combined_validation.get("ok"):
        msg = "模板建議無法全部對應：" + "；".join(combined_validation.get("issues") or [])
        if validation.get("issues") and not validation.get("ok"):
            msg = "模板建議無法全部對應到面板下拉：" + "；".join(validation.get("issues") or [])
        elif validation_2d.get("issues") and not validation_2d.get("ok"):
            msg = "2D 模板建議無法在本機庫解析：" + "；".join(validation_2d.get("issues") or [])
        return {
            "success": False,
            "error": msg,
            "data": {
                "programming_mode": mode,
                "thinking_layer": thinking_layer or None,
                "eligibility": eligibility,
                "validation": validation,
                "ai_plan": ai_data,
                "executed": False,
            },
        }

    setup_name = ""
    cam_setup = ctx.get("cam_setup")
    if cam_setup is not None:
        try:
            setup_name = str(cam_setup.name)
        except Exception:
            setup_name = ""

    plan = build_execute_plan_from_ai(
        ai_data,
        setup_name=setup_name,
        material=material,
        programming_mode=mode,
        thinking_layer=thinking_layer,
    )

    report = (ai_data.get("overall_report") or "").strip()
    header = eligibility.get("summary", "") + "\n\n"
    if report_banner:
        header = report_banner + "\n\n" + header
    ai_data["intuitive_header"] = eligibility.get("summary", "")
    ai_data["programming_mode"] = mode
    ai_data["usage_tier"] = usage_tier_for_mode(mode)
    if thinking_layer:
        ai_data["thinking_layer"] = thinking_layer
        ai_data["seed_mode"] = PROGRAMMING_MODE
    ai_data["overall_report"] = header + report

    executed = False
    if do_execute and callable(execute_from_palette):
        execute_from_palette(plan)
        executed = True

    mode_label = mode_display_name(mode)
    return {
        "success": True,
        "message": "{}已套用建議".format(mode_label)
        + ("並觸發執行（先2D後3D）" if executed else "（未執行）"),
        "data": {
            "programming_mode": mode,
            "usage_tier": usage_tier_for_mode(mode),
            "thinking_layer": thinking_layer or None,
            "seed_mode": PROGRAMMING_MODE if thinking_layer else None,
            "eligibility": eligibility,
            "validation": validation,
            "validation_2d": validation_2d,
            "ai_plan": ai_data,
            "execute_plan": plan,
            "executed": executed,
            "report_text": ai_data.get("overall_report", ""),
        },
    }
