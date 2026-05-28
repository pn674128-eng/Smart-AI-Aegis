# -*- coding: utf-8 -*-
r"""
Fusion 360 本地刀具庫查詢模組
=====================================
讀取 %APPDATA%\Autodesk\CAM360\libraries\Local\加工刀具 下的所有 .json
提供統計 / 列舉 / 條件搜尋 / 最佳匹配 四種模式給 MCP 與 cam-helper Agent 使用

設計原則：
1. **唯讀** - 不修改任何刀具庫檔案
2. **無依賴** - 只用 stdlib
3. **小快取** - 60 秒 mtime 檢查，避免每次都重讀 ~1MB
4. **正規化** - 把雜亂的 expressions/geometry 抽出統一的 normalized fields
5. **材質匹配** - 自動辨識【ALUS】=鋁用 / 【CIB】=鋼用 等中文標籤
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Path resolution
# ============================================================

def _default_tool_library_path() -> str:
    """預設 Fusion 360 本地刀具庫位置，可由 SMART_AI_CAM_TOOL_LIB env 覆蓋。"""
    override = os.environ.get("SMART_AI_CAM_TOOL_LIB")
    if override and os.path.isdir(override):
        return override
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Autodesk", "CAM360", "libraries", "Local", "加工刀具")


# ============================================================
# Category classifier (依檔名 + description 判定刀具類型 + 適用材質)
# ============================================================

CATEGORY_PATTERNS: List[Tuple[str, str, List[str]]] = [
    # (canonical_name, display_zh, [filename keywords])
    ("center_drill",  "中心鑽",     ["中心鑽"]),
    ("chamfer",       "倒角刀",     ["倒角"]),
    ("face_mill",     "面銑刀",     ["面銑"]),
    ("ball_mill",     "球刀",       ["球刀"]),
    ("bull_nose",     "圓鼻刀",     ["圓鼻"]),
    ("end_mill_alu",  "鋁用端銑刀", ["ALUS", "鋁用銑刀", "鋁用鎢鋼", "鋁(屑)"]),
    ("end_mill_steel","鋼用端銑刀", ["CIB", "鋼用銑刀"]),
    ("end_mill",      "端銑刀",     ["端銑", "鎢鋼銑刀", "鎢鋼端銑"]),
    ("reamer",        "絞刀",       ["絞刀", "鉸刀"]),
    ("tap",           "攻牙刀",     ["攻牙", "螺紋"]),
    ("drill_carbide", "鎢鋼鑽頭",   ["鎢鋼鑽", "鎢鋼小頭", "高硬度鎢鋼鑽"]),
    ("drill_sg",      "SG 鑽頭",    ["SG"]),
    ("drill_hss_co",  "HSS-Co 鑽頭",["HSS-Co"]),
    ("drill_hss",     "HSS 鑽頭",   ["HSS"]),
    ("drill",         "鑽頭",       ["鑽刀", "鑽頭", "小頭"]),
]

# 材質適用：從 category + description 推測
ALU_KEYWORDS   = ["ALUS", "鋁", "Aluminum", "Alum", "ALU"]
STEEL_KEYWORDS = ["CIB", "鋼用", "Steel", "硬料"]


def _classify_category(filename: str, sample_desc: str = "") -> Tuple[str, str]:
    """從檔名與第一個刀的 description 判定類別。回傳 (canonical, display_zh)。"""
    base = os.path.splitext(filename)[0]
    blob = f"{base} {sample_desc}"
    for cano, disp, kws in CATEGORY_PATTERNS:
        for kw in kws:
            if kw in blob:
                return cano, disp
    return "unknown", base


def _suitable_materials(category: str, filename: str, description: str) -> List[str]:
    """推測適用材質列表（從類別 + 標籤）。"""
    blob = f"{filename} {description}"
    mats: List[str] = []
    is_alu = any(k in blob for k in ALU_KEYWORDS)
    is_steel = any(k in blob for k in STEEL_KEYWORDS)

    # ALUS 標籤 → 主要鋁用
    if is_alu:
        mats.extend(["AL6061", "AL7075", "Brass", "Plastics"])
    # CIB 標籤 → 主要鋼用 + 不鏽鋼
    if is_steel:
        mats.extend(["S50C", "S45C", "SUS304", "SKD11"])

    # 通用類 (HSS 鑽頭、絞刀、攻牙、中心鑽、倒角) → 全材質可用
    if not is_alu and not is_steel:
        if category in ("drill_hss", "drill_hss_co", "drill_sg", "drill", "center_drill",
                        "chamfer", "tap", "reamer"):
            mats = ["AL6061", "S50C", "SUS304", "Brass", "Plastics"]
        elif category in ("drill_carbide",):
            mats = ["S50C", "SUS304", "SKD11", "AL6061"]
        elif category in ("end_mill", "face_mill", "ball_mill", "bull_nose"):
            mats = ["AL6061", "S50C", "SUS304", "Brass"]
        else:
            mats = ["AL6061", "S50C"]

    return list(dict.fromkeys(mats))  # 去重保序


# ============================================================
# Value parsing (從 expressions 的字串中抽數字)
# ============================================================

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_mm(s: Any) -> Optional[float]:
    """從 '9.0 mm' 或 '(124-30) mm' 抽出數字。失敗回 None。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    s = s.strip().replace("'", "")
    # 形如 (124-30) mm → 算式
    if "(" in s and ")" in s:
        try:
            inner = s[s.index("(") + 1:s.index(")")]
            # 安全：只允許數字 + 基本運算
            if re.fullmatch(r"[\d\s\+\-\*/\.\(\)]+", inner):
                return float(eval(inner))  # noqa: S307 - we validated chars
        except Exception:
            pass
    m = _NUM_RE.search(s)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None


