# -*- coding: utf-8 -*-

"""Draw top-face sketch from vision_snapshot (read-only verification)."""

from __future__ import annotations

import math

from typing import Any, Dict, List, Optional

import adsk.cam

import adsk.core

import adsk.fusion

SKETCH_NAME_VISION = "SemiAuto_VisionSketch"

SKETCH_NAME_DEFAULT = SKETCH_NAME_VISION

def _pick_active_setup(cam):

    if not cam or cam.setups.count < 1:

        return None

    for i in range(cam.setups.count):

        s = cam.setups.item(i)

        try:

            if s.isActive:

                return s

        except Exception:

            pass

    return cam.setups.item(0)

def _setup_target_bodies(setup, root):

    bodies, seen = [], set()

    try:

        models = setup.models

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

            if bname:

                for ri in range(root.bRepBodies.count):

                    rb = root.bRepBodies.item(ri)

                    try:

                        if (rb.name or "") == bname:

                            mapped = rb

                            break

                    except Exception:

                        pass

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

    if not bodies and root.bRepBodies.count > 0:

        bodies = [root.bRepBodies.item(0)]

    return bodies

def _find_top_face(bodies, origin, x_axis, y_axis, z_axis):

    def body_xy_area(body):

        try:

            bb = body.boundingBox

            corners = [

                (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z),

                (bb.minPoint.x, bb.minPoint.y, bb.maxPoint.z),

                (bb.minPoint.x, bb.maxPoint.y, bb.minPoint.z),

                (bb.minPoint.x, bb.maxPoint.y, bb.maxPoint.z),

                (bb.maxPoint.x, bb.minPoint.y, bb.minPoint.z),

                (bb.maxPoint.x, bb.minPoint.y, bb.maxPoint.z),

                (bb.maxPoint.x, bb.maxPoint.y, bb.minPoint.z),

                (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z),

            ]

            xmin = ymin = 1.0e99

            xmax = ymax = -1.0e99

            for x0, y0, z0 in corners:

                px = x0 * x_axis.x + y0 * x_axis.y + z0 * x_axis.z

                py = x0 * y_axis.x + y0 * y_axis.y + z0 * y_axis.z

                xmin, xmax = min(xmin, px), max(xmax, px)

                ymin, ymax = min(ymin, py), max(ymax, py)

            return max(0.0, xmax - xmin) * max(0.0, ymax - ymin)

        except Exception:

            return 0.0

    envelope, best = None, -1.0

    for b in bodies:

        a = body_xy_area(b)

        if a > best:

            best, envelope = a, b

    if not envelope and bodies:

        envelope = bodies[0]

    if not envelope:

        return None

    top_face, top_proj = None, -1.0e99

    for fi in range(envelope.faces.count):

        face = envelope.faces.item(fi)

        try:

            geom = face.geometry

            if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:

                continue

            normal = adsk.core.Plane.cast(geom).normal

            ndot = float(normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z)

            if abs(abs(ndot) - 1.0) > 0.01:

                continue

            bb = face.boundingBox

            cx = 0.5 * (bb.minPoint.x + bb.maxPoint.x)

            cy = 0.5 * (bb.minPoint.y + bb.maxPoint.y)

            cz = 0.5 * (bb.minPoint.z + bb.maxPoint.z)

            proj = float(cx * z_axis.x + cy * z_axis.y + cz * z_axis.z)

            if proj > top_proj:

                top_proj, top_face = proj, face

        except Exception:

            pass

    return top_face

def _local_xy_cm_from_face(face, origin, x_axis, y_axis):
    # 完美避免 split-cylinder 的 bbox 偏置 Bug，優先使用圓柱幾何軸心 (Cylinder.origin)
    try:
        if face.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
            cyl = adsk.core.Cylinder.cast(face.geometry)
            pt = cyl.origin
            dx, dy, dz = pt.x - origin.x, pt.y - origin.y, pt.z - origin.z
            lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
            ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
            return lx, ly
    except Exception:
        pass

    bb = face.boundingBox

    wx = (bb.minPoint.x + bb.maxPoint.x) / 2.0

    wy = (bb.minPoint.y + bb.maxPoint.y) / 2.0

    wz = (bb.minPoint.z + bb.maxPoint.z) / 2.0

    dx, dy, dz = wx - origin.x, wy - origin.y, wz - origin.z

    lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z

    ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z

    return lx, ly

