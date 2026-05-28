# -*- coding: utf-8 -*-
r"""
常規加工銑削 (Regular Milling, Non-Hard Machining)
====================================================
用戶 2026.05 親授場內 S50C 加工心法 (Gemini 驗證)

定位 (相對於 4 層架構):
  L1 GOLD     = 本地 Fusion preset (用戶實機驗證上機值)
  L2 SILVER   = 廠商表 (GoldCobra / 奇力揚 / OSG SG)
  L2B AMBER   = 銘九通用表 (廠商通用值, 任何鎢鋼塗層刀)
  L3 BRONZE_A = 純物理推斷 (machining_heuristics.apply_ceilings)
  L3 BRONZE_B ← 本檔: 「常規加工 5 工法心法」(用戶口傳, 含 Chip Thinning)

═══════════════════════════════════════════════════════════════════════
  ★ 核心設計哲學 (用戶口傳, 2026.05)
═══════════════════════════════════════════════════════════════════════
  「以刀具直徑 D 做基準, 5 工法各自有 Vc/fz/AE/AP 公式」

  基準算法:
      RPM = (Vc × 1000) / (π × D)
      F   = fz × Z × RPM
      fz  = D × 0.01 (面銑/側銑, S50C 中庸值)
            (D/2.5) × 0.01 (滿刃銑, 大降)
            0.025 (插銑, 固定不隨 D)

  5 工法 Vc 切換:
      面銑/側銑/孔銑:  Vc = 100 (S50C 基準)
      滿刃銑:          Vc =  70 (-30%, 抑制 180° 接觸高熱)
      插銑:            Vc =  80 (-20%, 軸向吃刀緩衝)


═══════════════════════════════════════════════════════════════════════
  ★ 核心哲學 (用戶 2026.05 親授)
═══════════════════════════════════════════════════════════════════════
       「參數是活的, 物理特性是死的」

  物理特性 (死):  材料硬度/剪切應力/導熱率/刀把剛性/接觸角/徑向力
                 這些不可違背
  參數 (活):     S/F/AE/AP/工法/刀把組合
                 在「死」的邊界內千變萬化


═══════════════════════════════════════════════════════════════════════
  ★ 用戶場內三大約束 (內建於本套規則)
═══════════════════════════════════════════════════════════════════════
  ① 切削油 (flood coolant): fz 不必全 chip thinning 補償 (預設 comp=0)
  ② ER 系列刀把: 大徑 (D≥10) AP 必降載 (從 0.1D 降到 0.06D)
  ③ 散件加工: 直接套上機中庸值, 不再額外打折
  ④ 滿刃銑專用後拉式刀把 (剛性硬碰硬, AP 可回到 0.7D 原值)


═══════════════════════════════════════════════════════════════════════
  ★ 8 大刀把 + 工法配對 (用戶 2026.05 親授)
═══════════════════════════════════════════════════════════════════════
  緊固力 強 → 弱:
    熱縮 ★★★★★ → 油壓 ★★★★½ → 後拉 ★★★★½ →
    側固 ★★★★  → SK   ★★★½  → ER   ★★½   →
    鑽夾頭 ★    → 攻牙 (功能性)

  工法 → 黃金刀把:
    面銑 (AP 降載)  → ER 可                  (用戶實機)
    側銑動態擺線   → SK / 熱縮 / 油壓        (低跳動)
    孔銑           → ER 可                  (對照面銑)
    ★滿刃開槽     → 後拉 / 側固 / 熱縮      (剛性硬碰硬)
    插銑          → ER 可                  (軸向力為主)


═══════════════════════════════════════════════════════════════════════
  ★ Chip Thinning (晶片減薄) 數學模型
═══════════════════════════════════════════════════════════════════════
  接觸角:      cos(θ) = 1 - 2×AE/D    θ = acos(1 - 2×AE/D)
  實際切屑厚度: hex = fz_program × sin(θ)   (當 AE < D/2)

  反推 fz_program:
      fz_program = hex_target / sin(θ)

  D=10 範例:
      AE = 7.5 (0.75D): θ=120°, sin=0.866 → 無減薄,  hex = fz × 0.866
      AE = 0.3 (3%D):   θ=20°,  sin=0.346 → 大減薄,  hex = fz × 0.346
      AE = 0.25(2.5%D): θ=18°,  sin=0.312 → 大減薄,  hex = fz × 0.312
"""

from typing import Any, Dict, List, Optional, Tuple
import math


