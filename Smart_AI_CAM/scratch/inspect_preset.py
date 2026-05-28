# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\Fusion\插件\Smart_AI_CAM')
from smart_ai_cam_mcp import tool_library_query as t

tools, _ = t._load_tools()


def show(cat, D, label):
    for tl in tools:
        if tl['category'] == cat and abs((tl.get('diameter_mm') or 0) - D) < 0.1:
            print(f'=== {label} D={D} ===')
            print(f'  T={tl.get("tool_number")}  desc: {tl.get("description")}')
            print(f'  vendor={tl.get("vendor")}  pid={tl.get("product_id")}')
            print(f'  teeth={tl.get("teeth")}  flute_len={tl.get("flute_length_mm")}')
            for p in tl.get('presets') or []:
                nm = p.get('name')
                mc = p.get('material_category')
                rpm = p.get('rpm')
                feed = p.get('feed_mm_min')
                vc = p.get('v_c_m_min')
                fz = p.get('f_z_mm_tooth')
                fn = p.get('f_n_mm_rev')
                ae = p.get('stepover_mm')
                ap = p.get('stepdown_mm')
                print(f'    [{nm:8s}] mat={mc:10s} RPM={rpm} F={feed} '
                      f'Vc={vc} fz={fz} fn={fn} ae={ae} ap={ap}')
            print()
            return


show('end_mill_alu', 6, 'ALU 鋁刀')
show('end_mill_steel', 10, 'CIB 鋼刀')
show('drill_sg', 5, 'SG 鑽頭')
show('drill_hss', 6, 'HSS 鑽頭')
show('reamer', 6, '絞刀')
show('face_mill', 50, '面銑刀')
show('bull_nose', 6, '圓鼻刀')
show('chamfer', 6, '倒角刀')