def _hole_centers_from_rows(holes_rows, origin, x_axis, y_axis, pos_tol_cm=0.05):

    out, seen = [], set()

    def snap(v):

        return round(round(v / pos_tol_cm) * pos_tol_cm, 4)

    for row in holes_rows or []:

        if not isinstance(row, dict):

            continue

        try:

            dia_mm = float(row.get("diameter_mm", 0.0))

        except Exception:

            continue

        if dia_mm <= 0:

            continue

        for f in row.get("faces") or []:

            try:

                lx, ly = _local_xy_cm_from_face(f, origin, x_axis, y_axis)

            except Exception:

                continue

            key = (snap(lx), snap(ly), round(dia_mm, 3))

            if key in seen:

                continue

            seen.add(key)

            out.append({"cx_mm": round(lx * 10.0, 3), "cy_mm": round(ly * 10.0, 3), "diameter_mm": round(dia_mm, 3)})

    return out

def _body_max_wcs_z_cm(bodies, origin, z_axis):
    zmax = -1.0e99
    for body in bodies or []:
        try:
            bb = body.boundingBox
            for x, y, z in (
                (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z),
                (bb.minPoint.x, bb.minPoint.y, bb.maxPoint.z),
                (bb.minPoint.x, bb.maxPoint.y, bb.minPoint.z),
                (bb.minPoint.x, bb.maxPoint.y, bb.maxPoint.z),
                (bb.maxPoint.x, bb.minPoint.y, bb.minPoint.z),
                (bb.maxPoint.x, bb.minPoint.y, bb.maxPoint.z),
                (bb.maxPoint.x, bb.maxPoint.y, bb.minPoint.z),
                (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z),
            ):
                dz = (x - origin.x) * z_axis.x + (y - origin.y) * z_axis.y + (z - origin.z) * z_axis.z
                zmax = max(zmax, float(dz))
        except Exception:
            pass
    return zmax if zmax > -1.0e90 else 0.0


def _wcs_point_on_setup_z_top(origin, x_axis, y_axis, z_axis, lx_cm, ly_cm, z_top_cm):
    """World point on Setup WCS XY plane at body top Z (orthographic sketch basis)."""
    bx = origin.x + lx_cm * x_axis.x + ly_cm * y_axis.x
    by = origin.y + lx_cm * x_axis.y + ly_cm * y_axis.y
    bz = origin.z + lx_cm * x_axis.z + ly_cm * y_axis.z
    z_base = (bx - origin.x) * z_axis.x + (by - origin.y) * z_axis.y + (bz - origin.z) * z_axis.z
    dz = float(z_top_cm) - z_base
    return adsk.core.Point3D.create(
        bx + dz * z_axis.x,
        by + dz * z_axis.y,
        bz + dz * z_axis.z,
    )


def _wcs_point_on_top_face(origin, x_axis, y_axis, z_axis, lx_cm, ly_cm, top_face):
    """Legacy: point on a specific top face plane (fallback)."""
    ox = origin.x + lx_cm * x_axis.x + ly_cm * y_axis.x
    oy = origin.y + lx_cm * x_axis.y + ly_cm * y_axis.y
    oz = origin.z + lx_cm * x_axis.z + ly_cm * y_axis.z
    try:
        plane = adsk.core.Plane.cast(top_face.geometry)
        n = plane.normal
        p0 = plane.origin
        ndotz = n.x * z_axis.x + n.y * z_axis.y + n.z * z_axis.z
        if abs(ndotz) < 1e-12:
            return adsk.core.Point3D.create(ox, oy, oz)
        lz = (n.x * (p0.x - ox) + n.y * (p0.y - oy) + n.z * (p0.z - oz)) / ndotz
        return adsk.core.Point3D.create(
            ox + lz * z_axis.x,
            oy + lz * z_axis.y,
            oz + lz * z_axis.z,
        )
    except Exception:
        return adsk.core.Point3D.create(ox, oy, oz)