# ═══════════════════════════════════════════════════════════════════════
#  ⓪ 8 大刀把規格 (用戶 2026.05 親授)
# ═══════════════════════════════════════════════════════════════════════

# 刀把屬性:
#   stars          緊固力星等 (1~5)
#   tir_um         典型徑向跳動 μm (low=精密好)
#   rigidity       剛性係數 (相對 shrink_fit=1.0)
#   anti_pullout   防掉刀係數 (0~1, 1=絕不會掉)
#   suit_high_rpm  適合高轉速 (true=可衝)
#   ap_slot_factor 滿刃 AP 公式倍率 (1.0=用戶原值 0.7D, 0.71=降到 0.5D)
HOLDER_PROFILES: Dict[str, Dict[str, Any]] = {
    "shrink_fit": {
        "name_zh": "熱縮刀把",
        "stars": 5.0, "tir_um": 3, "rigidity": 1.00,
        "anti_pullout": 1.00, "suit_high_rpm": True,
        "ap_slot_factor": 1.00,
        "notes": "近乎一體無縫包覆, 深度清角/高速精密首選",
    },
    "hydraulic": {
        "name_zh": "油壓刀把",
        "stars": 4.5, "tir_um": 5, "rigidity": 0.95,
        "anti_pullout": 0.90, "suit_high_rpm": True,
        "ap_slot_factor": 1.00,
        "notes": "內油腔減震, 動態擺線/光潔度極佳",
    },
    "pullback": {
        "name_zh": "後拉強力刀把",
        "stars": 4.5, "tir_um": 10, "rigidity": 0.95,
        "anti_pullout": 1.00, "suit_high_rpm": False,
        "ap_slot_factor": 1.00,
        "notes": "★ 滿刃開槽首選, 重切絕不掉刀",
    },
    "weldon": {
        "name_zh": "側固式刀把",
        "stars": 4.0, "tir_um": 30, "rigidity": 0.90,
        "anti_pullout": 1.00, "suit_high_rpm": False,
        "ap_slot_factor": 1.00,
        "notes": "螺絲死鎖扁平, 跳動大但 100% 不掉刀, 粗加工",
    },
    "sk": {
        "name_zh": "SK/GER/OZ 高精密筒夾",
        "stars": 3.5, "tir_um": 5, "rigidity": 0.85,
        "anti_pullout": 0.70, "suit_high_rpm": True,
        "ap_slot_factor": 0.85,
        "notes": "夾緊力是 ER 的 1.5~2 倍, 動態擺線最佳",
    },
    "er": {
        "name_zh": "ER 彈性筒夾",
        "stars": 2.5, "tir_um": 15, "rigidity": 0.70,
        "anti_pullout": 0.50, "suit_high_rpm": False,
        "ap_slot_factor": 0.71,   # 0.7D × 0.71 ≈ 0.5D (Gemini 修正)
        "notes": "萬用標配/散件加工, 重切會被吸出",
    },
    "drill_chuck": {
        "name_zh": "鑽頭夾頭",
        "stars": 1.0, "tir_um": 100, "rigidity": 0.30,
        "anti_pullout": 0.20, "suit_high_rpm": False,
        "ap_slot_factor": 0.30,
        "notes": "僅軸向受力, 不能銑 (徑向會滑)",
    },
    "tap_chuck": {
        "name_zh": "攻牙刀把",
        "stars": None, "tir_um": None, "rigidity": None,
        "anti_pullout": None, "suit_high_rpm": False,
        "ap_slot_factor": None,
        "notes": "絲攻浮動補正專用, 不用於銑削",
    },
}


def _normalize_holder(holder: str) -> str:
    """容錯映射 (ER20/ER32/ER → er, 等)"""
    h = (holder or "er").strip().lower()
    if h.startswith("er"):          return "er"
    if h.startswith("sk") or h in ("ger", "oz"): return "sk"
    if h in ("hsk_shrink", "hsk_thermal", "shrink", "shrinkfit"):
        return "shrink_fit"
    if h in ("hydro", "hyd"):       return "hydraulic"
    if h in ("pull", "pullback_strong", "powermilling", "power_milling"):
        return "pullback"
    if h in ("flat", "sidelock"):   return "weldon"
    if h in ("drill", "drillchuck"): return "drill_chuck"
    if h in ("tap", "tapping"):     return "tap_chuck"
    return h if h in HOLDER_PROFILES else "er"


