"""
在 Fusion 內由 MCP fusion_mcp_execute 呼叫：對鑽孔類工序寫入隨機參數並讀回驗證
（語意接近「在 UI 改數字後工序是否吃進去」，並非點 HTML 面板）。

複製下列 def run 的單一函式內容貼至 MCP execute 的 script 字串即可；或整檔 import。
"""

import random
import time

import adsk.core
import adsk.cam


def _gexpr(p):
    if not p:
        return None
    try:
        return p.expression
    except Exception:
        try:
            return str(p.value)
        except Exception:
            return None


def _setexpr(ps, name, expr):
    p = ps.itemByName(name)
    if not p:
        return False, "missing:" + name
    try:
        p.expression = expr
        return True, _gexpr(p)
    except Exception as e:
        return False, str(e)


def _cycle_blob(ps):
    p = ps.itemByName("cycleType")
    return (_gexpr(p) or "").lower()


def _looks_like_drillable(ps):
    blob = _cycle_blob(ps)
    keys = (
        "drilling",
        "deep-drilling",
        "break-through",
        "chip-breaking",
        "gun-drilling",
    )
    return any(k in blob for k in keys)


def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if not doc:
        print("NO_DOCUMENT")
        return
    cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))
    if not cam:
        print("NO_CAM")
        return

    su = None
    for i in range(cam.setups.count):
        s = cam.setups.item(i)
        try:
            if s.isActive:
                su = s
                break
        except Exception:
            pass
    if su is None:
        su = cam.setups.item(0)

    rng = random.Random(int(time.time() * 1000.0) % 1_000_000_001)

    results = []
    n = su.operations.count
    for j in range(n):
        op = su.operations.item(j)
        ps = op.parameters
        if not _looks_like_drillable(ps):
            continue

        bt = rng.choice(("true", "false"))
        brk = round(rng.uniform(1.0, 3.0), 2)
        hole_b = rng.random() < 0.5
        if hole_b:
            bh_mode = "'from hole bottom'"
            # 通孔常見組合：底在孔底 / offset 0 或正值小穿透；與外掛其中一分支對齊
            bh_off = "0mm" if rng.random() < 0.5 else str(round(rng.uniform(0.5, 2.0), 2)) + "mm"
        else:
            bh_mode = "'from stock bottom'"
            bh_off = "0mm"

        before = {
            "breakThroughDepth": _gexpr(ps.itemByName("breakThroughDepth")),
            "drillTipThroughBottom": _gexpr(ps.itemByName("drillTipThroughBottom")),
            "bottomHeight_mode": _gexpr(ps.itemByName("bottomHeight_mode")),
            "bottomHeight_offset": _gexpr(ps.itemByName("bottomHeight_offset")),
        }

        ok1, a1 = _setexpr(ps, "drillTipThroughBottom", bt)
        ok2, a2 = _setexpr(ps, "breakThroughDepth", str(brk) + "mm")
        ok3, a3 = _setexpr(ps, "bottomHeight_mode", bh_mode)
        ok4, a4 = _setexpr(ps, "bottomHeight_offset", bh_off)

        after = {
            "breakThroughDepth": _gexpr(ps.itemByName("breakThroughDepth")),
            "drillTipThroughBottom": _gexpr(ps.itemByName("drillTipThroughBottom")),
            "bottomHeight_mode": _gexpr(ps.itemByName("bottomHeight_mode")),
            "bottomHeight_offset": _gexpr(ps.itemByName("bottomHeight_offset")),
        }

        misc = (ok1, a1, ok2, a2, ok3, a3, ok4, a4)
        ok_all = ok1 and ok2 and ok3 and ok4
        chk_bt = str(bt) in str(after.get("drillTipThroughBottom", ""))
        chk_brk = str(brk) in str(after.get("breakThroughDepth", ""))

        results.append(
            {
                "idx": j,
                "name": op.name,
                "ok_write": ok_all,
                "misc": misc,
                "before": before,
                "after": after,
                "readback_tip_ok": chk_bt,
                "readback_brk_ok": chk_brk,
            }
        )

    print("SETUP=" + su.name + " drill_like_ops=" + str(len(results)))
    for r in results:
        flag = "PASS" if (r["ok_write"] and r["readback_tip_ok"] and r["readback_brk_ok"]) else "FAIL"
        print(flag + " | [%d] %s" % (r["idx"], r["name"]))
        print("  rand_tip=%s rand_brk_mm=%s mode=%s off=%s" % (misc[0], str(brk), bh_mode, bh_off))
        print("  before=" + str(r["before"]))
        print("  after=" + str(r["after"]))
        if not r["ok_write"]:
            print("  write_err=" + str(r["misc"]))
