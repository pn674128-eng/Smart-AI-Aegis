# -*- coding: utf-8 -*-
"""
Structured capability manifest for Fusion AI / external MCP clients (gap audit).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Fusion CAM areas the plugin does NOT target (for gap-audit diff vs full Fusion)
FUSION_CAM_NOT_COVERED: List[Dict[str, str]] = [
    {"area": "5_axis", "note": "未納入模板路徑與 execute 預設流程"},
    {"area": "probing", "note": "無探測工序自動化"},
    {"area": "adaptive_clearing", "note": "API 可建；插件未預設 Adaptive 全自動策略"},
    {"area": "turning", "note": "僅銑削 Setup（MillingOperation）"},
    {"area": "wire_edm", "note": "未支援"},
    {"area": "additive_cam", "note": "未支援"},
    {"area": "nest_sheet", "note": "未支援"},
    {"area": "post_processor_editor", "note": "僅 generateToolpath；後處理不在插件內"},
    {"area": "toolpath_simulation_ui", "note": "可透過 API 觸發；插件未包裝完整模擬 UI 流程"},
    {"area": "machine_connect", "note": "未支援"},
    {"area": "any_operation_without_local_template", "note": "依本機 .f3dhsm 模板庫；無對應 URL 則無法 createFromCAMTemplate"},
]

MCP_ACTIONS: List[Dict[str, Any]] = [
    {"action": "get_cam_agent_manifest", "destructive": False, "needs_document": False,
     "purpose": "回傳插件能力清單（供 Fusion AI 缺口稽核）"},
    {"action": "get_fusion_ai_gap_audit_pack", "destructive": False, "needs_document": False,
     "purpose": "manifest + 學習庫統計 + 稽核提示詞（一鍵給 Assistant）"},
    {"action": "get_addin_info", "destructive": False, "needs_document": False},
    {"action": "scan_machining_features", "destructive": False, "needs_document": True,
     "purpose": "孔/槽/平面/官方口袋/特徵目錄"},
    {"action": "recognize_contour_2d", "destructive": False, "needs_document": True,
     "purpose": "2D 頂面／外輪廓／倒角斜邊辨識 → recommended_templates（可 apply 帶入面板）"},
    {"action": "refresh_vision_snapshot", "destructive": False, "needs_document": True,
     "purpose": "重建 vision_snapshot；params: vision_mode(FAST_2D|FULL_3D), rescan_holes(bool)"},
    {"action": "get_vision_snapshot", "destructive": False, "needs_document": True,
     "purpose": "讀取 runtime vision_snapshot（含 points_3d 與 spherical_scan 診斷）"},
    {"action": "get_ai_recommendations", "destructive": False, "needs_document": True},
    {"action": "get_cam_depth_plan", "destructive": False, "needs_document": True,
     "purpose": "flat_depths → CAM 高度／切深計劃（可 include_ai_tuning）"},
    {"action": "verify_cam_depth_plan", "destructive": False, "needs_document": True,
     "purpose": "MCP 驗收：顶面坯料切深 + AI 建議 + terrace face_depth"},
    {"action": "execute_machining_plan", "destructive": True, "needs_document": True},
    {"action": "auto_create_cam_setup", "destructive": True, "needs_document": True},
    {"action": "get_machining_report", "destructive": False, "needs_document": True},
    {"action": "verify_tool_library", "destructive": False, "needs_document": True},
    {"action": "run_intuitive_one_click", "destructive": True, "needs_document": True},
    {"action": "run_intuitive_programming", "destructive": True, "needs_document": True},
    {"action": "check_intuitive_eligibility", "destructive": False, "needs_document": True},
    {"action": "run_thinking_programming", "destructive": True, "needs_document": True,
     "purpose": "L0/L1/L2 thinking; L2 supports resume_from_sequence=2 after flip"},
    {"action": "get_multi_setup_plan", "destructive": False, "needs_document": False,
     "purpose": "Read cached L2 dual-Setup script JSON"},
    {"action": "check_thinking_eligibility", "destructive": False, "needs_document": True},
    {"action": "get_thinking_layers", "destructive": False, "needs_document": False},
    {"action": "run_internal_ai_autopilot", "destructive": True, "needs_document": True},
    {"action": "import_cam_from_active_document", "destructive": False, "needs_document": True},
    {"action": "batch_import_reference_library", "destructive": False, "needs_document": False},
    {"action": "scan_reference_library", "destructive": False, "needs_document": False},
    {"action": "list_reference_f3z", "destructive": False, "needs_document": False},
    {"action": "list_reference_files", "destructive": False, "needs_document": False},
    {"action": "knowledge_stats", "destructive": False, "needs_document": False},
    {"action": "knowledge_query", "destructive": False, "needs_document": False},
    {"action": "knowledge_feedback", "destructive": False, "needs_document": False},
    {"action": "knowledge_export", "destructive": False, "needs_document": False},
    {"action": "knowledge_import", "destructive": False, "needs_document": False},
    {"action": "knowledge_rebuild_index", "destructive": False, "needs_document": False},
    {"action": "knowledge_merge_duplicates", "destructive": False, "needs_document": False},
    {"action": "knowledge_resolve_templates", "destructive": False, "needs_document": False},
    {"action": "get_knowledge_stats", "destructive": False, "needs_document": False},
    {"action": "query_best_template", "destructive": False, "needs_document": False},
    {"action": "query_all_recommendations", "destructive": False, "needs_document": False},
    {"action": "execute_python_code", "destructive": True, "needs_document": False,
     "purpose": "除錯用；稽核時不建議 Fusion AI 任意執行"},

    # ─────────────────────────────────────────────────────────────────
    # ★ 智能切削參數 6 層解析器 (cutting_resolver) — 主入口
    # ─────────────────────────────────────────────────────────────────
    {"action": "query_smart_cutting", "destructive": False, "needs_document": False,
     "purpose": ("★主入口★ 6 層解析: L1 本地 preset > L2A GoldCobra (HRC≥48) "
                 "> L2B 用戶 5 工法 (regular_milling) > L2C 奇力揚 > L2D 銘九 "
                 "> L3 推斷. 必填 material/tool_dia, 可選 operation/holder/coolant/"
                 "hardness_hrc/hole_diameter/cutting_pattern/chip_thinning_compensation")},
    {"action": "query_regular_milling", "destructive": False, "needs_document": False,
     "purpose": ("用戶口傳 5 工法 (face/side/hole/slot/plunge) + 8 種刀把 "
                 "+ Chip Thinning. mode: recommend / list_profiles / list_holders "
                 "/ recommend_holder / compute_hex / fz_for_hex")},
    {"action": "query_gold_cobra", "destructive": False, "needs_document": False,
     "purpose": ("GoldCobra 硬車鋼 (NXE/NZB/R-NM) + 4 硬度區 + 側壁⇔平面 /2 對調. "
                 "mode: recommend / list_series / list_bands / convert_apae")},
    {"action": "query_general_catalog", "destructive": False, "needs_document": False,
     "purpose": ("銘九通用切削表 (鋁/銅/淬火鋼平刀+球刀+長刃+微徑) + sanity_check "
                 "防護層. mode: recommend / sanity_check / list_routes")},
    {"action": "query_heuristics", "destructive": False, "needs_document": False,
     "purpose": ("推斷引擎 + 物理上限 (machining_heuristics). mode: list_rules "
                 "/ operation_factors / vc_ceiling / feed_ceiling / substitute "
                 "/ apply_ceilings / derive / estimate_tool_geometry")},
    {"action": "query_tool_holders", "destructive": False, "needs_document": False,
     "purpose": "刀把規格 / RPM 軟上限 (ER/SK/後拉式/熱縮/油壓/側固/SK/...)"},
]

FEATURE_RECOGNITION: List[Dict[str, Any]] = [
    {"category": "hole", "sources": ["B-rep 射線", "RecognizedHoleGroup（需 ME）"],
     "template_keys": ["generalHole", "tapHole", "locatingHole", "countersinkHole", "holeChamfer"],
     "geometry_index": ["diameter_mm", "hole_type"]},
    {"category": "slot", "sources": ["開口面 B-rep"],
     "template_keys": ["slotHole"], "geometry_index": ["width_mm"]},
    {"category": "pocket_corner_r", "sources": ["槽角 R 圓柱"],
     "template_keys": ["generalHole"], "geometry_index": ["diameter_mm as 2R"]},
    {"category": "face_plane", "sources": ["朝上平面叢集", "flat_depths"],
     "template_keys": ["topFaceRough", "topFaceFinish"], "geometry_index": ["material only"]},
    {"category": "outer_contour", "sources": ["外輪廓 WCS", "contour_2d_recognizer"],
     "template_keys": ["profileRough", "profileFinish"], "geometry_index": ["material only"]},
    {"category": "chamfer_bevel", "sources": ["斜邊"],
     "template_keys": ["holeChamfer", "contourChamfer"], "geometry_index": ["diameter_mm", "chamfer_tag"]},
    {"category": "official_pocket", "sources": ["RecognizedPocket（需 ME）"],
     "template_keys": ["slotHole"], "notes": "腰形 vs 封闭口袋；2D/3D 綁定"},
]

FUSION_API_USED: List[str] = [
    "adsk.fusion Design B-rep (faces, edges, bodies)",
    "adsk.cam setups.add (MillingOperation)",
    "adsk.cam operations via createFromCAMTemplate + template library URL",
    "adsk.cam generateToolpath",
    "Manufacturing: recognize holes/pockets (optional, extension)",
    "CustomEvent + palette HTML (UI)",
    "TCP localhost MCP bridge (port 9877)",
]

GAP_AUDIT_PROMPT_ZH = """你是 Autodesk Fusion 的 CAM／API 專家。請比對以下兩份資料：

