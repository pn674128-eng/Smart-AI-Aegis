# -*- coding: utf-8 -*-
"""Cursor 協作客戶端（預設嚴格：SDK 不可用即阻塞，不假補位）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from bridge.context import build_phase_prompt, read_prompt


def _strict_mode_enabled() -> bool:
    return os.environ.get("BRIDGE_STRICT_NON_AEGIS", "1").strip().lower() not in ("0", "false", "no")


def _blocked(reason: str) -> Tuple[str, str]:
    text = (
        "backend=blocked\n"
        "【阻塞】Cursor SDK 不可用，已依嚴格模式停止實作輪，避免以 Ollama 假冒改檔。\n"
        f"原因：{reason}\n"
        "處理：修復 SDK/runtime，或改由 Cursor 對話窗人工真改檔並回寫 ticket。"
    )
    return text, "blocked"


def _is_local_bridge_socket_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10038:
        return True
    msg = str(exc).lower()
    return "10038" in msg or "socket" in msg


def _ollama_fallback(prompt: str, *, reason: str = "") -> Tuple[str, str]:
    from bridge.aegis_client import ollama_chat

    system = read_prompt("cursor_system.txt") or "你是 Cursor 收斂通道。"
    note = (
        "【備援模式】你無法直接寫入磁碟。請給出可執行的改動清單與具體路徑，"
        "供工程師或 Cursor IDE 套用。\n\n"
    )
    if reason:
        note += f"【原因】{reason}\n\n"
    text = ollama_chat(
        os.environ.get("CURSOR_MODEL", os.environ.get("AEGIS_MODEL", "smart-ai-aegis")),
        system,
        note + prompt,
    )
    return text, "ollama-fallback"


def _run_cursor_sdk_prompt(
    prompt: str,
    *,
    api_key: str,
    model: str,
    workspace: Path,
) -> Tuple[str, str]:
    from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, CloudRepository, LocalAgentOptions

    mode = os.environ.get("BRIDGE_CURSOR_RUNTIME", "local").strip().lower()
    if mode == "http":
        raise RuntimeError(
            "BRIDGE_CURSOR_RUNTIME=http 尚未實作（目前僅支援 local/cloud/auto）。"
            " 請改用 BRIDGE_CURSOR_MODE=ollama，或提供 Cursor Cloud REST 端點規格後再接入。"
        )

    if mode == "cloud" or (mode == "auto" and sys.platform == "win32"):
        repo_url = os.environ.get("CURSOR_CLOUD_REPO", "").strip()
        if repo_url:
            result = Agent.prompt(
                prompt,
                AgentOptions(
                    api_key=api_key,
                    model=model,
                    cloud=CloudAgentOptions(
                        repos=[CloudRepository(url=repo_url)],
                        auto_create_pr=bool(
                            os.environ.get("CURSOR_CLOUD_AUTO_PR", "").lower()
                            in ("1", "true", "yes")
                        ),
                    ),
                ),
            )
            body = getattr(result, "result", None) or str(result)
            status = getattr(result, "status", "unknown")
            return (
                f"backend=cursor-sdk-cloud\nstatus={status}\n{body}".strip(),
                "cursor-sdk-cloud",
            )

    if mode not in ("cloud",):
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=str(workspace.resolve())),
            ),
        )
        body = getattr(result, "result", None) or str(result)
        status = getattr(result, "status", "unknown")
        return f"backend=cursor-sdk-local\nstatus={status}\n{body}".strip(), "cursor-sdk-local"

    raise RuntimeError("cloud 模式需要設定 CURSOR_CLOUD_REPO（Git 遠端 URL）")


def run_cursor_implement(
    *,
    workspace: Path,
    task: str,
    thread: str,
) -> Tuple[str, str]:
    prompt = build_phase_prompt(
        phase="implement",
        workspace=workspace,
        task=task,
        thread=thread,
    )
    if os.environ.get("BRIDGE_CURSOR_MODE", "sdk").lower() in ("ollama", "off", "0"):
        if _strict_mode_enabled():
            return _blocked("BRIDGE_CURSOR_MODE=ollama/off")
        text, be = _ollama_fallback(prompt)
        return f"backend={be}\n{text}", be

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        if _strict_mode_enabled():
            return _blocked("未設定 CURSOR_API_KEY")
        text, be = _ollama_fallback(prompt, reason="未設定 CURSOR_API_KEY")
        return f"backend={be}\n{text}", be

    try:
        from cursor_sdk import Agent  # noqa: F401
    except ImportError:
        if _strict_mode_enabled():
            return _blocked("cursor-sdk 未安裝")
        text, be = _ollama_fallback(prompt, reason="cursor-sdk 未安裝")
        return f"backend={be}\n{text}", be

    model = os.environ.get("CURSOR_SDK_MODEL", "composer-2.5")
    try:
        text, backend = _run_cursor_sdk_prompt(
            prompt, api_key=api_key, model=model, workspace=workspace
        )
        return text, backend
    except Exception as e:
        if _strict_mode_enabled():
            return _blocked(f"SDK 錯誤: {e}")
        win_note = ""
        if _is_local_bridge_socket_error(e):
            win_note = (
                "Windows 上 cursor-sdk 本機 bridge 已知 WinError 10038。"
                "解法：(1) 設 CURSOR_CLOUD_REPO=你的GitHub倉庫URL 且 BRIDGE_CURSOR_RUNTIME=cloud；"
                "(2) 或用本 Cursor 對話窗直接改檔；"
                "(3) 或 BRIDGE_CURSOR_MODE=ollama 僅跑協作票。"
            )
        text, be = _ollama_fallback(prompt, reason=f"{e}. {win_note}".strip())
        return f"backend={be}\n{text}", be
