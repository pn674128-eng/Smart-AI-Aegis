# -*- coding: utf-8 -*-
r"""
CNC 加工推斷引擎 (Machining Heuristics)
==========================================
用戶設計哲學 (2026.05):
  「以表中的轉速進給去換算其他刀具,
   並不一定全部都要有, 推斷也是 CNC 加工的重點」
  「大徑要考慮的就是機台剛性 + 刀把剛性 + 刀具材質剛性,
   任何物質都有其上限值」

本模組編碼 3 條鐵則:
  鐵則 ① 工法折扣 (粗 / 精 / 側壁精 / 擺線 / 插銑 ...)
  鐵則 ② 三層剛性鏈 + 材質物理上限 (Vc 飽和 / F 功率封頂)
  鐵則 ③ 「先動 ae/ap/f 再動 V/S」調參優先序

→ 提供 6 條核心推斷規則 API, 讓 cam-helper 在缺表時也能推算合理參數
→ 廠商錨點表 (keili_catalog.params_table_official) 是「上限值」,
  本模組是「中間值/變換規則」

數據來源:
  - 奇力揚官網 ALUS / CIB 切削表 (用戶 2026.05 提供)
  - 用戶 Mazak i600 Ti-6Al-4V 試算表 (內部上機值)
  - 用戶口述工程心法 (散件 75/50 折 / 三層剛性 / 物質上限)
"""

from typing import Any, Dict, List, Optional, Tuple
import math


# ═══════════════════════════════════════════════════════════════════════
#  鐵則 ① 工法折扣表 (對任何系列普適)
# ═══════════════════════════════════════════════════════════════════════
# 數據錨點: 用戶 Mazak i600 Ti6Al4V 試算表
# 規律: 粗→精 Vc ↓5-15%, fz ↓30-45% (精銑核心: fz 變小避免擦削)
# 註: vc_factor 與 fz_factor 相對「粗加工 (roughing) = 1.0」

OPERATION_FACTORS: Dict[str, Dict[str, Any]] = {
    # ─── 粗加工系列 (Vc/fz 滿表) ───
    "roughing": {
        "name_zh": "粗銑 (面銑/側銑/擺線通用)",
        "vc_factor": 1.00,
        "fz_factor": 1.00,
        "ae_pct_range": (0.35, 0.60),  # 35-60% D
        "ap_pct_range": (0.25, 0.45),  # 0.25-0.45 D
        "note": "粗銑/半粗銑共用 Vc 與 fz",
    },
    "face_roughing": {
        "name_zh": "面銑粗加工",
        "vc_factor": 1.00,
        "fz_factor": 1.00,
        "ae_pct_range": (0.35, 0.60),
        "ap_pct_range": (0.25, 0.45),
        "note": "大面順銑; 轉角減載",
    },
    "side_roughing": {
        "name_zh": "側銑粗加工",
        "vc_factor": 1.00,
        "fz_factor": 1.00,
        "ae_pct_range": (0.08, 0.20),  # 8-20% D
        "ap_pct_range": (0.20, 0.40),
        "note": "伸出長取下端; 順銑; 轉角注意尖峰",
    },
    "trochoidal": {
        "name_zh": "擺線銑 / 動態粗銑",
        "vc_factor": 1.00,
        "fz_factor": 1.00,
        "ae_pct_range": (0.10, 0.22),  # 起步 10-18%, 穩定後 ≤ 22%
        "ap_pct_range": (0.35, 0.70),  # 軸向可吃深
        "note": "ae 小但 ap 大, 優先調 ae 步距",
    },

    # ─── 精加工系列 (Vc 微降, fz 大降) ───
    "face_finishing": {
        "name_zh": "面精銑",
        "vc_factor": 0.92,   # 78 → 72 (Ti 試算佐證)
        "fz_factor": 0.70,   # 0.030 → 0.020
        "ae_pct_range": (0.25, 0.45),
        "ap_pct_range": (0.03, 0.12),  # 可分 1-2 次
        "note": "精銑 fz 較小避免擦削; 冷卻對準刃口",
    },
    "wall_finishing": {
        "name_zh": "側壁精銑",
        "vc_factor": 0.87,   # 78 → 68
        "fz_factor": 0.55,   # 0.030 → 0.018
        "ae_pct_range": (0.03, 0.08),  # 薄削 3-8% D 或留 0.1-0.2mm
        "ap_pct_range": (1.0, 1.0),    # 一次拉深為主
        "note": "側壁餘量+同軸; 深件可分 2 段拉深",
    },
    "profile_finishing": {
        "name_zh": "輪廓精銑 (側壁精的別名)",
        "vc_factor": 0.87,
        "fz_factor": 0.55,
        "ae_pct_range": (0.03, 0.08),
        "ap_pct_range": (1.0, 1.0),
        "note": "= wall_finishing",
    },

    # ─── 特殊工法 (Vc/fz/F 都要大降) ───
    "plunge": {
        "name_zh": "插銑 / 垂直下刀",
        "vc_factor": 0.50,
        "fz_factor": 0.50,
        "ae_pct_range": None,   # 不適用 ae
        "ap_pct_range": None,
        "note": "刃口承受純軸向力, 排屑差 → V/F 各砍半",
    },
    "helix_ramp": {
        "name_zh": "螺旋下刀 / Ramp",
        "vc_factor": 0.70,
        "fz_factor": 0.50,
        "ae_pct_range": (0.0, 0.5),    # 寬度漸進
        "ap_pct_range": None,           # 由 helix angle 控
        "note": "Ramp angle 1-3° 為佳; 不可超 5°",
    },
    "slot": {
        "name_zh": "溝銑 (槽銑) / 全寬切削",
        "vc_factor": 0.85,
        "fz_factor": 0.85,
        "ae_pct_range": (1.0, 1.0),    # 1D 全寬
        "ap_pct_range": (0.5, 1.0),
        "note": "Ae=1D 排屑差, 廠商表給的 Slot 表已內建此降速",
    },
    "drilling": {
        "name_zh": "鑽孔",
        "vc_factor": 1.00,   # 鑽頭用 fr (mm/rev), 不適用 fz_factor
        "fz_factor": 1.00,
        "ae_pct_range": (1.0, 1.0),
        "ap_pct_range": (0.5, 6.0),    # 鑽深可 ≤ 6D, 超過要啄鑽
        "note": "深徑比 > 3D 啟動啄鑽; 鈦合金深孔 > 5D 必須啄",
    },
    "tapping": {
        "name_zh": "攻牙",
        "vc_factor": 1.00,   # 攻牙用 V_tap_m_min, 跟銑刀不同尺度
        "fz_factor": 1.00,
        "ae_pct_range": (1.0, 1.0),
        "ap_pct_range": None,
        "note": "F = S × pitch (剛性同步); 鋁可 V20, 不銹鋼僅 V4-6",
    },
    "thread_milling": {
        "name_zh": "螺紋銑削",
        "vc_factor": 0.70,
        "fz_factor": 0.50,
        "ae_pct_range": None,
        "ap_pct_range": None,
        "note": "螺紋銑刃口接觸短, fz 要小 (避免崩刃)",
    },
}


