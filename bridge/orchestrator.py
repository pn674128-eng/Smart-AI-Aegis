# -*- coding: utf-8 -*-
"""
本機雙 SDK 協作橋編排。

phase: master → explore(AG) → implement(Cursor) → challenge(AG) → facilitate(Aegis)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from bridge.aegis_client import run_aegis_facilitate
from bridge.antigravity_client import run_antigravity
from bridge.cad_client import cad_post, ensure_cad_mcp
from bridge.context import format_thread
from bridge.cursor_client import run_cursor_implement

_COLLAB_JSON = Path(__file__).resolve().parent.parent / "Smart AI CAD" / "store" / "collab_tickets.json"


def _discussion_from_store(ticket_id: str) -> Optional[List[Dict[str, Any]]]:
    try:
        if not _COLLAB_JSON.is_file():
            return None
        data = json.loads(_COLLAB_JSON.read_text(encoding="utf-8"))
        t = (data.get("tickets") or {}).get(ticket_id)
        if t:
            return list(t.get("discussion") or [])
    except Exception:
        pass
    return None


def _discussion_list(ticket_id: str) -> List[Dict[str, Any]]:
    r = cad_post("assist_get_discussion", {"ticket_id": ticket_id})
    if not r.get("success"):
        return []
    return list((r.get("result") or {}).get("discussion") or [])


def _add_turn(
    ticket_id: str,
    *,
    by: str,
    role: str,
    content: str,
) -> Dict[str, Any]:
    return cad_post(
        "assist_add_discussion",
        {"ticket_id": ticket_id, "by": by, "role": role, "content": content},
    )


def _patch_payload(ticket_id: str, rev: int, patch: dict) -> None:
    cad_post(
        "assist_append_context",
        {
            "ticket_id": ticket_id,
            "if_match_rev": rev,
            "by": "bridge",
            "patch": {"payload": patch},
        },
    )


def _is_blocked_backend(backend: str) -> bool:
    return str(backend).strip().lower() in ("blocked", "error", "unavailable")


def _require_file_change_enabled() -> bool:
    return os.environ.get("BRIDGE_REQUIRE_FILE_CHANGE", "1").strip().lower() not in ("0", "false", "no")


def _collect_git_change_evidence(workspace: Path) -> Dict[str, Any]:
    """Return git-backed file change evidence. If repo unavailable, mark unsupported."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0 or inside.stdout.strip().lower() != "true":
            return {"supported": False, "reason": "workspace is not a git work tree"}

        changed = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        files = []
        for out in (changed.stdout, staged.stdout, untracked.stdout):
            for line in (out or "").splitlines():
                s = line.strip()
                if s and s not in files:
                    files.append(s)
        return {"supported": True, "files": files, "count": len(files)}
    except Exception as e:
        return {"supported": False, "reason": f"git evidence error: {e}"}


def _extract_target_paths(ticket_payload: Dict[str, Any]) -> List[str]:
    # 支援多種鍵名，避免舊票不相容
    raw = (
        ticket_payload.get("target_paths")
        or ticket_payload.get("target_files")
        or ticket_payload.get("expected_files")
        or []
    )
    out: List[str] = []
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        for x in raw:
            s = str(x).strip().replace("\\", "/")
            if s:
                out.append(s)
    return out


def _match_target_paths(changed_files: List[str], targets: List[str]) -> Dict[str, Any]:
    changed_norm = [str(f).strip().replace("\\", "/") for f in changed_files]
    matched_targets: List[str] = []
    matched_files: List[str] = []
    for t in targets:
        t_norm = t.strip().replace("\\", "/")
        hit = [f for f in changed_norm if f == t_norm or f.startswith(t_norm.rstrip("/") + "/")]
        if hit:
            matched_targets.append(t)
            for h in hit:
                if h not in matched_files:
                    matched_files.append(h)
    return {
        "required_targets": targets,
        "matched_targets": matched_targets,
        "matched_files": matched_files,
        "ok": len(matched_targets) > 0,
    }


