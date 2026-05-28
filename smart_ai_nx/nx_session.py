# -*- coding: utf-8 -*-
"""NX session bridge — file queue until NX Open journal executes."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from .config import NX_BRIDGE_REQUEST, NX_BRIDGE_RESPONSE, NX_BRIDGE_DIR


def nx_bridge_status() -> Dict[str, Any]:
    return {
        "bridge_dir": str(NX_BRIDGE_DIR),
        "request_pending": NX_BRIDGE_REQUEST.is_file(),
        "response_pending": NX_BRIDGE_RESPONSE.is_file(),
        "note": "在 NX 內執行 smart_ai_nx_boot journal 可處理佇列",
    }


def post_nx_bridge_request(action: str, params: Optional[Dict[str, Any]] = None,
                           timeout_sec: float = 2.0) -> Dict[str, Any]:
    payload = {"action": action, "params": params or {}, "ts": time.time()}
    NX_BRIDGE_RESPONSE.unlink(missing_ok=True)
    NX_BRIDGE_REQUEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if NX_BRIDGE_RESPONSE.is_file():
            try:
                return json.loads(NX_BRIDGE_RESPONSE.read_text(encoding="utf-8"))
            except Exception as e:
                return {"success": False, "error": f"bad bridge response: {e}"}
        time.sleep(0.15)
    return {
        "success": False,
        "error": "NX bridge timeout — 請在 NX 製造模組執行「Smart AI NX」→ 處理佇列",
        "pending_request": payload,
    }


def get_addin_info() -> Dict[str, Any]:
    from .config import ADDIN_VERSION, MCP_PORT, FUSION_ADDIN_DIR, NX_CAM_LIBRARY_ASCII
    from .nx_cam_library import library_status

    nx_running = False
    try:
        import NXOpen  # noqa: F401
        nx_running = True
    except ImportError:
        pass

    return {
        "success": True,
        "data": {
            "name": "Smart AI CAM-NX",
            "version": ADDIN_VERSION,
            "mcp_port": MCP_PORT,
            "fusion_addin_readonly": str(FUSION_ADDIN_DIR),
            "nx_open_in_process": nx_running,
            "cam_library": library_status(),
        },
    }
