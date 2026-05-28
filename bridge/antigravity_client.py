# -*- coding: utf-8 -*-
"""Antigravity 協作客戶端（預設嚴格：SDK 不可用即阻塞，不假補位）。"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Tuple

from bridge.context import build_phase_prompt, read_prompt


def _strict_mode_enabled() -> bool:
    return os.environ.get("BRIDGE_STRICT_NON_AEGIS", "1").strip().lower() not in ("0", "false", "no")


def _blocked(reason: str) -> Tuple[str, str]:
    text = (
        "backend=blocked\n"
        "【阻塞】Antigravity SDK 不可用，已依嚴格模式停止此輪，避免以 Ollama 假冒探索/覆核。\n"
        f"原因：{reason}\n"
        "處理：安裝/修復 google-antigravity（或在可用環境執行），再重跑協作。"
    )
    return text, "blocked"


def _ollama_fallback(prompt: str) -> Tuple[str, str]:
    from bridge.aegis_client import ollama_chat

    system = read_prompt("antigravity_system.txt") or "你是 Antigravity 探索通道。"
    text = ollama_chat(
        os.environ.get("ANTIGRAVITY_MODEL", os.environ.get("AEGIS_MODEL", "smart-ai-aegis")),
        system,
        prompt,
    )
    return text, "ollama-fallback"


def run_antigravity(
    *,
    phase: str,
    workspace: Path,
    task: str,
    thread: str,
) -> Tuple[str, str]:
    """回傳 (content, backend)。"""
    prompt = build_phase_prompt(
        phase=phase,
        workspace=workspace,
        task=task,
        thread=thread,
    )
    if os.environ.get("BRIDGE_AG_MODE", "sdk").lower() in ("ollama", "off", "0"):
        if _strict_mode_enabled():
            return _blocked("BRIDGE_AG_MODE=ollama/off")
        text, be = _ollama_fallback(prompt)
        return f"backend={be}\n{text}", be

    try:
        from google.antigravity import Agent, LocalAgentConfig
    except ImportError:
        if _strict_mode_enabled():
            return _blocked("google-antigravity 未安裝或無可用 wheel")
        text, be = _ollama_fallback(prompt)
        return f"backend={be} (google-antigravity 未安裝)\n{text}", be

    system = read_prompt("antigravity_system.txt") or (
        "你是 Antigravity 協作探索者。預設不修改檔案，只分析與審查。繁體中文。"
    )

    async def _run() -> str:
        cfg = LocalAgentConfig(
            system_instructions=system,
            workspaces=[str(workspace.resolve())],
        )
        async with Agent(cfg) as agent:
            response = await agent.chat(prompt)
            return (await response.text()).strip()

    try:
        text = asyncio.run(_run())
        return f"backend=google-antigravity\n{text}", "google-antigravity"
    except Exception as e:
        if _strict_mode_enabled():
            return _blocked(f"SDK 錯誤: {e}")
        text, be = _ollama_fallback(prompt)
        return f"backend={be} (SDK 錯誤: {e})\n{text}", be
