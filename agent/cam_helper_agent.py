# -*- coding: utf-8 -*-
"""
Smart AI Aegis Agent — Ollama + Smart AI CAM Fusion MCP (127.0.0.1:9877) tool calling.

v2 升級重點:
    * Streaming 輸出（邊生成邊印，UX 大幅改善）
    * 多輪對話記憶（REPL 維持 messages 歷史）
    * 三種 tool_call 格式 fallback（標準 / JSON 嵌入 / [tool_call: xxx] 文字）
    * 彩色 ANSI 輸出（Win10+ 自動支援）
    * 自動重試 Ollama 暫時斷線
    * REPL 指令:
        :q          退出
        :v          切 verbose
        :tools      列出 MCP 工具
        :reset      清空對話歷史
        :save FILE  存對話到檔
        :stream     切 streaming on/off
        :help       顯示說明

執行：
    python scripts\\cam_helper_agent.py
    （啟動互動式 REPL；輸入 :q 或 Ctrl+C 結束）

也可單次提問：
    python scripts\\cam_helper_agent.py "學習庫現在幾筆？"

前提：
    1. Ollama 在 127.0.0.1:11434 跑著 cam-helper 模型
    2. Fusion 360 已載入 Smart AI CAM Fusion（MCP 9877，見 Smart_AI_CAM/DEPLOY_FUSION.md）
       — 若 MCP 離線，Agent 仍會回應，但會明確標示「離線」
    3. NX 1953：先執行 Start-Smart-AI-NX-MCP.bat（MCP 9878）
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
from typing import Any, Dict, List, Optional, Iterator, Tuple

import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Win10+ enable ANSI escape (no-op on Linux/Mac)
if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# ---------- 設定 ----------

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_ROOT = os.path.dirname(_AGENT_DIR)
if _TOOLS_ROOT not in sys.path:
    sys.path.insert(0, _TOOLS_ROOT)

import knowledge_service as _knowledge_service  # noqa: E402

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
try:
    from aegis_paths import default_ollama_model, CAD_MCP_HOST, CAD_MCP_PORT

    MODEL = default_ollama_model()
except ImportError:
    MODEL = os.environ.get(
        "AEGIS_MODEL",
        os.environ.get("CAM_HELPER_MODEL", "smart-ai-aegis"),
    )
    CAD_MCP_HOST = os.environ.get("CAD_MCP_HOST", "127.0.0.1")
    CAD_MCP_PORT = int(os.environ.get("CAD_MCP_PORT", "9876"))
MCP_HOST = os.environ.get("CAM_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("CAM_MCP_PORT", "9877"))
NX_MCP_HOST = os.environ.get("NX_MCP_HOST", "127.0.0.1")
NX_MCP_PORT = int(os.environ.get("NX_MCP_PORT", "9878"))
MAX_TOOL_ROUNDS = 5
MAX_TOOL_RESULT_CHARS = 4000
HTTP_TIMEOUT = 180
RETRY_OLLAMA = 2  # Ollama 連線失敗自動重試次數

# ---------- 顏色 ----------

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    GRAY    = "\033[90m"

def _color(txt: str, c: str) -> str:
    if not sys.stdout.isatty():
        return txt
    return f"{c}{txt}{C.RESET}"


# ---------- MCP Tools 定義 ----------

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_stats",
            "description": "查 Smart AI CAM Fusion 學習庫統計（總筆數、按材質/特徵類型分布）。優先讀 Ollama 本機 mirror；不需開啟 Fusion 文件。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_query",
            "description": "查特定特徵的歷史模板紀錄。不需開啟 Fusion 文件。當使用者要查『AL6061 上 M8 攻牙的歷史』『某直徑某材質的記錄』時用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_type": {
                        "type": "string",
                        "description": "特徵類型，可選: hole / slot / face_plane / outer_contour / chamfer_bevel / pocket_corner_r / official_pocket",
                    },
                    "material": {
                        "type": "string",
                        "description": "材質，常見: AL6061, S50C",
                    },
                    "geometry": {
                        "type": "object",
                        "description": "幾何參數（可選），例: {\"diameter_mm\":8.0,\"hole_type\":\"tap\"}",
                    },
                },
                "required": ["feature_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_addin_info",
            "description": "查 Smart_AI_CAM 版號、當前 Setup 狀態、坯料尺寸等系統資訊。不需文件但有文件時資訊更完整。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cam_agent_manifest",
            "description": "查插件能力清單（支援的特徵類型、MCP actions、模板路徑鍵）。不需開啟 Fusion 文件。當使用者問『插件能做什麼』『有哪些功能』時用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reference_f3z",
            "description": "列出可匯入學習的 .f3z 樣本檔（E:\\Fusion\\參考範本\\f3z已編程）。不需開啟 Fusion 文件。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_machining_features",
            "description": "掃描當前 Fusion 文件，回傳完整 feature_catalog（孔、槽、外輪廓、平面、倒角等）。**需要開啟 Fusion 文件**。當使用者問當前模型有什麼特徵、辨識結果時用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material": {
                        "type": "string",
                        "description": "材質，預設由 Setup 決定；可指定 AL6061 / S50C",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ai_recommendations",
            "description": "對當前文件取得 AI 完整方案（decisions + panel_apply + recommended_templates）。**需要開啟 Fusion 文件**。當使用者要 AI 建議參數/模板時用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_material_properties",
            "description": "★ 查 Smart_AI_CAM 材質資料庫的「物性參數」（不做計算，只查資料）。回傳：密度 g/cm³、基準切削速度 base_vc、基準每齒進給 base_fz、比切削能、硬度 HB、特殊衰減係數 extra_damping、特性描述。**僅當用戶單純問材質物性（密度多少？硬度多少？特性？）時用**。若用戶要算 RPM/Feed 一定要改用 calculate_cutting_params 而不是這個 tool。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material": {
                        "type": "string",
                        "description": "材質鍵: AL6061 / S50C / SUS304 / Brass / Plastics。不填則回傳全部 5 種",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_tool_library",
            "description": "★ 查 Fusion 360 本地刀具庫 (150 把刀，分 10 類：HSS鑽頭/SG鑽頭/鎢鋼鑽頭/絞刀/鋁用端銑刀(ALUS)/鋼用端銑刀(CIB)/面銑刀/中心鑽/倒角刀/球刀)。支援 3 種模式：(1) stats: 總覽，回傳各分類數量+材質分布+直徑分布 (2) list: 列舉特定分類所有刀 (3) search: 依直徑/類別/適用材質/刃數搜尋。**用戶問「我有哪些刀？」「刀具庫多少把？」「列出所有 D8 刀」時用此 tool**。要算 RPM/F 或推薦最佳刀則改用 find_tool_for_job。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "stats (總覽) / list (列分類) / search (條件搜尋)，預設 stats",
                    },
                    "category": {
                        "type": "string",
                        "description": "分類鍵: end_mill_alu 鋁用端銑刀 / end_mill_steel 鋼用端銑刀 / drill_hss / drill_sg / drill_carbide / face_mill / reamer / chamfer / center_drill / ball_mill / bull_nose",
                    },
                    "diameter_mm": {
                        "type": "number",
                        "description": "刀徑 mm (search 用)",
                    },
                    "material_target": {
                        "type": "string",
                        "description": "適用工件材質 (search 用): AL6061/S50C/SUS304/Brass/Plastics/SKD11/S45C",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多回傳幾把 (預設 30)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_tool_for_job",
            "description": "★★★ 給「加工需求」自動找最適合的真實刀具（從本地 150 把刀挑）。會自動匹配 ALUS 鋁用標籤 / CIB 鋼用標籤，避免推薦鋁刀切鋼料的錯誤。回傳排序後的最佳刀 + 替代刀清單，含真實 T 刀號、刀徑、刃數、避空長度、廠商、產品 ID。**用戶問「S50C 銑外輪廓 D6 用哪把刀」「AL6061 鑽 D5 推薦」「我這個工件用什麼刀」時必用此 tool**。回傳的 T 號可直接用在 G-code (T## M06)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_type": {
                        "type": "string",
                        "description": "★必填★ 加工類型: hole (鑽孔) / hole_tap (攻牙) / hole_ream (絞孔) / center (中心鑽) / face (面銑) / contour (外輪廓) / pocket (口袋) / chamfer (倒角) / slot (槽) / ball (球面)",
                    },
                    "material_target": {
                        "type": "string",
                        "description": "★必填★ 工件材質: AL6061 / S50C / SUS304 / Brass / Plastics / SKD11 / S45C / AL7075",
                    },
                    "diameter_mm": {
                        "type": "number",
                        "description": "希望的刀徑 mm (例: D5 鑽孔→5, D6 銑→6)。攻牙時填底孔徑",
                    },
                    "diameter_tolerance": {
                        "type": "number",
                        "description": "刀徑容差 mm (預設 0.5)。給寬一點可找到更多候選",
                    },
                    "required_reach_mm": {
                        "type": "number",
                        "description": "工件加工深度 mm，用來檢查避空長度是否足夠（避免撞刀）",
                    },
                },
                "required": ["feature_type", "material_target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_keili_cutting",
            "description": "★★★★★ **預設切削參數 tool**。任何用戶問 RPM / Feed / 轉速 / 進給 / 切削參數 / 銑 / 鑽 / 攻牙 / 銑牙 + 材質+刀徑，**第一優先呼叫此 tool**，不是 calculate_cutting_params。整合 3 家廠商 6 系列實機數據，比物理引擎準 1.25-3.39 倍且涵蓋更廣。\n自動依 operation 分流:\n• operation=milling (預設, 銑削) → 奇力揚 CLUS鋁 / CIB鋼 / CAVN不鏽鋼鈦合金\n• operation=drilling (鑽孔) → OSG SG 高速鋼鑽頭 (S50C/AL6061, D1-D11.8)\n• operation=tapping (攻牙) → TOPMS CH01M (M2-M24, F=S×pitch 同步)\n• operation=thread_milling (銑牙) → 奇力揚 CFSL (M3-M27)\n★ calculate_cutting_params 只在此 tool 回傳 error '未收錄' 才用 (fallback)。\n★ 不要因為用戶沒明確提「廠商」就跳過此 tool, 預設就用。\n回傳 vendor + series_code (奇力揚SKU) + rpm + feed_mm_min 是最終答案, 直接告訴用戶。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material": {
                        "type": "string",
                        "description": "★必填★ 材質鍵: AL6061/AL7075/S45C/S50C/SUS304/NAK80/SKD11/Ti-6Al-4V/Brass/Plastics/Cast_Iron",
                    },
                    "tool_dia": {
                        "type": "number",
                        "description": "★必填★ 刀徑 mm (攻牙時=螺紋外徑, 例如 M6→6)",
                    },
                    "operation": {
                        "type": "string",
                        "description": "操作型: milling(預設, 銑) / drilling(鑽) / tapping(攻牙) / thread_milling(銑牙)",
                    },
                    "teeth": {
                        "type": "integer",
                        "description": "刃數 (預設用系列預設: CIB=4, CAVN=4, CLUS=3, CFSL 從刀表取, 鑽/攻牙不需)",
                    },
                    "pitch": {
                        "type": "number",
                        "description": "螺距 mm (攻牙/銑牙時填, 例 M6x1.0→1.0)",
                    },
                    "series": {
                        "type": "string",
                        "description": "強制指定系列 CIB/CAVN/CLUS/CFSL/CH01M/SG (預設依 operation+material 自動選)",
                    },
                    "use_max": {
                        "type": "boolean",
                        "description": "true=取 V/FZ 範圍上限(積極) / false=取中位/保守值(預設)",
                    },
                },
                "required": ["material", "tool_dia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_keili_catalog",
            "description": "★ 查廠商目錄系列總覽或某系列詳細。mode=list_series 列全部 6 系列 (CIB/CAVN/CLUS 銑、CFSL 銑牙、CH01M 攻牙、SG 鑽頭) / mode=get_series series=X 看某系列完整資料 / mode=list_tools series=X diameter_mm=6 找特定刀具型號。用戶問「奇力揚有什麼系列」「CLUS 系列有什麼特色」「SG 鑽頭 D6 規格」時用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "list_series (全 6 系列總覽) / get_series (單系列) / list_tools (列刀具)",
                    },
                    "series": {
                        "type": "string",
                        "description": "CIB / CAVN / CLUS / CFSL / CH01M / SG",
                    },
                    "diameter_mm": {
                        "type": "number",
                        "description": "刀徑 mm (list_tools 用，過濾特定刀徑)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_cutting_params",
            "description": "★ **僅限 fallback** - Smart_AI_CAM 物理引擎切削參數計算。**只有當 recommend_keili_cutting 回傳 error '未收錄此材質/操作' 時才用此 tool**。物理引擎較保守且有侷限: 銑刀偏保守 1/2-1/3 廠商實機值, 鑽 AL6061 偏激進 4x 危險, 只覆蓋 5 種材質 (AL6061/S50C/SUS304/Brass/Plastics)。如果用戶問 RPM/Feed 切削參數, **第一步應該是呼叫 recommend_keili_cutting**, 不是這個 tool。回傳 rpm/feed_mm_min 是計算結果直接呈現給用戶。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material": {
                        "type": "string",
                        "description": "★必填★ 材質鍵: AL6061 / S50C / SUS304 / Brass / Plastics",
                    },
                    "tool_dia": {
                        "type": "number",
                        "description": "★必填★ 刀具直徑 mm (例: D5→5, D6→6, D8→8, D10→10)。攻牙時填底孔直徑 (M5=4.2, M6=5.0, M8=6.8, M10=8.5)",
                    },
                    "teeth": {
                        "type": "integer",
                        "description": "刀刃數 (預設 4)。常見: 端銑刀 2-4 刃, 鑽頭固定 2, 攻牙刀 4",
                    },
                    "is_drill": {
                        "type": "boolean",
                        "description": "是否為鑽孔 (預設 false)。鑽孔 true → 自動 vc×0.75, fz×0.85, Z=2",
                    },
                    "is_tap": {
                        "type": "boolean",
                        "description": "是否為攻牙 (預設 false)。攻牙 true → 自動 vc×0.30, F=N×pitch",
                    },
                    "pitch": {
                        "type": "number",
                        "description": "攻牙螺距 mm (is_tap=true 時必填)。M3=0.5, M4=0.7, M5=0.8, M6=1.0, M8=1.25, M10=1.5",
                    },
                },
                "required": ["material", "tool_dia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nx_get_manifest",
            "description": "Smart AI CAM-NX (UG/NX1953) 能力清單。不需 Fusion。需 NX MCP 9878 在線。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nx_list_material_profiles",
            "description": "列出 NX 三類 PRT：carbon_steel / aluminum / high_hardness。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nx_query_smart_cutting",
            "description": "NX 版 6 層切削解析。material_profile 用 carbon_steel|aluminum|high_hardness；或 material+tool_dia+operation。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_profile": {"type": "string"},
                    "material": {"type": "string"},
                    "tool_dia": {"type": "number"},
                    "operation": {"type": "string"},
                    "holder": {"type": "string"},
                },
                "required": ["tool_dia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nx_semi_auto_plan",
            "description": "NX 半自動編程劇本：特徵陣列 + material_profile → matched_rule + nx_operations (UG template) + 特徵身分。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_profile": {"type": "string"},
                    "scheme_id": {"type": "string", "description": "加工方案，預設 default_part_milling"},
                    "drawing_no": {"type": "string"},
                    "features": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "例 hole: {category,hole,diameter_mm,through,tolerance}",
                    },
                },
                "required": ["material_profile", "features"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nx_hole_cam_catalog",
            "description": "列出 Smart AI NX 孔/槽/面規則與 oper_templates 鍵（參照星空資料驅動，自有 YAML）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_create_ticket",
            "description": "★三方校準★ 建立協作單（Antigravity 探索 / Cursor 收斂 / Aegis 裁決）。用戶要改插件、校準主腦、架構變更時必用。回傳 ticket_id；告知師父到 Cursor 處理該 ticket。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "一句話任務摘要"},
                    "type": {
                        "type": "string",
                        "description": "plugin_change | schema | quote_tuning | bridge_mapping | calibration | general",
                    },
                    "owner": {
                        "type": "string",
                        "description": "預設 cursor；探索階段可 antigravity",
                    },
                    "priority": {"type": "string", "description": "low | normal | high"},
                    "theory_from_user": {
                        "type": "string",
                        "description": "師父口述的理論/原則（Aegis 只記錄，拆解交 AI 協作）",
                    },
                    "payload": {"type": "object", "description": "額外結構化需求"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_watch_tickets",
            "description": "輪詢協作單變更（Cursor/Antigravity 更新後 Aegis 可讀）。since_rev 用上次 cursor_rev。",
            "parameters": {
                "type": "object",
                "properties": {
                    "since_rev": {"type": "integer"},
                    "status": {"type": "string"},
                    "include_events": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_get_ticket",
            "description": "取得單一協作單完整內容（含 events、rev）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                },
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_append_context",
            "description": "更新協作單（必帶 if_match_rev）。Aegis 核准時 patch.core_approved=true。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "if_match_rev": {"type": "integer"},
                    "by": {"type": "string", "description": "aegis | cursor | antigravity"},
                    "patch": {"type": "object", "description": "status, reply, core_approved, payload, artifacts"},
                },
                "required": ["ticket_id", "if_match_rev", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_resolve_ticket",
            "description": "結案協作單。★僅在 core_approved=true 後★ 且 if_match_rev 正確。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "if_match_rev": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "required": ["ticket_id", "if_match_rev"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_add_discussion",
            "description": "三方協作討論串：追加一輪發言。by=aegis|cursor|antigravity|master。role=explore|converge|facilitate|theory|challenge。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "by": {"type": "string"},
                    "role": {"type": "string"},
                    "content": {"type": "string"},
                    "if_match_rev": {"type": "integer"},
                },
                "required": ["ticket_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_get_discussion",
            "description": "讀取協作單完整討論串與各方發言次數。師父說「協作進度」「繼續討論」時必用。",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_collab_status",
            "description": "檢查協作是否達「三方皆已發言、可綜述結論」。",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assist_propose_conclusion",
            "description": "★三方對話完成後★ Aegis 綜述結論草案。缺任一方發言會 409。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "conclusion": {"type": "string"},
                    "if_match_rev": {"type": "integer"},
                },
                "required": ["ticket_id", "conclusion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_ai_collaboration",
            "description": "★師父說「開始AI協作」時必用★ 啟動 9876、建立協作會話 ticket、嘗試開啟 Cursor 與 Antigravity。師父不必切換介面，繼續在 Ollama 對話即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "本次協作主題（可選）",
                    },
                    "open_cursor": {"type": "boolean", "description": "是否嘗試開 Cursor，預設 true"},
                    "open_antigravity": {
                        "type": "boolean",
                        "description": "是否嘗試開 Antigravity，預設 true",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cad_run_quote",
            "description": "Smart AI CAD 估價（9876）。需先 set_quote_facts 或 load_demo。",
            "parameters": {
                "type": "object",
                "properties": {
                    "facts": {"type": "object", "description": "可選，直接帶 quote_facts"},
                },
                "required": [],
            },
        },
    },
]

ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}


# ---------- MCP 呼叫 ----------

def _mcp_call_on(host: str, port: int, action: str, params: Optional[dict] = None,
                 *, timeout: float = 60.0, offline_hint: str = "") -> Dict[str, Any]:
    payload = {"action": action, "params": params or {}}
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        sock = socket.create_connection((host, port), timeout=5)
    except (ConnectionRefusedError, OSError, socket.timeout) as e:
        return {
            "success": False,
            "error": f"MCP offline ({host}:{port}) - {type(e).__name__}: {e}",
            "hint": offline_hint,
            "offline": True,
        }
    try:
        sock.settimeout(timeout)
        sock.sendall(line.encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(262144)
            if not chunk:
                break
            buf += chunk
        raw = buf.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
        if not raw:
            return {"success": False, "error": "MCP 回傳空資料"}
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"MCP 回應非 JSON: {e}", "raw": buf[:500].decode("utf-8", "replace")}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _mcp_call(action: str, params: Optional[dict] = None, *, timeout: float = 60.0) -> Dict[str, Any]:
    """Smart AI CAM Fusion MCP (9877)."""
    return _mcp_call_on(
        MCP_HOST, MCP_PORT, action, params, timeout=timeout,
        offline_hint="請在 Fusion 360 內 reload Smart AI CAM Fusion 外掛後重試",
    )


def _mcp_call_nx(action: str, params: Optional[dict] = None, *, timeout: float = 60.0) -> Dict[str, Any]:
    """Smart AI CAM-NX MCP (9878)."""
    return _mcp_call_on(
        NX_MCP_HOST, NX_MCP_PORT, action, params, timeout=timeout,
        offline_hint="請執行 E:\\ollama\\cam-helper-tools\\Start-Smart-AI-NX-MCP.bat",
    )


def _mcp_call_cad(action: str, params: Optional[dict] = None, *, timeout: float = 30.0) -> Dict[str, Any]:
    """Smart AI CAD MCP (9876, HTTP JSON)."""
    url = f"http://{CAD_MCP_HOST}:{CAD_MCP_PORT}/"
    payload = json.dumps({"action": action, "params": params or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ok"):
            return {"success": True, "action": data.get("action"), "result": data.get("result")}
        return {
            "success": False,
            "error": data.get("error", "CAD MCP error"),
            "status": data.get("status"),
        }
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"error": raw or str(e)}
        return {
            "success": False,
            "error": data.get("error", str(e)),
            "status": e.code,
        }
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as e:
        return {
            "success": False,
            "error": f"CAD MCP offline ({CAD_MCP_HOST}:{CAD_MCP_PORT}) - {e}",
            "offline": True,
            "hint": "請執行 Start-Smart-AI-CAD-MCP.bat",
        }


def _truncate_json(obj: Any, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    """大型 JSON 回應截斷後給模型，避免吃掉所有 context。"""
    txt = json.dumps(obj, ensure_ascii=False)
    if len(txt) <= max_chars:
        return txt
    return txt[: max_chars - 80] + f'... (truncated, total {len(txt)} chars)"}}'


# ---------- Tool call 解析 (3 種 fallback 格式) ----------

_INLINE_TOOL_RE = re.compile(
    r"\[tool_call:\s*(\w+)(?:\((.*?)\))?\]",
    re.DOTALL,
)


def _parse_text_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """v4 Modelfile few-shot 教的格式: `[tool_call: name(arg1=val1, ...)]`"""
    if not content:
        return None
    m = _INLINE_TOOL_RE.search(content)
    if not m:
        return None
    name = m.group(1)
    args_str = (m.group(2) or "").strip()
    if name not in ALLOWED_TOOLS:
        return None

    args: Dict[str, Any] = {}
    if args_str:
        try:
            args = json.loads("{" + args_str + "}") if args_str.startswith('"') else {}
        except json.JSONDecodeError:
            args = {}
        if not args:
            for pair in args_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k = k.strip().strip('"').strip("'")
                    v = v.strip().strip('"').strip("'")
                    if k:
                        args[k] = v

    return {
        "id": "text_0",
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def _parse_json_inline_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """qwen2.5-coder 偶爾把 tool call 寫成 JSON 塞 content 裡。"""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name") or obj.get("tool") or obj.get("function")
    args = obj.get("arguments", obj.get("args", obj.get("parameters", {})))
    if not name or name not in ALLOWED_TOOLS:
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    return {
        "id": "inline_0",
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def _detect_tool_calls(msg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """三層 fallback 偵測 tool_calls。回傳 (tool_calls, cleaned_content)"""
    content = msg.get("content", "") or ""
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        return tool_calls, content

    # Fallback 1: JSON inline (整段內容是 JSON)
    inline = _parse_json_inline_tool_call(content)
    if inline:
        return [inline], ""

    # Fallback 2: [tool_call: xxx] 文字格式
    text_tc = _parse_text_tool_call(content)
    if text_tc:
        cleaned = _INLINE_TOOL_RE.sub("", content).strip()
        return [text_tc], cleaned

    return [], content


# ---------- Ollama 健康檢查 / 模型解析 ----------

def _ollama_list_models() -> List[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        out: List[str] = []
        for m in data.get("models") or []:
            name = str(m.get("name") or "")
            if name:
                out.append(name)
        return out
    except Exception:
        return []


def _model_installed(preferred: str, installed: List[str]) -> bool:
    p = preferred.lower()
    for n in installed:
        base = n.split(":")[0].lower()
        if base == p or n.lower().startswith(p + ":"):
            return True
    return False


def resolve_ollama_model(preferred: Optional[str] = None) -> str:
    """若 preferred 未安裝，嘗試 cam-helper 等別名。"""
    want = preferred or MODEL
    installed = _ollama_list_models()
    if not installed:
        return want
    if _model_installed(want, installed):
        return want
    for alt in ("cam-helper", "cam_helper", "smart-ai-aegis"):
        if alt != want and _model_installed(alt, installed):
            return alt.split(":")[0]
    return want


def check_ollama_startup() -> Optional[str]:
    """REPL 啟動時檢查；回傳要印出的警告（無則 None）。"""
    global MODEL
    installed = _ollama_list_models()
    if not installed:
        return (
            f"[警告] 無法讀取 Ollama 模型清單 ({OLLAMA_URL})。\n"
            "  請確認 ollama serve 已啟動，或設定 OLLAMA_URL。"
        )
    wanted = MODEL
    resolved = resolve_ollama_model(wanted)
    if resolved != wanted:
        MODEL = resolved
        return f"[提示] 模型「{wanted}」未安裝，已自動改用: {MODEL}"
    if not _model_installed(MODEL, installed):
        return (
            f"[警告] 模型「{MODEL}」尚未建立 (會出現 HTTP 404)。\n"
            f"  請執行: {os.path.join(_TOOLS_ROOT, 'Build-Smart-AI-Aegis.bat')}\n"
            f"  或: ollama create smart-ai-aegis -f \"{os.path.join(_TOOLS_ROOT, 'Modelfile')}\"\n"
            f"  目前已安裝: {', '.join(installed[:12])}"
            + (" …" if len(installed) > 12 else "")
        )
    return None


def _ollama_error_message(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
        installed = _ollama_list_models()
        return (
            f"[Ollama] 模型「{MODEL}」不存在 (HTTP 404).\n"
            f"請執行 Build-Smart-AI-Aegis.bat，或:\n"
            f"  ollama create smart-ai-aegis -f \"{os.path.join(_TOOLS_ROOT, 'Modelfile')}\"\n"
            f"暫用舊模型: set CAM_HELPER_MODEL=cam-helper\n"
            f"已安裝模型: {', '.join(installed) if installed else '(無 / 無法連線)'}"
        )
    if isinstance(exc, urllib.error.URLError):
        return f"[Ollama 連線失敗] {exc}\n請確認 ollama serve 在 {OLLAMA_URL} 運行中"
    return f"[Ollama 錯誤] {type(exc).__name__}: {exc}"


# ---------- Ollama Chat (streaming + non-streaming) ----------

def _ollama_chat(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
                 stream: bool = False) -> Dict[str, Any]:
    """非串流：一次回完整 dict。"""
    body: Dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.25, "top_p": 0.85},
    }
    if tools:
        body["tools"] = tools
    last_err = None
    for attempt in range(RETRY_OLLAMA + 1):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/chat",
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as e:
            last_err = e
            if attempt < RETRY_OLLAMA:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_err  # type: ignore[misc]


def _ollama_chat_stream(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
                        ) -> Iterator[Dict[str, Any]]:
    """串流：每行 yield 一個 chunk dict。"""
    body: Dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.25, "top_p": 0.85},
    }
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        for line in resp:
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue


def _stream_collect(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                    print_realtime: bool = True) -> Dict[str, Any]:
    """串流並即時印出 + 收集成完整 message dict（含 tool_calls 合併）。"""
    full_content_parts: List[str] = []
    tool_calls_acc: List[Dict[str, Any]] = []
    final = {"message": {"content": "", "tool_calls": []}, "done": False}

    for chunk in _ollama_chat_stream(messages, tools=tools):
        msg = chunk.get("message", {}) or {}
        delta = msg.get("content", "") or ""
        if delta:
            full_content_parts.append(delta)
            if print_realtime:
                sys.stdout.write(delta)
                sys.stdout.flush()
        tcs = msg.get("tool_calls") or []
        if tcs:
            tool_calls_acc.extend(tcs)
        if chunk.get("done"):
            final = chunk
            break

    if print_realtime:
        sys.stdout.write("\n")
        sys.stdout.flush()

    final["message"] = {
        "role": "assistant",
        "content": "".join(full_content_parts),
        "tool_calls": tool_calls_acc,
    }
    return final


# ---------- Agent Loop ----------

def run_agent(user_msg: str, *, history: Optional[List[Dict[str, Any]]] = None,
              verbose: bool = False, stream: bool = True,
              use_tools: bool = True) -> Tuple[str, List[Dict[str, Any]]]:
    """單輪對話 Agent loop。回傳 (最終回答, 更新後的 messages)。
    若傳入 history 則會延續對話。use_tools=False 時僅純聊天（較快，不呼叫 MCP）。"""
    messages: List[Dict[str, Any]] = list(history or [])
    messages.append({"role": "user", "content": user_msg})
    tools = TOOLS if use_tools else None

    rounds = 0
    final_text = ""

    while rounds < MAX_TOOL_ROUNDS:
        rounds += 1
        if verbose:
            print(_color(f"[round {rounds}] 送 Ollama (stream={stream})...", C.GRAY), file=sys.stderr)

        try:
            if stream:
                resp = _stream_collect(messages, tools or [], print_realtime=False)
            else:
                resp = _ollama_chat(messages, tools=tools, stream=False)
        except urllib.error.HTTPError as e:
            return _ollama_error_message(e), messages
        except urllib.error.URLError as e:
            return _ollama_error_message(e), messages
        except Exception as e:
            return _ollama_error_message(e), messages

        msg = resp.get("message", {}) or {}
        tool_calls, content = _detect_tool_calls(msg)

        if not use_tools:
            tool_calls = []

        if not tool_calls:
            final_text = content.strip() or "(模型未產生回應)"
            messages.append({"role": "assistant", "content": final_text})
            return final_text, messages

        # 有 tool calls -> 記錄 assistant + 執行 tools
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            if verbose:
                print(_color(f"  → tool_call: {name}({json.dumps(args, ensure_ascii=False)})",
                             C.CYAN), file=sys.stderr)
            else:
                # 簡短進度
                print(_color(f"  [{name}]", C.CYAN), file=sys.stderr, end="", flush=True)

            if name not in ALLOWED_TOOLS:
                result = {"success": False, "error": f"未知工具 {name}"}
            elif name == "knowledge_stats":
                result = _knowledge_service.knowledge_stats_local() or _mcp_call(name, {})
            elif name == "knowledge_query":
                params = {k: args[k] for k in ("feature_type", "material", "geometry") if k in args}
                result = _knowledge_service.knowledge_query_local(params) or _mcp_call(name, params)
            elif name == "scan_machining_features":
                params = {k: args[k] for k in ("material",) if k in args}
                result = _mcp_call(name, params)
            elif name == "recommend_keili_cutting":
                # Agent tool → MCP action query_keili_catalog (mode=recommend)
                if "material" not in args or "tool_dia" not in args:
                    result = {
                        "success": False,
                        "error": "recommend_keili_cutting 必須帶 material 與 tool_dia",
                        "missing": [k for k in ("material", "tool_dia") if k not in args],
                    }
                else:
                    params = {"mode": "recommend"}
                    for k in ("material", "tool_dia", "teeth", "series",
                              "use_max", "operation", "pitch"):
                        if k in args:
                            params[k] = args[k]
                    result = _mcp_call("query_keili_catalog", params)
            elif name == "lookup_keili_catalog":
                # Agent tool → MCP action query_keili_catalog (mode=list_series/get_series/list_tools)
                params = {"mode": args.get("mode", "list_series")}
                for k in ("series", "diameter_mm"):
                    if k in args:
                        params[k] = args[k]
                result = _mcp_call("query_keili_catalog", params)
            elif name == "lookup_tool_library":
                # Agent tool → MCP action query_tool_library
                params = {}
                for k in ("mode", "category", "diameter_mm",
                          "material_target", "limit"):
                    if k in args:
                        params[k] = args[k]
                if "mode" not in params:
                    params["mode"] = "stats"
                result = _mcp_call("query_tool_library", params)
            elif name == "find_tool_for_job":
                # Agent tool → MCP action query_tool_library mode=find_best
                if "feature_type" not in args or "material_target" not in args:
                    result = {
                        "success": False,
                        "error": "find_tool_for_job 必須帶 feature_type 與 material_target",
                        "missing": [k for k in ("feature_type", "material_target")
                                    if k not in args],
                    }
                else:
                    params = {"mode": "find_best"}
                    for k in ("feature_type", "material_target", "diameter_mm",
                              "diameter_tolerance", "required_reach_mm"):
                        if k in args:
                            params[k] = args[k]
                    result = _mcp_call("query_tool_library", params)
            elif name == "lookup_material_properties":
                # Agent-level tool → MCP action: query_material_physics (lookup 模式)
                params = {"mode": "lookup"}
                if "material" in args:
                    params["material"] = args["material"]
                result = _mcp_call("query_material_physics", params)
            elif name == "calculate_cutting_params":
                # Agent-level tool → MCP action: query_material_physics (calculate 模式)
                # 強制要求 material 與 tool_dia
                if "material" not in args or "tool_dia" not in args:
                    result = {
                        "success": False,
                        "error": "calculate_cutting_params 必須帶 material 與 tool_dia 參數。"
                                 "範例: {\"material\":\"SUS304\",\"tool_dia\":6,\"teeth\":4}",
                        "missing": [k for k in ("material", "tool_dia") if k not in args],
                    }
                else:
                    params = {"mode": "calculate"}
                    for k in ("material", "tool_dia", "teeth", "is_drill", "is_tap", "pitch"):
                        if k in args:
                            params[k] = args[k]
                    result = _mcp_call("query_material_physics", params)
            elif name == "nx_get_manifest":
                result = _mcp_call_nx("get_cam_agent_manifest", {})
            elif name == "nx_list_material_profiles":
                result = _mcp_call_nx("list_material_profiles", {})
            elif name == "nx_query_smart_cutting":
                result = _mcp_call_nx("query_smart_cutting", dict(args))
            elif name == "nx_semi_auto_plan":
                result = _mcp_call_nx("get_semi_auto_plan", dict(args))
            elif name == "nx_hole_cam_catalog":
                result = _mcp_call_nx("nx_hole_cam_catalog", {})
            elif name == "assist_create_ticket":
                params = {
                    "source": "aegis",
                    "type": args.get("type", "general"),
                    "summary": args.get("summary", ""),
                    "owner": args.get("owner", "cursor"),
                    "priority": args.get("priority", "normal"),
                    "payload": dict(args.get("payload") or {}),
                }
                if args.get("theory_from_user"):
                    params["payload"]["theory_from_user"] = args["theory_from_user"]
                result = _mcp_call_cad("assist_create_ticket", params)
            elif name == "assist_watch_tickets":
                wparams = {}
                for k in ("since_rev", "status", "include_events", "limit"):
                    if k in args:
                        wparams[k] = args[k]
                if "include_events" not in wparams:
                    wparams["include_events"] = True
                result = _mcp_call_cad("assist_watch_tickets", wparams)
            elif name == "assist_get_ticket":
                result = _mcp_call_cad("assist_get_ticket", {"ticket_id": args.get("ticket_id", "")})
            elif name == "assist_append_context":
                result = _mcp_call_cad("assist_append_context", dict(args))
            elif name == "assist_resolve_ticket":
                result = _mcp_call_cad("assist_resolve_ticket", dict(args))
            elif name == "cad_run_quote":
                qparams = {}
                if "facts" in args:
                    qparams["facts"] = args["facts"]
                result = _mcp_call_cad("run_quote", qparams)
            elif name == "start_ai_collaboration":
                sparams = {"topic": args.get("topic") or args.get("summary") or "AI 協作"}
                if "open_cursor" in args:
                    sparams["open_cursor"] = args["open_cursor"]
                if "open_antigravity" in args:
                    sparams["open_antigravity"] = args["open_antigravity"]
                result = _mcp_call_cad("start_ai_collaboration", sparams)
            elif name == "assist_add_discussion":
                dparams = {k: args[k] for k in ("ticket_id", "by", "role", "content", "if_match_rev") if k in args}
                if "by" not in dparams:
                    dparams["by"] = "aegis"
                result = _mcp_call_cad("assist_add_discussion", dparams)
            elif name == "assist_get_discussion":
                result = _mcp_call_cad("assist_get_discussion", {"ticket_id": args.get("ticket_id", "")})
            elif name == "assist_collab_status":
                result = _mcp_call_cad("assist_collab_status", {"ticket_id": args.get("ticket_id", "")})
            elif name == "assist_propose_conclusion":
                result = _mcp_call_cad(
                    "assist_propose_conclusion",
                    {k: args[k] for k in ("ticket_id", "conclusion", "if_match_rev") if k in args},
                )
            else:
                result = _mcp_call(name, {})

            tool_payload = _truncate_json(result)
            if verbose:
                preview = tool_payload[:300] + ("..." if len(tool_payload) > 300 else "")
                print(_color(f"    ← result: {preview}", C.DIM), file=sys.stderr)
            elif result.get("offline"):
                print(_color(" [MCP offline]", C.RED), file=sys.stderr, end="", flush=True)
            elif not result.get("success", True):
                print(_color(" [tool error]", C.YELLOW), file=sys.stderr, end="", flush=True)

            messages.append({
                "role": "tool",
                "content": tool_payload,
            })

        if not verbose:
            print("", file=sys.stderr)  # 換行收尾

    final_text = "[達到 tool 呼叫上限，請重新提問]"
    messages.append({"role": "assistant", "content": final_text})
    return final_text, messages


# ---------- CLI ----------

HELP_TEXT = """\
指令：
  :q | :quit          退出
  :v                  切 verbose（看內部 tool 流程）
  :stream             切 streaming on/off
  :tools              列出可用 MCP 工具
  :reset              清空對話歷史
  :save <FILE>        存對話到 JSON 檔
  :help               顯示此說明
