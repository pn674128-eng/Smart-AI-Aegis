# -*- coding: utf-8 -*-
"""
掃描 E:\\Fusion\\參考範本\\f3z已編程 內所有參考檔（.f3d / .f3z），更新 manifest.json。

不刪除、不搬移既有檔案（您手動放入的 .f3d 會完整登錄）。

用法:
  python scripts/scan_reference_library.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Smart_AI.reasoning import reference_paths as rp

REFERENCE_EXTENSIONS = (".f3d", ".f3z")


def scan_reference_dir() -> dict:
    lib_dir = rp.reference_f3z_dir()
    if not lib_dir or not os.path.isdir(lib_dir):
        return {"ok": False, "error": "reference dir missing", "entries": []}

    entries = []
    counts = {ext: 0 for ext in REFERENCE_EXTENSIONS}
    for fn in sorted(os.listdir(lib_dir)):
        if fn.startswith("."):
            continue
        low = fn.lower()
        ext = None
        for e in REFERENCE_EXTENSIONS:
            if low.endswith(e):
                ext = e
                break
        if not ext:
            continue
        fp = os.path.join(lib_dir, fn)
        if not os.path.isfile(fp):
            continue
        counts[ext] = counts.get(ext, 0) + 1
        entries.append(
            {
                "file_type": ext.lstrip("."),
                "archive_name": fn,
                "path": fp,
                "size_bytes": os.path.getsize(fp),
                "mtime_iso": datetime.fromtimestamp(
                    os.path.getmtime(fp), tz=timezone.utc
                ).isoformat(),
                "source": "reference_library",
            }
        )

    manifest = {
        "version": "1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fusion_root": rp.fusion_root_from_desktop(),
        "reference_template_root": rp.reference_template_root(),
        "library_dir": lib_dir,
        "extensions": list(REFERENCE_EXTENSIONS),
        "counts_by_type": counts,
        "count": len(entries),
        "entries": entries,
        "note": (
            ".f3d=設計檔（可含 CAM，請在 Fusion 開啟後 import_cam_from_active_document）；"
            ".f3z=封裝檔。見 docs/F3Z_LEARNING.md"
        ),
    }
    out_path = rp.reference_manifest_path()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return {"ok": True, "manifest_path": out_path, "manifest": manifest}


def main():
    res = scan_reference_dir()
    if not res.get("ok"):
        print("[error]", res.get("error"))
        return 1
    m = res["manifest"]
    print("[manifest]", res["manifest_path"])
    print("[count]", m["count"], m.get("counts_by_type"))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
