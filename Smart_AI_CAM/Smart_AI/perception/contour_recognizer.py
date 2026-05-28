"""
contour_recognizer.py
Method A: contour edge recognition.
"""

import math

import adsk.core
import adsk.fusion


def _face_max_z_wcs(face: adsk.fusion.BRepFace, z_axis: adsk.core.Vector3D) -> float:
    bb = face.boundingBox
    vals = []
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
        vals.append(x * z_axis.x + y * z_axis.y + z * z_axis.z)
    return max(vals)


def _face_min_z_wcs(face: adsk.fusion.BRepFace, z_axis: adsk.core.Vector3D) -> float:
    bb = face.boundingBox
    vals = []
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
        vals.append(x * z_axis.x + y * z_axis.y + z * z_axis.z)
    return min(vals)


def _point_uv_wcs(
    pt: adsk.core.Point3D,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
) -> tuple:
    dx = pt.x - origin.x
    dy = pt.y - origin.y
    dz = pt.z - origin.z
    u = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
    v = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
    return float(u), float(v)


def _face_uv_bbox(
    face: adsk.fusion.BRepFace,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
) -> tuple:
    bb = face.boundingBox
    us, vs = [], []
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
        u, v = _point_uv_wcs(adsk.core.Point3D.create(x, y, z), origin, x_axis, y_axis)
        us.append(u)
        vs.append(v)
    return min(us), max(us), min(vs), max(vs)


def _is_xy_shadowed_by_higher_face(
    face: adsk.fusion.BRepFace,
    higher_faces: list,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
    uv_margin_cm: float = 0.02,
) -> bool:
    """Skip pocket/slot floors ONLY if they are completely hidden under higher terraces in top view."""
    try:
        z_lo = _face_max_z_wcs(face, z_axis)
        bb = face.boundingBox
        # Get all 4 corners of the low face bounding box
        corners = [
            (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z),
            (bb.minPoint.x, bb.maxPoint.y, bb.maxPoint.z),
            (bb.maxPoint.x, bb.minPoint.y, bb.maxPoint.z),
            (bb.maxPoint.x, bb.maxPoint.y, bb.minPoint.z),
        ]
        for hf in higher_faces:
            if _face_max_z_wcs(hf, z_axis) <= z_lo + 1e-6:
                continue
            u0, u1, v0, v1 = _face_uv_bbox(hf, origin, x_axis, y_axis)
            
            # Low face is shadowed only if ALL 4 corners are inside the higher face UV bounds
            all_inside = True
            for cx, cy, cz in corners:
                cu, cv = _point_uv_wcs(adsk.core.Point3D.create(cx, cy, cz), origin, x_axis, y_axis)
                if not ((u0 - uv_margin_cm) <= cu <= (u1 + uv_margin_cm) and (v0 - uv_margin_cm) <= cv <= (v1 + uv_margin_cm)):
                    all_inside = False
                    break
            if all_inside:
                return True
    except Exception:
        pass
    return False


def get_machining_top_faces_wcs(
    body: adsk.fusion.BRepBody,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
    z_tol_cm: float = 0.05,
    min_area_cm2: float = 1.0,
    terrace_z_gap_cm: float = 3.0,
) -> list:
    """Upward planar faces: global top band + lower terraces (groove/step dual-pad parts)."""
    candidates = []
    for fi in range(body.faces.count):
        face = body.faces.item(fi)
        try:
            geom = face.geometry
            if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                continue
            ev = face.evaluator
            bb = face.boundingBox
            mid = adsk.core.Point3D.create(
                (bb.minPoint.x + bb.maxPoint.x) / 2.0,
                (bb.minPoint.y + bb.maxPoint.y) / 2.0,
                (bb.minPoint.z + bb.maxPoint.z) / 2.0,
            )
            ok, uv = ev.getParameterAtPoint(mid)
            if ok:
                ok2, normal = ev.getNormalAtParameter(uv)
                if not ok2:
                    normal = adsk.core.Plane.cast(geom).normal
            else:
                normal = adsk.core.Plane.cast(geom).normal
            ndot = float(normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z)
            if ndot < 0.9:
                continue
            area = float(face.area)
            if area < min_area_cm2:
                continue
            zmax = _face_max_z_wcs(face, z_axis)
            candidates.append((zmax, area, face))
        except Exception:
            continue
    if not candidates:
        tf = get_top_face(body)
        return [tf] if tf else []
    top_z = max(c[0] for c in candidates)
    gap = max(float(terrace_z_gap_cm), float(z_tol_cm))
    high_band = [c[2] for c in candidates if c[0] >= top_z - z_tol_cm]
    terrace_band = [
        c[2] for c in candidates if (top_z - gap) <= c[0] < (top_z - z_tol_cm)
    ]
    faces = list(high_band)
    for tf in terrace_band:
        if _is_xy_shadowed_by_higher_face(tf, faces, origin, x_axis, y_axis, z_axis):
            continue
        faces.append(tf)
    faces.sort(key=lambda f: float(f.area), reverse=True)
    return faces


