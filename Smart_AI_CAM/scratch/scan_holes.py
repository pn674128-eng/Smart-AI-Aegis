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

result = "Detail analysis of ray hits:\\n"

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
    root_comp = des.rootComponent
    
    # Let's find one hole group
    from Smart_AI.perception import hole_recognizer as hr
    
    # We will run the scan first to find the faces
    body_z_range = {}
    for comp in des.allComponents:
        for bi in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(bi)
            body_z_range[body.entityToken] = hr._bbox_proj_min_max(body.boundingBox, z_axis)
            
    # Run the raw scan_holes_by_ray to inspect
    raw = hr.scan_holes_by_ray(des, setup, trace_through=True)
    
    result += f"Found {len(raw)} hole groups.\\n"
    for idx, r in enumerate(raw):
        result += f"\\n--- Group {idx}: D={r.get('diameter_mm')} mm, through={r.get('through')} ---\\n"
        faces = r.get("faces") or []
        result += f"Faces in group: {len(faces)}\\n"
        
        # Re-run ray cast for this group to get all faces
        # We mimic the ray casting inside analyze_with_ray
        def _bbox_proj_min_max(bb, axis):
            ax, ay, az = axis.x, axis.y, axis.z
            minx, miny, minz = bb.minPoint.x, bb.minPoint.y, bb.minPoint.z
            maxx, maxy, maxz = bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z
            pmax = (maxx if ax >= 0 else minx) * ax + (maxy if ay >= 0 else miny) * ay + (maxz if az >= 0 else minz) * az
            pmin = (minx if ax >= 0 else maxx) * ax + (miny if ay >= 0 else maxy) * ay + (minz if az >= 0 else maxz) * az
            return pmin, pmax
            
        def _surface_type_label(face):
            t = face.geometry.surfaceType
            if t == adsk.core.SurfaceTypes.PlaneSurfaceType: return "Plane"
            if t == adsk.core.SurfaceTypes.CylinderSurfaceType: return "Cylinder"
            if t == adsk.core.SurfaceTypes.ConeSurfaceType: return "Cone"
            if t == adsk.core.SurfaceTypes.SphereSurfaceType: return "Sphere"
            return f"Type({int(t)})"
            
        # Get center
        face = faces[0]
        bb = face.boundingBox
        cx = (bb.minPoint.x + bb.maxPoint.x) / 2
        cy = (bb.minPoint.y + bb.maxPoint.y) / 2
        cz = (bb.minPoint.z + bb.maxPoint.z) / 2
        
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
            cyl = adsk.core.Cylinder.cast(geom)
            pt = cyl.origin
            dx, dy, dz = pt.x - origin.x, pt.y - origin.y, pt.z - origin.z
            cx = origin.x + dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
            cy = origin.y + dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
            cz = origin.z + dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
            
        bmaxz = -1e9
        for body in des.rootComponent.bRepBodies:
            _, bz = _bbox_proj_min_max(body.boundingBox, z_axis)
            if bz > bmaxz: bmaxz = bz
            
        start_pt = adsk.core.Point3D.create(cx + z_axis.x * (bmaxz + 1.0), cy + z_axis.y * (bmaxz + 1.0), cz + z_axis.z * (bmaxz + 1.0))
        ray_dir = adsk.core.Vector3D.create(-z_axis.x, -z_axis.y, -z_axis.z)
        ray_radius = max(geom.radius - 0.01, 0.001)
        
        hit_pts = adsk.core.ObjectCollection.create()
        entities = root_comp.findBRepUsingRay(start_pt, ray_dir, adsk.fusion.BRepEntityTypes.BRepFaceEntityType, ray_radius, False, hit_pts)
        
        result += f"Ray Start: ({start_pt.x:.4f}, {start_pt.y:.4f}, {start_pt.z:.4f})\\n"
        result += f"Ray Radius: {ray_radius:.4f} cm\\n"
        result += f"Hit entities count: {entities.count}\\n"
        for i in range(entities.count):
            f_hit = entities.item(i)
            pt_hit = hit_pts.item(i)
            pt_z = pt_hit.x * z_axis.x + pt_hit.y * z_axis.y + pt_hit.z * z_axis.z
            
            # Print details
            stype = _surface_type_label(f_hit)
            area = f_hit.area
            is_part_of_group = f_hit in faces
            result += f"  Hit {i}: Type={stype}, Z_val={pt_z:.4f} cm, Area={area:.4f}, PartOfGroup={is_part_of_group}\\n"
            
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
    
    if buffer:
        response = json.loads(buffer.strip())
        print(response.get("data", {}).get("result", ""))

if __name__ == "__main__":
    run_remote_code()
