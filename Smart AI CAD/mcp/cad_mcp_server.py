# -*- coding: utf-8 -*-
"""
Smart AI CAD MCP — 讀圖事實 + 估價（預設 127.0.0.1:9876）

  python "Smart AI CAD\\mcp\\cad_mcp_server.py"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_CAD_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_ROOT = _CAD_ROOT.parent
_INBOX_DIR = _TOOLS_ROOT / "store" / "inbox"
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))
if str(_CAD_ROOT) not in sys.path:
    sys.path.insert(0, str(_CAD_ROOT))

from core.facts_merge import merge_quote_facts  # noqa: E402
from core.quote_engine import estimate_from_facts  # noqa: E402

HOST = os.environ.get("CAD_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("CAD_MCP_PORT", "9876"))

# 記憶體暫存（Phase 0）；之後可改檔案/DB
_STORE: Dict[str, Any] = {"primary_facts": None, "bridge_facts": []}
_COLLAB_PATH = _CAD_ROOT / "store" / "collab_tickets.json"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ensure_collab_store() -> Dict[str, Any]:
    _COLLAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _COLLAB_PATH.is_file():
        try:
            return json.loads(_COLLAB_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tickets": {}, "next_rev": 1}


_COLLAB = _ensure_collab_store()


def _save_collab() -> None:
    _COLLAB_PATH.write_text(
        json.dumps(_COLLAB, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _new_rev() -> int:
    rev = int(_COLLAB.get("next_rev", 1))
    _COLLAB["next_rev"] = rev + 1
    return rev


def _write_inboxes(t: Dict[str, Any], *, event: str = "created") -> None:
    """寫入收件匣，減少師父手動切換 Cursor / Antigravity。"""
    try:
        _INBOX_DIR.mkdir(parents=True, exist_ok=True)
        snap = {
            "event": event,
            "ticket_id": t["ticket_id"],
            "rev": t["rev"],
            "status": t["status"],
            "type": t["type"],
            "summary": t["summary"],
            "owner": t["owner"],
            "core_approved": t.get("core_approved", False),
            "reply": t.get("reply", ""),
            "payload": t.get("payload") or {},
            "updated_at": t.get("updated_at"),
        }
        (_INBOX_DIR / "latest_ticket.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        theory = (t.get("payload") or {}).get("theory_from_user", "")
        md = (
            f"# 協作單 {t['ticket_id']}\n\n"
            f"- 狀態: {t['status']}\n"
            f"- 類型: {t['type']}\n"
            f"- 負責: {t['owner']}\n"
            f"- rev: {t['rev']}\n\n"
            f"## 摘要\n{t['summary']}\n\n"
        )
        if theory:
            md += f"## 師父理論\n{theory}\n\n"
        if t.get("reply"):
            md += f"## 最新回覆\n{t['reply']}\n\n"
        md += (
            "## 給 Cursor（不必切換介面）\n"
            "在 **cam-helper-tools** 專案開 Cursor 時，對話說：`處理最新協作單` 即可。\n\n"
            "## 給師父（只跟 Aegis 說）\n"
            "- 「協作單進度如何」\n"
            "- 「核准並結案」\n"
        )
        (_INBOX_DIR / "LATEST_FOR_CURSOR.md").write_text(md, encoding="utf-8")
        if event == "created":
            (_INBOX_DIR / "PENDING_FOR_CURSOR.flag").write_text(t["ticket_id"], encoding="utf-8")
        if t.get("status") == "review" and t.get("reply"):
            (_INBOX_DIR / "PENDING_FOR_AEGIS.flag").write_text(
                f"{t['ticket_id']}|rev={t['rev']}", encoding="utf-8"
            )
    except Exception:
        pass


def _cad_mcp_alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False


def _spawn_cad_mcp_background() -> bool:
    try:
        script = _CAD_ROOT / "mcp" / "cad_mcp_server.py"
        pyw = os.environ.get("PYTHONW") or "pythonw"
        if not Path(pyw).is_file() and Path(sys.executable).is_file():
            pyw = sys.executable.replace("python.exe", "pythonw.exe")
            if not Path(pyw).is_file():
                pyw = sys.executable
        subprocess.Popen(
            [pyw, str(script)],
            cwd=str(_TOOLS_ROOT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def _try_launch(command: str) -> bool:
    try:
        subprocess.Popen(
            command,
            shell=True,
            cwd=str(_TOOLS_ROOT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def _launch_cursor() -> Optional[str]:
    root = str(_TOOLS_ROOT)
    for cmd in (f'cursor "{root}"', f'code "{root}"'):
        if _try_launch(cmd):
            return cmd
    return None


def _launch_antigravity() -> Optional[str]:
    env = os.environ.get("ANTIGRAVITY_EXE", "").strip()
    candidates = []
    if env:
        candidates.append(f'"{env}"')
    local = os.environ.get("LOCALAPPDATA", "")
    for name in ("Antigravity", "antigravity", "Programs/Antigravity/Antigravity.exe"):
        p = Path(local) / name
        if p.is_file():
            candidates.append(f'"{p}"')
    for cmd in candidates:
        if _try_launch(cmd):
            return cmd
    return None


def _require_ticket(ticket_id: str) -> Dict[str, Any]:
    t = (_COLLAB.get("tickets") or {}).get(ticket_id)
    if not t:
        raise ApiError(404, f"ticket not found: {ticket_id}")
    return t


def _json_response(handler: BaseHTTPRequestHandler, code: int, body: Dict[str, Any]) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "service": "Smart AI CAD MCP",
                    "port": PORT,
                    "schema": "quote_facts v0.1",
                },
            )
            return
        if path == "/manifest":
            _json_response(
                self,
                200,
                {
                    "plugin": "Smart AI CAD",
                    "version": "0.1.0",
                    "actions": [a[0] for a in _ACTIONS],
                },
            )
            return
        _json_response(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json()
        action = body.get("action") or path.strip("/")
        for name, fn in _ACTIONS:
            if action == name:
                try:
                    result = fn(body.get("params") or body)
                except ApiError as e:
                    _json_response(
                        self,
                        e.status,
                        {"ok": False, "error": e.message, "status": e.status},
                    )
                    return
                except Exception as e:
                    _json_response(self, 500, {"ok": False, "error": str(e)})
                    return
                _json_response(self, 200, {"ok": True, "action": name, "result": result})
                return
        _json_response(self, 400, {"ok": False, "error": f"unknown action: {action}"})


def _action_set_facts(params: Dict[str, Any]) -> Dict[str, Any]:
    role = params.get("role", "primary")
    facts = params.get("facts") or params
    facts.setdefault("schema_version", "0.1")
    if role == "bridge":
        _STORE["bridge_facts"].append(facts)
    else:
        _STORE["primary_facts"] = facts
    return {"stored": role, "source_id": facts.get("source_id")}


def _action_get_merged_facts(_params: Dict[str, Any]) -> Dict[str, Any]:
    primary = _STORE.get("primary_facts") or {
        "schema_version": "0.1",
        "source_id": "manual",
        "units": "mm",
        "capabilities": [],
    }
    merged = merge_quote_facts(primary, *_STORE.get("bridge_facts") or [])
    return merged


def _action_run_quote(params: Dict[str, Any]) -> Dict[str, Any]:
    if params.get("facts"):
        facts = params["facts"]
    else:
        facts = _action_get_merged_facts({})
    override = params.get("override_params") or params.get("override")
    return estimate_from_facts(facts, override)


def _action_clear_facts(_params: Dict[str, Any]) -> Dict[str, Any]:
    _STORE["primary_facts"] = None
    _STORE["bridge_facts"] = []
    return {"cleared": True}


def _action_demo_sample(_params: Dict[str, Any]) -> Dict[str, Any]:
    """示範用：寫入一筆 3D + 一筆 2D bridge facts。"""
    _action_clear_facts({})
    _action_set_facts(
        {
            "role": "primary",
            "facts": {
                "schema_version": "0.1",
                "source_id": "freecad_core",
                "capabilities": ["3d"],
                "units": "mm",
                "qty": 10,
                "material": "AL6061",
                "envelope_mm": [120, 80, 25],
                "volume_cm3": 180.0,
                "holes": [{"diameter_mm": 8, "count": 6, "depth_mm": 15}],
            },
        }
    )
    _action_set_facts(
        {
            "role": "bridge",
            "facts": {
                "schema_version": "0.1",
                "source_id": "zwcad_2d",
                "capabilities": ["2d", "notes"],
                "units": "mm",
                "drawing_notes": ["鍍鎳"],
                "2d": {"perimeter_mm": 520, "block_count": 2},
            },
        }
    )
    return {"demo": True, "merged": _action_get_merged_facts({})}


def _ensure_ticket_discussion_fields(t: Dict[str, Any]) -> None:
    t.setdefault("discussion", [])
    t.setdefault("discussion_status", "open")
    t.setdefault("proposed_conclusion", "")
    t.setdefault(
        "required_participants",
        ["antigravity", "cursor", "aegis"],
    )


def _discussion_stats(t: Dict[str, Any]) -> Dict[str, int]:
    stats = {"antigravity": 0, "cursor": 0, "aegis": 0, "master": 0, "total": 0}
    for d in t.get("discussion") or []:
        by = str(d.get("by", "")).lower()
        if by in stats:
            stats[by] += 1
        stats["total"] += 1
    return stats


def _ticket_summary(t: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_ticket_discussion_fields(t)
    stats = _discussion_stats(t)
    return {
        "ticket_id": t["ticket_id"],
        "type": t["type"],
        "status": t["status"],
        "owner": t["owner"],
        "priority": t["priority"],
        "rev": t["rev"],
        "core_approved": t["core_approved"],
        "updated_at": t["updated_at"],
        "summary": t["summary"],
        "discussion_status": t.get("discussion_status"),
        "discussion_turns": stats,
        "has_proposed_conclusion": bool(t.get("proposed_conclusion")),
    }


def _append_event(t: Dict[str, Any], event_type: str, payload: Dict[str, Any]) -> None:
    t["events"].append(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "at": _now_iso(),
            "payload": payload,
            "rev": t["rev"],
        }
    )


def _action_assist_create_ticket(params: Dict[str, Any]) -> Dict[str, Any]:
    source = str(params.get("source") or "aegis")
    ticket_type = str(params.get("type") or "general")
    summary = str(params.get("summary") or "").strip()
    if not summary:
        raise ApiError(400, "summary is required")

    ticket_id = "tkt_" + uuid.uuid4().hex[:12]
    now = _now_iso()
    rev = _new_rev()
    t = {
        "ticket_id": ticket_id,
        "source": source,
        "type": ticket_type,
        "priority": str(params.get("priority") or "normal"),
        "status": "open",
        "owner": str(params.get("owner") or "unassigned"),
        "summary": summary,
        "payload": params.get("payload") or {},
        "artifacts": params.get("artifacts") or [],
        "reply": "",
        "core_approved": bool(params.get("core_approved", False)),
        "rev": rev,
        "created_at": now,
        "updated_at": now,
        "events": [],
        "discussion": [],
        "discussion_status": "open",
        "proposed_conclusion": "",
        "required_participants": ["antigravity", "cursor", "aegis"],
    }
    _append_event(t, "ticket_created", {"source": source, "summary": summary})
    _COLLAB["tickets"][ticket_id] = t
    _save_collab()
    _write_inboxes(t, event="created")
    return _ticket_summary(t)


def _action_assist_get_ticket(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    return _require_ticket(ticket_id)


def _action_assist_list_tickets(params: Dict[str, Any]) -> Dict[str, Any]:
    status_filter = params.get("status")
    owner_filter = params.get("owner")
    out = []
    for t in (_COLLAB.get("tickets") or {}).values():
        if status_filter and t.get("status") != status_filter:
            continue
        if owner_filter and t.get("owner") != owner_filter:
            continue
        out.append(_ticket_summary(t))
    out.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"items": out, "count": len(out)}


def _action_assist_watch_tickets(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    輪詢友善：回傳自 since_rev 以來有變更的 ticket 摘要（可附增量事件）。
    客戶端下次請求帶回傳的 cursor_rev 作為 since_rev。
    """
    since_rev = params.get("since_rev")
    since_updated_at = params.get("since_updated_at")
    status_filter = params.get("status")
    owner_filter = params.get("owner")
    include_events = bool(params.get("include_events", False))
    limit = int(params.get("limit") or 50)
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    sv = int(since_rev) if since_rev is not None else None
    changed: List[Dict[str, Any]] = []
    max_rev = sv or 0

    for t in (_COLLAB.get("tickets") or {}).values():
        if status_filter and t.get("status") != status_filter:
            continue
        if owner_filter and t.get("owner") != owner_filter:
            continue
        if since_updated_at and str(t.get("updated_at") or "") <= str(since_updated_at):
            continue
        trev = int(t.get("rev") or 0)
        if sv is not None and trev <= sv:
            continue

        max_rev = max(max_rev, trev)
        row = _ticket_summary(t)
        row["last_event_type"] = ""
        evs = t.get("events") or []
        if evs:
            row["last_event_type"] = evs[-1].get("event_type", "")
        if include_events:
            if sv is not None:
                row["events"] = [e for e in evs if int(e.get("rev", 0)) > sv]
            else:
                row["events"] = evs[-5:]
        changed.append(row)

    changed.sort(key=lambda x: x["updated_at"], reverse=True)
    truncated = len(changed) > limit
    if truncated:
        changed = changed[:limit]

    cursor_rev = max_rev
    if changed:
        cursor_rev = max(int(x["rev"]) for x in changed)

    return {
        "cursor_rev": cursor_rev,
        "global_next_rev": int(_COLLAB.get("next_rev", 1)),
        "count": len(changed),
        "truncated": truncated,
        "items": changed,
    }