def get_operation_factors(operation: str) -> Dict[str, Any]:
    """取得工法折扣係數。未知工法回傳 roughing 預設並警告。"""
    op = (operation or "roughing").lower().replace("-", "_")
    if op in OPERATION_FACTORS:
        return {**OPERATION_FACTORS[op], "operation_key": op}
    # 容錯別名
    aliases = {
        "rough":             "roughing",
        "face":              "face_roughing",
        "side":              "side_roughing",
        "contour":           "side_roughing",
        "adaptive":          "trochoidal",
        "high_speed":        "trochoidal",
        "facing":            "face_finishing",
        "finish":            "face_finishing",
        "finishing":         "face_finishing",
        "wall":              "wall_finishing",
        "profile":           "profile_finishing",
        "ramp":              "helix_ramp",
        "helix":             "helix_ramp",
        "slot_milling":      "slot",
        "slotting":          "slot",
        "drill":             "drilling",
        "tap":               "tapping",
    }
    if op in aliases:
        key = aliases[op]
        return {**OPERATION_FACTORS[key], "operation_key": key,
                "alias_resolved_from": operation}
    return {**OPERATION_FACTORS["roughing"], "operation_key": "roughing",
            "warning": f"未知工法 '{operation}', 套用 roughing 預設"}


# ═══════════════════════════════════════════════════════════════════════
#  鐵則 ② 三層剛性鏈 + 物質上限 (Vc 飽和 / F 功率封頂)
# ═══════════════════════════════════════════════════════════════════════

# ── 2a. 材質 Vc 物理上限 (任何刀具不能突破) ──
# 數據來源:
#   - ALUS 官網表 D ≥ 10 Vc 飽和於 250 m/min
#   - CIB 官網表 D ≥ 10 碳鋼 Vc 飽和於 120 m/min
#   - 用戶 Ti6Al4V 試算 Vc 最高 78 m/min

# ─────────────────────────────────────────────────────────────────
# ★ 重要設計 (用戶 2026.05 指示): 材質鍵預設 = 「出貨/常態」硬度
# 同一材質鍵, 不同熱處理狀態 Vc 上限可差 50%+
#
#   未淬火 (退火/出貨態)        ─ 用戶實機粗加工時的常態
#       SKD11      ~HRC 20-25   Vc ≤ 130  (跟 S50C 接近)
#       S136       ~HRC 20      Vc ≤ 130
#       DC53       ~HRC 20      Vc ≤ 130
#       SKD61      ~HRC 20      Vc ≤ 130
#
#   預硬鋼 (出廠已預質)         ─ 不需另外熱處理
#       NAK80      ~HRC 38-42   Vc ≤ 110
#       HPM38      ~HRC 32-38   Vc ≤ 110
#       SCM440     ~HRC 28-32   Vc ≤ 120
#
#   淬火態 (用 _hardened 後綴指定)  ─ 精加工/模具光整階段
#       SKD11_hardened   ~HRC 58-62   Vc ≤ 80
#       S136_hardened    ~HRC 50-53   Vc ≤ 100
#       DC53_hardened    ~HRC 60+     Vc ≤ 75
#       SKD61_hardened   ~HRC 48-52   Vc ≤ 100
#
# 用法: 預設 material="SKD11" 走退火態; 要切淬火態請傳:
#   material="SKD11_hardened" 或 material="SKD11" + hardness_hrc=58
# ─────────────────────────────────────────────────────────────────