"""


def _print_tools():
    print(_color(f"  共 {len(TOOLS)} 個 MCP 工具：", C.BOLD))
    for t in TOOLS:
        f = t["function"]
        print(f"  {_color(f['name'], C.CYAN)} - {f['description'][:80]}")


def _repl():
    print(_color("Smart AI Aegis — 值得信任的智能體 (Fusion MCP + 本機學習庫)", C.BOLD + C.MAGENTA))
    warn = check_ollama_startup()
    if warn:
        print(_color(warn, C.YELLOW))
    print(_color(f"  Ollama: {OLLAMA_URL}  |  Model: {MODEL}  |  MCP: {MCP_HOST}:{MCP_PORT}", C.GRAY))
    print(_color("  輸入問題後按 Enter；:help 查指令；:q 結束", C.GRAY))
    print()

    verbose = False
    stream = True
    history: List[Dict[str, Any]] = []

    while True:
        try:
            q = input(_color("你> ", C.GREEN + C.BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not q:
            continue

        if q.lower() in (":q", ":quit", "exit"):
            break
        if q.lower() == ":v":
            verbose = not verbose
            print(_color(f"[verbose = {verbose}]", C.YELLOW))
            continue
        if q.lower() == ":stream":
            stream = not stream
            print(_color(f"[stream = {stream}]", C.YELLOW))
            continue
        if q.lower() == ":tools":
            _print_tools()
            continue
        if q.lower() == ":reset":
            history = []
            print(_color("[對話歷史已清空]", C.YELLOW))
            continue
        if q.lower() == ":help":
            print(_color(HELP_TEXT, C.GRAY))
            continue
        if q.lower().startswith(":save"):
            parts = q.split(maxsplit=1)
            fname = parts[1].strip() if len(parts) > 1 else "agent_chat.json"
            try:
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                print(_color(f"[已存 {fname} ({len(history)} 條訊息)]", C.YELLOW))
            except Exception as e:
                print(_color(f"[存檔失敗: {e}]", C.RED))
            continue

        t0 = time.time()
        try:
            ans, history = run_agent(q, history=history, verbose=verbose, stream=stream)
        except Exception as e:
            ans = f"[Agent 錯誤] {type(e).__name__}: {e}"
        dt = time.time() - t0
        print()
        print(_color("助理>", C.BLUE + C.BOLD), ans)
        print()
        print(_color(f"[{dt:.1f}s, history={len(history)} msgs]", C.GRAY))
        print()


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        question = " ".join(sys.argv[1:])
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        stream = "--no-stream" not in sys.argv
        ans, _ = run_agent(question, verbose=verbose, stream=stream)
        print(ans)
    else:
        _repl()


if __name__ == "__main__":
    main()