def _action_assist_get_events(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    t = _require_ticket(ticket_id)
    events = list(t.get("events") or [])
    since_rev = params.get("since_rev")
    if since_rev is not None:
        sv = int(since_rev)
        events = [e for e in events if int(e.get("rev", 0)) > sv]
    return {
        "ticket_id": ticket_id,
        "count": len(events),
        "events": events,
        "current_rev": t["rev"],
    }


def _action_assist_append_context(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    t = _require_ticket(ticket_id)

    if_match_rev = params.get("if_match_rev")
    if if_match_rev is not None and int(if_match_rev) != int(t["rev"]):
        raise ApiError(409, f"revision conflict: current={t['rev']} provided={if_match_rev}")

    patch = params.get("patch") or {}
    for k in ("status", "owner", "priority", "summary", "reply"):
        if k in patch:
            t[k] = patch[k]
    if "core_approved" in patch:
        t["core_approved"] = bool(patch["core_approved"])
    if "payload" in patch and isinstance(patch["payload"], dict):
        t["payload"] = {**(t.get("payload") or {}), **patch["payload"]}
    if "artifacts" in patch and isinstance(patch["artifacts"], list):
        t["artifacts"] = list(t.get("artifacts") or []) + patch["artifacts"]

    t["rev"] = _new_rev()
    t["updated_at"] = _now_iso()
    _append_event(
        t,
        "context_appended",
        {"by": params.get("by", "unknown"), "keys": list((patch or {}).keys())},
    )
    _save_collab()
    _write_inboxes(t, event="updated")
    return _ticket_summary(t)


def _action_assist_add_discussion(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    content = str(params.get("content") or "").strip()
    if not content:
        raise ApiError(400, "content is required")
    by = str(params.get("by") or "unknown").lower()
    role = str(params.get("role") or "comment")
    t = _require_ticket(ticket_id)
    _ensure_ticket_discussion_fields(t)

    if_match_rev = params.get("if_match_rev")
    if if_match_rev is not None and int(if_match_rev) != int(t["rev"]):
        raise ApiError(409, f"revision conflict: current={t['rev']} provided={if_match_rev}")

    turn = {
        "turn_id": str(uuid.uuid4()),
        "by": by,
        "role": role,
        "content": content,
        "at": _now_iso(),
    }
    t["discussion"].append(turn)
    t["discussion_status"] = "discussing"
    t["rev"] = _new_rev()
    t["updated_at"] = _now_iso()
    _append_event(t, "discussion_added", {"by": by, "role": role, "turn_id": turn["turn_id"]})
    _save_collab()
    _write_inboxes(t, event="discussion")
    return {
        "ticket_id": ticket_id,
        "rev": t["rev"],
        "turn": turn,
        "discussion_turns": _discussion_stats(t),
        "discussion_status": t["discussion_status"],
    }


def _action_assist_get_discussion(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    t = _require_ticket(ticket_id)
    _ensure_ticket_discussion_fields(t)
    return {
        "ticket_id": ticket_id,
        "rev": t["rev"],
        "discussion_status": t.get("discussion_status"),
        "proposed_conclusion": t.get("proposed_conclusion", ""),
        "discussion": list(t.get("discussion") or []),
        "discussion_turns": _discussion_stats(t),
        "required_participants": t.get("required_participants"),
    }


def _action_assist_collab_status(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    t = _require_ticket(ticket_id)
    _ensure_ticket_discussion_fields(t)
    stats = _discussion_stats(t)
    missing = []
    for p in t.get("required_participants") or []:
        if stats.get(p, 0) < 1:
            missing.append(p)
    ready_for_conclusion = not missing and bool(t.get("proposed_conclusion"))
    can_propose = not missing and stats.get("total", 0) >= 3
    return {
        "ticket_id": ticket_id,
        "rev": t["rev"],
        "discussion_status": t.get("discussion_status"),
        "discussion_turns": stats,
        "missing_participants": missing,
        "can_propose_conclusion": can_propose,
        "ready_for_master_approval": ready_for_conclusion,
        "proposed_conclusion": t.get("proposed_conclusion", ""),
    }


def _action_assist_propose_conclusion(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    conclusion = str(params.get("conclusion") or params.get("content") or "").strip()
    if not ticket_id or not conclusion:
        raise ApiError(400, "ticket_id and conclusion are required")
    t = _require_ticket(ticket_id)
    _ensure_ticket_discussion_fields(t)

    if_match_rev = params.get("if_match_rev")
    if if_match_rev is not None and int(if_match_rev) != int(t["rev"]):
        raise ApiError(409, f"revision conflict: current={t['rev']} provided={if_match_rev}")

    status = _action_assist_collab_status({"ticket_id": ticket_id})
    if status.get("missing_participants"):
        raise ApiError(
            409,
            "discussion incomplete: missing turns from "
            + ", ".join(status["missing_participants"])
            + " — 協作須三方對話後才能提出結論",
        )

    t["proposed_conclusion"] = conclusion
    t["discussion_status"] = "conclusion_draft"
    t["status"] = "review"
    t["rev"] = _new_rev()
    t["updated_at"] = _now_iso()
    _append_event(t, "conclusion_proposed", {"by": params.get("by", "aegis")})
    _save_collab()
    _write_inboxes(t, event="conclusion_draft")
    (_INBOX_DIR / "PENDING_FOR_AEGIS.flag").write_text(
        f"{ticket_id}|rev={t['rev']}|approve_conclusion", encoding="utf-8"
    )
    return {
        "ticket_id": ticket_id,
        "rev": t["rev"],
        "discussion_status": t["discussion_status"],
        "proposed_conclusion": conclusion,
        "message": "結論草案已產出，待師父認可後 core_approved 結案",
    }


def _action_start_ai_collaboration(params: Dict[str, Any]) -> Dict[str, Any]:
    """一鍵啟動三方協作：9876 + 會話 ticket + 嘗試開 Cursor / Antigravity。"""
    topic = str(params.get("topic") or params.get("summary") or "AI 協作").strip()
    open_cursor = bool(params.get("open_cursor", True))
    open_antigravity = bool(params.get("open_antigravity", True))

    mcp_was_up = _cad_mcp_alive()
    if not mcp_was_up:
        _spawn_cad_mcp_background()
        for _ in range(12):
            time.sleep(0.25)
            if _cad_mcp_alive():
                mcp_was_up = True
                break

    ticket = _action_assist_create_ticket(
        {
            "source": "aegis",
            "type": "collaboration_session",
            "summary": f"協作會話: {topic}",
            "owner": "aegis",
            "priority": "normal",
            "payload": {
                "session": True,
                "topic": topic,
                "trigger": "開始AI協作",
                "collab_mode": "dialogue_until_conclusion",
            },
        }
    )
    tid = ticket.get("ticket_id", "")
    _action_assist_add_discussion(
        {
            "ticket_id": tid,
            "by": "aegis",
            "role": "facilitate",
            "content": (
                f"【協作開場】主題：{topic}。請 Antigravity 發表探索觀點（假設/風險/替代方案），"
                f"請 Cursor 發表收斂觀點（可行性/改動範圍/測試）。"
                f"三方對話達成共識後，由我綜述結論草案，師父認可後寫入主腦。"
            ),
        }
    )

    launched: Dict[str, str] = {}
    notes: List[str] = []
    if open_cursor:
        c = _launch_cursor()
        if c:
            launched["cursor"] = c
        else:
            notes.append("Cursor 未自動開啟，請手動開啟 cam-helper-tools 資料夾")
    if open_antigravity:
        a = _launch_antigravity()
        if a:
            launched["antigravity"] = a
        else:
            notes.append(
                "Antigravity 未自動開啟；可設環境變數 ANTIGRAVITY_EXE=你的 Antigravity.exe 路徑"
            )

    session = {
        "active": True,
        "started_at": _now_iso(),
        "topic": topic,
        "ticket_id": ticket.get("ticket_id"),
        "cad_mcp": f"http://{HOST}:{PORT}",
        "cad_mcp_was_running": mcp_was_up,
        "launched": launched,
        "notes": notes,
    }
    try:
        _INBOX_DIR.mkdir(parents=True, exist_ok=True)
        (_INBOX_DIR / "COLLAB_SESSION.json").write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tid = str(ticket.get("ticket_id", ""))
        (_INBOX_DIR / "PENDING_FOR_CURSOR.flag").write_text(tid, encoding="utf-8")
        (_INBOX_DIR / "PENDING_FOR_ANTIGRAVITY.flag").write_text(tid, encoding="utf-8")
        ag_md = (
            f"# Antigravity 協作 — ticket {tid}\n\n"
            f"主題：{topic}\n\n"
            f"請在 Antigravity 對話輸入：\n\n"
            f"```\n參與協作 {tid}\n探索輪：請就主題提出假設、風險、替代方案\n```\n\n"
            f"或執行：\n`python tools/antigravity_collab_post.py {tid} explore \"你的觀點\"`\n"
        )
        (_INBOX_DIR / "LATEST_FOR_ANTIGRAVITY.md").write_text(ag_md, encoding="utf-8")
    except Exception:
        pass

    t_full = _require_ticket(str(ticket.get("ticket_id", "")))

    return {
        "ok": True,
        "session": session,
        "ticket": _ticket_summary(t_full),
        "message_for_master": (
            "協作已啟動（對話直到結論）。Antigravity 與 Cursor 皆須在協作單發言；"
            "你繼續在 Ollama 跟我說即可。可說「協作進度」「繼續討論」「提出結論草案」。"
        ),
    }


def _action_assist_resolve_ticket(params: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        raise ApiError(400, "ticket_id is required")
    t = _require_ticket(ticket_id)

    if_match_rev = params.get("if_match_rev")
    if if_match_rev is not None and int(if_match_rev) != int(t["rev"]):
        raise ApiError(409, f"revision conflict: current={t['rev']} provided={if_match_rev}")

    if not bool(t.get("proposed_conclusion")):
        raise ApiError(
            409,
            "conclusion required: run assist_propose_conclusion after triad discussion",
        )
    if not bool(t.get("core_approved")):
        raise ApiError(
            409,
            "core approval required: set core_approved=true via assist_append_context before resolve",
        )

    t["status"] = "resolved"
    t["rev"] = _new_rev()
    t["updated_at"] = _now_iso()
    _append_event(
        t,
        "ticket_resolved",
        {"by": params.get("by", "unknown"), "note": params.get("note", "")},
    )
    _save_collab()
    _write_inboxes(t, event="resolved")
    for name in ("PENDING_FOR_CURSOR.flag", "PENDING_FOR_AEGIS.flag"):
        try:
            p = _INBOX_DIR / name
            if p.is_file():
                p.unlink()
        except Exception:
            pass
    return _ticket_summary(t)


_ACTIONS: List[Tuple[str, Any]] = [
    ("set_quote_facts", _action_set_facts),
    ("get_merged_facts", _action_get_merged_facts),
    ("run_quote", _action_run_quote),
    ("clear_quote_facts", _action_clear_facts),
    ("load_demo_sample", _action_demo_sample),
    ("assist_create_ticket", _action_assist_create_ticket),
    ("assist_get_ticket", _action_assist_get_ticket),
    ("assist_list_tickets", _action_assist_list_tickets),
    ("assist_get_events", _action_assist_get_events),
    ("assist_watch_tickets", _action_assist_watch_tickets),
    ("start_ai_collaboration", _action_start_ai_collaboration),
    ("assist_add_discussion", _action_assist_add_discussion),
    ("assist_get_discussion", _action_assist_get_discussion),
    ("assist_collab_status", _action_assist_collab_status),
    ("assist_propose_conclusion", _action_assist_propose_conclusion),
    ("assist_append_context", _action_assist_append_context),
    ("assist_resolve_ticket", _action_assist_resolve_ticket),
]


class MyHTTPServer(HTTPServer):
    allow_reuse_address = True

def main() -> None:
    print(f"Smart AI CAD MCP http://{HOST}:{PORT}", flush=True)
    server = MyHTTPServer((HOST, PORT), _Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
