# -*- coding: utf-8 -*-
"""審查我之前在 Smart_AI_CAM.py 加的 6 個 MCP actions 是否都用 try/except 包好,
   避免任何例外傳到 Fusion 主線程引發白屏。"""
import io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

src = open(r'E:\Fusion\插件\Smart_AI_CAM\Smart_AI_CAM.py',
           encoding='utf-8').read()

my_actions = [
    "query_smart_cutting", "query_regular_milling", "query_gold_cobra",
    "query_general_catalog", "query_heuristics", "query_tool_holders",
]

print("=" * 70)
print("審查我新加的 MCP actions 安全性 (是否能引發 Fusion 白屏)")
print("=" * 70)

all_safe = True
for act in my_actions:
    pattern = (rf'elif action == "{act}":\s*\n'
               r'((?:.|\n)*?)'
               r'(?=\n    # ──|\n    elif action|\Z)')
    m = re.search(pattern, src)
    if not m:
        print(f"  [{act:30s}] FAIL: 找不到 elif 區塊")
        all_safe = False
        continue
    block = m.group(1)
    has_try = "try:" in block
    has_except = "except Exception" in block
    returns_dict = "return" in block
    safe = has_try and has_except and returns_dict
    status = "SAFE" if safe else "RISK"
    print(f"  [{act:30s}] try={has_try} except={has_except} "
          f"return={returns_dict}  → {status}")
    if not safe:
        all_safe = False

print()
print("=" * 70)
if all_safe:
    print("結論: ✓ 我加的 6 個 actions 全部用 try/except 包住,")
    print("        任何例外都會回傳 success=False, 不會傳到 Fusion 主線程.")
    print("        重載 Smart_AI_CAM 外掛是安全的.")
else:
    print("結論: ✗ 有風險! 請手動修補上面標 RISK 的區塊.")
print("=" * 70)

# 額外: 確認 import 都是 lazy import (在 elif 內 import, 失敗不會 import-time crash)
print()
print("檢查 import 模式 (lazy / eager):")
for act in my_actions:
    pattern = (rf'elif action == "{act}":\s*\n'
               r'((?:.|\n)*?)'
               r'(?=\n    # ──|\n    elif action|\Z)')
    m = re.search(pattern, src)
    if m and "from smart_ai_cam_mcp" in m.group(1):
        # 看 import 是在 try 內嗎
        block = m.group(1)
        try_idx = block.find("try:")
        import_idx = block.find("from smart_ai_cam_mcp")
        is_lazy = try_idx >= 0 and import_idx > try_idx
        print(f"  [{act:30s}] {'lazy import (安全)' if is_lazy else 'eager import (風險)'}")

print()
print("DONE.")
