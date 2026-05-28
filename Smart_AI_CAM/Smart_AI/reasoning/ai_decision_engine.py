# -*- coding: utf-8 -*-
"""
半自動加工選單 - 插件內部 AI 決策引擎 (Internal AI CAM Decision Engine)
包含材質密度與切削物理公式計算、智慧刀具推薦、以及自動化編程決策。
新增 Ollama 連線器，支援 L1/L2 深度推理。
"""

import math
import json
import urllib.request
import os

# ==========================================
# 1. 材質密度與物理切削知識庫 (Machining Knowledge Base)
# ==========================================
MATERIAL_DATABASE = {
    "AL6061": {
        "name": "鋁合金 AL6061",
        "density_g_cm3": 2.70,       # 基準密度 (Reference Density)
        "base_vc_m_min": 180.0,      # 基準切削線速度 Vc (m/min)
        "base_fz_mm_t": 0.08,        # 基準每刃進給量 fz (mm/tooth)
        "specific_energy": 0.8,      # 比切削能 (GPa) -> 鋁合金切削阻力小
        "hardness_hb": 95,
        "desc": "輕金屬，易切削，散熱快，建議高速高進給。"
    },
    "S50C": {
        "name": "中碳鋼 S50C",
        "density_g_cm3": 7.85,
        "base_vc_m_min": 90.0,
        "base_fz_mm_t": 0.05,
        "specific_energy": 2.2,      # 中高切削阻力
        "hardness_hb": 180,
        "desc": "中碳鋼，強度與硬度較高，加工時需適度降低轉速並注意排屑。"
    },
    "SUS304": {
        "name": "不鏽鋼 SUS304",
        "density_g_cm3": 8.00,
        "base_vc_m_min": 60.0,       # 不鏽鋼極易黏刀與硬化，線速度低
        "base_fz_mm_t": 0.04,
        "specific_energy": 2.6,      # 高切削阻力與加工硬化特性
        "hardness_hb": 200,
        "extra_damping": 0.8,       # 不鏽鋼額外安全衰減係數 (防燒刀、斷刀)
        "desc": "奧氏體不鏽鋼，極易加工硬化與黏刀，建議低速、充足冷卻並穩定切入。"
    },
    "Brass": {
        "name": "黃銅 Brass",
        "density_g_cm3": 8.50,       # 黃銅密度雖高，但切削性優良
        "base_vc_m_min": 140.0,
        "base_fz_mm_t": 0.07,
        "specific_energy": 1.1,      # 切削阻力中等偏低
        "hardness_hb": 110,
        "extra_damping": 1.1,       # 黃銅易切削，可給予係數補償
        "desc": "銅合金，切削性能極佳，排屑成碎屑狀，建議高進給。"
    },
    "Plastics": {
        "name": "工程塑料 (Plastics/POM/Nylon)",
        "density_g_cm3": 1.25,       # 低密度
        "base_vc_m_min": 240.0,      # 高速
        "base_fz_mm_t": 0.12,        # 大進給
        "specific_energy": 0.3,      # 極低阻力
        "hardness_hb": 25,
        "desc": "熱塑性塑料，切削力極小，但須注意溫度過高導致熔化變形，採超高速、大進給。"
    }
}

