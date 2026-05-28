# -*- coding: utf-8 -*-
"""
在 Fusion 主執行緒一次跑 N 檔（供 fusion_mcp_execute / 增益集腳本呼叫）。
"""
from __future__ import annotations

import json
import os
import sys


def run_n(
    n: int = 20,
    material: str = "AL6061",
    scan_geometry: bool = True,
    addin_root: str = "",
) -> None:
    import adsk.cam
    import adsk.core
    import adsk.fusion

    root = addin_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    from Smart_AI.reasoning import reference_batch_import as rbi

    app = adsk.core.Application.get()
    cam = des = None

    def refresh():
        nonlocal cam, des
        doc = app.activeDocument
        cam = des = None
        if doc:
            des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
            try:
                cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))
            except Exception:
                cam = None
        return {"cam_obj": cam, "des_obj": des}

    refresh()
    print("START n={} material={} scan_geometry={}".format(n, material, scan_geometry))
    ok = 0
    for i in range(1, n + 1):
        st = rbi.get_batch_import_status()
        pending = int(st.get("pending_count") or 0)
        if pending <= 0:
            print("DONE all completed={}".format(st.get("completed_count")))
            break
        print("--- {}/{} pending={} ---".format(i, n, pending))
        res = rbi.run_batch_import_step(
            app,
            cam,
            material=material,
            max_files=1,
            open_file=True,
            scan_geometry=scan_geometry,
            scan_ctx=None,
            refresh_doc_refs=refresh,
        )
        refresh()
        if not res.get("success"):
            print("BATCH_FAIL", json.dumps(res, ensure_ascii=False)[:2000])
            continue
        for step in (res.get("data") or {}).get("steps") or []:
            imp = (step.get("import") or {})
            if imp.get("success"):
                sd = imp.get("data") or {}
                sc = sd.get("scan") or {}
                print(
                    "OK",
                    step.get("label"),
                    "ops",
                    sc.get("operation_count"),
                    "geo",
                    sc.get("geometry_matched_count"),
                )
                ok += 1
            else:
                print("FAIL", step.get("label"), imp.get("error"))
    print("FINISH imported_steps={}".format(ok))


def run(_context: str):
    root = os.path.join("E:", "Fusion", "插件", "Smart_AI_CAM")
    run_n(20, "AL6061", True, addin_root=root)
