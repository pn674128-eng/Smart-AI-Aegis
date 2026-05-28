# -*- coding: utf-8 -*-
r"""
銘九通用銑刀切削條件庫 (General Cutting Conditions Catalog)
=============================================================
用戶 2026.05 提供: 銘九 (Mingjiu / chliyang 旗下) 官方通用值表

定位 (相對於三層架構):
  L1 GOLD     = 本地 Fusion preset (用戶實機驗證)
  L2 SILVER   = 奇力揚特定系列 (CIB/ALUS/CAVN/CFSL/CH01M/SG)
  L2B AMBER ← 本檔: 銘九通用值 (非特定型號, 任何鎢鋼塗層銑刀可參考)
  L3 BRONZE   = 純推斷 (machining_heuristics)

設計哲學:
  - 銘九資料定位是「通用值」, 給任何鎢鋼塗層銑刀作為參考
  - 用法: L2 奇力揚特定表查無命中時, 自動走 L2B 銘九通用表
  - 兩者都按「刀類別 × 材質硬度」精細匹配

7 個資料表:
  ① alu_square        - 鋁/銅用平刀 (2 材質: C1020 銅 / A5020 鋁)
  ② alu_ball          - 鋁/銅用球刀 (高速主軸 RPM)
  ③ hardened_2f       - 淬火鋼 2刃平刀 (3 硬度: HRC30-40 / 50-58 / 58-62)
  ④ hardened_4f       - 淬火鋼 4刃平刀 (2 硬度: HRC45-52 / 52-62)
  ⑤ hardened_4f_long  - 淬火鋼 4刃加長平刀 (RPM ≈ 4刃常規 × 53%)
  ⑥ hardened_ball     - 淬火鋼球刀 (3 硬度: HRC30 / 52 / 60)
  ⑦ micro_ball        - 微徑球刀 (R0.15-0.45, 全 25000 RPM)
"""

from typing import Any, Dict, List, Optional, Tuple
import math


# ═══════════════════════════════════════════════════════════════════════
#  資料表 ─ 7 張銘九通用表 (D, RPM, F mm/min)
# ═══════════════════════════════════════════════════════════════════════

