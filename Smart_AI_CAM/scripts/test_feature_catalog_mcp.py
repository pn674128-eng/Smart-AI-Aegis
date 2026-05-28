# -*- coding: utf-8 -*-
import json
import socket
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOST = "127.0.0.1"
PORT = 9877


def send_request(action, params=None):
    if params is None:
        params = {}
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(30.0)
    client.connect((HOST, PORT))
    payload = {"action": action, "params": params}
    client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    buffer = ""
    while True:
        data = client.recv(65536)
        if not data:
            break
        buffer += data.decode("utf-8")
        if "\n" in buffer:
            break
    client.close()
    return json.loads(buffer.strip()) if buffer else None


if __name__ == "__main__":
    for action in ("scan_machining_features", "get_ai_recommendations"):
        r = send_request(action, {"material": "AL6061"})
        print("\n===", action, "===")
        print("success:", r.get("success"))
        data = r.get("data") or {}
        if action == "scan_machining_features":
            print("data keys:", list(data.keys()))
            s = data.get("feature_catalog_summary") or {}
            c = data.get("feature_catalog") or {}
            print("summary:", json.dumps(s, ensure_ascii=False))
            print("feature_count:", c.get("feature_count"))
            print("counts:", c.get("counts_by_category"))
        else:
            print("feature_catalog_summary:", json.dumps(data.get("feature_catalog_summary"), ensure_ascii=False))
            dec = (data.get("decisions") or {}).get("feature_catalog")
            print("decisions.feature_catalog:", json.dumps(dec, ensure_ascii=False))