VC_CEILING: Dict[str, Dict[str, Any]] = {
    # ─── 鋁/銅/塑膠 ───
    "AL6061":     {"Vc_ceiling": 250, "D_saturate": 10, "hrc_typical": 0,
                   "note": "鋁合金 6 系, 散熱好可衝高 Vc"},
    "AL7075":     {"Vc_ceiling": 250, "D_saturate": 10, "hrc_typical": 0,
                   "note": "鋁合金 7 系, 跟 6061 上限相同"},
    "Brass":      {"Vc_ceiling": 350, "D_saturate": 8,  "hrc_typical": 0,
                   "note": "黃銅 Vc 可比鋁高 40%"},
    "Copper":     {"Vc_ceiling": 350, "D_saturate": 8,  "hrc_typical": 0,
                   "note": "純銅 (C1020 級)"},
    "Plastics":   {"Vc_ceiling": 400, "D_saturate": 6,  "hrc_typical": 0,
                   "note": "POM/Nylon 可衝, Acrylic 要降避免熔"},
    # ─── 碳鋼/鑄鐵 ───
    "S50C":       {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 20,
                   "note": "碳鋼 ~20HRC, CIB 表上限"},
    "S45C":       {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 18,
                   "note": "= S50C 範圍"},
    "Cast_Iron":  {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 22,
                   "note": "FC 灰口鑄鐵"},
    # ─── 預質鋼 (出廠就有硬度, 不需熱處理) ───
    "SCM440":     {"Vc_ceiling": 120, "D_saturate": 10, "hrc_typical": 30,
                   "note": "合金鋼調質 ~30HRC"},
    "NAK80":      {"Vc_ceiling": 110, "D_saturate": 10, "hrc_typical": 40,
                   "note": "預質鋼 ~40HRC (出貨即預硬)"},
    "HPM38":      {"Vc_ceiling": 110, "D_saturate": 10, "hrc_typical": 36,
                   "note": "預質模具鋼 ~36HRC"},
    # ─── 模具鋼: 預設 = 退火/出貨態 (用戶實機粗加工常態) ───
    "S136":       {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 20,
                   "note": "模具鋼出貨退火 ~20HRC, 跟 S50C 等級"},
    "SKD11":      {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 22,
                   "note": "冷作工具鋼退火 ~22HRC (出貨態), 跟 S50C 接近"},
    "SKD61":      {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 20,
                   "note": "熱作工具鋼退火 ~20HRC (出貨態)"},
    "DC53":       {"Vc_ceiling": 130, "D_saturate": 10, "hrc_typical": 22,
                   "note": "改良冷作工具鋼退火 ~22HRC (出貨態)"},
    # ─── 模具鋼: 淬火態 (用 _hardened 後綴指定) ───
    "SKD11_hardened":  {"Vc_ceiling": 80,  "D_saturate": 8, "hrc_typical": 60,
                        "note": "★淬火態 SKD11 ~HRC 58-62, Vc 大降"},
    "S136_hardened":   {"Vc_ceiling": 100, "D_saturate": 8, "hrc_typical": 52,
                        "note": "★淬火態 S136 ~HRC 50-53"},
    "DC53_hardened":   {"Vc_ceiling": 75,  "D_saturate": 8, "hrc_typical": 60,
                        "note": "★淬火態 DC53 ~HRC 60+"},
    "SKD61_hardened":  {"Vc_ceiling": 100, "D_saturate": 8, "hrc_typical": 50,
                        "note": "★淬火態 SKD61 ~HRC 48-52"},
    "ASP23":           {"Vc_ceiling": 80,  "D_saturate": 8, "hrc_typical": 62,
                        "note": "粉末高速鋼, 出廠就 60HRC+"},
    "SKH9":            {"Vc_ceiling": 80,  "D_saturate": 8, "hrc_typical": 60,
                        "note": "高速鋼 HRC 60+"},
    # ─── 不銹鋼 ───
    "SUS304":     {"Vc_ceiling": 80,  "D_saturate": 8, "hrc_typical": 18,
                   "note": "奧氏體不銹鋼, 加工硬化嚴重要保守"},
    "SUS316":     {"Vc_ceiling": 80,  "D_saturate": 8, "hrc_typical": 18,
                   "note": "= 304 等級 Vc"},
    "SUS420":     {"Vc_ceiling": 75,  "D_saturate": 8, "hrc_typical": 22,
                   "note": "馬氏體不銹鋼"},
    "SUS440":     {"Vc_ceiling": 70,  "D_saturate": 8, "hrc_typical": 30,
                   "note": "高鉻馬氏體不銹鋼"},
    # ─── 鈦/超合金 ───
    "Ti-6Al-4V":  {"Vc_ceiling": 78,  "D_saturate": 6, "hrc_typical": 36,
                   "note": "鈦合金 (用戶 Mazak i600 試算佐證)"},
    "TC4":        {"Vc_ceiling": 78,  "D_saturate": 6, "hrc_typical": 36,
                   "note": "= Ti-6Al-4V 中國牌號"},
    "Inconel":    {"Vc_ceiling": 40,  "D_saturate": 6, "hrc_typical": 30,
                   "note": "鎳基超合金, 切削極度困難"},
}


# 材質鍵正規化: SKD11_hardened / SKD11_quenched / SKD11淬 → SKD11_hardened
_MATERIAL_ALIASES: Dict[str, str] = {
    "SKD11_quenched": "SKD11_hardened",
    "SKD11淬":        "SKD11_hardened",
    "SKD11淬火":      "SKD11_hardened",
    "SKD11_HRC58":    "SKD11_hardened",
    "SKD11_HRC60":    "SKD11_hardened",
    "S136淬":         "S136_hardened",
    "S136淬火":       "S136_hardened",
    "S136_HRC52":     "S136_hardened",
    "DC53淬":         "DC53_hardened",
    "SKD61淬":        "SKD61_hardened",
    "SCM":            "SCM440",
}


def normalize_material(material: str,
                       hardness_hrc: Optional[float] = None) -> str:
    """正規化材質鍵, 並依 hardness_hrc 自動切換淬火/退火態。

    範例:
        normalize_material("SKD11") → "SKD11"           (退火態)
        normalize_material("SKD11_淬火") → "SKD11_hardened"
        normalize_material("SKD11", hardness_hrc=58) → "SKD11_hardened"
        normalize_material("SKD11", hardness_hrc=22) → "SKD11"
    """
    if not material:
        return material
    m = material.strip()
    # 1. 別名映射
    if m in _MATERIAL_ALIASES:
        m = _MATERIAL_ALIASES[m]
    # 2. 依 hardness_hrc 自動切換 (僅對「有淬火態變體」的材質)
    if hardness_hrc is not None:
        base = m.replace("_hardened", "")
        hardened_key = f"{base}_hardened"
        if hardened_key in VC_CEILING:
            # 有淬火態變體 → 依 HRC 判斷
            base_hrc = VC_CEILING.get(base, {}).get("hrc_typical", 0)
            hardened_hrc = VC_CEILING[hardened_key]["hrc_typical"]
            threshold = (base_hrc + hardened_hrc) / 2  # 兩態中間值當門檻
            return hardened_key if hardness_hrc >= threshold else base
    return m


def get_vc_ceiling(material: str) -> Dict[str, Any]:
    """取得材質 Vc 物理上限。未知材質回傳鋼料預設保守值。"""
    m = (material or "").strip()
    if m in VC_CEILING:
        return {**VC_CEILING[m], "material": m, "source": "user_validated"}
    return {"Vc_ceiling": 100, "D_saturate": 10, "material": m,
            "note": f"未知材質 '{material}', 預設保守 Vc≤100 m/min",
            "source": "default_fallback"}


# ── 2b. 刀具材質剛性係數 (對碳化鎢=1.0) ──
# 用法: HSS 鑽頭打鋼 Vc = 鎢鋼基準 × 0.25

