# -*- coding: utf-8 -*-
"""四方協作編排：9876 ticket + Ollama 三通道。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS = Path(__file__).resolve().parent / "prompts"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
AEGIS_MODEL = os.environ.get(
    "AEGIS_MODEL",
    os.environ.get("CAM_HELPER_MODEL", "smart-ai-aegis"),
)
AG_MODEL = os.environ.get("ANTIGRAVITY_MODEL", AEGIS_MODEL)
CURSOR_MODEL = os.environ.get("CURSOR_MODEL", AEGIS_MODEL)
CAD_MCP = os.environ.get("CAD_MCP_URL", "http://127.0.0.1:9876/")


def _cad_post(action: str, params: Optional[dict] = None) -> Dict[str, Any]:
    body = json.dumps({"action": action, "params": params or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        CAD_MCP,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("ok"):
            return {"success": True, "result": data.get("result")}
        return {"success": False, "error": data.get("error", "unknown")}
    except Exception as e:
        return {"success": False, "error": str(e), "offline": True}


def _read_prompt(name: str) -> str:
    p = _PROMPTS / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _format_thread(discussion: List[Dict[str, Any]]) -> str:
    lines = []
    for d in discussion:
        who = d.get("by", "?")
        role = d.get("role", "")
        content = d.get("content", "")
        lines.append(f"[{who}/{role}] {content}")
    return "\n".join(lines) if lines else "(尚無訊息)"


def _ollama_chat(model: str, system: str, user_content: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.35},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message") or {}).get("content", "").strip() or "(無回覆)"


def _party_reply(
    party: str,
    model: str,
    system_file: str,
    discussion: List[Dict[str, Any]],
    master_line: str,
    topic: str,
) -> str:
    thread = _format_thread(discussion)
    user_block = (
        f"協作主題：{topic}\n\n"
        f"=== 目前討論串 ===\n{thread}\n\n"
        f"=== 師父剛說 ===\n{master_line}\n\n"
        f"請以【{party}】身份回覆本輪。"
    )
    return _ollama_chat(model, _read_prompt(system_file), user_block)


def start_session(topic: str = "四方協作") -> Dict[str, Any]:
    r = _cad_post(
        "start_ai_collaboration",
        {"topic": topic, "open_cursor": False, "open_antigravity": False},
    )
    if not r.get("success"):
        return r
    return {"success": True, "session": r.get("result")}


def get_session_state() -> Dict[str, Any]:
    inbox = _ROOT / "store" / "inbox" / "COLLAB_SESSION.json"
    if inbox.is_file():
        try:
            return json.loads(inbox.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_discussion(ticket_id: str) -> Dict[str, Any]:
    return _cad_post("assist_get_discussion", {"ticket_id": ticket_id})


def broadcast_master_message(
    ticket_id: str,
    text: str,
    *,
    reply_antigravity: bool = True,
    reply_cursor: bool = True,
    reply_aegis: bool = True,
) -> Dict[str, Any]:
    _cad_post(
        "assist_add_discussion",
        {"ticket_id": ticket_id, "by": "master", "role": "theory", "content": text},
    )
    disc = get_discussion(ticket_id)
    if not disc.get("success"):
        return disc
    result = disc.get("result") or {}
    discussion: List[Dict[str, Any]] = list(result.get("discussion") or [])
    topic = (get_session_state().get("topic") or "協作")

    replies: Dict[str, str] = {}

    def _run_ag():
        return _party_reply(
            "antigravity", AG_MODEL, "antigravity_system.txt", discussion, text, topic
        )

    def _run_cu():
        return _party_reply(
            "cursor", CURSOR_MODEL, "cursor_system.txt", discussion, text, topic
        )

    def _run_ae():
        aegis_sys = (
            "你是 Smart AI Aegis (主腦)。主持協作、整合 Antigravity 探索與 Cursor 收斂，"
            "回覆師父，繁體中文。可指出下一步與是否可進入結論草案階段。"
        )
        thread = _format_thread(discussion)
        user_block = (
            f"主題：{topic}\n\n討論串：\n{thread}\n\n師父：{text}\n\n請以 Aegis 主持回覆。"
        )
        return _ollama_chat(AEGIS_MODEL, aegis_sys, user_block)

    tasks = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        if reply_antigravity:
            tasks[ex.submit(_run_ag)] = "antigravity"
        if reply_cursor:
            tasks[ex.submit(_run_cu)] = "cursor"
        if reply_aegis:
            tasks[ex.submit(_run_ae)] = "aegis"
        for fut in as_completed(tasks):
            party = tasks[fut]
            try:
                replies[party] = fut.result()
            except Exception as e:
                replies[party] = f"[錯誤] {e}"

    role_map = {
        "antigravity": ("antigravity", "explore"),
        "cursor": ("cursor", "converge"),
        "aegis": ("aegis", "facilitate"),
    }
    for party, content in replies.items():
        by, role = role_map[party]
        _cad_post(
            "assist_add_discussion",
            {"ticket_id": ticket_id, "by": by, "role": role, "content": content},
        )

    disc2 = get_discussion(ticket_id)
    status = _cad_post("assist_collab_status", {"ticket_id": ticket_id})
    return {
        "success": True,
        "replies": replies,
        "discussion": (disc2.get("result") or {}).get("discussion"),
        "collab_status": status.get("result"),
    }


def propose_conclusion(ticket_id: str, conclusion: str) -> Dict[str, Any]:
    return _cad_post(
        "assist_propose_conclusion",
        {"ticket_id": ticket_id, "conclusion": conclusion, "by": "aegis"},
    )


def approve_and_resolve(ticket_id: str, rev: int) -> Dict[str, Any]:
    _cad_post(
        "assist_append_context",
        {
            "ticket_id": ticket_id,
            "if_match_rev": rev,
            "by": "aegis",
            "patch": {"core_approved": True},
        },
    )
    disc = get_discussion(ticket_id)
    rev2 = int((disc.get("result") or {}).get("rev", rev))
    return _cad_post(
        "assist_resolve_ticket",
        {"ticket_id": ticket_id, "if_match_rev": rev2, "note": "master approved via triad UI"},
    )
