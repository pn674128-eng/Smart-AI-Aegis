# -*- coding: utf-8 -*-
"""
cam-helper Web UI server (Python stdlib only, no pip required)

  Smart_AI_CAM cam-helper v5 主腦版 Web UI
  Backend: http.server.ThreadingHTTPServer + cam_helper_agent
  Frontend: vanilla HTML/CSS/JS (no React/Vue framework)
  Streaming: Server-Sent Events (SSE)

Routes:
  GET  /                   → static/index.html
  GET  /static/<file>      → static files (css, js)
  GET  /api/status         → {ollama, mcp, model} health
  GET  /api/tools          → list MCP tools (from cam_helper_agent.TOOLS)
  POST /api/chat           → SSE streaming chat (multi-turn agent loop)
  POST /api/reset          → clear history (server-side stored per-session)

Usage:
  python E:\\Ollama\\cam-helper-tools\\webui\\server.py
  → 開瀏覽器到 http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

# ---- Force UTF-8 on stdout/stderr (Windows console default cp950 will crash on Chinese print) ----
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---- 找 cam_helper_agent ----
HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.normpath(os.path.join(HERE, "..", "agent"))
sys.path.insert(0, AGENT_DIR)

try:
    import cam_helper_agent as agent  # type: ignore
except ImportError as e:
    print(f"[FATAL] cam_helper_agent.py 找不到於 {AGENT_DIR}: {e}", file=sys.stderr)
    sys.exit(1)

# ---- 設定 ----
HOST = "127.0.0.1"
PORT = 8000
STATIC_DIR = os.path.join(HERE, "static")

# 全域對話歷史（單 user 個人用足夠；多用戶要改 session-based）
_history_lock = threading.Lock()
_history: List[Dict[str, Any]] = []


# ============================================================
#  Helpers
# ============================================================

def check_ollama() -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{agent.OLLAMA_URL}/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        return {"ok": True, "models": [m["name"] for m in data.get("models", [])]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_mcp() -> Dict[str, Any]:
    try:
        sock = socket.create_connection((agent.MCP_HOST, agent.MCP_PORT), timeout=2)
        sock.close()
        return {"ok": True, "host": agent.MCP_HOST, "port": agent.MCP_PORT}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
#  Streaming Agent (web 包裝)
# ============================================================

def stream_agent(user_msg: str, history: List[Dict[str, Any]],
                 verbose: bool = False):
    """執行 multi-turn agent loop，yield SSE 字串。"""
    messages = list(history)
    messages.append({"role": "user", "content": user_msg})

    rounds = 0
    final_assistant_msg = ""

    yield _sse("status", {"phase": "round_start", "round": 1})

    while rounds < agent.MAX_TOOL_ROUNDS:
        rounds += 1
        yield _sse("status", {"phase": "ollama_request", "round": rounds})

        try:
            full_content_parts: List[str] = []
            tool_calls_acc: List[Dict[str, Any]] = []

            for chunk in agent._ollama_chat_stream(messages, tools=agent.TOOLS):
                msg = chunk.get("message", {}) or {}
                delta = msg.get("content", "") or ""
                if delta:
                    full_content_parts.append(delta)
                    yield _sse("token", {"text": delta})
                tcs = msg.get("tool_calls") or []
                if tcs:
                    tool_calls_acc.extend(tcs)
                if chunk.get("done"):
                    break

            content = "".join(full_content_parts)
            tool_calls, cleaned_content = agent._detect_tool_calls({
                "content": content,
                "tool_calls": tool_calls_acc,
            })

            if not tool_calls:
                final_assistant_msg = (cleaned_content or content).strip() or "(模型未產生回應)"
                messages.append({"role": "assistant", "content": final_assistant_msg})
                yield _sse("done", {"text": final_assistant_msg, "rounds": rounds})
                # 更新全域 history
                with _history_lock:
                    _history.clear()
                    _history.extend(messages)
                return

            # ---- 有 tool_calls：記錄 + 執行 ----
            messages.append({
                "role": "assistant",
                "content": cleaned_content,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {}) or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}

                yield _sse("tool_call", {"name": name, "args": args})

                if name not in agent.ALLOWED_TOOLS:
                    result = {"success": False, "error": f"未知工具 {name}"}
                elif name == "knowledge_query":
                    params = {k: args[k] for k in ("feature_type", "material", "geometry") if k in args}
                    result = agent._mcp_call(name, params)
                elif name == "scan_machining_features":
                    params = {k: args[k] for k in ("material",) if k in args}
                    result = agent._mcp_call(name, params)
                else:
                    result = agent._mcp_call(name, {})

                tool_payload = agent._truncate_json(result)
                messages.append({"role": "tool", "content": tool_payload})

                yield _sse("tool_result", {
                    "name": name,
                    "success": result.get("success", False) if isinstance(result, dict) else False,
                    "offline": result.get("offline", False) if isinstance(result, dict) else False,
                    "preview": tool_payload[:400] + ("..." if len(tool_payload) > 400 else ""),
                })

        except urllib.error.URLError as e:
            yield _sse("error", {"message": f"Ollama 連線失敗: {e}"})
            return
        except Exception as e:
            yield _sse("error", {"message": f"Agent 錯誤: {type(e).__name__}: {e}"})
            return

    yield _sse("error", {"message": "達到 tool 呼叫上限（5 輪），請重新提問或縮小範圍"})


def _sse(event: str, data: Any) -> bytes:
    """格式化 Server-Sent Event。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


