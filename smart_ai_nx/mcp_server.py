# -*- coding: utf-8 -*-
"""
Smart AI CAM-NX MCP server — TCP JSON-lines on 127.0.0.1:9878
Mirrors Fusion Smart_AI_CAM MCP (9877) without modifying Fusion add-in.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
from typing import Any, Dict

from .config import MCP_HOST, MCP_PORT, ADDIN_VERSION
from .process_request import process_mcp_request

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _handle_client(conn: socket.socket) -> None:
    buf = ""
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                break
            buf += data.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except json.JSONDecodeError as e:
                    resp = {"success": False, "error": f"JSON parse: {e}"}
                else:
                    action = req.get("action") or ""
                    params = req.get("params") or {}
                    resp = process_mcp_request(action, params)
                conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        conn.close()


def serve_forever() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((MCP_HOST, MCP_PORT))
    srv.listen(8)
    print(f"Smart AI CAM-NX MCP {ADDIN_VERSION} on {MCP_HOST}:{MCP_PORT}", flush=True)
    while True:
        client, addr = srv.accept()
        t = threading.Thread(target=_handle_client, args=(client,), daemon=True)
        t.start()


def main() -> None:
    serve_forever()


if __name__ == "__main__":
    main()