def _get_holder(holder: str) -> Dict[str, Any]:
    return HOLDER_PROFILES.get(_normalize_holder(holder),
                               HOLDER_PROFILES["er"])


# 工法 → 推薦刀把
OPERATION_HOLDER_RECO: Dict[str, Dict[str, Any]] = {
    "face": {
        "primary":   "er",
        "alternatives": ["sk", "hydraulic"],
        "rationale": "AP 已主動降載, ER 可扛, 散件首選",
    },
    "side": {
        "primary":   "sk",
        "alternatives": ["hydraulic", "shrink_fit", "er"],
        "rationale": "動態擺線需低跳動 (TIR<10μm), SK 最佳",
    },
    "hole": {
        "primary":   "er",
        "alternatives": ["sk", "hydraulic"],
        "rationale": "對照面銑, 螺旋下刀剛性需求中等",
    },
    "slot": {
        "primary":   "pullback",
        "alternatives": ["weldon", "shrink_fit", "hydraulic"],
        "rationale": "180° 滿刃重切, 後拉式剛性硬碰硬",
    },
    "plunge": {
        "primary":   "er",
        "alternatives": ["pullback", "hydraulic"],
        "rationale": "Z 軸軸向力為主, 徑向力小, ER 可勝任",
    },
}


def recommend_holder(operation: str) -> Dict[str, Any]:
    """給定工法, 推薦刀把組合。"""
    op = (operation or "face").lower()
    rec = OPERATION_HOLDER_RECO.get(op)
    if not rec:
        return {"success": False, "error": f"未知工法 {operation}"}
    return {
        "success": True,
        "operation": op,
        "primary": {
            "key": rec["primary"],
            **HOLDER_PROFILES[rec["primary"]],
        },
        "alternatives": [
            {"key": k, **HOLDER_PROFILES[k]} for k in rec["alternatives"]
        ],
        "rationale": rec["rationale"],
    }


# ═══════════════════════════════════════════════════════════════════════
#  ① Chip Thinning (晶片減薄) 數學
# ═══════════════════════════════════════════════════════════════════════

def compute_engagement_angle(D: float, AE: float) -> float:
    """計算徑向接觸角 (弧度)。

    cos(θ) = 1 - 2×AE/D
    特殊情況:
      AE >= D:      θ = 180° (滿刀)
      AE >= D/2:    θ > 90°
      AE <  D/2:    θ < 90°
    """
    D = float(D)
    AE = float(AE)
    if AE >= D:
        return math.pi
    if AE <= 0:
        return 0.0
    cos_theta = 1.0 - 2.0 * AE / D
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.acos(cos_theta)


def compute_hex(D: float, AE: float, fz_program: float) -> float:
    """計算實際切屑厚度 hex。

    hex = fz_program × sin(θ)  (當 AE < D/2)
        = fz_program            (當 AE >= D/2)
    """
    theta = compute_engagement_angle(D, AE)
    # 當 AE >= D/2, theta >= 90°, sin(theta) = sin(180-theta), 但 hex
    # 的「最大」厚度仍是 fz, 不再減薄
    if 2.0 * AE >= D:
        return float(fz_program)
    return float(fz_program) * math.sin(theta)


def compute_fz_for_hex(D: float, AE: float, hex_target: float) -> float:
    """依目標切屑厚度反推 fz_program。"""
    if 2.0 * AE >= D:
        return float(hex_target)  # 無減薄, 直接給
    theta = compute_engagement_angle(D, AE)
    return float(hex_target) / math.sin(theta)


# ═══════════════════════════════════════════════════════════════════════
#  ② 5 工法 Profile (S50C 為基準)
# ═══════════════════════════════════════════════════════════════════════

# Vc 縮放表 (相對 S50C 基準 = 1.0)
# 套用方式: Vc_material = Vc_profile × material_scale
MATERIAL_VC_SCALE: Dict[str, float] = {
    # ─── 鋁/銅 ───
    "AL6061":         2.00,  # Vc 200 (鋁散熱好, 翻倍)
    "AL7075":         2.00,
    "Brass":          2.50,  # Vc 250 (黃銅可衝最快)
    "Copper":         2.50,
    "Plastics":       3.00,
    # ─── 碳鋼 / 鑄鐵 (基準) ───
    "S50C":           1.00,  # ★ 基準
    "S45C":           1.00,
    "Cast_Iron":      1.00,
    "SCM":            0.95,
    # ─── 退火態模具鋼 (跟 S50C 接近) ───
    "SKD11":          0.90,  # 退火 SKD11 略硬
    "SKD61":          0.90,
    "DC53":           0.90,
    "S136":           0.95,
    # ─── 預質 / 中度淬火 (HRC 30-50) ───
    "SCM440":         0.85,  # 30HRC 預質
    "NAK80":          0.75,  # 40HRC 預硬
    "HPM38":          0.75,
    # ─── 不銹鋼 (沾刀, 半 Vc) ───
    "SUS304":         0.70,
    "SUS316":         0.70,
    "SUS420":         0.65,
    "SUS440":         0.60,
    # ─── 鈦 (Mazak i600 試算佐證) ───
    "Ti-6Al-4V":      0.60,  # Vc 60
    "TC4":            0.60,
    # ─── 超合金 ───
    "Inconel":        0.40,
}


