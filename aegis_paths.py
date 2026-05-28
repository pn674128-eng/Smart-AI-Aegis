# -*- coding: utf-8 -*-
"""Smart AI Aegis 工具樹路徑（單一來源）。"""
from __future__ import annotations

import os
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parent

# Fusion 外掛本體（已併入 cam-helper-tools）
FUSION_ADDIN_DIR = Path(
    os.environ.get("SMART_AI_FUSION_ADDIN", str(TOOLS_ROOT / "Smart_AI_CAM"))
)

# 學習庫：live = 外掛執行時寫入；mirror = 主腦備份（sync 腳本維護）
KNOWLEDGE_LIVE_DIR = FUSION_ADDIN_DIR / "Smart_AI" / "memory" / "data"
KNOWLEDGE_MIRROR_DIR = Path(
    os.environ.get("SMART_AI_KNOWLEDGE_MIRROR", str(TOOLS_ROOT / "knowledge" / "mirror"))
)
KNOWLEDGE_MIRROR_DIR.mkdir(parents=True, exist_ok=True)

STORE_DIR = Path(os.environ.get("SMART_AI_STORE_DIR", str(TOOLS_ROOT / "store")))
STORE_DIR.mkdir(parents=True, exist_ok=True)

# 產品正名
PRODUCT_AEGIS = "Smart AI Aegis"
PRODUCT_FUSION_CAM = "Smart AI CAM Fusion"
PRODUCT_NX_CAM = "Smart AI CAM-NX"
PRODUCT_CAD = "Smart AI CAD"

# CAD 核心（讀圖 + 估價；開源客製主體）
SMART_AI_CAD_DIR = Path(
    os.environ.get("SMART_AI_CAD_DIR", str(TOOLS_ROOT / "Smart AI CAD"))
)

# Ollama 模型（正名 smart-ai-aegis；cam-helper 為向後相容別名）
OLLAMA_MODEL_AEGIS = "smart-ai-aegis"
OLLAMA_MODEL_LEGACY = "cam-helper"


def default_ollama_model() -> str:
    return (
        os.environ.get("AEGIS_MODEL")
        or os.environ.get("CAM_HELPER_MODEL")
        or OLLAMA_MODEL_AEGIS
    )

# MCP
FUSION_MCP_HOST = os.environ.get("CAM_MCP_HOST", "127.0.0.1")
FUSION_MCP_PORT = int(os.environ.get("CAM_MCP_PORT", "9877"))
NX_MCP_PORT = int(os.environ.get("NX_MCP_PORT", "9878"))
CAD_MCP_HOST = os.environ.get("CAD_MCP_HOST", "127.0.0.1")
CAD_MCP_PORT = int(os.environ.get("CAD_MCP_PORT", "9876"))