def run_comodify(
    workspace: str | Path,
    task: str,
    *,
    ticket_id: Optional[str] = None,
    master_note: str = "",
    skip_challenge: bool = False,
    ensure_mcp: bool = True,
) -> Dict[str, Any]:
    """
    執行一輪完整本機協同修改。

    回傳 dict 含 ticket_id、各 phase backend、collab_status。
    """
    ws = Path(workspace).expanduser().resolve()
    if not ws.is_dir():
        return {"success": False, "error": f"工作區不存在: {ws}"}

    task = (task or "").strip()
    if not task:
        return {"success": False, "error": "task 不可為空"}

    if ensure_mcp:
        boot = ensure_cad_mcp()
        if not boot.get("success"):
            return {"success": False, "error": boot.get("error"), "offline": True}

    backends: Dict[str, str] = {}
    phases_run: List[str] = []

    if ticket_id:
        tid = ticket_id.strip()
        disc = cad_post("assist_get_discussion", {"ticket_id": tid})
        if not disc.get("success"):
            return {"success": False, "error": f"找不到 ticket: {tid}"}
    else:
        created = cad_post(
            "assist_create_ticket",
            {
                "source": "bridge",
                "type": "plugin_change",
                "summary": f"協同修改: {task[:200]}",
                "owner": "cursor",
                "priority": "normal",
                "payload": {
                    "workspace": str(ws),
                    "task": task,
                    "bridge": "local_dual_sdk",
                    "phase": "open",
                },
            },
        )
        if not created.get("success"):
            return {"success": False, "error": created.get("error", "建票失敗")}
        tid = str((created.get("result") or {}).get("ticket_id", ""))
        if not tid:
            return {"success": False, "error": "建票未回傳 ticket_id"}

    master_line = master_note.strip() or f"協同修改：{task}"
    _add_turn(tid, by="master", role="theory", content=master_line)
    phases_run.append("master")

    thread = format_thread(_discussion_list(tid))

    # Phase 1 — Antigravity explore
    ag_text, ag_be = run_antigravity(phase="explore", workspace=ws, task=task, thread=thread)
    backends["explore"] = ag_be
    _add_turn(tid, by="antigravity", role="explore", content=ag_text)
    phases_run.append("explore")
    if _is_blocked_backend(ag_be):
        ticket = cad_post("assist_get_ticket", {"ticket_id": tid})
        rev = int((ticket.get("result") or {}).get("rev", 0))
        _patch_payload(
            tid,
            rev,
            {
                "workspace": str(ws),
                "task": task,
                "bridge": "local_dual_sdk",
                "phase": "blocked_explore",
                "backends": backends,
                "blocked_reason": "Antigravity SDK unavailable",
            },
        )
        return {
            "success": False,
            "ticket_id": tid,
            "workspace": str(ws),
            "task": task,
            "phases_run": phases_run,
            "backends": backends,
            "blocked_phase": "explore",
            "message": "協同已阻塞：Antigravity SDK 不可用（嚴格模式禁止 fallback）。",
        }
    thread = format_thread(_discussion_list(tid))

    # Phase 2 — Cursor implement
    cu_text, cu_be = run_cursor_implement(workspace=ws, task=task, thread=thread)
    backends["implement"] = cu_be
    _add_turn(tid, by="cursor", role="converge", content=cu_text)
    phases_run.append("implement")
    if _is_blocked_backend(cu_be):
        ticket = cad_post("assist_get_ticket", {"ticket_id": tid})
        rev = int((ticket.get("result") or {}).get("rev", 0))
        _patch_payload(
            tid,
            rev,
            {
                "workspace": str(ws),
                "task": task,
                "bridge": "local_dual_sdk",
                "phase": "blocked_implement",
                "backends": backends,
                "blocked_reason": "Cursor SDK unavailable",
            },
        )
        return {
            "success": False,
            "ticket_id": tid,
            "workspace": str(ws),
            "task": task,
            "phases_run": phases_run,
            "backends": backends,
            "blocked_phase": "implement",
            "message": "協同已阻塞：Cursor SDK 不可用（嚴格模式禁止 fallback）。",
        }
    if _require_file_change_enabled():
        evidence = _collect_git_change_evidence(ws)
        if evidence.get("supported") and int(evidence.get("count", 0)) < 1:
            ticket = cad_post("assist_get_ticket", {"ticket_id": tid})
            rev = int((ticket.get("result") or {}).get("rev", 0))
            _patch_payload(
                tid,
                rev,
                {
                    "workspace": str(ws),
                    "task": task,
                    "bridge": "local_dual_sdk",
                    "phase": "blocked_evidence",
                    "backends": backends,
                    "blocked_reason": "no real file change evidence",
                    "change_evidence": evidence,
                },
            )
            _add_turn(
                tid,
                by="aegis",
                role="facilitate",
                content=(
                    "backend=blocked\n"
                    "【阻塞】未偵測到真實檔案變更（git diff/untracked 皆為空），"
                    "依規則禁止進入結案流程。請先完成實際改檔後重跑。"
                ),
            )
            return {
                "success": False,
                "ticket_id": tid,
                "workspace": str(ws),
                "task": task,
                "phases_run": phases_run,
                "backends": backends,
                "blocked_phase": "evidence",
                "change_evidence": evidence,
                "message": "協同已阻塞：缺少真實檔案變更證據。",
            }
        # 若 ticket 指定目標路徑，需命中至少一個
        ticket_now = cad_post("assist_get_ticket", {"ticket_id": tid})
        payload_now = (ticket_now.get("result") or {}).get("payload") or {}
        targets = _extract_target_paths(payload_now if isinstance(payload_now, dict) else {})
        if targets and evidence.get("supported"):
            target_check = _match_target_paths(evidence.get("files") or [], targets)
            if not target_check.get("ok"):
                rev = int((ticket_now.get("result") or {}).get("rev", 0))
                _patch_payload(
                    tid,
                    rev,
                    {
                        "workspace": str(ws),
                        "task": task,
                        "bridge": "local_dual_sdk",
                        "phase": "blocked_target_paths",
                        "backends": backends,
                        "blocked_reason": "file changes did not hit required target paths",
                        "change_evidence": evidence,
                        "target_check": target_check,
                    },
                )
                _add_turn(
                    tid,
                    by="aegis",
                    role="facilitate",
                    content=(
                        "backend=blocked\n"
                        "【阻塞】已偵測到檔案變更，但未命中此工單指定的 target_paths/target_files。"
                        "請依工單目標路徑實際改檔後重跑。"
                    ),
                )
                return {
                    "success": False,
                    "ticket_id": tid,
                    "workspace": str(ws),
                    "task": task,
                    "phases_run": phases_run,
                    "backends": backends,
                    "blocked_phase": "target_paths",
                    "change_evidence": evidence,
                    "target_check": target_check,
                    "message": "協同已阻塞：變更未命中指定目標路徑。",
                }
        if not evidence.get("supported"):
            _add_turn(
                tid,
                by="aegis",
                role="facilitate",
                content=(
                    "backend=ollama-aegis\n"
                    f"【提示】無法執行 git 證據檢查：{evidence.get('reason','unknown')}。"
                    "建議改用 git 工作區，或手動提供改檔證據。"
                ),
            )
    thread = format_thread(_discussion_list(tid))

    # Phase 3 — Antigravity challenge
    if not skip_challenge:
        ch_text, ch_be = run_antigravity(phase="challenge", workspace=ws, task=task, thread=thread)
        backends["challenge"] = ch_be
        _add_turn(tid, by="antigravity", role="challenge", content=ch_text)
        phases_run.append("challenge")
        if _is_blocked_backend(ch_be):
            ticket = cad_post("assist_get_ticket", {"ticket_id": tid})
            rev = int((ticket.get("result") or {}).get("rev", 0))
            _patch_payload(
                tid,
                rev,
                {
                    "workspace": str(ws),
                    "task": task,
                    "bridge": "local_dual_sdk",
                    "phase": "blocked_challenge",
                    "backends": backends,
                    "blocked_reason": "Antigravity SDK unavailable",
                },
            )
            return {
                "success": False,
                "ticket_id": tid,
                "workspace": str(ws),
                "task": task,
                "phases_run": phases_run,
                "backends": backends,
                "blocked_phase": "challenge",
                "message": "協同已阻塞：Antigravity challenge 不可用（嚴格模式禁止 fallback）。",
            }
        thread = format_thread(_discussion_list(tid))

    # Phase 4 — Aegis facilitate
    ae_text, ae_be = run_aegis_facilitate(workspace=ws, task=task, thread=thread)
    backends["facilitate"] = ae_be
    _add_turn(tid, by="aegis", role="facilitate", content=ae_text)
    phases_run.append("facilitate")

    ticket = cad_post("assist_get_ticket", {"ticket_id": tid})
    rev = int((ticket.get("result") or {}).get("rev", 0))
    _patch_payload(
        tid,
        rev,
        {
            "workspace": str(ws),
            "task": task,
            "bridge": "local_dual_sdk",
            "phase": "facilitate_done",
            "backends": backends,
        },
    )

    status = cad_post("assist_collab_status", {"ticket_id": tid})
    disc_final = cad_post("assist_get_discussion", {"ticket_id": tid})
    discussion_out = (disc_final.get("result") or {}).get("discussion")
    collab_out = status.get("result")
    if discussion_out is None:
        discussion_out = _discussion_from_store(tid)
    if collab_out is None and discussion_out:
        collab_out = cad_post("assist_collab_status", {"ticket_id": tid}).get("result")

    # 更新協作會話檔（與 start_ai_collaboration 相容）
    try:
        inbox = Path(__file__).resolve().parent.parent / "store" / "inbox" / "COLLAB_SESSION.json"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        session = {
            "active": True,
            "topic": task[:120],
            "ticket_id": tid,
            "workspace": str(ws),
            "bridge": "local_dual_sdk",
            "backends": backends,
        }
        inbox.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "success": True,
        "ticket_id": tid,
        "workspace": str(ws),
        "task": task,
        "phases_run": phases_run,
        "backends": backends,
        "collab_status": collab_out,
        "discussion": discussion_out,
        "message": (
            f"協同修改完成。ticket={tid}。"
            f"實作 backend={backends.get('implement')}。"
            "師父可說「提出結論草案」或於 UI 結案。"
        ),
    }