def _parse_int(s: Any) -> Optional[int]:
    v = _parse_mm(s)
    if v is None:
        return None
    return int(v)


def _strip_quotes(s: Any) -> str:
    if not isinstance(s, str):
        return str(s) if s is not None else ""
    return s.strip().strip("'").strip('"')


# ============================================================
# Tool normalization
# ============================================================

def _extract_presets(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """抽取每把刀的 start-values.presets[] 實機切削參數列表。
    
    Fusion 360 本地刀具庫每把刀帶有 N 個 preset (工序), 例如:
      "粗銑", "精銑", "側銑", "層銑", "孔銑", "插銑", "滿刃銑", "面銑",
      "側壁精銑", "測銑", "長條孔" ...
    每個 preset 是「用戶實際在他機台跑過驗證過的參數」, 為金標準。
    """
    out: List[Dict[str, Any]] = []
    presets = (raw.get("start-values") or {}).get("presets") or []
    for p in presets:
        # rpm 跟 feedrate 可能在 expressions 內(字串)或頂層(數字), 優先用頂層
        n = p.get("n")
        v_f = p.get("v_f")
        if (n is None or v_f is None):
            expr = p.get("expressions") or {}
            if n is None:
                try: n = float(str(expr.get("tool_spindleSpeed", "")).split()[0])
                except Exception: n = None
            if v_f is None:
                try: v_f = float(str(expr.get("tool_feedCutting", "")).split()[0])
                except Exception: v_f = None
        out.append({
            "name": _strip_quotes(p.get("name", "")),
            "rpm": int(n) if n else None,
            "feed_mm_min": float(v_f) if v_f else None,
            "v_c_m_min": p.get("v_c"),         # 切削速度 (廠商物理推導值)
            "f_z_mm_tooth": p.get("f_z"),      # 每齒進給
            "f_n_mm_rev": p.get("f_n"),        # 每轉進給 (鑽頭主要用)
            "feed_plunge": p.get("v_f_plunge"),
            "feed_ramp": p.get("v_f_ramp"),
            "ramp_angle_deg": p.get("ramp-angle"),
            "stepdown_mm": p.get("stepdown"),
            "stepover_mm": p.get("stepover"),
            "coolant": p.get("tool-coolant"),
            "material_category": (p.get("material") or {}).get("category", "all"),
            "use_stepdown": p.get("use-stepdown"),
            "use_stepover": p.get("use-stepover"),
        })
    return out


def _normalize_tool(raw: Dict[str, Any], category: str, category_zh: str,
                    source_file: str) -> Dict[str, Any]:
    """把原始 Fusion tool JSON 抽出統一欄位。"""
    expr = raw.get("expressions") or {}
    geom = raw.get("geometry") or {}
    description = _strip_quotes(expr.get("tool_description") or raw.get("description") or "")
    vendor = _strip_quotes(expr.get("tool_vendor") or raw.get("vendor") or "")
    product_id = _strip_quotes(expr.get("tool_productId") or raw.get("product-id") or "")

    out = {
        "category": category,
        "category_zh": category_zh,
        "source_file": source_file,
        "guid": raw.get("guid"),
        "tool_number": _parse_int(expr.get("tool_number")),
        "description": description,
        "vendor": vendor,
        "product_id": product_id,
        "material": _strip_quotes(raw.get("BMC", "")),  # "hss" / "carbide"
        "diameter_mm": _parse_mm(expr.get("tool_diameter")) or geom.get("DC"),
        "flute_length_mm": _parse_mm(expr.get("tool_fluteLength")) or geom.get("LCF"),
        "shoulder_length_mm": (_parse_mm(expr.get("tool_shoulderLength"))
                               or geom.get("shoulder-length")),
        "overall_length_mm": _parse_mm(expr.get("tool_overallLength")) or geom.get("OAL"),
        "shaft_diameter_mm": _parse_mm(expr.get("tool_shaftDiameter")),
        "teeth": (_parse_int(expr.get("tool_numberOfFlutes"))
                  or geom.get("NOF") or 0),
        "corner_radius_mm": _parse_mm(expr.get("tool_cornerRadius")) or geom.get("RE"),
        "tip_angle_deg": _parse_mm(expr.get("tool_tipAngle")) or geom.get("SIG"),
        "suitable_materials": _suitable_materials(category, source_file, description),
        "holder_id": (raw.get("holder", {}) or {}).get("product-id", ""),
        "type": _strip_quotes(raw.get("type", "")),
        # ★ 實機 preset (用戶在他機台跑過的真實參數, 金標準 L0)
        "presets": _extract_presets(raw),
    }
    return out


# ============================================================
# Cache
# ============================================================

class _Cache:
    def __init__(self, ttl_sec: float = 60.0) -> None:
        self.ttl = ttl_sec
        self.last_load: float = 0.0
        self.last_root: str = ""
        self.last_mtime: float = 0.0
        self.tools: List[Dict[str, Any]] = []
        self.error: Optional[str] = None

_CACHE = _Cache()


def _root_mtime(root: str) -> float:
    """所有 .json 的 max(mtime) 拿來判斷是否需重載。"""
    try:
        mtimes = []
        for fn in os.listdir(root):
            if fn.endswith(".json"):
                mtimes.append(os.path.getmtime(os.path.join(root, fn)))
        return max(mtimes) if mtimes else 0.0
    except Exception:
        return 0.0


def _load_tools(root: Optional[str] = None, force: bool = False) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """讀全部刀具，回傳 (tools, error)。帶快取。"""
    root = root or _default_tool_library_path()
    now = time.time()
    mtime = _root_mtime(root)

    if (not force
            and _CACHE.last_root == root
            and _CACHE.last_mtime == mtime
            and (now - _CACHE.last_load) < _CACHE.ttl
            and _CACHE.tools):
        return _CACHE.tools, _CACHE.error

    if not os.path.isdir(root):
        err = f"刀具庫路徑不存在: {root}"
        _CACHE.error = err
        _CACHE.tools = []
        _CACHE.last_load = now
        _CACHE.last_root = root
        _CACHE.last_mtime = 0
        return [], err

    tools: List[Dict[str, Any]] = []
    errors: List[str] = []
    for fn in sorted(os.listdir(root)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"{fn}: {e}")
            continue
        items = data.get("data") or []
        if not items:
            continue
        sample_desc = (items[0].get("description") or "") if items else ""
        cano, disp = _classify_category(fn, sample_desc)
        for raw in items:
            try:
                tools.append(_normalize_tool(raw, cano, disp, fn))
            except Exception as e:
                errors.append(f"{fn}/{raw.get('guid', '?')}: {e}")

    _CACHE.tools = tools
    _CACHE.error = "; ".join(errors) if errors else None
    _CACHE.last_load = now
    _CACHE.last_root = root
    _CACHE.last_mtime = mtime
    return tools, _CACHE.error


# ============================================================
# Public API - 4 query modes
# ============================================================

def stats(root: Optional[str] = None) -> Dict[str, Any]:
    """總覽：總刀數、各分類數、材質分布、直徑分布。"""
    tools, err = _load_tools(root)
    by_category: Dict[str, int] = {}
    by_category_zh: Dict[str, str] = {}
    by_material: Dict[str, int] = {}
    by_dia_bucket: Dict[str, int] = {}
    by_teeth: Dict[str, int] = {}

    for t in tools:
        cat = t["category"]
        by_category[cat] = by_category.get(cat, 0) + 1
        by_category_zh[cat] = t["category_zh"]
        bmc = t.get("material") or "unknown"
        by_material[bmc] = by_material.get(bmc, 0) + 1
        dia = t.get("diameter_mm")
        if dia is not None:
            bucket = (f"<2mm" if dia < 2 else
                      f"2-5mm" if dia < 5 else
                      f"5-10mm" if dia < 10 else
                      f"10-20mm" if dia < 20 else
                      f">=20mm")
            by_dia_bucket[bucket] = by_dia_bucket.get(bucket, 0) + 1
        tn = t.get("teeth") or 0
        if tn:
            by_teeth[str(tn)] = by_teeth.get(str(tn), 0) + 1

    return {
        "library_path": root or _default_tool_library_path(),
        "total_tools": len(tools),
        "categories": [
            {"key": k, "zh": by_category_zh[k], "count": v}
            for k, v in sorted(by_category.items(), key=lambda x: -x[1])
        ],
        "by_material": by_material,
        "by_diameter_bucket": by_dia_bucket,
        "by_teeth": by_teeth,
        "load_error": err,
    }


def list_by_category(category: Optional[str] = None,
                     limit: int = 100,
                     root: Optional[str] = None) -> Dict[str, Any]:
    """列舉指定分類所有刀（不帶 category=列全部）。"""
    tools, err = _load_tools(root)
    if category:
        tools = [t for t in tools if t["category"] == category
                 or t["category_zh"] == category]
    tools = tools[:limit]
    return {
        "category": category,
        "count": len(tools),
        "tools": [_compact_tool(t) for t in tools],
        "load_error": err,
    }


def search(diameter_mm: Optional[float] = None,
           diameter_tolerance: float = 0.5,
           category: Optional[str] = None,
           material_target: Optional[str] = None,
           teeth_min: Optional[int] = None,
           teeth_max: Optional[int] = None,
           tool_material: Optional[str] = None,  # hss / carbide
           limit: int = 30,
           root: Optional[str] = None) -> Dict[str, Any]:
    """條件搜尋。"""
    tools, err = _load_tools(root)
    out = []
    for t in tools:
        if category and t["category"] != category and t["category_zh"] != category:
            continue
        if diameter_mm is not None:
            d = t.get("diameter_mm")
            if d is None or abs(d - diameter_mm) > diameter_tolerance:
                continue
        if material_target:
            if material_target not in (t.get("suitable_materials") or []):
                continue
        if teeth_min is not None and (t.get("teeth") or 0) < teeth_min:
            continue
        if teeth_max is not None and (t.get("teeth") or 0) > teeth_max:
            continue
        if tool_material and (t.get("material") or "").lower() != tool_material.lower():
            continue
        out.append(t)

    out.sort(key=lambda x: (
        abs((x.get("diameter_mm") or 0) - (diameter_mm or 0)) if diameter_mm else 0,
        -(x.get("shoulder_length_mm") or 0),
    ))
    out = out[:limit]
    return {
        "query": {
            "diameter_mm": diameter_mm,
            "diameter_tolerance": diameter_tolerance,
            "category": category,
            "material_target": material_target,
            "teeth_min": teeth_min,
            "teeth_max": teeth_max,
            "tool_material": tool_material,
        },
        "count": len(out),
        "tools": [_compact_tool(t) for t in out],
        "load_error": err,
    }


# 加工任務 → 推薦類別優先順序
_JOB_CATEGORY_PRIORITY: Dict[str, List[str]] = {
    # feature_type → 偏好的 category（依優先順序）
    "hole":       ["drill_carbide", "drill_sg", "drill_hss", "drill_hss_co", "drill"],
    "hole_tap":   ["tap"],
    "hole_ream":  ["reamer"],
    "center":     ["center_drill"],
    "face":       ["face_mill", "end_mill_alu", "end_mill_steel", "end_mill"],
    "contour":    ["end_mill_alu", "end_mill_steel", "end_mill"],
    "pocket":     ["end_mill_alu", "end_mill_steel", "end_mill", "ball_mill"],
    "chamfer":    ["chamfer", "end_mill"],
    "slot":       ["end_mill_alu", "end_mill_steel", "end_mill"],
    "ball":       ["ball_mill", "bull_nose"],
}


def find_best(feature_type: str,
              material_target: str,
              diameter_mm: Optional[float] = None,
              diameter_tolerance: float = 0.5,
              required_reach_mm: Optional[float] = None,
              root: Optional[str] = None) -> Dict[str, Any]:
    """加工需求 → 最適刀具推薦。

    feature_type: hole / hole_tap / hole_ream / center / face / contour /
                  pocket / chamfer / slot / ball
    material_target: AL6061 / S50C / SUS304 / Brass / Plastics / SKD11 / S45C
    diameter_mm: 想要的刀徑 (mm)
    required_reach_mm: 工件加工深度 → 用來檢查避空長度

    回傳排序後候選列表，第 1 個是最推薦。
    """
    tools, err = _load_tools(root)
    cats = _JOB_CATEGORY_PRIORITY.get(feature_type, [feature_type])

    candidates: List[Tuple[float, Dict[str, Any], str]] = []
    for t in tools:
        cat = t["category"]
        if cat not in cats:
            continue
        if material_target and material_target not in (t.get("suitable_materials") or []):
            continue
        if diameter_mm is not None:
            d = t.get("diameter_mm")
            if d is None or abs(d - diameter_mm) > diameter_tolerance:
                continue

        # 分數計算
        score = 0.0
        warnings: List[str] = []

        # 1. 類別優先序（越前面越好）
        cat_rank = cats.index(cat)
        score += (10 - cat_rank) * 10

        # 2. 直徑接近度
        if diameter_mm is not None:
            d = t.get("diameter_mm") or 0
            score += max(0, 50 - abs(d - diameter_mm) * 100)

        # 3. 避空長度足夠
        if required_reach_mm:
            shoulder = t.get("shoulder_length_mm") or 0
            if shoulder >= required_reach_mm:
                score += 20
            else:
                warnings.append(f"避空 {shoulder}mm < 所需 {required_reach_mm}mm，撞刀風險")
                score -= 50

        # 4. 刀號優先（有刀號 → 已在機台上 → 加分）
        if t.get("tool_number"):
            score += 5

        # 5. 鋁料優先 ALUS 標籤 / 鋼料優先 CIB 標籤
        if material_target in ("AL6061", "AL7075", "Brass") and cat == "end_mill_alu":
            score += 30
        if material_target in ("S50C", "S45C", "SUS304", "SKD11") and cat == "end_mill_steel":
            score += 30

        candidates.append((score, t, "; ".join(warnings) if warnings else "OK"))

    candidates.sort(key=lambda x: -x[0])

    top = candidates[:5]
    return {
        "feature_type": feature_type,
        "material_target": material_target,
        "diameter_mm": diameter_mm,
        "required_reach_mm": required_reach_mm,
        "found": len(top),
        "best": (_compact_tool(top[0][1], warnings=top[0][2], score=top[0][0])
                 if top else None),
        "alternatives": [_compact_tool(t, warnings=w, score=s) for s, t, w in top[1:]],
        "preferred_categories": cats,
        "load_error": err,
    }


# ============================================================
# ★ 特定刀具 + 工法 preset 檢索 (GOLD STANDARD 查詢)
# ============================================================
# 設計 (用戶 2026.05): 「當有特定刀具就以刀具的表參數做依據,
#   沒有就以餵的資料做參考」
# 本地 preset 是用戶在自己機台跑過驗證的「上機值」, 比廠商官網表更準
#
# 銑刀類 preset name = 工法 (側銑/面銑/滿刃銑/插銑/層銑/孔銑/側壁精銑/測銑/長條孔)
# 鑽頭/絞刀/倒角刀 preset name = 材質 (S50C/AL6061/SKD11/ASP 23)

# 材質 → 偏好刀具類別 (用 _JOB_CATEGORY_PRIORITY 補)
# 大徑刀 (D≥30) 通常是面銑刀類, 加入 face_mill / bull_nose / ball_mill 候選
_MATERIAL_TO_END_MILL_CAT: Dict[str, List[str]] = {
    "AL6061":     ["end_mill_alu",   "face_mill", "bull_nose", "ball_mill", "end_mill"],
    "AL7075":     ["end_mill_alu",   "face_mill", "bull_nose", "ball_mill", "end_mill"],
    "Brass":      ["end_mill_alu",   "face_mill", "end_mill"],
    "Plastics":   ["end_mill_alu",   "end_mill"],
    "S50C":       ["end_mill_steel", "face_mill", "bull_nose", "ball_mill", "end_mill"],
    "S45C":       ["end_mill_steel", "face_mill", "bull_nose", "ball_mill", "end_mill"],
    "Cast_Iron":  ["end_mill_steel", "face_mill", "end_mill"],
    "SCM440":     ["end_mill_steel", "face_mill", "end_mill"],
    "NAK80":      ["end_mill_steel", "face_mill", "bull_nose", "ball_mill", "end_mill"],
    "HPM38":      ["end_mill_steel", "face_mill", "end_mill"],
    "S136":       ["end_mill_steel", "face_mill", "bull_nose", "end_mill"],
    "SKD11":      ["end_mill_steel", "face_mill", "end_mill"],
    "SKD61":      ["end_mill_steel", "end_mill"],
    "DC53":       ["end_mill_steel", "end_mill"],
    "SUS304":     ["end_mill_steel", "face_mill", "end_mill"],
    "SUS316":     ["end_mill_steel", "face_mill", "end_mill"],
    "SUS420":     ["end_mill_steel", "end_mill"],
    "Ti-6Al-4V":  ["end_mill_steel", "end_mill"],
    "TC4":        ["end_mill_steel", "end_mill"],
}

# 工法關鍵字 → 本地 preset name 候選 (按優先序)
_OPERATION_KEYWORDS: Dict[str, List[str]] = {
    # ── 中文 ──
    "面銑":      ["面銑"],
    "粗銑":      ["粗銑", "粗加工", "滿刃銑", "層銑"],
    "精銑":      ["精銑", "側壁精銑", "精加工"],
    "側銑":      ["側銑", "側壁精銑"],
    "層銑":      ["層銑"],
    "滿刃銑":    ["滿刃銑", "滿刃", "槽銑"],
    "插銑":      ["插銑", "Ramp"],
    "孔銑":      ["孔銑"],
    "側壁精銑":   ["側壁精銑", "精銑"],
    "輪廓":      ["側銑", "側壁精銑"],
    "切槽":      ["滿刃銑", "層銑"],
    "螺旋下刀":   ["插銑", "Ramp"],
    "長條孔":    ["長條孔", "孔銑"],
    "測銑":      ["測銑", "側銑"],
    # ── 英文/工法分類 ──
    "roughing":         ["粗銑", "滿刃銑", "層銑"],
    "face_roughing":    ["面銑", "粗銑"],
    "side_roughing":    ["側銑", "層銑"],
    "trochoidal":       ["側銑", "層銑"],  # 擺線通常用側銑路徑
    "finishing":        ["精銑", "側壁精銑"],
    "face_finishing":   ["面銑", "精銑"],
    "wall_finishing":   ["側壁精銑", "精銑"],
    "profile_finishing":["側壁精銑", "精銑"],
    "face":             ["面銑"],
    "side":             ["側銑"],
    "slot":             ["滿刃銑", "層銑"],
    "plunge":           ["插銑"],
    "helix_ramp":       ["插銑"],
    "contour":          ["側銑"],
    "pocket":           ["側銑", "層銑"],
    "milling":          ["側銑", "滿刃銑", "層銑", "粗銑", "精銑"],
}

# 鑽頭/絞刀/倒角刀 材質映射 (本地 preset name 用 Smart_AI_CAM 材質鍵)
_DRILL_MATERIAL_ALIASES: Dict[str, List[str]] = {
    "S50C":       ["S50C", "S45C", "FC", "鑄鐵"],
    "S45C":       ["S45C", "S50C"],
    "Cast_Iron":  ["S50C", "FC", "鑄鐵"],
    "AL6061":     ["AL6061", "AL7075", "鋁"],
    "AL7075":     ["AL7075", "AL6061"],
    "Brass":      ["AL6061", "黃銅"],          # 鑽頭打銅用鋁参數略保守
    "Plastics":   ["AL6061"],
    "SKD11":      ["SKD11", "SKD 11", "ASP 23"],
    "SKD61":      ["SKD11", "SKD 11"],
    "S136":       ["SKD11", "ASP 23"],
    "HPM38":      ["SKD11"],
    "SUS304":     ["SKD11", "S50C"],            # 不銹鋼鑽降 30%
    "SUS316":     ["SKD11", "S50C"],
    "Ti-6Al-4V":  ["SKD11"],                    # 鈦鑽 fallback 用 SKD11
}


def _resolve_operation_keywords(operation: str) -> List[str]:
    """工法字串 → preset name 候選 (按優先序匹配)。"""
    op = (operation or "").strip()
    if op in _OPERATION_KEYWORDS:
        return _OPERATION_KEYWORDS[op]
    # 小寫英文 fallback
    op_lo = op.lower()
    if op_lo in _OPERATION_KEYWORDS:
        return _OPERATION_KEYWORDS[op_lo]
    # 模糊匹配 (包含關係)
    for k, v in _OPERATION_KEYWORDS.items():
        if k in op or op in k:
            return v
    return ["側銑", "滿刃銑", "層銑"]  # 預設銑刀候選


def _select_preset_by_keywords(presets: List[Dict[str, Any]],
                               keywords: List[str]) -> Optional[Tuple[Dict[str, Any], str]]:
    """從 presets 找 name 包含關鍵字的 preset (依關鍵字順序)。"""
    for kw in keywords:
        for p in presets:
            nm = (p.get("name") or "").strip()
            if kw in nm and p.get("rpm"):
                return (p, nm)
    return None


def find_preset_for_query(material: str,
                          diameter_mm: float,
                          operation: str = "side",
                          feature_type: Optional[str] = None,
                          diameter_tolerance: float = 0.6,
                          category_hint: Optional[str] = None,
                          tool_id: Optional[int] = None,
                          root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """★ 特定刀具檢索 (GOLD STANDARD) — 找本地 preset 完全匹配。

    判斷邏輯 (依 feature_type 切換兩種模式):

    模式 A - 銑刀 (含面銑/球刀/圓鼻刀):
      1. 用「材質 → 刀類別」找候選 (AL6061→end_mill_alu, S50C→end_mill_steel)
      2. 直徑接近度排序, 取最近的
      3. 從該刀 presets 中找 name 含「operation 關鍵字」的 preset
      4. 回傳 (tool + preset) 或 None

    模式 B - 鑽頭/絞刀/倒角刀:
      1. 用 feature_type 找類別 (hole→drill, hole_ream→reamer, chamfer→chamfer)
      2. 直徑接近度排序
      3. 從該刀 presets 中找 name == material 的 preset (e.g. "S50C")
      4. 回傳 (tool + preset)

    Returns:
        {tool: {...}, preset: {...}, match_quality, confidence, source}
        或 None (沒命中)
    """
    tools, err = _load_tools(root)
    if not tools:
        return None

    # 1. 指定 tool_id 強制匹配
    if tool_id is not None:
        for t in tools:
            if t.get("tool_number") == int(tool_id):
                return _resolve_preset_from_tool(t, material, operation,
                                                 feature_type, match_quality="exact_tool_id")
        return None

    # 2. 判定刀類別候選
    fty = (feature_type or "").lower()
    is_drill_like = fty in ("hole", "drill", "drilling")
    is_ream = fty in ("hole_ream", "ream", "reamer", "reaming")
    is_tap = fty in ("hole_tap", "tap", "tapping")
    is_chamfer = fty in ("chamfer", "chamfering")
    is_center = fty in ("center", "center_drill")
    is_ball = fty in ("ball", "ball_mill", "ball_milling")

    if is_drill_like:
        cats = ["drill_carbide", "drill_sg", "drill_hss_co", "drill_hss", "drill"]
    elif is_ream:
        cats = ["reamer"]
    elif is_tap:
        cats = ["tap"]
    elif is_chamfer:
        cats = ["chamfer"]
    elif is_center:
        cats = ["center_drill"]
    elif is_ball:
        cats = ["ball_mill", "bull_nose"]
    elif category_hint:
        cats = [category_hint]
    else:
        # 銑刀預設: 用材質映射
        cats = _MATERIAL_TO_END_MILL_CAT.get(material, ["end_mill"])

    # 3. 收集候選刀具 (嚴格模式: 材質不匹配的刀具直接踢除)
    # 設計: L1 GOLD 必須是「該刀本來就是給這材質用」的 preset,
    #       否則 fallthrough 到 L2/L3 由廠商表 / 推斷引擎處理.
    candidates = []
    for t in tools:
        if t["category"] not in cats:
            continue
        d = t.get("diameter_mm")
        if d is None or abs(d - diameter_mm) > diameter_tolerance:
            continue
        if not t.get("presets"):
            continue
        # ★ 嚴格材質過濾: 若有 suitable_materials 標記但不含目標材質, 踢除
        # (鑽頭/絞刀/倒角刀等通用類預設 suitable_materials 寬鬆已不會被踢)
        suitable = t.get("suitable_materials") or []
        if suitable and material not in suitable:
            continue
        score = -abs(d - diameter_mm) * 100
        if t.get("tool_number"):
            score += 5
        # 類別優先級
        cat_rank = cats.index(t["category"])
        score += (10 - cat_rank) * 10
        candidates.append((score, t))

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])

    # 4. 從最佳候選依序找 preset
    for _, t in candidates[:5]:
        result = _resolve_preset_from_tool(t, material, operation,
                                           feature_type, match_quality="best_fit")
        if result:
            return result
    return None


