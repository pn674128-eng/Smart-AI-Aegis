# -*- coding: utf-8 -*-
"""
Smart_AI 物理與切削力學引擎 — 廠內實體刀具與物理切削參數計算器
===========================================================
• 整合奇力揚 (Chliyang) 廠內刀具庫資料（ALUS 鏡面鋁用刀、CIB 無敵重切削銑刀、CAV 鈦合金銑刀）
• 基於切削速度 (Vc) 與每刃進給 (fz) 物理公式，動態計算最優 RPM (S) 與進給率 (F)
• 提供超載與功率安全檢驗模型
"""
from __future__ import annotations

import math
from typing import Dict, Any, Tuple

# ─────────────────────────────────────────────
# 1. 廠內實體刀具規格定義 (奇力揚系列)
# ─────────────────────────────────────────────
FACTORY_TOOLS = {
    "AL6061": {
        "series": "ALUS-鏡面鋁用刀",
        "code": "A412",
        "flutes": 3,
        "material_class": "N10 鋁件、銅件、非鐵金屬",
        "coating": "無塗層 (K05 高耐磨超微粒鎢鋼 + 刃口微鈍化月牙開法)",
        "optimal_vc": 350.0,       # 建議切削速度 Vc (m/min)
        "fz_base": 0.05,           # 基準每刃進給量 (mm/tooth for D=10)
    },
    "S50C": {
        "series": "CIB-無敵重切削銑刀",
        "code": "A419",
        "flutes": 4,
        "material_class": "P30 鋼件, K300 鑄鐵, HRC45以下鐵金屬 (中碳鋼、紅十字、SKD系列)",
        "coating": "高度耐磨抗崩塗層 (不等分割變導程重切削設計)",
        "optimal_vc": 113.0,       # 建議切削速度 Vc (m/min) (S3600 D10 對應 Vc=113)
        "fz_base": 0.03,           # 基準每刃進給量 (mm/tooth)
        "extreme_s": 4000,
        "extreme_f": 800,
        "max_ap": 10.0             # 最大軸向切深 (DP=10)
    },
    "TITANIUM": {
        "series": "CAV-鈦合金銑刀",
        "code": "A420",
        "flutes": 4,
        "material_class": "S 鈦、鎳合金, M 不鏽鋼",
        "coating": "G1 塗層 (低摩擦係數、變導程不等分割不黏屑設計)",
        "optimal_vc": 85.0,        # 建議切削速度 Vc (m/min) (範圍 69 - 110)
        "fz_base": 0.025,          # 基準每刃進給量 (mm/tooth)
    }
}

# ─────────────────────────────────────────────
# 2. 廠內 CNC 實體機台參數定義
# ─────────────────────────────────────────────
CNC_MACHINES = {
    "未指定機台 (常規 12,000 RPM)": {
        "max_rpm": 12000,
        "taper": "通用",
        "rigidity": "通用",
        "description": "常規彈性混搭加工模式，轉速上限限制為 12,000 RPM 以相容各型主軸。"
    },
    "Centra 14MiB BT30 (最高 24,000 RPM)": {
        "max_rpm": 24000,
        "taper": "BT30",
        "rigidity": "中低剛性",
        "description": "廠內高速 BT30 主軸機台，極致轉速可達 24,000 RPM，最適合鋁合金高效高速切削。"
    },
    "Centra 21MiB BT30 (最高 24,000 RPM)": {
        "max_rpm": 24000,
        "taper": "BT30",
        "rigidity": "中低剛性",
        "description": "廠內高速 BT30 主軸機台，轉速極限 24,000 RPM，適合精密非鐵金屬與鋁材高速切削。"
    },
    "Victor VCP76 BBT40 (最高 12,000 RPM)": {
        "max_rpm": 12000,
        "taper": "BBT40",
        "rigidity": "高剛性",
        "description": "台中精機高剛性雙面接觸 BBT40 主軸，轉速極限 12,000 RPM，提供優越切削扭力，為鐵金屬/鈦合金首選。"
    },
    "Mazak VARIAXIS i-600 BBT40 (最高 12,000 RPM)": {
        "max_rpm": 12000,
        "taper": "BBT40",
        "rigidity": "高剛性",
        "description": "馬扎克高性能高剛性雙面接觸 BBT40 主軸，極速 12,000 RPM，具有五軸剛性，為硬質鋼材/鈦合金重切削首選。"
    }
}

