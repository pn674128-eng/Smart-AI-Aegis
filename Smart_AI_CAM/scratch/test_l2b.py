# -*- coding: utf-8 -*-
"""銘九 L2B + 4 層架構 + 刀具幾何 端對端測試."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\Fusion\插件\Smart_AI_CAM')

from smart_ai_cam_mcp import cutting_resolver as r
from smart_ai_cam_mcp import general_catalog as g
from smart_ai_cam_mcp import machining_heuristics as h


def section(t): print(f"\n{'='*72}\n  {t}\n{'='*72}")


def show(label, **kwargs):
    print(f"\n  >>> {label}")
    res = r.resolve(**kwargs)
    p = res.get("params") or {}
    layer = res.get("layer", "?")
    conf = res.get("confidence", 0)
    print(f"      [{layer}] conf={conf:.2f}")
    print(f"      RPM={p.get('rpm')}  F={p.get('feed_mm_min')}  "
          f"Vc={p.get('Vc_m_min')}  Z={p.get('teeth')}")
    if res.get("source"):
        print(f"      source: {res['source']}")
    chain = res.get("fallback_chain") or []
    print(f"      chain: {' -> '.join(chain)}")
    if res.get("clamps_applied"):
        for c in res["clamps_applied"]:
            print(f"        [clamp] {c}")


# ═══════════════════════════════════════════════
section("【1】銘九 L2B 直接命中: S136 淬火 (HRC~53)")
show("S136 D=10 滿刃銑 (期 L2B 4刃 HRC52-62 = RPM 2000 F 1358)",
     material="S136", tool_dia=10, operation="slot")

show("S136 D=6 側銑 (期 L2B)",
     material="S136", tool_dia=6, operation="側銑")

show("S136 D=10 球刀 (期 L2B hardened_ball HRC52)",
     material="S136", tool_dia=10, operation="ball", feature_type="ball")

show("SKD11 D=10 滿刃銑 (期 L2B HRC52-62, RPM 2000)",
     material="SKD11", tool_dia=10, operation="slot")

show("HPM38 D=8 側銑 (期 L2B 4刃 HRC45-52)",
     material="HPM38", tool_dia=8, operation="side")


# ═══════════════════════════════════════════════
section("【2】L1 本地優先: AL6061 用本地 preset 不走銘九")
show("AL6061 D=6 側銑 (期 L1 本地 RPM=9500)",
     material="AL6061", tool_dia=6, operation="側銑")

show("AL6061 D=6 強走 L2B (期 銘九 A5020 表 RPM ≈ 8500×0.75)",
     material="AL6061", tool_dia=6, operation="side",
     prefer_layer="L2B")


# ═══════════════════════════════════════════════
section("【3】銅料: L1/L2 沒 → L2B 命中 (C1020 表)")
show("Brass D=6 側銑 (期 L2B C1020 表)",
     material="Brass", tool_dia=6, operation="side",
     skip_local_preset=True)


# ═══════════════════════════════════════════════
section("【4】微徑球刀: L2B 25000 → 物理上限鉗 12000")
show("S136 R0.3 (D=0.6) 球刀微徑 (期 L2B + RPM 鉗)",
     material="S136", tool_dia=0.6, operation="ball",
     feature_type="micro_ball")


# ═══════════════════════════════════════════════
section("【5】長刃刀: 工件深度推薦")
ans = h.recommend_tool_profile_for_depth(10, 25)
print(f"  D=10 工件深 25mm → {ans['recommended_zh']}")
print(f"  理由: {ans['reason']}")
print(f"  常規幾何: H={ans['regular']['flute_length_mm']}mm, L={ans['regular']['total_length_mm']}mm")

ans2 = h.recommend_tool_profile_for_depth(10, 35)
print(f"\n  D=10 工件深 35mm → {ans2['recommended_zh']}")
print(f"  理由: {ans2['reason']}")
print(f"  RPM 調整: {ans2['rpm_adjustment']}")
print(f"  F 調整: {ans2['f_adjustment']}")

ans3 = h.recommend_tool_profile_for_depth(10, 60)
print(f"\n  D=10 工件深 60mm → {ans3['recommended_zh']}")
print(f"  理由: {ans3['reason']}")
for s in ans3.get("suggestion_zh", []):
    print(f"    {s}")


# ═══════════════════════════════════════════════
section("【6】刀具幾何估算")
for D in [3, 6, 8, 10, 12, 16]:
    geo_r = h.estimate_tool_geometry(D, long_flute=False)
    geo_l = h.estimate_tool_geometry(D, long_flute=True)
    print(f"  D={D:2d}  常規: H={geo_r['flute_length_mm']:5.1f} L={geo_r['total_length_mm']:3d} "
          f"shoulder={geo_r['shoulder_length_mm']:5.1f}  |  "
          f"長刃: H={geo_l['flute_length_mm']:5.1f} L={geo_l['total_length_mm']:3d} "
          f"shoulder={geo_l['shoulder_length_mm']:5.1f}")


# ═══════════════════════════════════════════════
section("【7】銘九 catalog 總覽")
listing = g.list_routes()
print(f"  總表數: {listing['total_tables']}")
for k, v in listing['catalog'].items():
    print(f"  {k:25s} | Z={v['teeth_default']} | tables={v['tables']}")
