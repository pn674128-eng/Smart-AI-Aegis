# -*- coding: utf-8 -*-
"""
Bridge for Autodesk Fusion Assistant (Script Execute) → Smart_AI_CAM MCP :9877.

Usage inside Fusion (Text Commands or Assistant-generated script):

    import sys, os
    addin = r"E:\\Fusion\\插件\\Smart_AI_CAM"  # adjust path
    if addin not in sys.path:
        sys.path.insert(0, addin)
    from scripts.fusion_ai_bridge import cam_call, gap_audit_pack

    pack = gap_audit_pack()
    # Copy pack JSON to Assistant chat for gap analysis.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Dict, Optional

HOST = "127.0.0.1"
PORT = 9877
DEFAULT_TIMEOUT = 120.0


def cam_call(
    action: str,
    params: Optional[dict] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    host: str = HOST,
    port: int = PORT,
) -> Dict[str, Any]:
    """Send one MCP request; return parsed JSON response."""
    payload = {"action": action, "params": params or {}}
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    sock = socket.create_connection((host, port), timeout=10)
    try:
        sock.settimeout(timeout)
        sock.sendall(line.encode("utf-8"))
        buf = ""
        while "\n" not in buf:
            chunk = sock.recv(262144)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
        raw = buf.strip().split("\n", 1)[0] if buf.strip() else ""
        if not raw:
            return {"success": False, "error": "empty response from MCP"}
        return json.loads(raw)
    finally:
        sock.close()


def gap_audit_pack() -> Dict[str, Any]:
    """Fetch full audit pack from running add-in."""
    return cam_call("get_fusion_ai_gap_audit_pack", {}, timeout=60.0)


def manifest_only() -> Dict[str, Any]:
    return cam_call("get_cam_agent_manifest", {}, timeout=30.0)


if __name__ == "__main__":
    import sys

    action = (sys.argv[1] if len(sys.argv) > 1 else "get_fusion_ai_gap_audit_pack").strip()
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            params = {}
    out = cam_call(action, params)
    print(json.dumps(out, ensure_ascii=False, indent=2))
