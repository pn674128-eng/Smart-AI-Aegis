# -*- coding: utf-8 -*-
"""Serve nx_palette.html and proxy MCP calls to 127.0.0.1:9878 (Smart AI CAM trunk parity)."""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

UI_DIR = Path(__file__).resolve().parent
MCP_HOST = "127.0.0.1"
MCP_PORT = 9878
HTTP_PORT = int(__import__("os").environ.get("NX_PANEL_PORT", "9879"))


def mcp_call(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {"action": action, "params": params or {}}
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        sock = socket.create_connection((MCP_HOST, MCP_PORT), timeout=5)
        sock.settimeout(120)
        sock.sendall(line.encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(262144)
            if not chunk:
                break
            buf += chunk
        sock.close()
        return json.loads(buf.decode("utf-8"))
    except OSError as e:
        return {
            "success": False,
            "error": f"MCP offline ({MCP_HOST}:{MCP_PORT}): {e}",
            "hint": "Run Start-Smart-AI-NX-MCP.bat first",
        }


class PanelHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj: Dict[str, Any], code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/nx_palette.html"):
            html = (UI_DIR / "nx_palette.html").read_text(encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        if path == "/health":
            self._send_json({"ok": True, "mcp": f"{MCP_HOST}:{MCP_PORT}"})
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode("utf-8")
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json({"success": False, "error": "invalid json"}, 400)
            return
        action = req.get("action") or ""
        params = req.get("params") or {}
        self._send_json(mcp_call(action, params))


def main():
    httpd = HTTPServer((MCP_HOST, HTTP_PORT), PanelHandler)
    print(f"Smart AI NX Panel: http://{MCP_HOST}:{HTTP_PORT}/")
    print(f"MCP proxy -> {MCP_HOST}:{MCP_PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
