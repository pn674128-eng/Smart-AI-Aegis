# -*- coding: utf-8 -*-
r"""
GoldCobra (金眼鏡蛇) 高硬度高速切削刀具系列
=============================================
用戶 2026.05 提供官方手冊 (GoldCobra_2021版.pdf), 是場內實際使用的廠商.

定位: L2 SILVER (廠商實測上機值, 信賴 0.80)

═══════════════════════════════════════════════════════════════════════
  ★★★ 關鍵設計哲學: 硬銑「Z 軸長吃, X/Y 軸薄吃」★★★
═══════════════════════════════════════════════════════════════════════
  用戶 2026.05 指示:
    「鎢鋼刀硬度才多少 加工HRC 60左右的東西 負載是要降到很低的」

  GoldCobra 表完美印證:
    SKD11 HRC55-62 D=10 NXE 平刀側壁加工:
        AP=20mm (200%D, 整個刃長拉滿)
        AE=0.1mm (1%D!!!, 極薄薄切)
        RPM=960, F=192

  這跟「一般加工」的 ae大 ap小 完全相反:
    一般加工 (HRC<30):  ae=30~50%D, ap=50%~100%D
    硬銑 (HRC>55):      ae=1~3%D,   ap=100~200%D ← Z 拉長, X/Y 薄切

  理由 (物理): 鎢鋼刀 HRA91 ≈ HRC75, 跟工件 HRC60 只差 15
              → 橫向力 (AE) 是崩刃主因, 必須極小化
              → 軸向 (AP) 拉長無妨, 反正單刃只吃 0.1mm 寬


═══════════════════════════════════════════════════════════════════════
  3 個系列 (用戶場內主力)
═══════════════════════════════════════════════════════════════════════
  ① NXE  - 高速高硬度專用立銑刀 (平刀, 4 刃, HRC65 以下)
  ② NZB  - 高速高硬度專用球頭立銑刀 (R0.5-R8, HRC65 以下)
  ③ R-NM - 螺紋銑刀 (M1.0-M20, ISO 60°, HRC65 以下)


═══════════════════════════════════════════════════════════════════════
  4 個硬度區段 (GoldCobra 表共通分類)
═══════════════════════════════════════════════════════════════════════
  A. HRc23-32 - 合金工具鋼 / 碳工具鋼 (退火態 SKD11/SKD61, P20, SK3)
  B. HRc36-45 - 調質鋼 / 預硬鋼 (NAK80, AISI420, M310)
  C. HRc48-54 - 熱處理鋼半硬 (SKD61 淬, STAVAX, 17-4PH, H13)
  D. HRc55-62 - 熱處理鋼全硬 (SKD11 淬, SKH9, D2, M2) ← 硬銑主戰場


═══════════════════════════════════════════════════════════════════════
  ★ 側壁 ↔ 平面 對調規則 (用戶 2026.05 場內口訣)
═══════════════════════════════════════════════════════════════════════
  「此表的 AE/AP 參數 可以 /2 對調 = 平面加工參數」

      平面加工 AE = 側壁 AP / 2
      平面加工 AP = 側壁 AE / 2

  範例 (D=10 SKD11 HRC55-62 NXE):
      側壁:  AP=20mm (200%D, 拉長刃),  AE=0.1mm (1%D, 薄壁薄切)
      平面:  AE=10mm (100%D, 滿刀寬), AP=0.05mm (0.5%D, 極薄層削)

  物理意義 (硬銑哲學一致):
      側壁加工: Z 軸長吃 + X/Y 軸薄吃
      平面加工: X/Y 軸滿吃 + Z 軸薄切
      → 兩軸至少一軸要極薄, 鎢鋼刀切硬鋼才不崩刃


數據來源: GoldCobra_2021版.pdf
"""

from typing import Any, Dict, List, Optional, Tuple
import math


