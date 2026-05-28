# -*- coding: utf-8 -*-
"""Smart AI NX — paths & ports (Ollama cam-helper-tools tree)."""
from __future__ import annotations

import os
from pathlib import Path

# This package: E:\ollama\cam-helper-tools\smart_ai_nx
PKG_DIR = Path(__file__).resolve().parent
TOOLS_ROOT = PKG_DIR.parent
STORE_DIR = Path(os.environ.get("SMART_AI_STORE_DIR", str(TOOLS_ROOT / "store")))
STORE_DIR.mkdir(parents=True, exist_ok=True)

# Smart AI CAM Fusion（6-layer resolver 唯讀 import）
import sys as _sys

if str(TOOLS_ROOT) not in _sys.path:
    _sys.path.insert(0, str(TOOLS_ROOT))
try:
    from aegis_paths import FUSION_ADDIN_DIR
except ImportError:
    FUSION_ADDIN_DIR = Path(
        os.environ.get("SMART_AI_FUSION_ADDIN", str(TOOLS_ROOT / "Smart_AI_CAM"))
    )

# Company NX CAM library (cut methods / feeds & speeds)
NX_CAM_LIBRARY_ASCII = Path(
    os.environ.get(
        "UGII_CAM_LIBRARY_FEEDS_SPEEDS_ASCII_DIR",
        r"C:\Users\y00079\Documents\NX_CAM_Library\feeds_speeds\ascii",
    )
)

MCP_HOST = os.environ.get("NX_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("NX_MCP_PORT", "9878"))

# Bridge queue: NX journal polls this when running inside NX
NX_BRIDGE_DIR = Path(os.environ.get("SMART_AI_NX_BRIDGE", str(PKG_DIR / "nx_bridge")))
NX_BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
NX_BRIDGE_REQUEST = NX_BRIDGE_DIR / "request.json"
NX_BRIDGE_RESPONSE = NX_BRIDGE_DIR / "response.json"

ADDIN_VERSION = "0.3.0-aegis-trunk"
PLUGIN_CONFIG_PATH = PKG_DIR / "plugin_config.yaml"
DATA_DIR = PKG_DIR / "data"