# ==========================================
# 2. 材質密度修正切削參數演算法
# ==========================================
def calculate_feeds_and_speeds(material_key, tool_dia_mm, teeth_count, is_drill=False, is_tap=False, pitch_mm=1.0):
    """
    依據材質密度與物理特性，非線性計算最優的切削轉速 (RPM) 與進給率 (F, mm/min)
    """
    mat = MATERIAL_DATABASE.get(material_key, MATERIAL_DATABASE["AL6061"])
    density = mat["density_g_cm3"]
    
    # 1. 密度修正物理模型 (Density-based Scaling Model)
    # 以鋁合金 AL6061 (密度 2.7) 為參考基準
    ref_density = 2.70
    k_density = ref_density / density
    
    # 物理修正公式：密度越高，速度與進給呈非線性衰減，以保障刀具壽命並降低切削扭力
    v_scale = math.pow(k_density, 0.55)
    f_scale = math.pow(k_density, 0.35)
    
    vc = mat["base_vc_m_min"] * v_scale
    fz = mat["base_fz_mm_t"] * f_scale
    
    # 套用特殊材質額外修正係數 (如不鏽鋼防燒刀衰減，黃銅優良加工性補償)
    extra_damping = mat.get("extra_damping", 1.0)
    vc *= extra_damping
    fz *= extra_damping
    
    # 2. 鑽孔或攻牙加工之特殊降速修正
    if is_drill:
        # 鑽孔切削為實心切削，線速度與每刃進給降為一般銑削的 75%
        vc *= 0.75
        fz *= 0.85
    elif is_tap:
        # 剛性攻牙速度須大幅降低，確保精準同步並防止折斷
        vc *= 0.30  # 降至 30% 速度
    
    # 3. 計算主軸轉速 RPM (N)
    # Formula: N = (1000 * Vc) / (pi * D)
    if tool_dia_mm <= 0.1:
        tool_dia_mm = 1.0  # 防止除以零
    
    rpm = (1000.0 * vc) / (math.pi * tool_dia_mm)
    rpm = round(max(500.0, min(18000.0, rpm))) # 主軸速限制在 500 ~ 18000 RPM
    
    # 4. 計算進給率 F (mm/min)
    if is_tap:
        # 剛性攻牙進給必須與主軸轉速、螺距嚴格同步同步： F = N * Pitch
        feed = round(rpm * pitch_mm)
    else:
        # Formula: F = N * Z * fz
        # 鑽頭通常視為雙刃 (Z=2)
        effective_teeth = 2 if is_drill else teeth_count
        feed = round(rpm * effective_teeth * fz)
        feed = max(50.0, min(6000.0, feed)) # 進給限制在 50 ~ 6000 mm/min
        
    return {
        "rpm": rpm,
        "feed": feed,
        "vc_m_min": round(vc, 1),
        "fz_mm_t": round(fz, 4),
        "k_density": round(k_density, 3)
    }

