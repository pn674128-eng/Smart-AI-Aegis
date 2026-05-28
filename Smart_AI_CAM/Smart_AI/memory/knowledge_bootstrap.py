# -*- coding: utf-8 -*-
"""
知識庫引導模組 (Knowledge Bootstrap)
======================================
從已編寫的規則代碼與 MD 文件中萃取專家知識，自動預填充 KnowledgeDB，
讓學習資料庫從第一次使用就具備高信心基礎，無需從零累積。

知識來源優先級（信心分數由高到低）：
  1. 真實加工操作記錄        → 動態計算（最高）
  2. MD 文件解析             → 0.75（結構化文件知識）
  3. 內部規則代碼            → 0.70（ai_decision_engine 等）
  4. 跨材料推薦              → 0.35（降級使用）

規則代碼知識來源：
  ① 材質切削物理參數 (MATERIAL_DATABASE)
  ② 孔類型決策規則 (hole_recognizer)
  ③ 槽寬刀徑可行性規則 (ai_decision_engine)
  ④ 模板路徑結構 (TEMPLATE_FOLDER_PATHS)
  ⑤ 牙孔規格表 (_METRIC_TAP_HOLE_SPEC_ITEMS)
  ⑥ 實際模板庫掃描結果 (CAM360/templates)

MD 文件知識來源：
  • implementation_plan.md   → 架構決策、模板結構、功能對照表
  • task.md                  → 已完成功能清單（視為驗證過的知識）
  • walkthrough.md           → 修復記錄、驗證結果、切削參數公式
  • docs/*.md                → 加工規則、材質參數、特徵辨識文件
"""
from __future__ import annotations

import os
import json
import traceback
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────
#  內嵌專家知識（從 ai_decision_engine.py 萃取）
# ─────────────────────────────────────────────

# 材質資料庫（完整複製，避免 Fusion API 依賴）
_MATERIAL_DATABASE = {
    "AL6061": {
        "name": "鋁合金 AL6061",
        "density_g_cm3": 2.70,
        "base_vc_m_min": 180.0,
        "base_fz_mm_t": 0.08,
        "specific_energy": 0.8,
        "hardness_hb": 95,
        "desc": "輕金屬，易切削，散熱快，建議高速高進給。"
    },
    "S50C": {
        "name": "中碳鋼 S50C",
        "density_g_cm3": 7.85,
        "base_vc_m_min": 90.0,
        "base_fz_mm_t": 0.05,
        "specific_energy": 2.2,
        "hardness_hb": 180,
        "desc": "中碳鋼，強度與硬度較高，加工時需適度降低轉速並注意排屑。"
    },
}

# 牙孔規格表（從 template_service.py 萃取）
_METRIC_TAP_SPECS = (
    ("M2",     1.6,  1.7,  0.4),
    ("M2.5",   2.1,  2.2,  0.45),
    ("M3",     2.5,  2.6,  0.5),
    ("M4",     3.3,  3.4,  0.7),
    ("M5",     4.2,  4.3,  0.8),
    ("M6",     5.0,  5.1,  1.0),
    ("M6x0.75",5.3,  5.4,  0.75),
    ("M8",     6.8,  6.9,  1.25),
    ("M8x1.0", 7.0,  7.1,  1.0),
    ("M10",    8.5,  8.6,  1.5),
    ("M12",   10.3, 10.4,  1.75),
)

# 槽寬→刀徑可行性規則（從 ai_decision_engine.py 萃取）
_SLOT_TOOL_CANDIDATES_MM = (2.0, 3.0, 4.0, 6.0, 10.0)

# 模板資料夾路徑（從 Smart_AI_CAM.py 萃取）
_TEMPLATE_FOLDER_PATHS = {
    "topFaceRough":    "{material}/面銑刀模塊 【{material}】/粗加工【{material}】",
    "topFaceFinish":   "{material}/面銑刀模塊 【{material}】/精加工【{material}】",
    "topFaceLegacy":   "{material}/面銑刀模塊 【{material}】",
    "profileRough":    "{material}/銑刀模塊 【{material}】/外輪廓加工 【{material}】/粗加工 【{material}】",
    "profileFinish":   "{material}/銑刀模塊 【{material}】/外輪廓加工 【{material}】/精加工 【{material}】",
    "profileLegacy":   "{material}/銑刀模塊 【{material}】/外輪廓加工 【{material}】",
    "generalHole":     "{material}/孔加工模塊 【{material}】/一般孔 【{material}】",
    "tapHole":         "{material}/孔加工模塊 【{material}】/牙孔 【{material}】",
    "locatingHole":    "{material}/孔加工模塊 【{material}】/定位孔 【{material}】",
    "countersinkHole": "{material}/孔加工模塊 【{material}】/沉頭孔 【{material}】",
    "slotHole":        "{material}/孔加工模塊 【{material}】/長條孔 【{material}】",
    "holeChamfer":     "{material}/倒角刀模塊 【{material}】/孔倒角 【{material}】",
    "contourChamfer":  "{material}/倒角刀模塊 【{material}】/輪廓倒角 【{material}】",
}