def _resolve_preset_from_tool(t: Dict[str, Any],
                              material: str,
                              operation: str,
                              feature_type: Optional[str],
                              match_quality: str) -> Optional[Dict[str, Any]]:
    """從單一刀具找 preset, 區分銑刀/鑽頭兩種命名模式。"""
    presets = t.get("presets") or []
    if not presets:
        return None

    cat = t["category"]
    fty = (feature_type or "").lower()

    # 模式 B: 鑽頭/絞刀/倒角刀 — preset name = 材質
    if cat in ("drill_carbide", "drill_sg", "drill_hss", "drill_hss_co", "drill",
               "reamer", "tap", "chamfer", "center_drill", "face_mill",
               "bull_nose", "ball_mill"):
        # 嘗試材質匹配 (含別名)
        mat_aliases = _DRILL_MATERIAL_ALIASES.get(material, [material])
        for alias in mat_aliases:
            for p in presets:
                nm = (p.get("name") or "").strip()
                if alias.lower() == nm.lower() or alias in nm:
                    if p.get("rpm"):
                        return _format_preset_result(t, p, "material",
                                                     material, alias,
                                                     match_quality)
        # 找不到對應材質, 但這刀類別應該還是回工法 preset (面銑/倒角)
        # → 試試工法 keyword 匹配
        kws = _resolve_operation_keywords(operation)
        sel = _select_preset_by_keywords(presets, kws)
        if sel:
            return _format_preset_result(t, sel[0], "operation_fallback",
                                         material, sel[1], match_quality)
        return None

    # 模式 A: 銑刀 — preset name = 工法
    kws = _resolve_operation_keywords(operation)
    sel = _select_preset_by_keywords(presets, kws)
    if sel:
        return _format_preset_result(t, sel[0], "operation",
                                     material, sel[1], match_quality)
    return None