# ─────────────────────────────────────────────
# 3. 物理參數動態計算核心
# ─────────────────────────────────────────────
def calculate_optimal_params(
    material: str,
    tool_diameter_mm: float = 10.0,
    is_roughing: bool = True,
    machine_name: str = "未指定機台 (常規 12,000 RPM)"
) -> Dict[str, Any]:
    """
    依據工件材質、實體刀具外徑、以及選定的 CNC 機台規格，
    套用散單安全切削係數 (70% 負荷) 與主軸速限，動態計算 spindle speed (S) 與 feedrate (F)。
    
    物理公式：
      S (RPM) = (Vc * 1000) / (pi * D)
      F (mm/min) = S * Z * fz
    """
    mat_key = str(material).upper().strip()
    
    # 支援別名對齊
    if "AL" in mat_key:
        mat_ref = "AL6061"
    elif "S50C" in mat_key or "STEEL" in mat_key or "CARBON" in mat_key:
        mat_ref = "S50C"
    elif "TI" in mat_key or "TITAN" in mat_key or "COBALT" in mat_key:
        mat_ref = "TITANIUM"
    else:
        mat_ref = "S50C"  # 預設為中碳鋼保守安全模式

    tool_info = FACTORY_TOOLS.get(mat_ref)
    
    # 取得基礎規格
    flutes = tool_info["flutes"]
    vc = tool_info["optimal_vc"]
    fz = tool_info["fz_base"]
    
    # 依刀具外徑調整 fz 比例 (小徑刀具每刃進給需縮小防止斷刀)
    # 比例公式： fz_actual = fz_base * (D / 10.0)^0.8
    dia = max(0.5, float(tool_diameter_mm))
    fz_actual = fz * math.pow(dia / 10.0, 0.8)
    
    # 精加工微調
    if not is_roughing:
        vc *= 1.2
        fz_actual *= 0.7
    
    # ─────────────────────────────────────────────
    # 【核心修正】套用散單穩定首件加工安全折減係數：70% (0.7)
    # ─────────────────────────────────────────────
    SAFETY_FACTOR = 0.7
    vc_safe = vc * SAFETY_FACTOR
    fz_safe = fz_actual * SAFETY_FACTOR
    
    # 獲取選用機台規格 (預設為通用 12,000 RPM)
    m_name = str(machine_name).strip()
    if m_name not in CNC_MACHINES:
        # 模糊匹配
        matched = False
        for k in CNC_MACHINES.keys():
            if m_name in k or k in m_name:
                m_name = k
                matched = True
                break
        if not matched:
            m_name = "未指定機台 (常規 12,000 RPM)"
            
    machine_profile = CNC_MACHINES[m_name]
    max_rpm = machine_profile["max_rpm"]
    taper = machine_profile["taper"]
    rigidity_level = machine_profile["rigidity"]
    
    # 轉速計算 (RPM)
    rpm = (vc_safe * 1000.0) / (math.pi * dia)
    rpm = int(round(rpm))
    
    # 奇力揚 CIB 極限防禦限制：D10 對應 S4000/F800
    if mat_ref == "S50C" and "extreme_s" in tool_info:
        cib_max_rpm = int(tool_info["extreme_s"] * (10.0 / dia) * SAFETY_FACTOR)
        if rpm > cib_max_rpm:
            rpm = cib_max_rpm
            
    # 轉速鉗制 (Clamp)
    is_rpm_clamped = False
    original_rpm = rpm
    if rpm > max_rpm:
        rpm = max_rpm
        is_rpm_clamped = True
        
    # 限制轉速合理下限，防止極端小刀具導致轉速低於 100
    if rpm < 100:
        rpm = 100
        
    # 進給計算 (mm/min)
    # 配合被鉗制後的實際轉速計算進給率，以維持安全的每刃切削量 fz_safe
    feed = rpm * flutes * fz_safe
    
    # 奇力揚 CIB 極限防禦進給限制
    if mat_ref == "S50C" and "extreme_f" in tool_info:
        cib_max_feed = int(tool_info["extreme_f"] * (dia / 10.0) * SAFETY_FACTOR)
        if feed > cib_max_feed:
            feed = cib_max_feed
            
    feed = int(round(feed))
    if feed < 1:
        feed = 1
        
    # ─────────────────────────────────────────────
    # 【鋼性匹配適配度與安全警告】
    # ─────────────────────────────────────────────
    rigidity_match = True
    rigidity_warning = ""
    
    if mat_ref in ["S50C", "TITANIUM"]:
        if taper == "BT30":
            rigidity_match = False
            rigidity_warning = (
                f"【主軸剛性警告】加工 {mat_ref} 鋼件/難切削材需要極高剛性主軸與高扭力。當前選用 '{taper}' ({m_name}) "
                "主軸在重切削下極易產生劇烈震動、撓曲與刀具破損！強烈建議改用雙接觸面 BBT40 (如 Victor 或 Mazak) 高剛性機台進行加工。"
            )
            
    return {
        "material_ref": mat_ref,
        "tool_series": tool_info["series"],
        "tool_code": tool_info["code"],
        "flutes": flutes,
        "coating": tool_info["coating"],
        "materials_class": tool_info["material_class"],
        "diameter": dia,
        "optimal_vc": round(vc_safe, 1),
        "fz_actual": round(fz_safe, 4),
        "spindle_speed": rpm,
        "feedrate": feed,
        "original_spindle_speed": original_rpm,
        "is_rpm_clamped": is_rpm_clamped,
        "max_rpm_limit": max_rpm,
        "active_machine": m_name,
        "taper_type": taper,
        "rigidity_level": rigidity_level,
        "rigidity_match": rigidity_match,
        "rigidity_warning": rigidity_warning,
        "safety_factor": SAFETY_FACTOR,
        "ap_limit_mm": round(dia * 0.8 if mat_ref != "S50C" else min(10.0, dia * 1.0), 2)
    }

