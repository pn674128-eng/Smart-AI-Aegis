# -*- coding: utf-8 -*-
"""Cursor 協作發言 — 寫入 9876 討論串。

用法:
  python tools/cursor_collab_post.py <ticket_id> converge "收斂觀點..."
"""
from __future__ import annotations

import json
import sys
import urllib.request

def post(action: str, params: dict) -> dict:
    body = json.dumps({"action": action, "params": params}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:9876/",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    if len(sys.argv) < 4:
        print("用法: python tools/cursor_collab_post.py <ticket_id> converge \"觀點...\"")
        sys.exit(1)
    resp = post(
        "assist_add_discussion",
        {
            "ticket_id": sys.argv[1],
            "by": "cursor",
            "role": sys.argv[2],
            "content": " ".join(sys.argv[3:]).strip().strip('"'),
        },
    )
    print(json.dumps(resp, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