TOOL_MATERIAL_FACTOR: Dict[str, Dict[str, Any]] = {
    "HSS": {
        "name_zh": "高速鋼 (HSS)",
        "vc_factor": 0.25,
        "rigidity": "低",
        "typical_uses": ["手攻", "傳統麻花鑽", "便宜端銑"],
        "note": "Vc 是鎢鋼的 1/4, 但延展性好不易崩",
    },
    "HSS-Co": {
        "name_zh": "含鈷高速鋼 (HSS-Co)",
        "vc_factor": 0.35,
        "rigidity": "中低",
        "typical_uses": ["攻牙刀", "難加工材鑽頭"],
        "note": "鈷 5-8% 強化耐熱, 用於不銹鋼/鈦合金攻牙",
    },
    "Powder_HSS": {
        "name_zh": "粉末高速鋼 (PM-HSS)",
        "vc_factor": 0.45,
        "rigidity": "中",
        "typical_uses": ["精密鑽頭", "絞刀", "成型刀"],
        "note": "如 NACHI LIST7570P SG-ES, 介於 HSS 與鎢鋼間",
    },
    "Carbide": {
        "name_zh": "鎢鋼 (硬質合金/WC)",
        "vc_factor": 1.00,
        "rigidity": "高",
        "typical_uses": ["銑刀", "鑽頭", "車刀"],
        "note": "基準值, 多數廠商表以此為準",
    },
    "Carbide_coated": {
        "name_zh": "塗層鎢鋼 (TiAlN/AlCrN/UMG)",
        "vc_factor": 1.20,
        "rigidity": "高",
        "typical_uses": ["高效銑刀", "難加工材銑刀"],
        "note": "塗層降低摩擦, Vc 可上修 20%",
    },
    "Cermet": {
        "name_zh": "金屬陶瓷 (Cermet)",
        "vc_factor": 1.50,
        "rigidity": "高",
        "typical_uses": ["精車", "精銑鋼料"],
        "note": "鋼料精加工專用, Vc 比鎢鋼高 50%",
    },
    "PCD": {
        "name_zh": "聚晶鑽石 (PCD)",
        "vc_factor": 3.00,
        "rigidity": "極高",
        "typical_uses": ["鋁加工", "銅加工", "碳纖維"],
        "note": "不能打鐵 (碳會擴散到鐵裡), 但鋁可衝 Vc 1000+",
    },
    "CBN": {
        "name_zh": "立方氮化硼 (CBN)",
        "vc_factor": 2.50,
        "rigidity": "極高",
        "typical_uses": ["淬火鋼 HRC50+", "鑄鐵", "高速精車"],
        "note": "HRC ≥ 50 的鋼料專用, Vc 是鎢鋼的 2.5 倍",
    },
}


def get_tool_material_factor(tool_material: str) -> Dict[str, Any]:
    """取得刀具材質係數。"""
    m = (tool_material or "Carbide").strip()
    # 別名容錯
    aliases = {
        "WC":               "Carbide",
        "carbide":          "Carbide",
        "鎢鋼":             "Carbide",
        "硬質合金":         "Carbide",
        "HSSE":             "HSS-Co",
        "HSS_Co":           "HSS-Co",
        "含鈷高速鋼":       "HSS-Co",
        "高速鋼":           "HSS",
        "粉末高速鋼":       "Powder_HSS",
        "SG":               "Powder_HSS",
        "SG-ES":            "Powder_HSS",
        "塗層":             "Carbide_coated",
        "TiAlN":            "Carbide_coated",
        "AlCrN":            "Carbide_coated",
        "UMG":              "Carbide_coated",
        "鑽石":             "PCD",
        "聚晶鑽石":         "PCD",
        "氮化硼":           "CBN",
    }
    if m in TOOL_MATERIAL_FACTOR:
        return {**TOOL_MATERIAL_FACTOR[m], "tool_material_key": m}
    if m in aliases:
        k = aliases[m]
        return {**TOOL_MATERIAL_FACTOR[k], "tool_material_key": k,
                "alias_resolved_from": tool_material}
    return {**TOOL_MATERIAL_FACTOR["Carbide"], "tool_material_key": "Carbide",
            "warning": f"未知刀具材質 '{tool_material}', 套用鎢鋼預設"}


# ── 2c. 機台主軸功率 F 上限 (mm/min/kW × 機台 kW) ──
# 鐵則: F_max = spindle_kW × material_factor
# 用戶機台 (Mazak i600) 標稱主軸功率約 7.5-15 kW (依配置)

SPINDLE_F_FACTOR: Dict[str, Dict[str, Any]] = {
    # ★ 2026.05 校正: 用戶實機 S50C D=10 face F=1273 / 7.5kW ≈ 170/kW
    # 動態側銑 F=1273 (ae=0.3 ap=20 MRR=7639) 也要過得了 → 拉高到 200
    "aluminum": {
        "materials": ["AL6061", "AL7075", "Brass", "Plastics", "Copper"],
        "f_per_kw":   400,  # 用戶 AL6061 D=6 F=1500 = 200/kW, 留 buffer
        "note": "鋁/塑膠加工切削力小, F 可衝高",
    },
    "carbon_steel": {
        "materials": ["S50C", "S45C", "Cast_Iron", "SCM"],
        "f_per_kw":   200,  # 用戶 S50C D=10 F=1273 反推 170, 留 buffer
        "note": "碳鋼/鑄鐵中等切削力",
    },
    "alloy_steel": {
        "materials": ["SCM440", "NAK80", "HPM38"],
        "f_per_kw":   130,
        "note": "合金鋼 30-45HRC 切削力較高",
    },
    "hardened_steel": {
        "materials": ["S136", "SKD11", "SKD61", "DC53",
                      "SKD11_hardened", "SKD61_hardened", "S136_hardened"],
        "f_per_kw":   90,
        "note": "淬火鋼切削力大, 但硬車本來就低 F",
    },
    "stainless": {
        "materials": ["SUS304", "SUS316", "SUS420", "SUS440"],
        "f_per_kw":   90,
        "note": "不銹鋼加工硬化 F 要保守",
    },
    "titanium": {
        "materials": ["Ti-6Al-4V", "TC4"],
        "f_per_kw":   70,
        "note": "鈦合金切削阻力大, F 上限低",
    },
    "nickel_alloy": {
        "materials": ["Inconel"],
        "f_per_kw":   50,
        "note": "鎳基超合金, 切削阻力極大",
    },
}


def get_feed_ceiling(material: str, spindle_kw: float = 7.5) -> Dict[str, Any]:
    """計算主軸功率 F 上限 (mm/min)。預設 7.5 kW (一般 CNC)。"""
    m = (material or "").strip()
    for key, group in SPINDLE_F_FACTOR.items():
        if m in group["materials"]:
            return {
                "F_ceiling_mm_min": int(spindle_kw * group["f_per_kw"]),
                "spindle_kw": spindle_kw,
                "f_per_kw": group["f_per_kw"],
                "material_group": key,
                "note": group["note"],
            }
    return {
        "F_ceiling_mm_min": int(spindle_kw * 80),  # 預設中等切削力
        "spindle_kw": spindle_kw,
        "f_per_kw": 80,
        "material_group": "default",
        "note": f"未知材質 '{material}', 套保守 80 mm/min/kW",
    }


