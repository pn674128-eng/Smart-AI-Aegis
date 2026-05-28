# -*- coding: utf-8 -*-
r"""
切削參數三層解析器 (Cutting Parameters Resolver)
=================================================
用戶 2026.05 設計指示:
  「當有特定刀具就以刀具的表參數做依據 (建立特定刀具檢索表),
   沒有就以餵給的資料當作參考依據 (建立大數據庫)」
  「以表中的轉速進給去換算其他刀具,
   不一定全部都要有, 推斷也是 CNC 加工的重點」

六層降級架構 (Confidence-Decreasing Fallback):

  ┌──────────────────────────────────────────────────────────────────┐
  │ L1 GOLD       = 本地 Fusion preset (用戶實機「上機值」)            │ 0.90+
  │ ──────────────────────────────────────────────────────────────── │
  │ L2A SILVER_GC = gold_cobra (硬車鋼 HRC≥48 OR 模具鋼)              │ 0.78
  │ L2B SILVER_RM = regular_milling (用戶口傳 5 工法 + holder + 油)   │ 0.75
  │ L2C SILVER_KE = keili_catalog (奇力揚 CIB/ALUS/CAVN/CFSL/CH01M)   │ 0.72
  │ ──────────────────────────────────────────────────────────────── │
  │ L2D BRONZE_MJ = 銘九通用表 (鋁/銅/淬火鋼平刀+球刀+長刃+微徑)       │ 0.60
  │ L3  INFER     = 推斷引擎 (Vc 上限 × 工法折扣 × 物理上限)           │ 0.55
  └──────────────────────────────────────────────────────────────────┘

  順位邏輯:
    • L1 一律最高優先 (用戶實機, 絕對信任)
    • L2A 在 L2B 前: 硬車 HRC≥48 直接走 GoldCobra
    • L2B 在 L2C 前: 用戶口傳 5 工法 (regular_milling) 比廠商通用值貼合
    • L2C 在 L2D 前: 奇力揚特定材質表 > 銘九通用表
    • 任一層成功即返回 (節省 token + 加快回應)
    • 所有層最終都過 machining_heuristics.apply_ceilings 物理封頂
    • 結果都過 general_catalog.sanity_check 銘九「防護層」驗證

範例呼叫:
  resolve(material="AL6061", tool_dia=6, operation="側銑")
    → L1 命中本地 ALUS T6 D=6 側銑 preset → RPM=9500 F=1500 Vc=179

  resolve(material="SUS304", tool_dia=8, operation="side")
    → L1 沒匹配 → L2 命中 CAVN 鈦/不銹鋼表 → 套散件折扣 → 套物理上限

  resolve(material="Inconel", tool_dia=10, operation="finishing")
    → L1/L2 都沒 → L3 推斷 (Vc 40 + 工法折扣 + 物理上限)
"""

from typing import Any, Dict, List, Optional
import math

try:
    from . import tool_library_query as _tlq
    from . import keili_catalog as _kc
    from . import general_catalog as _gc
    from . import machining_heuristics as _mh
    from . import tool_holders as _th
    try:
        from . import gold_cobra_catalog as _gcc
    except ImportError:
        _gcc = None
    try:
        from . import regular_milling as _rm
    except ImportError:
        _rm = None
except ImportError:
    from smart_ai_cam_mcp import tool_library_query as _tlq
    from smart_ai_cam_mcp import keili_catalog as _kc
    from smart_ai_cam_mcp import general_catalog as _gc
    from smart_ai_cam_mcp import machining_heuristics as _mh
    from smart_ai_cam_mcp import tool_holders as _th
    try:
        from smart_ai_cam_mcp import gold_cobra_catalog as _gcc
    except ImportError:
        _gcc = None
    try:
        from smart_ai_cam_mcp import regular_milling as _rm
    except ImportError:
        _rm = None


# ─────────────────────────────────────────────────────────────────────
# regular_milling 工法名稱對映 (中文/英文 → rm key)
# ─────────────────────────────────────────────────────────────────────
_RM_OP_MAP = {
    "face":   "face",   "facing": "face",   "面銑": "face",
    "side":   "side",   "side_milling": "side", "側銑": "side",
    "contour": "side",  "外形": "side",     "外形精修": "side",
    "adaptive": "side", "adaptive_clearing": "side", "動態": "side",
    "hole":   "hole",   "hole_milling": "hole", "孔銑": "hole",
    "helix":  "hole",   "helical": "hole",
    "slot":   "slot",   "slotting": "slot", "滿刃銑": "slot", "開槽": "slot",
    "plunge": "plunge", "plunging": "plunge", "插銑": "plunge",
}


def _map_to_rm_operation(operation: str,
                         feature_type: Optional[str]) -> Optional[str]:
    """把 cutting_resolver 的 operation/feature_type 對映到 rm 工法鍵。"""
    if not operation:
        return None
    op_lower = (operation or "").lower().strip()
    fty_lower = (feature_type or "").lower().strip()
    # feature_type 優先 (Fusion 給的)
    if fty_lower in _RM_OP_MAP:
        return _RM_OP_MAP[fty_lower]
    if op_lower in _RM_OP_MAP:
        return _RM_OP_MAP[op_lower]
    # 模糊匹配
    for key, val in _RM_OP_MAP.items():
        if key in op_lower or key in fty_lower:
            return val
    return None


