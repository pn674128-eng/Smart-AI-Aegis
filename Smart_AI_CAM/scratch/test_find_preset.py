# -*- coding: utf-8 -*-
"""find_preset_for_query 冒煙測試."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\Fusion\插件\Smart_AI_CAM')

from smart_ai_cam_mcp import tool_library_query as t


def show(label, mat, D, op, feature_type=None):
    r = t.find_preset_for_query(mat, D, operation=op, feature_type=feature_type)
    if r is None:
        print(f"  [{label:30s}] -> NO MATCH ({mat} D={D} op={op})")
        return
    tool = r['tool']
    p = r['params']
    T = tool.get('T') or '-'
    desc = (tool.get('description') or '?')[:22]
    vc = p.get('Vc_m_min')
    vc_s = f"{vc:.0f}" if vc else "-"
    print(f"  [{label:30s}] T{str(T):<3} {desc:<22s} "
          f"preset='{r['preset_matched']:<8s}' "
          f"RPM={p['rpm']:<5} F={p.get('feed_mm_min')} Vc={vc_s} "
          f"ae={p.get('stepover_mm')} ap={p.get('stepdown_mm')}")


print("=" * 70)
print("  銑刀類 (preset 用工法名)")
print("=" * 70)
show("AL6061 D=6 側銑",       'AL6061', 6,   'side')
show("AL6061 D=6 滿刃銑",     'AL6061', 6,   '滿刃銑')
show("AL6061 D=6 插銑",       'AL6061', 6,   '插銑')
show("AL6061 D=10 層銑",      'AL6061', 10,  '層銑')
show("S50C D=10 側銑",        'S50C',   10,  '側銑')
show("S50C D=10 面銑",        'S50C',   10,  '面銑')
show("S50C D=6 粗銑(模糊)",   'S50C',   6,   'roughing')
show("S50C D=6 精銑(模糊)",   'S50C',   6,   'finishing')

print()
print("=" * 70)
print("  鑽頭/絞刀/倒角 (preset 用材質名)")
print("=" * 70)
show("S50C D=6 鑽孔",         'S50C',   6,   'hole',    'hole')
show("AL6061 D=6 鑽孔",       'AL6061', 6,   'hole',    'hole')
show("SKD11 D=5 鑽孔",        'SKD11',  5,   'hole',    'hole')
show("SUS304 D=6 鑽孔",       'SUS304', 6,   'hole',    'hole')
show("S50C D=6 絞孔",         'S50C',   6,   'ream',    'hole_ream')
show("S50C D=6 倒角",         'S50C',   6,   'chamfer', 'chamfer')
show("AL6061 D=6 倒角",       'AL6061', 6,   'chamfer', 'chamfer')
show("S50C D=50 面銑刀",      'S50C',   50,  'face',    'face')

print()
print("=" * 70)
print("  Edge cases (找不到應該回 None)")
print("=" * 70)
show("Ti-6Al-4V D=6 側銑",    'Ti-6Al-4V', 6, 'side')
show("Inconel D=10 側銑",     'Inconel',   10, 'side')
show("AL6061 D=99 不存在",   'AL6061',     99, 'side')