_TEMPLATES_ROOT = os.path.normpath(
    os.path.join(os.environ.get("APPDATA", ""), "Autodesk", "CAM360", "templates")
)

_BOOTSTRAP_SOURCE    = "rule_bootstrap_v1"
_MD_BOOTSTRAP_SOURCE = "md_bootstrap_v1"
_BOOTSTRAP_CONFIDENCE    = 0.70  # 規則代碼預置信心分數
_MD_BOOTSTRAP_CONFIDENCE = 0.75  # MD 文件預置信心分數（略高，因文件已經人工驗證）
_BOOTSTRAP_COUNT         = 7     # 等效使用次數


# ─────────────────────────────────────────────
#  工具函式
# ─────────────────────────────────────────────

def _scan_templates_in_folder(folder_abs: str) -> List[str]:
    """掃描資料夾下所有 .f3dhsm-template 檔案，回傳 display name 列表。"""
    names = []
    if not os.path.isdir(folder_abs):
        return names
    for dirpath, dirnames, filenames in os.walk(folder_abs):
        dirnames[:] = [d for d in dirnames if d != "_XRef_"]
        for fn in filenames:
            if fn.lower().endswith(".f3dhsm-template"):
                base = fn.replace(".f3dhsm-template", "").strip()
                import re, unicodedata
                # 移除全形【…】顯示標記
                display = re.sub(r"\u3010[^\u3011]*\u3011", "", base).strip()
                if display:
                    names.append(display)
    return names


def _folder_abs(material: str, key: str) -> str:
    rel = _TEMPLATE_FOLDER_PATHS.get(key, "")
    if not rel:
        return ""
    parts = [p.strip() for p in rel.format(material=material).split("/") if p.strip()]
    return os.path.join(_TEMPLATES_ROOT, *parts)


# ─────────────────────────────────────────────
#  各知識來源的引導記錄生成
# ─────────────────────────────────────────────

def _gen_material_cutting_params(db) -> int:
    """
    引導①：材質切削物理參數知識
    記錄每種材質的基礎加工類型（面銑/輪廓/孔）的推薦策略。
    """
    count = 0
    for mat, mat_info in _MATERIAL_DATABASE.items():
        # 面銑刀知識
        face_names = _scan_templates_in_folder(_folder_abs(mat, "topFaceRough"))
        face_names += _scan_templates_in_folder(_folder_abs(mat, "topFaceFinish"))
        if not face_names:
            face_names = [f"面銑刀模板【{mat}】"]
        best_face = face_names[0]
        rec_id = db.record_operation(
            feature_type="face",
            material=mat,
            geometry={"area_mm2": 1000.0, "z_height_mm": 0.0},
            template_used=best_face,
            template_path=_TEMPLATE_FOLDER_PATHS.get("topFaceRough", "").format(material=mat),
            parameters_override={"source": _BOOTSTRAP_SOURCE, "density": mat_info["density_g_cm3"]},
        )
        if rec_id:
            db.submit_feedback(rec_id, user_kept=True)
            count += 1

        # 外輪廓知識
        profile_names = _scan_templates_in_folder(_folder_abs(mat, "profileRough"))
        profile_names += _scan_templates_in_folder(_folder_abs(mat, "profileFinish"))
        if not profile_names:
            profile_names = [f"輪廓銑模板【{mat}】"]
        best_profile = profile_names[0]
        rec_id = db.record_operation(
            feature_type="profile",
            material=mat,
            geometry={"depth_mm": 20.0},
            template_used=best_profile,
            template_path=_TEMPLATE_FOLDER_PATHS.get("profileRough", "").format(material=mat),
            parameters_override={"source": _BOOTSTRAP_SOURCE},
        )
        if rec_id:
            db.submit_feedback(rec_id, user_kept=True)
            count += 1

    return count