# ═══════════════════════════════════════════════════════════════════════
#  鐵則 ③ 跨材質換算規律 (用戶實機鐵則)
# ═══════════════════════════════════════════════════════════════════════
# 鐵律 (用戶實機反推): SUS316 → Ti6Al4V = Vc×0.7, fz×0.7
#   → F 自然 = Vc×fz×Z = 原 F × 0.49 (≈ 50%)
#   即 "F 砍半" 是 RPM 和 fz 各 ×0.7 後的自然結果, 不額外再降
#
# 公式: RPM_new = RPM_old × vc_factor
#       F_new   = F_old   × vc_factor × fz_factor
#       (因 F = RPM × fz × Z, fz 比例就是 fz_factor)

MATERIAL_SUBSTITUTION: Dict[Tuple[str, str], Dict[str, Any]] = {
    # ─── 用戶實機驗證的對映 ───
    ("SUS316", "Ti-6Al-4V"): {
        "vc_factor": 0.70, "fz_factor": 0.70,
        "note": "用戶試算 D20: SUS316 S=2387 F=1003 → Ti S=1671 F=491 "
                "(實機選 F=500, 誤差 < 2%)",
    },
    ("SUS304", "Ti-6Al-4V"): {
        "vc_factor": 0.70, "fz_factor": 0.70,
        "note": "等同 SUS316",
    },
    # ─── 從 Vc_ceiling 比值推算的對映 (推斷規則) ───
    ("S50C", "SUS304"): {
        "vc_factor": 0.65,  # 80/130
        "fz_factor": 0.80,
        "note": "Vc 上限比 = 80/130 ≈ 65%, fz 額外保守 (加工硬化)",
    },
    ("S50C", "Ti-6Al-4V"): {
        "vc_factor": 0.60,  # 78/130
        "fz_factor": 0.65,
        "note": "鈦比鋼難切, Vc 60% fz 65% (F 自然 ×0.39)",
    },
    ("AL6061", "AL7075"): {
        "vc_factor": 0.85, "fz_factor": 0.85,
        "note": "7075 較硬, Vc/fz 各降 15%",
    },
    ("S50C", "SCM440"): {
        "vc_factor": 0.92,  # 120/130
        "fz_factor": 0.90,
        "note": "30HRC 合金鋼比 S50C 略保守",
    },
    ("S50C", "NAK80"): {
        "vc_factor": 0.85,  # 110/130
        "fz_factor": 0.75,
        "note": "40HRC 預質鋼, Vc 上限 110",
    },
    ("S50C", "SKD11"): {
        "vc_factor": 0.77,  # 100/130
        "fz_factor": 0.60,
        "note": "淬火 58HRC, 需用塗層或 CBN 刀",
    },
}


def substitute_material(from_material: str,
                        to_material: str,
                        rpm: float,
                        feed: float) -> Dict[str, Any]:
    """從已知材質的 RPM/F 推算目標材質的 RPM/F。

    使用 user 提供的實機對映表; 找不到時用 Vc_ceiling 比值推算。

    Args:
        from_material: 已知參數的材質 (e.g. "SUS316")
        to_material:   要換算到的材質 (e.g. "Ti-6Al-4V")
        rpm:           已知 RPM
        feed:          已知 Feed (mm/min)

    Returns:
        {rpm, feed, vc_factor, fz_factor, source}
    """
    key = (from_material, to_material)
    if key in MATERIAL_SUBSTITUTION:
        sub = MATERIAL_SUBSTITUTION[key]
        vf = float(sub["vc_factor"])
        ff = float(sub.get("fz_factor", vf))
        # F = RPM × fz × Z, 所以 F_new/F_old = vf × ff
        return {
            "rpm": int(round(rpm * vf)),
            "feed": int(round(feed * vf * ff)),
            "vc_factor": vf,
            "fz_factor": ff,
            "source": "user_validated_table",
            "note": sub["note"],
        }
    # 找不到實機對映 → 用 Vc_ceiling 比值推算 (推斷規則)
    a = get_vc_ceiling(from_material)
    b = get_vc_ceiling(to_material)
    if a["Vc_ceiling"] and b["Vc_ceiling"]:
        vf = b["Vc_ceiling"] / a["Vc_ceiling"]
        return {
            "rpm": int(round(rpm * vf)),
            "feed": int(round(feed * vf * vf)),  # 進給 ~Vc^2 (因 fz 也要降)
            "vc_factor": round(vf, 3),
            "fz_factor": round(vf, 3),
            "source": "vc_ceiling_extrapolation",
            "note": (f"沒有 {from_material}→{to_material} 實機對映, "
                     f"用 Vc 上限比 {b['Vc_ceiling']}/{a['Vc_ceiling']}"
                     f"={vf:.2f} 推算"),
        }
    return {"error": f"無法推算 {from_material} → {to_material}",
            "rpm": int(rpm), "feed": int(feed)}


# ═══════════════════════════════════════════════════════════════════════
#  鐵則 ② 收尾: 應用所有上限到計算結果
# ═══════════════════════════════════════════════════════════════════════