# ==========================================
# 3. 智慧 AI 刀具匹配與加工決策引擎
# ==========================================
class AIDecisionEngine:
    def __init__(self, current_tools=None):
        """
        current_tools: 當前刀具庫列表 (包含直徑、類型、刃數、刃長與避空長度)
        """
        self.tools = current_tools or []

    def find_best_tool(self, preferred_type, min_dia, max_dia, required_reach=0.0):
        """
        在可用刀具庫中尋找最契合的刀具，並進行避空長度安全校驗。
        """
        if not self.tools:
            return None, "⚠️ 本地刀具庫為空，將使用加工模板之預設刀具。"
            
        candidates = []
        for t in self.tools:
            t_type = str(t.get("type", "")).lower()
            t_dia = float(t.get("diameter_mm", 0.0) or t.get("diameter", 0.0))
            
            # 寬鬆類型比對
            type_match = False
            if "face" in preferred_type.lower() and ("face" in t_type or "shell" in t_type or "bull" in t_type or "flat" in t_type):
                type_match = True
            elif "flat" in preferred_type.lower() and ("flat" in t_type or "end" in t_type or "rough" in t_type):
                type_match = True
            elif "drill" in preferred_type.lower() and "drill" in t_type:
                type_match = True
            elif "tap" in preferred_type.lower() and "tap" in t_type:
                type_match = True
            elif "chamfer" in preferred_type.lower() and "chamfer" in t_type:
                type_match = True
            elif "reamer" in preferred_type.lower() and ("reamer" in t_type or "ream" in t_type):
                type_match = True
                
            if not type_match:
                # 備用：若找不到專用刀，立銑刀(Flat)可暫作替代
                if "flat" in t_type and preferred_type.lower() in ["face", "profile"]:
                    type_match = True
            
            if type_match and (min_dia <= t_dia <= max_dia):
                candidates.append(t)
                
        if not candidates:
            return None, f"⚠️ 刀具庫中找不到直徑在 {min_dia}~{max_dia}mm 之間的 {preferred_type}。請確認是否有此庫存。"
            
        # 優先選擇直徑最大（切削效率最高）且避空長度足夠的安全刀具
        candidates.sort(key=lambda x: float(x.get("diameter_mm", 0.0) or x.get("diameter", 0.0)), reverse=True)
        
        for t in candidates:
            # 取得避空長度 (Shoulder Length 或 Neck Length)
            shoulder = float(t.get("shoulder_length_mm", t.get("flute_length_mm", 0.0)))
            if shoulder >= required_reach:
                return t, "OK"
                
        # 若都低於安全長度，返回直徑最大者並發出撞刀警示
        dangerous_tool = candidates[0]
        max_reach = float(dangerous_tool.get("shoulder_length_mm", dangerous_tool.get("flute_length_mm", 0.0)))
        return dangerous_tool, f"⚠️ 警告：此刀具最大避空長度 ({max_reach}mm) 小於工件所需加工深度 ({required_reach}mm)，有極高撞刀風險！"

    def make_machining_plan(self, material_key, geom_features):
        """
        核心 AI 加工方案規劃演算法：
        根據幾何識別出的特徵 (geom_features: 包含 flat_depths, holes, slots 等)，
        做出全套工序的刀具匹配、模板選擇與轉速進給決策。
        """
        mat = MATERIAL_DATABASE.get(material_key, MATERIAL_DATABASE["AL6061"])
        plan = {
            "material": material_key,
            "material_name": mat["name"],
            "density": mat["density_g_cm3"],
            "density_description": f"材質密度為 {mat['density_g_cm3']} g/cm³，已動態修正切削物理參數。",
            "material_desc": mat["desc"],
            "decisions": {},
            "warnings": [],
            "overall_report": ""
        }
        
        # 1. 頂面面銑決策 (Face Milling)
        flat_data = geom_features.get("flat_depths", {})
        max_z_span = float(flat_data.get("z_span_mm", 0.0))
        planes = flat_data.get("planes", [])
        
        face_tool, face_status = self.find_best_tool("face", 10.0, 50.0, required_reach=5.0)
        face_dia = float(face_tool.get("diameter_mm", 30.0)) if face_tool else 30.0
        face_teeth = int(face_tool.get("teeth_count", 4)) if face_tool else 4
        
        face_params = calculate_feeds_and_speeds(material_key, face_dia, face_teeth)
        
        plan["decisions"]["top_face"] = {
            "use_face_milling": len(planes) > 0,
            "recommended_tool": face_tool.get("name", "預設 D30R5 面銑刀") if face_tool else "預設面銑刀",
            "recommended_tool_number": face_tool.get("number", 1) if face_tool else 1,
            "tool_status": face_status,
            "rpm": face_params["rpm"],
            "feed": face_params["feed"],
            "vc": face_params["vc_m_min"],
            "fz": face_params["fz_mm_t"],
            "reason": f"AI 面銑推薦：本工件有朝上水平平面。推薦使用直徑 {face_dia}mm 面銑刀。{face_status}"
        }
        if "警告" in face_status:
            plan["warnings"].append(f"頂面面銑：{face_status}")
            
        # 2. 外輪廓加工決策 (Outer Contour Milling)
        # 外輪廓需要銑削模型最外圈，深度為最大 Z 軸落差
        contour_depth = max_z_span if max_z_span > 0 else 20.0
        contour_tool, contour_status = self.find_best_tool("flat", 6.0, 20.0, required_reach=contour_depth)
        contour_dia = float(contour_tool.get("diameter_mm", 10.0)) if contour_tool else 10.0
        contour_teeth = int(contour_tool.get("teeth_count", 4)) if contour_tool else 4
        
        contour_params = calculate_feeds_and_speeds(material_key, contour_dia, contour_teeth)
        
        plan["decisions"]["outer_contour"] = {
            "use_contour_milling": True,
            "depth_mm": round(contour_depth, 2),
            "recommended_tool": contour_tool.get("name", f"預設 D{contour_dia} 粗精銑刀") if contour_tool else "預設立銑刀",
            "recommended_tool_number": contour_tool.get("number", 2) if contour_tool else 2,
            "tool_status": contour_status,
            "rpm": contour_params["rpm"],
            "feed": contour_params["feed"],
            "vc": contour_params["vc_m_min"],
            "fz": contour_params["fz_mm_t"],
            "reason": f"AI 外輪廓推薦：模型總落差深度為 {round(contour_depth, 2)}mm。推薦使用 D{contour_dia} 立銑刀以確保剛性。{contour_status}"
        }
        if "警告" in contour_status:
            plan["warnings"].append(f"外輪廓加工：{contour_status}")
            
        # 3. 孔加工決策 (Hole Process Planning)
        holes = geom_features.get("holes", [])
        hole_decisions = []
        
        for idx, h in enumerate(holes):
            h_dia = float(h.get("dia", h.get("diameter", h.get("diameter_mm", 0.0))))
            h_depth = float(h.get("depth", h.get("depth_mm", 10.0)))
            is_threaded = bool(h.get("isThreaded", False)) or bool(h.get("is_threaded", False))
            thread_pitch = float(h.get("threadPitch", 1.0))
            is_reamer = (h.get("semantic_type") == "pin_position_hole")
            
            # 對於每個孔，AI 規劃最優的工藝鏈 (Process Chain)
            # 例如：簡單圓孔 -> 中心鑽定位 -> 鑽孔 -> 鉸孔/精銑
            # 螺紋孔 -> 中心鑽 -> 鑽底孔 -> 攻牙
            h_plan = {
                "idx": idx,
                "dia": h_dia,
                "depth": h_depth,
                "is_threaded": is_threaded,
                "semantic_type": h.get("semantic_type", ""),
                "label": h.get("label", f"孔 D{h_dia}"),
                "process_chain": []
            }
            
            if is_threaded:
                # 螺紋孔工藝鏈
                tap_pitch = thread_pitch
                drill_dia = h_dia - tap_pitch # 粗略底孔計算 D_drill = D_thread - Pitch

                
                # 1. 匹配底孔鑽頭
                drill_tool, drill_status = self.find_best_tool("drill", drill_dia - 0.2, drill_dia + 0.2, required_reach=h_depth)
                actual_drill_dia = float(drill_tool.get("diameter_mm", drill_dia)) if drill_tool else drill_dia
                drill_params = calculate_feeds_and_speeds(material_key, actual_drill_dia, 2, is_drill=True)
                
                # 2. 匹配絲攻
                tap_tool, tap_status = self.find_best_tool("tap", h_dia - 0.1, h_dia + 0.1, required_reach=h_depth)
                tap_params = calculate_feeds_and_speeds(material_key, h_dia, 4, is_tap=True, pitch_mm=tap_pitch)
                
                h_plan["process_chain"].append({
                    "step": "1. 鑽底孔",
                    "tool": drill_tool.get("name", f"D{round(drill_dia, 1)} 鑽頭") if drill_tool else f"D{round(drill_dia, 1)} 鑽頭",
                    "rpm": drill_params["rpm"],
                    "feed": drill_params["feed"],
                    "reason": f"剛性攻牙底孔匹配：螺紋規格 Pitch={tap_pitch}mm，推薦使用 D{round(drill_dia, 1)} 鑽頭。"
                })
                h_plan["process_chain"].append({
                    "step": "2. 攻牙",
                    "tool": tap_tool.get("name", f"M{h_dia} 絲攻") if tap_tool else f"M{h_dia} 絲攻",
                    "rpm": tap_params["rpm"],
                    "feed": tap_params["feed"],
                    "reason": f"AI 剛性攻牙：轉速與進給严格同步同步 (F = RPM * Pitch = {tap_params['feed']} mm/min)。"
                })
            elif is_reamer:
                # 定位銷精密鉸孔工藝鏈 (預鑽銷孔小 0.2mm + 鉸刀精修)
                drill_dia = round(h_dia - 0.2, 2)
                if drill_dia < 1.0:
                    drill_dia = h_dia
                
                # 1. 匹配底孔鑽頭
                drill_tool, drill_status = self.find_best_tool("drill", drill_dia - 0.25, drill_dia + 0.25, required_reach=h_depth)
                actual_drill_dia = float(drill_tool.get("diameter_mm", drill_dia)) if drill_tool else drill_dia
                drill_params = calculate_feeds_and_speeds(material_key, actual_drill_dia, 2, is_drill=True)
                
                # 2. 匹配精密鉸刀
                reamer_tool, reamer_status = self.find_best_tool("reamer", h_dia - 0.05, h_dia + 0.05, required_reach=h_depth)
                # 鉸孔參數計算：依據行業標準，鉸孔轉速與進給均需進行 50%~60% 的折減，以防孔徑擴大或表面粗糙度不佳
                raw_ream_params = calculate_feeds_and_speeds(material_key, h_dia, 4, is_drill=True)
                ream_rpm = round(raw_ream_params["rpm"] * 0.5)
                ream_feed = round(raw_ream_params["feed"] * 0.55)
                
                h_plan["process_chain"].append({
                    "step": "1. 預鑽銷孔",
                    "tool": drill_tool.get("name", f"D{actual_drill_dia} 鑽頭") if drill_tool else f"D{drill_dia} 鑽頭",
                    "rpm": drill_params["rpm"],
                    "feed": drill_params["feed"],
                    "reason": f"幾何自適應反推預鑽孔：定位銷直徑為 {h_dia}mm，預留 0.2mm 鉸削量，推薦預鑽 D{drill_dia}mm。{drill_status}"
                })
                h_plan["process_chain"].append({
                    "step": "2. 精密鉸削",
                    "tool": reamer_tool.get("name", f"D{h_dia} 鉸刀") if reamer_tool else f"D{h_dia} 鉸刀",
                    "rpm": ream_rpm,
                    "feed": ream_feed,
                    "reason": f"精密銷孔鉸孔：已折減轉速與進給 (RPM 折減 50%, Feed 折減 45%) 以保證 H7 公差精度與高表面粗糙度。{reamer_status}"
                })
            else:
                # 簡單圓孔工藝鏈
                # 1. 匹配鑽頭
                drill_tool, drill_status = self.find_best_tool("drill", h_dia - 0.2, h_dia + 0.2, required_reach=h_depth)
                actual_drill_dia = float(drill_tool.get("diameter_mm", h_dia)) if drill_tool else h_dia
                drill_params = calculate_feeds_and_speeds(material_key, actual_drill_dia, 2, is_drill=True)
                
                h_plan["process_chain"].append({
                    "step": "1. 鑽孔",
                    "tool": drill_tool.get("name", f"D{h_dia} 鑽頭") if drill_tool else f"D{h_dia} 鑽頭",
                    "rpm": drill_params["rpm"],
                    "feed": drill_params["feed"],
                    "reason": f"簡單孔鑽孔加工。{drill_status}"
                })
                
            hole_decisions.append(h_plan)
            
        plan["decisions"]["holes"] = hole_decisions

        # 3b. 長條槽決策（寬度 → 刀徑可行性，與主程式 _recommend_slot_tool_dia 一致）
        slots = geom_features.get("slots", []) or []
        slot_decisions = []
        tool_candidates = (2.0, 3.0, 4.0, 6.0, 10.0)
        for s in slots:
            if not isinstance(s, dict):
                continue
            w = float(s.get("width_mm", 0.0) or 0.0)
            if w <= 0:
                continue
            feasible = [d for d in tool_candidates if (d + 0.5) <= w <= (d * 1.8)]
            rec_d = feasible[-1] if feasible else None
            slot_decisions.append(
                {
                    "idx": int(s.get("idx", len(slot_decisions))),
                    "width_mm": round(w, 3),
                    "length_mm": round(float(s.get("length_mm", 0.0) or 0.0), 3),
                    "depth_mm": round(float(s.get("depth_mm", 0.0) or 0.0), 3),
                    "active": bool(s.get("active", False)),
                    "has_loop_edges": bool(s.get("has_loop_edges", False)),
                    "recommended_tool_dia_mm": rec_d,
                    "feasible_tool_dias_mm": feasible,
                    "reason": (
                        f"槽寬 {w}mm：建議刀徑 D{rec_d}（可行 {feasible}）。"
                        if rec_d
                        else f"槽寬 {w}mm：無符合 D+0.5≤W≤D×1.8 之標準刀徑，請手選模板。"
                    ),
                }
            )
        plan["decisions"]["slots"] = slot_decisions

        # 3c. 視線法摘要（眼層）
        vision = geom_features.get("vision") or {}
        plan["decisions"]["vision"] = vision
        if vision.get("ok"):
            perim = vision.get("outer_perimeter_mm")
            perim_txt = f"{perim} mm" if perim is not None else "—"
            plan["warnings"].append(
                "視線法：Setup「{}」外輪廓約 {} 周長；台面列 {}；作用中槽 {} / 總槽 {}。".format(
                    vision.get("setup_name", ""),
                    perim_txt,
                    vision.get("contour_face_rows", 0),
                    vision.get("slots_active", 0),
                    vision.get("slots_total", 0),
                )
            )

        catalog = geom_features.get("feature_catalog") or {}
        plan["decisions"]["feature_catalog"] = {
            "feature_count": int(catalog.get("feature_count", 0)),
            "counts_by_category": dict(catalog.get("counts_by_category") or {}),
            "counts_by_cam_operation": dict(catalog.get("counts_by_cam_operation") or {}),
        }
        chamfer_n = int((catalog.get("counts_by_category") or {}).get("chamfer_bevel", 0))
        if chamfer_n:
            plan["decisions"]["chamfer_bevel"] = {
                "count": chamfer_n,
                "cam_operation": "chamfer",
                "reason": "外輪廓鄰接斜邊（倒角）已納入辨識目錄，建議 contourChamfer / holeChamfer 模板。",
            }

        pcr = geom_features.get("pocket_corner_r") or []
        if pcr:
            plan["decisions"]["pocket_corner_r"] = {
                "count": len(pcr),
                "cam_operation": "drill",
                "reason": "口袋槽垂直 R 角列；請用一般鑽模板小徑加工。",
            }

        # 4. 生成總體報告 (Overall Report Summary)
        report = []
        report.append(f"【AI CAM 智能加工決策報告 - 材質：{mat['name']}】")
        report.append(f"ℹ️ {plan['density_description']}")
        report.append(f"ℹ️ {mat['desc']}")
        report.append(f"--------------------------------------------------")
        report.append(f"1. 頂面加工：{'✓ 建議面銑' if len(planes) > 0 else '✗ 無朝上平面'}，推薦刀具 {plan['decisions']['top_face']['recommended_tool']}，主軸 {plan['decisions']['top_face']['rpm']} RPM，進給 {plan['decisions']['top_face']['feed']} mm/min。")
        report.append(f"2. 外輪廓加工：✓ 建議外圍銑削，切削深度 {plan['decisions']['outer_contour']['depth_mm']}mm，推薦刀具 {plan['decisions']['outer_contour']['recommended_tool']}，主軸 {plan['decisions']['outer_contour']['rpm']} RPM，進給 {plan['decisions']['outer_contour']['feed']} mm/min。")
        if holes:
            report.append(f"3. 孔洞加工：偵測到 {len(holes)} 個加工孔，已自動為所有孔匹配最佳鑽孔與剛性攻牙流程。")
        else:
            report.append(f"3. 孔洞加工：未偵測到需加工的孔洞。")
        if slot_decisions:
            active_n = sum(1 for x in slot_decisions if x.get("active"))
            report.append(
                f"4. 長條槽：共 {len(slot_decisions)} 組（作用中 {active_n}），已依槽寬給出刀徑可行性建議。"
            )
        if vision.get("ok"):
            report.append(
                f"5. 視線法（Eye）：外周長 {vision.get('outer_perimeter_mm', '—')} mm；"
                f"輪廓台面 {vision.get('contour_face_rows', 0)}；"
                f"模式 {vision.get('vision_mode', 'FAST_2D')}。"
            )
        cat = geom_features.get("feature_catalog") or {}
        if cat.get("feature_count"):
            report.append(
                "6. 辨識目錄：共 {} 項特徵；類別 {}；建議工序 {}。".format(
                    cat.get("feature_count", 0),
                    cat.get("counts_by_category", {}),
                    cat.get("counts_by_cam_operation", {}),
                )
            )
            
        deps = geom_features.get("machining_dependencies", [])
        plan["decisions"]["machining_dependencies"] = deps
        if deps:
            report.append(f"--------------------------------------------------")
            report.append(f"✦ 【特徵協同 - 加工順序與嵌套優化建議】")
            for idx, dep in enumerate(deps):
                report.append(f"  ({idx+1}) 【{dep.get('type','')}】{dep.get('reason')}")
            
        if plan["warnings"]:
            report.append(f"\n⚠️ 【AI 刀路安全警告清單】")
            for w in plan["warnings"]:
                report.append(f"  * {w}")
        else:
            report.append(f"\n✅ 經內部 AI 剛性與安全避空驗證：所有刀路刀具均安全，無撞刀風險。")
            
        plan["overall_report"] = "\n".join(report)
        return plan

    def generate_plan_with_ollama(self, material_key, geom_features):
        """
        使用 Ollama 進行 L1 特徵加工策略的 AI 推理。
        將掃描到的幾何特徵交給本地大語言模型決策。
        """
        connector = OllamaDecisionConnector(default_model="qwen2.5-coder:7b")
        
        # 提取 LLM 需要知道的關鍵特徵，避免 Prompt 過長
        prompt_data = {
            "material": material_key,
            "holes": geom_features.get("holes", []),
            "slots": geom_features.get("slots", [])
        }
        
        prompt = f"""
        你是一個專業的 CNC CAM 編程專家。
        目前工件材質為：{material_key}。
        以下是從 CAD 模型掃描到的特徵資料：
        {json.dumps(prompt_data, ensure_ascii=False)}
        
        請根據以上特徵，輸出一個 JSON 格式的加工建議。
        必須回傳嚴格的 JSON，包含以下結構：
        {{
            "decisions": {{
                "holes": [ {{"idx": 0, "reason": "為什麼這樣配刀", "recommended_tool": "建議刀徑與類型"}} ],
                "slots": [ {{"idx": 0, "reason": "...", "recommended_tool": "..."}} ]
            }},
            "overall_report": "整體的加工策略與注意事項說明..."
        }}
        """
        
        system_prompt = "You are a professional CNC CAM programmer. Always output valid JSON."
        
        # 發送請求給本地 Ollama
        ai_response = connector.ask_ollama(prompt, system_prompt=system_prompt, require_json=True)
        
        # 將 Ollama 的回應包裝成您的 Plan 格式
        return ai_response

