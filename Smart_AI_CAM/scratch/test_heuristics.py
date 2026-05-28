# -*- coding: utf-8 -*-
"""machining_heuristics 端對端冒煙測試."""
import sys, json, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\Fusion\插件\Smart_AI_CAM')
from smart_ai_cam_mcp import machining_heuristics as h


def section(t):
    print(f"\n{'='*68}\n  {t}\n{'='*68}")


# ============================================================
section("【情境 1】D=6 Ti6Al4V 錨點 → 推算 D=10 (預期 Vc 維持 78)")
print("錨點 (用戶 Mazak 試算): D=6 RPM=4138 F=497 Z=4 (粗銑)")
r = h.derive_from_anchor(
    anchor_D=6, anchor_rpm=4138, anchor_feed=497,
    target_D=10, material='Ti-6Al-4V', teeth_anchor=4)
print(f"  反推 Vc = {r['anchor']['Vc_reverse_calc']} m/min")
print(f"  反推 fz = {r['anchor']['fz_reverse_calc']} mm/tooth")
print(f"  → D=10 推算: RPM={r['target']['rpm_final']}, F={r['target']['feed_final']}")
print(f"  → 套用上限: Vc={r['target']['Vc_final']} m/min")
for c in r['clamps_applied']:
    print(f"     [clamp] {c}")
print(f"  預期: Vc=78 維持, D=10 RPM ~= 2482, F ~= 298")


# ============================================================
section("【情境 2】SUS316 → Ti-6Al-4V 跨材質換算 (D20 用戶實機驗證)")
print("已知 SUS316: D=20 RPM=2387 F=1003")
r = h.substitute_material('SUS316', 'Ti-6Al-4V', 2387, 1003)
print(f"  換算到 Ti6Al4V: RPM={r['rpm']}, F={r['feed']}")
print(f"  使用係數: vc_factor={r['vc_factor']}, fz_factor={r['fz_factor']}")
print(f"  來源: {r['source']}")
print(f"  預期 (用戶試算): RPM~1675, F~500 (誤差 < 2%)")


# ============================================================
section("【情境 3】D=20 銑 Ti6Al4V 撞主軸功率 F 上限")
print("計算原始: 假設 V=78 fz=0.05 Z=4 → RPM=1242, F=1242×0.05×4=248")
print("(這個 F=248 沒超 Ti @ 7.5kW 上限 375, 應該不鉗)")
r = h.apply_ceilings('Ti-6Al-4V', 20, rpm_calc=1242, feed_calc=248,
                     spindle_kw=7.5, spindle_rpm_max=12000)
print(f"  最終: RPM={r['rpm']}, F={r['feed_mm_min']}, Vc={r['Vc_m_min']}")
print(f"  F 上限參考: {r['F_ceiling_used']}")
print(f"  Clamps: {r['clamps_applied']}")

print("\n再來一個極端: 假設算出 F=600 (超上限 375)")
r2 = h.apply_ceilings('Ti-6Al-4V', 20, rpm_calc=1242, feed_calc=600,
                      spindle_kw=7.5)
print(f"  最終: RPM={r2['rpm']}, F={r2['feed_mm_min']}")
for c in r2['clamps_applied']:
    print(f"     [clamp] {c}")


# ============================================================
section("【情境 4】D=2 銑 AL6061 應撞主軸 RPM 12000 上限")
print("假設 Vc=250 (鋁上限), D=2 → RPM_calc = 250×318.3/2 = 39787")
r = h.apply_ceilings('AL6061', 2, rpm_calc=39787, feed_calc=39787*0.04*3,
                     spindle_kw=7.5, spindle_rpm_max=12000)
print(f"  最終: RPM={r['rpm']}, F={r['feed_mm_min']}")
print(f"  Vc 實際: {r['Vc_m_min']} m/min")
for c in r['clamps_applied']:
    print(f"     [clamp] {c}")


# ============================================================
section("【情境 5】工法折扣 — Ti6Al4V D=6 面精銑 vs 粗銑")
op_rough = h.get_operation_factors('roughing')
op_fine = h.get_operation_factors('face_finishing')
print(f"粗銑: vc×{op_rough['vc_factor']}, fz×{op_rough['fz_factor']}, "
      f"ae {op_rough['ae_pct_range']}, ap {op_rough['ap_pct_range']}")
print(f"面精銑: vc×{op_fine['vc_factor']}, fz×{op_fine['fz_factor']}, "
      f"ae {op_fine['ae_pct_range']}, ap {op_fine['ap_pct_range']}")
print(f"\n粗→精 Vc 折扣: {op_fine['vc_factor']/op_rough['vc_factor']:.3f} "
      f"(用戶試算: 72/78 = 0.923 [v])")
print(f"粗→精 fz 折扣: {op_fine['fz_factor']/op_rough['fz_factor']:.3f} "
      f"(用戶試算: 0.022/0.030 = 0.733 [v])")


# ============================================================
section("【情境 6】刀具材質升級 HSS → 鎢鋼 vs PCD")
for tm in ['HSS', 'HSS-Co', 'Powder_HSS', 'Carbide', 'Carbide_coated', 'PCD', 'CBN']:
    info = h.get_tool_material_factor(tm)
    print(f"  {tm:18s} vc×{info['vc_factor']:.2f}  剛性={info['rigidity']}")


# ============================================================
section("【情境 7】調參優先序")
adj = h.adjustment_priority()
print(f"鐵則: {adj['rule_zh']}")
print(f"反模式: {adj['anti_pattern_zh']}")
for step in adj['steps']:
    print(f"\n  Step {step['step']}: {step['action_zh']}")
    print(f"    適用: {', '.join(step['applies_to'])}")
    print(f"    例: {step['example']}")