def _gen_general_hole_rules(db) -> int:
    """
    引導②：一般孔（直孔）辨識規則
    從 hole_recognizer 的直徑範圍規則萃取。
    涵蓋各標準鑽孔直徑 1.0~20.0mm。
    """
    count = 0
    # 常見一般孔直徑（從 hole_recognizer 的鑽孔表推導）
    standard_diameters = [
        1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5,
        5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0,
        10.0, 11.0, 12.0, 14.0, 16.0, 18.0, 20.0
    ]
    for mat in _MATERIAL_DATABASE:
        hole_templates = _scan_templates_in_folder(_folder_abs(mat, "generalHole"))
        loc_templates  = _scan_templates_in_folder(_folder_abs(mat, "locatingHole"))
        for dia in standard_diameters:
            # 嘗試從實際模板名找最佳匹配
            best_tmpl = _find_best_template_for_dia(hole_templates, dia)
            if not best_tmpl:
                best_tmpl = f"鑽孔 D{dia} 【{mat}】"
            rec_id = db.record_operation(
                feature_type="hole",
                material=mat,
                geometry={
                    "diameter_mm": dia,
                    "depth_mm": round(dia * 3, 1),   # 深度 = 3×直徑（常見規則）
                    "hole_type": "general",
                    "is_through": False,
                },
                template_used=best_tmpl,
                template_path=_TEMPLATE_FOLDER_PATHS.get("generalHole", "").format(material=mat),
                parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "standard_drill_diameter"},
            )
            if rec_id:
                db.submit_feedback(rec_id, user_kept=True)
                count += 1

            # 定位孔（精孔）
            if loc_templates:
                best_loc = _find_best_template_for_dia(loc_templates, dia)
                if best_loc:
                    rec_id = db.record_operation(
                        feature_type="hole",
                        material=mat,
                        geometry={
                            "diameter_mm": dia,
                            "depth_mm": round(dia * 2, 1),
                            "hole_type": "locating",
                            "is_through": False,
                        },
                        template_used=best_loc,
                        template_path=_TEMPLATE_FOLDER_PATHS.get("locatingHole", "").format(material=mat),
                        parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "locating_hole"},
                    )
                    if rec_id:
                        db.submit_feedback(rec_id, user_kept=True)
                        count += 1
    return count


def _gen_tap_hole_rules(db) -> int:
    """
    引導③：牙孔規格知識（從 _METRIC_TAP_HOLE_SPEC_ITEMS 萃取）
    M2~M12 完整規格表。
    """
    count = 0
    for mat in _MATERIAL_DATABASE:
        tap_templates = _scan_templates_in_folder(_folder_abs(mat, "tapHole"))
        for spec_key, dia_lo, dia_hi, pitch in _METRIC_TAP_SPECS:
            base = spec_key.split("x")[0].split("X")[0]
            pitch_s = str(pitch).rstrip("0").rstrip(".")
            display_key = f"{base}-{pitch_s}"
            best_tmpl = _find_template_containing(tap_templates, display_key)
            if not best_tmpl:
                best_tmpl = _find_template_containing(tap_templates, spec_key)
            if not best_tmpl:
                best_tmpl = f"牙孔 {display_key} 【{mat}】"
            for bottom_dia in [dia_lo, dia_hi]:
                rec_id = db.record_operation(
                    feature_type="hole",
                    material=mat,
                    geometry={
                        "diameter_mm": round(bottom_dia, 1),
                        "hole_type": "tap",
                        "tap_spec": spec_key,
                        "pitch_mm": pitch,
                        "is_through": False,
                    },
                    template_used=best_tmpl,
                    template_path=_TEMPLATE_FOLDER_PATHS.get("tapHole", "").format(material=mat),
                    parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "metric_tap_spec"},
                )
                if rec_id:
                    db.submit_feedback(rec_id, user_kept=True)
                    count += 1
    return count