CATALOG: Dict[str, Dict[str, Any]] = {
    # ─── ① 鋁用平刀 ───
    "alu_square": {
        "name_zh": "鋁用平刀 (常規鎢鋼塗層)",
        "tool_type": "square_endmill",
        "teeth_default": 3,  # 鋁用刀通常 3 刃
        "vendor": "銘九 Generic",
        "tables": {
            "C1020_copper": {
                "material_zh": "C1020 純銅 / Brass 黃銅",
                "applicable_materials": ["Copper", "Brass"],
                "table": [
                    # (D, RPM, F)
                    (3.0,  16000, 1600),
                    (4.0,  12500, 1250),
                    (5.0,  10000, 2000),
                    (6.0,   8500, 1700),
                    (8.0,   6500, 1300),
                    (10.0, 12000, 2400),
                    (12.0, 10000, 2000),
                    (16.0,  6000, 1050),
                    (20.0,  4500, 1050),
                ],
            },
            "A5020_alu": {
                "material_zh": "A5020 鋁合金 5XXX 系",
                "applicable_materials": ["AL6061", "AL7075", "Plastics"],
                "table": [
                    (3.0,  16000, 3200),
                    (4.0,  12500, 2500),
                    (5.0,  10000, 2000),
                    (6.0,   8500, 1700),
                    (8.0,   6500, 1300),
                    (10.0,  4800,  960),
                    (12.0,  4000,  800),
                    (16.0,  3500,  700),
                    (20.0,  3000,  600),
                ],
            },
        },
    },

    # ─── ② 鋁用球刀 ───
    "alu_ball": {
        "name_zh": "鋁用球刀 (高速主軸用)",
        "tool_type": "ball_endmill",
        "teeth_default": 2,
        "vendor": "銘九 Generic",
        "note": "D 為球徑 (R = D/2). 小徑 RPM 超 12000 須機台高速主軸",
        "tables": {
            "C1020_copper": {
                "material_zh": "C1020 純銅 / Brass 黃銅",
                "applicable_materials": ["Copper", "Brass"],
                "table": [
                    # (D=球徑, RPM, F)
                    (1.0,  32000,  600),
                    (1.5,  21500,  600),
                    (2.0,  16500,  600),
                    (3.0,  11500,  750),
                    (4.0,   8500,  750),
                    (5.0,   6600,  750),
                    (6.0,   5500,  750),
                    (8.0,   4200,  750),
                    (10.0,  3400,  750),
                    (12.0,  2900,  750),
                    (16.0,  2200,  750),
                    (20.0,  1800,  750),
                ],
            },
            "A5020_alu": {
                "material_zh": "A5020 鋁合金",
                "applicable_materials": ["AL6061", "AL7075", "Plastics"],
                "table": [
                    (1.0,  47500,  900),
                    (1.5,  47500,  900),
                    (2.0,  24000,  900),
                    (3.0,  16500, 1700),
                    (4.0,  12500, 1700),
                    (5.0,   9800, 1700),
                    (6.0,   8200, 1700),
                    (8.0,   6200, 1700),
                    (10.0,  5000, 1700),
                    (12.0,  4400, 1700),
                    (16.0,  3200, 1700),
                    (20.0,  2500, 1700),
                ],
            },
        },
    },

    # ─── ③ 淬火鋼 2 刃平刀 (細徑用) ───
    "hardened_2f": {
        "name_zh": "淬火鋼 2 刃平刀 (細徑/微銑用)",
        "tool_type": "square_endmill",
        "teeth_default": 2,
        "vendor": "銘九 Generic",
        "tables": {
            "HRC30_40": {
                "material_zh": "預質鋼 ~HRC30-40 (NAK80/SCM440)",
                "applicable_materials": ["NAK80", "SCM440", "HPM38"],
                "hardness_range": [30, 40],
                "table": [
                    # (D, RPM, F)
                    (1.0,  11500,  384),
                    (1.5,  10800,  480),
                    (2.0,   9472,  448),
                    (2.5,   9100,  500),
                    (3.0,   7680,  525),
                    (4.0,   6950,  680),
                    (5.0,   6400,  700),
                    (6.0,   6200,  750),
                    (7.0,   5900,  850),
                    (8.0,   4500, 1140),
                    (10.0,  2900, 1400),
                    (11.0,  2700, 1300),
                    (12.0,  2450, 1000),
                    (13.0,  1800,  700),
                    (14.0,  1680,  650),
                    (16.0,  1400,  600),
                    (20.0,   920,  550),
                ],
            },
            "HRC50_58": {
                "material_zh": "淬火工具鋼 ~HRC50-58 (SKD11/S136 淬)",
                "applicable_materials": ["SKD11", "S136", "DC53", "SKD61"],
                "hardness_range": [50, 58],
                "table": [
                    (1.0,   8896,  288),
                    (1.5,   8250,  380),
                    (2.0,   8192,  384),
                    (2.5,   8050,  420),
                    (3.0,   7150,  490),
                    (4.0,   6350,  580),
                    (5.0,   5850,  600),
                    (6.0,   5900,  650),
                    (7.0,   5000,  760),
                    (8.0,   2880,  800),
                    (10.0,  1500,  750),
                    (11.0,  1250,  500),
                    (12.0,  1020,  450),
                    (13.0,   870,  350),
                    (14.0,   740,  320),
                    (16.0,   670,  300),
                    (20.0,   440,  210),
                ],
            },
            "HRC58_62": {
                "material_zh": "高硬度模具鋼 ~HRC58-62 (SKH/SKD11 深淬)",
                "applicable_materials": ["SKD11", "SKH9", "ASP23"],
                "hardness_range": [58, 62],
                "table": [
                    (1.0,   6720,  243),
                    (1.5,   6400,  290),
                    (2.0,   5760,  320),
                    (2.5,   5600,  320),
                    (3.0,   4991,  320),
                    (4.0,   4480,  350),
                    (5.0,   4310,  360),
                    (6.0,   3900,  380),
                    (7.0,   3700,  420),
                    (8.0,   1850,  470),
                    (10.0,  1100,  380),
                    (11.0,   950,  300),
                    (12.0,   790,  270),
                    (13.0,   620,  180),
                    (14.0,   570,  170),
                    (16.0,   490,  170),
                    (20.0,   310,  170),
                ],
            },
        },
    },

    # ─── ④ 淬火鋼 4 刃平刀 (主力) ───
    "hardened_4f": {
        "name_zh": "淬火鋼 4 刃平刀 (高硬度模具鋼主力)",
        "tool_type": "square_endmill",
        "teeth_default": 4,
        "vendor": "銘九 Generic",
        "tables": {
            "HRC45_52": {
                "material_zh": "淬火鋼 ~HRC45-52 (S136/HPM38/NAK80 淬)",
                "applicable_materials": ["S136", "HPM38", "NAK80",
                                         "SKD11", "DC53"],
                "hardness_range": [45, 52],
                "table": [
                    (3.0,  14040, 1498),
                    (4.0,  10920, 1778),
                    (5.0,   9360, 2013),
                    (6.0,   8320, 2714),
                    (8.0,   4640, 2714),
                    (10.0,  3360, 2668),
                    (12.0,  2480, 2246),
                    (16.0,  1440, 1685),
                    (20.0,   612,  576),
                    (25.0,   468,  360),
                ],
            },
            "HRC52_62": {
                "material_zh": "高硬度模具鋼 ~HRC52-62",
                "applicable_materials": ["S136", "SKD11", "ASP23", "SKH9"],
                "hardness_range": [52, 62],
                "table": [
                    (3.0,   6760,  749),
                    (4.0,   5200,  842),
                    (5.0,   4628,  983),
                    (6.0,   4160, 1358),
                    (8.0,   2400, 1358),
                    (10.0,  2000, 1358),
                    (12.0,  1520, 1123),
                    (16.0,  1080,  842),
                    (20.0,   504,  456),
                    (25.0,   342,  216),
                ],
            },
        },
    },

    # ─── ⑤ 淬火鋼 4 刃加長平刀 (RPM ≈ 常規 × 53%) ───
    "hardened_4f_long": {
        "name_zh": "淬火鋼 4 刃加長平刀 (深腔/側壁用)",
        "tool_type": "square_endmill_long",
        "teeth_default": 4,
        "vendor": "銘九 Generic",
        "note": "長刃比常規 4 刃 RPM 降 ~47%, F 降 ~50% (剛性弱化補償)",
        "tables": {
            "HRC45_52": {
                "material_zh": "淬火鋼 ~HRC45-52 加長刃用",
                "applicable_materials": ["S136", "HPM38", "NAK80",
                                         "SKD11", "DC53"],
                "hardness_range": [45, 52],
                "table": [
                    (3.0,   5200,  599),
                    (4.0,   4640,  711),
                    (5.0,   3360,  805),
                    (6.0,   3080, 1086),
                    (8.0,   2240, 1086),
                    (10.0,  1800, 1087),
                    (12.0,  1320,  899),
                    (16.0,   680,  570),
                    (20.0,   510,  480),
                    (25.0,   390,  300),
                ],
            },
            "HRC52_62": {
                "material_zh": "高硬度模具鋼 ~HRC52-62 加長刃用",
                "applicable_materials": ["S136", "SKD11", "ASP23"],
                "hardness_range": [52, 62],
                "table": [
                    (3.0,   2704,  300),
                    (4.0,   2080,  337),
                    (5.0,   1851,  393),
                    (6.0,   1664,  543),
                    (8.0,   1248,  543),
                    (10.0,   998,  543),
                    (12.0,   832,  449),
                    (16.0,   624,  337),
                    (20.0,   420,  380),
                    (25.0,   285,  220),
                ],
            },
        },
    },

    # ─── ⑥ 淬火鋼球刀 ───
    "hardened_ball": {
        "name_zh": "淬火鋼球刀 (模具拋光/3D 曲面用)",
        "tool_type": "ball_endmill",
        "teeth_default": 2,
        "vendor": "銘九 Generic",
        "note": "R 為球半徑 (D = 2R). 拋光用球刀 fz 小但 RPM 高",
        "tables": {
            "HRC30": {
                "material_zh": "預質鋼 ~HRC30 (NAK80/HPM38)",
                "applicable_materials": ["NAK80", "HPM38"],
                "hardness_range": [25, 35],
                "table": [
                    # (D = 2R, RPM, F)
                    (1.0,  20480,  768),
                    (1.5,  19500,  820),
                    (2.0,  18944,  896),
                    (2.5,  17000, 1060),
                    (3.0,  15360, 1408),
                    (4.0,  14720, 2048),
                    (5.0,  13800, 2560),
                    (6.0,  12800, 2560),
                    (7.0,   9300, 2680),
                    (8.0,   8320, 2816),
                    (9.0,   6590, 2560),
                    (10.0,  4864, 2432),
                    (12.0,  3800, 2300),
                    (14.0,  2200, 1250),
                    (16.0,  1650,  780),
                    (20.0,  1100,  600),
                    (25.0,   860,  500),
                ],
            },
            "HRC52": {
                "material_zh": "淬火鋼 ~HRC52 (S136/SKD61 淬)",
                "applicable_materials": ["S136", "SKD61", "DC53"],
                "hardness_range": [48, 55],
                "table": [
                    (1.0,  16640,  512),
                    (1.5,  15700,  680),
                    (2.0,  14272,  742),
                    (2.5,  12800,  950),
                    (3.0,  11520, 1024),
                    (4.0,  10880,  960),
                    (5.0,   9984, 1280),
                    (6.0,   9728, 1216),
                    (7.0,   6800, 1420),
                    (8.0,   6144, 1536),
                    (9.0,   4100, 1108),
                    (10.0,  2560, 1152),
                    (12.0,  2560, 1280),
                    (14.0,  1580,  690),
                    (16.0,  1050,  700),
                    (20.0,   580,  410),
                    (25.0,   530,  260),
                ],
            },
            "HRC60": {
                "material_zh": "高硬度淬火鋼 ~HRC60 (SKD11 深淬)",
                "applicable_materials": ["SKD11", "ASP23", "SKH9"],
                "hardness_range": [55, 62],
                "table": [
                    (1.0,  13440,  486),
                    (1.5,  12700,  560),
                    (2.0,  11520,  640),
                    (2.5,  10500,  640),
                    (3.0,   9984,  640),
                    (4.0,   8960,  870),
                    (5.0,   7040, 1280),
                    (6.0,   6400, 1280),
                    (7.0,   4500, 1280),
                    (8.0,   3200, 1280),
                    (9.0,   2560, 1280),
                    (10.0,  2048, 1280),
                    (12.0,  1536, 1280),
                    (14.0,  1280, 1280),
                    (16.0,   700,  360),
                    (20.0,   490,  240),
                    (25.0,   385,  190),
                ],
            },
        },
    },

    # ─── ⑦ 微徑球刀 (高速主軸專用) ───
    "micro_ball": {
        "name_zh": "微徑球刀 (R<0.5, 高速主軸用)",
        "tool_type": "micro_ball_endmill",
        "teeth_default": 2,
        "vendor": "銘九 Generic",
        "note": "全壓 25000 RPM (高速主軸), 12K 機台會被鉗到 12000",
        "tables": {
            "HRC45_52": {
                "material_zh": "淬火鋼 ~HRC45-52",
                "applicable_materials": ["S136", "HPM38", "NAK80",
                                         "SKD11", "DC53"],
                "hardness_range": [45, 52],
                "table": [
                    # D = 2R
                    (0.30, 25000, 200),  # R0.15
                    (0.40, 25000, 275),  # R0.2
                    (0.50, 25000, 330),  # R0.25
                    (0.60, 25000, 418),  # R0.3
                    (0.70, 25000, 495),  # R0.35
                    (0.80, 25000, 561),  # R0.4
                    (0.90, 25000, 638),  # R0.45
                ],
            },
            "HRC52_62": {
                "material_zh": "高硬度模具鋼 ~HRC52-62",
                "applicable_materials": ["S136", "SKD11", "ASP23"],
                "hardness_range": [52, 62],
                "table": [
                    (0.30, 25000, 198),
                    (0.40, 25000, 248),
                    (0.50, 25000, 297),
                    (0.60, 25000, 376),
                    (0.70, 25000, 446),
                    (0.80, 25000, 505),
                    (0.90, 25000, 574),
                ],
            },
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  材質 + 工具類型 → 最佳 catalog 路徑 (查詢用)
# ═══════════════════════════════════════════════════════════════════════
# 用法: 給 material + tool_type → 自動回 (category, table_key)
# 多個候選按優先序; 沒命中回 None

def _match_routes(material: str,
                  tool_type: str,
                  hardness_hrc: Optional[float] = None
                  ) -> List[Tuple[str, str]]:
    """依材質+工具類型+硬度 推斷候選 (category, table) 列表。

    ★ 2026.05 修正: 材質鍵預設 = 出貨/退火態
      - "SKD11" / "S136" / "DC53" / "SKD61" 預設 HRC=20-22 (出貨態)
        → 不走 hardened_4f, 應該走 alu_square (沒有專用碳鋼表) 或回 L3
      - "SKD11_hardened" / "SKD11" + hardness_hrc>=45 才走 hardened 系列
      - "NAK80" / "HPM38" 出廠就預質 → 走 hardened 系列
    """
    m = (material or "").strip()
    tt = (tool_type or "square").lower()
    routes: List[Tuple[str, str]] = []

    is_alu = m in ("AL6061", "AL7075", "Plastics")
    is_copper = m in ("Brass", "Copper", "C1020")

    # ★ 退火態材質 (出貨, 還沒熱處理) → 不能走 hardened 表
    annealed_steel_keys = ("S136", "SKD11", "SKD61", "DC53",
                           "S50C", "S45C", "Cast_Iron")
    # ★ 淬火態 / 預質鋼 (出廠或熱處理後已硬化) → 走 hardened 表
    prehardened_keys = ("NAK80", "HPM38", "SCM440")  # 出貨即預質
    hardened_keys = ("ASP23", "SKH9")                # 出貨即高硬度
    is_hardened_explicit = m.endswith("_hardened")

    # 顯式優先級: hardness_hrc 給定 → 完全依硬度決定
    if hardness_hrc is not None:
        is_hardened = hardness_hrc >= 40
        is_annealed_steel = (m in annealed_steel_keys) and not is_hardened
    else:
        # 沒給硬度 → 依材質鍵預設語義
        is_annealed_steel = (m in annealed_steel_keys) and not is_hardened_explicit
        is_hardened = (m in prehardened_keys or m in hardened_keys
                       or is_hardened_explicit)

    is_ball = ("ball" in tt) or tt == "球刀"
    is_micro = ("micro" in tt) or tt == "微徑球刀"
    is_long = ("long" in tt) or tt == "長刃"

    # ─── 鋁/銅 ───
    if is_alu:
        if is_ball:
            routes.append(("alu_ball", "A5020_alu"))
        else:
            routes.append(("alu_square", "A5020_alu"))
    elif is_copper:
        if is_ball:
            routes.append(("alu_ball", "C1020_copper"))
        else:
            routes.append(("alu_square", "C1020_copper"))

    # ─── 退火態鋼: 銘九沒有對應通用表, 回空 List 強制走 L3 ───
    #   (用戶實機在 S50C/SKD11退火 等價情境用 CIB 表 = L2, 由 keili_catalog 處理)
    if is_annealed_steel:
        return routes  # 不加任何 hardened 路由

    # ─── 預質/淬火鋼 ───
    if is_hardened:
        # 解析硬度
        h = hardness_hrc
        if h is None:
            base = m.replace("_hardened", "")
            hardened_hrc_map = {
                "SKD11": 60, "S136": 52, "DC53": 60, "SKD61": 50,
                "NAK80": 40, "HPM38": 36, "SCM440": 30,
                "ASP23": 62, "SKH9": 60,
            }
            h = hardened_hrc_map.get(base, 50)

        if is_micro:
            key = "HRC45_52" if h < 52 else "HRC52_62"
            routes.append(("micro_ball", key))
        elif is_ball:
            if h < 40:    key = "HRC30"
            elif h < 55:  key = "HRC52"
            else:         key = "HRC60"
            routes.append(("hardened_ball", key))
        elif is_long:
            key = "HRC45_52" if h < 52 else "HRC52_62"
            routes.append(("hardened_4f_long", key))
        else:
            # 預設用 4 刃平刀 (主力)
            key_4f = "HRC45_52" if h < 52 else "HRC52_62"
            routes.append(("hardened_4f", key_4f))
            # 備援用 2 刃 (細徑時更穩)
            if h < 45:    key_2f = "HRC30_40"
            elif h < 58:  key_2f = "HRC50_58"
            else:         key_2f = "HRC58_62"
            routes.append(("hardened_2f", key_2f))

    return routes


# ═══════════════════════════════════════════════════════════════════════
#  插值與推薦 API
# ═══════════════════════════════════════════════════════════════════════

def _interp(table: List[Tuple[float, float, float]],
            D: float) -> Tuple[Optional[float], Optional[float]]:
    """線性插值 (D, RPM, F)。超出範圍 clamp 到端點。"""
    if not table:
        return (None, None)
    s = sorted(table, key=lambda r: r[0])
    if D <= s[0][0]:
        return (float(s[0][1]), float(s[0][2]))
    if D >= s[-1][0]:
        return (float(s[-1][1]), float(s[-1][2]))
    for i in range(len(s) - 1):
        d_lo, r_lo, f_lo = s[i]
        d_hi, r_hi, f_hi = s[i + 1]
        if d_lo <= D <= d_hi:
            if d_hi == d_lo:
                return (float(r_lo), float(f_lo))
            t = (D - d_lo) / (d_hi - d_lo)
            return (r_lo + t * (r_hi - r_lo), f_lo + t * (f_hi - f_lo))
    return (None, None)


def recommend(material: str,
              tool_dia: float,
              tool_type: str = "square_endmill",
              hardness_hrc: Optional[float] = None,
              mode: str = "conservative",
              rpm_factor: Optional[float] = None,
              feed_factor: Optional[float] = None) -> Dict[str, Any]:
    """銘九通用表查詢 + 線性插值 + 散件折扣。

    Args:
        material:     工件材質 (AL6061/Brass/S136/SKD11...)
        tool_dia:     刀徑 mm (球刀用球徑 D=2R)
        tool_type:    square_endmill / ball / micro_ball / long
        hardness_hrc: 工件硬度 HRC (用來選硬度欄, 沒給就從材質推測)
        mode:         conservative (預設 75/50 折) / aggressive (滿表值)
        rpm_factor:   覆蓋 mode 預設
        feed_factor:  覆蓋 mode 預設

    Returns:
        {success, layer="L2B_AMBER", route, params, ...}
    """
    routes = _match_routes(material, tool_type, hardness_hrc)
    if not routes:
        return {
            "success": False,
            "error": f"銘九通用表無 {material} ({tool_type}) 對映",
            "tip": "改用 keili_catalog 或 machining_heuristics L3",
        }

    # 套散件折扣
    if rpm_factor is None:
        rpm_factor = 0.75 if mode == "conservative" else 1.00
    if feed_factor is None:
        feed_factor = 0.50 if mode == "conservative" else 1.00

    # 試每個路徑
    for cat_key, tbl_key in routes:
        cat = CATALOG.get(cat_key)
        if not cat:
            continue
        tbl_data = cat["tables"].get(tbl_key)
        if not tbl_data:
            continue
        rpm_max, feed_max = _interp(tbl_data["table"], float(tool_dia))
        if rpm_max is None:
            continue

        rpm = float(rpm_max) * float(rpm_factor)
        feed = float(feed_max) * float(feed_factor)

        return {
            "success": True,
            "layer": "L2B_AMBER",
            "confidence": 0.70,
            "material": material,
            "tool_dia_mm": float(tool_dia),
            "tool_type": tool_type,
            "route": {
                "category": cat_key,
                "category_zh": cat["name_zh"],
                "table_key": tbl_key,
                "material_match_zh": tbl_data["material_zh"],
                "applicable_materials": tbl_data.get("applicable_materials"),
                "hardness_range": tbl_data.get("hardness_range"),
            },
            "params": {
                "rpm": int(round(rpm)),
                "feed_mm_min": int(round(feed)),
                "Vc_m_min": round(math.pi * float(tool_dia) * rpm / 1000.0, 1),
                "teeth": cat.get("teeth_default"),
                "rpm_vendor_max": int(rpm_max),
                "feed_vendor_max": int(feed_max),
            },
            "mode": mode,
            "rpm_factor": rpm_factor,
            "feed_factor": feed_factor,
            "source": f"銘九通用表 / {cat['name_zh']} / {tbl_data['material_zh']}",
            "note": (f"銘九通用值: {cat['name_zh']} D={tool_dia}mm "
                     f"@ {tbl_data['material_zh']} "
                     f"{'散件' if mode=='conservative' else '量產'} "
                     f"RPM={int(round(rpm))} F={int(round(feed))} "
                     f"(廠商上限 {int(rpm_max)}/{int(feed_max)} × "
                     f"{rpm_factor}/{feed_factor})"),
        }

    return {
        "success": False,
        "error": f"路徑 {routes} 都無數據",
    }


# ═══════════════════════════════════════════════════════════════════════
#  ★ 防護層 (Sanity Check) ─ 用戶 2026.05 指示
#  「數值超過太多會是低太多就有可能有問題」
#  用銘九通用表 (廠商通用值) 當 L1/L2/L3 結果的「夾擠驗證」
# ═══════════════════════════════════════════════════════════════════════

def sanity_check(material: str,
                 tool_dia: float,
                 rpm_proposed: float,
                 feed_proposed: float,
                 tool_type: str = "square_endmill",
                 hardness_hrc: Optional[float] = None,
                 high_tol_pct: float = 30.0,
                 low_tol_pct: float = 60.0) -> Dict[str, Any]:
    """把候選 (rpm, feed) 跟銘九通用表 (aggressive 滿表值) 比對。

    觸發條件:
      - 候選 RPM > 銘九上限 × (1 + high_tol_pct/100)  → 過快警告
      - 候選 RPM < 銘九上限 × (1 - low_tol_pct/100)   → 過保守提示
      - 候選 Feed 同上

    Args:
        rpm_proposed:    待驗證的 RPM
        feed_proposed:   待驗證的 Feed mm/min
        high_tol_pct:    超出上限多少 % 算「過快」(預設 30%)
        low_tol_pct:     低於上限多少 % 算「過保守」(預設 60%)

    Returns:
        {status: 'PASS'/'WARN'/'BLOCKED'/'NO_BENCHMARK', ...}
        - PASS         = 在合理區間內
        - WARN         = 偏離廠商通用值, 但仍可上機
        - BLOCKED      = 嚴重超過廠商上限, 可能有問題
        - NO_BENCHMARK = 銘九表沒有對應資料 (無從比對)
    """
    bench = recommend(material=material,
                      tool_dia=tool_dia,
                      tool_type=tool_type,
                      hardness_hrc=hardness_hrc,
                      mode="aggressive")  # 銘九「滿表值」當基準
    if not bench.get("success"):
        return {
            "status": "NO_BENCHMARK",
            "material": material,
            "tool_dia_mm": tool_dia,
            "tool_type": tool_type,
            "note": f"銘九通用表無 {material} ({tool_type}) D={tool_dia} 對映, "
                    f"無從做防護驗證 (可考慮回報補資料)",
        }

    bench_rpm = float(bench["params"]["rpm"])
    bench_feed = float(bench["params"]["feed_mm_min"])
    rpm_ratio = rpm_proposed / bench_rpm if bench_rpm else 0
    feed_ratio = feed_proposed / bench_feed if bench_feed else 0

    high_factor = 1 + high_tol_pct / 100.0
    low_factor = 1 - low_tol_pct / 100.0

    warnings: List[str] = []
    blocks: List[str] = []

    # RPM 防護
    if rpm_proposed > bench_rpm * (1 + 2 * high_tol_pct / 100.0):
        blocks.append(
            f"RPM 過高: {int(rpm_proposed)} > 銘九上限 {int(bench_rpm)} "
            f"× {1 + 2*high_tol_pct/100:.1f} (嚴重超標 ≥ {2*high_tol_pct:.0f}%)"
        )
    elif rpm_proposed > bench_rpm * high_factor:
        warnings.append(
            f"RPM 偏高: {int(rpm_proposed)} > 銘九上限 {int(bench_rpm)} "
            f"× {high_factor:.2f} (+{(rpm_ratio-1)*100:.0f}%)"
        )
    elif rpm_proposed < bench_rpm * low_factor:
        warnings.append(
            f"RPM 偏保守: {int(rpm_proposed)} < 銘九上限 {int(bench_rpm)} "
            f"× {low_factor:.2f} (-{(1-rpm_ratio)*100:.0f}%, 可考慮放寬)"
        )

    # Feed 防護
    if feed_proposed > bench_feed * (1 + 2 * high_tol_pct / 100.0):
        blocks.append(
            f"Feed 過高: {int(feed_proposed)} > 銘九上限 {int(bench_feed)} "
            f"× {1 + 2*high_tol_pct/100:.1f} (嚴重超標 ≥ {2*high_tol_pct:.0f}%)"
        )
    elif feed_proposed > bench_feed * high_factor:
        warnings.append(
            f"Feed 偏高: {int(feed_proposed)} > 銘九上限 {int(bench_feed)} "
            f"× {high_factor:.2f} (+{(feed_ratio-1)*100:.0f}%)"
        )
    elif feed_proposed < bench_feed * low_factor:
        warnings.append(
            f"Feed 偏保守: {int(feed_proposed)} < 銘九上限 {int(bench_feed)} "
            f"× {low_factor:.2f} (-{(1-feed_ratio)*100:.0f}%, 可考慮放寬)"
        )

    if blocks:
        status = "BLOCKED"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "material": material,
        "tool_dia_mm": tool_dia,
        "tool_type": tool_type,
        "proposed": {
            "rpm": int(round(rpm_proposed)),
            "feed_mm_min": int(round(feed_proposed)),
        },
        "benchmark_mingjiu": {
            "rpm": int(bench_rpm),
            "feed_mm_min": int(bench_feed),
            "source": bench.get("source"),
            "table": bench.get("route", {}).get("table_key"),
        },
        "ratio": {
            "rpm": round(rpm_ratio, 2),
            "feed": round(feed_ratio, 2),
        },
        "tolerance": {
            "high_pct": high_tol_pct,
            "low_pct": low_tol_pct,
        },
        "warnings": warnings,
        "blocks": blocks,
        "advice": (
            "建議照常上機" if status == "PASS" else
            ("可上機但留意 (建議首件慢進確認)" if status == "WARN" else
             "建議重新檢查參數或材質硬度設定")
        ),
    }


def list_routes(material: Optional[str] = None,
                tool_type: Optional[str] = None) -> Dict[str, Any]:
    """列出所有可用路徑 (給 cam-helper 查詢用)。"""
    if material and tool_type:
        routes = _match_routes(material, tool_type)
        return {
            "success": True,
            "material": material,
            "tool_type": tool_type,
            "routes": [{"category": c, "table": t} for c, t in routes],
        }
    # 列全部
    out = {}
    for k, v in CATALOG.items():
        out[k] = {
            "name_zh": v["name_zh"],
            "tool_type": v.get("tool_type"),
            "teeth_default": v.get("teeth_default"),
            "tables": list(v.get("tables", {}).keys()),
            "applicable_materials": list(set(
                m for tbl in v.get("tables", {}).values()
                for m in tbl.get("applicable_materials", [])
            )),
        }
    return {"success": True, "catalog": out,
            "total_tables": sum(len(c.get("tables", {}))
                                for c in CATALOG.values())}


# ═══════════════════════════════════════════════════════════════════════
#  MCP dispatch
# ═══════════════════════════════════════════════════════════════════════

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point。

    params:
      {"mode": "list_routes"}                                 → 全表列表
      {"mode": "list_routes", "material": "...", "tool_type": "..."} → 篩選
      {"mode": "recommend", "material": "...", "tool_dia": ...,
                            "tool_type": "...", "hardness_hrc": ...,
                            "mode_strategy": "conservative"} → 推薦
    """
    mode = (params.get("mode") or "list_routes").lower()

    if mode == "list_routes":
        return list_routes(
            material=params.get("material"),
            tool_type=params.get("tool_type"),
        )

    if mode == "recommend":
        mat = params.get("material")
        D = params.get("tool_dia") or params.get("diameter_mm")
        if not mat or D is None:
            return {"success": False, "error": "需 material 與 tool_dia"}
        return recommend(
            material=mat,
            tool_dia=float(D),
            tool_type=params.get("tool_type") or "square_endmill",
            hardness_hrc=(float(params["hardness_hrc"])
                          if params.get("hardness_hrc") else None),
            mode=(params.get("mode_strategy") or "conservative"),
            rpm_factor=(float(params["rpm_factor"])
                        if params.get("rpm_factor") else None),
            feed_factor=(float(params["feed_factor"])
                         if params.get("feed_factor") else None),
        )

    if mode == "sanity_check":
        mat = params.get("material")
        D = params.get("tool_dia") or params.get("diameter_mm")
        rpm_p = params.get("rpm") or params.get("rpm_proposed")
        feed_p = params.get("feed_mm_min") or params.get("feed_proposed")
        if not all([mat, D, rpm_p, feed_p]):
            return {"success": False,
                    "error": "需 material / tool_dia / rpm / feed_mm_min"}
        return sanity_check(
            material=mat,
            tool_dia=float(D),
            rpm_proposed=float(rpm_p),
            feed_proposed=float(feed_p),
            tool_type=params.get("tool_type") or "square_endmill",
            hardness_hrc=(float(params["hardness_hrc"])
                          if params.get("hardness_hrc") else None),
            high_tol_pct=float(params.get("high_tol_pct", 30.0)),
            low_tol_pct=float(params.get("low_tol_pct", 60.0)),
        )

    return {"success": False, "error": f"未知 mode: {mode}",
            "valid_modes": ["list_routes", "recommend", "sanity_check"]}