# ─────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────

def resolve(material: str,
            tool_dia: float,
            operation: str = "side",
            feature_type: Optional[str] = None,
            teeth: Optional[int] = None,
            series: Optional[str] = None,
            mode: str = "conservative",
            holder: str = "ER",
            spindle_kw: float = 7.5,
            spindle_rpm_max: int = 12000,
            tool_id: Optional[int] = None,
            tool_material: str = "Carbide",
            pitch: Optional[float] = None,
            prefer_layer: Optional[str] = None,
            skip_local_preset: bool = False,
            hardness_hrc: Optional[float] = None,
            enable_sanity_check: bool = True,
            coolant: str = "flood",
            hole_diameter: Optional[float] = None,
            tool_flute_length: Optional[float] = None,
            cutting_pattern: str = "sidewall",
            chip_thinning_compensation: float = 0.0) -> Dict[str, Any]:
    """三層降級解析切削參數。

    Args:
        material:     工件材質 (AL6061/S50C/SUS304/NAK80/Ti-6Al-4V...)
        tool_dia:     刀徑 mm (攻牙時=螺紋外徑)
        operation:    工法 (中文/英文): 側銑/面銑/滿刃銑/插銑/...
        feature_type: 加工類型 (hole/face/contour/pocket/chamfer/ball)
                      hole/chamfer 會自動切換到「鑽頭/絞刀/倒角」模式
        teeth:        刃數 (L2/L3 用; L1 從 preset 取)
        series:       廠商系列 (L2 用; 預設依 material 自動選)
        mode:         "conservative" (散件 75/50 折) / "aggressive" (量產)
        holder:       刀把類型 (ER/SK/pullback)
        spindle_kw:   主軸功率 (用 L3 算 F 上限)
        spindle_rpm_max: 主軸 RPM 硬上限 (預設 12000, 用戶機台)
        tool_id:      指定 T 編號 (跳過自動選刀)
        tool_material: 刀具材質 (HSS/HSS-Co/Powder_HSS/Carbide/PCD/CBN)
        pitch:        攻牙/螺紋銑用 (mm)
        prefer_layer: "L1"/"L2"/"L3" 強制使用某一層 (預設自動降級)
        skip_local_preset: True 跳過 L1 直接用 L2 (debug 用)
        hardness_hrc: 工件硬度 HRC (影響材質正規化, 例如 SKD11+58 → SKD11_hardened)
                      ★ 預設 None → 用材質鍵預設狀態 (出貨/退火態)
        enable_sanity_check: 對最終結果跑銘九通用表「防護層」驗證 (預設 True)
        coolant:      "flood" (切削油) / "air" (吹氣) / "dry" (乾切)
                      影響 L2C regular_milling chip thinning 補償
        hole_diameter: 孔銑用, 孔直徑 mm (給 L2C regular_milling 算螺旋空間)
        tool_flute_length: 插銑用, 刃長 mm (給 L2C regular_milling 算 AP)
        cutting_pattern: "sidewall" (側壁) / "face" (平面)
                      影響 L2A gold_cobra 的 AE/AP 對調
        chip_thinning_compensation: 0.0~1.0 (L2C 側銑用, 預設 0 = 用戶實機)

    Returns:
        {
            "success": True,
            "layer": "L1_GOLD" | "L2_SILVER" | "L3_BRONZE",
            "confidence": float,
            "params": {rpm, feed_mm_min, Vc_m_min, fz_mm_tooth, ae_mm, ap_mm, ...},
            "tool": {T, description, ...} (L1 才有),
            "source_detail": {...層別專屬資訊},
            "clamps_applied": [...物理上限被套用的審計軌跡],
            "fallback_chain": ["L1 missed", "L2 hit"] (顯示為何到這層),
            "note": "...人類可讀說明",
        }
    """
    fallback_chain: List[str] = []
    force_layer = (prefer_layer or "").upper()

    # ★ 材質鍵正規化 (僅給 L2/L2B/L3 用; L1 保留原字串去匹配用戶本地 preset)
    #   - L1: 用戶本地 preset 通常用基礎字串 (SKD11, 不會帶 _hardened)
    #   - L2/L2B/L3: 需要正規化後的鍵, 才能 hit 對的 Vc/HRC 欄位
    material_l1 = material  # 給 L1 用 (原字串)
    material_norm = _mh.normalize_material(material, hardness_hrc=hardness_hrc)
    if material_norm != material_l1:
        fallback_chain.append(
            f"材質正規化 (L2+): {material_l1} (HRC={hardness_hrc}) → {material_norm}"
        )

    result: Optional[Dict[str, Any]] = None

    # ═══════════════════ L1 GOLD: 本地 preset ═══════════════════
    if not skip_local_preset and force_layer in ("", "L1"):
        l1 = _try_l1_local_preset(material_l1, tool_dia, operation,
                                  feature_type, tool_id)
        if l1:
            # L1 本地 preset 是用戶實機驗證, 用原字串 (不正規化) 套 ceilings
            # 避免: 用戶查 "SKD11" 本地有退火 preset, 卻被淬火態緊縮上限夾
            l1 = _enrich_with_ceilings(l1, material_l1, tool_dia,
                                       spindle_kw, spindle_rpm_max,
                                       hardness_hrc=None)  # ★L1 不用 hrc 強制
            l1["fallback_chain"] = fallback_chain + ["L1 HIT (本地 preset)"]
            result = l1
        else:
            fallback_chain.append("L1 miss (本地刀具庫無匹配 preset)")
            if force_layer == "L1":
                return _miss_result("L1 forced but not found", fallback_chain)

    # ═══════════ L2A SILVER_GC: gold_cobra 硬車鋼 (HRC≥48 觸發) ═══════════
    if (result is None and force_layer in ("", "L2", "L2A") and _gcc is not None
            and _gc_eligible(material_norm, series, hardness_hrc)):
        l2a = _try_l2a_gold_cobra(material_norm, tool_dia, series, feature_type,
                                  mode, hardness_hrc, cutting_pattern)
        if l2a.get("success"):
            l2a = _enrich_with_ceilings(l2a, material_norm, tool_dia,
                                        spindle_kw, spindle_rpm_max,
                                        hardness_hrc=hardness_hrc)
            l2a["fallback_chain"] = fallback_chain + ["L2A HIT (GoldCobra)"]
            result = l2a
        else:
            fallback_chain.append(f"L2A miss ({l2a.get('error','no match')})")
            if force_layer == "L2A":
                return _miss_result(l2a.get("error", "L2A forced but failed"),
                                    fallback_chain)

    # ═══════ L2B SILVER_RM: regular_milling 用戶口傳 5 工法 (operation 觸發) ═══
    if result is None and force_layer in ("", "L2", "L2B") and _rm is not None:
        rm_op = _map_to_rm_operation(operation, feature_type)
        if rm_op is not None:
            l2b_rm = _try_l2c_regular_milling(material_norm, tool_dia, rm_op,
                                              holder, coolant, teeth,
                                              hole_diameter, tool_flute_length,
                                              chip_thinning_compensation,
                                              operation_original=operation)
            if l2b_rm.get("success"):
                # 更新 layer 標籤為新的命名
                l2b_rm["layer"] = "L2B_SILVER_RM"
                l2b_rm["confidence"] = 0.75
                l2b_rm = _enrich_with_ceilings(l2b_rm, material_norm, tool_dia,
                                               spindle_kw, spindle_rpm_max,
                                               hardness_hrc=hardness_hrc)
                l2b_rm["fallback_chain"] = fallback_chain + [
                    f"L2B HIT (regular_milling, rm_op={rm_op})"]
                result = l2b_rm
            else:
                fallback_chain.append(
                    f"L2B miss ({l2b_rm.get('error', 'no match')})")
                if force_layer == "L2B":
                    return _miss_result(
                        l2b_rm.get("error", "L2B forced but failed"),
                        fallback_chain)
        else:
            fallback_chain.append(
                f"L2B skip (operation={operation} 不在 5 工法清單)")

    # ═══════════════════ L2C SILVER_KE: 奇力揚特定系列 ═══════════════════
    if result is None and force_layer in ("", "L2", "L2C"):
        l2 = _try_l2_vendor_catalog(material_norm, tool_dia, operation, feature_type,
                                    teeth, series, mode, holder, pitch)
        if l2.get("success"):
            # 重新標籤
            l2["layer"] = "L2C_SILVER_KE"
            l2["confidence"] = 0.72
            l2 = _enrich_with_ceilings(l2, material_norm, tool_dia,
                                       spindle_kw, spindle_rpm_max,
                                       hardness_hrc=hardness_hrc)
            l2["fallback_chain"] = fallback_chain + ["L2C HIT (奇力揚)"]
            result = l2
        else:
            fallback_chain.append(f"L2C miss ({l2.get('error','no match')})")
            if force_layer == "L2C":
                return _miss_result(l2.get("error", "L2C forced but failed"),
                                    fallback_chain)

    # ═══════════════════ L2D BRONZE_MJ: 銘九通用值庫 ═══════════════════
    if result is None and force_layer in ("", "L2D", "L2B_MJ"):
        l2b = _try_l2b_general_catalog(material_norm, tool_dia, operation,
                                       feature_type, mode,
                                       hardness_hrc=hardness_hrc)
        if l2b.get("success"):
            l2b = _enrich_with_ceilings(l2b, material_norm, tool_dia,
                                        spindle_kw, spindle_rpm_max,
                                        hardness_hrc=hardness_hrc)
            l2b["fallback_chain"] = fallback_chain + ["L2D HIT (銘九通用)"]
            result = l2b
        else:
            fallback_chain.append(f"L2D miss ({l2b.get('error','no match')})")
            if force_layer == "L2D":
                return _miss_result(l2b.get("error", "L2D forced but failed"),
                                    fallback_chain)

    # ═══════════════════ L3 INFER: 推斷引擎 ═══════════════════
    if result is None:
        l3 = _try_l3_heuristics(material_norm, tool_dia, operation, feature_type,
                                teeth, tool_material, mode,
                                spindle_kw, spindle_rpm_max,
                                hardness_hrc=hardness_hrc)
        l3["fallback_chain"] = fallback_chain + ["L3 HIT (推斷引擎)"]
        result = l3

    # ═══════════════════ ★ 防護層: 跟銘九通用表夾擠驗證 ═══════════════════
    # 用戶 2026.05 指示: 「通用表的參數可以作為防護層,
    #                     數值超過太多或低太多就有可能有問題」
    if enable_sanity_check and result.get("success") and result.get("params"):
        try:
            p = result["params"]
            tool_type_hint = "ball" if (feature_type or "").lower() == "ball" \
                                       or "ball" in (operation or "").lower() \
                             else "square_endmill"
            # L1 用原字串 (preset 對應的工件狀態未知); 其他層用 normalized
            sanity_mat = material_l1 if result.get("layer") == "L1_GOLD" \
                                     else material_norm
            sanity_hrc = None if result.get("layer") == "L1_GOLD" \
                              else hardness_hrc
            check = _gc.sanity_check(
                material=sanity_mat,
                tool_dia=tool_dia,
                rpm_proposed=p.get("rpm", 0),
                feed_proposed=p.get("feed_mm_min", 0),
                tool_type=tool_type_hint,
                hardness_hrc=sanity_hrc,
            )
            result["sanity_check"] = check
            # 若是 L1 結果且 sanity check WARN/BLOCKED → 顯示提示但不覆寫
            # (L1 是用戶實機驗證, 保留尊重; 但要讓用戶知道差距)
            if check["status"] in ("WARN", "BLOCKED"):
                advice = f"⚠ 防護層 ({check['status']}): " + \
                         "; ".join(check.get("warnings", []) + check.get("blocks", []))
                if result["layer"] == "L1_GOLD" and check["status"] == "WARN":
                    advice += "  (L1 為本地實機值, 提示僅供參考)"
                result["sanity_notice"] = advice
        except Exception as e:
            result["sanity_check"] = {"status": "ERROR", "error": str(e)}

    return result


