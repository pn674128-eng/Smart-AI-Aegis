# -*- coding: utf-8 -*-
"""
智能 CAD 報價計算引擎（子插件物理與幾何計算端，不包含 LLM 商業決策）
所有商業利潤加成、談判策略與高階定價，由主插件 Smart AI Aegis 控制與覆蓋。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# 標準材質密度 g/cm³（物理客觀常數）
_DENSITY = {
    "AL6061": 2.70,
    "AL7075": 2.81,
    "S45C": 7.85,
    "S50C": 7.85,
    "SUS304": 7.93,
    "BRASS": 8.50,
}

# 標準材質基準價格 CNY/kg（此部分可由 Aegis 傳入參數覆蓋）
_MATERIAL_PRICE_PER_KG = {
    "AL6061": 28.0,
    "AL7075": 32.0,
    "S45C": 8.5,
    "S50C": 9.0,
    "SUS304": 22.0,
    "BRASS": 45.0,
}

# 基礎切削加工費率 CNY/分鐘
_MACHINING_RATE_PER_MIN = 3.5


def _norm_material(raw: Optional[str]) -> str:
    if not raw:
        return "AL6061"
    u = raw.strip().upper().replace(" ", "")
    aliases = {
        "ALUMINUM": "AL6061",
        "鋁": "AL6061",
        "鋁合金": "AL6061",
        "碳鋼": "S45C",
        "不鏽鋼": "SUS304",
    }
    return aliases.get(u, u)


def estimate_from_facts(
    facts: Dict[str, Any],
    override_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    輸入 quote_facts，計算純物理與加工之基準成本。
    支援 Aegis (主插件) 傳入 override_params 進行費率覆蓋與商業加成。
    """
    override = override_params or {}
    
    # 1. 費率與引數覆蓋（由主插件 Aegis 覆蓋）
    machining_rate = float(override.get("machining_rate_per_min") or _MACHINING_RATE_PER_MIN)
    markup_ratio = float(override.get("markup_ratio") or 1.0)  # 商業利潤成數，預設 1.0 (無加成)
    material_price_scale = float(override.get("material_price_scale") or 1.0)
    
    material = _norm_material(facts.get("material"))
    qty = max(1, int(facts.get("qty") or 1))
    
    # 2. 幾何物理計算
    vol = float(facts.get("volume_cm3") or 0.0)
    envelope_vol = 0.0
    envelope = facts.get("envelope_mm") or []
    if len(envelope) >= 3:
        L, W, H = envelope[:3]
        envelope_vol = (L * W * H) / 1000.0  # mm³ 轉 cm³
        if vol <= 0:
            vol = envelope_vol

    density = _DENSITY.get(material, 2.70)
    
    # 材質價格加權 (支援 Aegis 調整)
    base_price_kg = _MATERIAL_PRICE_PER_KG.get(material, 30.0)
    price_kg = base_price_kg * material_price_scale
    
    mass_kg = (vol * density) / 1000.0
    material_cost = mass_kg * price_kg

    # 3. 特徵工時估算
    holes = facts.get("holes") or []
    hole_count = sum(int(h.get("count") or 1) for h in holes)
    slots = facts.get("slots") or []
    slot_count = sum(int(s.get("count") or 1) for s in slots)

    mach_min = 15.0  # 基礎裝夾工時
    if vol > 0:
        mach_min += vol * 0.8  # 體積去除工時
    mach_min += hole_count * 0.8 + slot_count * 2.0  # 孔洞與凹槽加工時間
    
    perim = float((facts.get("2d") or {}).get("perimeter_mm") or 0)
    if perim > 0:
        mach_min += perim / 200.0

    machining_cost = mach_min * machining_rate
    
    # 4. 表面處理工藝加價
    surface_notes = facts.get("drawing_notes") or []
    surface_extra = 0.0
    treatment_type = "無"
    for n in surface_notes:
        if any(k in str(n) for k in ("陽極", "噴砂", "電鍍", "鈍化", "黑染")):
            surface_extra += 5.0 * qty
            treatment_type = str(n)
            break

    # 5. 幾何衝突檢測 (Conflicts Check)
    conflicts = list(facts.get("conflicts") or [])
    
    # 衝突 1: 實體體積大於包絡體積 (物理上不可能)
    if envelope_vol > 0 and vol > envelope_vol * 1.05:
        conflicts.append({
            "source": "quote_engine",
            "type": "geometry_mismatch",
            "message": f"衝突：實體體積 ({vol:.1f} cm³) 大於包絡箱體積 ({envelope_vol:.1f} cm³)，幾何事實異常。"
        })
        
    # 衝突 2: 未知材質警告
    if material not in _DENSITY:
        conflicts.append({
            "source": "quote_engine",
            "type": "unknown_material",
            "message": f"警告：未知的材質種類 '{material}'，已降級使用預設密度與報價計算。"
        })

    # 6. 計算總價並應用 Aegis 商業成數
    cost_subtotal = (material_cost + machining_cost + surface_extra) * qty
    final_subtotal = cost_subtotal * markup_ratio

    # 7. 標準化輸出明細（提供給大腦 Aegis 進行透明審核）
    lines: List[Dict[str, Any]] = [
        {
            "item": "材料費", 
            "base_amount": round(material_cost * qty, 2),
            "final_amount": round(material_cost * qty * markup_ratio, 2),
            "detail": f"{material} {mass_kg:.3f} kg/件 (單價: {price_kg:.1f} CNY/kg)"
        },
        {
            "item": "加工費", 
            "base_amount": round(machining_cost * qty, 2),
            "final_amount": round(machining_cost * qty * markup_ratio, 2),
            "detail": f"估算工時: {mach_min:.1f} 分鐘 (費率: {machining_rate:.1f} CNY/min)"
        },
    ]
    if surface_extra > 0:
        lines.append({
            "item": "表面處理費", 
            "base_amount": round(surface_extra, 2),
            "final_amount": round(surface_extra * markup_ratio, 2),
            "detail": f"工藝: {treatment_type}"
        })

    return {
        "ok": True,
        "currency": "CNY",
        "qty": qty,
        "material": material,
        "volume_cm3": round(vol, 3),
        "lines": lines,
        "base_cost": round(cost_subtotal, 2),
        "subtotal": round(final_subtotal, 2),  # 應用 Aegis 商業成數後的最終售價
        "markup_ratio": markup_ratio,
        "conflicts": conflicts,
        "note": "幾何物理基礎成本計算完成。商業成數與加價策略已由主插件 Aegis 覆蓋與核准。",
    }