def get_top_face(body: adsk.fusion.BRepBody):
    top_face = None
    max_area = 0.0
    for face in body.faces:
        if face.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        ev = face.evaluator
        bb = face.boundingBox
        mid = adsk.core.Point3D.create(
            (bb.minPoint.x + bb.maxPoint.x) / 2.0,
            (bb.minPoint.y + bb.maxPoint.y) / 2.0,
            (bb.minPoint.z + bb.maxPoint.z) / 2.0,
        )
        ok, uv = ev.getParameterAtPoint(mid)
        if not ok:
            continue
        ok2, n = ev.getNormalAtParameter(uv)
        if not ok2:
            continue
        if n.z > 0.9 and face.area > max_area:
            max_area = face.area
            top_face = face
    return top_face


def _loop_edges(lp: adsk.fusion.BRepLoop) -> list:
    out = []
    for ci in range(lp.coEdges.count):
        try:
            out.append(lp.coEdges.item(ci).edge)
        except Exception:
            pass
    return out


def _loop_perimeter_cm(loop_edges: list) -> float:
    total = 0.0
    for e in loop_edges:
        try:
            total += float(e.length)
        except Exception:
            pass
    return total


def _edge_token(edge) -> str:
    try:
        return edge.entityToken or str(id(edge))
    except Exception:
        return str(id(edge))


