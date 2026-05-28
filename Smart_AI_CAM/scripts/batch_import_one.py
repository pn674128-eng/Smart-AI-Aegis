# -*- coding: utf-8 -*-
"""匯入參考檔（完整幾何）。用法:
  python scripts/batch_import_one.py          # 1 檔
  python scripts/batch_import_one.py --count 20
"""
import argparse
import json
import socket
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOST, PORT = "127.0.0.1", 9877
TIMEOUT = 900.0
STATE_PATH = r"E:\Fusion\參考範本\batch_import_state.json"
MANIFEST_PATH = r"E:\Fusion\參考範本\manifest.json"


def _status_from_disk():
    total = 117
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            total = int(json.load(f).get("count") or total)
    except Exception:
        pass
    completed_n = 0
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            completed_n = len(json.load(f).get("completed") or [])
    except Exception:
        pass
    return {
        "pending_count": max(0, total - completed_n),
        "completed_count": completed_n,
        "failed_count": 0,
        "total": total,
    }


def _status(sock):
    st = _call(sock, "batch_import_reference_library", {"status_only": True}, timeout=60.0)
    if st.get("success"):
        return st.get("data") or {}
    if st.get("error"):
        print("MCP 狀態:", st.get("error"), "（改讀磁碟進度）")
    return _status_from_disk()


def _call(sock, action, params, timeout=60.0):
    sock.settimeout(timeout)
    sock.sendall((json.dumps({"action": action, "params": params}) + "\n").encode("utf-8"))
    buf = ""
    while True:
        data = sock.recv(1048576)
        if not data:
            break
        buf += data.decode("utf-8")
        if "\n" in buf:
            break
    return json.loads(buf.strip()) if buf.strip() else {}


def import_one(sock) -> int:
    d = _status(sock)
    pending = int(d.get("pending_count") or 0)
    completed = int(d.get("completed_count") or 0)
    if pending <= 0:
        print("全部完成：{} 檔".format(completed))
        return 2

    print("佇列：已完成 {}，待處理 {} — 下一檔…".format(completed, pending))
    t0 = time.time()
    r = _call(
        sock,
        "batch_import_reference_library",
        {
            "max_files": 1,
            "open_file": True,
            "scan_geometry": True,
            "material": "AL6061",
        },
        timeout=TIMEOUT,
    )
    elapsed = time.time() - t0
    if not r.get("success"):
        err = str(r.get("error") or "")
        print("失敗 ({:.0f}s):".format(elapsed), err)
        if "timed out" in err.lower():
            print("等待 Fusion 背景完成（90s）…")
            time.sleep(90)
            d2 = _status(sock)
            c2 = int(d2.get("completed_count") or 0)
            if c2 > completed:
                print("逾時但已進度 +{} 檔（累計 {}）".format(c2 - completed, c2))
                print("  → 剩餘", d2.get("pending_count"))
                return 0
        return 1

    for step in (r.get("data") or {}).get("steps") or []:
        label = step.get("label", "?")
        opn = step.get("open") or {}
        imp = step.get("import") or {}
        if not opn.get("ok"):
            print(label, "開檔失敗:", opn.get("error"))
            return 1
        if not imp.get("success"):
            print(label, "匯入失敗:", imp.get("error"))
            return 1
        sd = imp.get("data") or {}
        sc = sd.get("scan") or {}
        print(
            "[{:.0f}s] OK".format(elapsed),
            label,
            "| 工序",
            sc.get("operation_count"),
            "| 幾何匹配",
            sc.get("geometry_matched_count"),
            "| DB+",
            (sd.get("import") or {}).get("imported"),
        )

    nd = r.get("data") or {}
    print("  → 剩餘", nd.get("pending_count"), "| 累計完成", nd.get("completed_count"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1, help="連續處理檔數（預設 1）")
    args = ap.parse_args()
    n = max(1, int(args.count))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)
    try:
        sock.connect((HOST, PORT))
    except OSError as e:
        print("無法連線 MCP（請開啟 Fusion 並載入 Smart AI CAM）:", e)
        return 1

    ping = _call(sock, "get_addin_info", {}, timeout=20.0)
    if not ping.get("success"):
        print("增益集 MCP 未就緒:", ping.get("error"))
        print("請：1) 開啟 Fusion  2) 重載 Smart AI CAM 增益集  3) 再執行本腳本")
        d = _status_from_disk()
        print("磁碟進度：已完成 {}/{}".format(d.get("completed_count"), d.get("total")))
        sock.close()
        return 1

    print("=== 連續匯入 {} 檔（每檔 max_files=1, scan_geometry=true）===".format(n))
    ok = 0
    for i in range(1, n + 1):
        print("\n--- {}/{} ---".format(i, n))
        rc = import_one(sock)
        if rc == 2:
            break
        if rc != 0:
            print("第 {} 檔失敗；可重跑 --count 繼續剩餘佇列".format(i))
            sock.close()
            return 1
        ok += 1
        if i < n:
            time.sleep(1)

    sock.close()
    print("\n=== 本輪完成 {} 檔 ===".format(ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