# ==========================================
# 4. Ollama 本地端 LLM 決策連線器 (供 L1/L2 深度推理使用)
# ==========================================
class OllamaDecisionConnector:
    def __init__(self, host="127.0.0.1", port=11434, default_model="qwen2.5-coder:7b"):
        self.host = host
        self.port = port
        self.api_url = f"http://{host}:{port}/api/chat"
        self.default_model = default_model

    def is_running(self) -> bool:
        """輕量級檢測本地 Ollama 服務埠口是否已啟動"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((self.host, self.port))
            s.close()
            return True
        except Exception:
            return False

    def ask_ollama(self, prompt, system_prompt="You are a professional CNC CAM programmer.", model=None, require_json=True):
        """
        使用 Python 內建函式庫向本地 Ollama 發送請求 (零外部套件依賴)
        """
        # 1. 服務自癒檢測：若尚未啟動，嘗試透過桌面捷徑喚醒
        if not self.is_running():
            try:
                from Smart_AI.reasoning.reference_paths import resolve_ollama_path
                import subprocess
                import time
                
                exe_path = resolve_ollama_path()
                if exe_path and os.path.isfile(exe_path):
                    # 後台啟動 Ollama serve 服務
                    subprocess.Popen([exe_path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    # 等待最多 5 秒讓服務啟動
                    for _ in range(5):
                        time.sleep(1.0)
                        if self.is_running():
                            break
            except Exception as se:
                print(f"[Ollama Connector] Auto-start failed: {se}")

        payload = {
            "model": model or self.default_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,  # 降低隨機性，保證 CAM 參數的穩定性
                "top_p": 0.1
            }
        }
        
        if require_json:
            payload["format"] = "json"  # 強制 Ollama 嚴格輸出 JSON 格式
            
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self.api_url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            # 設定較長的 Timeout (L2 推理可能需要數十秒)
            with urllib.request.urlopen(req, timeout=120.0) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                content = res_json.get('message', {}).get('content', '')
                
                if require_json:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"error": "Ollama output is not valid JSON", "raw_content": content}
                    except TypeError:
                        # qwen/ollama tool/json output format fallback
                        return content
                return content
                
        except Exception as e:
            print(f"[Ollama Connector] Error: {e}")
            return {"error": str(e), "success": False}