def _format_preset_result(t: Dict[str, Any],
                          p: Dict[str, Any],
                          match_mode: str,
                          material_query: str,
                          preset_matched: str,
                          match_quality: str) -> Dict[str, Any]:
    """格式化 GOLD STANDARD 結果, 統一給 cutting_resolver 用。"""
    rpm = p.get("rpm") or 0
    feed = p.get("feed_mm_min")
    vc = p.get("v_c_m_min")
    fz = p.get("f_z_mm_tooth")
    fn = p.get("f_n_mm_rev")
    return {
        "layer": "L1_GOLD_local_preset",
        "source": "Fusion 360 local tool library (user-validated)",
        "confidence": 0.95 if match_quality == "exact_tool_id" else 0.90,
        "match_mode": match_mode,  # "operation" | "material" | "operation_fallback"
        "preset_matched": preset_matched,
        "match_quality": match_quality,
        "tool": {
            "T": t.get("tool_number"),
            "description": t.get("description"),
            "category": t.get("category"),
            "category_zh": t.get("category_zh"),
            "D": t.get("diameter_mm"),
            "teeth": t.get("teeth"),
            "flute_len": t.get("flute_length_mm"),
            "shoulder_len": t.get("shoulder_length_mm"),
            "vendor": t.get("vendor"),
            "product_id": t.get("product_id"),
            "tool_material": t.get("material"),  # hss/carbide
            "suitable_for": t.get("suitable_materials"),
            "source_file": t.get("source_file"),
        },
        "params": {
            "rpm": rpm,
            "feed_mm_min": feed,
            "Vc_m_min": vc,
            "fz_mm_tooth": fz,
            "fn_mm_rev": fn,
            "feed_plunge": p.get("feed_plunge"),
            "feed_ramp": p.get("feed_ramp"),
            "ramp_angle_deg": p.get("ramp_angle_deg"),
            "stepdown_mm": p.get("stepdown_mm"),
            "stepover_mm": p.get("stepover_mm"),
            "coolant": p.get("coolant"),
        },
        "material_query": material_query,
        "note": (f"GOLD: 本地 preset 「{preset_matched}」匹配 "
                 f"T{t.get('tool_number')} D{t.get('diameter_mm')} "
                 f"({t.get('description')}) → "
                 f"RPM={rpm} F={feed} Vc={vc}"),
    }


