# -*- coding: utf-8 -*-
"""Quick self-test (no NX GUI required). Run: python test_mcp.py"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", 9878


def call(action: str, params=None):
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.sendall((json.dumps({"action": action, "params": params or {}}) + "\n").encode("utf-8"))
    buf = b""
    while b"\n" not in buf:
        buf += s.recv(65536)
    s.close()
    return json.loads(buf.decode("utf-8"))


def main():
    # start server if not up
    try:
        call("get_addin_info")
    except OSError:
        proc = subprocess.Popen(
            [sys.executable, "-m", "smart_ai_nx.mcp_server"],
            cwd=str(ROOT.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.2)
        print("started mcp_server pid", proc.pid)

    tests = [
        ("get_cam_agent_manifest", {}),
        ("list_material_profiles", {}),
        ("nx_recommend_cut_method", {"material_profile": "carbon_steel", "stage": "rough"}),
        ("query_smart_cutting", {"material_profile": "carbon_steel", "tool_dia": 10, "operation": "face"}),
        ("check_semi_auto_eligibility", {
            "material_profile": "aluminum",
            "features": [
                {"category": "hole", "diameter_mm": 5.5},
                {"category": "hole", "diameter_mm": 5.5},
                {"category": "hole", "diameter_mm": 5.0},
                {"category": "hole", "diameter_mm": 5.0},
            ],
        }),
        ("get_semi_auto_plan", {
            "material_profile": "carbon_steel",
            "drawing_no": "TEST-001",
            "features": [
                {"category": "hole", "diameter_mm": 10, "tolerance": "H7"},
                {"category": "face_plane", "kind": "TOP_PLANAR"},
            ],
        }),
        ("nx_hole_cam_catalog", {}),
        ("nx_match_feature_cam", {
            "material_profile": "aluminum",
            "feature": {"category": "hole", "diameter_mm": 5.5, "through": True},
        }),
        ("get_plugin_config", {}),
    ]
    ok = 0
    for action, params in tests:
        r = call(action, params)
        good = r.get("success", False)
        ok += int(good)
        print(f"[{'OK' if good else 'FAIL'}] {action}")
        if not good:
            print(" ", r.get("error", r)[:200])
    print(f"\n{ok}/{len(tests)} passed")
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
