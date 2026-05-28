# -*- coding: utf-8 -*-
"""Antigravity 協作發言 — 寫入 9876 討論串。

用法:
  python tools/antigravity_collab_post.py <ticket_id> explore "你的探索觀點..."
  python tools/antigravity_collab_post.py <ticket_id> challenge "對 Cursor 方案的質疑..."
"""
from __future__ import annotations

import json
import sys
import urllib.request

HOST = "127.0.0.1"
PORT = 9876


def post(action: str, params: dict) -> dict:
    body = json.dumps({"action": action, "params": params}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    ticket_id = sys.argv[1]
    role = sys.argv[2]
    content = " ".join(sys.argv[3:]).strip().strip('"')
    resp = post(
        "assist_add_discussion",
        {
            "ticket_id": ticket_id,
            "by": "antigravity",
            "role": role,
            "content": content,
        },
    )
    print(json.dumps(resp, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
