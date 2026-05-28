# -*- coding: utf-8 -*-
"""cutting_resolver 三層降級端對端測試."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\Fusion\插件\Smart_AI_CAM')

from smart_ai_cam_mcp import cutting_resolver as r


def show(label, **kwargs):
    print(f"\n  >>> {label}")
    res = r.resolve(**kwargs)
    p = res.get("params") or {}
    layer = res.get("layer", "?")
    conf = res.get("confidence", 0)
    print(f"      [{layer}] confidence={conf:.2f}")
    print(f"      RPM={p.get('rpm')}  F={p.get('feed_mm_min')}  "
          f"Vc={p.get('Vc_m_min')}  fz={p.get('fz_mm_tooth')}  "
          f"ae={p.get('ae_mm')} ap={p.get('ap_mm')}")
    if res.get("tool"):
        t = res["tool"]
        print(f"      tool: T{t.get('T')} {t.get('description', '')[:30]}")
    chain = res.get("fallback_chain") or []
    print(f"      chain: {' -> '.join(chain)}")
    clamps = res.get("clamps_applied") or []
    if clamps:
        for c in clamps:
            print(f"        [clamp] {c}")


print("=" * 72)
print("  L1 GOLD: 本地 preset 應該優先命中 (用戶日常用刀)")
print("=" * 72)

show("AL6061 D=6 側銑 (期望 L1)",
     material="AL6061", tool_dia=6, operation="側銑")

show("AL6061 D=6 滿刃銑 (期望 L1)",
     material="AL6061", tool_dia=6, operation="滿刃銑")

show("S50C D=10 側銑 (期望 L1)",
     material="S50C", tool_dia=10, operation="側銑")

show("S50C D=6 鑽孔 (期望 L1 鑽頭 preset)",
     material="S50C", tool_dia=6, operation="hole", feature_type="hole")

show("SUS304 D=6 鑽孔 (L1 smart fallback → SKD11 preset)",
     material="SUS304", tool_dia=6, operation="hole", feature_type="hole")

print()
print("=" * 72)
print("  L2 SILVER: 本地沒命中 → 走廠商表")
print("=" * 72)

show("SKD11 D=10 側銑 (本地少, 期望 L2 CIB 表)",
     material="SKD11", tool_dia=10, operation="side")

show("Ti-6Al-4V D=20 側銑 (跳 L1 強走 L2)",
     material="Ti-6Al-4V", tool_dia=20, operation="side",
     skip_local_preset=True)

show("AL6061 D=6 側銑 量產模式 (skip L1, 強走 L2 量產)",
     material="AL6061", tool_dia=6, operation="side",
     skip_local_preset=True, mode="aggressive")

print()
print("=" * 72)
print("  L3 BRONZE: 推斷引擎 (沒廠商表的材質)")
print("=" * 72)

show("Inconel D=10 側銑 (期望 L3, Vc 上限 40)",
     material="Inconel", tool_dia=10, operation="side")

show("Ti-6Al-4V D=10 精銑 (期望 L3 推斷)",
     material="Ti-6Al-4V", tool_dia=10, operation="finishing")

show("HPM38 D=8 滿刃銑 (淬火, 期望 L2 或 L3)",
     material="HPM38", tool_dia=8, operation="slot")

print()
print("=" * 72)
print("  特殊: 物理上限觸發 (大徑 / 小徑 / 高負荷)")
print("=" * 72)

show("AL6061 D=2 側銑 強走 L2 (小徑撞 RPM=12000)",
     material="AL6061", tool_dia=2, operation="side",
     skip_local_preset=True, mode="aggressive")

show("Ti-6Al-4V D=20 側銑 (撞 F 功率上限)",
     material="Ti-6Al-4V", tool_dia=20, operation="side",
     skip_local_preset=True, mode="aggressive")