def get_complete_outer_contour_edges(top_face: adsk.fusion.BRepFace) -> list:
    """Full outer contour on a face: outer loop + planar outer/special edges missing from the loop."""
    loop_edges = get_outer_loop_edges(top_face)
    seen = {_edge_token(e) for e in loop_edges}
    out = list(loop_edges)
    rec = recognize_contour_edges(top_face)
    for e in rec.get("outer", []) + rec.get("special", []):
        key = _edge_token(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _face_shares_edge(face_a: adsk.fusion.BRepFace, face_b: adsk.fusion.BRepFace) -> bool:
    for i in range(face_a.edges.count):
        ea = face_a.edges.item(i)
        for j in range(face_b.edges.count):
            if face_b.edges.item(j) == ea:
                return True
    return False


def _is_vertical_plane_at_top_z(
    face: adsk.fusion.BRepFace,
    z_axis: adsk.core.Vector3D,
    top_z: float,
    z_tol_cm: float = 0.05,
) -> bool:
    try:
        if face.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            return False
        normal = adsk.core.Plane.cast(face.geometry).normal
        ndot = abs(float(normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z))
        if ndot > 0.15:
            return False
        return _face_max_z_wcs(face, z_axis) >= top_z - z_tol_cm
    except Exception:
        return False


def get_groove_wall_faces_wcs(
    body: adsk.fusion.BRepBody,
    top_faces: list,
    z_axis: adsk.core.Vector3D,
    z_tol_cm: float = 0.05,
    min_wall_area_cm2: float = 2.0,
) -> list:
    """Vertical planar faces spanning the terrace band that meet a top-pad boundary."""
    if not top_faces:
        return []
    top_z_max = max(_face_max_z_wcs(tf, z_axis) for tf in top_faces)
    top_z_min = min(_face_max_z_wcs(tf, z_axis) for tf in top_faces)
    boundary_tokens = set()
    for tf in top_faces:
        loop = get_outer_loop_edges(tf)
        rec = recognize_contour_edges(tf)
        loop_tokens = {_edge_token(e) for e in loop}
        for e in loop:
            boundary_tokens.add(_edge_token(e))
        for e in rec.get("outer", []) + rec.get("special", []) + rec.get("skipped", []):
            if _edge_token(e) not in loop_tokens:
                boundary_tokens.add(_edge_token(e))

    walls = []
    seen_faces = set()
    for tf in top_faces:
        try:
            seen_faces.add(tf.entityToken)
        except Exception:
            pass

    for fi in range(body.faces.count):
        face = body.faces.item(fi)
        try:
            if face.entityToken in seen_faces:
                continue
        except Exception:
            pass
        try:
            if face.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                continue
            normal = adsk.core.Plane.cast(face.geometry).normal
            ndot = abs(float(normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z))
            if ndot > 0.15:
                continue
            fz_max = _face_max_z_wcs(face, z_axis)
            fz_min = _face_min_z_wcs(face, z_axis)
            if fz_max < top_z_min - z_tol_cm or fz_min > top_z_max + z_tol_cm:
                continue
        except Exception:
            continue
        if float(face.area) < min_wall_area_cm2:
            continue
        touches = False
        for i in range(face.edges.count):
            if _edge_token(face.edges.item(i)) in boundary_tokens:
                touches = True
                break
        if not touches:
            continue
        for tf in top_faces:
            if _face_shares_edge(face, tf):
                walls.append(face)
                break
    return walls


def get_terrace_step_edges_wcs(
    body: adsk.fusion.BRepBody,
    top_faces: list,
    z_axis: adsk.core.Vector3D,
    z_tol_cm: float = 0.05,
) -> list:
    """Riser edges between terraces at different Z (closes gaps at groove/step dividers)."""
    if len(top_faces) < 2:
        return []
    token_set = set()
    z_by_token = {}
    for tf in top_faces:
        try:
            tok = tf.entityToken
            if not tok:
                continue
            token_set.add(tok)
            z_by_token[tok] = _face_max_z_wcs(tf, z_axis)
        except Exception:
            pass
    if len(token_set) < 2:
        return []
    out = []
    seen = set()
    for ei in range(body.edges.count):
        edge = body.edges.item(ei)
        adj_z = []
        for fi in range(edge.faces.count):
            face = edge.faces.item(fi)
            try:
                tok = face.entityToken
                if tok in z_by_token:
                    adj_z.append(z_by_token[tok])
            except Exception:
                pass
        if len(adj_z) < 2:
            continue
        if max(adj_z) - min(adj_z) <= z_tol_cm:
            continue
        try:
            sp, ep = edge.evaluator.getEndPoints()
            dz = abs(
                (ep.x - sp.x) * z_axis.x
                + (ep.y - sp.y) * z_axis.y
                + (ep.z - sp.z) * z_axis.z
            )
            elen = float(edge.length)
            if elen > 1e-9 and (dz / elen) < 0.35:
                continue
        except Exception:
            pass
        key = _edge_token(edge)
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _terrace_z_gap_for_body(
    body: adsk.fusion.BRepBody,
    z_axis: adsk.core.Vector3D,
    z_tol_cm: float = 0.05,
) -> float:
    """Use full upward-face Z span so lower terraces are never dropped."""
    ups = []
    for fi in range(body.faces.count):
        face = body.faces.item(fi)
        try:
            geom = face.geometry
            if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                continue
            n = adsk.core.Plane.cast(geom).normal
            ndot = float(n.x * z_axis.x + n.y * z_axis.y + n.z * z_axis.z)
            if ndot < 0.9:
                continue
            ups.append(_face_max_z_wcs(face, z_axis))
        except Exception:
            continue
    if len(ups) < 2:
        return 3.0
    return max(3.0, max(ups) - min(ups) + z_tol_cm * 4.0)


def _face_normal_dot_z(face: adsk.fusion.BRepFace, z_axis: adsk.core.Vector3D) -> float:
    try:
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            n = adsk.core.Plane.cast(geom).normal
        else:
            ev = face.evaluator
            bb = face.boundingBox
            mid = adsk.core.Point3D.create(
                0.5 * (bb.minPoint.x + bb.maxPoint.x),
                0.5 * (bb.minPoint.y + bb.maxPoint.y),
                0.5 * (bb.minPoint.z + bb.maxPoint.z),
            )
            ok, uv = ev.getParameterAtPoint(mid)
            if not ok:
                return 0.0
            ok2, n = ev.getNormalAtParameter(uv)
            if not ok2:
                return 0.0
        return float(n.x * z_axis.x + n.y * z_axis.y + n.z * z_axis.z)
    except Exception:
        return 0.0


def collect_machining_outline_edges_wcs(
    body: adsk.fusion.BRepBody,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
    z_tol_cm: float = 0.05,
    min_area_cm2: float = 1.0,
    min_wall_area_cm2: float = 2.0,
) -> list:
    """
    All B-rep edges to project for a top-view verification sketch:
    terrace loops, groove walls, step risers, and +Z silhouette edges.
    """
    gap = _terrace_z_gap_for_body(body, z_axis, z_tol_cm)
    tops = get_machining_top_faces_wcs(
        body,
        origin,
        x_axis,
        y_axis,
        z_axis,
        z_tol_cm=z_tol_cm,
        min_area_cm2=min_area_cm2,
        terrace_z_gap_cm=gap,
    )
    walls = get_groove_wall_faces_wcs(
        body, tops, z_axis, z_tol_cm=z_tol_cm, min_wall_area_cm2=min_wall_area_cm2
    )
    seen = set()
    out = []

    def add(edge) -> None:
        key = _edge_token(edge)
        if key in seen:
            return
        seen.add(key)
        out.append(edge)

    for face in list(tops) + list(walls):
        for edge in get_complete_outer_contour_edges(face):
            add(edge)
        rec = recognize_contour_edges(face)
        for edge in rec.get("outer", []) + rec.get("special", []):
            add(edge)

    for edge in get_terrace_step_edges_wcs(body, tops, z_axis, z_tol_cm):
        add(edge)

    wall_tokens = set()
    for wf in walls:
        try:
            tok = wf.entityToken
            if tok:
                wall_tokens.add(tok)
        except Exception:
            pass
    top_tokens = set()
    for tf in tops:
        try:
            tok = tf.entityToken
            if tok:
                top_tokens.add(tok)
        except Exception:
            pass
    for ei in range(body.edges.count):
        edge = body.edges.item(ei)
        if _edge_token(edge) in seen:
            continue
        has_top = False
        has_wall = False
        for fi in range(edge.faces.count):
            face = edge.faces.item(fi)
            try:
                tok = face.entityToken
                if tok in top_tokens:
                    has_top = True
                if tok in wall_tokens:
                    has_wall = True
            except Exception:
                pass
        if has_top and has_wall:
            add(edge)

    for ei in range(body.edges.count):
        edge = body.edges.item(ei)
        if _edge_token(edge) in seen:
            continue
        ndots = []
        zups = []
        for fi in range(edge.faces.count):
            face = edge.faces.item(fi)
            nd = _face_normal_dot_z(face, z_axis)
            ndots.append(nd)
            if nd > 0.35:
                zups.append(_face_max_z_wcs(face, z_axis))
        if not ndots:
            continue
        has_up = any(d > 0.35 for d in ndots)
        has_down = any(d < -0.35 for d in ndots)
        has_vert = any(abs(d) <= 0.25 for d in ndots)
        if has_up and (has_down or has_vert):
            add(edge)
            continue
        if len(zups) >= 2 and max(zups) - min(zups) > z_tol_cm:
            add(edge)

    # 終極兜底補漏：遍歷 body 的所有 face，如果面朝上且不是極小碎面，就將其 complete outer contour edges 加入
    for fi in range(body.faces.count):
        face = body.faces.item(fi)
        try:
            nd = _face_normal_dot_z(face, z_axis)
            if nd > 0.01:  # 只要稍微面向 WCS 頂部視角 (可見面)
                if float(face.area) < 0.05:  # 排除小於 5 mm² 的碎面防雜訊
                    continue
                for edge in get_complete_outer_contour_edges(face):
                    add(edge)
        except Exception:
            continue

    return out


def get_machining_contour_faces_wcs(
    body: adsk.fusion.BRepBody,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
    z_tol_cm: float = 0.05,
    min_area_cm2: float = 1.0,
    min_wall_area_cm2: float = 2.0,
    terrace_z_gap_cm: float = 3.0,
) -> list:
    """Horizontal top pads + vertical groove walls for a complete outer contour sketch."""
    tops = get_machining_top_faces_wcs(
        body,
        origin,
        x_axis,
        y_axis,
        z_axis,
        z_tol_cm=z_tol_cm,
        min_area_cm2=min_area_cm2,
        terrace_z_gap_cm=terrace_z_gap_cm,
    )
    walls = get_groove_wall_faces_wcs(
        body, tops, z_axis, z_tol_cm=z_tol_cm, min_wall_area_cm2=min_wall_area_cm2
    )
    out = list(tops)
    seen = set()
    for tf in tops:
        try:
            seen.add(tf.entityToken)
        except Exception:
            pass
    for wf in walls:
        try:
            key = wf.entityToken
        except Exception:
            key = str(id(wf))
        if key in seen:
            continue
        seen.add(key)
        out.append(wf)
    return out


def get_outer_loop_edges(top_face: adsk.fusion.BRepFace) -> list:
    """Outer boundary edges: prefer isOuter loop; else largest loop; else classified outer+skipped."""
    edges = []
    seen = set()
    candidate_loops = []

    for li in range(top_face.loops.count):
        lp = top_face.loops.item(li)
        try:
            if bool(lp.isOuter):
                candidate_loops = [lp]
                break
        except Exception:
            candidate_loops.append(lp)

    if not candidate_loops:
        for li in range(top_face.loops.count):
            candidate_loops.append(top_face.loops.item(li))

    if len(candidate_loops) > 1:
        candidate_loops = [
            max(candidate_loops, key=lambda lp: _loop_perimeter_cm(_loop_edges(lp)))
        ]

    for lp in candidate_loops:
        for e in _loop_edges(lp):
            try:
                key = e.entityToken or str(id(e))
            except Exception:
                key = str(id(e))
            if key in seen:
                continue
            seen.add(key)
            edges.append(e)

    if edges:
        return edges

    rec = recognize_contour_edges(top_face)
    for e in rec.get("outer", []) + rec.get("special", []) + rec.get("skipped", []):
        try:
            key = e.entityToken or str(id(e))
        except Exception:
            key = str(id(e))
        if key in seen:
            continue
        seen.add(key)
        edges.append(e)
    return edges


def recognize_contour_edges(top_face: adsk.fusion.BRepFace) -> dict:
    outer, special, skipped = [], [], []
    for edge in top_face.edges:
        adj = [f for f in edge.faces if f != top_face]
        has_cyl = any(f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType for f in adj)
        has_plane = any(f.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType for f in adj)
        if has_cyl:
            skipped.append(edge)
        elif has_plane:
            outer.append(edge)
        else:
            special.append(edge)
    return {
        "outer": outer,
        "special": special,
        "skipped": skipped,
        "outer_count": len(outer),
        "special_count": len(special),
        "skipped_count": len(skipped),
    }


def get_chamfer_bevel_edges_wcs(
    body: adsk.fusion.BRepBody,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
    min_angle_deg: float = 20.0,
    max_angle_deg: float = 70.0,
    min_length_cm: float = 0.05,
) -> list:
    """
    Straight edges beveled between ~20–70 deg from Setup XY (typical part chamfers).
    """
    tops = get_machining_top_faces_wcs(body, origin, x_axis, y_axis, z_axis)
    if not tops:
        return []
    top_z_max = max(_face_max_z_wcs(tf, z_axis) for tf in tops)
    top_z_min = min(_face_max_z_wcs(tf, z_axis) for tf in tops)
    outline_tokens = set()
    for e in collect_machining_outline_edges_wcs(body, origin, x_axis, y_axis, z_axis):
        outline_tokens.add(_edge_token(e))

    out = []
    seen = set()
    min_ang = math.radians(min_angle_deg)
    max_ang = math.radians(max_angle_deg)

    for ei in range(body.edges.count):
        edge = body.edges.item(ei)
        key = _edge_token(edge)
        if key in seen:
            continue
        try:
            if edge.geometry.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
                continue
            elen = float(edge.length)
            if elen < min_length_cm:
                continue
            sp, ep = edge.evaluator.getEndPoints()
            vx = ep.x - sp.x
            vy = ep.y - sp.y
            vz = ep.z - sp.z
            dz = abs(vx * z_axis.x + vy * z_axis.y + vz * z_axis.z)
            horiz = math.sqrt(
                max(0.0, elen * elen - dz * dz)
            )
            if horiz < 1e-9:
                continue
            ang = math.atan2(dz, horiz)
            if ang < min_ang or ang > max_ang:
                continue
            zm = 0.5 * (
                (sp.x - origin.x) * z_axis.x
                + (sp.y - origin.y) * z_axis.y
                + (sp.z - origin.z) * z_axis.z
                + (ep.x - origin.x) * z_axis.x
                + (ep.y - origin.y) * z_axis.y
                + (ep.z - origin.z) * z_axis.z
            )
            if zm < top_z_min - 0.2 or zm > top_z_max + 0.05:
                continue
            touches_outline = False
            for fi in range(edge.faces.count):
                for ej in range(edge.faces.item(fi).edges.count):
                    if _edge_token(edge.faces.item(fi).edges.item(ej)) in outline_tokens:
                        touches_outline = True
                        break
                if touches_outline:
                    break
            if not touches_outline:
                continue
            seen.add(key)
            out.append(edge)
        except Exception:
            continue
    return out

