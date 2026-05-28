import os

files_to_search = [
    r"c:\Users\ASUS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\半自動加工選單【UI穩定版】\半自動加工選單【UI穩定版】.py",
    r"C:\Users\ASUS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\Smart_AI_CAM\Smart_AI_CAM.py",
]
out_path = "find_mesh_results.txt"

try:
    with open(out_path, "w", encoding="utf-8") as out_f:
        for filepath in files_to_search:
            out_f.write(f"\n=================== SEARCHING: {filepath} ===================\n")
            if not os.path.exists(filepath):
                out_f.write("FILE DOES NOT EXIST\n")
                continue
                
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            for idx, line in enumerate(lines):
                # Search for mesh related keywords
                if "mesh_3d" in line or "mesh3d" in line or "getTriangleMesh" in line or "meshManager" in line or "calculateMesh" in line:
                    out_f.write(f"Line {idx+1}: {line.strip()}\n")
                    # Write surrounding 3 lines
                    start = max(0, idx - 5)
                    end = min(len(lines), idx + 8)
                    out_f.write("--- Context ---\n")
                    for c_idx in range(start, end):
                        prefix = ">>> " if c_idx == idx else "    "
                        out_f.write(f"{prefix}{c_idx+1}: {lines[c_idx]}")
                    out_f.write("---------------\n")
    print("SUCCESS")
except Exception as e:
    import traceback
    with open(out_path, "w", encoding="utf-8") as out_f:
        out_f.write(traceback.format_exc())
    print("ERROR")