# ============================================================
#  HTTP Handler
# ============================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "CamHelperWebUI/1.0"

    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        sys.stderr.write(f"  [{ts}] {self.address_string()} {fmt % args}\n")

    # ----- helpers -----

    def _send_json(self, obj: Any, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, content_type: str):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._send_json({"error": "Not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ----- routing -----

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/":
            return self._send_file(os.path.join(STATIC_DIR, "index.html"),
                                    "text/html; charset=utf-8")

        if path == "/api/status":
            return self._send_json({
                "ollama": check_ollama(),
                "mcp": check_mcp(),
                "model": agent.MODEL,
                "tools_count": len(agent.TOOLS),
                "history_len": len(_history),
            })

        if path == "/api/tools":
            return self._send_json({
                "tools": [{
                    "name": t["function"]["name"],
                    "desc": t["function"]["description"],
                    "params": list(t["function"].get("parameters", {}).get("properties", {}).keys()),
                } for t in agent.TOOLS]
            })

        if path == "/api/history":
            with _history_lock:
                return self._send_json({"history": list(_history)})

        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            # 防 path traversal
            rel = rel.replace("..", "").lstrip("/\\")
            full = os.path.join(STATIC_DIR, rel)
            ext = os.path.splitext(full)[1].lower()
            ctype = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
            }.get(ext, "application/octet-stream")
            return self._send_file(full, ctype)

        self._send_json({"error": "Not found", "path": path}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/reset":
            with _history_lock:
                _history.clear()
            return self._send_json({"ok": True, "history_len": 0})

        if path == "/api/chat":
            body = self._read_json_body()
            user_msg = (body.get("message") or "").strip()
            if not user_msg:
                return self._send_json({"error": "message required"}, 400)

            with _history_lock:
                history_snapshot = list(_history)

            # SSE response
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()

            try:
                for chunk in stream_agent(user_msg, history_snapshot,
                                           verbose=bool(body.get("verbose"))):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # 用戶關閉 tab
            return

        self._send_json({"error": "Not found", "path": path}, 404)


# ============================================================
#  Main
# ============================================================

def main():
    if not os.path.exists(STATIC_DIR):
        os.makedirs(STATIC_DIR, exist_ok=True)

    print("=" * 64)
    print("  cam-helper Web UI v1.0")
    print("=" * 64)
    print(f"  Listen : http://{HOST}:{PORT}")
    print(f"  Static : {STATIC_DIR}")
    print(f"  Agent  : {os.path.join(AGENT_DIR, 'cam_helper_agent.py')}")
    print(f"  Ollama : {agent.OLLAMA_URL}  ({agent.MODEL})")
    print(f"  MCP    : {agent.MCP_HOST}:{agent.MCP_PORT}")
    print("=" * 64)

    # health check before start
    print("  Health check ...")
    o = check_ollama()
    m = check_mcp()
    print(f"    Ollama : {'OK' if o['ok'] else 'FAIL ' + str(o.get('error', ''))}")
    print(f"    MCP    : {'OK' if m['ok'] else 'OFFLINE'}")
    print()
    print(f"  Open browser: http://{HOST}:{PORT}")
    print("  Stop   : Ctrl+C")
    print()

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.allow_reuse_address = True  # 避免 TIME_WAIT 卡住重啟
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped")
        server.server_close()


if __name__ == "__main__":
    main()
