# -*- coding: utf-8 -*-
"""診斷本機橋能否使用真實 SDK。python -m bridge.diagnose"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=== Local AI Bridge 診斷 ===\n")

    key = os.environ.get("CURSOR_API_KEY", "").strip()
    print(f"CURSOR_API_KEY: {'已設定 (' + str(len(key)) + ' 字元)' if key else '未設定'}")
    print(f"GEMINI_API_KEY:   {'已設定' if os.environ.get('GEMINI_API_KEY', '').strip() else '未設定'}")
    print(f"BRIDGE_CURSOR_MODE: {os.environ.get('BRIDGE_CURSOR_MODE', 'sdk')}")
    print(f"BRIDGE_AG_MODE:     {os.environ.get('BRIDGE_AG_MODE', 'sdk')}\n")
    print(f"BRIDGE_STRICT_NON_AEGIS: {os.environ.get('BRIDGE_STRICT_NON_AEGIS', '1')}")
    print(f"BRIDGE_REQUIRE_FILE_CHANGE: {os.environ.get('BRIDGE_REQUIRE_FILE_CHANGE', '1')}")

    try:
        import cursor_sdk  # noqa: F401

        print("cursor-sdk: 已安裝")
    except ImportError:
        print("cursor-sdk: 未安裝 → pip install cursor-sdk")

    try:
        import google.antigravity  # noqa: F401

        print("google-antigravity: 已安裝")
    except ImportError:
        print("google-antigravity: 未安裝或無 Windows wheel → pip install google-antigravity 或 BRIDGE_AG_MODE=ollama")

    from bridge.cad_client import cad_mcp_alive

    print(f"\nCAD MCP 9876: {'在線' if cad_mcp_alive() else '離線 → Start-Smart-AI-CAD-MCP.bat'}\n")

    runtime = os.environ.get("BRIDGE_CURSOR_RUNTIME", "local").strip().lower()
    print(f"BRIDGE_CURSOR_RUNTIME: {runtime} (Windows 建議 cloud 或 auto+CURSOR_CLOUD_REPO)")
    print(f"CURSOR_CLOUD_REPO: {'已設定' if os.environ.get('CURSOR_CLOUD_REPO', '').strip() else '未設定'}")
    if runtime == "http":
        print("注意：http runtime 目前尚未在 bridge 實作，會改走備援路徑。")

    if key:
        try:
            from bridge.cursor_client import _run_cursor_sdk_prompt

            text, backend = _run_cursor_sdk_prompt(
                "只回覆 OK",
                api_key=key,
                model=os.environ.get("CURSOR_SDK_MODEL", "composer-2.5"),
                workspace=Path(os.getcwd()),
            )
            print(f"Cursor SDK 試連: backend={backend}")
            print(text[:300])
        except Exception as e:
            print(f"Cursor SDK 試連失敗: {e}")
            if sys.platform == "win32":
                print(
                    "  → WinError 10038 為 cursor-sdk 本機 bridge 在 Windows 的已知問題；"
                    "請設 CURSOR_CLOUD_REPO 並 BRIDGE_CURSOR_RUNTIME=cloud，或改用 Cursor IDE 改檔。"
                )
    else:
        print("Cursor SDK 試連: 略過（無金鑰）")


if __name__ == "__main__":
    main()