# ═══════════════════════════════════════════════════════════════════════
#  硬度區段定義 (4 個共通分檔)
# ═══════════════════════════════════════════════════════════════════════
HARDNESS_BANDS: Dict[str, Dict[str, Any]] = {
    "A_HRc23_32": {
        "label_zh": "合金工具鋼/碳工具鋼 (退火態)",
        "hrc_range": [23, 32],
        "materials_zh": ["P20", "P5", "SK3", "SKD61", "SKD11", "H13", "D2",
                         "1.2311", "1.1545", "1.2379", "1.2344"],
        "applicable_materials": ["P20", "P5", "SK3", "SKD61", "SKD11",
                                 "H13", "D2", "S50C", "S45C", "Cast_Iron",
                                 "DC53"],
        "note": "退火態/出貨態鋼料 (用戶場內 SKD11 退火主用此段)",
    },
    "B_HRc36_45": {
        "label_zh": "調質鋼/預硬鋼",
        "hrc_range": [36, 45],
        "materials_zh": ["NAK80", "AISI420", "M310", "1.2083"],
        "applicable_materials": ["NAK80", "HPM38", "SUS420", "SCM440"],
        "note": "預質鋼 (出廠就硬, NAK80 系列)",
    },
    "C_HRc48_54": {
        "label_zh": "熱處理鋼 (半硬)",
        "hrc_range": [48, 54],
        "materials_zh": ["SKD61", "STAVAX", "17-4PH", "H13", "420"],
        "applicable_materials": ["SKD61_hardened", "S136_hardened",
                                 "STAVAX", "17-4PH"],
        "note": "中度淬火鋼 (SKD61 淬, STAVAX 等)",
    },
    "D_HRc55_62": {
        "label_zh": "熱處理鋼 (全硬, 硬銑主戰場)",
        "hrc_range": [55, 62],
        "materials_zh": ["SKD11", "SKH9", "D2", "M2", "1.2379", "1.3342"],
        "applicable_materials": ["SKD11_hardened", "SKH9", "ASP23",
                                 "DC53_hardened"],
        "note": "★ 鎢鋼刀切此段必須「AE極小, AP拉長」硬銑思維",
    },
}


def select_band(hardness_hrc: Optional[float], material: str) -> str:
    """依硬度 / 材質鍵推斷硬度區段。"""
    if hardness_hrc is not None:
        h = float(hardness_hrc)
        if h <= 32:  return "A_HRc23_32"
        if h <= 45:  return "B_HRc36_45"
        if h <= 54:  return "C_HRc48_54"
        return "D_HRc55_62"
    # 沒給硬度 → 從材質名推
    m = (material or "").strip()
    if m.endswith("_hardened"):
        base = m.replace("_hardened", "")
        if base in ("SKD11", "DC53"):  return "D_HRc55_62"
        if base in ("S136", "SKD61"):  return "C_HRc48_54"
        return "C_HRc48_54"
    if m in ("NAK80", "HPM38"):       return "B_HRc36_45"
    if m in ("SKH9", "ASP23"):        return "D_HRc55_62"
    if m in ("SKD11", "SKD61", "DC53", "S136", "S50C", "S45C",
             "Cast_Iron"):
        return "A_HRc23_32"  # 退火/出貨態
    return "A_HRc23_32"  # 預設保守


# ═══════════════════════════════════════════════════════════════════════
#  ① NXE 平刀側壁加工參數表 (10000 RPM 機台欄, 用戶 12000 主軸用此欄)
# ═══════════════════════════════════════════════════════════════════════
# 格式: D → (RPM, F mm/min, AP mm, AE mm)
# 用戶機台 12000 RPM 上限, 用 10000 機欄即可 (官方提供 10000 / 20000 / 30000 三檔)

