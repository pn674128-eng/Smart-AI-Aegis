# -*- coding: utf-8 -*-
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'smart_ai_cam_mcp'))
from regular_milling import recommend_holder

print("=" * 78)
print("★ 刀把推薦 API (5 工法各自首選 + 備選)")
print("=" * 78)
for op in ["face", "side", "hole", "slot", "plunge"]:
    r = recommend_holder(op)
    pri = r["primary"]
    alts = ", ".join(f"{a['key']}({a['name_zh']})"
                     for a in r["alternatives"])
    print(f"\n  ▶ {op}")
    print(f"    首選: [{pri['key']:11s}] {pri['name_zh']:14s} "
          f"(緊固 ★{pri['stars']}, TIR={pri['tir_um']}μm)")
    print(f"    備選: {alts}")
    print(f"    理由: {r['rationale']}")
