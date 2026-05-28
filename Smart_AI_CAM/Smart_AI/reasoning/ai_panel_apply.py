# -*- coding: utf-8 -*-
"""
Map AI decision plan → panel row indices (tmplIdx, 2D templates).
Read-only mapping; does not execute CAM or alter hole recognition baseline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


def _norm_label(s: str) -> str:
    return str(s or "").strip().lower()


def _label_has_any(label: str, keywords: Sequence[str]) -> bool:
    lab = _norm_label(label)
    for kw in keywords:
        if kw and kw.lower() in lab:
            return True
    return False


def _parse_tool_dia_from_label(label: str) -> Optional[float]:
    m = re.search(r"d\s*(\d+(?:\.\d+)?)", _norm_label(label), re.I)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*mm", _norm_label(label))
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            return None
    return None


def find_tmpl_idx_by_keywords(
    drop_items: List[dict],
    *,
    include_keywords: Optional[Sequence[str]] = None,
    exclude_keywords: Optional[Sequence[str]] = None,
    prefer_has_drill: bool = False,
    prefer_has_slot: bool = False,
    prefer_has_chamfer: bool = False,
    target_tool_dia_mm: Optional[float] = None,
) -> int:
    """Return dropItems index or -1."""
    items = drop_items or []
    best_idx = -1
    best_score = -1.0

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "") or "")
        if label == "(不使用)":
            continue
        lab_n = _norm_label(label)
        if exclude_keywords and _label_has_any(lab_n, exclude_keywords):
            continue
        if include_keywords and not _label_has_any(lab_n, include_keywords):
            continue

        score = 1.0
        if prefer_has_drill and it.get("hasDrill"):
            score += 2.0
        if prefer_has_slot and (it.get("hasSlot") or it.get("slotUrl")):
            score += 2.0
        if prefer_has_chamfer and (it.get("hasChamfer") or it.get("chamferUrl")):
            score += 1.0

        if target_tool_dia_mm is not None:
            td = it.get("toolDia")
            if td is not None:
                try:
                    score += 10.0 - abs(float(td) - float(target_tool_dia_mm))
                except Exception:
                    pass
            else:
                td_lab = _parse_tool_dia_from_label(label)
                if td_lab is None:
                    score -= 0.5
                else:
                    score += 10.0 - abs(td_lab - float(target_tool_dia_mm))

        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx >= 0:
        return best_idx

    # Fallback: first non-unused
    for i, it in enumerate(items):
        if isinstance(it, dict) and str(it.get("label", "")) != "(不使用)":
            return i
    return 0 if items else -1


def _hole_decision_by_idx(ai_plan: dict) -> Dict[int, dict]:
    out = {}
    for h in (ai_plan.get("decisions") or {}).get("holes") or []:
        if isinstance(h, dict) and "idx" in h:
            out[int(h["idx"])] = h
    return out


def _slot_decision_by_idx(ai_plan: dict) -> Dict[int, dict]:
    out = {}
    for s in (ai_plan.get("decisions") or {}).get("slots") or []:
        if isinstance(s, dict) and "idx" in s:
            out[int(s["idx"])] = s
    return out


def build_panel_apply_patch(
    ai_plan: dict,
    holes_panel: List[dict],
    slots_panel: List[dict],
    pocket_corner_r_panel: Optional[List[dict]] = None,
    *,
    fusion_hole_hints: Optional[List[dict]] = None,
    flat_depths: Optional[dict] = None,
    feature_catalog: Optional[dict] = None,
    contour_chamfer_names: Optional[List[str]] = None,
    top_face_rough_names: Optional[List[str]] = None,
    top_face_finish_names: Optional[List[str]] = None,
    official_slot_pocket_panel: Optional[List[dict]] = None,
    official_pocket_slot_panel: Optional[List[dict]] = None,
    thinking_layer: str = "",
) -> dict:
    """
    Structured patch for palette.html — user may edit any field before Execute.
    """
    rec = dict(ai_plan.get("recommended_templates") or {})
    try:
        from Smart_AI.perception import contour_2d_recognizer as c2d
        from . import feature_apply as fap

        c2d_rec = ai_plan.get("contour_2d_recognition")
        if c2d_rec and isinstance(c2d_rec, dict):
            c2d_tmpl = c2d_rec.get("recommended_templates") or {}
            for k in ("topFaceRough", "topFaceFinish", "profileRough", "profileFinish"):
                v = c2d_tmpl.get(k)
                if v and v != "(不使用)":
                    rec[k] = v

        terrace = fap.build_terrace_2d_templates(
            flat_depths or ai_plan.get("flat_depths"),
            list(top_face_rough_names or []),
            list(top_face_finish_names or []),
        )
        if terrace.get("strategy") in ("multi_terrace", "single_terrace"):
            for k in ("topFaceRough", "topFaceFinish"):
                v = terrace.get(k)
                if v and v != "(不使用)":
                    rec[k] = v
            if terrace.get("terrace_face_ops"):
                rec["terrace_face_ops"] = list(terrace.get("terrace_face_ops") or [])

        chamfer_n = int((feature_catalog or {}).get("counts_by_category", {}).get("chamfer_bevel", 0) or 0)
        if not chamfer_n and feature_catalog is None:
            chamfer_n = int((ai_plan.get("decisions") or {}).get("chamfer_bevel", {}).get("count", 0) or 0)
        rec = fap.merge_contour_chamfer_template(
            rec,
            chamfer_bevel_count=chamfer_n,
            contour_chamfer_names=contour_chamfer_names,
        )
    except Exception:
        pass

    hole_by_idx = _hole_decision_by_idx(ai_plan)
    slot_by_idx = _slot_decision_by_idx(ai_plan)
    fusion_by_idx = {int(x["idx"]): x for x in (fusion_hole_hints or []) if isinstance(x, dict) and "idx" in x}

    hole_rows = []
    for idx, h in enumerate(holes_panel or []):
        if not isinstance(h, dict):
            continue
        items = h.get("dropItems") or []
        ai_h = hole_by_idx.get(idx, {})
        try:
            from . import feature_apply as fap

            tmpl_idx, reason = fap.apply_hole_row_with_hints(
                h, items, fusion_hint=fusion_by_idx.get(idx), ai_h=ai_h
            )
        except Exception:
            tmpl_idx, reason = 0, "fallback"

        hole_rows.append(
            {
                "idx": idx,
                "tmplIdx": tmpl_idx,
                "reason": reason,
                "is_threaded": bool(
                    fusion_by_idx.get(idx, {}).get("prefer_tap") or ai_h.get("is_threaded", False)
                ),
            }
        )

    slot_rows = []
    for idx, s in enumerate(slots_panel or []):
        if not isinstance(s, dict):
            continue
        ai_s = slot_by_idx.get(idx, {})
        if ai_s.get("active") is False:
            slot_rows.append(
                {
                    "idx": idx,
                    "tmplIdx": -1,
                    "reason": ai_s.get("reason", "槽列標記為非加工用（略過 execute）"),
                    "active": False,
                    "skip_execute": True,
                }
            )
            continue
        items = s.get("dropItems") or []
        rec_dia = ai_s.get("recommended_tool_dia_mm")
        if rec_dia is None:
            try:
                rec_dia = float(s.get("tool_dia", "").replace("D", ""))
            except Exception:
                rec_dia = None
        try:
            from . import feature_apply as fap

            tmpl_idx, slot_reason = fap.apply_slot_row_with_chamfer(
                items, rec_dia=float(rec_dia) if rec_dia is not None else None
            )
        except Exception:
            tmpl_idx = find_tmpl_idx_by_keywords(
                items,
                include_keywords=("槽", "slot", "pocket"),
                prefer_has_slot=True,
                target_tool_dia_mm=float(rec_dia) if rec_dia is not None else None,
            )
            slot_reason = ai_s.get("reason", "AI 槽寬刀徑建議")
        if tmpl_idx < 0:
            tmpl_idx = find_tmpl_idx_by_keywords(items, prefer_has_slot=True)
        slot_rows.append(
            {
                "idx": idx,
                "tmplIdx": max(0, tmpl_idx),
                "reason": slot_reason,
                "recommended_tool_dia_mm": rec_dia,
            }
        )

    pcr_rows = []
    for idx, row in enumerate(pocket_corner_r_panel or []):
        if not isinstance(row, dict):
            continue
        items = row.get("dropItems") or []
        try:
            r_mm = float(row.get("radius_mm", row.get("r_mm", 0)) or 0)
        except Exception:
            r_mm = 0.0
        target_d = max(1.0, round(2.0 * r_mm, 2)) if r_mm > 0 else 3.0
        tmpl_idx = find_tmpl_idx_by_keywords(
            items,
            include_keywords=("鑽", "drill", "general"),
            prefer_has_drill=True,
            target_tool_dia_mm=target_d,
        )
        ch = items[tmpl_idx] if 0 <= tmpl_idx < len(items) else {}
        if str(ch.get("label", "") or "") == "(不使用)":
            pcr_rows.append(
                {
                    "idx": idx,
                    "tmplIdx": tmpl_idx,
                    "reason": "口袋 R：未選模板",
                    "skip_execute": True,
                }
            )
            continue
        pcr_rows.append(
            {
                "idx": idx,
                "tmplIdx": max(0, tmpl_idx if tmpl_idx >= 0 else 0),
                "reason": f"口袋 R：建議小徑鑽 D≈{target_d}mm",
            }
        )

    official_slot_rows: List[dict] = []
    official_pocket_rows: List[dict] = []
    layer = str(thinking_layer or "").strip()
    if layer == "L1_extended_features":
        try:
            from . import feature_apply as fap

            for i, row in enumerate(official_slot_pocket_panel or []):
                if not isinstance(row, dict):
                    continue
                d2 = row.get("dropItems2d") or []
                d3 = row.get("dropItems3d") or []
                t2, t3, bind, reason = fap.apply_official_pocket_row(row, d2, d3)
                official_slot_rows.append(
                    {
                        "idx": i,
                        "panel_row_index": int(row.get("panel_row_index", i)),
                        "body_token": str(row.get("body_token", "") or ""),
                        "pocket_index": int(row.get("pocket_index", 0) or 0),
                        "bindMode": bind,
                        "tmpl2dIdx": t2,
                        "tmpl3dIdx": t3,
                        "through": bool(row.get("through")),
                        "pocket_kind": str(row.get("pocket_kind", "slot") or "slot"),
                        "reason": reason,
                    }
                )
            for i, row in enumerate(official_pocket_slot_panel or []):
                if not isinstance(row, dict):
                    continue
                d2 = row.get("dropItems2d") or []
                d3 = row.get("dropItems3d") or []
                t2, t3, bind, reason = fap.apply_official_pocket_row(row, d2, d3)
                official_pocket_rows.append(
                    {
                        "idx": i,
                        "panel_row_index": int(row.get("panel_row_index", i)),
                        "body_token": str(row.get("body_token", "") or ""),
                        "pocket_index": int(row.get("pocket_index", 0) or 0),
                        "bindMode": bind,
                        "tmpl2dIdx": t2,
                        "tmpl3dIdx": t3,
                        "through": bool(row.get("through")),
                        "pocket_kind": str(row.get("pocket_kind", "pocket") or "pocket"),
                        "reason": reason,
                    }
                )
        except Exception:
            pass

    decisions = ai_plan.get("decisions") or {}
    terrace_ops = rec.get("terrace_face_ops") or []
    apply_2d = bool(
        decisions.get("top_face")
        or decisions.get("outer_contour")
        or (rec.get("contourChamfer") and rec.get("contourChamfer") != "(不使用)")
        or len(terrace_ops) > 0
    )

    return {
        "version": "1.0",
        "apply_2d_templates": apply_2d,
        "recommended_templates": rec,
        "hole_rows": hole_rows,
        "slot_rows": slot_rows,
        "pocket_corner_r_rows": pcr_rows,
        "terrace_face_ops": terrace_ops,
        "official_slot_pocket_rows": official_slot_rows,
        "official_pocket_slot_rows": official_pocket_rows,
        "notes": [
            "此為 AI 建議填入面板；所有下拉與深度仍可手動修改後再按「執行」。",
            "孔列優先 Fusion RecognizedHoleGroup + 設計 HoleFeature 螺紋；不足處由語意規則補強。",
            "倒角斜邊可帶入輪廓精加工模板；孔倒角組合依 Fusion 倒角段判斷。",
            "倒角篩選（C0.2/C0.3/僅倒角）仍由操作者控制，不覆寫全域設定。",
        ],
    }
