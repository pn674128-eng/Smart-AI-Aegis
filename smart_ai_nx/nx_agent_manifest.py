# -*- coding: utf-8 -*-
"""MCP manifest — mirrors Fusion Smart_AI_CAM actions (NX1953 platform)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config import ADDIN_VERSION, MCP_PORT, PKG_DIR, FUSION_ADDIN_DIR, STORE_DIR
from .material_profiles import list_profiles

# implementation: live | bridge | stub | store
MCP_ACTIONS: List[Dict[str, Any]] = [
    {"action": "get_cam_agent_manifest", "impl": "live", "needs_nx": False,
     "purpose": "NX 能力清單（對照 Fusion manifest）"},
    {"action": "get_addin_info", "impl": "live", "needs_nx": False},
    {"action": "nx_library_status", "impl": "live", "needs_nx": False,
     "purpose": "公司 cut_methods / feeds_speeds 路徑狀態"},
    {"action": "list_material_profiles", "impl": "live", "needs_nx": False,
     "purpose": "碳鋼 / 鋁材 / 高硬度 三類 PRT"},
    {"action": "nx_recommend_cut_method", "impl": "live", "needs_nx": False,
     "purpose": "material_profile + rough|semi|finish → HSM 工法名"},
    {"action": "query_smart_cutting", "impl": "bridge", "needs_nx": False,
     "purpose": "6 層 resolver（唯讀 Fusion 模組）"},
    {"action": "query_regular_milling", "impl": "bridge", "needs_nx": False},
    {"action": "query_gold_cobra", "impl": "bridge", "needs_nx": False},
    {"action": "query_general_catalog", "impl": "bridge", "needs_nx": False},
    {"action": "query_heuristics", "impl": "bridge", "needs_nx": False},
    {"action": "query_tool_holders", "impl": "bridge", "needs_nx": False},
    {"action": "cad_submit_features", "impl": "store", "needs_nx": False,
     "purpose": "上傳特徵至 Ollama store（僅經 Aegis）"},
    {"action": "cam_get_features", "impl": "store", "needs_nx": False},
    {"action": "cam_submit_machining", "impl": "store", "needs_nx": False},
    {"action": "cad_get_machining", "impl": "store", "needs_nx": False},
    {"action": "check_semi_auto_eligibility", "impl": "live", "needs_nx": False},
    {"action": "get_semi_auto_plan", "impl": "live", "needs_nx": False,
     "purpose": "半自動劇本：hole_rules + oper_templates → nx_operations"},
    {"action": "nx_hole_cam_catalog", "impl": "live", "needs_nx": False,
     "purpose": "列出孔/槽/面規則與 UG 模板鍵（參照星空資料驅動）"},
    {"action": "nx_match_feature_cam", "impl": "live", "needs_nx": False,
     "purpose": "單一特徵匹配規則並展開工序"},
    {"action": "get_plugin_config", "impl": "live", "needs_nx": False,
     "purpose": "外掛全域設定 plugin_config.yaml"},
    {"action": "scan_machining_features", "impl": "bridge_nx", "needs_nx": True,
     "purpose": "NX Open 掃描（需 NX 執行 journal）"},
    {"action": "run_semi_auto_programming", "impl": "stub", "needs_nx": True,
     "purpose": "建立工序 — 下一階段接 UG 工法"},
    {"action": "run_thinking_programming", "impl": "stub", "needs_nx": True},
    {"action": "nx_bridge_status", "impl": "live", "needs_nx": False},
]

NX_FEATURE_RECOGNITION: List[Dict[str, str]] = [
    {"category": "hole", "nx_note": "鑽/鉸/攻 — 特徵身分 HOLE_*"},
    {"category": "threaded_hole", "nx_note": "攻牙/螺紋銑"},
    {"category": "slot", "nx_note": "槽 — pocket/slot 工法"},
    {"category": "face_plane", "nx_note": "平面粗精 — HSM ROUGH/FINISH"},
    {"category": "surface_shoe", "nx_note": "鞋面 — UG 曲面工法（優勢區）"},
]


def build_agent_manifest() -> Dict[str, Any]:
    return {
        "platform": "NX1953",
        "product": "Smart AI CAM-NX",
        "version": ADDIN_VERSION,
        "mcp_host": "127.0.0.1",
        "mcp_port": MCP_PORT,
        "package_dir": str(PKG_DIR),
        "store_dir": str(STORE_DIR),
        "fusion_addin_readonly": str(FUSION_ADDIN_DIR),
        "material_profiles": list_profiles(),
        "mcp_actions": MCP_ACTIONS,
        "feature_recognition": NX_FEATURE_RECOGNITION,
        "architecture": {
            "trunk": "Smart_AI_CAM",
            "trunk_ui": "Fusion palette.html + MCP 9877",
            "reference": "StarCAM_QuickCAM_V8702",
            "reference_data": ["hole_type.txt", "oper_type_new.txt", "config.ini"],
            "nx_ui": "ui/nx_palette.html @ :9879",
            "doc": "docs/MASTER_ARCHITECTURE.md",
        },
        "philosophy": [
            "主幹 Smart AI CAM：UI 流程 + MCP 契約 + 6 層切削",
            "參照 V8.702：hole/oper 規則表結構（自有 YAML）",
            "上傳只經 Ollama store",
            "孔身分快篩 + 特徵身分 → UG 工法",
        ],
        "data_layout": {
            "hole_rules": "data/hole_cam/hole_rules.yaml",
            "oper_templates": "data/hole_cam/oper_templates.yaml",
            "schemes": "data/schemes/*.yaml",
        },
    }
