# -*- coding: utf-8 -*-
"""
廠商刀具目錄 - 結構化資料 (多廠商混合)
================================================
資料來源：用戶提供的型錄 PDF / 截圖 / CSV，手動或半自動解析
覆蓋系列：
  [銑削 - 奇力揚 KEILI]
  CIB  (A419) - 無敵重切削銑刀 (碳鋼/預質鋼/鑄鐵 重切削)
  CAVN (A413) - 鈦合金銑刀 (不鏽鋼/鈦合金/熱處理鋼)
  CLUS (A412/A412L) - 鏡面無痕鋁用銑刀 (鋁合金/工程塑膠)
  [螺紋 - 奇力揚 KEILI / TOPMS]
  CFSL (A804) - 鎢鋼螺旋銑牙刀 (M3-M27 全材質銑牙)
  CH01M (TOPMS) - 含鈷螺旋絲攻 (M2-M24 全材質攻牙) [德國棒材]
  [鑽孔 - OSG]
  SG (OSG) - SG 高速鋼鑽頭 (S50C/AL6061 實機保守值: 75折轉速 + 6折進給)

廠商推薦參數計算公式：
  S (rpm)    = V × 318.3 / D
  F (mm/min) = S × FZ × Z      (Z = 刃數)
  Ae (切寬)  = 0.25D ~ 0.75D

與 Smart_AI_CAM 刀具庫對應：
  CLUS = 刀具庫【ALUS】鎢鋼銑刀 (鋁用 3 刃)
  CIB  = 刀具庫【CIB】鎢鋼銑刀  (鋼用 4 刃)
  CAVN = 進階款 (刀具庫目前未列，可導入用於不鏽鋼/鈦合金)

設計原則：
  廠商推薦值優先級 > Smart_AI_CAM 物理引擎估算值
  此模組提供 cam-helper 在「材質+刀徑+刀具系列」匹配時調用真實廠商數據
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


# ============================================================
# 完整目錄資料（從 user 提供的 3 張截圖手動 OCR 整理）
# ============================================================

CATALOG: Dict[str, Any] = {
    "vendor": "奇力揚",
    "vendor_en": "KEILI",
    "year": 2023,
    "source": "用戶提供 PDF 截圖 (A412/A413/A419)",
    "formulas": {
        "spindle_rpm": "S = V × 318.3 / D",
        "feed_mm_min": "F = S × FZ × Z",
        "stepover_range": "0.25D ≤ Ae ≤ 0.75D",
        "S": "主軸轉速 rpm",
        "V": "切削速度 m/min",
        "D": "刀具直徑 mm",
        "FZ": "每刃進給 mm/tooth",
        "Z": "刃數",
        "Ae": "切寬 mm",
    },

    "series": {
        # ============================================================
        # CIB - 無敵重切削銑刀 (A419)
        # ============================================================
        "CIB": {
            "code": "A419",
            "name": "無敵重切削銑刀",
            "name_en": "CIB Heavy Cutting End Mill",
            "use_cases": ["粗加工", "3D輪廓", "重切削"],
            "use_cases_not": ["精加工 (NG)", "刃向插銑 (NG)"],
            "ok_use_cases_partial": ["插孔", "平面精銑"],
            "suitable_materials": ["P_steel", "K_cast_iron", "N_non_ferrous"],
            "suitable_materials_zh": ["P 鋼 (碳鋼/預質鋼)", "K 鑄鐵", "N 非鐵金屬"],
            "not_suitable": ["M_stainless", "H_heat_treated", "S_titanium_nickel"],
            "features": [
                "圓溝設計，剛性增加，排屑性好",
                "不等分割變導程設計，切削穩定性佳",
                "刀具抗折性佳，適合重切削",
            ],
            "flutes_default": 4,
            "smart_ai_cam_match": {
                "category_zh": "【CIB】鎢鋼銑刀",
                "category_key": "end_mill_steel",
                "note": "完全對應 Smart_AI_CAM 刀具庫 CIB 系列",
            },
            "tools": [
                # 型號, D, T, H(刃長), d(柄徑), L(總長)
                {"sku": "CIB0204", "D": 2,  "T": 4, "H": 5,  "d": 4,  "L": 50},
                {"sku": "CIB0304", "D": 3,  "T": 4, "H": 8,  "d": 4,  "L": 50},
                {"sku": "CIB0306", "D": 3,  "T": 4, "H": 8,  "d": 6,  "L": 50},
                {"sku": "CIB0404", "D": 4,  "T": 4, "H": 10, "d": 4,  "L": 50},
                {"sku": "CIB0406", "D": 4,  "T": 4, "H": 10, "d": 6,  "L": 50},
                {"sku": "CIB0506", "D": 5,  "T": 4, "H": 13, "d": 6,  "L": 50},
                {"sku": "CIB0606", "D": 6,  "T": 4, "H": 15, "d": 6,  "L": 50},
                {"sku": "CIB0708", "D": 7,  "T": 4, "H": 18, "d": 8,  "L": 60},
                {"sku": "CIB0808", "D": 8,  "T": 4, "H": 20, "d": 8,  "L": 60},
                {"sku": "CIB1010", "D": 10, "T": 4, "H": 30, "d": 10, "L": 75},
                {"sku": "CIB1112", "D": 11, "T": 4, "H": 32, "d": 12, "L": 75},
                {"sku": "CIB1212", "D": 12, "T": 4, "H": 32, "d": 12, "L": 75},
                {"sku": "CIB1616", "D": 16, "T": 4, "H": 50, "d": 16, "L": 110},
            ],
            # 切削條件表（廠商推薦）
            "cutting_table": {
                "carbon_steel": {
                    "material_zh": "碳鋼",
                    "smart_ai_cam_materials": ["S45C", "S50C"],
                    "V_m_min_range": [95, 120],
                    "FZ_mm_tooth": {
                        "D1-D4":   [0.02, 0.035],
                        "D6-D10":  [0.03, 0.05],
                        "D12-D16": [0.03, 0.06],
                    },
                },
                "pre_hardened_steel": {
                    "material_zh": "預質鋼 (HRC 35-45)",
                    "smart_ai_cam_materials": ["NAK80"],
                    "V_m_min_range": [95, 120],
                    "FZ_mm_tooth": {
                        "D1-D4":   [0.01, 0.025],
                        "D6-D10":  [0.02, 0.03],
                        "D12-D16": [0.02, 0.04],
                    },
                },
            },
            # ★ 官網切削條件表 — CIB 無敵銑刀 (Side / Slot Milling Conditions)
            # 來源: chliyang.com.tw CIB 無敵銑刀 (2026.05 用戶提供 PDF 影像)
            # 區分「側銑 Side Milling (Ap≤1.5D, Ae≤0.4D)」與
            #     「溝銑 Slot Milling (Ap≤1D, Ae=1.0D)」兩個工法
            # × 4 個材質硬度欄 (碳鋼/SCM 30HRC/SCM 45HRC/不銹鋼)
            # → 這是「理想值」(廠商給的最大切削量),
            #   散件「上機值」 = 此表 × 散件折扣 (RPM×0.75 / F×0.5 典型)
            #   實機驗證: D=10 S50C 側銑 V=87 (官網 120 的 72.5%) ✓
            "params_table_official": {
                "side": {  # 側面切削 Ap≤1.5D, Ae≤0.4D
                    "S50C_20HRC": {
                        "material_zh": "碳素鋼/鑄鐵 S45C/FC ~20HRC",
                        "smart_ai_cam_materials": ["S50C", "S45C"],
                        "Vc_range": [110, 130],
                        # (D, RPM, Fz_min, Fz_max)
                        "table": [
                            (2.0,  19100, 0.010, 0.015),
                            (3.0,  12730, 0.010, 0.020),
                            (4.0,   9550, 0.010, 0.025),
                            (5.0,   7640, 0.015, 0.030),
                            (6.0,   6370, 0.020, 0.040),
                            (8.0,   4770, 0.030, 0.060),
                            (10.0,  3820, 0.030, 0.080),
                            (12.0,  3180, 0.040, 0.100),
                            (16.0,  2390, 0.050, 0.120),
                            (20.0,  1910, 0.050, 0.140),
                        ],
                    },
                    "SCM_30HRC": {
                        "material_zh": "合金鋼 SCM/SKT/SKD/SCr ~30HRC",
                        "smart_ai_cam_materials": ["SCM440", "SKT", "SCr"],
                        "Vc_range": [100, 120],
                        "table": [
                            (2.0,  17510, 0.010, 0.015),
                            (3.0,  11670, 0.010, 0.020),
                            (4.0,   8750, 0.010, 0.025),
                            (5.0,   7000, 0.015, 0.030),
                            (6.0,   5840, 0.020, 0.040),
                            (8.0,   4380, 0.030, 0.060),
                            (10.0,  3500, 0.030, 0.080),
                            (12.0,  2920, 0.040, 0.100),
                            (16.0,  2190, 0.050, 0.120),
                            (20.0,  1750, 0.050, 0.140),
                        ],
                    },
                    "SCM_45HRC": {
                        "material_zh": "合金鋼/模具鋼 SCM/SKT/SKD ~45HRC",
                        "smart_ai_cam_materials": ["NAK80", "HPM38", "S136", "SKD11", "SKD61", "DC53"],
                        "Vc_range": [90, 110],
                        "table": [
                            (2.0,  15920, 0.005, 0.010),
                            (3.0,  10610, 0.010, 0.015),
                            (4.0,   7960, 0.010, 0.020),
                            (5.0,   6370, 0.010, 0.025),
                            (6.0,   5310, 0.020, 0.040),
                            (8.0,   3980, 0.020, 0.050),
                            (10.0,  3180, 0.025, 0.060),
                            (12.0,  2650, 0.025, 0.070),
                            (16.0,  1990, 0.030, 0.080),
                            (20.0,  1590, 0.030, 0.100),
                        ],
                    },
                    "SUS": {
                        "material_zh": "不銹鋼 SUS3/SUS4",
                        "smart_ai_cam_materials": ["SUS304", "SUS316", "SUS420", "SUS440"],
                        "Vc_range": [60, 80],
                        "table": [
                            (2.0,  11940, 0.005, 0.010),
                            (3.0,   7960, 0.010, 0.015),
                            (4.0,   5970, 0.010, 0.020),
                            (5.0,   4770, 0.015, 0.025),
                            (6.0,   3980, 0.020, 0.040),
                            (8.0,   2980, 0.020, 0.050),
                            (10.0,  2390, 0.030, 0.060),
                            (12.0,  1990, 0.030, 0.070),
                            (16.0,  1490, 0.040, 0.080),
                            (20.0,  1190, 0.040, 0.090),
                        ],
                    },
                },
                "slot": {  # 溝銑 Ap≤1D, Ae=1.0D
                    "S50C_20HRC": {
                        "material_zh": "碳素鋼/鑄鐵 S45C/FC ~20HRC",
                        "smart_ai_cam_materials": ["S50C", "S45C"],
                        "Vc_range": [100, 120],
                        "table": [
                            (2.0,  17510, 0.010, 0.015),
                            (3.0,  11670, 0.010, 0.020),
                            (4.0,   8750, 0.010, 0.025),
                            (5.0,   7000, 0.015, 0.030),
                            (6.0,   5840, 0.020, 0.040),
                            (8.0,   4380, 0.030, 0.060),
                            (10.0,  3500, 0.030, 0.080),
                            (12.0,  2920, 0.040, 0.100),
                            (16.0,  2190, 0.050, 0.120),
                            (20.0,  1750, 0.050, 0.140),
                        ],
                    },
                    "SCM_30HRC": {
                        "material_zh": "合金鋼 SCM/SKT/SKD/SCr ~30HRC",
                        "smart_ai_cam_materials": ["SCM440", "SKT", "SCr"],
                        "Vc_range": [90, 110],
                        "table": [
                            (2.0,  15920, 0.010, 0.015),
                            (3.0,  10610, 0.010, 0.020),
                            (4.0,   7960, 0.010, 0.025),
                            (5.0,   6370, 0.015, 0.030),
                            (6.0,   5310, 0.020, 0.040),
                            (8.0,   3980, 0.030, 0.060),
                            (10.0,  3180, 0.030, 0.080),
                            (12.0,  2650, 0.040, 0.100),
                            (16.0,  1990, 0.050, 0.120),
                            (20.0,  1590, 0.050, 0.140),
                        ],
                    },
                    "SCM_45HRC": {
                        "material_zh": "合金鋼/模具鋼 SCM/SKT/SKD ~45HRC",
                        "smart_ai_cam_materials": ["NAK80", "HPM38", "S136", "SKD11", "SKD61", "DC53"],
                        "Vc_range": [70, 90],
                        "table": [
                            (2.0,  12730, 0.005, 0.010),
                            (3.0,   8490, 0.010, 0.015),
                            (4.0,   6370, 0.010, 0.020),
                            (5.0,   5090, 0.010, 0.025),
                            (6.0,   4240, 0.020, 0.040),
                            (8.0,   3180, 0.020, 0.050),
                            (10.0,  2550, 0.025, 0.060),
                            (12.0,  2120, 0.025, 0.070),
                            (16.0,  1590, 0.030, 0.080),
                            (20.0,  1270, 0.030, 0.100),
                        ],
                    },
                    "SUS": {
                        "material_zh": "不銹鋼 SUS3/SUS4",
                        "smart_ai_cam_materials": ["SUS304", "SUS316", "SUS420", "SUS440"],
                        "Vc_range": [50, 70],
                        "table": [
                            (2.0,   9550, 0.005, 0.010),
                            (3.0,   6370, 0.010, 0.015),
                            (4.0,   4770, 0.010, 0.020),
                            (5.0,   3820, 0.015, 0.025),
                            (6.0,   3180, 0.020, 0.040),
                            (8.0,   2390, 0.020, 0.050),
                            (10.0,  1910, 0.030, 0.060),
                            (12.0,  1590, 0.030, 0.070),
                            (16.0,  1190, 0.040, 0.080),
                            (20.0,   950, 0.040, 0.090),
                        ],
                    },
                },
            },
        },

        # ============================================================
        # CAVN - 鈦合金銑刀 (A413)
        # ============================================================
        "CAVN": {
            "code": "A413",
            "name": "鈦合金銑刀",
            "name_en": "CAVN Titanium Alloy End Mill",
            "use_cases": ["粗加工", "精加工", "纜線加工", "3D輪廓",
                          "平面精銑", "重切削"],
            "use_cases_partial": ["刃向插銑"],
            "use_cases_not": ["旋槽斜降 (NG)"],
            "suitable_materials": ["M_stainless", "H_heat_treated",
                                   "N_non_ferrous", "S_titanium_nickel"],
            "suitable_materials_zh": ["M 不鏽鋼", "H 熱處理",
                                      "N 非鐵金屬", "S 鈦鎳"],
            "not_suitable": ["P_steel (use CIB instead)"],
            "features": [
                "雙溝槽設計，可粗銑可精銑",
                "不等分割變導程，切削能力佳",
                "G1 塗層，摩擦係數低不黏屑",
            ],
            "flutes_default": 4,
            "smart_ai_cam_match": {
                "category_zh": "(進階款 - 刀具庫目前未列)",
                "category_key": "end_mill_titanium",
                "note": "可導入支援 SUS304/Ti-6Al-4V/SKD11 等高階加工",
            },
            "tools": [
                {"sku": "CAVN0104",  "D": 1,   "T": 3, "H": 2.5,  "d": 4,  "L": 50},
                {"sku": "CAVN01504", "D": 1.5, "T": 4, "H": 4,    "d": 4,  "L": 50},
                {"sku": "CAVN0204",  "D": 2,   "T": 4, "H": 5,    "d": 4,  "L": 50},
                {"sku": "CAVN0206",  "D": 2,   "T": 4, "H": 5,    "d": 6,  "L": 50},
                {"sku": "CAVN02504", "D": 2.5, "T": 4, "H": 6.25, "d": 4,  "L": 50},
                {"sku": "CAVN0304",  "D": 3,   "T": 4, "H": 7.5,  "d": 4,  "L": 50},
                {"sku": "CAVN0306",  "D": 3,   "T": 4, "H": 7.5,  "d": 6,  "L": 50},
                {"sku": "CAVN03504", "D": 3.5, "T": 4, "H": 10,   "d": 4,  "L": 50},
                {"sku": "CAVN0404",  "D": 4,   "T": 4, "H": 10,   "d": 4,  "L": 50},
                {"sku": "CAVN0406",  "D": 4,   "T": 4, "H": 10,   "d": 6,  "L": 50},
                {"sku": "CAVN0506",  "D": 5,   "T": 4, "H": 13,   "d": 6,  "L": 50},
                {"sku": "CAVN0606",  "D": 6,   "T": 4, "H": 15,   "d": 6,  "L": 50},
                {"sku": "CAVN0708",  "D": 7,   "T": 4, "H": 18,   "d": 8,  "L": 60},
                {"sku": "CAVN0808",  "D": 8,   "T": 4, "H": 20,   "d": 8,  "L": 60},
                {"sku": "CAVN1010",  "D": 10,  "T": 4, "H": 30,   "d": 10, "L": 75},
                {"sku": "CAVN1212",  "D": 12,  "T": 4, "H": 32,   "d": 12, "L": 75},
                {"sku": "CAVN1616",  "D": 16,  "T": 4, "H": 45,   "d": 16, "L": 100},
                {"sku": "CAVN2020",  "D": 20,  "T": 4, "H": 50,   "d": 20, "L": 100},
            ],
            "cutting_table": {
                "stainless_steel": {
                    "material_zh": "不鏽鋼",
                    "smart_ai_cam_materials": ["SUS304", "SUS316"],
                    "V_m_min_range": [69, 110],
                    "FZ_mm_tooth": {
                        "D1-D4":   [0.02, 0.03],
                        "D6-D10":  [0.02, 0.035],
                        "D12-D16": [0.02, 0.04],
                    },
                },
                "titanium_alloy": {
                    "material_zh": "鈦合金",
                    "smart_ai_cam_materials": ["Ti-6Al-4V", "TC4"],
                    "V_m_min_range": [69, 110],
                    "FZ_mm_tooth": {
                        "D1-D4":   [0.02, 0.03],
                        "D6-D10":  [0.03, 0.04],
                        "D12-D16": [0.03, 0.05],
                    },
                },
            },
        },

        # ============================================================
        # CLUS - 鏡面無痕鋁用銑刀 (A412 / A412L)
        # ============================================================
        "CLUS": {
            "code": "A412 / A412L",
            "name": "鏡面無痕鋁用銑刀",
            "name_en": "CLUS Mirror Finish Aluminum End Mill",
            "use_cases": ["精加工", "纜線加工", "3D輪廓", "平面精銑"],
            "use_cases_partial": ["刃向插銑"],
            "use_cases_not": ["粗加工 (改用 CIB)", "重切削 (改用 CIB)"],
            "suitable_materials": ["N_non_ferrous"],
            "suitable_materials_zh": ["N 非鐵金屬 (鋁合金/工程塑膠)"],
            "not_suitable": ["P_steel", "M_stainless", "H_heat_treated",
                             "S_titanium_nickel", "K_cast_iron"],
            "features": [
                "橫向側鏡面無拉痕",
                "針對航太 7075 鋁合金壽命穩佳",
                "適用中精加工",
            ],
            "flutes_default": 3,
            "smart_ai_cam_match": {
                "category_zh": "【ALUS】鎢鋼銑刀",
                "category_key": "end_mill_alu",
                "note": "對應 Smart_AI_CAM 刀具庫 ALUS 系列 (3 刃鋁用)",
            },
            "tools_standard": [  # A412 標準型
                {"sku": "CLUS01504","D": 1.5,"T": 3, "H": 4.5, "d": 4,  "L": 50},
                {"sku": "CLUS0204", "D": 2,  "T": 3, "H": 6,   "d": 4,  "L": 50},
                {"sku": "CLUS0206", "D": 2,  "T": 3, "H": 6,   "d": 6,  "L": 50},
                {"sku": "CLUS0303", "D": 3,  "T": 3, "H": 9,   "d": 3,  "L": 50},
                {"sku": "CLUS0304", "D": 3,  "T": 3, "H": 9,   "d": 4,  "L": 50},
                {"sku": "CLUS0306", "D": 3,  "T": 3, "H": 9,   "d": 6,  "L": 50},
                {"sku": "CLUS0404", "D": 4,  "T": 3, "H": 12,  "d": 4,  "L": 50},
                {"sku": "CLUS0406", "D": 4,  "T": 3, "H": 12,  "d": 6,  "L": 50},
                {"sku": "CLUS0506", "D": 5,  "T": 3, "H": 15,  "d": 6,  "L": 50},
                {"sku": "CLUS0606", "D": 6,  "T": 3, "H": 18,  "d": 6,  "L": 50},
                {"sku": "CLUS0808", "D": 8,  "T": 3, "H": 24,  "d": 8,  "L": 60},
                {"sku": "CLUS1010", "D": 10, "T": 3, "H": 30,  "d": 10, "L": 75},
                {"sku": "CLUS1212", "D": 12, "T": 3, "H": 36,  "d": 12, "L": 75},
                {"sku": "CLUS1616", "D": 16, "T": 3, "H": 50,  "d": 16, "L": 100},
                {"sku": "CLUS2020", "D": 20, "T": 3, "H": 55,  "d": 20, "L": 100},
            ],
            "tools_long": [  # A412L 長刃型
                {"sku": "CLUSL0404",  "D": 4,  "T": 3, "H": 16, "d": 4,  "L": 75},
                {"sku": "CLUSL0404S", "D": 4,  "T": 3, "H": 20, "d": 4,  "L": 75},
                {"sku": "CLUSL0506",  "D": 5,  "T": 3, "H": 20, "d": 6,  "L": 75},
                {"sku": "CLUSL0506S", "D": 5,  "T": 3, "H": 25, "d": 6,  "L": 75},
                {"sku": "CLUSL0606",  "D": 6,  "T": 3, "H": 24, "d": 6,  "L": 75},
                {"sku": "CLUSL0606S", "D": 6,  "T": 3, "H": 30, "d": 6,  "L": 75},
                {"sku": "CLUSL0808",  "D": 8,  "T": 3, "H": 32, "d": 8,  "L": 100},
                {"sku": "CLUSL0808S", "D": 8,  "T": 3, "H": 40, "d": 8,  "L": 100},
                {"sku": "CLUSL1010",  "D": 10, "T": 3, "H": 40, "d": 10, "L": 100},
                {"sku": "CLUSL1010S", "D": 10, "T": 3, "H": 50, "d": 10, "L": 100},
                {"sku": "CLUSL1212",  "D": 12, "T": 3, "H": 50, "d": 12, "L": 100},
                {"sku": "CLUSL1212S", "D": 12, "T": 3, "H": 55, "d": 12, "L": 100},
                {"sku": "CLUSL1616",  "D": 16, "T": 3, "H": 65, "d": 16, "L": 150},
                {"sku": "CLUSL1616S", "D": 16, "T": 3, "H": 80, "d": 16, "L": 150},
                {"sku": "CLUSL2020",  "D": 20, "T": 3, "H": 80, "d": 20, "L": 160},
                {"sku": "CLUSL2020S", "D": 20, "T": 3, "H": 100,"d": 20, "L": 160},
            ],
            "cutting_table": {
                "aluminum_alloy": {
                    "material_zh": "鋁合金",
                    "smart_ai_cam_materials": ["AL6061", "AL7075"],
                    "V_m_min_range": [200, 250],
                    "FZ_mm_tooth": {
                        "D1-D4":   [0.03, 0.08],
                        "D6-D10":  [0.05, 0.12],
                        "D12-D16": [0.05, 0.14],
                    },
                },
                "engineering_plastic": {
                    "material_zh": "工程塑膠 (POM/Nylon/PMMA)",
                    "smart_ai_cam_materials": ["Plastics"],
                    "V_m_min_range": [200, 250],
                    "FZ_mm_tooth": {
                        "D1-D4":   [0.05, 0.1],
                        "D6-D10":  [0.06, 0.2],
                        "D12-D16": [0.06, 0.2],
                    },
                },
            },
            # ★ 官網切削條件表 (Recommended Milling Conditions)
            # 來源: chliyang.com.tw ALUS 鏡面鋁用刀 (2026.05 用戶提供)
            # 標籤: 3 Flutes / UMG 塗層 / 螺旋角 40° / 刀具 HRC 40
            # 被切削材: 鋁合金 all the Aluminum type, HRC 20-30
            # 槽銑 (Slot, H ≤ 1D) 與側銑 (Side, Depth ≤ 2D & W = 0.2D) 官網兩表完全一致
            # → 這是「理想值」(廠商給的最大切削量), 散件「上機值」 = 此表 × 散件折扣
            "params_table_official": {
                "side": {
                    "aluminum_alloy": {
                        "material_zh": "鋁合金 HRC20-30",
                        "smart_ai_cam_materials": ["AL6061", "AL7075", "Brass", "Plastics"],
                        "source": "chliyang.com.tw ALUS Side Milling (Depth≤2D, W=0.2D)",
                        # (D, RPM, feed_mm_min)
                        "table": [
                            (3.0,  10500, 1200),
                            (4.0,   8000, 1100),
                            (5.0,   9500, 1700),
                            (6.0,   9500, 1700),
                            (8.0,   8000, 2300),
                            (10.0,  8000, 2800),
                            (12.0,  6600, 2400),
                            (16.0,  5000, 1800),
                            (20.0,  4000, 1400),
                        ],
                    },
                },
                "slot": {
                    "aluminum_alloy": {
                        "material_zh": "鋁合金 HRC20-30",
                        "smart_ai_cam_materials": ["AL6061", "AL7075", "Brass", "Plastics"],
                        "source": "chliyang.com.tw ALUS Slot Milling (H≤1D)",
                        # 跟 side 完全相同 (官網明確兩表數值一致)
                        "table": [
                            (3.0,  10500, 1200),
                            (4.0,   8000, 1100),
                            (5.0,   9500, 1700),
                            (6.0,   9500, 1700),
                            (8.0,   8000, 2300),
                            (10.0,  8000, 2800),
                            (12.0,  6600, 2400),
                            (16.0,  5000, 1800),
                            (20.0,  4000, 1400),
                        ],
                    },
                },
            },
        },

        # ============================================================
        # CFSL - 鎢鋼螺旋銑牙刀 (A804)  螺紋銑刀（旋轉式銑出螺紋）
        # ============================================================
        "CFSL": {
            "code": "A804",
            "name": "鎢鋼螺旋銑牙刀",
            "name_en": "CFSL Carbide Thread Mill",
            "operation_type": "thread_milling",  # 螺紋銑削 (非攻牙)
            "use_cases": ["銑牙"],
            "suitable_materials": ["P_steel", "M_stainless", "H_heat_treated",
                                   "N_non_ferrous", "S_titanium_nickel"],
            "suitable_materials_zh": ["P 鋼", "M 不鏽鋼", "H 熱處理",
                                      "N 非鐵金屬", "S 鈦鎳"],
            "features": [
                "可加工至底蓋（盲孔螺紋全深）",
                "可調整螺紋公差",
                "可加工特殊牙底",
                "可加工難切削材，減少使用攻牙油",
            ],
            "smart_ai_cam_match": {
                "category_zh": "(進階款 - 螺紋銑刀, 攻牙替代方案)",
                "category_key": "thread_mill",
                "note": "用於難切材螺紋 / 底盲孔 / 公差客製，比剛性攻牙更可控",
            },
            "tools": [
                # sku, 粗牙(COARSE), 細牙(FINE), pitch, D 外徑, H 刃長, T 刃數, d 柄徑, L 全長
                {"sku":"CFSL02405",  "thread_coarse":"M3x0.5",       "thread_fine":None,           "pitch":0.5,  "D":2.4,  "H":6,    "T":3, "d":4,  "L":50},
                {"sku":"CFSL031507", "thread_coarse":"M4x0.7",       "thread_fine":None,           "pitch":0.7,  "D":3.15, "H":8,    "T":3, "d":4,  "L":50},
                {"sku":"CFSL0605",   "thread_coarse":None,           "thread_fine":"M7.0x0.5",     "pitch":0.5,  "D":5.9,  "H":15,   "T":3, "d":6,  "L":60},
                {"sku":"CFSL036075", "thread_coarse":"M4.5x0.75",    "thread_fine":"M5.0x0.75",    "pitch":0.75, "D":3.6,  "H":10.1, "T":3, "d":6,  "L":60},
                {"sku":"CFSL06075",  "thread_coarse":None,           "thread_fine":"M8.0x0.75",    "pitch":0.75, "D":5.9,  "H":15,   "T":3, "d":6,  "L":60},
                {"sku":"CFSL08075",  "thread_coarse":None,           "thread_fine":"M10.0x0.75",   "pitch":0.75, "D":7.9,  "H":20,   "T":3, "d":8,  "L":60},
                {"sku":"CFSL0408",   "thread_coarse":None,           "thread_fine":"M5.0x0.8",     "pitch":0.8,  "D":3.9,  "H":10,   "T":3, "d":6,  "L":60},
                {"sku":"CFSL04810",  "thread_coarse":"M6.0x1.0",     "thread_fine":"M7.0x1.0",     "pitch":1.0,  "D":4.8,  "H":11.5, "T":3, "d":6,  "L":60},
                {"sku":"CFSL0810",   "thread_coarse":None,           "thread_fine":"M10.0x1.0",    "pitch":1.0,  "D":7.9,  "H":20,   "T":3, "d":8,  "L":60},
                {"sku":"CFSL1010",   "thread_coarse":None,           "thread_fine":"M12.0x1.0",    "pitch":1.0,  "D":9.9,  "H":25,   "T":4, "d":10, "L":75},
                {"sku":"CFSL06125",  "thread_coarse":"M8.0x1.25",    "thread_fine":"M9.0x1.25",    "pitch":1.25, "D":5.9,  "H":15,   "T":3, "d":6,  "L":60},
                {"sku":"CFSL0815",   "thread_coarse":"M10.0x1.5",    "thread_fine":"M11.0x1.5",    "pitch":1.5,  "D":7.9,  "H":20,   "T":3, "d":8,  "L":60},
                {"sku":"CFSL1015",   "thread_coarse":None,           "thread_fine":"M13.0x1.5",    "pitch":1.5,  "D":9.9,  "H":25,   "T":4, "d":10, "L":75},
                {"sku":"CFSL1215",   "thread_coarse":None,           "thread_fine":"M15.0x1.5",    "pitch":1.5,  "D":11.9, "H":25,   "T":4, "d":12, "L":75},
                {"sku":"CFSL1615",   "thread_coarse":None,           "thread_fine":"M20.0x1.5",    "pitch":1.5,  "D":15.9, "H":40,   "T":4, "d":16, "L":100},
                {"sku":"CFSL10175",  "thread_coarse":"M12.0x1.75",   "thread_fine":None,           "pitch":1.75, "D":9.9,  "H":25,   "T":4, "d":10, "L":75},
                {"sku":"CFSL1020",   "thread_coarse":None,           "thread_fine":"M14.0x2.0",    "pitch":2.0,  "D":9.9,  "H":25,   "T":4, "d":10, "L":75},
                {"sku":"CFSL1220",   "thread_coarse":None,           "thread_fine":"M16.0x2.0",    "pitch":2.0,  "D":11.9, "H":25,   "T":4, "d":12, "L":75},
                {"sku":"CFSL1620",   "thread_coarse":None,           "thread_fine":"M20.0x2.0",    "pitch":2.0,  "D":15.9, "H":40,   "T":4, "d":16, "L":100},
                {"sku":"CFSL1625",   "thread_coarse":None,           "thread_fine":"M20.0x2.5",    "pitch":2.5,  "D":15.9, "H":40,   "T":4, "d":16, "L":100},
                {"sku":"CFSL1630",   "thread_coarse":"M24.0x3.0",    "thread_fine":"M27.0x3.0",    "pitch":3.0,  "D":15.9, "H":40,   "T":4, "d":16, "L":100},
                {"sku":"CFSL2030",   "thread_coarse":None,           "thread_fine":"M27.0x3.0",    "pitch":3.0,  "D":19.9, "H":50,   "T":4, "d":20, "L":100},
            ],
            "cutting_table": {
                "non_ferrous": {
                    "material_zh": "非鐵金屬",
                    "smart_ai_cam_materials": ["AL6061", "AL7075", "Brass", "Plastics"],
                    "V_m_min_range": [120, 220],
                    "FZ_mm_tooth": {"ALL": [0.08, 0.15]},
                },
                "carbon_steel": {
                    "material_zh": "一般碳鋼",
                    "smart_ai_cam_materials": ["S45C", "S50C"],
                    "V_m_min_range": [40, 180],
                    "FZ_mm_tooth": {"ALL": [0.02, 0.12]},
                },
                "pre_hardened_steel": {
                    "material_zh": "調質鋼",
                    "smart_ai_cam_materials": ["NAK80"],
                    "V_m_min_range": [40, 80],
                    "FZ_mm_tooth": {"ALL": [0.02, 0.08]},
                },
                "stainless_steel": {
                    "material_zh": "不鏽鋼",
                    "smart_ai_cam_materials": ["SUS304", "SUS316"],
                    "V_m_min_range": [50, 110],
                    "FZ_mm_tooth": {"ALL": [0.02, 0.05]},
                },
            },
        },

        # ============================================================
        # CH01M - TOPMS 含鈷螺旋絲攻 (攻牙刀, 德國棒材含鈷)
        # ============================================================
        "CH01M": {
            "code": "CH01M",
            "vendor": "TOPMS",
            "name": "含鈷螺旋絲攻",
            "name_en": "TOPMS Cobalt Spiral Tap",
            "operation_type": "tapping",
            "use_cases": ["攻牙"],
            "suitable_materials": ["P_steel", "M_stainless", "K_cast_iron",
                                   "H_heat_treated", "N_non_ferrous"],
            "suitable_materials_zh": ["P 鋼", "M 不鏽鋼", "K 鑄鐵",
                                      "H 熱處理", "N 非鐵金屬"],
            "features": [
                "含鈷材質硬度增加 (HSS-Co)",
                "德國棒材",
                "螺旋槽設計，排屑佳適合盲孔",
            ],
            "smart_ai_cam_match": {
                "category_zh": "(攻牙刀 - 直接套 Smart_AI_CAM 的 tap 系列)",
                "category_key": "tap",
                "note": "剛性攻牙 F = S × pitch 同步進給 (M29)",
            },
            "tools": [
                # sku, 牙距 P (規格), 精度, 柄徑 D, 四角頭 K, 牙長 H, 全長 L, 售價
                {"sku":"CH01M-0204-T",   "thread":"M2x0.4",     "pitch":0.4,  "tolerance":"OH2", "D":3,    "K":2.5,  "H":4.5,  "L":40,  "price":590},
                {"sku":"CH01M-0305-T",   "thread":"M2.5x0.45",  "pitch":0.45, "tolerance":"OH2", "D":3,    "K":2.5,  "H":5,    "L":44,  "price":535},
                {"sku":"CH01M-0407-T",   "thread":"M2.6x0.45",  "pitch":0.45, "tolerance":"OH2", "D":3,    "K":2.5,  "H":5,    "L":44,  "price":468},
                {"sku":"CH01M-0508-T",   "thread":"M3x0.5",     "pitch":0.5,  "tolerance":"OH2", "D":4,    "K":3.2,  "H":6,    "L":46,  "price":377},
                {"sku":"CH01M-0610-T",   "thread":"M3.5x0.6",   "pitch":0.6,  "tolerance":"OH2", "D":4,    "K":3.2,  "H":7,    "L":48,  "price":410},
                {"sku":"CH01M-0810-T",   "thread":"M4x0.7",     "pitch":0.7,  "tolerance":"OH2", "D":5,    "K":4,    "H":7.5,  "L":52,  "price":365},
                {"sku":"CH01M-08125-T",  "thread":"M5x0.8",     "pitch":0.8,  "tolerance":"OH2", "D":5.5,  "K":4.5,  "H":8.5,  "L":60,  "price":375},
                {"sku":"CH01M-1010-T",   "thread":"M6x1.0",     "pitch":1.0,  "tolerance":"OH2", "D":6,    "K":4.5,  "H":11,   "L":62,  "price":400},
                {"sku":"CH01M-1015-T",   "thread":"M6x1.0",     "pitch":1.0,  "tolerance":"OH2", "D":6.2,  "K":5,    "H":11,   "L":70,  "price":630},
                {"sku":"CH01M-10125-T",  "thread":"M8x1.25",    "pitch":1.25, "tolerance":"OH2", "D":6.2,  "K":5,    "H":14,   "L":70,  "price":540},
                {"sku":"CH01M-1210-T",   "thread":"M10x1.0",    "pitch":1.0,  "tolerance":"OH2", "D":7,    "K":5.5,  "H":11,   "L":70,  "price":823},
                {"sku":"CH01M-1215-T",   "thread":"M10x1.5",    "pitch":1.5,  "tolerance":"OH2", "D":7,    "K":5.5,  "H":14,   "L":75,  "price":705},
                {"sku":"CH01M-12175-T",  "thread":"M12x1.75",   "pitch":1.75, "tolerance":"OH3", "D":8.5,  "K":6.5,  "H":16,   "L":80,  "price":1060},
                {"sku":"CH01M-1415-T",   "thread":"M14x1.5",    "pitch":1.5,  "tolerance":"OH3", "D":8.5,  "K":6.5,  "H":11,   "L":70,  "price":950},
                {"sku":"CH01M-1420-T",   "thread":"M14x2.0",    "pitch":2.0,  "tolerance":"OH3", "D":8.5,  "K":6.5,  "H":18.5, "L":82,  "price":950},
                {"sku":"CH01M-1615-T",   "thread":"M16x1.5",    "pitch":1.5,  "tolerance":"OH3", "D":10.5, "K":8,    "H":15,   "L":88,  "price":1230},
                {"sku":"CH01M-1620-T",   "thread":"M16x2.0",    "pitch":2.0,  "tolerance":"OH3", "D":10.5, "K":8,    "H":20,   "L":88,  "price":1230},
                {"sku":"CH01M-1825-T",   "thread":"M18x2.5",    "pitch":2.5,  "tolerance":"OH3", "D":12.5, "K":10,   "H":15,   "L":95,  "price":1460},
                {"sku":"CH01M-25045-T",  "thread":"M20x2.5",    "pitch":2.5,  "tolerance":"OH3", "D":12.5, "K":10,   "H":20,   "L":95,  "price":1460},
                {"sku":"CH01M-2025-T",   "thread":"M20x2.5",    "pitch":2.5,  "tolerance":"OH3", "D":14,   "K":11,   "H":18,   "L":100, "price":1900},
                {"sku":"CH01M-2430-T",   "thread":"M24x3.0",    "pitch":3.0,  "tolerance":"OH3", "D":15,   "K":12,   "H":25,   "L":105, "price":2460},
                {"sku":"CH01M-3506-T",   "thread":"M24x3.0",    "pitch":3.0,  "tolerance":"OH4", "D":19,   "K":15,   "H":30,   "L":120, "price":4060},
            ],
            # 攻牙切削速度 (公式: F = S × pitch, 不是 FZ × Z)
            "cutting_table": {
                "non_ferrous": {
                    "material_zh": "非鐵金屬",
                    "smart_ai_cam_materials": ["AL6061", "AL7075", "Brass", "Plastics"],
                    "V_m_min_range": [15, 18],
                    "tap_formula": "F = S × pitch",  # 同步進給
                },
                "carbon_steel": {
                    "material_zh": "一般碳鋼",
                    "smart_ai_cam_materials": ["S45C", "S50C"],
                    "V_m_min_range": [5, 8],
                    "tap_formula": "F = S × pitch",
                },
                "pre_hardened_steel": {
                    "material_zh": "調質鋼",
                    "smart_ai_cam_materials": ["NAK80"],
                    "V_m_min_range": [4, 6],
                    "tap_formula": "F = S × pitch",
                },
                "stainless_steel": {
                    "material_zh": "不鏽鋼",
                    "smart_ai_cam_materials": ["SUS304", "SUS316"],
                    "V_m_min_range": [2, 5],
                    "tap_formula": "F = S × pitch",
                },
            },
        },

        # ============================================================
        # SG - OSG SG 高速鋼鑽頭 (鑽孔)
        # 資料來源: 用戶提供 CSV (75折轉速 + 6折進給)
        # 數據格式: 查表 + 直徑線性插值, 不是 V × FZ × Z 公式
        # ============================================================
        "SG": {
            "code": "SG",
            "vendor": "OSG",
            "name": "SG 高速鋼鑽頭",
            "name_en": "OSG SG Drill",
            "operation_type": "drilling",  # 鑽孔
            "use_cases": ["鑽孔", "鑽中心孔"],
            "suitable_materials": ["P_steel", "N_non_ferrous"],
            "suitable_materials_zh": ["P 鋼", "N 非鐵金屬 (鋁)"],
            "features": [
                "OSG SG 系列高速鋼鑽頭",
                "資料為 75 折轉速 + 6 折進給 (廠商安全係數)",
                "100% 轉速 = 表中 / 0.75, 100% 進給 = 表中 / 0.6",
            ],
            "smart_ai_cam_match": {
                "category_zh": "(鑽頭 - 走 Smart_AI_CAM 的 drill 系列)",
                "category_key": "drill",
                "note": "查表插值, 不走 V × FZ × Z 公式",
            },
            "data_format": "lookup_table",
            "safety_factors": {
                "rpm_factor": 0.75,
                "feed_factor": 0.60,
                "comment": "表中已套 75 折/6 折; 100% 值 = 表值 / factor",
            },
            # 直徑 D (mm), 每個材質給 [rpm_75_percent, feed_60_percent]
            "params_table": {
                "S50C": [
                    # (D_mm, rpm, feed_mm_min)
                    (1.0,  7125, 150),
                    (1.2,  5938, 147),
                    (1.3,  5481, 146),
                    (1.5,  4750, 144),
                    (1.6,  4453, 143),
                    (1.8,  3958, 141),
                    (2.0,  4275, 180),
                    (2.6,  3289, 186),
                    (2.8,  3053, 204),
                    (3.4,  2515, 216),
                    (4.2,  2036, 216),
                    (4.3,  1988, 216),
                    (4.5,  1900, 216),
                    (4.8,  1781, 216),
                    (5.8,  1470, 204),
                    (6.8,  1252, 195),
                    (7.8,  1095, 186),
                    (9.8,   870, 168),
                    (10.8,  788, 165),
                    (11.8,  724, 156),
                ],
                "AL6061": [
                    (1.0, 11250, 300),
                    (1.2,  9375, 294),
                    (1.3,  8654, 291),
                    (1.5,  7500, 288),
                    (1.6,  7031, 285),
                    (1.8,  6250, 282),
                    (2.0,  7275, 378),
                    (2.6,  5595, 468),
                    (2.8,  5198, 480),
                    (3.4,  4275, 489),
                    (4.2,  3465, 477),
                    (4.3,  3382, 474),
                    (4.5,  3232, 468),
                    (4.8,  3030, 462),
                    (5.8,  2505, 441),
                    (6.8,  2138, 423),
                    (7.8,  1868, 408),
                    (9.8,  1485, 369),
                    (10.8, 1350, 360),
                    (11.8, 1230, 348),
                ],
            },
        },
    },
}


# ============================================================
# (操作 × 材質) → 系列推薦對照
# Smart_AI_CAM 材質 + 操作型 → 最佳系列 (priority list)
# operation 可選: milling (預設) / drilling / tapping / thread_milling
# ============================================================

MATERIAL_TO_SERIES_BY_OP: Dict[str, Dict[str, List[str]]] = {
    "milling": {
        "AL6061":    ["CLUS"],
        "AL7075":    ["CLUS"],
        "Brass":     ["CLUS"],         # 非鐵金屬類
        "Plastics":  ["CLUS"],
        "S50C":      ["CIB"],
        "S45C":      ["CIB"],
        "NAK80":     ["CIB"],          # 預質鋼
        "SUS304":    ["CAVN"],
        "SUS316":    ["CAVN"],
        "Ti-6Al-4V": ["CAVN"],
        "SKD11":     ["CAVN"],         # 熱處理
        "SKD61":     ["CAVN"],
        "Cast_Iron": ["CIB"],
    },
    "drilling": {
        # OSG SG 鑽頭目前只覆蓋 S50C 跟 AL6061 兩種材質
        "S50C":   ["SG"],
        "S45C":   ["SG"],              # 用 S50C 表近似
        "AL6061": ["SG"],
        "AL7075": ["SG"],              # 用 AL6061 表近似
    },
    "tapping": {
        # TOPMS CH01M 攻牙刀 (含鈷, M2-M24, 全材質)
        "AL6061":   ["CH01M"],
        "AL7075":   ["CH01M"],
        "Brass":    ["CH01M"],
        "Plastics": ["CH01M"],
        "S50C":     ["CH01M"],
        "S45C":     ["CH01M"],
        "NAK80":    ["CH01M"],
        "SUS304":   ["CH01M"],
        "SUS316":   ["CH01M"],
        "Cast_Iron":["CH01M"],
    },
    "thread_milling": {
        # 奇力揚 CFSL 螺紋銑刀 (A804, 全材質)
        "AL6061":    ["CFSL"],
        "AL7075":    ["CFSL"],
        "Brass":     ["CFSL"],
        "Plastics":  ["CFSL"],
        "S50C":      ["CFSL"],
        "S45C":      ["CFSL"],
        "NAK80":     ["CFSL"],
        "SUS304":    ["CFSL"],
        "SUS316":    ["CFSL"],
        "Ti-6Al-4V": ["CFSL"],
    },
}

# 向後相容: 舊版單層字典 (= milling 子表)
MATERIAL_TO_SERIES: Dict[str, List[str]] = MATERIAL_TO_SERIES_BY_OP["milling"]


# ============================================================
# Query helpers
# ============================================================

def _dia_bucket(D: float) -> str:
    """把刀徑映射到目錄表格的 FZ 區間欄位。"""
    if D <= 4:
        return "D1-D4"
    elif D <= 10:
        return "D6-D10"
    elif D <= 16:
        return "D12-D16"
    else:
        return "D12-D16"  # 超過 16 也用最大區間 (保守)


def _find_material_row(series_data: Dict[str, Any],
                       smart_ai_cam_material: str) -> Optional[Dict[str, Any]]:
    """從某系列的 cutting_table 找到對應 Smart_AI_CAM 材質的條件列。"""
    table = series_data.get("cutting_table", {})
    for key, row in table.items():
        if smart_ai_cam_material in (row.get("smart_ai_cam_materials") or []):
            return {**row, "_row_key": key}
    return None


def list_series() -> Dict[str, Any]:
    """總覽 - 三個系列簡介 + 適用材質。"""
    out = {
        "vendor": CATALOG["vendor"],
        "year": CATALOG["year"],
        "formulas": CATALOG["formulas"],
        "series": [],
    }
    for key, s in CATALOG["series"].items():
        tools_count = (len(s.get("tools") or [])
                       + len(s.get("tools_standard") or [])
                       + len(s.get("tools_long") or []))
        # SG 鑽頭沒 tools 列表, 算 params_table 條目數
        if not tools_count and s.get("params_table"):
            tools_count = sum(len(rows) for rows in s["params_table"].values())
        out["series"].append({
            "key": key,
            "code": s["code"],
            "vendor": s.get("vendor", CATALOG["vendor"]),
            "operation_type": s.get("operation_type", "milling"),
            "name": s["name"],
            "name_en": s["name_en"],
            "suitable_materials_zh": s["suitable_materials_zh"],
            "use_cases": s["use_cases"],
            "flutes_default": s.get("flutes_default"),
            "tools_count": tools_count,
            "smart_ai_cam_match": s["smart_ai_cam_match"],
        })
    return out


def get_series(series: str) -> Optional[Dict[str, Any]]:
    """取得單一系列完整資料。"""
    return CATALOG["series"].get(series.upper())


def list_tools(series: str,
               diameter_mm: Optional[float] = None,
               tolerance: float = 0.5) -> Dict[str, Any]:
    """列舉某系列的刀具，可選依直徑過濾。"""
    s = get_series(series)
    if not s:
        return {"error": f"未知系列 {series}", "available": list(CATALOG["series"].keys())}

    all_tools: List[Dict[str, Any]] = []
    if s.get("tools"):
        all_tools.extend([{**t, "_variant": "標準型"} for t in s["tools"]])
    if s.get("tools_standard"):
        all_tools.extend([{**t, "_variant": "標準型"} for t in s["tools_standard"]])
    if s.get("tools_long"):
        all_tools.extend([{**t, "_variant": "長刃型"} for t in s["tools_long"]])

    if diameter_mm is not None:
        all_tools = [t for t in all_tools
                     if abs(float(t["D"]) - float(diameter_mm)) <= tolerance]

    return {
        "series": series,
        "name": s["name"],
        "count": len(all_tools),
        "tools": all_tools,
    }


def _interp_table(table: List[tuple], D: float) -> tuple:
    """線性插值: 給定 (D, rpm, feed) 表 + 目標 D, 回傳 (rpm, feed)。

    - D 小於最小: 用最小; D 大於最大: 用最大 (clamp, 不外推)
    - D 落在表中相鄰兩點之間: 線性插值
    """
    if not table:
        return (None, None)
    sorted_t = sorted(table, key=lambda r: r[0])
    if D <= sorted_t[0][0]:
        return (float(sorted_t[0][1]), float(sorted_t[0][2]))
    if D >= sorted_t[-1][0]:
        return (float(sorted_t[-1][1]), float(sorted_t[-1][2]))
    for i in range(len(sorted_t) - 1):
        d_lo, r_lo, f_lo = sorted_t[i]
        d_hi, r_hi, f_hi = sorted_t[i + 1]
        if d_lo <= D <= d_hi:
            if d_hi == d_lo:
                return (float(r_lo), float(f_lo))
            t = (D - d_lo) / (d_hi - d_lo)
            return (r_lo + t * (r_hi - r_lo), f_lo + t * (f_hi - f_lo))
    return (None, None)


def _recommend_drilling(material: str, tool_dia: float,
                        s: Dict[str, Any], series: str,
                        use_max: bool) -> Dict[str, Any]:
    """鑽頭查表型 (OSG SG): 直接從 params_table 線性插值。"""
    tbl = (s.get("params_table") or {}).get(material)
    if not tbl:
        return {
            "success": False,
            "error": f"系列 '{series}' 未收錄材質 '{material}' 的鑽孔參數表",
            "series_supports": list((s.get("params_table") or {}).keys()),
        }
    rpm_75, feed_60 = _interp_table(tbl, float(tool_dia))
    if rpm_75 is None:
        return {"success": False, "error": f"插值失敗 D={tool_dia}"}

    sf = s.get("safety_factors") or {}
    rpm_factor = float(sf.get("rpm_factor", 0.75))
    feed_factor = float(sf.get("feed_factor", 0.60))
    rpm_100 = rpm_75 / rpm_factor if rpm_factor else rpm_75
    feed_100 = feed_60 / feed_factor if feed_factor else feed_60

    if use_max:
        rpm, feed = rpm_100, feed_100
        pick = "max (100% 廠商上限值)"
    else:
        rpm, feed = rpm_75, feed_60
        pick = f"safe ({int(rpm_factor*100)}折轉速 / {int(feed_factor*100)}折進給)"

    rpm = max(500, min(18000, round(rpm)))
    feed = max(50, min(6000, round(feed)))

    # 反推 Vc / fr 給用戶參考
    import math
    Vc = math.pi * float(tool_dia) * rpm / 1000.0
    fr = feed / rpm if rpm else 0.0

    return {
        "success": True,
        "data": {
            "vendor": s.get("vendor", CATALOG["vendor"]),
            "series": series,
            "series_name": s["name"],
            "series_code": s["code"],
            "operation": "drilling",
            "material": material,
            "tool_dia_mm": float(tool_dia),
            "teeth": None,
            "rpm": rpm,
            "feed_mm_min": feed,
            "Vc_m_min": round(Vc, 1),
            "fr_mm_rev": round(fr, 4),
            "formula_used": "查表插值 (OSG SG 廠商實機數據)",
            "smart_ai_cam_tool_category": s["smart_ai_cam_match"]["category_zh"],
            "pick_strategy": pick,
            "safety_factors": sf,
            "note": (f"OSG SG 系列 D={tool_dia}mm 在 {material} 的"
                     f"{'積極' if use_max else '保守'}值: "
                     f"RPM={rpm}, F={feed} mm/min "
                     f"(等效 Vc={Vc:.1f} m/min, fr={fr:.3f} mm/rev)"),
        },
    }


def _recommend_tapping(material: str, tool_dia: float,
                       s: Dict[str, Any], series: str,
                       pitch: Optional[float],
                       use_max: bool) -> Dict[str, Any]:
    """攻牙型 (TOPMS CH01M): F = S × pitch 同步進給。

    tool_dia 在攻牙語境是「螺紋外徑」(e.g. M6 → D=6)。
    pitch 必須給定 (e.g. M6x1.0 → pitch=1.0)。
    若 pitch 未給, 嘗試從 tools 表中找最接近 D 的標準 pitch。
    """
    if pitch is None:
        # 從刀具表找最接近這個 D 的 pitch
        candidates = [t for t in (s.get("tools") or []) if abs(float(t["D"]) - float(tool_dia)) < 0.5]
        if candidates:
            pitch = float(candidates[0]["pitch"])
        else:
            # 沒給也找不到, 用 ISO 粗牙慣例估
            DEFAULT_PITCH = {3:0.5, 4:0.7, 5:0.8, 6:1.0, 8:1.25, 10:1.5,
                            12:1.75, 14:2.0, 16:2.0, 18:2.5, 20:2.5, 24:3.0}
            pitch = DEFAULT_PITCH.get(int(round(tool_dia)), 1.0)

    row = _find_material_row(s, material)
    if not row:
        return {
            "success": False,
            "error": f"系列 '{series}' 未收錄材質 '{material}' 的攻牙條件",
            "series_supports": s.get("suitable_materials_zh"),
        }

    v_range = row["V_m_min_range"]
    V = float(v_range[1]) if use_max else (v_range[0] + v_range[1]) / 2.0

    rpm = V * 318.3 / float(tool_dia)
    feed = rpm * float(pitch)  # 攻牙剛性同步: F = S × P

    rpm = max(50, min(8000, round(rpm)))   # 攻牙轉速不會太高
    feed = max(20, min(8000, round(feed)))

    return {
        "success": True,
        "data": {
            "vendor": s.get("vendor", CATALOG["vendor"]),
            "series": series,
            "series_name": s["name"],
            "series_code": s["code"],
            "operation": "tapping",
            "material": material,
            "material_match_row": row["_row_key"],
            "material_match_zh": row["material_zh"],
            "tool_dia_mm": float(tool_dia),
            "pitch_mm": float(pitch),
            "teeth": None,
            "V_m_min": round(V, 1),
            "V_range": v_range,
            "rpm": rpm,
            "feed_mm_min": feed,
            "formula_used": "S = V × 318.3 / D,  F = S × pitch (剛性同步)",
            "smart_ai_cam_tool_category": s["smart_ai_cam_match"]["category_zh"],
            "pick_strategy": "max" if use_max else "median",
            "note": (f"{s.get('vendor', '')} {series} 攻牙 M{tool_dia:g}x{pitch} "
                     f"在 {row['material_zh']}: V={V:.0f} m/min, "
                     f"RPM={rpm}, F={feed} mm/min (剛性同步進給)"),
        },
    }


def recommend_cutting(material: str,
                      tool_dia: float,
                      teeth: Optional[int] = None,
                      series: Optional[str] = None,
                      use_max: bool = False,  # 向後相容: True 等同 mode='aggressive'
                      operation: str = "milling",
                      pitch: Optional[float] = None,
                      mode: str = "conservative",
                      rpm_factor: Optional[float] = None,
                      feed_factor: Optional[float] = None,
                      holder: str = "ER") -> Dict[str, Any]:
    """★ 核心函式：給操作+材質+刀徑 → 計算廠商建議切削參數。

    Args:
        material:    Smart_AI_CAM 材質鍵 (AL6061/S50C/SUS304/NAK80/Ti-6Al-4V...)
        tool_dia:    刀徑 mm (攻牙時=螺紋外徑)
        teeth:       刃數 (預設用系列預設值, CIB=4, CAVN=4, CLUS=3)
        series:      指定系列，預設依 operation+material 自動選
        operation:   milling (預設) / drilling / tapping / thread_milling
        pitch:       攻牙/銑牙時用的螺距 (mm), 若未給會自動推測
        mode:        "conservative" (預設, 散件求穩) / "aggressive" (量產求快)
        rpm_factor:  轉速折扣 (覆蓋 mode 預設, conservative=0.75 / aggressive=1.0)
        feed_factor: 進給折扣 (覆蓋 mode 預設, conservative=0.50 / aggressive=1.0)
        holder:      刀把類型 "ER"(預設,軟上限 8000) / "SK"(24000) / "pullback"(無上限)
        use_max:     [遺留] True 等同 mode='aggressive', False 等同 mode='conservative'

    Returns:
        {success, data: {rpm, feed_mm_min, vendor, series, mode, holder, ...}}

    散件預設策略 (用戶實機驗證):
        base    = 廠商上限值 (V_max, FZ_max)
        Vc      = V_max × rpm_factor   (轉速 75 折)
        FZ      = FZ_max × feed_factor (進給 5 折)
        rpm_calc = Vc × 318.3 / D
        若 rpm_calc > holder.rpm_soft_max (ER=8000) 且 mode=conservative:
            rpm  = holder.rpm_soft_max
            feed 等比例縮 (scale = holder_max / rpm_calc)
    """
    operation = (operation or "milling").lower()

    # ── 向後相容: use_max=True 自動切到 aggressive 模式 ──
    if use_max and mode == "conservative":
        mode = "aggressive"
    mode = mode.lower() if mode else "conservative"

    # ── 套用 mode 預設的折扣 ──
    if rpm_factor is None:
        rpm_factor = 0.75 if mode == "conservative" else 1.00
    if feed_factor is None:
        feed_factor = 0.50 if mode == "conservative" else 1.00

    # 1. 自動選系列 (按 operation + material)
    if not series:
        op_map = MATERIAL_TO_SERIES_BY_OP.get(operation, {})
        candidates = op_map.get(material, [])
        if not candidates:
            return {
                "success": False,
                "error": (f"操作 '{operation}' + 材質 '{material}' "
                          f"沒有對應的廠商系列"),
                "available_materials_for_op": sorted(op_map.keys()),
                "valid_operations": list(MATERIAL_TO_SERIES_BY_OP.keys()),
            }
        series = candidates[0]

    series = series.upper()
    s = get_series(series)
    if not s:
        return {
            "success": False,
            "error": f"未知系列 '{series}'",
            "available_series": list(CATALOG["series"].keys()),
        }

    # 2. 按 series 的 operation_type 分流
    op_type = s.get("operation_type", "milling")

    if op_type == "drilling":
        return _recommend_drilling(material, float(tool_dia), s, series, use_max)

    if op_type == "tapping":
        return _recommend_tapping(material, float(tool_dia), s, series,
                                  pitch, use_max)

    # ----- 銑削 (含螺紋銑) 走原本 V × FZ × Z 公式 -----
    row = _find_material_row(s, material)
    if not row:
        return {
            "success": False,
            "error": f"系列 '{series}' 未收錄材質 '{material}' 的切削條件",
            "series_supports": s.get("suitable_materials_zh"),
        }

    bucket = _dia_bucket(float(tool_dia))
    fz_range_map = row["FZ_mm_tooth"]
    # CFSL 螺紋銑刀用 "ALL" 區間 (不分直徑)
    fz_range = fz_range_map.get(bucket) or fz_range_map.get("ALL")
    v_range = row["V_m_min_range"]

    if not fz_range:
        return {
            "success": False,
            "error": f"刀徑 {tool_dia}mm ({bucket}) 不在此系列建議範圍",
        }

    # ★ 散件公式: base = 廠商上限值, 再套折扣
    V_max = float(v_range[1])
    FZ_max = float(fz_range[1])
    V = V_max * float(rpm_factor)
    FZ = FZ_max * float(feed_factor)

    # 螺紋銑刀的 flutes_default 沒設, 用刀具表 T 欄
    if op_type == "thread_milling" and not teeth:
        cand = [t for t in (s.get("tools") or [])
                if abs(float(t["D"]) - float(tool_dia)) < 0.5]
        Z = int(cand[0]["T"]) if cand else 3
    else:
        Z = int(teeth or s.get("flutes_default", 4))

    rpm_calc = V * 318.3 / float(tool_dia)
    feed_calc = rpm_calc * FZ * Z

    # ★ 套 Holder 軟上限 (僅 conservative 模式)
    try:
        from . import tool_holders as _th
    except ImportError:
        from smart_ai_cam_mcp import tool_holders as _th
    holder_info = _th.get_holder(holder)
    rpm_soft_max = holder_info.get("rpm_soft_max")
    rpm_clamped = False
    scale_used = 1.0

    if mode == "conservative" and rpm_soft_max is not None and rpm_calc > rpm_soft_max:
        scale_used = rpm_soft_max / rpm_calc
        rpm = float(rpm_soft_max)
        feed = feed_calc * scale_used
        rpm_clamped = True
    else:
        rpm = rpm_calc
        feed = feed_calc

    rpm = max(500, min(24000, round(rpm)))
    feed = max(50, min(8000, round(feed)))

    return {
        "success": True,
        "data": {
            "vendor": s.get("vendor", CATALOG["vendor"]),
            "series": series,
            "series_name": s["name"],
            "series_code": s["code"],
            "operation": op_type,
            "material": material,
            "material_match_row": row["_row_key"],
            "material_match_zh": row["material_zh"],
            "tool_dia_mm": float(tool_dia),
            "teeth": Z,
            "V_m_min": round(V, 1),
            "V_max_vendor": V_max,
            "FZ_mm_tooth": round(FZ, 4),
            "FZ_max_vendor": FZ_max,
            "V_range": v_range,
            "FZ_range_at_this_diameter": fz_range,
            "rpm": rpm,
            "feed_mm_min": feed,
            "rpm_before_holder_clamp": round(rpm_calc),
            "feed_before_holder_clamp": round(feed_calc),
            "ae_min_mm": round(float(tool_dia) * 0.25, 2),
            "ae_max_mm": round(float(tool_dia) * 0.75, 2),
            "formula_used": (f"V = V_max({V_max}) × rpm_factor({rpm_factor}), "
                             f"FZ = FZ_max({FZ_max}) × feed_factor({feed_factor}); "
                             f"rpm = V × 318.3 / D; feed = rpm × FZ × Z"),
            "smart_ai_cam_tool_category": s["smart_ai_cam_match"]["category_zh"],
            # ── 散件/量產 模式資訊 ──
            "mode": mode,
            "rpm_factor": rpm_factor,
            "feed_factor": feed_factor,
            # ── 刀把資訊 ──
            "holder": holder_info.get("name", holder),
            "holder_rpm_soft_max": rpm_soft_max,
            "rpm_holder_clamped": rpm_clamped,
            "holder_scale_factor": round(scale_used, 3) if rpm_clamped else 1.0,
            "note": (f"{s.get('vendor','奇力揚')} {series} 系列 {row['material_zh']} "
                     f"[{'散件 '+str(int(rpm_factor*100))+'/'+str(int(feed_factor*100))+'折' if mode=='conservative' else '量產上限'}, "
                     f"holder={holder_info.get('name', holder)}]"
                     + (f"; RPM 由 {round(rpm_calc)} 鉗制到 {int(rpm)} (holder 軟上限)" if rpm_clamped else "")),
        },
    }


# ============================================================
# MCP dispatch
# ============================================================

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point。

    params:
      {"mode": "list_series"}                    → 三系列總覽
      {"mode": "get_series", "series": "CLUS"}   → 單系列詳細
      {"mode": "list_tools", "series": "CIB", "diameter_mm": 6} → 列特定刀
      {"mode": "recommend", "material": "AL6061", "tool_dia": 6} → 推薦切削參數 (主要 API)
    """
    mode = (params.get("mode") or "recommend").lower()

    if mode == "list_series":
        return {"success": True, "data": list_series()}

    elif mode == "get_series":
        series = params.get("series")
        if not series:
            return {"success": False, "error": "get_series 模式需指定 series"}
        s = get_series(series)
        if not s:
            return {"success": False, "error": f"未知系列 {series}",
                    "available": list(CATALOG["series"].keys())}
        return {"success": True, "data": s}

    elif mode == "list_tools":
        series = params.get("series")
        if not series:
            return {"success": False, "error": "list_tools 模式需指定 series"}
        return {"success": True, "data": list_tools(
            series=series,
            diameter_mm=_to_float(params.get("diameter_mm")),
            tolerance=float(params.get("tolerance") or 0.5),
        )}

    elif mode == "recommend":
        material = params.get("material")
        tool_dia = _to_float(params.get("tool_dia"))
        if not material or tool_dia is None:
            return {"success": False,
                    "error": "recommend 模式需 material 與 tool_dia"}
        return recommend_cutting(
            material=material,
            tool_dia=tool_dia,
            teeth=_to_int(params.get("teeth")),
            series=params.get("series"),
            use_max=bool(params.get("use_max", False)),
            operation=params.get("operation") or "milling",
            pitch=_to_float(params.get("pitch")),
            mode=params.get("mode_strategy") or params.get("strategy") or "conservative",
            rpm_factor=_to_float(params.get("rpm_factor")),
            feed_factor=_to_float(params.get("feed_factor")),
            holder=params.get("holder") or "ER",
        )

    else:
        return {"success": False,
                "error": f"未知 mode: {mode}",
                "valid_modes": ["list_series", "get_series",
                                "list_tools", "recommend"]}


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
