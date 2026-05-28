import os
import shutil
import traceback

src = r"C:\Users\ASUS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\Smart_AI_CAM\palette.html"
dst = r"c:\Users\ASUS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\半自動加工選單【UI穩定版】\palette.html"
out_path = r"C:\Users\ASUS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\Smart_AI_CAM\scratch\sync_status.txt"

try:
    with open(src, "r", encoding="utf-8") as sf:
        content = sf.read()
        
    # Replace brand title and badge text if appropriate
    content = content.replace("<title>Smart AI CAM V2.0317</title>", "<title>半自動加工選單 V2.0317</title>")
    content = content.replace('<span style="font-size:14px;font-weight:600;color:#e8e8e8;">Smart AI CAM</span>', '<span style="font-size:14px;font-weight:600;color:#e8e8e8;">半自動加工選單</span>')
    
    with open(dst, "w", encoding="utf-8") as df:
        df.write(content)
        
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("SYNC SUCCESSFUL\n")
        f.write(f"Copied {len(content)} characters\n")
    print("SYNC SUCCESSFUL")
except Exception as e:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("SYNC ERROR:\n")
        f.write(traceback.format_exc())
    print("SYNC ERROR")