def _delete_component_by_name(collection, name):
    for i in range(collection.count - 1, -1, -1):
        item = collection.item(i)
        try:
            if item and item.name == name:
                item.deleteMe()
        except Exception:
            pass


def _create_sketch_on_setup_wcs_top(root, setup, bodies, sketch_name):
    """Sketch on Setup WCS XY at body top Z (true top view, not a single pad face)."""
    origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()
    z_top = _body_max_wcs_z_cm(bodies, origin, z_axis) + 0.02
    plane_name = sketch_name + "_plane"
    _delete_component_by_name(root.constructionPlanes, plane_name)
    _delete_component_by_name(root.sketches, sketch_name)
    plane_input = root.constructionPlanes.createInput()
    plane_origin = _wcs_point_on_setup_z_top(origin, x_axis, y_axis, z_axis, 0.0, 0.0, z_top)
    plane_input.setByOriginAndVectors(plane_origin, x_axis, y_axis)
    plane = root.constructionPlanes.add(plane_input)
    try:
        plane.name = plane_name
    except Exception:
        pass
    sk = root.sketches.add(plane)
    sk.name = sketch_name
    return sk, z_top

def _draw_hole_circles(sk, circles, origin, x_axis, y_axis, z_axis, z_top_cm=None, top_face=None):
    coll, n = sk.sketchCurves.sketchCircles, 0
    for c in circles:
        try:
            r_cm = float(c["diameter_mm"]) / 20.0
            lx, ly = float(c["cx_mm"]) / 10.0, float(c["cy_mm"]) / 10.0
            if z_top_cm is not None:
                wp = _wcs_point_on_setup_z_top(origin, x_axis, y_axis, z_axis, lx, ly, z_top_cm)
            elif top_face:
                wp = _wcs_point_on_top_face(origin, x_axis, y_axis, z_axis, lx, ly, top_face)
            else:
                continue
            sp = sk.modelToSketchSpace(wp)
            coll.addByCenterRadius(sp, r_cm)
            n += 1
        except Exception:
            pass
    return n


def _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, u, v, z_top_cm=None, top_face=None):
    lx = cx + u * ux + v * vx
    ly = cy + u * uy + v * vy
    if z_top_cm is not None:
        wp = _wcs_point_on_setup_z_top(origin, x_axis, y_axis, z_axis, lx, ly, z_top_cm)
    elif top_face:
        wp = _wcs_point_on_top_face(origin, x_axis, y_axis, z_axis, lx, ly, top_face)
    else:
        return None
    return sk.modelToSketchSpace(wp)


def _draw_slot_capsule(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, half_len_cm, half_wid_cm, z_top_cm=None, top_face=None):
    """Obround slot: two semicircles + straight sides (no bounding rectangle)."""
    lines = sk.sketchCurves.sketchLines
    arcs = sk.sketchCurves.sketchArcs
    r = half_wid_cm
    if r <= 0:
        return 0
    if half_len_cm <= r + 1e-9:
        try:
            center = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, 0.0, 0.0, z_top_cm, top_face)
            sk.sketchCurves.sketchCircles.addByCenterRadius(center, r)
            return 1
        except Exception:
            return 0
    d = half_len_cm - r
    try:
        p_bl = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, -d, -r, z_top_cm, top_face)
        p_br = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, d, -r, z_top_cm, top_face)
        p_tl = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, -d, r, z_top_cm, top_face)
        p_tr = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, d, r, z_top_cm, top_face)
        lines.addByTwoPoints(p_bl, p_br)
        lines.addByTwoPoints(p_tl, p_tr)
        c_l = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, -d, 0.0, z_top_cm, top_face)
        c_r = _slot_sketch_point(sk, origin, x_axis, y_axis, z_axis, cx, cy, ux, uy, vx, vy, d, 0.0, z_top_cm, top_face)
        arcs.addByCenterStartSweep(c_l, p_tl, math.pi)
        arcs.addByCenterStartSweep(c_r, p_br, math.pi)
        return 1
    except Exception:
        return 0