def _gen_countersink_rules(db) -> int:
    """
    引導④：沉頭孔（Countersink）知識
    """
    count = 0
    for mat in _MATERIAL_DATABASE:
        cs_templates = _scan_templates_in_folder(_folder_abs(mat, "countersinkHole"))
        common_cs_diameters = [3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
        for dia in common_cs_diameters:
            best_tmpl = _find_best_template_for_dia(cs_templates, dia)
            if not best_tmpl and cs_templates:
                best_tmpl = cs_templates[0]
            if not best_tmpl:
                best_tmpl = f"沉頭孔 D{dia} 【{mat}】"
            rec_id = db.record_operation(
                feature_type="hole",
                material=mat,
                geometry={
                    "diameter_mm": dia,
                    "hole_type": "countersink",
                    "is_through": False,
                },
                template_used=best_tmpl,
                template_path=_TEMPLATE_FOLDER_PATHS.get("countersinkHole", "").format(material=mat),
                parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "countersink"},
            )
            if rec_id:
                db.submit_feedback(rec_id, user_kept=True)
                count += 1
    return count


def _gen_slot_rules(db) -> int:
    """
    引導⑤：長條槽加工知識
    從 ai_decision_engine 的槽寬→刀徑可行性規則萃取。
    """
    count = 0
    for mat in _MATERIAL_DATABASE:
        slot_templates = _scan_templates_in_folder(_folder_abs(mat, "slotHole"))
        # 常見槽寬
        slot_widths = [3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0]
        for w in slot_widths:
            feasible = [d for d in _SLOT_TOOL_CANDIDATES_MM if (d + 0.5) <= w <= (d * 1.8)]
            if not feasible:
                continue
            rec_dia = feasible[-1]
            best_tmpl = _find_best_template_for_dia(slot_templates, rec_dia)
            if not best_tmpl and slot_templates:
                best_tmpl = slot_templates[0]
            if not best_tmpl:
                best_tmpl = f"長條孔 D{rec_dia} 【{mat}】"
            rec_id = db.record_operation(
                feature_type="slot",
                material=mat,
                geometry={
                    "width_mm": w,
                    "recommended_tool_dia_mm": rec_dia,
                },
                template_used=best_tmpl,
                template_path=_TEMPLATE_FOLDER_PATHS.get("slotHole", "").format(material=mat),
                parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "slot_width_tool_match"},
            )
            if rec_id:
                db.submit_feedback(rec_id, user_kept=True)
                count += 1
    return count


def _gen_chamfer_rules(db) -> int:
    """
    引導⑥：倒角加工知識（孔倒角 + 輪廓倒角）
    """
    count = 0
    for mat in _MATERIAL_DATABASE:
        hc_templates = _scan_templates_in_folder(_folder_abs(mat, "holeChamfer"))
        cc_templates = _scan_templates_in_folder(_folder_abs(mat, "contourChamfer"))
        # 孔倒角（常見孔徑）
        chamfer_diameters = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
        for dia in chamfer_diameters:
            best_tmpl = _find_best_template_for_dia(hc_templates, dia)
            if not best_tmpl and hc_templates:
                best_tmpl = hc_templates[0]
            if best_tmpl:
                rec_id = db.record_operation(
                    feature_type="chamfer",
                    material=mat,
                    geometry={"diameter_mm": dia, "chamfer_tag": "C0.2"},
                    template_used=best_tmpl,
                    template_path=_TEMPLATE_FOLDER_PATHS.get("holeChamfer", "").format(material=mat),
                    parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "hole_chamfer_c02"},
                )
                if rec_id:
                    db.submit_feedback(rec_id, user_kept=True)
                    count += 1
        # 輪廓倒角
        if cc_templates:
            rec_id = db.record_operation(
                feature_type="chamfer",
                material=mat,
                geometry={"chamfer_tag": "contour", "chamfer_type": "contour"},
                template_used=cc_templates[0],
                template_path=_TEMPLATE_FOLDER_PATHS.get("contourChamfer", "").format(material=mat),
                parameters_override={"source": _BOOTSTRAP_SOURCE, "rule": "contour_chamfer"},
            )
            if rec_id:
                db.submit_feedback(rec_id, user_kept=True)
                count += 1
    return count


# ─────────────────────────────────────────────
#  模板名稱匹配工具
# ─────────────────────────────────────────────

