# -*- coding: utf-8 -*-
"""端對端驗證 regular_milling.py"""
import io
import os
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'smart_ai_cam_mcp'))

from regular_milling import dispatch, recommend, recommend_holder, \
    compute_hex, compute_engagement_angle


def fmt(r):
    if not r.get("success"):
        return f"FAIL: {r.get('error')}"
    p = r["params"]
    line = (f"{r['operation_zh']:30s} "
            f"S={p['rpm']:5d} F={p['feed_mm_min']:5d} "
            f"AE={p['ae_mm']!s:>6} AP={p['ap_mm']!s:>5} "
            f"hex={p['hex_mm_actual']!s:>7}")
    if r.get("hex_health") != "OK":
        line += f"  ⚠ {r['hex_health']}"
    return line


print("=" * 88)
print("S50C D=10 切削油 散件 (用戶實機驗證版, 各工法配對其推薦刀把)")
print("=" * 88)

# ★ 滿刃銑用後拉式, 其他用 ER (按用戶實機)
cases = [
    ("face",   "ER20",     {}),
    ("side",   "ER20",     {}),
    ("hole",   "ER20",     {"hole_diameter": 10.5}),
    ("hole",   "ER20",     {"hole_diameter": 11.0}),
    ("hole",   "ER20",     {"hole_diameter": 12.0}),
    ("hole",   "ER20",     {"hole_diameter": 15.0}),
    ("slot",   "pullback", {}),  # ★ 後拉式!
    ("plunge", "ER20",     {"tool_flute_length": 30}),
]
for op, holder, extra in cases:
    r = recommend(material="S50C", tool_dia=10, holder=holder,
                  coolant="flood", operation=op, **extra)
    label = op
    if "hole_diameter" in extra:
        label = f"{op}(孔{extra['hole_diameter']})"
    ha = r.get("holder_advisor", {})
    match_tag = ha.get("match", "?")
    print(f"  [{label:18s}|{holder:8s}|{match_tag:11s}] {fmt(r)}")

print()
print("=" * 88)
print("側銑 chip_thinning_compensation 三檔升級 (S50C D=10 AE=0.3)")
print("=" * 88)
for comp in [0.0, 0.5, 1.0]:
    r = recommend(material="S50C", tool_dia=10, operation="side",
                  holder="ER20", coolant="flood",
                  chip_thinning_compensation=comp)
    p = r["params"]
    ct = r["chip_thinning"]
    label = f"comp={comp:.1f}"
    if comp == 0.0:
        label += " (用戶切削油實機, 預設)"
    elif comp == 1.0:
        label += " (Gemini 推動態極限)"
    print(f"  [{label:35s}] S={p['rpm']} F={p['feed_mm_min']} "
          f"fz={p['fz_program_mm_tooth']} hex={p['hex_mm_actual']} "
          f"applied={ct['applied']}")

print()
print("=" * 88)
print("Vc 縮放推到其他材質 (面銑 D=10 ER20)")
print("=" * 88)
for mat in ["AL6061", "Brass", "S50C", "SKD11", "NAK80",
            "SUS304", "Ti-6Al-4V", "Inconel"]:
    r = recommend(material=mat, tool_dia=10, operation="face",
                  holder="ER20", coolant="flood")
    p = r["params"]
    print(f"  {mat:12s}: Vc={p['Vc_m_min']:6.1f} S={p['rpm']:5d} "
          f"F={p['feed_mm_min']:5d} (scale={r['vc_scale_applied']})")

print()
print("=" * 88)
print("D 規格化推算 (面銑 S50C ER20, D=2/4/6/8/10/12)")
print("=" * 88)
for D in [2, 4, 6, 8, 10, 12, 16]:
    r = recommend(material="S50C", tool_dia=D, operation="face",
                  holder="ER20", coolant="flood")
    p = r["params"]
    print(f"  D={D:>2}: S={p['rpm']:5d} F={p['feed_mm_min']:5d} "
          f"AP={p['ap_mm']:>5} AE={p['ae_mm']:>5} "
          f"(AP%D={p['ap_pct_D']}% AE%D={p['ae_pct_D']}%)")

print()
print("=" * 88)
print("★ 滿刃銑 holder 動態 AP (證明後拉式 vs ER 差異, D=10 S50C)")
print("=" * 88)
for holder in ["pullback", "shrink_fit", "hydraulic", "weldon",
               "sk", "ER20", "drill_chuck"]:
    r = recommend(material="S50C", tool_dia=10, operation="slot",
                  holder=holder, coolant="flood")
    p = r["params"]
    ha = r["holder_advisor"]
    print(f"  {holder:13s} ({ha['current']['name_zh']:10s}): "
          f"AP={p['ap_mm']:>5} ({p['ap_pct_D']}%D) "
          f"match={ha['match']:11s}")
    if ha.get("warning"):
        print(f"               → {ha['warning']}")

print()
print("=" * 88)
print("★ 刀把推薦 API (recommend_holder, 5 工法各自推薦)")
print("=" * 88)
for op in ["face", "side", "hole", "slot", "plunge"]:
    r = recommend_holder(op)
    pri = r["primary"]
    alts = ', '.join(f"{a['key']}({a['name_zh']})" for a in r["alternatives"])
    print(f"  {op:8s} → 首選 [{pri['key']:11s}] {pri['name_zh']} (★{pri['stars']})")
    print(f"           備選: {alts}")
    print(f"           理由: {r['rationale']}")

print()
print("=" * 88)
print("獨立 API: compute_fz_for_hex (高效率調校工具)")
print("=" * 88)
for spec in [
    ("D=10 AE=0.25 hex=0.03", 10, 0.25, 0.030),
    ("D=10 AE=0.25 hex=0.05", 10, 0.25, 0.050),
    ("D=10 AE=0.30 hex=0.03", 10, 0.30, 0.030),
    ("D=10 AE=0.50 hex=0.05", 10, 0.50, 0.050),
    ("D=10 AE=1.00 hex=0.05", 10, 1.00, 0.050),
    ("D=10 AE=5.00 hex=0.10 (無減薄)", 10, 5.00, 0.100),
]:
    label, D, AE, hex_t = spec
    r = dispatch({"mode": "fz_for_hex", "D": D, "AE": AE,
                  "hex_target": hex_t})
    print(f"  {label:35s} → fz={r['fz_program_required']}")

print()
print("DONE.")
