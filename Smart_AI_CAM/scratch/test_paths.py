import sys
import os
sys.path.insert(0, r"E:\Fusion\插件\Smart_AI_CAM")
from smart_ai_cam_templates import template_fs_cache

def main():
    root = template_fs_cache.templates_root()
    print("templates_root:", root)
    mat_root = template_fs_cache.material_fs_root("AL6061")
    print("material_fs_root:", mat_root)
    entries, sig = template_fs_cache.get_material_fs_entries("AL6061")
    print(f"Found {len(entries)} entries")
    if entries:
        for e in entries[:3]:
            print(e)
            
            # test url_join_relative_path without adsk
            relpath_posix = e['relpath']
            default_root = os.path.normpath(os.path.join(os.environ.get("APPDATA", ""), "Autodesk", "CAM360", "templates"))
            if os.path.normpath(root).lower() != default_root.lower():
                abs_path = os.path.join(root, "AL6061", relpath_posix.replace("/", os.sep))
                abs_path_norm = os.path.normpath(abs_path).replace("\\", "/")
                print("Generated URL string:", 'file:///' + abs_path_norm)
                print("Exists on disk?", os.path.exists(abs_path_norm))

if __name__ == '__main__':
    main()