# 動態銑削極限 hex 目標 (吹氣冷卻環境, 給「升級到極限」用)
# 用戶切削油環境的「合理 hex」已內建於 fz = D × 0.01 公式中
# 此表只在 chip_thinning_compensation > 0 時使用 (預設 0, 不啟用補償)
HEX_TARGET_FULL_DYNAMIC: Dict[Tuple[str, str], float] = {
    # (coolant_target, material_class) → hex_target_mm (動態極限值)
    ("air", "carbon_steel"):    0.050,  # ★ Gemini 推 S50C 動態極限
    ("air", "annealed_steel"):  0.050,
    ("air", "prehardened"):     0.035,  # NAK80/HPM38 動態極限
    ("air", "stainless"):       0.030,
    ("air", "titanium"):        0.035,
    ("air", "aluminum"):        0.100,  # 鋁吹氣可衝
    ("air", "copper"):          0.100,
    ("air", "plastics"):        0.120,
    # 「flood」欄保留, 但實際很少用 — 用戶切削油已含 fz=D×0.01 隱含補償
    ("flood", "carbon_steel"):  0.040,
    ("flood", "aluminum"):      0.080,
}


def _classify_material(material: str) -> str:
    """把材質鍵映射到 hex 表的材質類別。"""
    m = (material or "").strip()
    if m in ("AL6061", "AL7075", "Plastics"):    return "aluminum"
    if m in ("Brass", "Copper"):                  return "copper"
    if m in ("S50C", "S45C", "Cast_Iron", "SCM"): return "carbon_steel"
    if m in ("SKD11", "SKD61", "DC53", "S136"):   return "annealed_steel"
    if m in ("SCM440", "NAK80", "HPM38"):          return "prehardened"
    if m.startswith("SUS"):                        return "stainless"
    if m in ("Ti-6Al-4V", "TC4"):                  return "titanium"
    return "carbon_steel"  # 預設


# ═══════════════════════════════════════════════════════════════════════
#  5 工法各自的 AE/AP/Vc 公式
# ═══════════════════════════════════════════════════════════════════════

def _ap_face(D: float, holder: str) -> float:
    """面銑 AP 公式 (剛性弱刀把 + 大徑時降載)。

    剛性弱 (ER): D≥10 用 0.06D, 否則 0.10D
    剛性強 (SK/Pullback/Shrink/Hydraulic): 一律 0.10D
    微徑 (D<2): 0.05D
    """
    if D < 2:
        return 0.05 * D                   # 微徑保護 (D=1 → 0.05)
    h = _normalize_holder(holder)
    is_weak = h in ("er", "weldon", "drill_chuck")
    if D >= 10 and is_weak:
        return 0.06 * D                   # ER 大徑降載 (D=10 → 0.6)
    return 0.10 * D                       # 標準 (剛性夠的刀把不降)


def _ap_side(D: float, holder: str) -> float:
    """側銑 AP = 2D (≈ 刃長 × 0.7), 不依賴 holder。"""
    return 2.0 * D


def _ae_side(D: float, holder: str) -> float:
    """側銑 AE = (面銑 AP) / 2 (用戶記憶法則, ER D=10 = 0.3mm)。"""
    return _ap_face(D, holder) / 2.0


def _ap_slot(D: float, holder: str) -> float:
    """滿刃銑 AP (依 holder 剛性動態):
       後拉/熱縮/油壓/側固: 0.7D (用戶教學原值, 剛性硬碰硬)
       SK:                  0.6D (中間值)
       ER:                  0.5D (Gemini 修正, 防震掉)
       微徑 D<3:             0.4D (進一步保護)
    """
    h = _normalize_holder(holder)
    factor = HOLDER_PROFILES[h].get("ap_slot_factor") or 0.71
    base_ap = 0.70 * D                    # 用戶原始公式 (剛性夠)
    if D < 3:
        return min(0.40 * D, base_ap * factor)
    return base_ap * factor


