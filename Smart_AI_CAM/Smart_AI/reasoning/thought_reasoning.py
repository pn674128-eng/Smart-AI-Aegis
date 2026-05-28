# -*- coding: utf-8 -*-
"""
Smart_AI 思維與推理層 — 思想推理機 (ThoughtReasoning)
===================================================
• 執行幾何特徵與物理特徵的 Chain of Thought (CoT) 推理
• 深度結合 docs/fusion_api_reference 進行「API 事實檢索」與 RAG 查證
• 整合廠內實體刀具與物理切削參數計算 (physical_tool_engine)
• 提供 UI 思考鏈的結構化數據
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
from . import physical_tool_engine

# ─────────────────────────────────────────────
#  路徑與物理資料對齊
# ─────────────────────────────────────────────

def _brain_dir() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _api_ref_dir() -> str:
    return os.path.join(_brain_dir(), "..", "docs", "fusion_api_reference")


_PHYSICAL_MAT_INFO = {
    "AL6061": {
        "density": 2.70,
        "hardness": "95 HB (易切削)",
        "characteristic": "輕金屬，散熱快，排屑阻力低，適合高速切削。"
    },
    "S50C": {
        "density": 7.85,
        "hardness": "180 HB (中碳鋼)",
        "characteristic": "高硬度高強度，切削熱易集中在刀刃上，鐵屑不易切斷，排屑阻力極高。"
    }
}


# ─────────────────────────────────────────────
#  API 參考文檔 RAG 事實檢索器
# ─────────────────────────────────────────────

def _query_api_ref_facts(keyword: str, max_facts: int = 2) -> List[str]:
    """
    從 docs/fusion_api_reference 下的 HTML 文件中檢索與關鍵字相關的 API 事實段落。
    這實現了 AI 的大腦離線事實查證 (Fact-checking RAG)。
    """
    facts = []
    ref_dir = _api_ref_dir()
    if not os.path.isdir(ref_dir):
        return facts
        
    kw_pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    
    try:
        for fn in os.listdir(ref_dir):
            if not fn.lower().endswith(".html"):
                continue
            fp = os.path.join(ref_dir, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
                # 簡單移除 HTML tags 以獲取純文字
                text_only = re.sub(r"<[^>]+>", " ", content)
                # 依句點或換行拆分段落
                paragraphs = [p.strip() for p in re.split(r"[\n\.\;]", text_only) if p.strip()]
                for p in paragraphs:
                    if kw_pattern.search(p) and len(p) > 20 and len(p) < 200:
                        # 清理多餘空白
                        cleaned = " ".join(p.split())
                        facts.append(f"[參照手冊 {fn}] {cleaned}")
                        if len(facts) >= max_facts:
                            break
            except Exception:
                pass
            if len(facts) >= max_facts:
                break
    except Exception:
        pass
        
    return facts


# ─────────────────────────────────────────────
#  思維鏈推理主入口
# ─────────────────────────────────────────────

def generate_thought(
    feature_type:  str,
    material:      str,
    geometry:      dict,
    best_template: str,
    machine:       str = "未指定機台 (常規 12,000 RPM)"
) -> dict:
    """
    針對給定的加工情境與模板，生成結構化的思維推理日誌。

    Returns:
        {
           "intent": str,
           "observations": List[str],
           "hypothesis": List[str],
           "reasoning_steps": List[str]
        }
    """
    ft = str(feature_type).lower()
    mat = str(material).upper()
    geom = dict(geometry or {})
    
    mat_info = _PHYSICAL_MAT_INFO.get(mat, {"density": 5.0, "hardness": "未知", "characteristic": "一般金屬"})
    
    observations = []
    hypothesis = []
    reasoning_steps = []
    
    # 建立加工意圖 (Intent)
    intent = f"為 {mat} 材質的 {ft} 特徵進行安全且高效率的自動化編程決策 (機台: {machine})"
    
    # 1. 感知與觀察 (Observations)
    observations.append(f"識別到加工特徵類型為 {ft.upper()}，工件材質為 {mat}。")
    observations.append(f"材質屬性：硬度為 {mat_info['hardness']}。{mat_info['characteristic']}")
    
    # 針對特徵的幾何觀察與刀具直徑推算
    tool_dia = 10.0
    ratio = 0.0
    if ft == "hole":
        dia = geom.get("diameter_mm", 5.0)
        dep = geom.get("depth_mm", 15.0)
        htype = geom.get("hole_type", "general")
        ratio = round(dep / dia, 1) if dia > 0 else 0
        tool_dia = dia
        observations.append(f"孔幾何規格：直徑 D{dia} mm，深度 {dep} mm，深徑比為 {ratio}。")
        if ratio > 3.0:
            observations.append(f"【關鍵觀察】深徑比 {ratio} 達到深孔標準 (>3.0)，存在極高排屑阻力與積熱風險。")
            
        # 進行 API Facts 檢索
        facts = _query_api_ref_facts("DrillingType", 1)
        facts += _query_api_ref_facts("peckDepth", 1)
        for fact in facts:
            observations.append(f"【API 事實參考】{fact}")
            
    elif ft == "slot":
        w = geom.get("width_mm", 6.0)
        tool_dia = w
        observations.append(f"長條槽規格：槽寬 {w} mm。")
        facts = _query_api_ref_facts("Slot", 1)
        for fact in facts:
            observations.append(f"【API 事實參考】{fact}")
            
    elif ft == "face":
        area = geom.get("area_mm2", 1000.0)
        observations.append(f"面銑規格：大平面面積為 {area} mm²。")
        facts = _query_api_ref_facts("Face", 1)
        for fact in facts:
            observations.append(f"【API 事實參考】{fact}")
            
    elif ft == "profile":
        dep = geom.get("depth_mm", 20.0)
        observations.append(f"外輪廓銑削深度：{dep} mm。")
        facts = _query_api_ref_facts("Contour", 1)
        for fact in facts:
            observations.append(f"【API 事實參考】{fact}")
            
    else:
        observations.append("一般幾何觀察。")

    # 2. 動態調用力學引擎計算廠內實體刀具參數 (代入選用機台與 70% 散單安全係數)
    phys = physical_tool_engine.calculate_optimal_params(mat, tool_dia, is_roughing=True, machine_name=machine)
    observations.append(
        f"【廠內實體刀具適配】自動對齊奇力揚系列：'{phys['tool_series']}' ({phys['tool_code']})，"
        f"適用於 {phys['materials_class']}，具有 {phys['coating']}。"
    )
    observations.append(
        f"【機台配對觀測】當前選用機台：'{phys['active_machine']}'，主軸形式：{phys['taper_type']}，速限：{phys['max_rpm_limit']} RPM。"
    )
    observations.append(
        f"【少量散單加工安全約束】因應少量散單加工特性（每批 2-4 件），已自動調降理論參數至 {int(phys['safety_factor'] * 100)}% 保守值，保證加工平穩平順。"
    )
    
    # 轉速限速警告
    if phys['is_rpm_clamped']:
        observations.append(
            f"【主軸轉速安全限速】物理最佳轉速 {phys['original_spindle_speed']} RPM 已超越選用機台 (或常規限速) 極限，"
            f"已鉗制至安全轉速 S={phys['spindle_speed']} RPM，並等比例將進給率下修至 F={phys['feedrate']} mm/min，"
            f"以確保首件加工穩定性、防止斷刀震刀。"
        )
    else:
        observations.append(
            f"【力學切削計算】外徑 D{phys['diameter']} mm，安全下修 Vc={phys['optimal_vc']} m/min，"
            f"最優轉速 S={phys['spindle_speed']} RPM，安全每刃進給 fz={phys['fz_actual']} mm/tooth，"
            f"進給率 F={phys['feedrate']} mm/min，最大單次切深 Ap={phys['ap_limit_mm']} mm。"
        )
        
    # 剛性警告注入
    if not phys['rigidity_match']:
        observations.append(phys['rigidity_warning'])

    # 3. 方案評估與物理假說 (Hypothesis)
    if ft == "hole" and ratio > 3.0:
        hypothesis.append("假說 A (常規直鑽): 普通單次鑽孔到底，在中碳鋼 S50C 上可能導致切屑阻塞孔底，刀具扭斷。風險極高，予以排除。")
        hypothesis.append(f"假說 B (啄鑽排屑 + 廠內實體參數): 採用啄鑽 (Peck Drilling) 搭配 {phys['tool_series']}，每次進給 1mm 即全退刀排屑，轉速 {phys['spindle_speed']} RPM，進給 {phys['feedrate']} mm/min。安全性提升 200%。")
        hypothesis.append("決策取捨: 在高硬度深孔加工中，安全係數為第一優先，決定採用假說 B 啄鑽。")
    else:
        hypothesis.append(f"假說 A (標準刀路): 根據材質 {mat} 調用基準切削速度與進給率。")
        if mat == "S50C":
            hypothesis.append(f"假說 B (CIB 無敵重切專家模型): 調用 CIB 專用擺線/重切削參數，提供高抗震性與高剛性，在 HRC45 以下碳鋼上推薦轉速 {phys['spindle_speed']} RPM，進給率 {phys['feedrate']} mm/min。")
            if not phys['rigidity_match']:
                hypothesis.append("【剛性折衷假說】由於在 BT30 機台上切削鋼件剛性不足，除參數調降至 70% 外，強烈建議分段軸向切深 (Ap) 調低 30% 以減輕切削震動阻力。")
            hypothesis.append("決策取捨: 決定採用假說 B，配合散單極限安全參數與 Ap 約束安全輸出，以防崩刃。")
        elif "TI" in mat:
            hypothesis.append(f"假說 B (CAV 鈦合金專家模型): 鈦合金極易黏屑積熱，調用 CAV G1 塗層不等分割參數，轉速 {phys['spindle_speed']} RPM，進給率 {phys['feedrate']} mm/min，以防止黏刀並順暢排屑。")
            if not phys['rigidity_match']:
                hypothesis.append("【剛性折衷假說】在 BT30 上切削鈦合金時主軸剛性偏低，必須調小 Ap 切深，防範震刀與拉刀現象。")
            hypothesis.append("決策取捨: 採用假說 B，防黏刀模型安全輸出。")
        else:
            hypothesis.append(f"假說 B (ALUS 鏡面鋁用刀模型): 鋁合金易切削，月牙開法利刃可保持滿載高速輸出，於目前機台下推薦以（{phys['spindle_speed']} RPM / {phys['feedrate']} mm/min）運作，實現極致無刀痕鏡面加工。")
            hypothesis.append("決策取捨: 採用假說 B，維持散單安全速率輸出。")

    # 4. 決策推理步驟 (Reasoning Steps)
    reasoning_steps.append("步驟 1: 對齊物理模型，確認該加工特徵的最佳加工類型。")
    
    if ft == "hole" and ratio > 3.0:
        reasoning_steps.append(f"步驟 2: 設定 CAM 啄鑽參數。參考 API 規範，指定 peckDepth 為安全值 1.0 mm。轉速 S={phys['spindle_speed']} RPM，進給 F={phys['feedrate']} mm/min。")
    else:
        reasoning_steps.append(f"步驟 2: 設定切削數值。調用力學引擎，完成廠內實體刀具 {phys['tool_code']} 的轉速 RPM 與進給率（含散單 70% 保守折減及機台主軸限幅鉗制）校正。")
        
    reasoning_steps.append(f"步驟 3: 查詢 KnowledgeDB 信心推薦 ➔ 匹配最優模板：'{best_template}'。決策完成。")

    return {
        "intent":          intent,
        "observations":    observations,
        "hypothesis":      hypothesis,
        "reasoning_steps": reasoning_steps
    }
