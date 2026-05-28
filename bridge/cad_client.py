# -*- coding: utf-8 -*-
"""Smart AI CAD MCP (9876) HTTP 客戶端。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

_TOOLS_ROOT = Path(__file__).resolve().parent.parent
CAD_MCP_URL = os.environ.get("CAD_MCP_URL", "http://127.0.0.1:9876/")
CAD_MCP_HOST = os.environ.get("CAD_MCP_HOST", "127.0.0.1")
CAD_MCP_PORT = int(os.environ.get("CAD_MCP_PORT", "9876"))


def cad_post(action: str, params: Optional[dict] = None, *, timeout: float = 120.0) -> Dict[str, Any]:
    body = json.dumps({"action": action, "params": params or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        CAD_MCP_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("ok"):
            return {"success": True, "result": data.get("result")}
        return {"success": False, "error": data.get("error", "unknown")}
    except Exception as e:
        return {"success": False, "error": str(e), "offline": True}


def cad_mcp_alive() -> bool:
    try:
        r = cad_post("assist_list_tickets", {"limit": 1}, timeout=3.0)
        return bool(r.get("success"))
    except Exception:
        return False


def ensure_cad_mcp(*, wait_sec: float = 4.0) -> Dict[str, Any]:
    if cad_mcp_alive():
        return {"success": True, "started": False}
    mcp_py = _TOOLS_ROOT / "Smart AI CAD" / "mcp" / "cad_mcp_server.py"
    if not mcp_py.is_file():
        return {"success": False, "error": f"找不到 MCP: {mcp_py}"}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        subprocess.Popen(
            [sys.executable, str(mcp_py)],
            cwd=str(_TOOLS_ROOT),
            creationflags=flags,
        )
    except Exception as e:
        return {"success": False, "error": f"啟動 MCP 失敗: {e}"}
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        time.sleep(0.25)
        if cad_mcp_alive():
            return {"success": True, "started": True}
    return {"success": False, "error": "CAD MCP 9876 啟動逾時", "offline": True}
