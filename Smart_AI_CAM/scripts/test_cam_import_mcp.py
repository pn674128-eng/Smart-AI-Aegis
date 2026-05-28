# -*- coding: utf-8 -*-
"""Smart AI CAM MCP 測試：參考庫清單、單檔匯入、批次狀態／一步。"""
import json
import socket
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOST = "127.0.0.1"
PORT = 9877


def send_request(action, params=None, timeout=120.0):
    if params is None:
        params = {}
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect((HOST, PORT))
    payload = {"action": action, "params": params}
    client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    buffer = ""
    while True:
        data = client.recv(524288)
        if not data:
            break
        buffer += data.decode("utf-8")
        if "\n" in buffer:
            break
    client.close()
    return json.loads(buffer.strip()) if buffer else None


def main():
    tests = [
        ("get_addin_info", {}),
        ("list_reference_f3z", {}),
        ("batch_import_reference_library", {"status_only": True}),
    ]
    if len(sys.argv) > 1 and sys.argv[1] == "import":
        tests.append(
            ("import_cam_from_active_document", {"material": "AL6061", "scan_geometry": True})
        )
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        tests.append(
            (
                "batch_import_reference_library",
                {"max_files": 1, "material": "AL6061", "retry_failed": True},
            )
        )

    for action, params in tests:
        print("\n===", action, "===")
        to = 180.0 if "batch" in action or "import_cam" in action else 30.0
        try:
            r = send_request(action, params, timeout=to)
            print(json.dumps(r, ensure_ascii=False, indent=2)[:6000])
        except Exception as e:
            print("ERROR:", type(e).__name__, e)


if __name__ == "__main__":
    main()
