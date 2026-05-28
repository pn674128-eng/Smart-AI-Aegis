# -*- coding: utf-8 -*-
"""
批次匯入 E:\\Fusion\\參考範本 全部參考檔至 KnowledgeDB（MCP 127.0.0.1:9877）。

用法:
  python scripts/batch_import_all_references.py
  python scripts/batch_import_all_references.py --material S50C
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOST = "127.0.0.1"
PORT = 9877
DEFAULT_TIMEOUT = 600.0
LOG_PATH = r"E:\Fusion\參考範本\batch_import_run.log"
STATE_PATH = r"E:\Fusion\參考範本\batch_import_state.json"
MANIFEST_PATH = r"E:\Fusion\參考範本\manifest.json"


def log(msg: str, also_print: bool = True) -> None:
    line = "[{}] {}".format(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if also_print:
        print(line, flush=True)


def send_request(action: str, params=None, timeout: float = DEFAULT_TIMEOUT) -> dict:
    params = params or {}
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect((HOST, PORT))
    client.sendall((json.dumps({"action": action, "params": params}) + "\n").encode("utf-8"))
    buffer = ""
    while True:
        data = client.recv(1048576)
        if not data:
            break
        buffer += data.decode("utf-8")
        if "\n" in buffer:
            break
    client.close()
    if not buffer.strip():
        return {"success": False, "error": "empty response"}
    return json.loads(buffer.strip())


def queue_counts_from_disk():
    """Fusion 忙碌時 MCP status 可能異常，以磁碟狀態為準。"""
    total = 117
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            total = int(json.load(f).get("count") or total)
    except Exception:
        pass
    completed_n = 0
    failed_n = 0
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            st = json.load(f)
        completed_n = len(st.get("completed") or [])
        failed_n = len(st.get("failed") or [])
    except Exception:
        pass
    pending = max(0, total - completed_n)
    return pending, completed_n, failed_n, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", default="AL6061")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--keep-completed",
        type=int,
        default=0,
        help="僅保留 manifest 前 N 檔為已完成（例如 6 = 自第 7 檔重跑）",
    )
    args = ap.parse_args()
    req_timeout = float(args.timeout)

    if args.keep_completed > 0:
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                entries = json.load(f).get("entries") or []
            keep = entries[: args.keep_completed]
            paths = [e.get("path") for e in keep if e.get("path")]
            next_ent = entries[args.keep_completed] if len(entries) > args.keep_completed else None
            st = {
                "version": 1,
                "completed": paths,
                "failed": [],
                "resume_from_index": args.keep_completed + 1,
                "resume_from_file": (next_ent or {}).get("archive_name", ""),
            }
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
            log(
                "RESET keep_completed={} next_file={}".format(
                    args.keep_completed, st.get("resume_from_file")
                )
            )
        except Exception as e:
            log("WARN keep_completed reset failed: {}".format(e))

    p0, c0, f0, t0 = queue_counts_from_disk()
    log(
        "=== RESUME batch_import material={} timeout={}s disk: {}/{} done, {} pending ===".format(
            args.material, req_timeout, c0, t0, p0
        )
    )

    try:
        info = send_request("get_addin_info", {}, timeout=30)
        if info.get("success"):
            d = info.get("data") or {}
            log("addin {} active_doc={}".format(d.get("version"), d.get("active_document")))
        else:
            log("WARN get_addin_info: {}".format(info.get("error")))
    except Exception as e:
        log("ERROR cannot connect MCP: {}".format(e))
        return 1

    step_idx = 0
    while True:
        pending, completed, failed_n, total = queue_counts_from_disk()
        try:
            st = send_request("batch_import_reference_library", {"status_only": True}, timeout=60)
            if st.get("success"):
                d = st.get("data") or {}
                pending = int(d.get("pending_count") if d.get("pending_count") is not None else pending)
                completed = int(d.get("completed_count") or completed)
                failed_n = int(d.get("failed_count") or failed_n)
        except Exception:
            pass
        if pending <= 0:
            log("DONE completed={}/{} failed={}".format(completed, total, failed_n))
            break

        step_idx += 1
        log("STEP {} pending={} completed={} failed={}".format(step_idx, pending, completed, failed_n))
        t0 = time.time()
        try:
            r = send_request(
                "batch_import_reference_library",
                {
                    "max_files": 1,
                    "open_file": True,
                    "scan_geometry": True,
                    "material": args.material,
                    "retry_failed": False,
                },
                timeout=req_timeout,
            )
        except socket.timeout:
            log("TIMEOUT step {} (>{}s) — check Fusion UI".format(step_idx, req_timeout))
            time.sleep(5)
            continue
        except Exception as e:
            log("SOCKET ERROR step {}: {}".format(step_idx, e))
            time.sleep(10)
            continue

        elapsed = time.time() - t0
        if not r.get("success"):
            err = str(r.get("error") or "")
            log("FAIL step {} {:.1f}s error={}".format(step_idx, elapsed, err))
            time.sleep(15 if "timed out" in err.lower() else 5)
            continue

        data = r.get("data") or {}
        for s in data.get("steps") or []:
            label = s.get("label") or "?"
            opn = s.get("open") or {}
            imp = s.get("import") or {}
            if not opn.get("ok"):
                log("  {} OPEN FAIL: {}".format(label, opn.get("error")))
                continue
            if not imp.get("success"):
                log("  {} IMPORT FAIL: {}".format(label, imp.get("error")))
                continue
            sd = imp.get("data") or {}
            sc = sd.get("scan") or {}
            gi = sd.get("geometry_index") or {}
            log(
                "  {} OK {:.1f}s ops={} geo_matched={} holes_scanned={} db={}".format(
                    label,
                    elapsed,
                    sc.get("operation_count"),
                    sc.get("geometry_matched_count"),
                    gi.get("hole_row_count") if gi else "-",
                    (sd.get("import") or {}).get("imported"),
                )
            )

        log(
            "  queue pending={} completed={} failed={}".format(
                data.get("pending_count"),
                data.get("completed_count"),
                data.get("failed_count"),
            )
        )
        time.sleep(1)

    st = send_request("batch_import_reference_library", {"status_only": True}, timeout=60).get("data") or {}
    if st.get("failed"):
        log("Failed entries ({}):".format(len(st["failed"])))
        for f in st["failed"][:20]:
            log("  {} — {}".format(f.get("label"), f.get("error")))
        if len(st["failed"]) > 20:
            log("  ... +{} more".format(len(st["failed"]) - 20))
    return 0


if __name__ == "__main__":
    sys.exit(main())