def apply_ceilings(material: str,
                   tool_dia: float,
                   rpm_calc: float,
                   feed_calc: float,
                   spindle_kw: float = 7.5,
                   spindle_rpm_max: int = 12000,
                   hardness_hrc: Optional[float] = None) -> Dict[str, Any]:
    """套用所有物理上限到計算結果, 回傳被鉗制後的 (rpm, feed) 與審計軌跡。

    階層 (從上而下檢查):
      ① 主軸 RPM 硬上限 (機台規格)
      ② 材質 Vc 飽和線 (大徑反推 RPM)
      ③ 主軸功率 F 上限 (材質 × kW)

    Args:
        hardness_hrc: 若提供, 自動把材質鍵正規化到對應熱處理狀態
                      (e.g. SKD11 + 58HRC → SKD11_hardened)
    """
    # ★ 0. 先正規化材質鍵 (處理 SKD11/SKD11_hardened 二態問題)
    material = normalize_material(material, hardness_hrc=hardness_hrc)

    clamps: List[str] = []
    rpm_final = float(rpm_calc)
    feed_final = float(feed_calc)

    # ① 主軸 RPM 硬上限
    if rpm_final > spindle_rpm_max:
        scale = spindle_rpm_max / rpm_final
        rpm_final = float(spindle_rpm_max)
        feed_final *= scale
        clamps.append(f"主軸 RPM 上限 {spindle_rpm_max}: {int(rpm_calc)} → {int(rpm_final)} "
                      f"(Feed 同比例 ×{scale:.3f})")

    # ② 材質 Vc 飽和線 (任何刀具都不能突破)
    vc_info = get_vc_ceiling(material)
    vc_ceiling = float(vc_info["Vc_ceiling"])
    vc_now = math.pi * float(tool_dia) * rpm_final / 1000.0
    if vc_now > vc_ceiling:
        # 反推合理 RPM
        rpm_by_vc = vc_ceiling * 1000.0 / (math.pi * float(tool_dia))
        scale = rpm_by_vc / rpm_final
        rpm_final = rpm_by_vc
        feed_final *= scale
        clamps.append(f"材質 Vc 飽和 {vc_ceiling} m/min ({vc_info.get('note','')}): "
                      f"Vc {vc_now:.1f} → {vc_ceiling:.1f}, "
                      f"RPM ×{scale:.3f}")

    # ③ 主軸功率 F 上限
    f_info = get_feed_ceiling(material, spindle_kw)
    f_ceiling = float(f_info["F_ceiling_mm_min"])
    if feed_final > f_ceiling:
        clamps.append(f"主軸功率 F 上限 {int(f_ceiling)} mm/min "
                      f"({f_info['material_group']} @ {spindle_kw}kW): "
                      f"{int(feed_final)} → {int(f_ceiling)}")
        feed_final = f_ceiling

    return {
        "rpm": int(round(rpm_final)),
        "feed_mm_min": int(round(feed_final)),
        "Vc_m_min": round(math.pi * float(tool_dia) * rpm_final / 1000.0, 1),
        "Vc_ceiling_used": vc_ceiling,
        "F_ceiling_used": int(f_ceiling),
        "spindle_rpm_max": spindle_rpm_max,
        "spindle_kw": spindle_kw,
        "material_used": material,
        "hardness_hrc_assumed": vc_info.get("hrc_typical", 0),
        "clamps_applied": clamps,
        "no_clamp_applied": len(clamps) == 0,
    }


# ═══════════════════════════════════════════════════════════════════════
#  鐵則 ③ 「先動 ae/ap/f 再動 V/S」調參優先序
# ═══════════════════════════════════════════════════════════════════════

ADJUSTMENT_PRIORITY: List[Dict[str, Any]] = [
    {
        "step": 1,
        "action_zh": "檢查並調整 ae/ap (徑向/軸向吃刀)",
        "action_en": "Check and adjust ae/ap (radial/axial engagement)",
        "applies_to": ["顫動", "燒刀", "崩刃", "刀痕重", "尺寸跳"],
        "reason": "切削負荷的根源, 改變 ae/ap 比改 RPM 更直接",
        "example": "顫動 → ae 從 50%D 降到 30%D; 燒刀 → ap 減半",
    },
    {
        "step": 2,
        "action_zh": "降低 f (進給/fz)",
        "action_en": "Lower feed (f / fz)",
        "applies_to": ["顫動仍存在", "刀紋過深", "表面粗糙度差"],
        "reason": "降進給減負荷, 但不會把刀陷入低速不穩定區",
        "example": "fz 從 0.05 降到 0.03; F 從 1000 降到 600",
    },
    {
        "step": 3,
        "action_zh": "最後才動 Vc / S (轉速)",
        "action_en": "Last resort: adjust Vc / S",
        "applies_to": ["以上都沒效", "刀具溫度過高"],
        "reason": "降 RPM 會把刀陷入低速不穩定區; 升 RPM 會撞物質 Vc 上限",
        "example": "Vc 在物質上限附近時, 反而要考慮降而非升",
    },
]


def adjustment_priority() -> Dict[str, Any]:
    """回傳調參優先序給 cam-helper 引用。"""
    return {
        "rule_zh": "先動 ae/ap/f 再動 V/S",
        "rule_en": "Adjust ae/ap/f first, V/S last",
        "steps": ADJUSTMENT_PRIORITY,
        "anti_pattern_zh": "❌ 不要遇到問題就先降轉速 — 這會把刀陷入低速不穩定區反讓問題惡化",
        "rationale": "切削穩定性主要由 ae × ap × fz 構成的「切削力場」決定, "
                     "RPM 只是其中一維, 不應該優先動",
    }


# ═══════════════════════════════════════════════════════════════════════
#  鐵則 ④ 刀具幾何經驗公式 (用戶 2026.05 提供)
# ═══════════════════════════════════════════════════════════════════════
# 「常規銑刀 大約是 刀具徑 D × 3 = 刃長 H
#    刀具總長 D<8 大約 50 / D=8 大約 60 / D>8 大約 75」
# 「長刃銑刀 大約是 刀具徑 D × 4 = 刃長 H
#    刀具總長 D<8 大約 60 / D=8 大約 75 / D>8 大約 100」

def _estimate_total_length(D: float, long_flute: bool) -> int:
    """總長估算: <8 / =8 / >8 三段階梯。"""
    if long_flute:
        if D < 8:   return 60
        if D == 8:  return 75
        return 100
    else:
        if D < 8:   return 50
        if D == 8:  return 60
        return 75


def estimate_tool_geometry(tool_dia: float,
                            long_flute: bool = False) -> Dict[str, Any]:
    """估算「常規 vs 長刃」銑刀的刃長、總長、估算避空長度。

    Args:
        tool_dia:    刀徑 mm
        long_flute:  True = 長刃 (D×4), False = 常規 (D×3)

    Returns:
        {profile, D, flute_length_mm, total_length_mm, shoulder_length_mm}
    """
    D = float(tool_dia)
    profile = "long_flute_endmill" if long_flute else "regular_endmill"
    flute_len = D * (4.0 if long_flute else 3.0)
    total_len = _estimate_total_length(D, long_flute)
    # 經驗: 鎖緊段 ~ 20mm (柄部基本佔用)
    shoulder = max(0.0, total_len - flute_len - 20)

    return {
        "profile": profile,
        "profile_zh": "長刃銑刀" if long_flute else "常規銑刀",
        "tool_dia_mm": D,
        "flute_length_mm": round(flute_len, 1),
        "total_length_mm": int(total_len),
        "shoulder_length_mm": round(shoulder, 1),
        "rule_used": (f"H ≈ D × {'4' if long_flute else '3'}, "
                      f"L ≈ {'60/75/100' if long_flute else '50/60/75'} "
                      f"(D <8 / =8 / >8)"),
    }


