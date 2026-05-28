# -*- coding: utf-8 -*-
"""端對端驗證 cutting_resolver 6 層架構"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from smart_ai_cam_mcp.cutting_resolver import resolve


def show(label, r):
    layer = r.get("layer", "?")
    if not r.get("success"):
        print(f"  [{label:42s}] FAIL: {r.get('error', '?')[:60]}")
        return
    p = r["params"]
    chain = " → ".join(r.get("fallback_chain", []))
    line = (f"  [{label:42s}] {layer:18s} "
            f"S={p.get('rpm'):>5} F={p.get('feed_mm_min'):>5} "
            f"AE={p.get('ae_mm')!s:>5} AP={p.get('ap_mm')!s:>5}")
    if r.get("sanity_notice"):
        line += " ★sanity"
    print(line)
    if chain:
        print(f"     chain: {chain}")


print("=" * 100)
print("【測試 1】L1 命中: AL6061 D=6 側銑 (有本地 ALUS preset)")
print("=" * 100)
r = resolve(material="AL6061", tool_dia=6, operation="側銑",
            mode="conservative")
show("AL6061 D=6 side", r)

print()
print("=" * 100)
print("【測試 2】L2A 觸發 (硬車 HRC≥48 → gold_cobra)")
print("=" * 100)
for spec in [
    ("SKD11 hardened HRC60",  {"material": "SKD11", "tool_dia": 10,
                               "hardness_hrc": 60}),
    ("SKD11 退火 (HRC25 預設)", {"material": "SKD11", "tool_dia": 10}),
    ("NAK80 (預硬 HRC40 預設)",  {"material": "NAK80", "tool_dia": 10}),
    ("series=NXE 明指",         {"material": "S50C", "tool_dia": 10,
                               "series": "NXE", "hardness_hrc": 28}),
]:
    label, kw = spec
    r = resolve(operation="side", **kw)
    show(label, r)

print()
print("=" * 100)
print("【測試 3】L2C regular_milling 觸發 (S50C + operation 命中 5 工法)")
print("=" * 100)
for spec in [
    ("S50C D=10 face (ER20)",    {"operation": "面銑", "holder": "ER",
                                  "coolant": "flood"}),
    ("S50C D=10 side (動態擺線)",  {"operation": "側銑", "holder": "ER",
                                  "coolant": "flood"}),
    ("S50C D=10 slot (後拉式!)",  {"operation": "滿刃銑", "holder": "pullback",
                                  "coolant": "flood"}),
    ("S50C D=10 hole 孔12.0",     {"operation": "孔銑", "holder": "ER",
                                  "coolant": "flood", "hole_diameter": 12.0}),
    ("S50C D=10 plunge (清角)",    {"operation": "插銑", "holder": "ER",
                                  "coolant": "flood",
                                  "tool_flute_length": 30}),
]:
    label, kw = spec
    r = resolve(material="S50C", tool_dia=10, **kw)
    show(label, r)

print()
print("=" * 100)
print("【測試 4】L2D 銘九通用 (Inconel 球刀, gc/rm 都不適合)")
print("=" * 100)
r = resolve(material="Inconel", tool_dia=6, operation="球刀精修",
            feature_type="ball", mode="conservative")
show("Inconel D=6 球刀", r)

print()
print("=" * 100)
print("【測試 5】L3 推斷 (極冷僻 — Plastics)")
print("=" * 100)
r = resolve(material="Plastics", tool_dia=4, operation="contour",
            mode="conservative")
show("Plastics D=4 contour", r)

print()
print("=" * 100)
print("【測試 6】L2C × Chip Thinning 升級 (S50C side, 3 檔)")
print("=" * 100)
for comp in [0.0, 0.5, 1.0]:
    r = resolve(material="S50C", tool_dia=10, operation="側銑",
                holder="ER", coolant="flood",
                chip_thinning_compensation=comp)
    show(f"S50C D=10 side comp={comp}", r)

print()
print("=" * 100)
print("【測試 7】L2A NXE 側壁 vs 平面對調 (SKD11 hardened)")
print("=" * 100)
for cp in ["sidewall", "face"]:
    r = resolve(material="SKD11", tool_dia=10, operation="contour",
                hardness_hrc=60, cutting_pattern=cp, series="NXE")
    show(f"SKD11 HRC60 NXE {cp}", r)

print()
print("=" * 100)
print("【測試 8】強制 skip_local_preset → 看 L2A/L2C 內部行為")
print("=" * 100)

# 強制不用 L1, 看 L2A 跟 L2C 各自的表現
for spec in [
    ("[L2A] SKD11 HRC60 NXE sidewall",
        {"material": "SKD11", "tool_dia": 10, "hardness_hrc": 60,
         "series": "NXE", "cutting_pattern": "sidewall",
         "operation": "contour"}),
    ("[L2A] SKD11 HRC60 NXE face (對調/2)",
        {"material": "SKD11", "tool_dia": 10, "hardness_hrc": 60,
         "series": "NXE", "cutting_pattern": "face",
         "operation": "contour"}),
    ("[L2A] NAK80 HRC40 NZB 球刀",
        {"material": "NAK80", "tool_dia": 6, "hardness_hrc": 40,
         "feature_type": "ball", "operation": "球刀精修"}),
    ("[L2C] S50C D=10 face (ER20)",
        {"material": "S50C", "tool_dia": 10, "operation": "面銑",
         "holder": "ER", "coolant": "flood"}),
    ("[L2C] S50C D=10 side comp=0.0",
        {"material": "S50C", "tool_dia": 10, "operation": "側銑",
         "holder": "ER", "coolant": "flood",
         "chip_thinning_compensation": 0.0}),
    ("[L2C] S50C D=10 side comp=1.0 (極限)",
        {"material": "S50C", "tool_dia": 10, "operation": "側銑",
         "holder": "ER", "coolant": "flood",
         "chip_thinning_compensation": 1.0}),
    ("[L2C] S50C D=10 slot (後拉式)",
        {"material": "S50C", "tool_dia": 10, "operation": "滿刃銑",
         "holder": "pullback", "coolant": "flood"}),
    ("[L2C] S50C D=10 slot (ER, 應警告)",
        {"material": "S50C", "tool_dia": 10, "operation": "滿刃銑",
         "holder": "ER", "coolant": "flood"}),
    ("[L2C] S50C D=10 hole 孔10.5 (小)",
        {"material": "S50C", "tool_dia": 10, "operation": "孔銑",
         "holder": "ER", "coolant": "flood", "hole_diameter": 10.5}),
    ("[L2C] AL6061 D=10 side (鋁衝刺)",
        {"material": "AL6061", "tool_dia": 10, "operation": "側銑",
         "holder": "ER", "coolant": "flood"}),
]:
    label, kw = spec
    r = resolve(skip_local_preset=True, **kw)
    show(label, r)
    if r.get("source_detail", {}).get("holder_advisor"):
        ha = r["source_detail"]["holder_advisor"]
        if ha.get("warning"):
            print(f"     holder ⚠: {ha['warning']}")
    if r.get("source_detail", {}).get("hex_warning"):
        print(f"     hex ⚠: {r['source_detail']['hex_warning']}")

print("\nDONE.")