def list_presets_for_tool(tool_id: int,
                          root: Optional[str] = None) -> Dict[str, Any]:
    """列出指定 T 編號刀具的所有 preset。"""
    tools, err = _load_tools(root)
    for t in tools:
        if t.get("tool_number") == int(tool_id):
            return {
                "success": True,
                "tool": _compact_tool(t),
                "presets": t.get("presets") or [],
                "preset_count": len(t.get("presets") or []),
            }
    return {"success": False, "error": f"T{tool_id} 不存在於本地刀具庫"}


# ============================================================
# 既有的 _compact_tool 與 dispatch (繼續)
# ============================================================

def _compact_tool(t: Dict[str, Any], warnings: str = "", score: float = 0.0) -> Dict[str, Any]:
    """精簡版刀具資料給 LLM (省 token)。"""
    out = {
        "T": t.get("tool_number"),
        "description": t.get("description"),
        "category": t.get("category"),
        "category_zh": t.get("category_zh"),
        "D": t.get("diameter_mm"),
        "teeth": t.get("teeth"),
        "flute_len": t.get("flute_length_mm"),
        "shoulder_len": t.get("shoulder_length_mm"),
        "tip_angle": t.get("tip_angle_deg"),
        "material": t.get("material"),
        "vendor": t.get("vendor"),
        "product_id": t.get("product_id"),
        "suitable_for": t.get("suitable_materials"),
        "source": t.get("source_file"),
    }
    # 去掉 None 省空間
    out = {k: v for k, v in out.items() if v not in (None, "", 0)}
    if score:
        out["_score"] = round(score, 1)
    if warnings and warnings != "OK":
        out["_warn"] = warnings
    return out