def _draw_slot_rects(sk, slots, origin, x_axis, y_axis, z_axis, z_top_cm=None, top_face=None, drawn_tokens=None, design=None):
    """Draw slot as true loop edges when available; else obround capsule (not a square box)."""
    n = 0
    for s in slots or []:
        if not isinstance(s, dict):
            continue
        loop_edges = list(s.get("loop_edges") or [])
        if not loop_edges:
            toks = list(s.get("loop_edge_tokens") or [])
            if toks and design:
                try:
                    from smart_ai_cam_machining.geometry_utils import _resolve_slot_loop_edges_from_tokens
                    loop_edges = _resolve_slot_loop_edges_from_tokens(design, toks)
                except Exception:
                    loop_edges = []
        if loop_edges:
            n += _draw_contour_edge_list(sk, loop_edges, drawn_tokens)
            continue
        try:
            cx = float(s.get("cx", 0.0)) / 10.0
            cy = float(s.get("cy", 0.0)) / 10.0
            half_len_cm = float(s.get("length_mm", 0.0)) / 20.0
            half_wid_cm = float(s.get("width_mm", 0.0)) / 20.0
            ang = math.radians(float(s.get("angle_deg", 0.0)))
        except Exception:
            continue
        if half_len_cm <= 0 or half_wid_cm <= 0:
            continue
        ux, uy = math.cos(ang), math.sin(ang)
        vx, vy = -math.sin(ang), math.cos(ang)
        n += _draw_slot_capsule(
            sk, origin, x_axis, y_axis, z_axis,
            cx, cy, ux, uy, vx, vy, half_len_cm, half_wid_cm, z_top_cm, top_face,
        )
    return n

def _top_z_cm_from_face_bbox(bb, z_axis):

    top_z_cm = max(

        bb.minPoint.x * z_axis.x + bb.minPoint.y * z_axis.y + bb.minPoint.z * z_axis.z,

        bb.maxPoint.x * z_axis.x + bb.maxPoint.y * z_axis.y + bb.maxPoint.z * z_axis.z,

    )

    for c in (

        (bb.minPoint.x, bb.minPoint.y, bb.maxPoint.z),

        (bb.maxPoint.x, bb.minPoint.y, bb.maxPoint.z),

        (bb.minPoint.x, bb.maxPoint.y, bb.maxPoint.z),

        (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z),

    ):

        top_z_cm = max(top_z_cm, c[0] * z_axis.x + c[1] * z_axis.y + c[2] * z_axis.z)

    return top_z_cm

def _body_by_index(design, body_index):
    idx = 0
    for comp in design.allComponents:
        for bi in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(bi)
            try:
                if hasattr(body, "isVisible") and not body.isVisible:
                    continue
            except Exception:
                pass
            if idx == int(body_index):
                return body
            idx += 1
    return None


def _top_faces_for_contour_body_index(design, body_index, origin, x_axis, y_axis, z_axis):
    from Smart_AI.perception import contour_recognizer as cr
    body = _body_by_index(design, body_index)
    if not body:
        return []
    if origin is not None and x_axis is not None and y_axis is not None and z_axis is not None:
        return cr.get_machining_contour_faces_wcs(body, origin, x_axis, y_axis, z_axis)
    tf = cr.get_top_face(body)
    return [tf] if tf else []

