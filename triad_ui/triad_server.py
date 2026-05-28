# -*- coding: utf-8 -*-
"""
四方協作 UI — http://127.0.0.1:9880

  python triad_ui/triad_server.py
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_UI = Path(__file__).resolve().parent
_ROOT = _UI.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from triad_ui.triad_orchestrator import (  # noqa: E402
    approve_and_resolve,
    broadcast_master_message,
    get_discussion,
    get_session_state,
    propose_conclusion,
    start_session,
    _cad_post,
)
from bridge.orchestrator import run_comodify  # noqa: E402

HOST = os.environ.get("TRIAD_UI_HOST", "127.0.0.1")
PORT = int(os.environ.get("TRIAD_UI_PORT", "9880"))
STATIC = _UI / "static"


def _json(handler: BaseHTTPRequestHandler, code: int, obj: dict) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    n = int(handler.headers.get("Content-Length") or 0)
    if n <= 0:
        return {}
    return json.loads(handler.rfile.read(n).decode("utf-8"))


def _group_discussion(discussion: list) -> dict:
    cols = {"master": [], "antigravity": [], "cursor": [], "aegis": []}
    for d in discussion or []:
        by = str(d.get("by", "")).lower()
        if by not in cols:
            by = "aegis"
        cols[by].append(d)
    return cols


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            self._serve_file(STATIC / rel)
            return
        if path == "/api/health":
            _json(self, 200, {"ok": True, "port": PORT})
            return
        if path == "/api/session":
            sess = get_session_state()
            tid = sess.get("ticket_id")
            out = {"session": sess, "columns": {}}
            if tid:
                disc = get_discussion(tid)
                if disc.get("success"):
                    discussion = (disc.get("result") or {}).get("discussion") or []
                    out["discussion"] = discussion
                    out["columns"] = _group_discussion(discussion)
                    out["collab_status"] = _cad_post("assist_collab_status", {"ticket_id": tid}).get(
                        "result"
                    )
            _json(self, 200, out)
            return
        _json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = _read_body(self)
        try:
            if path == "/api/start":
                topic = body.get("topic") or "四方協作"
                r = start_session(topic)
                _json(self, 200, {"ok": r.get("success"), "data": r})
                return
            if path == "/api/send":
                sess = get_session_state()
                tid = body.get("ticket_id") or sess.get("ticket_id")
                if not tid:
                    _json(self, 400, {"ok": False, "error": "請先按「開始協作」"})
                    return
                text = str(body.get("text") or "").strip()
                if not text:
                    _json(self, 400, {"ok": False, "error": "訊息不可為空"})
                    return
                r = broadcast_master_message(
                    tid,
                    text,
                    reply_antigravity=body.get("reply_antigravity", True),
                    reply_cursor=body.get("reply_cursor", True),
                    reply_aegis=body.get("reply_aegis", True),
                )
                cols = _group_discussion(r.get("discussion") or [])
                _json(self, 200, {"ok": r.get("success"), "data": r, "columns": cols})
                return
            if path == "/api/propose":
                tid = body.get("ticket_id") or get_session_state().get("ticket_id")
                conclusion = body.get("conclusion") or ""
                r = propose_conclusion(tid, conclusion)
                _json(self, 200, {"ok": r.get("success"), "data": r})
                return
            if path == "/api/approve":
                tid = body.get("ticket_id") or get_session_state().get("ticket_id")
                rev = int(body.get("rev") or 0)
                r = approve_and_resolve(tid, rev)
                _json(self, 200, {"ok": r.get("success"), "data": r})
                return
            if path == "/api/bridge/run":
                workspace = str(body.get("workspace") or "").strip()
                task = str(body.get("task") or body.get("text") or "").strip()
                if not workspace or not task:
                    _json(self, 400, {"ok": False, "error": "需要 workspace 與 task"})
                    return
                r = run_comodify(
                    workspace,
                    task,
                    ticket_id=body.get("ticket_id"),
                    master_note=str(body.get("master") or ""),
                    skip_challenge=bool(body.get("skip_challenge")),
                    ensure_mcp=body.get("ensure_mcp", True),
                )
                cols = {}
                if r.get("success") and r.get("discussion"):
                    cols = _group_discussion(r.get("discussion"))
                _json(self, 200, {"ok": r.get("success"), "data": r, "columns": cols})
                return
            _json(self, 404, {"ok": False, "error": "not found"})
        except Exception as e:
            _json(self, 500, {"ok": False, "error": str(e)})

    def _serve_file(self, fp: Path, ctype: str | None = None) -> None:
        if not fp.is_file():
            _json(self, 404, {"ok": False, "error": "file not found"})
            return
        data = fp.read_bytes()
        if not ctype:
            ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    print(f"Smart AI 四方協作 UI  http://{HOST}:{PORT}", flush=True)
    print("請確認：Ollama + CAD MCP(9876) 已啟動", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
