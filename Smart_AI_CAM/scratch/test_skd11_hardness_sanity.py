# -*- coding: utf-8 -*-
"""
SKD11 退火/淬火二態 + 防護層 (sanity check) 驗證
================================================
用戶 2026.05 指示:
  ① 材質鍵預設 = 出貨/退火態 (用戶實機常態)
  ② SKD11 + hardness_hrc>=45 才走淬火表
  ③ 銘九通用表當「防護層」, 偏離過大要警告
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smart_ai_cam_mcp import cutting_resolver, machining_heuristics as mh
from smart_ai_cam_mcp import general_catalog as gc


def title(s):
    print(f"\n{'='*78}\n  {s}\n{'='*78}")


# ════════════════════════════════════════════════════════════════
# 1. 材質正規化測試
# ════════════════════════════════════════════════════════════════
title("1. 材質鍵正規化 (normalize_material)")

cases = [
    # (input_material, hardness_hrc, expected_key)
    ("SKD11",           None,    "SKD11"),            # 預設退火
    ("SKD11",           20,      "SKD11"),            # 明確軟態
    ("SKD11",           58,      "SKD11_hardened"),   # 淬火態
    ("SKD11_hardened",  None,    "SKD11_hardened"),   # 直接指定
    ("SKD11_淬火",      None,    "SKD11_hardened"),   # 中文別名
    ("SKD11_HRC58",     None,    "SKD11_hardened"),   # HRC 後綴
    ("S136",            None,    "S136"),             # 預設退火
    ("S136",            52,      "S136_hardened"),
    ("DC53",            None,    "DC53"),
    ("DC53",            60,      "DC53_hardened"),
    ("NAK80",           None,    "NAK80"),            # 預質鋼不變
    ("AL6061",          None,    "AL6061"),
]

ok = fail = 0
for mat_in, hrc, expect in cases:
    got = mh.normalize_material(mat_in, hardness_hrc=hrc)
    pass_ = (got == expect)
    print(f"  {'✓' if pass_ else '✗'} normalize({mat_in!r}, hrc={hrc}) "
          f"→ {got!r} (expect {expect!r})")
    if pass_: ok += 1
    else:     fail += 1
print(f"\n  小計: {ok} pass / {fail} fail")


# ════════════════════════════════════════════════════════════════
# 2. SKD11 退火態 vs 淬火態 推薦對照
# ════════════════════════════════════════════════════════════════
title("2. SKD11 退火 vs 淬火 推薦對照 (D=10, side, 散件)")

for label, mat, hrc in [
    ("退火態 (預設)",   "SKD11",          None),
    ("退火態 (HRC=22)", "SKD11",          22),
    ("淬火態 (HRC=58)", "SKD11",          58),
    ("淬火態 (鍵直指)", "SKD11_hardened", None),
]:
    r = cutting_resolver.resolve(
        material=mat,
        tool_dia=10,
        operation="side",
        hardness_hrc=hrc,
        mode="conservative",
        skip_local_preset=True,  # 跳過 L1 看純廠商/推斷結果
    )
    p = r.get("params", {})
    layer = r.get("layer", "?")
    print(f"\n  [{label}] material={mat!r} hrc={hrc}")
    print(f"    → layer={layer}")
    print(f"    → material_in_use={r.get('material', mat)}")
    print(f"    → RPM={p.get('rpm')} F={p.get('feed_mm_min')} "
          f"Vc={p.get('Vc_m_min')} m/min")
    if r.get("clamps_applied"):
        for c in r["clamps_applied"]:
            print(f"    ⚙ {c}")
    sc = r.get("sanity_check")
    if sc:
        print(f"    防護層: {sc['status']}")
        for w in sc.get("warnings", []) + sc.get("blocks", []):
            print(f"      • {w}")


# ════════════════════════════════════════════════════════════════
# 3. 防護層 sanity_check 獨立測試
# ════════════════════════════════════════════════════════════════
title("3. 防護層獨立測試 (gc.sanity_check)")

scenarios = [
    # (label, material, D, rpm, feed, hrc, expect_status)
    ("正常 SKD11 淬火",   "SKD11", 10, 1500, 200,  58, "PASS"),
    ("RPM 過高",          "SKD11", 10, 5000, 800,  58, "WARN/BLOCKED"),
    ("RPM 嚴重超標",      "SKD11", 10, 10000, 1500, 58, "BLOCKED"),
    ("過度保守",          "SKD11", 10, 300, 50,    58, "WARN"),
    ("AL6061 正常",       "AL6061", 6, 8000, 1200, None, "PASS"),
    ("AL6061 RPM 太低",   "AL6061", 6, 500, 100,   None, "WARN"),
]

for label, mat, D, rpm, feed, hrc, expect in scenarios:
    r = gc.sanity_check(
        material=mat,
        tool_dia=D,
        rpm_proposed=rpm,
        feed_proposed=feed,
        hardness_hrc=hrc,
    )
    print(f"\n  [{label}] {mat} D={D} RPM={rpm} F={feed} (HRC={hrc})")
    print(f"    狀態: {r['status']}  (期望: {expect})")
    if r.get("benchmark_mingjiu"):
        b = r["benchmark_mingjiu"]
        print(f"    銘九基準: RPM={b['rpm']} F={b['feed_mm_min']} "
              f"(表 {b.get('table','-')})")
    print(f"    比率: RPM×{r.get('ratio',{}).get('rpm','-')} "
          f"F×{r.get('ratio',{}).get('feed','-')}")
    for w in r.get("warnings", []):
        print(f"    ⚠ {w}")
    for b in r.get("blocks", []):
        print(f"    ✗ {b}")
    print(f"    建議: {r.get('advice','-')}")


# ════════════════════════════════════════════════════════════════
# 4. 對本地 preset (T40 SKD11 退火) 跑防護層
# ════════════════════════════════════════════════════════════════
title("4. 本地 preset 跑全流程含防護層 (期望 L1 命中)")

r = cutting_resolver.resolve(
    material="SKD11",     # 退火態
    tool_dia=10,
    operation="side",
    mode="conservative",
)
print(f"\n  layer    = {r.get('layer')}")
print(f"  material = {r.get('material')}")
if r.get("tool"):
    t = r["tool"]
    print(f"  tool     = T{t.get('T','-')} D{t.get('diameter_mm','-')} "
          f"{(t.get('description','') or '')[:40]}")
p = r.get("params", {})
print(f"  RPM      = {p.get('rpm')}")
print(f"  Feed     = {p.get('feed_mm_min')}")
print(f"  Vc       = {p.get('Vc_m_min')} m/min")
print(f"  fallback = {' | '.join(r.get('fallback_chain', []))}")
sc = r.get("sanity_check")
if sc:
    print(f"\n  ─── 防護層 ───")
    print(f"  狀態  : {sc['status']}")
    bm = sc.get("benchmark_mingjiu", {})
    print(f"  銘九  : RPM={bm.get('rpm')} F={bm.get('feed_mm_min')}")
    print(f"  比率  : RPM×{sc.get('ratio',{}).get('rpm')} "
          f"F×{sc.get('ratio',{}).get('feed')}")
    if sc.get("warnings"):
        for w in sc["warnings"]:
            print(f"  ⚠ {w}")
    print(f"  建議  : {sc.get('advice')}")
if r.get("sanity_notice"):
    print(f"\n  {r['sanity_notice']}")


print("\n" + "="*78)
print("  測試結束")
print("="*78)