def _ap_plunge(D: float, holder: str,
               tool_flute_length: Optional[float] = None) -> float:
    """插銑 AP = 視刀長 (一刀到底, 保留 10% 安全)。"""
    if tool_flute_length:
        return float(tool_flute_length) * 0.9
    # 估算: 常規銑刀 刃長 ≈ 3D
    return 3.0 * D * 0.9


# 工法 Profile 表
WORKFLOW_PROFILES: Dict[str, Dict[str, Any]] = {
    "face": {
        "name_zh": "面銑 (開粗 / 平面階梯)",
        "vc_m_min": 100,            # S50C 基準
        "fz_coefficient": 0.01,     # fz = D × 0.01
        "teeth_default": 4,
        "ae_formula": lambda D: 0.75 * D,
        "ap_func": _ap_face,
        "rationale": "求平面光潔度, ae=0.75D 接受 120° 接觸角",
        "use_chip_thinning": False,  # ae > D/2, 無減薄
    },
    "side": {
        "name_zh": "側銑 (動態擺線, 開粗主力)",
        "vc_m_min": 100,
        "fz_coefficient": 0.01,
        "teeth_default": 4,
        "ae_func": _ae_side,
        "ap_func": _ap_side,
        "rationale": "AE 極小 + AP 拉長, 動態銑削思維, 散熱+刀壽極佳",
        "use_chip_thinning": True,   # ae << D/2, 有減薄
    },
    "hole": {
        "name_zh": "孔銑 (螺旋下刀)",
        "vc_m_min": 100,
        "fz_coefficient": 0.005,    # = 面銑 × 0.5
        "teeth_default": 4,
        "ae_note": "= (孔直徑 - 銑刀直徑) / 2 (單邊)",
        "ap_note": "對照面銑",
        "ae_func": None,             # 由 unilateral_ae 算
        "ap_func": _ap_face,         # 對照面銑
        "rationale": "螺旋孔銑空間受限, F 隨單邊空間分級",
        "use_chip_thinning": False,
        "f_modifier_by_unilateral_ae": [
            (0.5,  0.50, "孔過小, 螺旋空間有限"),     # < 0.5
            (1.0,  0.75, "孔偏小, 螺旋空間受限"),     # 0.5~1.0
            (math.inf, 1.00, "孔適中, 螺旋空間良好"),  # > 1.0
        ],
    },
    "slot": {
        "name_zh": "滿刃銑 (開槽)",
        "vc_m_min": 70,              # -30% (180° 接觸控扭矩)
        "fz_coefficient": 0.01,
        "fz_extra_divisor": 2.5,     # fz = (D/2.5) × 0.01 (大降)
        "teeth_default": 4,
        "ae_formula": lambda D: 1.0 * D,
        "ap_func": _ap_slot,         # 0.5D (Gemini 修正)
        "rationale": "180° 滿吃, Vc/fz 必降, AP 0.4-0.5D 抑震",
        "use_chip_thinning": False,
    },
    "plunge": {
        "name_zh": "插銑 (Z 軸吃, 清角)",
        "vc_m_min": 80,              # -20%
        "fz_fixed": 0.025,           # 固定值! 不隨 D
        "teeth_default": 4,
        "ae_formula": lambda D: 0.05 * D,
        "ap_func": _ap_plunge,       # 視刀長
        "rationale": "Z 軸壓削, AE 極小, fz 固定保守",
        "use_chip_thinning": False,
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  ③ 主推薦 API
# ═══════════════════════════════════════════════════════════════════════

def recommend(material: str,
              tool_dia: float,
              operation: str = "face",
              teeth: Optional[int] = None,
              holder: str = "ER20",
              coolant: str = "flood",
              tool_flute_length: Optional[float] = None,
              hole_diameter: Optional[float] = None,
              chip_thinning_compensation: float = 0.0
              ) -> Dict[str, Any]:
    """常規加工 5 工法主推薦 API。

    Args:
        material:           工件材質 (S50C / AL6061 / NAK80 / SUS304 / ...)
        tool_dia:           刀徑 mm
        operation:          face / side / hole / slot / plunge
        teeth:              刃數 (預設 4)
        holder:             刀把類型 (ER / ER20 / SK / pullback)
        coolant:            flood (切削油, 預設) / air (吹氣) / dry (乾切)
        tool_flute_length:  插銑用, 刃長 mm
        hole_diameter:      孔銑用, 孔直徑 mm
        chip_thinning_compensation:
            ★ 晶片減薄「升級」係數 (0.0~1.0)
              0.0 = 用戶切削油實機值 (預設, fz = D × 0.01)
              0.5 = 中度升級 (切削油也可衝)
              1.0 = 動態銑削吹氣極限 (Gemini 推)
            僅在「側銑動態」工法生效 (ae < D/2)

    Returns:
        {success, params: {rpm, feed, ae, ap, vc, hex, fz, ...}, ...}
    """
    op_key = (operation or "face").lower()
    if op_key not in WORKFLOW_PROFILES:
        return {
            "success": False,
            "error": f"未知工法: {operation}",
            "valid_operations": list(WORKFLOW_PROFILES.keys()),
        }

    profile = WORKFLOW_PROFILES[op_key]
    D = float(tool_dia)
    Z = int(teeth or profile.get("teeth_default", 4))

    # ─── Vc (材質縮放) ───
    vc_base = float(profile["vc_m_min"])
    vc_scale = MATERIAL_VC_SCALE.get(material, 1.0)
    vc = vc_base * vc_scale

    # ─── RPM ───
    rpm = vc * 1000.0 / (math.pi * D)

    # ─── fz (各工法各自公式) ───
    if "fz_fixed" in profile:
        fz = float(profile["fz_fixed"])
    elif "fz_extra_divisor" in profile:
        fz = (D / float(profile["fz_extra_divisor"])) * \
              float(profile["fz_coefficient"])
    else:
        fz = D * float(profile["fz_coefficient"])

    # ─── AE / AP ───
    ae_mm: Optional[float] = None
    ap_mm: Optional[float] = None
    f_modifier = 1.0
    unilateral_ae: Optional[float] = None
    f_modifier_reason: Optional[str] = None

    if op_key == "hole":
        # 孔銑: AE 由孔徑算, F 階梯式調整
        if hole_diameter is None:
            return {
                "success": False,
                "error": "孔銑需提供 hole_diameter (孔直徑 mm)",
            }
        unilateral_ae = (float(hole_diameter) - D) / 2.0
        if unilateral_ae < 0:
            return {
                "success": False,
                "error": f"孔徑 {hole_diameter} < 刀徑 {D}, 無法螺旋孔銑",
            }
        ae_mm = unilateral_ae
        ap_mm = _ap_face(D, holder)  # 對照面銑 AP
        # F 階梯
        for upper, mod, reason in profile["f_modifier_by_unilateral_ae"]:
            if unilateral_ae < upper:
                f_modifier = mod
                f_modifier_reason = reason
                break
    elif op_key == "plunge":
        ae_mm = profile["ae_formula"](D)
        ap_mm = _ap_plunge(D, holder, tool_flute_length)
    elif op_key == "side":
        ae_mm = _ae_side(D, holder)
        ap_mm = _ap_side(D, holder)
    else:  # face / slot
        ae_mm = profile["ae_formula"](D)
        ap_func = profile.get("ap_func")
        ap_mm = ap_func(D, holder) if ap_func else None

    # ─── Chip Thinning「升級」補償 (側銑動態, 預設不啟用) ───
    # 哲學:
    #   fz = D × 0.01 (用戶教學公式) 已是「切削油 + ER20 + 散件」中庸值
    #   若用戶想升級到動態銑削極限 (配吹氣), 才傳 compensation > 0
    fz_program = fz
    hex_actual: Optional[float] = None
    chip_thinning_applied = False
    if (profile.get("use_chip_thinning") and ae_mm and 2 * ae_mm < D
            and chip_thinning_compensation > 0):
        mat_class = _classify_material(material)
        hex_target_full = HEX_TARGET_FULL_DYNAMIC.get(
            ("air", mat_class),
            HEX_TARGET_FULL_DYNAMIC.get(("air", "carbon_steel"), 0.050)
        )
        fz_full = compute_fz_for_hex(D, ae_mm, hex_target_full)
        # 只往「升級」方向 (fz_full > fz), 否則不動
        if fz_full > fz:
            fz_program = fz + (fz_full - fz) * float(chip_thinning_compensation)
            chip_thinning_applied = True

    # ─── F (進給) ───
    F_base = fz_program * Z * rpm
    F = F_base * f_modifier

    # ─── F 上限 (孔銑用面銑 F 當天花板) ───
    F_cap = None
    if op_key == "hole":
        # 上限 = 面銑 F (= D × 0.01 × Z × RPM)
        F_cap = (D * 0.01) * Z * rpm
        if F > F_cap:
            F = F_cap

    # ─── 實際 hex (給用戶看) ───
    if ae_mm:
        hex_actual = compute_hex(D, ae_mm, fz_program)

    # ─── 刀把適配檢查 (給用戶警示, informational) ───
    holder_norm = _normalize_holder(holder)
    holder_info = HOLDER_PROFILES[holder_norm]
    reco = OPERATION_HOLDER_RECO.get(op_key, {})
    holder_advisor: Dict[str, Any] = {
        "current": {"key": holder_norm, **{k: v for k, v in holder_info.items()
                                            if k != "notes"}},
        "current_notes": holder_info.get("notes"),
        "recommended_primary": reco.get("primary"),
        "recommended_alts": reco.get("alternatives", []),
        "match": "OK",
        "warning": None,
    }
    if reco:
        primary = reco["primary"]
        alts = reco.get("alternatives", [])
        if holder_norm == primary:
            holder_advisor["match"] = "OPTIMAL"
        elif holder_norm in alts:
            holder_advisor["match"] = "ACCEPTABLE"
        else:
            holder_advisor["match"] = "SUBOPTIMAL"
            holder_advisor["warning"] = (
                f"當前刀把 ({holder_info['name_zh']}) 非 {op_key} 工法推薦. "
                f"建議改用 {HOLDER_PROFILES[primary]['name_zh']} "
                f"({reco.get('rationale', '')})"
            )

    # ─── hex 健康度檢查 (僅對「動態減薄」場景, AE < D/2) ───
    # 注意: 面銑/滿刃/插銑 各有用戶教學的 fz 標準值, 不走此檢查
    hex_health = "OK"
    hex_warning = None
    if (hex_actual is not None and ae_mm and 2 * ae_mm < D
            and op_key == "side"):
        if hex_actual < 0.015:
            hex_health = "RUBBING_RISK"
            hex_warning = (f"hex={hex_actual:.4f} 過薄 (<0.015), "
                           "刀刃可能刮削產生高熱; 建議 ① 拉高 fz "
                           "(用 chip_thinning_compensation>0) ② 加大 AE")
        elif hex_actual > 0.080:
            hex_health = "OVERLOAD_RISK"
            hex_warning = (f"hex={hex_actual:.4f} 過厚 (>0.080), "
                           "單齒負荷過大; 建議 ① 降低 fz "
                           "② 換用不等齒抑震刀具")

    return {
        "success": True,
        "layer": "L3_BRONZE_B",
        "source": "regular_milling.py (用戶 2026.05 親授 + Gemini 驗證)",
        "material": material,
        "tool_dia_mm": D,
        "operation": op_key,
        "operation_zh": profile["name_zh"],
        "holder": holder,
        "coolant": coolant,
        "params": {
            "rpm": int(round(rpm)),
            "feed_mm_min": int(round(F)),
            "Vc_m_min": round(vc, 1),
            "fz_program_mm_tooth": round(fz_program, 4),
            "fz_baseline_mm_tooth": round(fz, 4),
            "hex_mm_actual": round(hex_actual, 4) if hex_actual else None,
            "engagement_angle_deg": (
                round(math.degrees(compute_engagement_angle(D, ae_mm)), 1)
                if ae_mm else None
            ),
            "ae_mm": round(ae_mm, 3) if ae_mm else None,
            "ap_mm": round(ap_mm, 3) if ap_mm else None,
            "ae_pct_D": round(ae_mm / D * 100, 2) if ae_mm else None,
            "ap_pct_D": round(ap_mm / D * 100, 1) if ap_mm else None,
            "teeth": Z,
            "MRR_mm3_per_min": (round(ae_mm * ap_mm * F, 0)
                                if ae_mm and ap_mm else None),
        },
        "chip_thinning": {
            "applied": chip_thinning_applied,
            "compensation_pct": (chip_thinning_compensation
                                 if chip_thinning_applied else None),
        },
        "hex_health": hex_health,
        "hex_warning": hex_warning,
        "holder_advisor": holder_advisor,
        "hole_milling_info": ({
            "unilateral_ae_mm": round(unilateral_ae, 3),
            "f_modifier": f_modifier,
            "f_modifier_reason": f_modifier_reason,
            "F_capped_at": int(F_cap) if F_cap else None,
        } if op_key == "hole" else None),
        "rationale": profile["rationale"],
        "vc_scale_applied": vc_scale,
        "confidence": 0.65,
        "note": (
            f"{profile['name_zh']} D={D}mm {material} ({holder}, {coolant}): "
            f"S={int(round(rpm))} F={int(round(F))} "
            f"AE={round(ae_mm, 2) if ae_mm else '-'} "
            f"AP={round(ap_mm, 2) if ap_mm else '-'} "
            f"hex={round(hex_actual, 4) if hex_actual else '-'}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
#  ④ Dispatch
# ═══════════════════════════════════════════════════════════════════════

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point.

    params:
      {"mode": "recommend", "material": "S50C", "tool_dia": 10,
       "operation": "face/side/hole/slot/plunge",
       "holder": "ER20", "coolant": "flood",
       "hole_diameter": 12,  # 孔銑用
       "tool_flute_length": 30}  # 插銑用
      {"mode": "compute_hex", "D": 10, "AE": 0.3, "fz": 0.1}
      {"mode": "fz_for_hex", "D": 10, "AE": 0.3, "hex_target": 0.03}
      {"mode": "list_profiles"} → 5 工法摘要
    """
    md = (params.get("mode") or "recommend").lower()

    if md == "list_profiles":
        return {
            "success": True,
            "profiles": {
                k: {
                    "name_zh": v["name_zh"],
                    "vc_m_min_base": v["vc_m_min"],
                    "rationale": v["rationale"],
                }
                for k, v in WORKFLOW_PROFILES.items()
            },
            "material_vc_scale": MATERIAL_VC_SCALE,
            "supported_operations": list(WORKFLOW_PROFILES.keys()),
        }

    if md == "list_holders":
        return {
            "success": True,
            "holders": HOLDER_PROFILES,
            "operation_recommendation": OPERATION_HOLDER_RECO,
        }

    if md == "recommend_holder":
        op = params.get("operation") or "face"
        return recommend_holder(op)

    if md == "compute_hex":
        D = float(params.get("D") or params.get("tool_dia") or 0)
        AE = float(params.get("AE") or params.get("ae") or 0)
        fz = float(params.get("fz") or 0)
        if not (D and fz):
            return {"success": False, "error": "需 D 和 fz"}
        theta = compute_engagement_angle(D, AE)
        return {
            "success": True,
            "D": D, "AE": AE, "fz_program": fz,
            "engagement_angle_deg": round(math.degrees(theta), 2),
            "engagement_angle_rad": round(theta, 4),
            "sin_theta": round(math.sin(theta), 4),
            "hex_actual": round(compute_hex(D, AE, fz), 5),
            "chip_thinning_active": 2 * AE < D,
        }

    if md == "fz_for_hex":
        D = float(params.get("D") or params.get("tool_dia") or 0)
        AE = float(params.get("AE") or params.get("ae") or 0)
        hex_t = float(params.get("hex_target") or 0.03)
        if not D:
            return {"success": False, "error": "需 D"}
        fz = compute_fz_for_hex(D, AE, hex_t)
        return {
            "success": True,
            "D": D, "AE": AE, "hex_target": hex_t,
            "fz_program_required": round(fz, 4),
            "note": (f"AE={AE}/D={D} ({100*AE/D:.1f}%D), "
                     f"hex 目標 {hex_t} → fz 程式設定 {fz:.4f} mm/tooth"),
        }

    if md == "recommend":
        mat = params.get("material")
        D = params.get("tool_dia") or params.get("diameter_mm")
        if not mat or D is None:
            return {"success": False,
                    "error": "需 material 與 tool_dia"}
        return recommend(
            material=mat,
            tool_dia=float(D),
            operation=(params.get("operation") or "face"),
            teeth=(int(params["teeth"]) if params.get("teeth") else None),
            holder=(params.get("holder") or "ER20"),
            coolant=(params.get("coolant") or "flood"),
            tool_flute_length=(float(params["tool_flute_length"])
                               if params.get("tool_flute_length") else None),
            hole_diameter=(float(params["hole_diameter"])
                           if params.get("hole_diameter") else None),
            chip_thinning_compensation=float(
                params.get("chip_thinning_compensation", 0.70)),
        )

    return {"success": False,
            "error": f"未知 mode: {md}",
            "valid_modes": ["recommend", "compute_hex", "fz_for_hex",
                            "list_profiles", "list_holders",
                            "recommend_holder"]}