def recommend_tool_profile_for_depth(tool_dia: float,
                                      work_depth_mm: float,
                                      safety_margin_mm: float = 3.0
                                      ) -> Dict[str, Any]:
    """依工件加工深度推薦「常規」或「長刃」銑刀, 含避空檢查。

    判斷邏輯:
      ① 常規 H 足夠 → 推薦常規 (剛性最佳, 精度高)
      ② 常規不夠但長刃夠 → 推薦長刃 (剛性略降, RPM 要降 ~50%)
      ③ 都不夠 → 警告 (需特殊長刃或加大刀徑)
    """
    D = float(tool_dia)
    depth = float(work_depth_mm)
    regular = estimate_tool_geometry(D, long_flute=False)
    long_f = estimate_tool_geometry(D, long_flute=True)

    if depth + safety_margin_mm <= regular["flute_length_mm"]:
        return {
            "recommended": "regular",
            "recommended_zh": "常規銑刀",
            "reason": (f"工件深 {depth}mm + 餘量 {safety_margin_mm}mm "
                       f"≤ 常規刃長 {regular['flute_length_mm']}mm, "
                       f"剛性最佳優先選常規"),
            "regular": regular,
            "long_flute": long_f,
            "rpm_adjustment": "無需 (使用常規切削參數)",
            "f_adjustment": "無需",
        }
    if depth + safety_margin_mm <= long_f["flute_length_mm"]:
        return {
            "recommended": "long_flute",
            "recommended_zh": "長刃銑刀",
            "reason": (f"工件深 {depth}mm 超過常規 {regular['flute_length_mm']}mm, "
                       f"但長刃 {long_f['flute_length_mm']}mm 夠用"),
            "regular": regular,
            "long_flute": long_f,
            "rpm_adjustment": "RPM × 0.50-0.60 (參考銘九長刃表)",
            "f_adjustment": "F × 0.40-0.50 (剛性弱化補償)",
            "warning": "長刃剛性降低, 避免重切削 (Ap 不超 1.0D)",
        }
    return {
        "recommended": "custom_or_larger_D",
        "recommended_zh": "特殊長刃或加大刀徑",
        "reason": (f"工件深 {depth}mm 超過 D{D} 長刃極限 "
                   f"({long_f['flute_length_mm']}mm)"),
        "regular": regular,
        "long_flute": long_f,
        "suggestion_zh": [
            f"選項 1: 加大刀徑 (例 D={D*1.5:.0f} 長刃 → 刃長 {D*1.5*4:.0f}mm)",
            "選項 2: 訂製超長刃 (但 RPM 要再降 30-40%)",
            "選項 3: 分層加工 (上半段常規 + 下半段絞孔 / 鎢鋼鑽接力)",
        ],
        "warning": "短 + 深 = 容易斷刀, 請務必首件驗證",
    }


def estimate_tool_geometry_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """估算刀具幾何 dispatch helper。"""
    D = params.get("tool_dia") or params.get("diameter_mm")
    if D is None:
        return {"success": False, "error": "需提供 tool_dia"}
    long_flute = bool(params.get("long_flute", False))
    return {"success": True, "data": estimate_tool_geometry(float(D), long_flute)}


def recommend_tool_profile_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """工件深度推薦刀型 dispatch helper。"""
    D = params.get("tool_dia") or params.get("diameter_mm")
    depth = params.get("work_depth_mm") or params.get("depth")
    if D is None or depth is None:
        return {"success": False,
                "error": "需提供 tool_dia 與 work_depth_mm"}
    margin = float(params.get("safety_margin_mm") or 3.0)
    return {"success": True,
            "data": recommend_tool_profile_for_depth(float(D), float(depth),
                                                    margin)}


# ═══════════════════════════════════════════════════════════════════════
#  推斷 API: 從錨點表推算其他刀具參數 (核心推斷規則 #1: 同系列換刀徑)
# ═══════════════════════════════════════════════════════════════════════

