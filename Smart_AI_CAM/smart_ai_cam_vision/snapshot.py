# -*- coding: utf-8 -*-
"""
Read-only part vision snapshot for semi-auto add-in (RayVision eye layer).

Uses hole/slot rows from the main scan pipeline when provided to avoid duplicate scans.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import adsk.cam
import adsk.core
import adsk.fusion

from .modes import inference_mode_from_vision_mode, normalize_vision_mode
from smart_ai_cam_state.runtime_state import state as runtime_state

SPHERICAL_VISION_SAMPLE_COUNT = 512


def _edge_tokens_from_objects(edges) -> List[str]:
    """Convert BRepEdge list (or token strings) to entityToken strings for JSON-safe snapshot."""
    out: List[str] = []
    for e in edges or []:
        if e is None:
            continue
        if isinstance(e, str):
            s = e.strip()
            if s:
                out.append(s)
            continue
        try:
            tok = e.entityToken
            if tok:
                out.append(str(tok))
        except Exception:
            pass
    return out


def snapshot_for_palette_json(snapshot: Optional[dict]) -> dict:
    """Deep-copy snapshot for palette HTML JSON; strip non-serializable Fusion entities."""
    if not snapshot or not isinstance(snapshot, dict):
        return {}

    def _sanitize(obj):
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [_sanitize(x) for x in obj]
        if isinstance(obj, dict):
            clean = {}
            for k, v in obj.items():
                key = str(k)
                if key == "loop_edges":
                    toks = _edge_tokens_from_objects(v)
                    if toks:
                        existing = clean.get("loop_edge_tokens")
                        if isinstance(existing, list):
                            seen = set(existing)
                            for t in toks:
                                if t not in seen:
                                    existing.append(t)
                                    seen.add(t)
                        else:
                            clean["loop_edge_tokens"] = toks
                    continue
                clean[key] = _sanitize(v)
            return clean
        try:
            tok = obj.entityToken
            if tok:
                return str(tok)
        except Exception:
            pass
        try:
            return str(obj)
        except Exception:
            return None

    return _sanitize(snapshot)


def vision_snapshot_json_string(snapshot: Optional[dict]) -> str:
    """JSON string safe for palette.sendInfoToHTML('vision_snapshot', ...)."""
    return json.dumps(snapshot_for_palette_json(snapshot), ensure_ascii=False)


def _collect_vision_target_bodies(design, setup) -> list:
    root = design.rootComponent if design else None
    if not root:
        return []
    target_bodies = []
    if setup:
        try:
            target_bodies = _get_setup_target_bodies(setup, root)
        except Exception:
            target_bodies = []
    if not target_bodies:
        scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
        if scan_bodies is not None:
            for entry in scan_bodies:
                if not entry["visible"]:
                    continue
                target_bodies.append(entry["body"])
        else:
            for comp in design.allComponents:
                for ri in range(comp.bRepBodies.count):
                    try:
                        body = comp.bRepBodies.item(ri)
                        try:
                            if hasattr(body, "isVisible") and not body.isVisible:
                                continue
                        except Exception:
                            pass
                        target_bodies.append(body)
                    except Exception:
                        continue
    return target_bodies


def _get_setup_target_bodies(setup, root) -> list:
    bodies, seen = [], set()
    try:
        models = setup.models
        des = root.parentDesign if hasattr(root, "parentDesign") else None
        for i in range(models.count):
            b = adsk.fusion.BRepBody.cast(models.item(i))
            if not b:
                continue
            mapped = b
            bname = ""
            try:
                bname = b.name or ""
            except Exception:
                pass
            if bname and des:
                found = False
                for comp in des.allComponents:
                    for ri in range(comp.bRepBodies.count):
                        rb = comp.bRepBodies.item(ri)
                        try:
                            if (rb.name or "") == bname:
                                mapped = rb
                                found = True
                                break
                        except Exception:
                            pass
                    if found:
                        break
            try:
                key = mapped.entityToken or ("b_%d" % i)
            except Exception:
                key = "b_%d" % i
            if key in seen:
                continue
            seen.add(key)
            bodies.append(mapped)
    except Exception:
        pass
    return bodies


def _scan_contours(design: adsk.fusion.Design, setup: Optional[adsk.cam.Setup] = None) -> List[dict]:
    from Smart_AI.perception import contour_recognizer as cr

    rows: List[dict] = []
    idx = 0
    wcs = None
    setup_body_tokens = set()
    if setup:
        try:
            wcs = setup.workCoordinateSystem.getAsCoordinateSystem()
            root_comp = design.rootComponent
            target_bodies = _get_setup_target_bodies(setup, root_comp)
            for b in target_bodies:
                try:
                    tok = b.entityToken
                    if tok:
                        setup_body_tokens.add(tok)
                except Exception:
                    pass
        except Exception:
            wcs = None
    bodies_to_scan = []
    scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
    if scan_bodies is not None:
        for entry in scan_bodies:
            if not entry["visible"]:
                continue
            bodies_to_scan.append(entry["body"])
    else:
        for comp in design.allComponents:
            for bi in range(comp.bRepBodies.count):
                body = comp.bRepBodies.item(bi)
                try:
                    if hasattr(body, "isVisible") and not body.isVisible:
                        continue
                except Exception:
                    pass
                bodies_to_scan.append(body)

    for body in bodies_to_scan:
            
            # 只限制掃描為 Setup 的加工本體實體，完美防範毛胚實體的矩形輪廓干擾，且維持 idx 對齊
            is_target = True
            if setup_body_tokens:
                try:
                    tok = body.entityToken
                    if tok and tok not in setup_body_tokens:
                        is_target = False
                except Exception:
                    pass

            if is_target:
                if wcs:
                    origin, x_axis, y_axis, z_axis = wcs
                    top_faces = cr.get_machining_contour_faces_wcs(
                        body, origin, x_axis, y_axis, z_axis
                    )
                else:
                    tf0 = cr.get_top_face(body)
                    top_faces = [tf0] if tf0 else []
                # 視線法摘要：每加工實體只取最大水平頂面作外輪廓，不把孔壁/台阶面算進「輪廓 N」
                planar_tops = []
                for tf in top_faces or []:
                    try:
                        if (
                            tf
                            and tf.geometry.surfaceType
                            == adsk.core.SurfaceTypes.PlaneSurfaceType
                        ):
                            planar_tops.append(tf)
                    except Exception:
                        pass
                if planar_tops:
                    faces_for_contour = [
                        max(planar_tops, key=lambda f: float(f.area))
                    ]
                else:
                    faces_for_contour = list(top_faces[:1]) if top_faces else []
                for ti, tf in enumerate(faces_for_contour):
                    if not tf:
                        continue
                    rec = cr.recognize_contour_edges(tf)
                    loop_edges = cr.get_complete_outer_contour_edges(tf)
                    perim_mm = 0.0
                    for e in loop_edges or rec.get("outer", []) + rec.get("special", []) + rec.get("skipped", []):
                        try:
                            perim_mm += float(e.length) * 10.0
                        except Exception:
                            pass
                    rows.append(
                        {
                            "feature_id": "contour_{}_{}".format(idx, ti),
                            "contour_role": "outer_primary",
                            "recognizer_source": "contour_recognizer",
                            "body_index": idx,
                            "top_face_index": ti,
                            "outer_count": int(rec.get("outer_count", 0)),
                            "special_count": int(rec.get("special_count", 0)),
                            "skipped_count": int(rec.get("skipped_count", 0)),
                            "outer_loop_count": len(loop_edges),
                            "edge_count": int(rec.get("outer_count", 0))
                            + int(rec.get("special_count", 0))
                            + int(rec.get("skipped_count", 0)),
                            "perimeter_mm": round(perim_mm, 3),
                            "draw_layers": {
                                "outer": True,
                                "special": True,
                                "skipped": True,
                                "outer_loop": True,
                            },
                        }
                    )
            idx += 1
    return rows


def _hole_instances_from_scan_rows(
    raw_holes: List[dict],
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    pos_tol_cm: float = 0.05,
) -> List[dict]:
    """Per-hole centers in Setup WCS XY (mm) for vision-layer sketch draw."""
    out: List[dict] = []
    seen = set()

    def snap(v_cm: float) -> float:
        return round(round(v_cm / pos_tol_cm) * pos_tol_cm, 4)

    def face_center_mm(face: adsk.fusion.BRepFace) -> tuple:
        bb = face.boundingBox
        wx = (bb.minPoint.x + bb.maxPoint.x) / 2.0
        wy = (bb.minPoint.y + bb.maxPoint.y) / 2.0
        wz = (bb.minPoint.z + bb.maxPoint.z) / 2.0
        dx, dy, dz = wx - origin.x, wy - origin.y, wz - origin.z
        lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
        ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
        return lx, ly, wx * 10.0, wy * 10.0, wz * 10.0

    for row_idx, row in enumerate(raw_holes or []):
        if not isinstance(row, dict):
            continue
        try:
            dia_mm = float(row.get("diameter_mm", 0.0))
        except Exception:
            continue
        if dia_mm <= 0.0:
            continue
        faces = row.get("faces") or []
        if not faces:
            continue
        for fi, face in enumerate(faces):
            try:
                lx, ly, wx_mm, wy_mm, wz_mm = face_center_mm(face)
            except Exception:
                continue
            key = (snap(lx), snap(ly), round(dia_mm, 3))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "instance_id": "hole_inst_{}_{}".format(row_idx, fi),
                    "feature_type": "hole_instance",
                    "row_index": row_idx,
                    "cx_mm": round(lx * 10.0, 3),
                    "cy_mm": round(ly * 10.0, 3),
                    "world_x_mm": round(wx_mm, 3),
                    "world_y_mm": round(wy_mm, 3),
                    "world_z_mm": round(wz_mm, 3),
                    "diameter_mm": round(dia_mm, 3),
                    "through": bool(row.get("through", False)),
                    "depth_mm": round(float(row.get("depth_mm", 0.0) or 0.0), 3),
                    "direction": str(row.get("dir", "unknown")),
                    "is_threaded": bool(row.get("is_threaded", False)),
                    "thread_designation": str(row.get("thread_designation", "")),
                }
            )
    return out


def _holes_from_scan_rows(raw_holes: List[dict]) -> List[dict]:
    out = []
    for idx, r in enumerate(raw_holes or []):
        if not isinstance(r, dict):
            continue
        try:
            dia = float(r.get("diameter_mm", 0.0))
        except Exception:
            dia = 0.0
        try:
            depth = float(r.get("depth_mm", 0.0))
        except Exception:
            depth = 0.0
        out.append(
            {
                "feature_id": "hole_{}".format(idx),
                "feature_type": "hole",
                "diameter_mm": round(dia, 3),
                "depth_mm": round(depth, 3),
                "through": bool(r.get("through", False)),
                "count": int(r.get("count", r.get("face_count", 1)) or 1),
                "ray_radius_mm": r.get("ray_radius_mm"),
                "direction": str(r.get("dir", "unknown")),
                "is_threaded": bool(r.get("is_threaded", False)),
                "thread_designation": str(r.get("thread_designation", "")),
            }
        )
    return out


def _slots_from_slot_info_list(slot_info_list: List[dict]) -> tuple:
    slots = []
    active = 0
    for idx, s in enumerate(slot_info_list or []):
        if not isinstance(s, dict):
            continue
        is_active = bool(s.get("active", False))
        if is_active:
            active += 1
        try:
            tokens = list(s.get("loop_edge_tokens") or [])
            if not tokens:
                tokens = _edge_tokens_from_objects(s.get("loop_edges"))
            slots.append(
                {
                    "feature_id": "slot_{}".format(idx),
                    "feature_type": "slot",
                    "width_mm": round(float(s.get("width_mm", 0.0)), 3),
                    "length_mm": round(float(s.get("length_mm", 0.0)), 3),
                    "depth_mm": round(float(s.get("depth_mm", 0.0)), 3),
                    "through": bool(s.get("through", False)),
                    "cx_mm": round(float(s.get("cx", 0.0)), 3),
                    "cy_mm": round(float(s.get("cy", 0.0)), 3),
                    "angle_deg": round(float(s.get("angle_deg", 0.0)), 1),
                    "active_for_machining": is_active,
                    "loop_edge_tokens": tokens,
                }
            )
        except Exception:
            continue
    return slots, active


def _topview_semantic(holes: List[dict], slots: List[dict], contours: List[dict]) -> dict:
    outer_chain = {"exists": False, "perimeter_mm": 0.0, "edge_count": 0}
    if contours:
        c0 = max(contours, key=lambda c: float(c.get("perimeter_mm", 0.0)))
        outer_chain = {
            "exists": True,
            "feature_id": str(c0.get("feature_id", "")),
            "perimeter_mm": float(c0.get("perimeter_mm", 0.0)),
            "edge_count": int(c0.get("outer_count", 0)),
        }
    return {
        "outer_chain": outer_chain,
        "inner_openings": {
            "holes": len(holes),
            "slots": sum(1 for s in slots if s.get("active_for_machining")),
        },
    }


def _fibonacci_dirs(n) -> list:
    import math
    dirs = []
    n = max(int(n), 8)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (2.0 * i) / float(n - 1)
        r = max(0.0, 1.0 - y * y) ** 0.5
        theta = golden_angle * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        dirs.append((x, y, z))
    return dirs


def _surface_type_name(surface_type) -> str:
    mapping = {
        adsk.core.SurfaceTypes.PlaneSurfaceType: 'plane',
        adsk.core.SurfaceTypes.CylinderSurfaceType: 'cylinder',
        adsk.core.SurfaceTypes.ConeSurfaceType: 'cone',
        adsk.core.SurfaceTypes.SphereSurfaceType: 'sphere',
        adsk.core.SurfaceTypes.TorusSurfaceType: 'torus',
        adsk.core.SurfaceTypes.NurbsSurfaceType: 'nurbs',
        adsk.core.SurfaceTypes.EllipticalCylinderSurfaceType: 'elliptical_cylinder',
        adsk.core.SurfaceTypes.EllipticalConeSurfaceType: 'elliptical_cone',
    }
    return mapping.get(surface_type, 'other')


def _body_identity_keys(body) -> set:
    keys = set()
    if not body:
        return keys
    for candidate in (body,):
        try:
            tok = candidate.entityToken
            if tok:
                keys.add(tok)
        except Exception:
            pass
        try:
            native = candidate.nativeObject if candidate.nativeObject else candidate
            tok = native.entityToken
            if tok:
                keys.add(tok)
        except Exception:
            pass
        try:
            name = candidate.name or ""
            if name:
                keys.add("name:" + name)
        except Exception:
            pass
    return keys


def _collect_target_scan_keys(target_bodies) -> tuple:
    face_tokens = set()
    body_tokens = set()
    body_names = set()
    for body in target_bodies or []:
        body_tokens.update(_body_identity_keys(body))
        try:
            name = body.name or ""
            if name:
                body_names.add(name)
        except Exception:
            pass
        try:
            for fi in range(body.faces.count):
                face = body.faces.item(fi)
                try:
                    tok = face.entityToken
                    if tok:
                        face_tokens.add(tok)
                except Exception:
                    pass
        except Exception:
            continue
    return face_tokens, body_tokens, body_names


def _face_matches_target_bodies(face, target_bodies, face_tokens, body_tokens, body_names, hit_pt=None) -> bool:
    if not face:
        return False
    try:
        if face.entityToken in face_tokens:
            return True
    except Exception:
        pass
    try:
        face_body = face.body
        if face_body:
            if _body_identity_keys(face_body) & body_tokens:
                return True
            try:
                fb_name = face_body.name or ""
                if fb_name and fb_name in body_names:
                    return True
            except Exception:
                pass
            for target_body in target_bodies or []:
                try:
                    fb_native = face_body.nativeObject if face_body.nativeObject else face_body
                    tb_native = target_body.nativeObject if target_body.nativeObject else target_body
                    if fb_native.entityToken == tb_native.entityToken:
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    if hit_pt is not None:
        for target_body in target_bodies or []:
            try:
                pc = target_body.pointContainment(hit_pt)
                if pc != adsk.fusion.PointContainment.PointOutsidePointContainment:
                    return True
            except Exception:
                pass
    return False


def _append_spherical_hit(points_3d, face, hit_pt, wcs_info=None) -> None:
    if not face or not hit_pt:
        return
    try:
        st_name = _surface_type_name(face.geometry.surfaceType)
    except Exception:
        st_name = 'other'
        
    lx, ly, lz = hit_pt.x, hit_pt.y, hit_pt.z
    if wcs_info:
        origin, x_axis, y_axis, z_axis = wcs_info
        dx, dy, dz = lx - origin.x, ly - origin.y, lz - origin.z
        lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
        ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
        lz = dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
        
    points_3d.append({
        'x': round(lx * 10.0, 3),
        'y': round(ly * 10.0, 3),
        'z': round(lz * 10.0, 3),
        'type': st_name,
    })


def _ray_cast_roots(root, target_bodies) -> list:
    roots = []
    seen = set()
    for body in target_bodies or []:
        comp = None
        try:
            comp = body.parentComponent
        except Exception:
            comp = None
        if not comp:
            continue
        try:
            key = comp.entityToken
        except Exception:
            key = None
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        roots.append(comp)
    if roots:
        return roots
    return [root] if root else []


def _cast_ray_on_components(ray_roots, start, ray_dir, ray_radius_cm):
    for comp in ray_roots or []:
        local_hit_pts = adsk.core.ObjectCollection.create()
        try:
            entities = comp.findBRepUsingRay(
                start,
                ray_dir,
                adsk.fusion.BRepEntityTypes.BRepFaceEntityType,
                ray_radius_cm,
                False,
                local_hit_pts,
            )
        except Exception:
            continue
        if entities and entities.count > 0:
            return entities, local_hit_pts
    return None, None


def _sample_body_surface_points(target_bodies, max_points=384, wcs_info=None) -> list:
    points = []
    bodies = list(target_bodies or [])
    if not bodies:
        return points
    per_body = max(12, int(max_points / max(len(bodies), 1)))
    for body in bodies:
        try:
            face_count = int(body.faces.count)
        except Exception:
            continue
        if face_count <= 0:
            continue
        step = max(1, face_count // per_body)
        for fi in range(0, face_count, step):
            try:
                face = body.faces.item(fi)
                hit_pt = face.pointOnFace
                _append_spherical_hit(points, face, hit_pt, wcs_info)
            except Exception:
                continue
            if len(points) >= max_points:
                return points
    return points


def _component_to_root_matrix(comp) -> adsk.core.Matrix3D:
    """Accumulate occurrence transforms from component up to root."""
    mat = adsk.core.Matrix3D.create()
    mat.setToIdentity()
    if not comp:
        return mat
    try:
        occ = comp.assemblyContext
        while occ:
            mat.transformBy(occ.transform)
            parent = occ.component
            occ = parent.assemblyContext if parent else None
    except Exception:
        pass
    return mat


def _point_cm_to_root(comp, x: float, y: float, z: float):
    pt = adsk.core.Point3D.create(x, y, z)
    try:
        pt.transformBy(_component_to_root_matrix(comp))
    except Exception:
        pass
    return pt.x, pt.y, pt.z


def _vector_to_wcs_local(nx, ny, nz, x_axis, y_axis, z_axis, has_wcs):
    if not has_wcs:
        return nx, ny, nz
    lnx = nx * x_axis.x + ny * x_axis.y + nz * x_axis.z
    lny = nx * y_axis.x + ny * y_axis.y + nz * y_axis.z
    lnz = nx * z_axis.x + ny * z_axis.y + nz * z_axis.z
    return lnx, lny, lnz


def _correct_wcs_origin_for_preview(origin, bodies):
    """
    Some Fusion Setups return WCS origin ~10x body bbox (mm/cm mismatch in API).
    Correct for 3D mesh preview only; hole scan keeps raw API origin.
    """
    if not origin or not bodies:
        return origin
    try:
        bb = bodies[0].boundingBox

        def _maybe_div10(o_val, b_min, b_max):
            for b in (b_min, b_max):
                if abs(b) > 1e-9:
                    ratio = o_val / b
                    if 8.0 <= abs(ratio) <= 12.0:
                        return o_val / 10.0
            return o_val

        ox = _maybe_div10(float(origin.x), bb.minPoint.x, bb.maxPoint.x)
        oy = _maybe_div10(float(origin.y), bb.minPoint.y, bb.maxPoint.y)
        oz = _maybe_div10(float(origin.z), bb.minPoint.z, bb.maxPoint.z)
        if ox == origin.x and oy == origin.y and oz == origin.z:
            return origin
        return adsk.core.Point3D.create(ox, oy, oz)
    except Exception:
        return origin


def _wcs_frame_from_setup(setup) -> tuple:
    """Build wcs_frame JSON + raw Fusion WCS tuple for a CAM Setup."""
    setup_name = ""
    try:
        setup_name = setup.name
    except Exception:
        pass
    try:
        origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()
        origin_world_mm = [
            round(origin.x * 10.0, 4),
            round(origin.y * 10.0, 4),
            round(origin.z * 10.0, 4),
        ]
        frame = {
            # 3D 預覽場景：Setup WCS 本地（原點=0，與零件 mesh 同一空間）
            "origin_mm": [0.0, 0.0, 0.0],
            "origin_world_mm": origin_world_mm,
            "x_axis": [round(x_axis.x, 6), round(x_axis.y, 6), round(x_axis.z, 6)],
            "y_axis": [round(y_axis.x, 6), round(y_axis.y, 6), round(y_axis.z, 6)],
            "z_axis": [round(z_axis.x, 6), round(z_axis.y, 6), round(z_axis.z, 6)],
            "setup_name": setup_name,
            "units": "mm",
            "z_up": True,
            "space": "setup_wcs_local",
        }
        return frame, origin, x_axis, y_axis, z_axis, True
    except Exception:
        frame = {
            "origin_mm": [0.0, 0.0, 0.0],
            "origin_world_mm": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
            "setup_name": setup_name,
            "units": "mm",
            "z_up": True,
            "space": "model_fallback",
        }
        return frame, None, None, None, None, False


def _build_mesh_3d_preview(design, setup, max_triangles=120000) -> dict:
    from smart_ai_cam_ui.diagnostics import send_diag_log

    target_bodies = _collect_vision_target_bodies(design, setup)
    if not target_bodies:
        send_diag_log("[3D Mesh] No target bodies for mesh preview")
        return {
            "ok": False,
            "vertices": [],
            "normals": [],
            "indices": [],
            "triangle_count": 0,
            "vertex_count": 0,
            "body_count": 0,
        }

    wcs_frame, origin, x_axis, y_axis, z_axis, has_wcs = _wcs_frame_from_setup(setup)
    if has_wcs and target_bodies:
        raw_origin = origin
        origin = _correct_wcs_origin_for_preview(origin, target_bodies)
        if (
            origin.x != raw_origin.x
            or origin.y != raw_origin.y
            or origin.z != raw_origin.z
        ):
            wcs_frame["origin_world_mm_api"] = list(wcs_frame.get("origin_world_mm") or [])
            wcs_frame["origin_world_mm"] = [
                round(origin.x * 10.0, 4),
                round(origin.y * 10.0, 4),
                round(origin.z * 10.0, 4),
            ]
            send_diag_log(
                "[3D Mesh] WCS origin corrected for preview cm: ({:.4f},{:.4f},{:.4f}) -> ({:.4f},{:.4f},{:.4f})".format(
                    raw_origin.x,
                    raw_origin.y,
                    raw_origin.z,
                    origin.x,
                    origin.y,
                    origin.z,
                )
            )
    if has_wcs:
        send_diag_log(
            "[3D Mesh] Setup WCS origin_world_mm={} setup={}".format(
                wcs_frame.get("origin_world_mm"), wcs_frame.get("setup_name", "")
            )
        )

    all_vertices: List[float] = []
    all_normals: List[float] = []
    all_indices: List[int] = []
    vertex_offset = 0
    triangle_count = 0
    meshed_bodies = 0

    for body in target_bodies:
        if triangle_count >= max_triangles:
            break
        try:
            mesh_manager = body.meshManager
            if not mesh_manager:
                continue
            mesh_calc = mesh_manager.createMeshCalculator()
            mesh_calc.setQuality(
                adsk.fusion.TriangleMeshQualityOptions.NormalQualityTriangleMesh
            )
            tri_mesh = mesh_calc.calculate()
            if not tri_mesh:
                continue
            coords = list(tri_mesh.nodeCoordinatesAsDouble or [])
            normals = list(tri_mesh.normalVectorsAsDouble or [])
            indices = list(tri_mesh.nodeIndices or [])
            if len(coords) < 9 or len(indices) < 3:
                continue
            n_verts = len(coords) // 3
            comp = None
            try:
                comp = body.parentComponent
            except Exception:
                comp = None

            coords_transformed = []
            normals_transformed = []

            for vi in range(n_verts):
                vx = coords[vi * 3]
                vy = coords[vi * 3 + 1]
                vz = coords[vi * 3 + 2]

                if has_wcs:
                    rx, ry, rz = _point_cm_to_root(comp, vx, vy, vz)
                    dx, dy, dz = rx - origin.x, ry - origin.y, rz - origin.z
                    lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
                    ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
                    lz = dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
                else:
                    lx, ly, lz = vx, vy, vz

                coords_transformed.extend(
                    [round(lx * 10.0, 4), round(ly * 10.0, 4), round(lz * 10.0, 4)]
                )

                if len(normals) >= (vi + 1) * 3:
                    nx = normals[vi * 3]
                    ny = normals[vi * 3 + 1]
                    nz = normals[vi * 3 + 2]
                    lnx, lny, lnz = _vector_to_wcs_local(
                        nx, ny, nz, x_axis, y_axis, z_axis, has_wcs
                    )
                    normals_transformed.extend([round(lnx, 6), round(lny, 6), round(lnz, 6)])
                else:
                    normals_transformed.extend([0.0, 0.0, 1.0])
                    
            all_vertices.extend(coords_transformed)
            all_normals.extend(normals_transformed)
            
            for idx in indices:
                all_indices.append(int(idx) + vertex_offset)
            vertex_offset += n_verts
            triangle_count += len(indices) // 3
            meshed_bodies += 1
        except Exception as ex:
            send_diag_log("[3D Mesh] tessellate failed: {}".format(ex))
            continue

    send_diag_log(
        "[3D Mesh] Preview ready: bodies={} tris={} verts={} wcs={}".format(
            meshed_bodies, triangle_count, len(all_vertices) // 3, has_wcs
        )
    )
    return {
        "ok": len(all_indices) >= 3,
        "vertices": all_vertices,
        "normals": all_normals,
        "indices": all_indices,
        "triangle_count": triangle_count,
        "vertex_count": len(all_vertices) // 3,
        "body_count": meshed_bodies,
        "wcs_applied": has_wcs,
        "coordinate_space": "setup_wcs_local_mm",
        "wcs_frame": wcs_frame,
    }


def _run_spherical_vision_scan(
    des, setup=None, sample_count=SPHERICAL_VISION_SAMPLE_COUNT
) -> dict:
    from smart_ai_cam_ui.diagnostics import send_diag_log
    
    send_diag_log(
        "[3D Scan] Starting spherical vision scan (samples={})...".format(
            int(sample_count)
        )
    )
    
    try:
        wcs_info = setup.workCoordinateSystem.getAsCoordinateSystem()
    except Exception:
        wcs_info = None
        
    root = des.rootComponent if des else None
    if not root:
        send_diag_log("[3D Scan] Error: root component is unavailable")
        return {'ok': False, 'points': []}

    target_bodies = _collect_vision_target_bodies(des, setup)
    send_diag_log("[3D Scan] Target bodies collected: {}".format(len(target_bodies)))

    _xmin = _ymin = _zmin = 1e99
    _xmax = _ymax = _zmax = -1e99
    for _b in target_bodies:
        try:
            _bb = _b.boundingBox
            _xmin = min(_xmin, _bb.minPoint.x); _xmax = max(_xmax, _bb.maxPoint.x)
            _ymin = min(_ymin, _bb.minPoint.y); _ymax = max(_ymax, _bb.maxPoint.y)
            _zmin = min(_zmin, _bb.minPoint.z); _zmax = max(_zmax, _bb.maxPoint.z)
        except Exception:
            continue
            
    send_diag_log(f"[3D Scan] Unified Bounding Box: min({round(_xmin*10.0,2)}, {round(_ymin*10.0,2)}, {round(_zmin*10.0,2)}) max({round(_xmax*10.0,2)}, {round(_ymax*10.0,2)}, {round(_zmax*10.0,2)})")
    
    if _xmin > _xmax:
        send_diag_log("[3D Scan] Error: invalid bounding box (min > max)")
        return {'ok': False, 'points': []}

    _cx = (_xmin + _xmax) * 0.5
    _cy = (_ymin + _ymax) * 0.5
    _cz = (_zmin + _zmax) * 0.5
    center = adsk.core.Point3D.create(_cx, _cy, _cz)
    _dx = _xmax - _xmin; _dy = _ymax - _ymin; _dz = _zmax - _zmin
    part_radius = (_dx * _dx + _dy * _dy + _dz * _dz) ** 0.5 * 0.5
    send_diag_log(f"[3D Scan] Center: ({round(_cx*10.0,2)}, {round(_cy*10.0,2)}, {round(_cz*10.0,2)}), Radius: {round(part_radius*10.0,2)} mm")
    
    if part_radius <= 0:
        send_diag_log("[3D Scan] Error: part radius is <= 0")
        return {'ok': False, 'points': []}

    face_tokens, body_tokens, body_names = _collect_target_scan_keys(target_bodies)
    ray_roots = _ray_cast_roots(root, target_bodies)
    send_diag_log(
        "[3D Scan] Target keys: faces={} bodies={} names={} ray_roots={}".format(
            len(face_tokens), len(body_tokens), len(body_names), len(ray_roots)
        )
    )

    dirs = _fibonacci_dirs(sample_count)
    points_3d = []
    start_scale = 2.2
    SPHERICAL_RAY_RADIUS_CM = max(0.001, min(part_radius * 0.05, 0.05))

    hit_count = 0
    miss_count = 0
    match_fail_count = 0
    fallback_hits = []
    preview_source = "spherical_ray"

    for idx, (dx, dy, dz) in enumerate(dirs):
        start = adsk.core.Point3D.create(
            center.x + dx * part_radius * start_scale,
            center.y + dy * part_radius * start_scale,
            center.z + dz * part_radius * start_scale,
        )
        ray_dir = adsk.core.Vector3D.create(-dx, -dy, -dz)

        entities, local_hit_pts = _cast_ray_on_components(
            ray_roots, start, ray_dir, SPHERICAL_RAY_RADIUS_CM
        )
        if not entities or entities.count == 0:
            miss_count += 1
            continue

        face = None
        face_idx = -1
        hit_pt = None
        for _ei in range(entities.count):
            _f = adsk.fusion.BRepFace.cast(entities.item(_ei))
            if not _f:
                continue
            _pt = None
            if local_hit_pts and local_hit_pts.count > _ei:
                try:
                    _pt = local_hit_pts.item(_ei)
                except Exception:
                    _pt = None
            if _face_matches_target_bodies(
                _f, target_bodies, face_tokens, body_tokens, body_names, _pt
            ):
                face = _f
                face_idx = _ei
                hit_pt = _pt
                break

        if not face:
            match_fail_count += 1
            try:
                _f0 = adsk.fusion.BRepFace.cast(entities.item(0))
                _pt0 = local_hit_pts.item(0) if local_hit_pts and local_hit_pts.count > 0 else None
                if _f0 and _pt0:
                    fallback_hits.append((_f0, _pt0))
            except Exception:
                pass
            continue

        hit_count += 1
        if hit_pt is None and local_hit_pts and local_hit_pts.count > face_idx:
            try:
                hit_pt = local_hit_pts.item(face_idx)
            except Exception:
                hit_pt = None
        _append_spherical_hit(points_3d, face, hit_pt, wcs_info)

    if not points_3d and fallback_hits:
        send_diag_log(
            "[3D Scan] No matched hits; using {} unfiltered ray hits for preview".format(
                len(fallback_hits)
            )
        )
        preview_source = "ray_unfiltered"
        for face, hit_pt in fallback_hits:
            _append_spherical_hit(points_3d, face, hit_pt, wcs_info)

    if not points_3d:
        sampled = _sample_body_surface_points(target_bodies, max_points=384, wcs_info=wcs_info)
        if sampled:
            send_diag_log(
                "[3D Scan] Ray scan empty; using {} face sample points".format(len(sampled))
            )
            points_3d = sampled
            preview_source = "face_sample"

    send_diag_log(
        "[3D Scan] Finished: hits={} misses={} match_fails={} points_recorded={} source={}".format(
            hit_count, miss_count, match_fail_count, len(points_3d), preview_source
        )
    )
    return {
        'ok': True,
        'points': points_3d,
        'diagnostics': {
            'hits': hit_count,
            'misses': miss_count,
            'match_fails': match_fail_count,
            'fallback_used': preview_source != "spherical_ray",
            'preview_source': preview_source,
            'ray_radius_cm': round(SPHERICAL_RAY_RADIUS_CM, 6),
            'sample_count': int(sample_count),
        },
    }


def project_bbox_to_wcs(bbox, setup) -> Optional[dict]:
    """
    Projects all 8 corners of a BoundingBox3D onto the WCS of a CAM Setup,
    returning the (min_u, max_u, min_v, max_v, min_w, max_w) coordinates in mm.
    Note: BoundingBox3D values in Fusion 360 API are in centimeters, so we multiply by 10 to get mm.
    """
    try:
        origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()
    except Exception as ex:
        try:
            from smart_ai_cam_ui.diagnostics import send_diag_log
            send_diag_log(f"[project_bbox] Failed to get WCS axes: {ex}")
        except:
            pass
        return None
        
    min_pt = bbox.minPoint
    max_pt = bbox.maxPoint
    
    # 8 corners of the bounding box in world coordinates (cm)
    corners = [
        adsk.core.Point3D.create(min_pt.x, min_pt.y, min_pt.z),
        adsk.core.Point3D.create(max_pt.x, min_pt.y, min_pt.z),
        adsk.core.Point3D.create(min_pt.x, max_pt.y, min_pt.z),
        adsk.core.Point3D.create(max_pt.x, max_pt.y, min_pt.z),
        adsk.core.Point3D.create(min_pt.x, min_pt.y, max_pt.z),
        adsk.core.Point3D.create(max_pt.x, min_pt.y, max_pt.z),
        adsk.core.Point3D.create(min_pt.x, max_pt.y, max_pt.z),
        adsk.core.Point3D.create(max_pt.x, max_pt.y, max_pt.z)
    ]
    
    min_u = min_v = min_w = float('inf')
    max_u = max_v = max_w = float('-inf')
    
    for p in corners:
        du = p.x - origin.x
        dv = p.y - origin.y
        dw = p.z - origin.z
        
        # Dot product with WCS axes to project, and convert from cm to mm
        u = (du * x_axis.x + dv * x_axis.y + dw * x_axis.z) * 10.0
        v = (du * y_axis.x + dv * y_axis.y + dw * y_axis.z) * 10.0
        w = (du * z_axis.x + dv * z_axis.y + dw * z_axis.z) * 10.0
        
        if u < min_u: min_u = u
        if u > max_u: max_u = u
        if v < min_v: min_v = v
        if v > max_v: max_v = v
        if w < min_w: min_w = w
        if w > max_w: max_w = w
        
    return {
        "min_u": round(min_u, 3),
        "max_u": round(max_u, 3),
        "min_v": round(min_v, 3),
        "max_v": round(max_v, 3),
        "min_w": round(min_w, 3),
        "max_w": round(max_w, 3)
    }


def scan_setup_fixtures(setup) -> List[dict]:
    """
    Scans the fixtures of a CAM Setup, returning a list of dictionaries
    representing each fixture's bounding box and Z height in the WCS (mm).
    """
    fixtures_data = []
    if not setup:
        return fixtures_data
        
    try:
        if not hasattr(setup, "fixtureEnabled") or not setup.fixtureEnabled:
            return fixtures_data
            
        fixtures_coll = getattr(setup, "fixtures", None)
        if not fixtures_coll or fixtures_coll.count == 0:
            return fixtures_data
            
        try:
            from smart_ai_cam_ui.diagnostics import send_diag_log
            send_diag_log(f"[fixtures-scan] Found {fixtures_coll.count} fixture items in Setup '{setup.name}'")
        except:
            pass
        
        for i in range(fixtures_coll.count):
            try:
                item = fixtures_coll.item(i)
                if not item or not getattr(item, "isValid", True):
                    continue
                    
                name = getattr(item, "name", f"Fixture #{i+1}")
                bbox = getattr(item, "boundingBox", None)
                if not bbox:
                    continue
                    
                proj = project_bbox_to_wcs(bbox, setup)
                if proj:
                    fixtures_data.append({
                        "name": name,
                        "min_x": proj["min_u"],
                        "max_x": proj["max_u"],
                        "min_y": proj["min_v"],
                        "max_y": proj["max_v"],
                        "min_z": proj["min_w"],
                        "max_z": proj["max_w"],
                        "token": getattr(item, "entityToken", f"fixture_{i}")
                    })
            except Exception as e_item:
                try:
                    from smart_ai_cam_ui.diagnostics import send_diag_log
                    send_diag_log(f"[fixtures-scan] Failed to scan item {i+1}: {e_item}")
                except:
                    pass
    except Exception as ex:
        try:
            from smart_ai_cam_ui.diagnostics import send_diag_log
            send_diag_log(f"[fixtures-scan] Scan error: {ex}")
        except:
            pass
        
    return fixtures_data


def build_part_vision_snapshot(
    *,
    design: adsk.fusion.Design,
    setup: adsk.cam.Setup,
    vision_mode: str = "FAST_2D",
    holes_rows: Optional[List[dict]] = None,
    slot_info_list: Optional[List[dict]] = None,
    hole_list_count: Optional[int] = None,
) -> dict:
    """
    Build full vision snapshot. Prefer holes_rows / slot_info_list from main scan.
    """
    mode = normalize_vision_mode(vision_mode)
    errors: List[str] = []
    setup_name = ""
    try:
        setup_name = setup.name
    except Exception:
        pass

    try:
        raw_holes = list(holes_rows or [])
        origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()
        wcs_frame, _, _, _, _, _ = _wcs_frame_from_setup(setup)
        contours = _scan_contours(design, setup)
        slots, slot_active = _slots_from_slot_info_list(slot_info_list or [])
        holes = _holes_from_scan_rows(raw_holes)
        hole_instances = _hole_instances_from_scan_rows(raw_holes, origin, x_axis, y_axis)

        special_profiles = []
        try:
            from Smart_AI.perception.contour_extension_recognizer import scan_undercuts_and_tslots
            special_profiles = scan_undercuts_and_tslots(design, setup, visible_only=True)
        except Exception as ex:
            errors.append("scan_special_profiles_failed: {}".format(ex))

        topview = _topview_semantic(holes, slots, contours)
        inference = inference_mode_from_vision_mode(mode)
        contours_primary = sum(
            1 for c in contours if str(c.get("contour_role", "")) == "outer_primary"
        )

        points_3d = []
        mesh_3d = {}
        spherical_diag = {}
        mesh_diag = {}
        if mode == "FULL_3D":
            try:
                mesh_3d = _build_mesh_3d_preview(design, setup)
                mesh_diag = {
                    "ok": bool(mesh_3d.get("ok")),
                    "triangle_count": int(mesh_3d.get("triangle_count") or 0),
                    "vertex_count": int(mesh_3d.get("vertex_count") or 0),
                    "body_count": int(mesh_3d.get("body_count") or 0),
                }
            except Exception as ex:
                errors.append("mesh_preview_failed: {}".format(ex))
            try:
                res_3d = _run_spherical_vision_scan(design, setup)
                if res_3d.get("ok"):
                    points_3d = res_3d.get("points", [])
                    spherical_diag = dict(res_3d.get("diagnostics") or {})
            except Exception as ex:
                errors.append("spherical_scan_failed: {}".format(ex))

        return {
            "ok": True,
            "reason": "",
            "plugin": "semi_auto_cam_vision",
            "vision_mode": mode,
            "machining_basis": {
                "coordinate_system": "WCS_STRICT",
                "direction_rule": "WCS Z+ -> WCS Z-",
                "inference_mode": inference,
                "setup_name": setup_name,
                "wcs_frame": wcs_frame,
            },
            "recognized_features": {
                "holes": holes,
                "hole_instances": hole_instances,
                "slots": slots,
                "contours": contours,
                "fixtures": scan_setup_fixtures(setup),
                "special_profiles": special_profiles,
                "points_3d": points_3d,
                "mesh_3d": mesh_3d if mesh_3d.get("ok") else {},
            },
            "draw_plan": {
                "source": "vision_snapshot",
                "sketch_name": "SemiAuto_VisionSketch",
                "layers": {
                    "hole_circles": True,
                    "slots_all": True,
                    "slots_active_only": False,
                    "contour_outer": True,
                    "contour_special": True,
                    "contour_skipped": True,
                    "contour_outer_loop": True,
                    "contour_all_bodies": True,
                },
            },
            "profiles": {
                "mode": mode,
                "topview_semantic": topview,
            },
            "scan_diagnostics": {
                "recognizer_source": "semi_auto_recognizers",
                "hole_rows": len(raw_holes),
                "hole_instance_count": len(hole_instances),
                "hole_list_count": int(hole_list_count if hole_list_count is not None else len(holes)),
                "slot_rows": len(slot_info_list or []),
                "slot_active_rows": slot_active,
                "contour_rows": len(contours),
                "contour_primary_rows": contours_primary,
                "special_profile_rows": len(special_profiles),
                "mesh_preview": mesh_diag,
                "spherical_scan": spherical_diag,
                "errors": errors,
            },
        }
    except Exception as ex:
        return {
            "ok": False,
            "reason": "snapshot_build_exception: {}".format(ex),
            "vision_mode": mode,
            "machining_basis": {
                "coordinate_system": "WCS_STRICT",
                "inference_mode": inference_mode_from_vision_mode(mode),
                "setup_name": setup_name,
            },
            "recognized_features": {
                "holes": [],
                "hole_instances": [],
                "slots": [],
                "contours": [],
                "points_3d": [],
            },
            "profiles": {"mode": mode, "topview_semantic": _topview_semantic([], [], [])},
            "scan_diagnostics": {"errors": [str(ex)]},
        }


def vision_summary_for_init(snapshot: Optional[dict]) -> dict:
    """Compact payload for palette init JSON."""
    if not snapshot or not isinstance(snapshot, dict):
        return {"enabled": False, "ok": False, "reason": "no_snapshot"}
    if not snapshot.get("ok"):
        return {
            "enabled": True,
            "ok": False,
            "reason": str(snapshot.get("reason", "unknown")),
            "vision_mode": snapshot.get("vision_mode", "FAST_2D"),
        }
    diag = snapshot.get("scan_diagnostics") or {}
    feats = snapshot.get("recognized_features") or {}
    topview = (snapshot.get("profiles") or {}).get("topview_semantic") or {}
    outer = topview.get("outer_chain") or {}
    mb = snapshot.get("machining_basis") or {}
    return {
        "enabled": True,
        "ok": True,
        "vision_mode": str(snapshot.get("vision_mode", "FAST_2D")),
        "setup_name": str(mb.get("setup_name", "")),
        "counts": {
            "holes_scan": int(diag.get("hole_rows", 0)),
            "hole_instances": int(diag.get("hole_instance_count", 0)),
            "holes_list": int(diag.get("hole_list_count", 0)),
            "slots": int(diag.get("slot_rows", 0)),
            "slots_active": int(diag.get("slot_active_rows", 0)),
            "contours": int(diag.get("contour_rows", len(feats.get("contours") or []))),
            "contours_primary": int(
                diag.get(
                    "contour_primary_rows",
                    diag.get("contour_rows", len(feats.get("contours") or [])),
                )
            ),
            "fixtures": len(feats.get("fixtures") or []),
            "special_profiles": len(feats.get("special_profiles") or []),
        },
        "outer_perimeter_mm": float(outer.get("perimeter_mm", 0.0)) if outer.get("exists") else None,
        "errors": list(diag.get("errors") or [])[:8],
    }
