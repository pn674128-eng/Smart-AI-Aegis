# -*- coding: utf-8 -*-
"""Aegis 主持輪 — Ollama（主腦不搶改碼）。"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Tuple

from bridge.context import build_phase_prompt

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
AEGIS_MODEL = os.environ.get(
    "AEGIS_MODEL",
    os.environ.get("CAM_HELPER_MODEL", "smart-ai-aegis"),
)


def _candidate_ollama_exe() -> str | None:
    cands = [
        os.environ.get("OLLAMA_EXE", "").strip(),
        r"E:\Ollama\ollama.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
    ]
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


def _ensure_ollama_running(wait_sec: float = 5.0) -> bool:
    health = f"{OLLAMA_URL}/api/tags"
    try:
        with urllib.request.urlopen(health, timeout=2):
            return True
    except Exception:
        pass

    exe = _candidate_ollama_exe()
    if not exe:
        return False

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen(
            [exe, "serve"],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=2):
                return True
        except Exception:
            time.sleep(0.4)
    return False


def ollama_chat(model: str, system: str, user_content: str, *, timeout: float = 180.0) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError:
        # Auto-heal: try to boot ollama serve once.
        if not _ensure_ollama_running():
            raise
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    return (data.get("message") or {}).get("content", "").strip() or "(無回覆)"


def run_aegis_facilitate(
    *,
    workspace,
    task: str,
    thread: str,
) -> Tuple[str, str]:
    prompt = build_phase_prompt(
        phase="facilitate",
        workspace=workspace,
        task=task,
        thread=thread,
    )
    system = (
        "你是 Smart AI Aegis (v5 R13) 協作主腦。主持三方、整合探索與實作，"
        "不代替師父 core_approved，不假裝已改檔。繁體中文。"
    )
    text = ollama_chat(AEGIS_MODEL, system, prompt)
    return f"backend=ollama-aegis\n{text}", "ollama-aegis"
