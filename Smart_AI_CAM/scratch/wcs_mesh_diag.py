# -*- coding: utf-8 -*-
"""MCP diagnostic: compare WCS vs mesh coordinate spaces."""
import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9877

CODE = r"""
import adsk.core, adsk.fusion, adsk.cam

def comp_to_root(comp):
    mat = adsk.core.Matrix3D.create()
    mat.setToIdentity()
    if not comp:
        return mat
    occ = comp.assemblyContext
    while occ:
        mat.transformBy(occ.transform)
        parent = occ.component
        occ = parent.assemblyContext if parent else None
    return mat

def pt_to_root(comp, x, y, z):
    pt = adsk.core.Point3D.create(x, y, z)
    pt.transformBy(comp_to_root(comp))
    return pt.x, pt.y, pt.z

def wcs_local(rx, ry, rz, origin, xa, ya, za):
    dx, dy, dz = rx - origin.x, ry - origin.y, rz - origin.z
    lx = dx * xa.x + dy * xa.y + dz * xa.z
    ly = dx * ya.x + dy * ya.y + dz * ya.z
    lz = dx * za.x + dy * za.y + dz * za.z
    return lx * 10.0, ly * 10.0, lz * 10.0

app = adsk.core.Application.get()
doc = app.activeDocument
des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))
setup = None
if cam:
    for i in range(cam.setups.count):
        s = cam.setups.item(i)
        if s.isActive:
            setup = s
            break
    if not setup and cam.setups.count:
        setup = cam.setups.item(0)
origin, xa, ya, za = setup.workCoordinateSystem.getAsCoordinateSystem()
print("ACTIVE_SETUP", setup.name)
print("WCS_ORIGIN_MM", round(origin.x * 10, 2), round(origin.y * 10, 2), round(origin.z * 10, 2))
print("WCS_Z", round(za.x, 4), round(za.y, 4), round(za.z, 4))

comp, body = None, None
for c in des.allComponents:
    for bi in range(c.bRepBodies.count):
        b = c.bRepBodies.item(bi)
        try:
            if hasattr(b, "isVisible") and not b.isVisible:
                continue
        except Exception:
            pass
        comp, body = c, b
        break
    if body:
        break

if not body:
    print("NO_BODY")
else:
    bb = body.boundingBox
    cx = (bb.minPoint.x + bb.maxPoint.x) / 2.0
    cy = (bb.minPoint.y + bb.maxPoint.y) / 2.0
    cz = (bb.minPoint.z + bb.maxPoint.z) / 2.0
    print("BODY_BB_ROOT_CM_MIN", round(bb.minPoint.x, 4), round(bb.minPoint.y, 4), round(bb.minPoint.z, 4))
    print("BODY_BB_ROOT_CM_MAX", round(bb.maxPoint.x, 4), round(bb.maxPoint.y, 4), round(bb.maxPoint.z, 4))
    print("BODY_CENTER_WCS_MM", [round(v, 2) for v in wcs_local(cx, cy, cz, origin, xa, ya, za)])

    tri = body.meshManager.createMeshCalculator()
    tri.setQuality(adsk.fusion.TriangleMeshQualityOptions.NormalQualityTriangleMesh)
    mesh = tri.calculate()
    coords = list(mesh.nodeCoordinatesAsDouble or [])
    vx, vy, vz = coords[0], coords[1], coords[2]
    rx, ry, rz = pt_to_root(comp, vx, vy, vz)
    print("MESH_V0_RAW_CM", round(vx, 4), round(vy, 4), round(vz, 4))
    print("MESH_V0_ROOT_CM", round(rx, 4), round(ry, 4), round(rz, 4))
    print("MESH_V0_WCS_MM_WITH_ROOT", [round(v, 2) for v in wcs_local(rx, ry, rz, origin, xa, ya, za)])
    print("MESH_V0_WCS_MM_NO_ROOT", [round(v, 2) for v in wcs_local(vx, vy, vz, origin, xa, ya, za)])

    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    mins2 = [1e9, 1e9, 1e9]
    maxs2 = [-1e9, -1e9, -1e9]
    n = len(coords) // 3
    step = max(1, n // 500)
    for i in range(0, n, step):
        vx, vy, vz = coords[i * 3], coords[i * 3 + 1], coords[i * 3 + 2]
        rx, ry, rz = pt_to_root(comp, vx, vy, vz)
        lx, ly, lz = wcs_local(rx, ry, rz, origin, xa, ya, za)
        lx2, ly2, lz2 = wcs_local(vx, vy, vz, origin, xa, ya, za)
        for j, v in enumerate([lx, ly, lz]):
            mins[j] = min(mins[j], v)
            maxs[j] = max(maxs[j], v)
        for j, v in enumerate([lx2, ly2, lz2]):
            mins2[j] = min(mins2[j], v)
            maxs2[j] = max(maxs2[j], v)
    print("MESH_WCS_BBOX_WITH_ROOT", [round(v, 2) for v in mins], [round(v, 2) for v in maxs])
    print("MESH_WCS_BBOX_NO_ROOT", [round(v, 2) for v in mins2], [round(v, 2) for v in maxs2])
    print("COMP_HAS_ASM_CTX", comp.assemblyContext is not None)

result = "done"
"""


def send(action, params=None, timeout=120):
    params = params or {}
    c = socket.socket()
    c.settimeout(timeout)
    c.connect((HOST, PORT))
    c.sendall(
        (json.dumps({"action": action, "params": params}, ensure_ascii=False) + "\n").encode("utf-8")
    )
    buf = ""
    while True:
        d = c.recv(262144)
        if not d:
            break
        buf += d.decode("utf-8", errors="replace")
        if "\n" in buf:
            break
    c.close()
    return json.loads(buf.strip()) if buf.strip() else None


def main():
    print("=== WCS mesh diagnostic via MCP 9877 ===")
    r = send("execute_python_code", {"code": CODE}, timeout=90)
    print(json.dumps(r, ensure_ascii=False, indent=2))

    r2 = send("get_vision_snapshot", {}, timeout=30)
    if r2 and r2.get("success"):
        snap = (r2.get("data") or {}).get("vision_snapshot") or {}
        mesh = (snap.get("recognized_features") or {}).get("mesh_3d") or {}
        wf = mesh.get("wcs_frame") or {}
        verts = mesh.get("vertices") or []
        print("\n=== vision_snapshot mesh_3d ===")
        print("wcs_frame:", json.dumps(wf, ensure_ascii=False))
        print("coordinate_space:", mesh.get("coordinate_space"))
        print("wcs_applied:", mesh.get("wcs_applied"))
        if len(verts) >= 3:
            xs = verts[0::3]
            ys = verts[1::3]
            zs = verts[2::3]
            print(
                "mesh bbox mm:",
                [round(min(xs), 2), round(min(ys), 2), round(min(zs), 2)],
                [round(max(xs), 2), round(max(ys), 2), round(max(zs), 2)],
            )


if __name__ == "__main__":
    main()
