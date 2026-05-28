# -*- coding: utf-8 -*-
"""SKD11 完整對齊審計: 本地 preset vs 銘九通用 vs 推斷引擎."""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\Fusion\插件\Smart_AI_CAM')

from smart_ai_cam_mcp import tool_library_query as t
from smart_ai_cam_mcp import general_catalog as g
from smart_ai_cam_mcp import keili_catalog as k
from smart_ai_cam_mcp import machining_heuristics as h
from smart_ai_cam_mcp import cutting_resolver as r


tools, _ = t._load_tools()

print("=" * 78)
print("  本地刀具庫 SKD11 相關 preset 全部列表")
print("=" * 78)
skd_tools = []
for tl in tools:
    if not tl.get('presets'): continue
    # 找含 SKD 標籤的 preset
    has_skd = any('SKD' in (p.get('name') or '') for p in tl['presets'])
    if has_skd or 'SKD11' in (tl.get('suitable_materials') or []):
        skd_tools.append(tl)

print(f"\n  本地 SKD11 相關刀具總數: {len(skd_tools)}")
for tl in skd_tools[:30]:
    D = tl.get('diameter_mm')
    T = tl.get('tool_number')
    cat = tl.get('category_zh')
    desc = (tl.get('description') or '')[:24]
    Z = tl.get('teeth')
    print(f"\n  T{T} D={D} {cat:<14s} Z={Z}  {desc}")
    for p in tl.get('presets', []):
        nm = (p.get('name') or '').strip()
        if 'SKD' not in nm and 'ASP' not in nm: continue
        rpm = p.get('rpm')
        feed = p.get('feed_mm_min')
        vc = p.get('v_c_m_min')
        fz = p.get('f_z_mm_tooth')
        print(f"    [{nm:<9s}] RPM={rpm:<6}  F={feed!s:>8}  Vc={vc!s:>6}  fz={fz}")


# ── 銑刀類沒 SKD preset 但 suitable_materials 含 SKD11 (CIB 系列) ──
print()
print("=" * 78)
print("  本地 CIB 鋼刀 (suitable_materials 含 SKD11)")
print("=" * 78)
cib_for_skd = []
for tl in tools:
    if tl['category'] != 'end_mill_steel': continue
    if 'SKD11' not in (tl.get('suitable_materials') or []): continue
    cib_for_skd.append(tl)
print(f"  共 {len(cib_for_skd)} 把 CIB 鋼刀可用於 SKD11")
for tl in cib_for_skd[:20]:
    D = tl.get('diameter_mm')
    T = tl.get('tool_number')
    desc = (tl.get('description') or '')[:24]
    presets_summary = ', '.join(f"{(p.get('name') or '').strip()}({p.get('rpm')}/{p.get('feed_mm_min')})"
                                 for p in tl.get('presets', []))
    print(f"  T{T} D={D!s:<5s} {desc:<24s}  → {presets_summary}")


# ── 三層對照表 ──
print()
print("=" * 78)
print("  SKD11 三層數據對照 (本地 vs 銘九 vs 推斷)")
print("  條件: 散件 conservative 模式, ER 刀把, 7.5 kW")
print("=" * 78)
print()
print(f"  {'D':>4s} {'工法':<12s}  "
      f"{'本地 preset (L1)':<25s}  "
      f"{'銘九通用 (L2B)':<25s}  "
      f"{'推斷 (L3)':<20s}")
print("  " + "-" * 96)

for D in [3, 4, 5, 6, 8, 10, 12, 16, 20]:
    for op in ['側銑', '滿刃銑']:
        # L1: 本地
        l1 = r.resolve(material='SKD11', tool_dia=D, operation=op,
                       prefer_layer='L1')
        l1_str = ('--' if not l1.get('success')
                  else f"RPM={l1['params']['rpm']:<5} F={l1['params'].get('feed_mm_min') or '--'}")

        # L2B: 銘九
        l2b = r.resolve(material='SKD11', tool_dia=D, operation=op,
                        prefer_layer='L2B')
        l2b_str = ('--' if not l2b.get('success')
                   else f"RPM={l2b['params']['rpm']:<5} F={l2b['params']['feed_mm_min']:<5}")

        # L3: 推斷
        l3 = r.resolve(material='SKD11', tool_dia=D, operation=op,
                       prefer_layer='L3')
        l3_str = ('--' if not l3.get('success')
                  else f"RPM={l3['params']['rpm']:<5} F={l3['params']['feed_mm_min']:<5}")

        print(f"  D={D:<3d}{op:<12s}  {l1_str:<25s}  {l2b_str:<25s}  {l3_str:<20s}")


# ── auto resolve (4 層自動降級) ──
print()
print("=" * 78)
print("  SKD11 4 層自動降級結果 (用戶實際呼叫時拿到的)")
print("=" * 78)
for D, op in [(3, '側銑'), (5, '側銑'), (6, '滿刃銑'), (8, '側銑'),
              (10, '滿刃銑'), (12, '側銑'), (16, '側銑'),
              (10, '面銑'), (10, 'ball')]:
    res = r.resolve(material='SKD11', tool_dia=D, operation=op)
    p = res.get('params', {})
    layer = res.get('layer', '?')
    rpm = p.get('rpm')
    feed = p.get('feed_mm_min')
    vc = p.get('Vc_m_min')
    chain = res.get('fallback_chain', [])
    clamps = res.get('clamps_applied', [])
    print(f"\n  D={D} {op} → [{layer}] RPM={rpm} F={feed} Vc={vc}")
    print(f"    chain: {' -> '.join(chain)}")
    for c in clamps:
        print(f"    [clamp] {c}")
