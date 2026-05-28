# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def format_thread(discussion: List[Dict[str, Any]]) -> str:
    lines = []
    for d in discussion:
        who = d.get("by", "?")
        role = d.get("role", "")
        content = d.get("content", "")
        lines.append(f"[{who}/{role}] {content}")
    return "\n".join(lines) if lines else "(尚無訊息)"


def read_prompt(name: str) -> str:
    p = Path(__file__).resolve().parent.parent / "triad_ui" / "prompts" / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def build_phase_prompt(
    *,
    phase: str,
    workspace: Path,
    task: str,
    thread: str,
    extra: str = "",
) -> str:
    ws = str(workspace.resolve())
    base = (
        f"工作區（本機絕對路徑）：{ws}\n"
        f"協同修改任務：{task}\n\n"
        f"=== 目前協作討論串 ===\n{thread}\n\n"
    )
    if phase == "explore":
        return (
            base
            + "=== 本輪：Antigravity 探索輪 ===\n"
            "禁止修改任何檔案。請繁體中文回覆：假設、風險、影響檔案/模組、建議 Cursor 實作範圍與驗證方式。\n"
            "開頭一行：backend=...\n"
            + extra
        )
    if phase == "challenge":
        return (
            base
            + "=== 本輪：Antigravity 覆核輪 ===\n"
            "禁止修改檔案。針對 Cursor 實作輪的總結：同意或質疑，須具體。\n"
            "開頭一行：backend=...\n"
            + extra
        )
    if phase == "implement":
        return (
            base
            + "=== 本輪：Cursor 實作輪 ===\n"
            "請在以上工作區內實際修改檔案以完成任務（不要只給空泛建議）。\n"
            "結束時繁體中文總結：改了哪些檔案、做了什麼、如何驗證。\n"
            "開頭一行：backend=...\n"
            + extra
        )
    if phase == "facilitate":
        return (
            base
            + "=== 本輪：Aegis 主持輪 ===\n"
            "整合 Antigravity 與 Cursor 觀點；指出是否可進入結論草案；不做最終核准。\n"
            "繁體中文，簡潔。\n"
            + extra
        )
    return base + extra