def _find_best_template_for_dia(templates: List[str], dia: float) -> Optional[str]:
    """在模板列表中找最接近目標直徑的模板（搜尋 D{dia} 模式）。"""
    if not templates:
        return None
    import re
    target = round(dia, 1)
    # 精確匹配 D5.0 / D5
    for tmpl in templates:
        ms = re.findall(r"[Dd]\s*(\d+(?:\.\d+)?)", tmpl)
        for m in ms:
            try:
                if abs(float(m) - target) < 0.05:
                    return tmpl
            except Exception:
                pass
    # 找最近的
    best = None
    best_diff = 999.0
    for tmpl in templates:
        ms = re.findall(r"[Dd]\s*(\d+(?:\.\d+)?)", tmpl)
        for m in ms:
            try:
                diff = abs(float(m) - target)
                if diff < best_diff:
                    best_diff = diff
                    best = tmpl
            except Exception:
                pass
    return best if best_diff <= 2.0 else None


def _find_template_containing(templates: List[str], keyword: str) -> Optional[str]:
    """在模板列表中找包含指定關鍵字的模板。"""
    if not templates or not keyword:
        return None
    kw = str(keyword).lower()
    for tmpl in templates:
        if kw in str(tmpl).lower():
            return tmpl
    return None


# ─────────────────────────────────────────────
#  MD 文件解析（知識來源②）
# ─────────────────────────────────────────────

def _md_search_dirs() -> List[str]:
    """搜尋所有可能存放 MD 文件的目錄。"""
    plugin_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    # 智慧識別使用者的 Home 目錄中的 .gemini 路徑
    user_home = os.path.expanduser("~")
    gemini_brain = os.path.normpath(os.path.join(user_home, ".gemini", "antigravity", "brain"))
    
    dirs = [
        plugin_root,
        os.path.join(plugin_root, "docs"),
        os.path.join(plugin_root, "knowledge"),
    ]
    if os.path.isdir(gemini_brain):
        dirs.append(gemini_brain)
        
    return dirs


def _read_md_files() -> List[tuple]:
    """
    掃描所有 MD 文件，回傳 [(檔名, 內容), ...]。
    優先讀取 implementation_plan.md、task.md、walkthrough.md。
    """
    priority = ["implementation_plan.md", "walkthrough.md", "task.md"]
    found: Dict[str, str] = {}

    for d in _md_search_dirs():
        if not os.path.isdir(d):
            continue
        try:
            # 使用 os.walk 來支援遞迴搜尋（包含子目錄，如不同的 conversation ID）
            for dirpath, _, filenames in os.walk(d):
                for fn in filenames:
                    if not fn.lower().endswith(".md"):
                        continue
                    fp = os.path.normpath(os.path.join(dirpath, fn))
                    if fp in found:
                        continue
                    try:
                        with open(fp, "r", encoding="utf-8") as fh:
                            found[fp] = fh.read()
                    except Exception:
                        pass
        except Exception:
            pass

    # 排序：priority 優先
    result = []
    for pname in priority:
        for fp, content in found.items():
            if os.path.basename(fp).lower() == pname.lower():
                result.append((os.path.basename(fp), content))
    for fp, content in found.items():
        bname = os.path.basename(fp).lower()
        if bname not in [p.lower() for p in priority]:
            result.append((os.path.basename(fp), content))
    return result


def _parse_md_table_rows(md_text: str) -> List[Dict[str, str]]:
    """
    解析 Markdown 表格，回傳行字典列表。
    例：| 功能 | 狀態 | 說明 |  →  [{"功能": ..., "狀態": ..., "說明": ...}]
    """
    import re
    rows = []
    table_pattern = re.compile(r"^\|(.+)\|$", re.MULTILINE)
    lines = [m.group(0) for m in table_pattern.finditer(md_text)]
    if len(lines) < 2:
        return rows
    # 第一行為標頭
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    # 第二行為分隔線，跳過
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _extract_template_mappings_from_md(md_text: str) -> List[dict]:
    """
    從 MD 表格中提取「模塊 → 材料 → 模板數量」映射。
    識別包含「模塊」、「AL6061」、「S50C」關鍵字的表格。
    """
    import re
    mappings = []
    rows = _parse_md_table_rows(md_text)
    for row in rows:
        vals = list(row.values())
        row_text = " ".join(vals)
        # 識別模板結構表格
        if "模塊" in row_text or "孔加工" in row_text or "面銑" in row_text:
            # 嘗試找材料和操作類型
            mat = None
            if "AL6061" in row_text:
                mat = "AL6061"
            elif "S50C" in row_text:
                mat = "S50C"
            if not mat:
                continue
            # 特徵類型判斷
            if "孔" in row_text and "加工" in row_text:
                ft = "hole"
            elif "面銑" in row_text or "粗加工" in row_text or "精加工" in row_text:
                ft = "face"
            elif "輪廓" in row_text:
                ft = "profile"
            elif "倒角" in row_text:
                ft = "chamfer"
            elif "槽" in row_text:
                ft = "slot"
            else:
                continue
            mappings.append({"feature_type": ft, "material": mat, "row": row})
    return mappings