NXE_SIDEWALL_10000: Dict[str, Dict[float, Tuple[int, int, float, float]]] = {
    "A_HRc23_32": {
        1.0:  (9600,  154,  1.5,  0.010),
        1.5:  (8533,  137,  2.25, 0.015),
        2.0:  (9600,  384,  4.8,  0.020),
        2.5:  (8320,  666,  4.8,  0.025),
        3.0:  (6933,  832,  4.8,  0.030),
        4.0:  (5200,  624,  4.8,  0.040),
        5.0:  (4160,  666, 10.4,  0.050),
        6.0:  (3467,  693, 12.0,  0.060),
        8.0:  (2600,  520, 16.0,  0.080),
        10.0: (2080,  416, 20.0,  0.100),
        12.0: (1733,  347, 24.0,  0.120),
        16.0: (1300,  260, 36.0,  0.160),
    },
    "B_HRc36_45": {
        1.0:  (9600,  154,  1.5,  0.010),
        1.5:  (8533,  137,  2.25, 0.015),
        2.0:  (8800,  352,  4.8,  0.020),
        2.5:  (7040,  563,  4.8,  0.025),
        3.0:  (5867,  704,  4.8,  0.030),
        4.0:  (4400,  528,  4.8,  0.040),
        5.0:  (3520,  563, 10.4,  0.050),
        6.0:  (2933,  587, 12.0,  0.060),
        8.0:  (2200,  440, 16.0,  0.080),
        10.0: (1760,  352, 20.0,  0.100),
        12.0: (1467,  293, 24.0,  0.120),
        16.0: (1100,  220, 36.0,  0.160),
    },
    "C_HRc48_54": {
        1.0:  (9600,  154,  1.5,  0.010),
        1.5:  (8533,  137,  2.25, 0.015),
        2.0:  (6400,  256,  4.8,  0.020),
        2.5:  (5120,  410,  4.8,  0.025),
        3.0:  (4267,  512,  4.8,  0.030),
        4.0:  (3200,  384,  4.8,  0.040),
        5.0:  (2560,  410, 10.4,  0.050),
        6.0:  (2133,  427, 12.0,  0.060),
        8.0:  (1600,  320, 16.0,  0.080),
        10.0: (1280,  256, 20.0,  0.100),
        12.0: (1067,  213, 24.0,  0.120),
        16.0:  (800,  160, 36.0,  0.160),
    },
    "D_HRc55_62": {
        1.0:  (9600,  154,  1.5,  0.010),
        1.5:  (6400,  102,  2.25, 0.015),
        2.0:  (4800,  192,  4.8,  0.020),
        2.5:  (3840,  307,  4.8,  0.025),
        3.0:  (3200,  384,  4.8,  0.030),
        4.0:  (2400,  288,  4.8,  0.040),
        5.0:  (1920,  307, 10.4,  0.050),
        6.0:  (1600,  320, 12.0,  0.060),
        8.0:  (1200,  240, 16.0,  0.080),
        10.0:  (960,  192, 20.0,  0.100),
        12.0:  (800,  160, 24.0,  0.120),
        16.0:  (600,  120, 36.0,  0.160),
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  ② NZB 球頭立銑刀加工參數表 (10000 RPM 機台欄)
# ═══════════════════════════════════════════════════════════════════════
# 格式: D (球刀直徑) → (RPM, F, AP, AE)
# 球刀 D=2R, AE/AP 較平刀大很多 (球頭刃接觸點分散)

NZB_BALL_10000: Dict[str, Dict[float, Tuple[int, int, float, float]]] = {
    "A_HRc23_32": {
        1.0:   (9600,  960, 0.04, 0.03),
        1.5:   (9600, 1152, 0.06, 0.05),
        2.0:   (9600, 1344, 0.08, 0.06),
        2.5:   (9600, 1536, 0.10, 0.08),
        3.0:   (9067, 1451, 0.12, 0.09),
        4.0:   (8800, 1408, 0.16, 0.12),
        5.0:  (10880, 1741, 0.20, 0.15),
        6.0:   (9067, 1451, 0.24, 0.18),
        8.0:   (6800, 1088, 0.32, 0.24),
        10.0:  (5440,  870, 0.40, 0.30),
        12.0:  (4533,  725, 0.48, 0.36),
        16.0:  (3400,  544, 0.64, 0.48),
    },
    "B_HRc36_45": {
        1.0:   (9600,  960, 0.04, 0.03),
        1.5:   (9600, 1152, 0.06, 0.05),
        2.0:   (9600, 1344, 0.08, 0.06),
        2.5:   (9600, 1536, 0.10, 0.08),
        3.0:   (9067, 1451, 0.12, 0.09),
        4.0:   (8800, 1408, 0.16, 0.12),
        5.0:   (8960, 1434, 0.20, 0.15),
        6.0:   (8000, 1280, 0.24, 0.18),
        8.0:   (6000,  960, 0.32, 0.24),
        10.0:  (4800,  768, 0.40, 0.30),
        12.0:  (4000,  640, 0.48, 0.36),
        16.0:  (3000,  480, 0.64, 0.48),
    },
    "C_HRc48_54": {
        1.0:   (9600,  960, 0.04, 0.03),
        1.5:   (9600, 1152, 0.06, 0.05),
        2.0:   (8960, 1254, 0.08, 0.06),
        2.5:   (9344, 1495, 0.10, 0.08),
        3.0:   (9067, 1451, 0.12, 0.09),
        4.0:   (8800, 1408, 0.16, 0.12),
        5.0:   (7680, 1229, 0.20, 0.15),
        6.0:   (6400, 1024, 0.24, 0.18),
        8.0:   (4800,  768, 0.32, 0.24),
        10.0:  (3840,  614, 0.40, 0.30),
        12.0:  (3200,  512, 0.48, 0.36),
        16.0:  (2400,  384, 0.64, 0.48),
    },
    "D_HRc55_62": {
        1.0:   (9600,  960, 0.04, 0.03),
        1.5:   (9600, 1152, 0.06, 0.05),
        2.0:   (8960, 1254, 0.08, 0.06),
        2.5:   (9600, 1536, 0.10, 0.08),
        3.0:   (8000, 1280, 0.12, 0.09),
        4.0:   (6000,  960, 0.16, 0.12),
        5.0:   (4800,  768, 0.20, 0.15),
        6.0:   (4000,  640, 0.24, 0.18),
        8.0:   (3000,  480, 0.32, 0.24),
        10.0:  (2400,  384, 0.40, 0.30),
        12.0:  (2000,  320, 0.48, 0.36),
        16.0:  (1500,  240, 0.64, 0.48),
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  ③ R-NM 螺紋銑刀 (內螺紋, ISO 60°)
# ═══════════════════════════════════════════════════════════════════════
# 螺紋銑刀規格 (型號, 螺紋大徑 M, pitch, 刃徑 d1, 有效長 L1)

R_NM_SPECS: List[Dict[str, Any]] = [
    {"type": "R-NM1002",  "M_thread": 1.00,  "pitch": 0.25, "d1": 0.72, "L1": 2.3},
    {"type": "R-NM1003",  "M_thread": 1.00,  "pitch": 0.25, "d1": 0.72, "L1": 3.2},
    {"type": "R-NM1202",  "M_thread": 1.20,  "pitch": 0.25, "d1": 0.90, "L1": 2.8},
    {"type": "R-NM1402",  "M_thread": 1.40,  "pitch": 0.30, "d1": 1.05, "L1": 3.2},
    {"type": "R-NM1602",  "M_thread": 1.60,  "pitch": 0.35, "d1": 1.20, "L1": 3.7},
    {"type": "R-NM2002S", "M_thread": 2.00,  "pitch": 0.40, "d1": 1.53, "L1": 4.6},
    {"type": "R-NM2002",  "M_thread": 2.00,  "pitch": 0.40, "d1": 1.53, "L1": 4.6},
    {"type": "R-NM2202",  "M_thread": 2.20,  "pitch": 0.45, "d1": 1.65, "L1": 5.1},
    {"type": "R-NM2502",  "M_thread": 2.50,  "pitch": 0.45, "d1": 1.95, "L1": 5.8},
    {"type": "R-NM3002",  "M_thread": 3.00,  "pitch": 0.50, "d1": 2.37, "L1": 6.5},
    {"type": "R-NM4002",  "M_thread": 4.00,  "pitch": 0.70, "d1": 3.20, "L1": 9.3},
    {"type": "R-NM5002",  "M_thread": 5.00,  "pitch": 0.80, "d1": 3.80, "L1": 11.5},
    {"type": "R-NM6002",  "M_thread": 6.00,  "pitch": 1.00, "d1": 4.65, "L1": 13.8},
    {"type": "R-NM8002",  "M_thread": 8.00,  "pitch": 1.25, "d1": 5.95, "L1": 18.4},
    {"type": "R-NM10002", "M_thread": 10.00, "pitch": 1.50, "d1": 7.80, "L1": 23.0},
    {"type": "R-NM12002", "M_thread": 12.00, "pitch": 1.75, "d1": 9.00, "L1": 26.0},
    {"type": "R-NM16002", "M_thread": 16.00, "pitch": 2.00, "d1": 11.80, "L1": 35.0},
    {"type": "R-NM20002", "M_thread": 20.00, "pitch": 2.50, "d1": 11.95, "L1": 42.0},
]


def find_r_nm_for_thread(M_thread: float) -> Optional[Dict[str, Any]]:
    """依公制螺紋外徑 (M) 查 R-NM 對映規格。"""
    best = None
    best_diff = 999
    for spec in R_NM_SPECS:
        diff = abs(spec["M_thread"] - float(M_thread))
        if diff < best_diff:
            best = spec
            best_diff = diff
    return best


# ═══════════════════════════════════════════════════════════════════════
#  ★ 側壁 ↔ 平面 對調規則 (用戶 2026.05 場內口訣)
# ═══════════════════════════════════════════════════════════════════════

def convert_sidewall_to_face_apae(ap_side: float,
                                  ae_side: float) -> Tuple[float, float]:
    """把側壁加工的 (AP, AE) 換算成平面加工的 (AP, AE)。

    用戶口訣: 「AE AP 參數 可以 /2 對調 = 平面加工參數」
        平面 AE = 側壁 AP / 2
        平面 AP = 側壁 AE / 2

    範例:
        side: AP=20, AE=0.1  (D=10 SKD11 HRC55-62 側銑)
        face: AP=0.05, AE=10 (D=10 SKD11 HRC55-62 面銑)
              ↑ Z 切 0.05mm 薄薄一層, X/Y 滿刀寬走

    Returns: (ap_face, ae_face)
    """
    ap_face = float(ae_side) / 2.0
    ae_face = float(ap_side) / 2.0
    return (ap_face, ae_face)


def convert_face_to_sidewall_apae(ap_face: float,
                                  ae_face: float) -> Tuple[float, float]:
    """反向轉換 (平面 → 側壁), 同樣 /2 對調。"""
    ap_side = float(ae_face) / 2.0
    ae_side = float(ap_face) / 2.0
    return (ap_side, ae_side)


# ═══════════════════════════════════════════════════════════════════════
#  插值與推薦 API
# ═══════════════════════════════════════════════════════════════════════

def _interp_table(table: Dict[float, Tuple[int, int, float, float]],
                  D: float) -> Optional[Tuple[float, float, float, float]]:
    """在 NXE/NZB 表中對直徑 D 做線性插值。"""
    if not table:
        return None
    keys = sorted(table.keys())
    if D <= keys[0]:
        return table[keys[0]]
    if D >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        d_lo, d_hi = keys[i], keys[i + 1]
        if d_lo <= D <= d_hi:
            r_lo, f_lo, ap_lo, ae_lo = table[d_lo]
            r_hi, f_hi, ap_hi, ae_hi = table[d_hi]
            if d_hi == d_lo:
                return table[d_lo]
            t = (D - d_lo) / (d_hi - d_lo)
            return (
                r_lo + t * (r_hi - r_lo),
                f_lo + t * (f_hi - f_lo),
                ap_lo + t * (ap_hi - ap_lo),
                ae_lo + t * (ae_hi - ae_lo),
            )
    return None


def recommend(material: str,
              tool_dia: float,
              series: Optional[str] = None,
              tool_type: str = "square_endmill",
              hardness_hrc: Optional[float] = None,
              spindle_rpm_class: int = 10000,
              mode: str = "conservative",
              rpm_factor: Optional[float] = None,
              feed_factor: Optional[float] = None,
              cutting_pattern: str = "sidewall") -> Dict[str, Any]:
    """GoldCobra 主推薦 API。

    Args:
        material:           工件 (SKD11/NAK80/...)
        tool_dia:           刀徑 mm (球刀用球徑 D=2R)
        series:             "NXE" (平刀) / "NZB" (球刀) / "R-NM" (螺紋)
                            預設依 tool_type 自動推
        tool_type:          square_endmill / ball / thread_mill
        hardness_hrc:       工件硬度 HRC
        spindle_rpm_class:  機台 RPM 等級 (10000 / 20000 / 30000)
                            用戶 12000 主軸用 10000 欄
        mode:               conservative (散件 75/50 折) / aggressive (滿表)
        rpm_factor/feed_factor: 覆蓋 mode 預設
        cutting_pattern:    "sidewall" (預設, 側壁加工原表) /
                            "face" (平面加工, AE/AP 對調/2 — 用戶 2026.05 口訣)

    Returns:
        {success, layer="L2_SILVER", series, params: {rpm, feed, ap, ae}, ...}
    """
    # 自動推系列
    if not series:
        tt = (tool_type or "").lower()
        if "ball" in tt:
            series = "NZB"
        elif "thread" in tt:
            series = "R-NM"
        else:
            series = "NXE"

    # 選硬度區段
    band_key = select_band(hardness_hrc, material)
    band = HARDNESS_BANDS[band_key]

    # 套散件折扣 (GoldCobra 表本身已是「上機值」, 折扣比銘九更輕)
    # 用戶說廠商實測表 = 廠商建議值, 散件再保守 25%
    if rpm_factor is None:
        rpm_factor = 0.85 if mode == "conservative" else 1.00
    if feed_factor is None:
        feed_factor = 0.75 if mode == "conservative" else 1.00

    if series == "NXE":
        table = NXE_SIDEWALL_10000.get(band_key)
        if not table:
            return {"success": False, "error": f"NXE {band_key} 表無數據"}
        v = _interp_table(table, float(tool_dia))
        if not v:
            return {"success": False,
                    "error": f"NXE D={tool_dia}mm 超出表範圍"}
        rpm_v, feed_v, ap_v, ae_v = v
        rpm = rpm_v * rpm_factor
        feed = feed_v * feed_factor
        # ★ 側壁 ↔ 平面 對調 (用戶 2026.05 口訣: AE AP /2 對調)
        if cutting_pattern == "face":
            ap_final, ae_final = convert_sidewall_to_face_apae(ap_v, ae_v)
        else:
            ap_final, ae_final = ap_v, ae_v
        return _format_result(
            success=True, series="NXE", band=band_key, band_info=band,
            material=material, tool_dia=tool_dia, hardness_hrc=hardness_hrc,
            rpm=rpm, feed=feed, ap=ap_final, ae=ae_final,
            rpm_vendor=rpm_v, feed_vendor=feed_v,
            mode=mode, rpm_factor=rpm_factor, feed_factor=feed_factor,
            teeth=4, cutting_pattern=cutting_pattern,
            ap_side=ap_v, ae_side=ae_v,
            workflow_note=_get_workflow_note(band_key, cutting_pattern),
        )

    if series == "NZB":
        table = NZB_BALL_10000.get(band_key)
        if not table:
            return {"success": False, "error": f"NZB {band_key} 表無數據"}
        v = _interp_table(table, float(tool_dia))
        if not v:
            return {"success": False,
                    "error": f"NZB D={tool_dia}mm 超出表範圍"}
        rpm_v, feed_v, ap_v, ae_v = v
        rpm = rpm_v * rpm_factor
        feed = feed_v * feed_factor
        # 球刀「曲面精銑」沒有平面/側壁區別 (本質上是 Z 軸 + R 軌跡)
        # 但若用戶硬要平面 (球底壓平), 同樣套對調規則
        if cutting_pattern == "face":
            ap_final, ae_final = convert_sidewall_to_face_apae(ap_v, ae_v)
        else:
            ap_final, ae_final = ap_v, ae_v
        return _format_result(
            success=True, series="NZB", band=band_key, band_info=band,
            material=material, tool_dia=tool_dia, hardness_hrc=hardness_hrc,
            rpm=rpm, feed=feed, ap=ap_final, ae=ae_final,
            rpm_vendor=rpm_v, feed_vendor=feed_v,
            mode=mode, rpm_factor=rpm_factor, feed_factor=feed_factor,
            teeth=2, cutting_pattern=cutting_pattern,
            ap_side=ap_v, ae_side=ae_v,
        )

    if series == "R-NM":
        spec = find_r_nm_for_thread(float(tool_dia))
        if not spec:
            return {"success": False, "error": f"R-NM 找不到 M{tool_dia} 規格"}
        # 螺紋銑刀的 RPM/F 共用 NXE 同直徑值 (用 d1 對應)
        table = NXE_SIDEWALL_10000.get(band_key)
        v = _interp_table(table, spec["d1"])
        if not v:
            return {"success": False,
                    "error": f"R-NM d1={spec['d1']}mm 超出 NXE 表範圍"}
        rpm_v, feed_v, _, _ = v
        rpm = rpm_v * rpm_factor
        feed = feed_v * feed_factor * 0.5  # 螺紋銑刀進給折半 (圓弧軌跡)
        return {
            "success": True,
            "layer": "L2_SILVER",
            "vendor": "GoldCobra",
            "series": "R-NM",
            "tool_spec": spec,
            "band": band_key,
            "material": material,
            "hardness_hrc_used": hardness_hrc,
            "params": {
                "rpm": int(round(rpm)),
                "feed_mm_min": int(round(feed)),
                "Vc_m_min": round(math.pi * spec["d1"] * rpm / 1000.0, 1),
                "M_thread": spec["M_thread"],
                "pitch": spec["pitch"],
                "d1_cutter": spec["d1"],
                "L1_effective": spec["L1"],
            },
            "confidence": 0.80,
            "note": (f"GoldCobra R-NM 螺紋銑刀 {spec['type']} "
                     f"M{spec['M_thread']}×{spec['pitch']} "
                     f"@ {band['label_zh']} → RPM={int(round(rpm))} "
                     f"F={int(round(feed))} (圓弧軌跡, 進給已折半)"),
            "source": "GoldCobra_2021版.pdf (R-NM 系列)",
        }

    return {"success": False, "error": f"未知系列: {series}"}


def _get_workflow_note(band_key: str, cutting_pattern: str) -> Optional[str]:
    """根據硬度區段 + 加工型態給工法提示。"""
    if band_key != "D_HRc55_62":
        if cutting_pattern == "face" and band_key == "C_HRc48_54":
            return "★ 平面加工 (硬度 HRC48-54): AP 已 /2 對調, Z 薄切壓制負載"
        return None
    if cutting_pattern == "face":
        return ("★ 平面硬銑 (HRC>55): AE 滿刀寬 (100%D), AP 極薄 (~0.5%D), "
                "Z軸層削思維 — 鎢鋼刀切硬鋼面銑必走薄削層")
    return ("★ 側壁硬銑 (HRC>55): AP=2D 拉長, AE=1%D 薄壁切, "
            "X/Y薄吃 + Z長吃 — 鎢鋼刀切硬鋼避免崩刃")


def _format_result(success, series, band, band_info, material, tool_dia,
                   hardness_hrc, rpm, feed, ap, ae, rpm_vendor, feed_vendor,
                   mode, rpm_factor, feed_factor, teeth,
                   cutting_pattern="sidewall",
                   ap_side=None, ae_side=None,
                   workflow_note=None) -> Dict[str, Any]:
    """格式化 NXE/NZB 結果。"""
    Vc = math.pi * float(tool_dia) * rpm / 1000.0
    pattern_zh = "平面加工" if cutting_pattern == "face" else "側壁加工"
    series_zh_map = {
        ("NXE", "sidewall"): "平刀側壁加工 (NXE)",
        ("NXE", "face"):     "平刀平面加工 (NXE, AE/AP /2 對調)",
        ("NZB", "sidewall"): "球頭曲面加工 (NZB)",
        ("NZB", "face"):     "球頭平面壓削 (NZB, AE/AP /2 對調)",
    }
    return {
        "success": success,
        "layer": "L2_SILVER",
        "vendor": "GoldCobra",
        "series": series,
        "series_zh": series_zh_map.get((series, cutting_pattern), series),
        "cutting_pattern": cutting_pattern,
        "cutting_pattern_zh": pattern_zh,
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "hardness_hrc_used": hardness_hrc,
        "band": band,
        "band_info": {
            "label_zh": band_info["label_zh"],
            "hrc_range": band_info["hrc_range"],
            "materials_zh": band_info["materials_zh"],
        },
        "params": {
            "rpm": int(round(rpm)),
            "feed_mm_min": int(round(feed)),
            "Vc_m_min": round(Vc, 1),
            "ap_mm": round(ap, 3),
            "ae_mm": round(ae, 3),
            "ae_pct_D": round(ae / float(tool_dia) * 100, 2),
            "ap_pct_D": round(ap / float(tool_dia) * 100, 1),
            "fz_mm_tooth": round(feed / rpm / teeth, 5) if rpm and teeth else None,
            "teeth": teeth,
            "rpm_vendor": int(rpm_vendor),
            "feed_vendor": int(feed_vendor),
        },
        "sidewall_reference": ({"ap_mm": round(ap_side, 3),
                                "ae_mm": round(ae_side, 3)}
                               if ap_side is not None and cutting_pattern == "face"
                               else None),
        "confidence": 0.80,
        "mode": mode,
        "rpm_factor": rpm_factor,
        "feed_factor": feed_factor,
        "workflow_note": workflow_note,
        "note": (f"GoldCobra {series} {pattern_zh} D={tool_dia}mm "
                 f"@ {band_info['label_zh']} ({band_info['hrc_range'][0]}-"
                 f"{band_info['hrc_range'][1]}HRC) → "
                 f"RPM={int(round(rpm))} F={int(round(feed))} "
                 f"AP={ap}mm ({round(ap/float(tool_dia)*100,1)}%D) "
                 f"AE={ae}mm ({round(ae/float(tool_dia)*100,2)}%D)"),
        "source": "GoldCobra_2021版.pdf (高速高硬度專用立銑刀手冊)",
    }


# ═══════════════════════════════════════════════════════════════════════
#  Dispatch
# ═══════════════════════════════════════════════════════════════════════

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point.

    params:
      {"mode": "recommend", "material": "SKD11", "tool_dia": 10,
       "series": "NXE", "hardness_hrc": 60,
       "cutting_pattern": "sidewall" / "face"}
      {"mode": "list_series"} → 列三個系列規格摘要
      {"mode": "list_bands"} → 列 4 個硬度區段
      {"mode": "convert_apae", "ap": 20, "ae": 0.1, "direction": "side_to_face"}
            → 側壁 ↔ 平面 轉換 (用戶 /2 對調口訣)
    """
    md = (params.get("mode") or "recommend").lower()

    if md == "list_series":
        return {
            "success": True,
            "series": {
                "NXE":  "平刀 (D=1~16, 4 刃, HRC≤65, 側壁精銑主力)",
                "NZB":  "球刀 (R0.5~R8, 2 刃, HRC≤65, 曲面精銑)",
                "R-NM": "螺紋銑刀 (M1.0~M20, ISO 60°, HRC≤65, L1=2D)",
            },
            "bands": {k: v["label_zh"] for k, v in HARDNESS_BANDS.items()},
            "rules": {
                "side_to_face": "平面 AE = 側壁 AP / 2; 平面 AP = 側壁 AE / 2",
                "hard_milling": "HRC>55: AE 1%D × AP 200%D (側) "
                                "或 AE 100%D × AP 0.5%D (面)",
            },
        }

    if md == "list_bands":
        return {"success": True, "bands": HARDNESS_BANDS}

    if md == "convert_apae":
        ap = params.get("ap")
        ae = params.get("ae")
        direction = (params.get("direction") or "side_to_face").lower()
        if ap is None or ae is None:
            return {"success": False, "error": "需 ap 和 ae"}
        if direction == "side_to_face":
            ap_new, ae_new = convert_sidewall_to_face_apae(float(ap),
                                                            float(ae))
            return {
                "success": True,
                "direction": "sidewall → face",
                "input":  {"ap_mm": ap, "ae_mm": ae},
                "output": {"ap_mm": round(ap_new, 4),
                           "ae_mm": round(ae_new, 4)},
                "rule": "平面 AE = 側壁 AP / 2; 平面 AP = 側壁 AE / 2",
            }
        else:
            ap_new, ae_new = convert_face_to_sidewall_apae(float(ap),
                                                            float(ae))
            return {
                "success": True,
                "direction": "face → sidewall",
                "input":  {"ap_mm": ap, "ae_mm": ae},
                "output": {"ap_mm": round(ap_new, 4),
                           "ae_mm": round(ae_new, 4)},
                "rule": "側壁 AP = 平面 AE / 2; 側壁 AE = 平面 AP / 2",
            }

    if md == "recommend":
        mat = params.get("material")
        D = params.get("tool_dia") or params.get("diameter_mm")
        if not mat or D is None:
            return {"success": False, "error": "需 material 與 tool_dia"}
        return recommend(
            material=mat,
            tool_dia=float(D),
            series=params.get("series"),
            tool_type=params.get("tool_type") or "square_endmill",
            hardness_hrc=(float(params["hardness_hrc"])
                          if params.get("hardness_hrc") else None),
            spindle_rpm_class=int(params.get("spindle_rpm_class") or 10000),
            mode=(params.get("mode_strategy") or "conservative"),
            rpm_factor=(float(params["rpm_factor"])
                        if params.get("rpm_factor") else None),
            feed_factor=(float(params["feed_factor"])
                         if params.get("feed_factor") else None),
            cutting_pattern=(params.get("cutting_pattern") or "sidewall"),
        )

    return {"success": False, "error": f"未知 mode: {md}",
            "valid_modes": ["recommend", "list_series", "list_bands",
                            "convert_apae"]}