# ─────────────────────────────────────────────────────────────────────
# L1: 本地 preset 查詢
# ─────────────────────────────────────────────────────────────────────

def _try_l1_local_preset(material: str, tool_dia: float, operation: str,
                         feature_type: Optional[str],
                         tool_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """嘗試從本地刀具庫找 preset。"""
    try:
        raw = _tlq.find_preset_for_query(
            material=material,
            diameter_mm=float(tool_dia),
            operation=operation,
            feature_type=feature_type,
            tool_id=tool_id,
        )
    except Exception as e:
        return None
    if not raw:
        return None
    p = raw["params"]
    rpm = p.get("rpm")
    feed = p.get("feed_mm_min")
    if not rpm:
        return None
    return {
        "success": True,
        "layer": "L1_GOLD",
        "confidence": raw["confidence"],
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "operation": operation,
        "params": {
            "rpm": int(rpm),
            "feed_mm_min": (round(float(feed)) if feed else None),
            "Vc_m_min": (round(p["Vc_m_min"], 1) if p.get("Vc_m_min") else None),
            "fz_mm_tooth": (round(p["fz_mm_tooth"], 4) if p.get("fz_mm_tooth") else None),
            "fn_mm_rev": (round(p["fn_mm_rev"], 4) if p.get("fn_mm_rev") else None),
            "ae_mm": p.get("stepover_mm"),
            "ap_mm": p.get("stepdown_mm"),
            "feed_plunge": p.get("feed_plunge"),
            "feed_ramp": p.get("feed_ramp"),
            "ramp_angle_deg": p.get("ramp_angle_deg"),
            "coolant": p.get("coolant"),
        },
        "tool": raw["tool"],
        "source": raw["source"],
        "source_detail": {
            "preset_matched": raw["preset_matched"],
            "match_mode": raw["match_mode"],
            "match_quality": raw["match_quality"],
        },
        "note": raw["note"],
    }


# ─────────────────────────────────────────────────────────────────────
# L2A: GoldCobra 硬車鋼 (gold_cobra_catalog)
# ─────────────────────────────────────────────────────────────────────

# gold_cobra 主戰場: 模具鋼 (硬車+預硬+淬火)
# 注意: S50C/S45C/Cast_Iron 是用戶教學「5 工法心法」的場景, 走 L2C 不走 L2A
_GC_MATERIALS = {
    "SKD11", "SKD11_hardened",
    "SKD61", "SKD61_hardened",
    "NAK80", "HPM38",
    "S136", "S136_hardened",
    "STAVAX", "17-4PH", "DC53", "H13", "D2", "P20", "SK3",
}
_GC_SERIES = {"NXE", "NZB", "R-NM"}

# 用戶有「5 工法心法」的材質 (regular_milling 主戰場, 跳過 L2A)
_RM_PRIORITY_MATERIALS = {
    "S50C", "S45C", "Cast_Iron", "SCM",
    "AL6061", "AL7075", "Brass", "Copper", "Plastics",
}


def _gc_eligible(material: str, series: Optional[str],
                 hardness_hrc: Optional[float]) -> bool:
    """L2A gold_cobra 觸發判定:

    A. series 明確指定 NXE / NZB / R-NM (用戶意圖明確)
    B. HRC ≥ 48 (硬車主戰場, 即使是 S50C 高硬度也走 L2A)
    C. 材質在 _GC_MATERIALS 模具鋼清單 (排除碳鋼+鋁)

    排除規則 (任一觸發即跳過 L2A):
    X1. 材質在 _RM_PRIORITY_MATERIALS 且未指定 series 且 HRC < 48
        → 走 L2C regular_milling
    """
    mat = material or ""
    base_mat = mat.split("_")[0]

    # A. 明確指定 series
    if series and series.upper() in _GC_SERIES:
        return True

    # X1. 用戶有 5 工法心法的材質 + HRC 低 → 直接跳給 L2C
    if (base_mat in _RM_PRIORITY_MATERIALS
            and (hardness_hrc is None or hardness_hrc < 48)):
        return False

    # B. 硬車主戰場
    if hardness_hrc is not None and hardness_hrc >= 48:
        return True

    # C. 模具鋼系列
    if mat in _GC_MATERIALS or base_mat in _GC_MATERIALS:
        return True
    return False


def _try_l2a_gold_cobra(material: str, tool_dia: float,
                        series: Optional[str],
                        feature_type: Optional[str],
                        mode: str,
                        hardness_hrc: Optional[float],
                        cutting_pattern: str) -> Dict[str, Any]:
    """嘗試從 gold_cobra_catalog 找參數。"""
    # 推 tool_type
    fty = (feature_type or "").lower()
    if "ball" in fty or "球" in fty:
        tool_type = "ball"
    elif "thread" in fty or "螺紋" in fty:
        tool_type = "thread_mill"
    else:
        tool_type = "square_endmill"
    try:
        r = _gcc.recommend(
            material=material,
            tool_dia=float(tool_dia),
            series=series,
            tool_type=tool_type,
            hardness_hrc=hardness_hrc,
            spindle_rpm_class=10000,
            mode=mode,
            cutting_pattern=cutting_pattern,
        )
    except Exception as e:
        return {"success": False, "error": f"gold_cobra 例外: {e}"}
    if not r.get("success"):
        return r
    p = r.get("params", {})
    return {
        "success": True,
        "layer": "L2A_SILVER_GC",
        "confidence": 0.78,
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "params": {
            "rpm": p.get("rpm"),
            "feed_mm_min": p.get("feed_mm_min"),
            "Vc_m_min": p.get("Vc_m_min"),
            "fz_mm_tooth": p.get("fz_mm_tooth"),
            "ae_mm": p.get("ae_mm"),
            "ap_mm": p.get("ap_mm"),
            "teeth": p.get("teeth", 4),
            "ae_pct_D": p.get("ae_pct_D"),
            "ap_pct_D": p.get("ap_pct_D"),
        },
        "source": f"GoldCobra {r.get('series', '?')} 系列",
        "source_detail": {
            "vendor": "GoldCobra",
            "series": r.get("series"),
            "band": r.get("band"),
            "cutting_pattern": cutting_pattern,
            "mode": r.get("mode"),
            "rpm_factor": r.get("rpm_factor"),
            "feed_factor": r.get("feed_factor"),
            "sidewall_reference": r.get("sidewall_reference"),
        },
        "note": (r.get("workflow_note") or "")
                + " | GoldCobra 硬車鋼表 (L2A 優先)",
    }


# ─────────────────────────────────────────────────────────────────────
# L2B: 廠商官網表 (奇力揚 keili_catalog) — 原 L2
# ─────────────────────────────────────────────────────────────────────

def _try_l2_vendor_catalog(material: str, tool_dia: float, operation: str,
                           feature_type: Optional[str],
                           teeth: Optional[int], series: Optional[str],
                           mode: str, holder: str,
                           pitch: Optional[float]) -> Dict[str, Any]:
    """嘗試從廠商目錄找切削參數。"""
    # 把 feature_type 映到 keili_catalog 的 operation 鍵
    fty = (feature_type or "").lower()
    if fty in ("hole", "drill", "drilling"):
        kc_op = "drilling"
    elif fty in ("hole_tap", "tap", "tapping"):
        kc_op = "tapping"
    elif fty in ("thread_milling", "thread"):
        kc_op = "thread_milling"
    else:
        kc_op = "milling"
    try:
        result = _kc.recommend_cutting(
            material=material,
            tool_dia=float(tool_dia),
            teeth=teeth,
            series=series,
            operation=kc_op,
            pitch=pitch,
            mode=mode,
            holder=holder,
        )
    except Exception as e:
        return {"success": False, "error": f"keili_catalog 例外: {e}"}

    if not result.get("success"):
        return result
    d = result["data"]
    return {
        "success": True,
        "layer": "L2_SILVER",
        "confidence": 0.75,
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "operation": operation,
        "params": {
            "rpm": d["rpm"],
            "feed_mm_min": d["feed_mm_min"],
            "Vc_m_min": d.get("V_m_min"),
            "fz_mm_tooth": d.get("FZ_mm_tooth"),
            "fn_mm_rev": d.get("fr_mm_rev"),
            "ae_mm": d.get("ae_max_mm"),
            "ap_mm": None,
            "teeth": d.get("teeth"),
        },
        "source": f"{d.get('vendor', '廠商')} {d.get('series', '?')} 系列",
        "source_detail": {
            "vendor": d.get("vendor"),
            "series": d.get("series"),
            "series_name": d.get("series_name"),
            "series_code": d.get("series_code"),
            "material_match_row": d.get("material_match_row"),
            "material_match_zh": d.get("material_match_zh"),
            "formula_used": d.get("formula_used"),
            "mode": d.get("mode"),
            "rpm_factor": d.get("rpm_factor"),
            "feed_factor": d.get("feed_factor"),
            "holder": d.get("holder"),
            "rpm_holder_clamped": d.get("rpm_holder_clamped"),
        },
        "note": d.get("note") or "L2 廠商表查表結果",
    }


# ─────────────────────────────────────────────────────────────────────
# L2C: regular_milling (用戶口傳 5 工法心法 + holder 配對 + chip thinning)
# ─────────────────────────────────────────────────────────────────────

def _try_l2c_regular_milling(material: str, tool_dia: float,
                              rm_op: str, holder: str, coolant: str,
                              teeth: Optional[int],
                              hole_diameter: Optional[float],
                              tool_flute_length: Optional[float],
                              chip_thinning_compensation: float,
                              operation_original: str) -> Dict[str, Any]:
    """嘗試從用戶口傳 5 工法心法計算參數。

    觸發條件: operation/feature_type 對映到 5 工法 (face/side/hole/slot/plunge)
    特色: holder 動態 AP 修正, Chip Thinning 支援, 5 工法各自 Vc/fz 公式
    """
    try:
        r = _rm.recommend(
            material=material,
            tool_dia=float(tool_dia),
            operation=rm_op,
            teeth=teeth,
            holder=holder,
            coolant=coolant,
            tool_flute_length=tool_flute_length,
            hole_diameter=hole_diameter,
            chip_thinning_compensation=chip_thinning_compensation,
        )
    except Exception as e:
        return {"success": False, "error": f"regular_milling 例外: {e}"}
    if not r.get("success"):
        return r
    p = r.get("params", {})
    return {
        "success": True,
        "layer": "L2C_BRONZE_RM",
        "confidence": 0.65,
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "operation": operation_original,
        "params": {
            "rpm": p.get("rpm"),
            "feed_mm_min": p.get("feed_mm_min"),
            "Vc_m_min": p.get("Vc_m_min"),
            "fz_mm_tooth": p.get("fz_program_mm_tooth"),
            "ae_mm": p.get("ae_mm"),
            "ap_mm": p.get("ap_mm"),
            "ae_pct_D": p.get("ae_pct_D"),
            "ap_pct_D": p.get("ap_pct_D"),
            "teeth": p.get("teeth"),
            "MRR_mm3_per_min": p.get("MRR_mm3_per_min"),
            "hex_mm_actual": p.get("hex_mm_actual"),
            "engagement_angle_deg": p.get("engagement_angle_deg"),
            "coolant": coolant,
        },
        "source": "regular_milling (用戶 2026.05 口傳 5 工法)",
        "source_detail": {
            "rm_operation": rm_op,
            "operation_zh": r.get("operation_zh"),
            "holder_advisor": r.get("holder_advisor"),
            "hex_health": r.get("hex_health"),
            "hex_warning": r.get("hex_warning"),
            "chip_thinning": r.get("chip_thinning"),
            "hole_milling_info": r.get("hole_milling_info"),
            "rationale": r.get("rationale"),
            "vc_scale_applied": r.get("vc_scale_applied"),
        },
        "note": r.get("note"),
    }


# ─────────────────────────────────────────────────────────────────────
# L2D: 銘九通用值庫 (general_catalog)
# ─────────────────────────────────────────────────────────────────────

def _try_l2b_general_catalog(material: str, tool_dia: float, operation: str,
                              feature_type: Optional[str],
                              mode: str,
                              hardness_hrc: Optional[float] = None
                              ) -> Dict[str, Any]:
    """嘗試從銘九通用表找切削參數。

    自動依 feature_type/operation 推斷 tool_type:
      ball / ball_mill        → "ball"
      micro_ball / R < 0.5    → "micro_ball"
      含 long / 長刃          → "long"
      其他                     → "square_endmill"
    """
    fty = (feature_type or "").lower()
    op = (operation or "").lower()
    if "micro" in fty or "micro" in op or (tool_dia and tool_dia < 1.0):
        tool_type = "micro_ball"
    elif "ball" in fty or "ball" in op or "球刀" in op:
        tool_type = "ball"
    elif "long" in fty or "long" in op or "長刃" in op:
        tool_type = "long"
    else:
        tool_type = "square_endmill"

    try:
        result = _gc.recommend(
            material=material,
            tool_dia=float(tool_dia),
            tool_type=tool_type,
            mode=mode,
            hardness_hrc=hardness_hrc,
        )
    except Exception as e:
        return {"success": False, "error": f"general_catalog 例外: {e}"}

    if not result.get("success"):
        return result

    # general_catalog 已用統一 "layer": "L2B_AMBER" 格式, 整理欄位給 resolver
    return {
        "success": True,
        "layer": "L2B_AMBER",
        "confidence": result["confidence"],
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "operation": operation,
        "params": result["params"],
        "source": result["source"],
        "source_detail": {
            "vendor": "銘九 Generic",
            "tool_type_resolved": tool_type,
            "route": result["route"],
            "mode": result["mode"],
            "rpm_factor": result["rpm_factor"],
            "feed_factor": result["feed_factor"],
        },
        "note": result["note"],
    }


# ─────────────────────────────────────────────────────────────────────
# L3: 推斷引擎 (machining_heuristics)
# ─────────────────────────────────────────────────────────────────────

def _try_l3_heuristics(material: str, tool_dia: float, operation: str,
                       feature_type: Optional[str],
                       teeth: Optional[int], tool_material: str,
                       mode: str,
                       spindle_kw: float,
                       spindle_rpm_max: int,
                       hardness_hrc: Optional[float] = None
                       ) -> Dict[str, Any]:
    """純物理 + 推斷規則計算 (材質 Vc 上限 × 工法折扣 × 刀具材質係數)。"""
    # 1. 取材質 Vc 上限作為基準
    vc_info = _mh.get_vc_ceiling(material)
    Vc_max = float(vc_info["Vc_ceiling"])

    # 2. 取工法折扣
    op_info = _mh.get_operation_factors(operation)
    Vc = Vc_max * float(op_info["vc_factor"])

    # 3. 套刀具材質係數
    tmf = _mh.get_tool_material_factor(tool_material)
    Vc *= float(tmf["vc_factor"])

    # 4. 套散件折扣 (mode)
    if mode == "conservative":
        Vc *= 0.75  # 散件 75 折
        feed_factor = 0.50
    else:
        feed_factor = 1.00

    # 5. 算 RPM / Feed
    rpm_calc = Vc * 318.3 / float(tool_dia) if tool_dia else 0
    # 預設 fz (依工法 + 材質類別粗估)
    fz_default = _guess_default_fz(material, float(tool_dia),
                                   op_info["operation_key"])
    Z = int(teeth or 4)
    feed_calc = rpm_calc * fz_default * Z * feed_factor

    # 6. 套物理上限 (含材質正規化)
    clamped = _mh.apply_ceilings(material, float(tool_dia),
                                 rpm_calc, feed_calc,
                                 spindle_kw, spindle_rpm_max,
                                 hardness_hrc=hardness_hrc)

    return {
        "success": True,
        "layer": "L3_BRONZE",
        "confidence": 0.55,
        "material": material,
        "tool_dia_mm": float(tool_dia),
        "operation": operation,
        "params": {
            "rpm": clamped["rpm"],
            "feed_mm_min": clamped["feed_mm_min"],
            "Vc_m_min": clamped["Vc_m_min"],
            "fz_mm_tooth": round(fz_default, 4),
            "ae_mm": (round(float(tool_dia) *
                            ((op_info["ae_pct_range"] or [0.3, 0.5])[1]), 2)
                      if op_info.get("ae_pct_range") else None),
            "ap_mm": (round(float(tool_dia) *
                            ((op_info["ap_pct_range"] or [0.3, 0.5])[1]), 2)
                      if op_info.get("ap_pct_range") else None),
            "teeth": Z,
        },
        "source": "推斷引擎 (machining_heuristics)",
        "source_detail": {
            "Vc_material_ceiling": Vc_max,
            "operation_vc_factor": op_info["vc_factor"],
            "operation_fz_factor": op_info["fz_factor"],
            "tool_material": tool_material,
            "tool_material_vc_factor": tmf["vc_factor"],
            "mode": mode,
            "rpm_factor_applied": 0.75 if mode == "conservative" else 1.00,
            "feed_factor_applied": feed_factor,
            "fz_default": fz_default,
        },
        "clamps_applied": clamped["clamps_applied"],
        "note": (f"L3 推斷: {material} Vc上限{Vc_max}×{op_info['vc_factor']}工法"
                 f"×{tmf['vc_factor']}刀材"
                 f"{'×0.75散件' if mode=='conservative' else ''} = {Vc:.1f} m/min "
                 f"→ RPM={clamped['rpm']} F={clamped['feed_mm_min']}"),
    }


def _guess_default_fz(material: str, tool_dia: float, operation_key: str) -> float:
    """L3 用的預設 fz (粗略, 後續可細化)。"""
    is_alu_like = material in ("AL6061", "AL7075", "Brass", "Plastics")
    is_steel = material in ("S50C", "S45C", "Cast_Iron", "SCM440")
    is_hard = material in ("NAK80", "HPM38", "S136", "SKD11", "SKD61", "DC53")
    is_sus = material in ("SUS304", "SUS316", "SUS420", "SUS440")
    is_ti = material in ("Ti-6Al-4V", "TC4")

    # 基準 fz (D=6 銑刀粗加工)
    if is_alu_like:    base = 0.060
    elif is_steel:     base = 0.040
    elif is_hard:      base = 0.025
    elif is_sus:       base = 0.030
    elif is_ti:        base = 0.030
    else:              base = 0.030  # 預設

    # 直徑校正 (大徑 fz 略升, 小徑略降)
    if tool_dia < 4:     base *= 0.5
    elif tool_dia < 6:   base *= 0.75
    elif tool_dia > 12:  base *= 1.3

    # 工法校正 (精銑 fz 大降)
    if "finish" in operation_key or operation_key == "wall_finishing":
        base *= 0.55
    elif operation_key in ("plunge", "helix_ramp"):
        base *= 0.50

    return base


# ─────────────────────────────────────────────────────────────────────
# 共用: 物理上限保險絲 (任何層的結果都跑一次)
# ─────────────────────────────────────────────────────────────────────

def _enrich_with_ceilings(result: Dict[str, Any], material: str,
                          tool_dia: float, spindle_kw: float,
                          spindle_rpm_max: int,
                          hardness_hrc: Optional[float] = None
                          ) -> Dict[str, Any]:
    """L1/L2 結果再過一次物理上限保險絲。"""
    p = result.get("params") or {}
    rpm = p.get("rpm")
    feed = p.get("feed_mm_min")
    if not rpm:
        return result
    clamped = _mh.apply_ceilings(material, float(tool_dia),
                                 float(rpm), float(feed or 0),
                                 spindle_kw, spindle_rpm_max,
                                 hardness_hrc=hardness_hrc)
    # 若被鉗 → 更新; 沒被鉗 → 原值, 但仍記下上限參考
    if clamped["clamps_applied"]:
        result["params"]["rpm"] = clamped["rpm"]
        result["params"]["feed_mm_min"] = clamped["feed_mm_min"]
        result["params"]["Vc_m_min"] = clamped["Vc_m_min"]
        result["clamps_applied"] = clamped["clamps_applied"]
        result["confidence"] = max(0.50, result.get("confidence", 0.7) - 0.10)
        result["note"] = (result.get("note", "") +
                          f" | 物理上限觸發: {'; '.join(clamped['clamps_applied'])}")
    else:
        result["clamps_applied"] = []
        result["physical_limits_reference"] = {
            "Vc_ceiling": clamped["Vc_ceiling_used"],
            "F_ceiling": clamped["F_ceiling_used"],
            "spindle_rpm_max": clamped["spindle_rpm_max"],
        }
    return result


def _miss_result(error: str, fallback_chain: List[str]) -> Dict[str, Any]:
    """強制 layer 失敗時的錯誤結果。"""
    return {
        "success": False,
        "error": error,
        "fallback_chain": fallback_chain,
        "suggestion": "改為 prefer_layer=None 讓自動降級, 或提供更多參數",
    }


# ─────────────────────────────────────────────────────────────────────
# MCP dispatch
# ─────────────────────────────────────────────────────────────────────

def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry point。

    params:
      必填: material, tool_dia
      可選: operation (預設 "side"), feature_type, teeth, series,
            mode (conservative/aggressive), holder, spindle_kw,
            spindle_rpm_max, tool_id, tool_material, pitch, prefer_layer
    """
    material = params.get("material")
    tool_dia = params.get("tool_dia") or params.get("diameter_mm")
    if not material or tool_dia is None:
        return {
            "success": False,
            "error": "需提供 material 與 tool_dia",
            "example": {"material": "AL6061", "tool_dia": 6,
                        "operation": "側銑"},
        }
    try:
        return resolve(
            material=material,
            tool_dia=float(tool_dia),
            operation=params.get("operation") or "side",
            feature_type=params.get("feature_type"),
            teeth=(int(params["teeth"]) if params.get("teeth") else None),
            series=params.get("series"),
            mode=(params.get("mode") or "conservative"),
            holder=(params.get("holder") or "ER"),
            spindle_kw=float(params.get("spindle_kw") or 7.5),
            spindle_rpm_max=int(params.get("spindle_rpm_max") or 12000),
            tool_id=(int(params["tool_id"]) if params.get("tool_id") else None),
            tool_material=(params.get("tool_material") or "Carbide"),
            pitch=(float(params["pitch"]) if params.get("pitch") else None),
            prefer_layer=params.get("prefer_layer"),
            skip_local_preset=bool(params.get("skip_local_preset", False)),
            hardness_hrc=(float(params["hardness_hrc"])
                          if params.get("hardness_hrc") else None),
            enable_sanity_check=bool(
                params.get("enable_sanity_check", True)),
            coolant=(params.get("coolant") or "flood"),
            hole_diameter=(float(params["hole_diameter"])
                           if params.get("hole_diameter") else None),
            tool_flute_length=(float(params["tool_flute_length"])
                               if params.get("tool_flute_length") else None),
            cutting_pattern=(params.get("cutting_pattern") or "sidewall"),
            chip_thinning_compensation=float(
                params.get("chip_thinning_compensation", 0.0)),
        )
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"resolver 例外: {e}",
            "traceback": traceback.format_exc(),
        }
