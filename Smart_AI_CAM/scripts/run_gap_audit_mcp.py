# -*- coding: utf-8 -*-
"""
Run from Windows (Fusion + Smart_AI_CAM add-in loaded).
Fetches gap-audit pack via MCP and writes docs/_gap_audit_pack.json + markdown summary.

  python scripts/run_gap_audit_mcp.py
"""

from __future__ import annotations

import json
import os
import sys

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)

from scripts.fusion_ai_bridge import cam_call, HOST, PORT  # noqa: E402


def main() -> int:
    print("Smart_AI_CAM gap audit — MCP %s:%s" % (HOST, PORT))
    ping = cam_call("get_addin_info", {}, timeout=15.0)
    if not ping.get("success"):
        print("FAIL: MCP not reachable. Load add-in in Fusion first.")
        print(" ", ping.get("error", ping))
        return 1
    ver = (ping.get("data") or {}).get("version", "?")
    print("Add-in version:", ver)

    pack_resp = cam_call("get_fusion_ai_gap_audit_pack", {}, timeout=60.0)
    if not pack_resp.get("success"):
        print("FAIL:", pack_resp.get("error", pack_resp))
        return 1

    data = pack_resp.get("data") or pack_resp
    out_json = os.path.join(ADDIN_DIR, "docs", "_gap_audit_pack.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Wrote:", out_json)

    manifest = data.get("manifest") or data
    not_cov = manifest.get("fusion_cam_not_covered") or []
    md_path = os.path.join(ADDIN_DIR, "docs", "_gap_audit_brief.md")
    lines = [
        "# Smart_AI_CAM — 缺口稽核素材（給 Fusion AI）",
        "",
        "版本: %s" % ver,
        "",
        "## 使用方式",
        "1. 將 `_gap_audit_pack.json` 內容（或下方摘要）貼到 **Autodesk Assistant**",
        "2. 再貼 `manifest.gap_audit.assistant_prompt_zh` 中的提示詞",
        "3. 請 Assistant 產出繁體中文缺口報告",
        "",
        "## 插件明確未涵蓋（Fusion CAM 可能有）",
    ]
    for item in not_cov:
        lines.append("- **%s**：%s" % (item.get("area", "?"), item.get("note", "")))
    lines.extend([
        "",
        "## 建議 MCP 驗證順序",
    ])
    for step in (manifest.get("gap_audit") or {}).get("recommended_mcp_sequence") or []:
        lines.append("- `%s`" % step)
    lines.append("")
    lines.append("完整 JSON: `docs/_gap_audit_pack.json`")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Wrote:", md_path)
    print("OK — open Fusion Assistant and paste the prompt from the pack.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