def _draw_contour_edge_list(sk, edges, drawn_tokens=None):
    lines, n = sk.sketchCurves.sketchLines, 0
    for edge in edges or []:
        if drawn_tokens is not None:
            try:
                from Smart_AI.perception.contour_recognizer import _edge_token
                key = _edge_token(edge)
            except Exception:
                key = str(id(edge))
            if key in drawn_tokens:
                continue
            drawn_tokens.add(key)
        try:
            oc = sk.project(edge)
            if oc and oc.count > 0:
                n += int(oc.count)
                continue
        except Exception:
            pass
        try:
            sp, ep = edge.evaluator.getEndPoints()
            lines.addByTwoPoints(sk.modelToSketchSpace(sp), sk.modelToSketchSpace(ep))
            n += 1
        except Exception:
            pass
    return n

def _draw_vision_contours(sk, design, contours, draw_plan, setup=None, bodies=None):
    from Smart_AI.perception import contour_recognizer as cr
    layers_plan = (draw_plan or {}).get("layers") or {}
    if not layers_plan.get("contour_outer", True) and not layers_plan.get("contour_outer_loop", True):
        return 0, 0, 0
    origin = x_axis = y_axis = z_axis = None
    if setup:
        try:
            origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()
        except Exception:
            pass
    if not bodies and setup and design:
        try:
            bodies = _setup_target_bodies(setup, design.rootComponent)
        except Exception:
            bodies = []
    drawn_tokens = set()
    n_outer = 0
    if bodies and origin is not None and z_axis is not None:
        for body in bodies:
            edges = cr.collect_machining_outline_edges_wcs(
                body, origin, x_axis, y_axis, z_axis
            )
            n_outer += _draw_contour_edge_list(sk, edges, drawn_tokens)
        return n_outer, 0, 0
    if not contours:
        return 0, 0, 0
    use_skipped = bool(layers_plan.get("contour_skipped", True))
    use_outer_loop = bool(layers_plan.get("contour_outer_loop", True))
    draw_all = bool(layers_plan.get("contour_all_bodies", True))
    rows = list(contours or [])
    if not draw_all and rows:
        rows = [max(rows, key=lambda c: float(c.get("perimeter_mm", 0.0)))]
    body_indices = sorted({int(r.get("body_index", 0)) for r in rows})
    for body_index in body_indices:
        body = _body_by_index(design, body_index)
        if not body or z_axis is None:
            continue
        n_outer += _draw_contour_edge_list(
            sk,
            cr.collect_machining_outline_edges_wcs(body, origin, x_axis, y_axis, z_axis),
            drawn_tokens,
        )
    return n_outer, 0, 0

def _vision_slots_for_draw(slots, draw_plan):

    layers = (draw_plan or {}).get("layers") or {}

    active_only = bool(layers.get("slots_active_only", False))

    out = []

    for s in slots or []:

        if not isinstance(s, dict):

            continue

        if active_only and not s.get("active_for_machining"):

            continue

        out.append(
            {
                "cx": s.get("cx_mm", s.get("cx", 0.0)),
                "cy": s.get("cy_mm", s.get("cy", 0.0)),
                "width_mm": s.get("width_mm", 0.0),
                "length_mm": s.get("length_mm", 0.0),
                "angle_deg": s.get("angle_deg", 0.0),
                "loop_edge_tokens": list(s.get("loop_edge_tokens") or []),
            }
        )

    return out

