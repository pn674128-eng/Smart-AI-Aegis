# -*- coding: utf-8 -*-
"""
KnowledgeDB training: record executes, enhance recommendations, MCP handlers.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .ai_panel_apply import find_tmpl_idx_by_keywords
from Smart_AI.memory.knowledge_db import get_db

KNOWLEDGE_MIN_CONFIDENCE = 0.35


def find_tmpl_idx_by_label(drop_items: List[dict], template_name: str) -> int:
    """Match dropItems index by template display name (substring)."""
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


def _hole_geometry_for_db(hole_row: dict, fusion_hint: Optional[dict] = None) -> dict:
    fusion_hint = fusion_hint or {}
    dia = 0.0
    for key in ("dia", "diameter", "diameter_mm"):
        try:
            dia = float(hole_row.get(key, 0) or 0)
            if dia > 0:
                break
        except Exception:
            pass
    if dia <= 0:
        m = re.search(r"d\s*(\d+(?:\.\d+)?)", str(hole_row.get("label", "")), re.I)
        if m:
            try:
                dia = float(m.group(1))
            except Exception:
                pass
    depth = 0.0
    try:
        depth = float(hole_row.get("depth", hole_row.get("depth_mm", 0)) or 0)
    except Exception:
        pass
    if bool(hole_row.get("isCBLarge")) or bool(fusion_hint.get("prefer_countersink")):
        hole_type = "countersink"
    elif bool(hole_row.get("isThreaded")) or bool(fusion_hint.get("prefer_tap")):
        hole_type = "tap"
    else:
        hole_type = "general"
    return {"diameter_mm": dia, "depth_mm": depth, "hole_type": hole_type}


def _slot_geometry_for_db(slot_row: dict) -> dict:
    w = 0.0
    for key in ("width_mm", "width"):
        try:
            w = float(slot_row.get(key, 0) or 0)
            if w > 0:
                break
        except Exception:
            pass
    if w <= 0:
        td = str(slot_row.get("tool_dia", "") or "")
        m = re.search(r"(\d+(?:\.\d+)?)", td)
        if m:
            try:
                w = float(m.group(1))
            except Exception:
                pass
    return {"width_mm": w}


def _template_label_from_row(panel_row: dict, info_list: List[dict]) -> str:
    idx = int(panel_row.get("idx", 0))
    tmpl_idx = int(panel_row.get("tmplIdx", 0))
    info = (info_list or [])[idx] if 0 <= idx < len(info_list or []) else {}
    items = info.get("dropItems") or []
    if 0 <= tmpl_idx < len(items) and isinstance(items[tmpl_idx], dict):
        return str(items[tmpl_idx].get("label", "") or "")
    return ""


def _resolve_tmpl_idx(items: List[dict], template_name: str) -> int:
    try:
        from .ai_template_picker import find_tmpl_idx_fuzzy

        return find_tmpl_idx_fuzzy(items, template_name)
    except Exception:
        return find_tmpl_idx_by_label(items, template_name)


def enhance_panel_apply_with_knowledge(
    panel_apply: dict,
    holes_data: List[dict],
    slots_data: List[dict],
    pocket_corner_r_data: Optional[List[dict]],
    material: str,
    *,
    top_face_rough_map: Optional[List[dict]] = None,
    top_face_finish_map: Optional[List[dict]] = None,
    profile_rough_map: Optional[List[dict]] = None,
    profile_finish_map: Optional[List[dict]] = None,
) -> None:
    """Override tmplIdx when KnowledgeDB has high-confidence history."""
    if not panel_apply:
        return
    db = get_db()
    mat = str(material or "AL6061").upper()

    for pr in panel_apply.get("hole_rows") or []:
        if not isinstance(pr, dict):
            continue
        idx = int(pr.get("idx", -1))
        if idx < 0 or idx >= len(holes_data or []):
            continue
        h = holes_data[idx]
        items = h.get("dropItems") or []
        geom = _hole_geometry_for_db(h)
        best = db.query_best_template("hole", mat, geom)
        if not best or float(best.get("confidence", 0)) < KNOWLEDGE_MIN_CONFIDENCE:
            continue
        tidx = _resolve_tmpl_idx(items, best.get("template_name", ""))
        if tidx < 0:
            try:
                from .template_resolver import resolve_template_entry

                ent = resolve_template_entry(mat, best.get("template_name", ""), feature_hint="hole")
                if ent and ent.get("name"):
                    tidx = _resolve_tmpl_idx(items, ent["name"])
            except Exception:
                pass
        if tidx < 0:
            continue
        pr["tmplIdx"] = tidx
        pr["knowledge_confidence"] = round(float(best.get("confidence", 0) or 0), 4)
        pr["knowledge_basis"] = best.get("basis", best.get("template_name", ""))
        pr["reason"] = "{} | 📚學習庫：{}".format(
            pr.get("reason", ""),
            best.get("basis", best.get("template_name", "")),
        ).strip(" |")

    for pr in panel_apply.get("slot_rows") or []:
        if not isinstance(pr, dict):
            continue
        idx = int(pr.get("idx", -1))
        if idx < 0 or idx >= len(slots_data or []):
            continue
        s = slots_data[idx]
        items = s.get("dropItems") or []
        geom = _slot_geometry_for_db(s)
        best = db.query_best_template("slot", mat, geom)
        if not best or float(best.get("confidence", 0)) < KNOWLEDGE_MIN_CONFIDENCE:
            continue
        tidx = _resolve_tmpl_idx(items, best.get("template_name", ""))
        if tidx < 0:
            try:
                from .template_resolver import resolve_template_entry

                ent = resolve_template_entry(mat, best.get("template_name", ""), feature_hint="slot")
                if ent and ent.get("name"):
                    tidx = _resolve_tmpl_idx(items, ent["name"])
            except Exception:
                pass
        if tidx < 0:
            tidx = find_tmpl_idx_by_keywords(
                items,
                include_keywords=(best.get("template_name", ""),),
                prefer_has_slot=True,
            )
        if tidx >= 0:
            pr["tmplIdx"] = tidx
            pr["knowledge_confidence"] = round(float(best.get("confidence", 0) or 0), 4)
            pr["knowledge_basis"] = best.get("basis", "")
            pr["reason"] = "{} | 📚學習庫：{}".format(
                pr.get("reason", ""),
                best.get("basis", ""),
            ).strip(" |")

    for pr in panel_apply.get("pocket_corner_r_rows") or []:
        if not isinstance(pr, dict):
            continue
        idx = int(pr.get("idx", -1))
        pcr = pocket_corner_r_data or []
        if idx < 0 or idx >= len(pcr):
            continue
        row = pcr[idx]
        items = row.get("dropItems") or []
        try:
            r_mm = float(row.get("r_mm", row.get("r", 0)) or 0)
        except Exception:
            r_mm = 0.0
        geom = {"diameter_mm": r_mm * 2.0, "hole_type": "pocket_corner_r"}
        best = db.query_best_template("hole", mat, geom)
        if not best or float(best.get("confidence", 0)) < KNOWLEDGE_MIN_CONFIDENCE:
            continue
        tidx = _resolve_tmpl_idx(items, best.get("template_name", ""))
        if tidx >= 0:
            pr["tmplIdx"] = tidx
            pr["knowledge_confidence"] = round(float(best.get("confidence", 0) or 0), 4)
            pr["knowledge_basis"] = best.get("basis", best.get("template_name", ""))

    panel_apply["row_intelligence"] = _build_row_intelligence(panel_apply)

    try:
        from .ai_template_picker import enhance_recommended_templates_with_knowledge

        rec = panel_apply.setdefault("recommended_templates", {})
        enhance_recommended_templates_with_knowledge(
            rec,
            mat,
            top_face_rough_map=top_face_rough_map,
            top_face_finish_map=top_face_finish_map,
            profile_rough_map=profile_rough_map,
            profile_finish_map=profile_finish_map,
        )
        meta = rec.pop("_picker_meta", None)
        if meta and isinstance(meta, dict):
            notes = panel_apply.setdefault("notes", [])
            for k, m in meta.items():
                if isinstance(m, dict) and m.get("source", "").startswith("knowledge"):
                    notes.append("2D {}：學習庫 → {}".format(k, rec.get(k, "")))
    except Exception:
        pass


def _build_row_intelligence(panel_apply: dict) -> dict:
    """Summarize per-row knowledge overrides for MCP / report."""
    out = {"holes": [], "slots": [], "pocket_corner_r": [], "templates_2d": {}}
    for pr in panel_apply.get("hole_rows") or []:
        if pr.get("knowledge_confidence") is not None:
            out["holes"].append(
                {
                    "idx": pr.get("idx"),
                    "confidence": pr.get("knowledge_confidence"),
                    "basis": pr.get("knowledge_basis", ""),
                }
            )
    for pr in panel_apply.get("slot_rows") or []:
        if pr.get("knowledge_confidence") is not None:
            out["slots"].append(
                {
                    "idx": pr.get("idx"),
                    "confidence": pr.get("knowledge_confidence"),
                    "basis": pr.get("knowledge_basis", ""),
                }
            )
    rec = panel_apply.get("recommended_templates") or {}
    meta = rec.get("_picker_meta") or panel_apply.get("_picker_meta")
    if isinstance(meta, dict):
        out["templates_2d"] = meta
    return out


def append_knowledge_report(ai_plan: dict) -> None:
    stats = get_db().get_statistics()
    total = int(stats.get("total_records", 0) or 0)
    if total <= 0:
        lines = [
            "",
            "📚 學習庫：尚無歷史記錄。",
            "   每次「執行」成功後會自動記錄孔/槽/2D 模板選擇，累積後 AI 建議會優先採用高信心歷史。",
        ]
    else:
        top = stats.get("top_5_templates") or []
        top_txt = "、".join(
            "{}×{}".format(x.get("name", ""), x.get("count", 0)) for x in top[:3]
        )
        lines = [
            "",
            "📚 學習庫：已累積 {} 筆記錄（本階段 {} 次操作）。".format(
                total, stats.get("session_ops_count", 0)
            ),
            "   高信心歷史已併入 panel_apply；常用模板：{}".format(top_txt or "—"),
        ]
    report = str(ai_plan.get("overall_report", "") or "")
    ai_plan["overall_report"] = report + "\n".join(lines)
    ai_plan["knowledge_statistics"] = stats


def record_execute_training(
    execute_data: dict,
    hole_info_list: List[dict],
    slot_info_list: List[dict],
    pocket_corner_r_list: Optional[List[dict]] = None,
) -> dict:
    """
    Record templates chosen at execute time into KnowledgeDB.
    Called from execute._executeFromPalette on success.
    """
    material = str(execute_data.get("material", "AL6061") or "AL6061").upper()
    prog_mode = str(execute_data.get("programming_mode") or "").strip().lower()
    if not prog_mode:
        try:
            from .programming_modes import MODE_MANUAL

            prog_mode = MODE_MANUAL
        except Exception:
            prog_mode = "manual"
    db = get_db()
    recorded: List[str] = []

    for row in execute_data.get("rows") or []:
        if not isinstance(row, dict):
            continue
        label = _template_label_from_row(row, hole_info_list)
        if not label or label == "(不使用)":
            continue
        idx = int(row.get("idx", 0))
        h = (hole_info_list or [])[idx] if 0 <= idx < len(hole_info_list or []) else {}
        geom = _hole_geometry_for_db(h)
        rid = db.record_operation(
            "hole",
            material,
            geom,
            label,
            op_count=1,
            programming_mode=prog_mode,
        )
        if rid:
            recorded.append(rid)

    for row in execute_data.get("slotRows") or []:
        if not isinstance(row, dict):
            continue
        label = _template_label_from_row(row, slot_info_list)
        if not label or label == "(不使用)":
            continue
        idx = int(row.get("idx", 0))
        s = (slot_info_list or [])[idx] if 0 <= idx < len(slot_info_list or []) else {}
        geom = _slot_geometry_for_db(s)
        rid = db.record_operation(
            "slot", material, geom, label, op_count=1, programming_mode=prog_mode
        )
        if rid:
            recorded.append(rid)

    pcr_list = pocket_corner_r_list or []
    for row in execute_data.get("pocketCornerRRows") or []:
        if not isinstance(row, dict):
            continue
        label = _template_label_from_row(row, pcr_list)
        if not label or label == "(不使用)":
            continue
        idx = int(row.get("idx", 0))
        pr = pcr_list[idx] if 0 <= idx < len(pcr_list) else {}
        try:
            r_mm = float(pr.get("r_mm", pr.get("r", 0)) or 0)
        except Exception:
            r_mm = 0.0
        geom = {"diameter_mm": r_mm * 2.0, "hole_type": "pocket_corner_r"}
        rid = db.record_operation(
            "hole", material, geom, label, op_count=1, programming_mode=prog_mode
        )
        if rid:
            recorded.append(rid)

    for ft_key, feat_type in (
        ("topFaceRough", "face"),
        ("topFaceFinish", "face"),
        ("profileRough", "profile"),
        ("profileFinish", "profile"),
    ):
        name = str(execute_data.get(ft_key, "") or "").strip()
        if not name or name == "(不使用)":
            continue
        rid = db.record_operation(
            feat_type, material, {}, name, op_count=1, programming_mode=prog_mode
        )
        if rid:
            recorded.append(rid)

    db.flush()
    return {"recorded_ids": recorded, "count": len(recorded)}


def handle_knowledge_mcp(action: str, params: dict) -> dict:
    db = get_db()
    if action == "knowledge_stats":
        return {"success": True, "data": db.get_statistics()}

    if action == "knowledge_feedback":
        rid = str(params.get("record_id", "") or "").strip()
        if not rid:
            feedback_list = params.get("feedback_list") or params.get("feedback") or []
            if isinstance(feedback_list, list) and feedback_list:
                result = db.import_ai_feedback(feedback_list)
                db.flush()
                return {"success": True, "data": result}
            return {"success": False, "error": "record_id or feedback_list required"}
        ok = db.submit_feedback(
            rid,
            user_kept=params.get("user_kept"),
            rating=params.get("rating"),
        )
        if ok:
            db.flush()
        return {"success": ok, "data": {"record_id": rid}}

    if action == "knowledge_export":
        max_rec = int(params.get("max_records", 200) or 200)
        return {"success": True, "data": db.export_for_mcp(max_records=max_rec)}

    if action == "knowledge_import":
        records = params.get("records") or []
        if not isinstance(records, list):
            return {"success": False, "error": "records must be a list"}
        imported = 0
        for rec in records:
            if not isinstance(rec, dict):
                continue
            ft = rec.get("feature_type", "hole")
            mat = rec.get("material", "AL6061")
            geom = rec.get("geometry") or {}
            tmpl = rec.get("template_used", "")
            if not tmpl:
                continue
            pm = str(rec.get("programming_mode") or "").strip().lower()
            db.record_operation(
                ft,
                mat,
                geom,
                tmpl,
                op_count=int(rec.get("op_count", 1) or 1),
                programming_mode=pm,
            )
            imported += 1
        db.rebuild_index()
        db.flush()
        return {"success": True, "data": {"imported": imported}}

    if action == "knowledge_rebuild_index":
        n = db.rebuild_index()
        db.flush()
        return {"success": True, "data": {"pattern_keys": n}}

    if action == "knowledge_merge_duplicates":
        stats = db.merge_pattern_index_duplicates()
        return {"success": True, "data": stats}

    if action == "knowledge_resolve_templates":
        mat = str(params.get("material", "AL6061") or "AL6061").upper()
        names = params.get("names") or params.get("template_names") or []
        if isinstance(names, str):
            names = [names]
        try:
            from .template_resolver import build_name_url_index, resolve_template_entry

            build_name_url_index(mat, force_refresh=bool(params.get("refresh_index")))
            resolved = []
            for nm in names:
                ent = resolve_template_entry(mat, str(nm), feature_hint=str(params.get("feature_hint", "")))
                resolved.append({"name": nm, "found": bool(ent), "entry": ent or {}})
            return {"success": True, "data": {"material": mat, "resolved": resolved}}
        except Exception as ex:
            return {"success": False, "error": str(ex)}

    if action == "knowledge_query":
        mat = params.get("material", "AL6061")
        ft = params.get("feature_type", "hole")
        geom = params.get("geometry") or {}
        best = db.query_best_template(ft, mat, geom)
        return {"success": True, "data": best or {}}

    return {"success": False, "error": "Unknown knowledge action"}