def _extract_cutting_rules_from_md(md_text: str) -> List[dict]:
    """
    從 MD 代碼區塊提取切削參數公式或規則說明。
    識別含有 RPM / 進給 / 材質 / 轉速 的文字段落。
    """
    import re
    rules = []
    # 搜尋 AL6061 / S50C 相關描述段落
    for mat in ("AL6061", "S50C"):
        # 找含材料名稱的行
        pattern = re.compile(
            rf".{{0,80}}{re.escape(mat)}.{{0,200}}",
            re.DOTALL,
        )
        for m in pattern.finditer(md_text):
            snippet = m.group(0).strip()
            if any(kw in snippet for kw in ("RPM", "進給", "切削", "速度", "mm/min", "vc", "fz")):
                rules.append({"material": mat, "snippet": snippet[:200]})
    return rules


def _gen_md_knowledge(db) -> int:
    """
    引導⑦：從 MD 文件解析知識。
    解析 implementation_plan.md、task.md、walkthrough.md 及 docs/*.md，
    提取模板結構映射、已驗證功能清單、切削參數說明。
    """
    count = 0
    md_files = _read_md_files()
    if not md_files:
        return 0

    for fname, content in md_files:
        try:
            # ── 1. 從表格提取模板映射 ──
            mappings = _extract_template_mappings_from_md(content)
            for m in mappings:
                ft  = m["feature_type"]
                mat = m["material"]
                # 用資料夾掃描找對應模板
                key_map = {
                    "hole":    "generalHole",
                    "face":    "topFaceRough",
                    "profile": "profileRough",
                    "chamfer": "holeChamfer",
                    "slot":    "slotHole",
                }
                folder_key = key_map.get(ft)
                tmpl_names = _scan_templates_in_folder(_folder_abs(mat, folder_key)) if folder_key else []
                best = tmpl_names[0] if tmpl_names else f"{ft}模板【{mat}】"
                geo: dict = {}
                if ft == "hole":
                    geo = {"hole_type": "general", "diameter_mm": 5.0}
                elif ft == "face":
                    geo = {"area_mm2": 1000.0}
                elif ft == "profile":
                    geo = {"depth_mm": 20.0}
                elif ft == "chamfer":
                    geo = {"chamfer_tag": "C0.2", "diameter_mm": 5.0}
                elif ft == "slot":
                    geo = {"width_mm": 6.0}
                rec_id = db.record_operation(
                    feature_type=ft,
                    material=mat,
                    geometry=geo,
                    template_used=best,
                    parameters_override={
                        "source": _MD_BOOTSTRAP_SOURCE,
                        "from_file": fname,
                    },
                )
                if rec_id:
                    db.submit_feedback(rec_id, user_kept=True)
                    count += 1

            # ── 2. 從切削規則描述提取材質知識 ──
            rules = _extract_cutting_rules_from_md(content)
            for r in rules:
                mat = r["material"]
                # 記錄為「材質知識文件」條目
                rec_id = db.record_operation(
                    feature_type="material_knowledge",
                    material=mat,
                    geometry={"doc_source": fname, "snippet": r["snippet"][:100]},
                    template_used=f"[文件知識] {fname}",
                    parameters_override={
                        "source": _MD_BOOTSTRAP_SOURCE,
                        "from_file": fname,
                        "type": "cutting_rule_doc",
                    },
                )
                if rec_id:
                    db.submit_feedback(rec_id, user_kept=True)
                    count += 1

            # ── 3. task.md 中已完成項目 = 已驗證功能 ──
            if "task" in fname.lower():
                import re
                done_items = re.findall(r"- \[x\] (.+)", content)
                for item in done_items:
                    item = item.strip()
                    if not item:
                        continue
                    # 推斷特徵類型
                    ft = "system_feature"
                    if "孔" in item or "hole" in item.lower():
                        ft = "hole"
                    elif "面銑" in item or "face" in item.lower():
                        ft = "face"
                    elif "輪廓" in item or "profile" in item.lower():
                        ft = "profile"
                    elif "槽" in item or "slot" in item.lower():
                        ft = "slot"
                    elif "倒角" in item or "chamfer" in item.lower():
                        ft = "chamfer"
                    rec_id = db.record_operation(
                        feature_type=ft,
                        material="AL6061",  # 預設材料
                        geometry={"validated_feature": item[:80]},
                        template_used=f"[已驗證] {item[:60]}",
                        parameters_override={
                            "source": _MD_BOOTSTRAP_SOURCE,
                            "from_file": fname,
                            "type": "validated_task",
                        },
                    )
                    if rec_id:
                        db.submit_feedback(rec_id, user_kept=True)
                        count += 1

        except Exception:
            pass  # 單個文件解析失敗不影響整體

    return count


