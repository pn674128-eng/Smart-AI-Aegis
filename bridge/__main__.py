# -*- coding: utf-8 -*-
"""CLI: python -m bridge run --workspace PATH --task \"...\""""
from __future__ import annotations

import argparse
import json
import sys

from bridge.orchestrator import run_comodify


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    p = argparse.ArgumentParser(description="本機雙 SDK 協作橋 (9876 ticket)")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="執行一輪協同修改")
    run_p.add_argument("--workspace", "-w", required=True, help="本機工作區目錄")
    run_p.add_argument("--task", "-t", required=True, help="協同修改任務描述")
    run_p.add_argument("--ticket", help="沿用既有 ticket_id")
    run_p.add_argument("--master", default="", help="師父補充（寫入討論串）")
    run_p.add_argument("--skip-challenge", action="store_true", help="略過 Antigravity 覆核輪")
    run_p.add_argument("--no-boot-mcp", action="store_true", help="不自動啟動 9876")

    args = p.parse_args()
    if args.cmd == "run":
        r = run_comodify(
            args.workspace,
            args.task,
            ticket_id=args.ticket,
            master_note=args.master,
            skip_challenge=args.skip_challenge,
            ensure_mcp=not args.no_boot_mcp,
        )
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0 if r.get("success") else 1)


if __name__ == "__main__":
    main()