def derive_from_anchor(anchor_D: float,
                       anchor_rpm: float,
                       anchor_feed: float,
                       target_D: float,
                       material: str,
                       tool_material: str = "Carbide",
                       teeth_anchor: int = 4,
                       teeth_target: Optional[int] = None) -> Dict[str, Any]:
    """從錨點刀具 (D, RPM, F) 推算目標刀具 (target_D, ?, ?) 的參數。

    推斷規律:
      - Vc 同 (= Vc_anchor); 套材質 Vc 上限封頂
      - fz 大致同 (假設工法相同)
      - 換算: RPM_new = Vc × 318.3 / D_new
              F_new   = RPM_new × fz × Z_new
      - 套刀具材質係數修正 (HSS→Carbide 等)
      - 套機台/材質物理上限
    """
    Z_a = int(teeth_anchor)
    Z_t = int(teeth_target or teeth_anchor)

    # 從錨點反推 Vc、fz
    Vc_anchor = math.pi * float(anchor_D) * float(anchor_rpm) / 1000.0
    fz_anchor = (float(anchor_feed) / (float(anchor_rpm) * Z_a)
                 if anchor_rpm and Z_a else 0.0)

    # 套刀具材質修正 (若同系列等於 1.0)
    tmf = get_tool_material_factor(tool_material)
    Vc_target = Vc_anchor * float(tmf["vc_factor"])
    fz_target = fz_anchor  # 同工法下 fz 不變

    # 算新刀的 RPM / F
    rpm_calc = Vc_target * 318.3 / float(target_D) if target_D else 0.0
    feed_calc = rpm_calc * fz_target * Z_t

    # 套物理上限
    clamped = apply_ceilings(material, float(target_D), rpm_calc, feed_calc)

    return {
        "success": True,
        "anchor": {
            "D": float(anchor_D), "rpm": int(anchor_rpm),
            "feed": int(anchor_feed), "Z": Z_a,
            "Vc_reverse_calc": round(Vc_anchor, 1),
            "fz_reverse_calc": round(fz_anchor, 4),
        },
        "target": {
            "D": float(target_D), "Z": Z_t,
            "tool_material": tool_material,
            "tool_material_factor": tmf["vc_factor"],
            "Vc_applied": round(Vc_target, 1),
            "fz_applied": round(fz_target, 4),
            "rpm_before_clamp": int(rpm_calc),
            "feed_before_clamp": int(feed_calc),
            "rpm_final": clamped["rpm"],
            "feed_final": clamped["feed_mm_min"],
            "Vc_final": clamped["Vc_m_min"],
        },
        "clamps_applied": clamped["clamps_applied"],
        "rules_used": [
            f"推斷規則#1: 同 Vc 換刀徑 (Vc={Vc_anchor:.1f} m/min)",
            f"推斷規則#5: 刀具材質 {tool_material} ({tmf['name_zh']}) × {tmf['vc_factor']}",
            "物理上限#1: 主軸 RPM 硬上限 12000",
            f"物理上限#2: {material} Vc ≤ {clamped['Vc_ceiling_used']} m/min",
            f"物理上限#3: 主軸功率 F ≤ {clamped['F_ceiling_used']} mm/min",
        ],
        "note": (f"從錨點 D{anchor_D} RPM{int(anchor_rpm)} F{int(anchor_feed)} "
                 f"(Vc={Vc_anchor:.0f}, fz={fz_anchor:.3f}) "
                 f"推算 D{target_D} → RPM{clamped['rpm']} F{clamped['feed_mm_min']}"),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MCP dispatch
# ═══════════════════════════════════════════════════════════════════════

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point。

    params 模式:
      {"mode": "list_rules"}                                  → 列出所有規則類別
      {"mode": "operation_factors", "operation": "..."}       → 工法折扣係數
      {"mode": "vc_ceiling", "material": "..."}               → 材質 Vc 上限
      {"mode": "tool_material_factor", "tool_material": "..."} → 刀具材質係數
      {"mode": "feed_ceiling", "material": "...", "spindle_kw": 7.5} → F 上限
      {"mode": "substitute", "from_material": "...", "to_material": "...",
                             "rpm": ..., "feed": ...}        → 跨材質換算
      {"mode": "apply_ceilings", "material": ..., "tool_dia": ...,
                                 "rpm": ..., "feed": ...}    → 套物理上限
      {"mode": "derive", "anchor_D": ..., "anchor_rpm": ..., "anchor_feed": ...,
                         "target_D": ..., "material": ..., ...} → 推算其他刀具
      {"mode": "adjustment_priority"}                         → 調參優先序
    """
    mode = (params.get("mode") or "list_rules").lower()

    if mode == "list_rules":
        return {
            "success": True,
            "data": {
                "module": "machining_heuristics",
                "philosophy": [
                    "錨點表 (廠商官網表) 是上限值",
                    "本模組是中間值/變換規則 (推斷引擎)",
                    "三條鐵則: 工法折扣 + 三層剛性/物質上限 + 調參優先序",
                ],
                "rules": {
                    "operation_factors": list(OPERATION_FACTORS.keys()),
                    "vc_ceiling_materials": list(VC_CEILING.keys()),
                    "tool_materials": list(TOOL_MATERIAL_FACTOR.keys()),
                    "spindle_f_groups": list(SPINDLE_F_FACTOR.keys()),
                    "material_substitution_pairs": [
                        f"{a} → {b}" for (a, b) in MATERIAL_SUBSTITUTION.keys()
                    ],
                },
                "core_apis": [
                    "get_operation_factors(operation)",
                    "get_vc_ceiling(material)",
                    "get_tool_material_factor(tool_material)",
                    "get_feed_ceiling(material, spindle_kw)",
                    "substitute_material(from, to, rpm, feed)",
                    "apply_ceilings(material, tool_dia, rpm, feed)",
                    "derive_from_anchor(anchor_D, anchor_rpm, anchor_feed, target_D, ...)",
                    "adjustment_priority()",
                ],
            },
        }

    if mode == "operation_factors":
        op = params.get("operation") or "roughing"
        return {"success": True, "data": get_operation_factors(op)}

    if mode == "vc_ceiling":
        m = params.get("material") or ""
        return {"success": True, "data": get_vc_ceiling(m)}

    if mode == "tool_material_factor":
        tm = params.get("tool_material") or "Carbide"
        return {"success": True, "data": get_tool_material_factor(tm)}

    if mode == "feed_ceiling":
        m = params.get("material") or ""
        kw = float(params.get("spindle_kw") or 7.5)
        return {"success": True, "data": get_feed_ceiling(m, kw)}

    if mode == "substitute":
        fm = params.get("from_material") or ""
        tm = params.get("to_material") or ""
        rpm = float(params.get("rpm") or 0)
        feed = float(params.get("feed") or 0)
        return {"success": True, "data": substitute_material(fm, tm, rpm, feed)}

    if mode == "apply_ceilings":
        m = params.get("material") or ""
        D = float(params.get("tool_dia") or 0)
        rpm = float(params.get("rpm") or 0)
        feed = float(params.get("feed") or 0)
        kw = float(params.get("spindle_kw") or 7.5)
        rpm_max = int(params.get("spindle_rpm_max") or 12000)
        return {"success": True,
                "data": apply_ceilings(m, D, rpm, feed, kw, rpm_max)}

    if mode == "derive":
        return derive_from_anchor(
            anchor_D=float(params.get("anchor_D") or 0),
            anchor_rpm=float(params.get("anchor_rpm") or 0),
            anchor_feed=float(params.get("anchor_feed") or 0),
            target_D=float(params.get("target_D") or 0),
            material=params.get("material") or "",
            tool_material=params.get("tool_material") or "Carbide",
            teeth_anchor=int(params.get("teeth_anchor") or 4),
            teeth_target=(int(params["teeth_target"])
                          if params.get("teeth_target") else None),
        )

    if mode == "adjustment_priority":
        return {"success": True, "data": adjustment_priority()}

    if mode == "estimate_tool_geometry":
        return estimate_tool_geometry_dispatch(params)

    if mode == "recommend_tool_profile":
        return recommend_tool_profile_dispatch(params)

    return {
        "success": False,
        "error": f"未知 mode: {mode}",
        "valid_modes": [
            "list_rules", "operation_factors", "vc_ceiling",
            "tool_material_factor", "feed_ceiling", "substitute",
            "apply_ceilings", "derive", "adjustment_priority",
            "estimate_tool_geometry", "recommend_tool_profile",
        ],
    }