# ─────────────────────────────────────────────
#  主引導函式
# ─────────────────────────────────────────────

def bootstrap_knowledge(db, force: bool = False) -> dict:
    """
    從現有規則代碼預填充知識資料庫。

    Args:
        db:    KnowledgeDB 實例
        force: True = 強制重新引導（即使已有記錄）

    Returns:
        {
          "already_seeded": bool,
          "total_injected": int,
          "breakdown": {分類名: 數量},
        }
    """
    # 檢查是否已引導過
    if not force:
        stats = db.get_statistics()
        existing = stats.get("total_records", 0)
        if existing >= 50:
            return {
                "already_seeded": True,
                "existing_records": existing,
                "total_injected": 0,
                "message": f"資料庫已有 {existing} 筆記錄，跳過引導。使用 force=True 強制重跑。",
            }

    breakdown = {}
    total = 0

    try:
        n = _gen_material_cutting_params(db)
        breakdown["材質切削參數"] = n
        total += n
    except Exception:
        breakdown["材質切削參數"] = f"ERROR: {traceback.format_exc()}"

    try:
        n = _gen_general_hole_rules(db)
        breakdown["一般孔/定位孔"] = n
        total += n
    except Exception:
        breakdown["一般孔/定位孔"] = f"ERROR: {traceback.format_exc()}"

    try:
        n = _gen_tap_hole_rules(db)
        breakdown["牙孔規格"] = n
        total += n
    except Exception:
        breakdown["牙孔規格"] = f"ERROR: {traceback.format_exc()}"

    try:
        n = _gen_countersink_rules(db)
        breakdown["沉頭孔"] = n
        total += n
    except Exception:
        breakdown["沉頭孔"] = f"ERROR: {traceback.format_exc()}"

    try:
        n = _gen_slot_rules(db)
        breakdown["長條槽"] = n
        total += n
    except Exception:
        breakdown["長條槽"] = f"ERROR: {traceback.format_exc()}"

    try:
        n = _gen_chamfer_rules(db)
        breakdown["孔倒角/輪廓倒角"] = n
        total += n
    except Exception:
        breakdown["孔倒角/輪廓倒角"] = f"ERROR: {traceback.format_exc()}"

    # ── MD 文件知識（信心分數 0.75，略高於規則代碼）──
    try:
        n = _gen_md_knowledge(db)
        breakdown["MD文件知識"] = n
        total += n
    except Exception:
        breakdown["MD文件知識"] = f"ERROR: {traceback.format_exc()}"

    # 儲存
    db.flush()

    return {
        "already_seeded": False,
        "total_injected": total,
        "breakdown": breakdown,
        "sources": {
            "rules": "ai_decision_engine.py + hole_recognizer + template_service",
            "md_files": "implementation_plan.md + task.md + walkthrough.md + docs/*.md",
            "templates": f"CAM360/templates ({_TEMPLATES_ROOT})",
        },
        "message": f"成功注入 {total} 筆預置知識（規則代碼 + MD文件）。",
    }


def get_bootstrap_status(db) -> dict:
    """取得引導狀態摘要。"""
    stats = db.get_statistics()
    records = stats.get("total_records", 0)
    # 計算有多少來自引導（parameters_overridden.source == _BOOTSTRAP_SOURCE）
    return {
        "total_records": records,
        "is_bootstrapped": records >= 20,
        "ready_for_ml": records >= 100,
        "statistics": stats,
    }
