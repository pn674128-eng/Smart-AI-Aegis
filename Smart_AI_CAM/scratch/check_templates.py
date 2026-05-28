import os
import sys

# Add plugin directories to path
plugin_dir = "E:/Fusion/插件/Smart_AI_CAM"
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from smart_ai_cam_templates import template_fs_cache

print("=== Template Scanner Diagnostics ===")
root = template_fs_cache.templates_root()
print(f"Templates Root: {root}")
print(f"Root Exists: {os.path.exists(root)}")

for mat in ['AL6061', 'S50C']:
    mat_root = template_fs_cache.material_fs_root(mat)
    print(f"\nMaterial: {mat}")
    print(f"Folder: {mat_root}")
    print(f"Exists: {os.path.exists(mat_root)}")
    if os.path.exists(mat_root):
        entries = template_fs_cache._scan_disk(mat)
        print(f"Total entries found by cache scan: {len(entries)}")
        for e in entries:
            print(f"  - {e['relpath']}")
        
        # Test folder checking
        rel = "{material}/面銑刀模塊 【{material}】/粗加工【{material}】"
        exists = template_fs_cache.fs_folder_exists(mat, rel)
        print(f"Folder exists check for {rel.format(material=mat)}: {exists}")