# ============================================================
# Entry dispatch (給 MCP 調用)
# ============================================================

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point。

    params 範例：
      {"mode": "stats"}
      {"mode": "list", "category": "end_mill_alu", "limit": 20}
      {"mode": "search", "diameter_mm": 6, "material_target": "S50C"}
      {"mode": "find_best", "feature_type": "contour", "material_target": "S50C",
       "diameter_mm": 6, "required_reach_mm": 15}
    """
    mode = (params.get("mode") or "stats").lower()
    root = params.get("library_path")

    if mode == "stats":
        return {"success": True, "data": stats(root=root)}

    elif mode == "list":
        try:
            return {"success": True, "data": list_by_category(
                category=params.get("category"),
                limit=int(params.get("limit") or 100),
                root=root,
            )}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif mode == "search":
        try:
            return {"success": True, "data": search(
                diameter_mm=_to_float(params.get("diameter_mm")),
                diameter_tolerance=float(params.get("diameter_tolerance") or 0.5),
                category=params.get("category"),
                material_target=params.get("material_target"),
                teeth_min=_to_int(params.get("teeth_min")),
                teeth_max=_to_int(params.get("teeth_max")),
                tool_material=params.get("tool_material"),
                limit=int(params.get("limit") or 30),
                root=root,
            )}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif mode == "find_best":
        feature_type = params.get("feature_type")
        material_target = params.get("material_target")
        if not feature_type or not material_target:
            return {"success": False,
                    "error": "find_best 模式需 feature_type 與 material_target"}
        try:
            return {"success": True, "data": find_best(
                feature_type=feature_type,
                material_target=material_target,
                diameter_mm=_to_float(params.get("diameter_mm")),
                diameter_tolerance=float(params.get("diameter_tolerance") or 0.5),
                required_reach_mm=_to_float(params.get("required_reach_mm")),
                root=root,
            )}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif mode == "find_preset":
        # ★ GOLD STANDARD: 找本地 preset 完全匹配 (用戶 2026.05 設計)
        material = params.get("material") or params.get("material_target")
        D = _to_float(params.get("diameter_mm"))
        operation = params.get("operation") or "side"
        if not material or D is None:
            return {"success": False,
                    "error": "find_preset 需 material 與 diameter_mm"}
        try:
            result = find_preset_for_query(
                material=material,
                diameter_mm=D,
                operation=operation,
                feature_type=params.get("feature_type"),
                diameter_tolerance=float(params.get("diameter_tolerance") or 0.6),
                category_hint=params.get("category_hint"),
                tool_id=_to_int(params.get("tool_id")),
                root=root,
            )
            if result is None:
                return {"success": True, "data": None,
                        "note": "本地刀具庫沒有匹配的 preset, 請改用廠商表 (L2) 或推斷 (L3)"}
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif mode == "list_presets":
        tool_id = _to_int(params.get("tool_id"))
        if tool_id is None:
            return {"success": False, "error": "list_presets 需 tool_id (T 編號)"}
        try:
            return {"success": True, "data": list_presets_for_tool(tool_id, root)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    else:
        return {"success": False,
                "error": f"未知 mode: {mode}",
                "valid_modes": ["stats", "list", "search", "find_best",
                                "find_preset", "list_presets"]}


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