【A】Smart_AI_CAM 插件能力清單（來自 MCP get_cam_agent_manifest / get_fusion_ai_gap_audit_pack 的 JSON）
【B】你所知的 Fusion 360 Manufacture／CAM API 與 Assistant Script Execute 可涵蓋的能力

請輸出繁體中文報告，結構如下：
1. **插件已覆蓋且合理**：列出與 Fusion 標準流程對齊的部分
2. **Fusion 有、插件明確未做**：對照 manifest 的 fusion_cam_not_covered 與你的知識，補充遺漏項
3. **插件有、但 Fusion 原生較弱或需 ME**：例如 RecognizedPocket、學習庫
4. **建議優先補強 TOP 5**：依「常用銑削件」優先級排序，每項一句理由
5. **MCP 可驗證項**：建議用哪個 action 在實機驗證（勿建議任意 execute_python_code）

限制：插件材質預設 AL6061/S50C；工序以本機 .f3dhsm 模板為主；勿假設插件已支援五軸／車削／探測。
"""


def build_agent_manifest(
    *,
    addin_version: str = "V2.0358",
    addin_dir: Optional[str] = None,
    mcp_port: int = 9877,
    live_stats: Optional[dict] = None,
) -> Dict[str, Any]:
    """Machine-readable manifest for gap audit."""
    adir = addin_dir or ""
    docs = [
        "docs/CAM_FEATURE_RECOGNITION_MAP.md",
        "docs/AI_SYSTEM_ARCHITECTURE.md",
        "docs/PROGRAMMING_MODES.md",
        "docs/F3Z_LEARNING.md",
    ]
    return {
        "plugin": {
            "name": "Smart AI CAM Fusion",
            "name_legacy": "Smart_AI_CAM",
            "version": addin_version,
            "role": "半自動 CAM：B-rep/官方辨識 → 模板工序 → 學習庫建議",
            "materials_supported": ["AL6061", "S50C"],
            "programming_modes": [
                "panel_manual",
                "ai_recommendations_apply",
                "intuitive_restricted",
                "thinking_L0",
                "imported_f3z_learning",
            ],
            "mcp": {"host": "127.0.0.1", "port": mcp_port, "protocol": "json line per request"},
            "addin_dir": adir,
            "doc_paths_relative": docs,
        },
        "feature_recognition": FEATURE_RECOGNITION,
        "template_library": {
            "source": "本機資料夾 .f3dhsm（TEMPLATE_FOLDER_PATHS）",
            "fields_per_item": ["name", "url", "hasDrill", "drillUrl", "chamferUrl", "toolDia", "cycleType"],
            "resolver": "template_resolver（名稱→URL）",
            "params_snapshot": "getTemplateParams（少數欄位：底面高度、pitch 等）",
        },
        "knowledge_db": {
            "path": "knowledge/feature_records.json",
            "feature_types": ["hole", "slot", "face", "profile", "chamfer"],
            "query_keys": "見 knowledge_db._feature_key",
            "live_stats": live_stats,
        },
        "mcp_actions": MCP_ACTIONS,
        "fusion_api_used": FUSION_API_USED,
        "fusion_cam_not_covered": FUSION_CAM_NOT_COVERED,
        "known_limitations": [
            "官方孔/口袋 API 需 Manufacturing Extension；失敗時回退 B-rep",
            "思考式 L2 多 Setup 已實作（Setup1 後需人工翻面再 resume）",
            "UI 未顯示 knowledge_confidence / reason（後端已有）",
            "參考 f3z 匯入時 template_path 常空，靠工序名與 resolver",
            "Autodesk Assistant 無直接呼叫 Add-In 的 API；需 MCP 橋接腳本",
        ],
        "gap_audit": {
            "purpose": "供 Fusion AI 與 Fusion 原生 CAM 能力對照",
            "recommended_mcp_sequence": [
                "get_fusion_ai_gap_audit_pack",
                "get_addin_info",
                "scan_machining_features",
                "get_ai_recommendations",
            ],
            "assistant_prompt_zh": GAP_AUDIT_PROMPT_ZH,
        },
    }


def build_gap_audit_pack(
    *,
    addin_version: str = "V2.0358",
    addin_dir: Optional[str] = None,
    include_live_knowledge: bool = True,
) -> Dict[str, Any]:
    live = None
    if include_live_knowledge:
        try:
            from Smart_AI.memory.knowledge_db import get_db

            live = get_db().get_statistics()
        except Exception as ex:
            live = {"error": str(ex)}
    manifest = build_agent_manifest(
        addin_version=addin_version,
        addin_dir=addin_dir,
        live_stats=live,
    )
    return {
        "manifest": manifest,
        "assistant_prompt_zh": GAP_AUDIT_PROMPT_ZH,
        "how_to_use_with_fusion_ai": [
            "1. Fusion 中載入 Smart_AI_CAM 增益集",
            "2. 在 Fusion 文字指令或 Assistant Script Execute 執行 scripts/fusion_ai_bridge.py",
            "3. 呼叫 cam_call('get_fusion_ai_gap_audit_pack')",
            "4. 將回傳 JSON 貼給 Autodesk Assistant，並貼上 assistant_prompt_zh",
            "5. 請 Assistant 產出缺口報告（勿直接執行 execute_machining_plan）",
        ],
    }
