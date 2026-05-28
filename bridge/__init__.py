# -*- coding: utf-8 -*-
"""本機雙 SDK 協作橋 — Antigravity 探索 + Cursor 實作 + 9876 ticket。"""

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # python-dotenv is optional at runtime.
    pass

from bridge.orchestrator import run_comodify

__all__ = ["run_comodify"]