def create_recognition_sketch_from_vision(vision_snapshot, setup=None, sketch_name=None):

    """Draw sketch using vision_snapshot only (same or richer than recognizer-direct draw)."""

    if not vision_snapshot or not isinstance(vision_snapshot, dict):

        return {"ok": False, "message": "vision_snapshot missing", "sketch_name": "", "source": "vision"}

    if not vision_snapshot.get("ok"):

        return {

            "ok": False,

            "message": str(vision_snapshot.get("reason", "vision snapshot not ok")),

            "sketch_name": "",

            "source": "vision",

        }

    draw_plan = vision_snapshot.get("draw_plan") or {}

    sketch_name = sketch_name or draw_plan.get("sketch_name") or SKETCH_NAME_VISION

    feats = vision_snapshot.get("recognized_features") or {}

    hole_instances = list(feats.get("hole_instances") or [])

    slots = list(feats.get("slots") or [])

    contours = list(feats.get("contours") or [])

    app = adsk.core.Application.get()

    if not app or not app.activeDocument:

        return {"ok": False, "message": "no active document", "sketch_name": "", "source": "vision"}

    doc = app.activeDocument

    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))

    if not des or not des.rootComponent:

        return {"ok": False, "message": "no design", "sketch_name": "", "source": "vision"}

    cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))

    if not cam:

        return {"ok": False, "message": "no cam", "sketch_name": "", "source": "vision"}

    setup = setup or _pick_active_setup(cam)

    if not setup:

        return {"ok": False, "message": "no setup", "sketch_name": "", "source": "vision"}

    setup_suffix = f"_{setup.name}"
    if not sketch_name.endswith(setup_suffix):
        sketch_name = f"{sketch_name}{setup_suffix}"

    root = des.rootComponent

    bodies = _setup_target_bodies(setup, root)

    if not bodies:

        return {"ok": False, "message": "no setup bodies", "sketch_name": "", "source": "vision"}

    origin, x_axis, y_axis, z_axis = setup.workCoordinateSystem.getAsCoordinateSystem()

    try:
        sk, z_top = _create_sketch_on_setup_wcs_top(root, setup, bodies, sketch_name)
    except Exception as ex:
        top_face = _find_top_face(bodies, origin, x_axis, y_axis, z_axis)
        if not top_face:
            return {"ok": False, "message": "sketch plane failed: {}".format(ex), "sketch_name": "", "source": "vision"}
        _delete_component_by_name(root.sketches, sketch_name)
        sk = root.sketches.add(top_face)
        sk.name = sketch_name
        z_top = _body_max_wcs_z_cm(bodies, origin, z_axis)

    if not hole_instances:

        return {

            "ok": False,

            "message": "vision snapshot has no hole_instances; rescan to refresh vision layer",

            "sketch_name": sketch_name,

            "source": "vision",

        }

    drawn_tokens = set()
    n_holes = _draw_hole_circles(
        sk, hole_instances, origin, x_axis, y_axis, z_axis, z_top_cm=z_top
    )
    n_slots = _draw_slot_rects(
        sk,
        _vision_slots_for_draw(slots, draw_plan),
        origin,
        x_axis,
        y_axis,
        z_axis,
        z_top_cm=z_top,
        drawn_tokens=drawn_tokens,
        design=des,
    )
    n_outer, n_special, n_skipped = _draw_vision_contours(
        sk, des, contours, draw_plan, setup, bodies=bodies
    )

    n_contour = n_outer + n_special + n_skipped

    return {

        "ok": True,

        "message": "vision holes=%d slots=%d contour=%d (outer=%d special=%d skipped=%d)"

        % (n_holes, n_slots, n_contour, n_outer, n_special, n_skipped),

        "sketch_name": sketch_name,

        "source": "vision",

        "vision_mode": vision_snapshot.get("vision_mode", "FAST_2D"),

        "hole_circles": n_holes,

        "slots": n_slots,

        "contour_segments": n_contour,

        "contour_outer": n_outer,

        "contour_special": n_special,

        "contour_skipped": n_skipped,

        "setup_name": setup.name,

    }

def create_recognition_sketch(

    holes_rows_raw=None,

    slot_info_list=None,

    setup=None,

    vision_snapshot=None,

    sketch_name=None,

):

    if vision_snapshot and isinstance(vision_snapshot, dict) and vision_snapshot.get("ok"):

        return create_recognition_sketch_from_vision(

            vision_snapshot, setup=setup, sketch_name=sketch_name

        )

    return {

        "ok": False,

        "message": "需要視線法快照：請先重新掃描後再繪製",

        "sketch_name": sketch_name or SKETCH_NAME_VISION,

        "source": "vision_required",

    }

