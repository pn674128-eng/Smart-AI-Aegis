import socket
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HOST = '127.0.0.1'
PORT = 9877

def run_remote_code():
    code = """
import sys
import os
import traceback
import adsk.core
import adsk.fusion
import adsk.cam

result = "Coordinate analysis:\\n"

addin_dir = r"C:\\Users\\ASUS\\AppData\\Roaming\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\半自動加工選單【UI穩定版】"
if addin_dir not in sys.path:
    sys.path.insert(0, addin_dir)

try:
    from Smart_AI.interaction import mcp_entry
    app = adsk.core.Application.get()
    doc = app.activeDocument
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))
    
    setup = mcp_entry._pick_active_setup(cam)
    wcs = setup.workCoordinateSystem
    origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()
    
    result += f"WCS Origin: ({origin.x:.4f}, {origin.y:.4f}, {origin.z:.4f})\\n"
    result += f"WCS Z Axis: ({z_axis.x:.4f}, {z_axis.y:.4f}, {z_axis.z:.4f})\\n"
    
    from Smart_AI.perception import hole_recognizer as hr
    
    raw = hr.scan_holes_by_ray(des, setup, trace_through=True)
    
    for idx, r in enumerate(raw):
        faces = r.get("faces") or []
        face = faces[0]
        bb = face.boundingBox
        cx = (bb.minPoint.x + bb.maxPoint.x) / 2
        cy = (bb.minPoint.y + bb.maxPoint.y) / 2
        cz = (bb.minPoint.z + bb.maxPoint.z) / 2
        
        # projected cz
        proj_cz = cx * z_axis.x + cy * z_axis.y + cz * z_axis.z
        
        bmaxz = -1e9
        for comp_i in des.allComponents:
            for bi in range(comp_i.bRepBodies.count):
                body = comp_i.bRepBodies.item(bi)
                _, bz = hr._bbox_proj_min_max(body.boundingBox, z_axis)
                if bz > bmaxz: bmaxz = bz
                
        start_pt = adsk.core.Point3D.create(cx + z_axis.x * (bmaxz + 1.0), cy + z_axis.y * (bmaxz + 1.0), cz + z_axis.z * (bmaxz + 1.0))
        proj_start_pt = start_pt.x * z_axis.x + start_pt.y * z_axis.y + start_pt.z * z_axis.z
        
        result += f"\\nHole {idx}: D={r.get('diameter_mm')}\\n"
        result += f"  Hole Center World: ({cx:.4f}, {cy:.4f}, {cz:.4f})\\n"
        result += f"  Hole Center Projected: {proj_cz:.4f}\\n"
        result += f"  Body Max Z Projected (bmaxz): {bmaxz:.4f}\\n"
        result += f"  Ray Start World: ({start_pt.x:.4f}, {start_pt.y:.4f}, {start_pt.z:.4f})\\n"
        result += f"  Ray Start Projected: {proj_start_pt:.4f}\\n"
        
except Exception as e:
    result = "Exception: " + traceback.format_exc()
"""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(30.0)
    client.connect((HOST, PORT))
    
    payload = {
        "action": "execute_python_code",
        "params": {"code": code}
    }
    
    client.sendall((json.dumps(payload) + "\n").encode('utf-8'))
    
    buffer = ""
    while True:
        data = client.recv(65536)
        if not data:
            break
        buffer += data.decode('utf-8')
        if "\n" in buffer:
            break
    
    client.close()
    print(response := json.loads(buffer.strip()).get("data", {}).get("result", ""))

if __name__ == "__main__":
    run_remote_code()
