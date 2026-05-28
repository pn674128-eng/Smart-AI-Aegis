"""
hole_recognizer.py
Stable recognizer module aligned with the previous in-main logic.
"""

import adsk.core
import adsk.fusion
import adsk.cam
import math

try:
    from smart_ai_cam_state.runtime_state import state as runtime_state
except Exception:
    runtime_state = None

# 圓柱孔軸與 Setup WCS Z 之對齊：|axis·z_unit| 須 ≥ 此值才納入 custom-ray 採樣（約 ±23° 內視為平行 Z+／Z-）。
# 舊門檻 0.5（≈60°）過鬆，易把交錯斜孔之側壁當成「軸向孔」進群，射線最後命中非體底而誤判盲孔。
HOLE_RAY_CYL_AXIS_MIN_ABS_DOT = 0.92


def _is_body_visible(body):
    try:
        return bool(body.isVisible)
    except:
        pass
    try:
        return bool(body.isLightBulbOn)
    except:
        pass
    return True


def _bbox_proj_min_max(bb, axis):
    ax, ay, az = axis.x, axis.y, axis.z
    minx, miny, minz = bb.minPoint.x, bb.minPoint.y, bb.minPoint.z
    maxx, maxy, maxz = bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z
    pmax = (maxx if ax >= 0 else minx) * ax + (maxy if ay >= 0 else miny) * ay + (maxz if az >= 0 else minz) * az
    pmin = (minx if ax >= 0 else maxx) * ax + (miny if ay >= 0 else maxy) * ay + (minz if az >= 0 else maxz) * az
    return pmin, pmax


def _loop_has_line_edge(planar_face, target_edge):
    try:
        for lp in planar_face.loops:
            has_target = False
            has_line = False
            for ce in lp.coEdges:
                e = ce.edge
                if e == target_edge:
                    has_target = True
                try:
                    if e.geometry.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
                        has_line = True
                except:
                    pass
            if has_target:
                return has_line
    except:
        pass
    return False


def _is_slot_opening(face):
    for edge in face.edges:
        for af in edge.faces:
            if af == face:
                continue
            try:
                if af.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                    continue
            except:
                continue
            if _loop_has_line_edge(af, edge):
                return True
    return False


def _cylinder_area_ratio_vs_full_wall(face, geom, z_axis):
    """實際圓柱面積 / 以 WCS Z 投影高度估算的完整側壁面積；腰形槽端半圓約 0.45–0.55，通孔整圓側壁通常 >0.85。"""
    try:
        pmin, pmax = _bbox_proj_min_max(face.boundingBox, z_axis)
        h = pmax - pmin
        if h <= 1e-9:
            return 1.0
        full = 2.0 * math.pi * float(geom.radius) * h
        if full <= 1e-9:
            return 1.0
        return float(face.area) / full
    except:
        return 1.0


def _is_likely_pocket_corner_fillet_cylinder(face, geom, z_axis):
    """口袋／槽底四角垂直圓角（如 R1→Ø2 圓柱）：僅圓周一小段，面積比明顯低於通孔整圓側壁。

    與腰形槽端半圓（約 0.45–0.55，已由 _is_likely_racetrack_semicircle_cylinder 處理）區隔：此處用較低
    門檻抓 1/4 圓周等「角 R」；軸須與 Setup Z 近似平行（同射線管線）。
    """
    try:
        ax = geom.axis
        ln = math.sqrt(ax.x * ax.x + ax.y * ax.y + ax.z * ax.z) or 1.0
        ux, uy, uz = ax.x / ln, ax.y / ln, ax.z / ln
        dot = abs(ux * z_axis.x + uy * z_axis.y + uz * z_axis.z)
        if dot < HOLE_RAY_CYL_AXIS_MIN_ABS_DOT:
            return False
    except Exception:
        return False
    ar = _cylinder_area_ratio_vs_full_wall(face, geom, z_axis)
    if ar >= 0.42:
        return False
    return True


def _is_likely_racetrack_semicircle_cylinder(face, geom, z_axis):
    """長條孔兩端半圓柱：面積比偏低且帶直線邊（與沉頭小徑整圓側壁區分）。"""
    ar = _cylinder_area_ratio_vs_full_wall(face, geom, z_axis)
    if ar >= 0.62 or ar <= 0.30:
        return False
    line_cnt = 0
    for edge in face.edges:
        try:
            if edge.geometry.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
                line_cnt += 1
        except:
            pass
    if line_cnt < 1:
        return False
    return True


def _row_is_slot_cap_hole_only(row, z_axis):
    """整列面皆為槽端半圓柱（如 6.5 在腰形端），非沉頭小徑通孔。"""
    faces = list(row.get('faces') or [])
    if not faces:
        return False
    cyl_tuples = []
    for f in faces:
        try:
            if f.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                return False
            cyl = adsk.core.Cylinder.cast(f.geometry)
            if not cyl:
                return False
            cyl_tuples.append((f, cyl))
        except:
            return False
    for f, cyl in cyl_tuples:
        if not _is_likely_racetrack_semicircle_cylinder(f, cyl, z_axis):
            return False
    return True


def _is_counterbore_topology(small_faces, large_faces):
    """沉頭大孔底平面拓樸：大孔圓柱鄰接平面，且該平面再連回小孔圓柱中心簇。"""
    tol = 0.01

    def face_center(face):
        bb = face.boundingBox
        return (
            round(((bb.minPoint.x + bb.maxPoint.x) / 2) / tol) * tol,
            round(((bb.minPoint.y + bb.maxPoint.y) / 2) / tol) * tol,
            round(((bb.minPoint.z + bb.maxPoint.z) / 2) / tol) * tol,
        )

    small_centers = set(face_center(f) for f in small_faces)
    large_centers = set(face_center(f) for f in large_faces)
    for large_face in large_faces:
        for edge in large_face.edges:
            for adj_face in edge.faces:
                if face_center(adj_face) in large_centers:
                    continue
                geom = adj_face.geometry
                if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                    continue
                for e2 in adj_face.edges:
                    for f2 in e2.faces:
                        if face_center(f2) in small_centers:
                            return True
    return False


def _count_holes_faces(faces, origin, x_axis, y_axis, tol=0.05):
    seen = set()
    for f in faces:
        try:
            bb = f.boundingBox
            wx = (bb.minPoint.x + bb.maxPoint.x) / 2
            wy = (bb.minPoint.y + bb.maxPoint.y) / 2
            wz = (bb.minPoint.z + bb.maxPoint.z) / 2
            dx = wx - origin.x
            dy = wy - origin.y
            dz = wz - origin.z
            lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
            ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
            cx = round(round(lx / tol) * tol, 4)
            cy = round(round(ly / tol) * tol, 4)
            seen.add((cx, cy))
        except:
            pass
    return max(len(seen), 1)


def _max_body_depth_mm_from_face(face, body_z_range):
    try:
        tok = face.body.entityToken
        if tok in body_z_range:
            b0, b1 = body_z_range[tok]
            return (b1 - b0) * 10.0
    except:
        pass
    return 0.0


def _face_bbox_center_local_xy_cm(face, origin, x_axis, y_axis):
    """取得圓柱軸心或面中心在 Setup WCS 之 XY 平面分量，完美避免 split-cylinder 的 bbox 偏置 Bug。"""
    try:
        if face.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
            cyl = adsk.core.Cylinder.cast(face.geometry)
            pt = cyl.origin
            dx = pt.x - origin.x
            dy = pt.y - origin.y
            dz = pt.z - origin.z
            lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
            ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
            return lx, ly
    except Exception:
        pass

    bb = face.boundingBox
    wx = (bb.minPoint.x + bb.maxPoint.x) / 2
    wy = (bb.minPoint.y + bb.maxPoint.y) / 2
    wz = (bb.minPoint.z + bb.maxPoint.z) / 2
    dx = wx - origin.x
    dy = wy - origin.y
    dz = wz - origin.z
    lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
    ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
    return lx, ly


def _corner_fillet_xy_extents_by_radius_for_body(body, origin, x_axis, y_axis, z_axis, pos_tol_mm, radius_tol_mm):
    """同 body 上槽角 R 圓柱（_is_likely_pocket_corner_fillet_cylinder）依半徑分桶後之 XY 範圍；至少 3 點才納入。"""
    def snap_r(r_cm):
        return round(round(r_cm / radius_tol_mm) * radius_tol_mm, 6)

    def snap_xy_coord(v_cm):
        return round(round(v_cm / pos_tol_mm) * pos_tol_mm, 4)

    buckets = {}
    for fi in range(body.faces.count):
        face = body.faces.item(fi)
        try:
            if face.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                continue
        except Exception:
            continue
        cyl = adsk.core.Cylinder.cast(face.geometry)
        if not cyl or not _is_likely_pocket_corner_fillet_cylinder(face, cyl, z_axis):
            continue
        rkey = snap_r(cyl.radius)
        lx, ly = _face_bbox_center_local_xy_cm(face, origin, x_axis, y_axis)
        buckets.setdefault(rkey, []).append((snap_xy_coord(lx), snap_xy_coord(ly)))
    out = {}
    for rkey, pts in buckets.items():
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out[rkey] = (min(xs), max(xs), min(ys), max(ys))
    return out


def _suppress_orphan_micro_full_cylinder_outside_corner_cluster(
    face,
    geom,
    cluster_xy_by_r,
    origin,
    x_axis,
    y_axis,
    z_axis,
    pos_tol_mm,
    radius_tol_mm,
):
    """同 body 已有多個同 R 槽角 R 時，略過遠離該角 R XY 叢集之「整圓側壁＋小徑」圓柱（Fusion 常見單面偽口袋圓柱）。"""
    try:
        dia_mm = round(geom.radius * 20.0, 3)
        if dia_mm > 3.0:
            return False
        ar = _cylinder_area_ratio_vs_full_wall(face, geom, z_axis)
        if ar < 0.85:
            return False

        def snap_r(r_cm):
            return round(round(r_cm / radius_tol_mm) * radius_tol_mm, 6)

        def snap_xy_coord(v_cm):
            return round(round(v_cm / pos_tol_mm) * pos_tol_mm, 4)

        rkey = snap_r(geom.radius)
        if rkey not in cluster_xy_by_r:
            return False
        lx, ly = _face_bbox_center_local_xy_cm(face, origin, x_axis, y_axis)
        lx_s = snap_xy_coord(lx)
        ly_s = snap_xy_coord(ly)
        minx, maxx, miny, maxy = cluster_xy_by_r[rkey]
        margin_cm = max(pos_tol_mm * 3.0, 0.1)
        if (lx_s < minx - margin_cm) or (lx_s > maxx + margin_cm) or (ly_s < miny - margin_cm) or (ly_s > maxy + margin_cm):
            return True
    except Exception:
        return False
    return False


def _collect_pocket_seed_rows(
    design,
    setup,
    visible_only,
    origin,
    x_axis,
    y_axis,
    z_axis,
    pos_tol_mm,
    body_z_range,
):
    """RecognizedPocket 全量種子列（與圓柱射線合併前）。攻擊方向取 Setup WCS -Z。

    跳過僅單一面之口袋（Fusion 常將單張圓柱誤列為口袋，不應當種子列）。
    """
    rows = []
    if not design or not setup:
        return rows
    attack = adsk.core.Vector3D.create(-z_axis.x, -z_axis.y, -z_axis.z)
    bodies_to_scan = []
    scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
    if scan_bodies is not None:
        for entry in scan_bodies:
            if visible_only and (not entry["visible"]):
                continue
            bodies_to_scan.append(entry["body"])
    else:
        for comp in design.allComponents:
            for bi in range(comp.bRepBodies.count):
                body = comp.bRepBodies.item(bi)
                if visible_only and (not _is_body_visible(body)):
                    continue
                bodies_to_scan.append(body)

    for body in bodies_to_scan:
        try:
            recognized = adsk.cam.RecognizedPocket.recognizePockets(body, attack)
        except:
            continue
        for pocket in recognized:
            try:
                faces_all = list(pocket.faces)
            except:
                continue
            if len(faces_all) == 1:
                continue
                cyl_faces = []
                for f in faces_all:
                    try:
                        if f.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                            continue
                    except:
                        continue
                    try:
                        cyl0 = adsk.core.Cylinder.cast(f.geometry)
                        if cyl0 and _is_likely_pocket_corner_fillet_cylinder(f, cyl0, z_axis):
                            continue
                    except Exception:
                        pass
                    cyl_faces.append(f)
                if not cyl_faces:
                    continue
                diameter_mm = None
                for f in cyl_faces:
                    cyl = adsk.core.Cylinder.cast(f.geometry)
                    if cyl:
                        diameter_mm = round(cyl.radius * 20.0, 3)
                        break
                if diameter_mm is None:
                    continue
                is_through = bool(pocket.isThrough)
                if is_through:
                    depth_mm = round(_max_body_depth_mm_from_face(cyl_faces[0], body_z_range), 3)
                else:
                    try:
                        depth_mm = round(float(pocket.depth) * 10.0, 3)
                    except:
                        depth_mm = round(_max_body_depth_mm_from_face(cyl_faces[0], body_z_range), 3)
                cnt = _count_holes_faces(cyl_faces, origin, x_axis, y_axis, pos_tol_mm)
                rows.append({
                    'diameter_mm': diameter_mm,
                    'through': is_through,
                    'depth_mm': depth_mm,
                    'face_count': len(cyl_faces),
                    'count': cnt,
                    'faces': cyl_faces,
                    'dir': 'Z+',
                    'ray_radius_mm': round(max((diameter_mm / 20.0) - 0.01, 0.001) * 10.0, 4),
                    'is_countersink_large': False,
                    'is_countersink_small': False,
                    'source': 'recognized-pocket',
                    'accessibilityHint': 'Z+',
                    'needsReview': False,
                })
    return rows


def collect_pocket_corner_r_rows(
    design,
    setup,
    visible_only=True,
    pos_tol_mm=0.05,
    radius_tol_mm=0.005,
):
    """辨識口袋／槽底四角垂直圓角 R（與 `scan_holes_by_ray` 排除之角 R 同一幾何規則）。

    與孔表分離：**kind** = ``pocket_corner_r``；**r_mm** 為圓角半徑；**cylinder_diameter_mm** 為該圓柱補丁之等效 Ø。
    回傳列含 **faces**（BRepFace），請勿直接 JSON 序列化。
    """
    if not design or not setup:
        return []
    wcs = setup.workCoordinateSystem
    origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()

    def snap_r(r_cm):
        return round(round(r_cm / radius_tol_mm) * radius_tol_mm, 6)

    def snap_xy_coord(v_cm):
        return round(round(v_cm / pos_tol_mm) * pos_tol_mm, 4)

    def dot_z(ax):
        return ax.x * z_axis.x + ax.y * z_axis.y + ax.z * z_axis.z

    groups = {}
    bodies_to_scan = []
    scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
    if scan_bodies is not None:
        for entry in scan_bodies:
            if visible_only and (not entry["visible"]):
                continue
            bodies_to_scan.append(entry["body"])
    else:
        for comp in design.allComponents:
            for bi in range(comp.bRepBodies.count):
                body = comp.bRepBodies.item(bi)
                if visible_only and (not _is_body_visible(body)):
                    continue
                bodies_to_scan.append(body)

    for body in bodies_to_scan:
        for face in body.faces:
                try:
                    geom = face.geometry
                    if geom.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                        continue
                except Exception:
                    continue
                cyl = adsk.core.Cylinder.cast(geom)
                if not cyl or not _is_likely_pocket_corner_fillet_cylinder(face, cyl, z_axis):
                    continue
                bb = face.boundingBox
                wx = (bb.minPoint.x + bb.maxPoint.x) / 2
                wy = (bb.minPoint.y + bb.maxPoint.y) / 2
                wz = (bb.minPoint.z + bb.maxPoint.z) / 2
                dx = wx - origin.x
                dy = wy - origin.y
                dz = wz - origin.z
                lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
                ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
                key = (snap_xy_coord(lx), snap_xy_coord(ly), snap_r(cyl.radius))
                groups.setdefault(key, []).append(face)

    rows = []
    for _key, faces in groups.items():
        faces = list(faces)
        if not faces:
            continue
        f0 = faces[0]
        cyl0 = adsk.core.Cylinder.cast(f0.geometry)
        if not cyl0:
            continue
        r_mm = round(cyl0.radius * 10.0, 3)
        cylinder_diameter_mm = round(cyl0.radius * 20.0, 3)
        ar = _cylinder_area_ratio_vs_full_wall(f0, cyl0, z_axis)
        try:
            axv = cyl0.axis
            dir_s = 'Z+' if dot_z(axv) >= 0 else 'Z-'
        except Exception:
            dir_s = 'Z+'
        bb = f0.boundingBox
        wx = (bb.minPoint.x + bb.maxPoint.x) / 2
        wy = (bb.minPoint.y + bb.maxPoint.y) / 2
        wz = (bb.minPoint.z + bb.maxPoint.z) / 2
        dx = wx - origin.x
        dy = wy - origin.y
        dz = wz - origin.z
        lx_cm = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
        ly_cm = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
        lz_cm = dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
        lx_mm = round(lx_cm * 10.0, 3)
        ly_mm = round(ly_cm * 10.0, 3)
        lz_mm = round(lz_cm * 10.0, 3)
        cx_mm = round(wx * 10.0, 3)
        cy_mm = round(wy * 10.0, 3)
        cz_mm = round(wz * 10.0, 3)
        cnt = _count_holes_faces(faces, origin, x_axis, y_axis, pos_tol_mm)
        rows.append({
            'kind': 'pocket_corner_r',
            'source': 'pocket-corner-r',
            'r_mm': r_mm,
            'cylinder_diameter_mm': cylinder_diameter_mm,
            'cylinder_area_ratio': round(ar, 4),
            'lx_mm': lx_mm,
            'ly_mm': ly_mm,
            'lz_mm': lz_mm,
            'cx_wcs_mm': cx_mm,
            'cy_wcs_mm': cy_mm,
            'cz_wcs_mm': cz_mm,
            'dir': dir_s,
            'count': cnt,
            'face_count': len(faces),
            'faces': faces,
        })
    rows.sort(key=lambda x: (x['r_mm'], x['lx_mm'], x['ly_mm']))
    return rows


def _merge_key_row(row, origin, x_axis, y_axis, pos_tol_mm):
    faces = row.get('faces') or []
    if not faces:
        return None
    try:
        dia = round(float(row.get('diameter_mm', 0.0)), 3)
        bb = faces[0].boundingBox
        wx = (bb.minPoint.x + bb.maxPoint.x) / 2
        wy = (bb.minPoint.y + bb.maxPoint.y) / 2
        wz = (bb.minPoint.z + bb.maxPoint.z) / 2
        dx = wx - origin.x
        dy = wy - origin.y
        dz = wz - origin.z
        lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
        ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z

        def snap_xy(v):
            return round(round(v / pos_tol_mm) * pos_tol_mm, 4)

        return (snap_xy(lx), snap_xy(ly), dia)
    except:
        return None


def _merge_pocket_and_custom(pocket_rows, custom_rows, origin, x_axis, y_axis, pos_tol_mm, trace_through=False):
    """同鍵時以 custom-ray 為準（幾何較完整），否則保留 pocket 補漏。"""
    m = {}
    for r in pocket_rows:
        k = _merge_key_row(r, origin, x_axis, y_axis, pos_tol_mm)
        if k:
            m[k] = r
    for r in custom_rows:
        k = _merge_key_row(r, origin, x_axis, y_axis, pos_tol_mm)
        if k:
            if trace_through and k in m:
                old = m[k]
                r.setdefault('throughTrace', []).extend(list(old.get('throughTrace') or []))
                r.setdefault('throughTrace', []).append(
                    "[merge] 同鍵以 custom-ray 覆蓋 pocket（pocket through=%r source=%s）"
                    % (old.get('through'), old.get('source'))
                )
            m[k] = r
    return list(m.values())


def _pos_key_row(row, origin, x_axis, y_axis, pos_tol_mm):
    faces = row.get('faces') or []
    if not faces:
        return None
    try:
        bb = faces[0].boundingBox
        wx = (bb.minPoint.x + bb.maxPoint.x) / 2
        wy = (bb.minPoint.y + bb.maxPoint.y) / 2
        wz = (bb.minPoint.z + bb.maxPoint.z) / 2
        dx = wx - origin.x
        dy = wy - origin.y
        dz = wz - origin.z
        lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
        ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
        return (
            round(round(lx / pos_tol_mm) * pos_tol_mm, 4),
            round(round(ly / pos_tol_mm) * pos_tol_mm, 4),
        )
    except:
        return None


def _surface_type_label(face):
    """供 through 追蹤：第一命中面類型（簡稱）。"""
    try:
        t = face.geometry.surfaceType
        if t == adsk.core.SurfaceTypes.PlaneSurfaceType:
            return "Plane"
        if t == adsk.core.SurfaceTypes.CylinderSurfaceType:
            return "Cylinder"
        if t == adsk.core.SurfaceTypes.ConeSurfaceType:
            return "Cone"
        if t == adsk.core.SurfaceTypes.SphereSurfaceType:
            return "Sphere"
        return "SurfaceType(%s)" % int(t)
    except Exception:
        return "?"


def _z_proj_on_axis(pt, z_axis):
    return pt.x * z_axis.x + pt.y * z_axis.y + pt.z * z_axis.z


def _ray_pierces_body_bottom(hit_pts, z_axis, body_z_range, body_tokens, tol_cm=0.05, entities=None):
    """
    射線沿 -z_axis 行進：最後一個命中點在 z_axis 上之投影若 ≤ 相關 body 之 bmin + tol，
    視為射穿至實體底（通孔）。命中少於 2 則無法視為貫穿（保守 False）。
    回傳 (pierced, last_z, bmin_all) 供 trace；失敗時 last_z／bmin_all 可為 None。
    已新增：利用 entities 進行內部阻擋面檢測，以精準區分通孔與盲孔。
    """
    bmins = []
    try:
        for tok in body_tokens or []:
            if tok in body_z_range:
                bmin, _ = body_z_range[tok]
                bmins.append(bmin)
    except Exception:
        pass
    bmin_all = min(bmins) if bmins else None
    
    if not hit_pts or hit_pts.count == 0:
        return False, None, bmin_all

    try:
        last = hit_pts.item(hit_pts.count - 1)
        last_z = _z_proj_on_axis(last, z_axis)
    except Exception:
        last_z = None

    if bmin_all is None:
        return False, last_z, None

    # 如果有傳入 hit faces (entities)，進行更精確的內部阻擋面檢測
    if entities and entities.count > 0:
        has_blocking_face_inside = False
        for idx in range(entities.count):
            try:
                face = entities.item(idx)
                pt = hit_pts.item(idx)
                proj_pt_z = _z_proj_on_axis(pt, z_axis)
                
                # 檢查是否為與 z_axis 平行的圓柱側壁面（非阻擋面）
                is_parallel_cylinder = False
                if face.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                    cyl_geom = adsk.core.Cylinder.cast(face.geometry)
                    cyl_dot = abs(cyl_geom.axis.x * z_axis.x + cyl_geom.axis.y * z_axis.y + cyl_geom.axis.z * z_axis.z)
                    if cyl_dot >= 0.9:
                        is_parallel_cylinder = True
                        
                if not is_parallel_cylinder:
                    # 阻擋面：檢查是否在體底之上（內部）
                    if proj_pt_z > (bmin_all + tol_cm):
                        has_blocking_face_inside = True
                        break
            except Exception:
                pass
        
        # 若無內部阻擋面，即視為通孔
        if not has_blocking_face_inside:
            return True, last_z, bmin_all
        else:
            return False, last_z, bmin_all

    # 保留舊有的 fallback 邏輯
    if hit_pts.count < 2:
        return False, last_z, bmin_all
    return (last_z <= (bmin_all + tol_cm)), last_z, bmin_all


def _cylinder_axis_anchor_point(group_dict, z_axis, min_axis_dot=0.9):
    """
    由群組內 BRep 圓柱面之 Cylinder 幾何取軸上參考點：平行於 z_axis 之面的 origin 做平均。
    用於與圓邊平均中心對照或模擬射線；拿不到則 None。
    """
    ox, oy, oz = [], [], []
    for f in group_dict.get("faces") or []:
        try:
            if f.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                continue
            cyl = adsk.core.Cylinder.cast(f.geometry)
            if not cyl:
                continue
            ax = cyl.axis
            ln = math.sqrt(ax.x * ax.x + ax.y * ax.y + ax.z * ax.z) or 1.0
            ux, uy, uz = ax.x / ln, ax.y / ln, ax.z / ln
            dot = abs(ux * z_axis.x + uy * z_axis.y + uz * z_axis.z)
            if dot < min_axis_dot:
                continue
            o = cyl.origin
            ox.append(o.x)
            oy.append(o.y)
            oz.append(o.z)
        except Exception:
            pass
    if not ox:
        return None
    k = float(len(ox))
    return adsk.core.Point3D.create(sum(ox) / k, sum(oy) / k, sum(oz) / k)


def _brep_face_key(face):
    """BRepFace 不可當 dict 鍵；用 entityToken（或退回 id）做拓樸索引。"""
    try:
        return face.entityToken
    except Exception:
        return id(face)


def _get_threaded_faces_map(design):
    """
    Scans all ThreadFeatures and HoleFeatures in all components of the design,
    returning a dictionary mapping BRepFace entityTokens (keys) to their threadDesignation.
    """
    face_to_thread = {}
    if not design:
        return face_to_thread
    try:
        for comp in design.allComponents:
            try:
                # ThreadFeatures
                if hasattr(comp, 'features') and hasattr(comp.features, 'threadFeatures'):
                    for feat in comp.features.threadFeatures:
                        try:
                            ti = feat.threadInfo
                            if ti:
                                desig = ti.threadDesignation
                                if desig:
                                    for f in feat.faces:
                                        try:
                                            face_to_thread[_brep_face_key(f)] = desig
                                        except:
                                            pass
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                # HoleFeatures
                if hasattr(comp, 'features') and hasattr(comp.features, 'holeFeatures'):
                    for feat in comp.features.holeFeatures:
                        try:
                            if feat.isThreaded:
                                ti = feat.threadInfo
                                if ti:
                                    desig = ti.threadDesignation
                                    if desig:
                                        for f in feat.sideFaces:
                                            try:
                                                face_to_thread[_brep_face_key(f)] = desig
                                            except:
                                                pass
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass
    return face_to_thread


def _split_cylinder_group_by_face_connectivity(g):
    """
    同 (XY 網格 × 半徑) 鍵可能誤併「交錯孔／極近同徑孔」之多張圓柱面。
    僅當圓柱面之間有共用邊（BRep 拓樸相鄰）才屬同一孔；否則拆成多群各自射線辨識。
    """
    faces = list(g.get("faces") or [])
    n = len(faces)
    if n <= 1:
        return [g]
    face_index = {}
    for i, f in enumerate(faces):
        face_index[_brep_face_key(f)] = i
    adj = [set() for _ in range(n)]
    for f in faces:
        i = face_index[_brep_face_key(f)]
        try:
            ec = f.edges.count
        except Exception:
            ec = 0
        for ei in range(ec):
            try:
                edge = f.edges.item(ei)
                fc = edge.faces.count
            except Exception:
                continue
            for fi in range(fc):
                try:
                    other = edge.faces.item(fi)
                except Exception:
                    continue
                if other is f:
                    continue
                ok = _brep_face_key(other)
                if ok in face_index:
                    adj[i].add(face_index[ok])
    visited = [False] * n
    comps = []
    for start in range(n):
        if visited[start]:
            continue
        stack = [start]
        visited[start] = True
        comp = []
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in adj[u]:
                if not visited[v]:
                    visited[v] = True
                    stack.append(v)
        comps.append(comp)
    if len(comps) <= 1:
        return [g]
    depths = list(g.get("depths") or [])
    z_mins = list(g.get("z_mins") or [])
    z_maxs = list(g.get("z_maxs") or [])
    out = []
    for comp in comps:
        sub_faces = [faces[i] for i in comp]
        new_bodies = set()
        sub_depths, sub_zmin, sub_zmax = [], [], []
        for i in comp:
            try:
                new_bodies.add(faces[i].body.entityToken)
            except Exception:
                pass
            if i < len(depths):
                sub_depths.append(depths[i])
            if i < len(z_mins):
                sub_zmin.append(z_mins[i])
            if i < len(z_maxs):
                sub_zmax.append(z_maxs[i])
        if not new_bodies:
            new_bodies = set(g.get("bodies") or [])
        out.append(
            {
                "radius": g["radius"],
                "faces": sub_faces,
                "depths": sub_depths,
                "z_mins": sub_zmin,
                "z_maxs": sub_zmax,
                "bodies": new_bodies,
            }
        )
    return out


def _through_depth_mm_from_cylinder_z_span(g):
    """
    通孔在 UI／CAM 上可填的「深度」：圓柱孔壁面群沿 Setup z_axis 之投影跨度（mm）。
    整板通孔時接近料厚；交錯／短通孔時為實際通道長（例如 8.4），非 max(body) 料厚。
    """
    zm = list(g.get("z_mins") or [])
    zx = list(g.get("z_maxs") or [])
    if not zm or not zx:
        return None
    try:
        span_cm = max(zx) - min(zm)
        if span_cm <= 1e-12:
            return None
        return round(span_cm * 10.0, 3)
    except Exception:
        return None


def _through_depth_mm_custom_ray(g, body_z_range):
    """custom-ray 通孔 depth_mm：優先圓柱 Z 跨度；不可用時退回所涉實體最大料厚（舊行為）。"""
    geom_mm = _through_depth_mm_from_cylinder_z_span(g)
    if geom_mm is not None and geom_mm >= 0.05:
        return geom_mm
    try:
        depths = [v[1] - v[0] for v in body_z_range.values()]
        if depths:
            return round(max(depths) * 10.0, 3)
    except Exception:
        pass
    if geom_mm is not None:
        return geom_mm
    return 0.0


# 同 XY 雙群時，半徑差（cm）低於此值則不當「沉頭小大徑」配對（避免兩個同徑交錯孔誤走 pair 邏輯）。
# 約 1.8 mm 半徑差 ≈ 孔徑差 3.6 mm；產品沉頭至少 2 mm 徑差，留 snap 容差。
_RAY_PAIR_MIN_RADIUS_DELTA_CM = 0.09


def _apply_countersink_user_rules(rows, origin, x_axis, y_axis, pos_tol_mm, trace_through=False):
    """
    沉頭定義（使用者定案）：
    - 同 XY 雙孔、直徑差 >= 2mm
    - 拓樸上為沉頭配對（大孔經平面連小孔）
    - 小孔：強制通孔，不標沉頭（is_countersink_small=False）
    - 大孔：盲孔、is_countersink_large=True
    """
    groups = {}
    for i, row in enumerate(rows):
        pk = _pos_key_row(row, origin, x_axis, y_axis, pos_tol_mm)
        if pk is None:
            continue
        groups.setdefault(pk, []).append(i)
    for _pk, idxs in groups.items():
        if len(idxs) < 2:
            continue
        idxs_sorted = sorted(idxs, key=lambda ii: float(rows[ii].get('diameter_mm', 0) or 0))
        si = idxs_sorted[0]
        li = idxs_sorted[-1]
        small = rows[si]
        large = rows[li]
        d_small = float(small.get('diameter_mm', 0) or 0)
        d_large = float(large.get('diameter_mm', 0) or 0)
        if d_large - d_small < 2.0 - 1e-6:
            continue
        sf = list(small.get('faces') or [])
        lf = list(large.get('faces') or [])
        if not _is_counterbore_topology(sf, lf):
            continue
        small['through'] = True
        small['is_countersink_small'] = False
        small['is_countersink_large'] = False
        small['dir'] = 'Z+'
        small['cbTopDia'] = d_large
        small['cbDepth'] = float(large.get('depth_mm', 0.0))
        
        large['through'] = False
        large['is_countersink_large'] = True
        large['is_countersink_small'] = False
        large['dir'] = 'Z+'
        large['cbTopDia'] = d_large
        large['cbDepth'] = float(large.get('depth_mm', 0.0))
        if trace_through:
            msg = (
                "[countersink_rule] 同 XY 雙徑且拓樸成沉頭: D小=%s -> through=True；D大=%s -> through=False, is_countersink_large=True, cbTopDia=%s, cbDepth=%s"
                % (d_small, d_large, d_large, large.get('depth_mm', 0.0))
            )
            small.setdefault('throughTrace', []).append(msg)
            large.setdefault('throughTrace', []).append(msg)
    return rows


def recognize_holes_by_pocket(body, attack_vector=None):
    """相容入口：使用 Fusion RecognizedPocket 分類通/盲與非純圓柱 pocket。"""
    if attack_vector is None:
        attack_vector = adsk.core.Vector3D.create(0, 0, -1)
    recognized = adsk.cam.RecognizedPocket.recognizePockets(body, attack_vector)
    through_holes, blind_holes, unclassified = [], [], []
    for pocket in recognized:
        faces = list(pocket.faces)
        all_cyl = all(f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType for f in faces)
        has_plane = any(f.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType for f in faces)
        diameter_mm = None
        for f in faces:
            cyl = adsk.core.Cylinder.cast(f.geometry)
            if cyl:
                diameter_mm = round(cyl.radius * 20.0, 3)
                break
        entry = {
            'pocket': pocket,
            'faces': faces,
            'diameter_mm': diameter_mm,
            'depth_mm': None if pocket.isThrough else round(pocket.depth * 10.0, 3),
            'is_through': pocket.isThrough,
        }
        if all_cyl:
            entry['type'] = 'through_hole' if pocket.isThrough else 'blind_hole'
            (through_holes if pocket.isThrough else blind_holes).append(entry)
        elif has_plane:
            entry['type'] = 'blind_hole'
            blind_holes.append(entry)
        else:
            entry['type'] = 'unclassified'
            unclassified.append(entry)
    return {
        'through_holes': through_holes,
        'blind_holes': blind_holes,
        'unclassified': unclassified,
        'through_count': len(through_holes),
        'blind_count': len(blind_holes),
    }


def scan_holes_by_ray(
    design,
    setup,
    runtime_state=None,
    ray_diameter_delta_mm=None,
    visible_only=True,
    pos_tol_mm=0.05,
    radius_tol_mm=0.005,
    include_countersink_large=True,
    trace_through=False,
):
    """RecognizedPocket 種子列 + 圓柱分群射線辨識合併；並套用沉頭（大盲+小通）使用者定義。

    單群／雙群之通盲（**custom-ray**）：**僅**依 **findBRepUsingRay** 之「無面命中（開路）」或 **射穿至相關實體底**
    （最後命中點在 Setup z_axis 上之投影 ≤ 該群所涉 body 之 bmin+容差，且至少兩個命中點）判定 **through**；
    **不再**用孔深與整料厚比對去改寫 **through**（避免與射線結論打架）。

    **孔軸與 WCS Z**：僅採集圓柱軸與 **Setup WCS Z** 夾角在約 ±23° 內之面（**HOLE_RAY_CYL_AXIS_MIN_ABS_DOT**），
    交錯之斜向孔壁原則不進本射線管線（可改由 RecognizedPocket 種子列補；若兩邊皆無則須另案）。

    **交錯孔／極近同徑孔**：僅以 (XY 網格、半徑) 分群時可能誤併多孔圓柱面；會先依 BRep「面是否共用邊」拆成拓樸連通群再射線。
    同 XY 僅兩群且半徑差過小時，不當沉頭小大徑配對，改為逐群獨立射線（避免兩通孔誤走 pair 邏輯）。
    **通孔 depth_mm**：優先取該群圓柱孔壁沿加工 Z 之投影跨度（短通／交錯時為通道長，如 8.4 mm），非整塊料厚；無法取得時才退回料厚。

    trace_through=True 時，輸出列可含 **throughTrace**：字串時間線，供校驗「何時被標成盲／通」。
    """
    if not design or not setup:
        return []

    wcs = setup.workCoordinateSystem
    origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()
    root_comp = design.rootComponent
    _ = runtime_state

    def snap_r(r_cm):
        return round(round(r_cm / radius_tol_mm) * radius_tol_mm, 6)

    def snap_xy(v_cm):
        return round(round(v_cm / pos_tol_mm) * pos_tol_mm, 4)

    def face_depth(face):
        pmin, pmax = _bbox_proj_min_max(face.boundingBox, z_axis)
        return pmax - pmin

    def dot_wcs_z(ax):
        return ax.x * z_axis.x + ax.y * z_axis.y + ax.z * z_axis.z

    body_z_range = {}
    cyl_faces = []
    
    scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
    if scan_bodies is None:
        scan_bodies = []
        for comp in design.allComponents:
            for bi in range(comp.bRepBodies.count):
                body = comp.bRepBodies.item(bi)
                token = None
                try: token = body.entityToken
                except: pass
                bbox = None
                try: bbox = body.boundingBox
                except: pass
                visible = True
                try: visible = body.isVisible
                except:
                    try: visible = body.isLightBulbOn
                    except: pass
                scan_bodies.append({
                    "body": body,
                    "token": token,
                    "bbox": bbox,
                    "visible": visible,
                    "comp": comp
                })
                
    for entry in scan_bodies:
        body = entry["body"]
        visible = entry["visible"]
        if visible_only and (not visible):
            continue
        token = entry["token"]
        bbox = entry["bbox"]
        if not token or not bbox:
            continue
        body_z_range[token] = _bbox_proj_min_max(bbox, z_axis)
        cluster_xy_by_r = _corner_fillet_xy_extents_by_radius_for_body(
            body, origin, x_axis, y_axis, z_axis, pos_tol_mm, radius_tol_mm
        )

        for face in body.faces:
            geom = face.geometry
            if geom.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                continue

            edge_count = face.edges.count
            linear_edges = []
            for edge in face.edges:
                try:
                    ctype = edge.geometry.curveType
                    if ctype == adsk.core.Curve3DTypes.Line3DCurveType:
                        linear_edges.append(edge)
                except:
                    pass
            # 對齊桌面放寬版：僅當直線邊連到平面時才視為長條孔（避免 4.2 等孔面被「有直線就當槽」誤殺）
            is_slot = False
            if len(linear_edges) > 0:
                for le in linear_edges:
                    for af in le.faces:
                        if af == face:
                            continue
                        try:
                            if af.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                                is_slot = True
                                break
                        except:
                            pass
                    if is_slot:
                        break
            if not is_slot and _is_slot_opening(face):
                is_slot = True
            if is_slot:
                continue
            # 長條孔端部半圓（如 6.5 鑽在槽端）：非沉頭小徑，自一般孔流程排除
            if _is_likely_racetrack_semicircle_cylinder(face, geom, z_axis):
                continue
            # 口袋槽底四角垂直 R（如 R1）：非鑽孔圓柱壁，排除以免與 custom-ray 誤列 Ø2
            if _is_likely_pocket_corner_fillet_cylinder(face, geom, z_axis):
                continue
            # 放寬：不再要求 edge_count==2 / 雙整圓 / area_ratio（易漏 4.2 等）
            if edge_count > 10:
                continue
            if _suppress_orphan_micro_full_cylinder_outside_corner_cluster(
                face,
                geom,
                cluster_xy_by_r,
                origin,
                x_axis,
                y_axis,
                z_axis,
                pos_tol_mm,
                radius_tol_mm,
            ):
                continue

            cyl_faces.append((face, geom, body))

    pocket_seed = _collect_pocket_seed_rows(
        design, setup, visible_only, origin, x_axis, y_axis, z_axis, pos_tol_mm, body_z_range
    )

    if trace_through:
        for _r in pocket_seed:
            _r.setdefault("throughTrace", []).append(
                "[pocket_seed] RecognizedPocket.isThrough -> through=%r depth_mm=%s"
                % (_r.get("through"), _r.get("depth_mm"))
            )

    if not cyl_faces:
        out = _merge_pocket_and_custom(
            pocket_seed, [], origin, x_axis, y_axis, pos_tol_mm, trace_through
        )
        out = [r for r in out if not _row_is_slot_cap_hole_only(r, z_axis)]
        out = _apply_countersink_user_rules(out, origin, x_axis, y_axis, pos_tol_mm, trace_through)
        if trace_through:
            for row in out:
                row.setdefault("throughTrace", []).append(
                    "[merge] 僅 pocket（無圓柱分群射線）: through=%r source=%s"
                    % (row.get("through"), row.get("source"))
                )
        out.sort(key=lambda x: x['diameter_mm'])
        return out

    groups = {}
    for face, geom, body in cyl_faces:
        dot = dot_wcs_z(geom.axis)
        if abs(dot) < HOLE_RAY_CYL_AXIS_MIN_ABS_DOT:
            continue
        bb = face.boundingBox
        # 完美避免 split-cylinder 的 bbox 偏置 Bug，優先使用圓柱幾何軸心 (Cylinder.origin)
        use_cyl_origin = False
        try:
            if geom.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                pt = geom.origin
                dx = pt.x - origin.x
                dy = pt.y - origin.y
                dz = pt.z - origin.z
                local_x = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
                local_y = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
                use_cyl_origin = True
        except Exception:
            use_cyl_origin = False

        if not use_cyl_origin:
            wx = (bb.minPoint.x + bb.maxPoint.x) / 2
            wy = (bb.minPoint.y + bb.maxPoint.y) / 2
            wz = (bb.minPoint.z + bb.maxPoint.z) / 2
            dx = wx - origin.x
            dy = wy - origin.y
            dz = wz - origin.z
            local_x = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
            local_y = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
        z_min, z_max = _bbox_proj_min_max(bb, z_axis)
        key = (snap_xy(local_x), snap_xy(local_y), snap_r(geom.radius))
        if key not in groups:
            groups[key] = {"radius": geom.radius, "faces": [], "depths": [], "z_mins": [], "z_maxs": [], "bodies": set()}
        g = groups[key]
        g["faces"].append(face)
        g["depths"].append(face_depth(face))
        g["z_mins"].append(z_min)
        g["z_maxs"].append(z_max)
        g["bodies"].add(body.entityToken)

    # 交錯孔／近距同徑：僅 XY×R 鍵會誤併多孔圓柱面，依拓樸相鄰拆群後再進 pos_groups。
    split_groups = {}
    for key, g in groups.items():
        subs = _split_cylinder_group_by_face_connectivity(g)
        for si, sg in enumerate(subs):
            if trace_through and len(subs) > 1:
                sg.setdefault("_trace_prepend", []).append(
                    "[split] 同網格鍵圓柱面不相鄰拆成 %d 群，此群 faces=%d"
                    % (len(subs), len(sg.get("faces") or []))
                )
            split_groups[(key[0], key[1], key[2], si)] = sg
    groups = split_groups

    if not groups:
        out = _merge_pocket_and_custom(
            pocket_seed, [], origin, x_axis, y_axis, pos_tol_mm, trace_through
        )
        out = [r for r in out if not _row_is_slot_cap_hole_only(r, z_axis)]
        out = _apply_countersink_user_rules(out, origin, x_axis, y_axis, pos_tol_mm, trace_through)
        if trace_through:
            for row in out:
                row.setdefault("throughTrace", []).append(
                    "[merge] 無圓柱群（groups 空）僅 pocket: through=%r source=%s"
                    % (row.get("through"), row.get("source"))
                )
        out.sort(key=lambda x: x['diameter_mm'])
        return out

    def analyze_with_ray(g, trace_lines=None):
        def tl(msg):
            if trace_lines is not None:
                trace_lines.append(msg)

        for _pre in (g.pop("_trace_prepend", None) or []):
            tl(_pre)

        def planar_circle_center():
            centers = []
            for f in g["faces"]:
                for e in f.edges:
                    try:
                        c = adsk.core.Circle3D.cast(e.geometry)
                        if not c:
                            continue
                        n = c.normal
                        dot = n.x * z_axis.x + n.y * z_axis.y + n.z * z_axis.z
                        if abs(dot) < 0.9:
                            continue
                        centers.append(c.center)
                    except:
                        pass
            if not centers:
                return None
            sx = sum(p.x for p in centers)
            sy = sum(p.y for p in centers)
            sz = sum(p.z for p in centers)
            k = float(len(centers))
            return adsk.core.Point3D.create(sx / k, sy / k, sz / k)

        cpt = planar_circle_center()
        if cpt:
            cx, cy, cz = cpt.x, cpt.y, cpt.z
        else:
            face = g["faces"][0]
            bb = face.boundingBox
            cx = (bb.minPoint.x + bb.maxPoint.x) / 2
            cy = (bb.minPoint.y + bb.maxPoint.y) / 2
            cz = (bb.minPoint.z + bb.maxPoint.z) / 2

        bmaxz = -1e9
        for tok in g["bodies"]:
            if tok in body_z_range:
                _, bz = body_z_range[tok]
                if bz > bmaxz:
                    bmaxz = bz
        if bmaxz < -1e8:
            bmaxz = cz + 10.0

        proj_cz = cx * z_axis.x + cy * z_axis.y + cz * z_axis.z
        shift_dist = bmaxz - proj_cz + 1.0
        start_pt = adsk.core.Point3D.create(cx + z_axis.x * shift_dist, cy + z_axis.y * shift_dist, cz + z_axis.z * shift_dist)
        ray_dir = adsk.core.Vector3D.create(-z_axis.x, -z_axis.y, -z_axis.z)
        if ray_diameter_delta_mm and ray_diameter_delta_mm > 0:
            ray_radius = max(g["radius"] - (float(ray_diameter_delta_mm) / 20.0), 0.001)
        else:
            ray_radius = max(g["radius"] - 0.01, 0.001)

        cyl_anchor = _cylinder_axis_anchor_point(g, z_axis)
        if trace_lines is not None:
            src = "planar_circle_avg" if cpt else "bbox_fallback"
            tl(
                "[axis_sim] 現行射線錨點(%s): (%.6f,%.6f,%.6f) cm"
                % (src, cx, cy, cz)
            )
            if cyl_anchor:
                d_xy_mm = math.hypot(cx - cyl_anchor.x, cy - cyl_anchor.y) * 10.0
                tl(
                    "[axis_sim] 圓柱幾何軸點(origin 平均): (%.6f,%.6f,%.6f) cm；與錨點 XY 距離 %.4f mm"
                    % (cyl_anchor.x, cyl_anchor.y, cyl_anchor.z, d_xy_mm)
                )
                proj_cyl_z = cyl_anchor.x * z_axis.x + cyl_anchor.y * z_axis.y + cyl_anchor.z * z_axis.z
                shift_cyl_dist = bmaxz - proj_cyl_z + 1.0
                start_cyl = adsk.core.Point3D.create(
                    cyl_anchor.x + z_axis.x * shift_cyl_dist,
                    cyl_anchor.y + z_axis.y * shift_cyl_dist,
                    cyl_anchor.z + z_axis.z * shift_cyl_dist,
                )
                hit_cyl = adsk.core.ObjectCollection.create()
                ent_cyl = root_comp.findBRepUsingRay(
                    start_cyl,
                    ray_dir,
                    adsk.fusion.BRepEntityTypes.BRepFaceEntityType,
                    ray_radius,
                    False,
                    hit_cyl,
                )
                surf_c = "?"
                if ent_cyl.count > 0:
                    try:
                        surf_c = _surface_type_label(ent_cyl.item(0))
                    except Exception:
                        pass
                tl(
                    "[axis_sim] 同參數改自圓柱軸點起射: hit_face_count=%d first_surface=%s"
                    % (ent_cyl.count, surf_c)
                )
            else:
                tl("[axis_sim] 無法自圓柱幾何取軸點（無與 z_axis 足夠平行之圓柱面）")

        hit_pts = adsk.core.ObjectCollection.create()
        entities = root_comp.findBRepUsingRay(start_pt, ray_dir, adsk.fusion.BRepEntityTypes.BRepFaceEntityType, ray_radius, False, hit_pts)
        tl(
            "[ray] findBRepUsingRay: hit_face_count=%d ray_radius_cm=%.6f start_offset(+Z)=%.6f on WCS Z"
            % (entities.count, ray_radius, shift_dist)
        )
        if entities.count == 0:
            tl("[ray] 無面命中 -> through_ray=True（開路）, accessible=True")
            return True, True, ray_radius
        surf = "?"
        try:
            surf = _surface_type_label(entities.item(0))
        except Exception:
            pass
        first_hit = hit_pts.item(0)
        hit_z = first_hit.x * z_axis.x + first_hit.y * z_axis.y + first_hit.z * z_axis.z
        hole_top_z = max(g["z_maxs"])
        is_accessible = hit_z <= hole_top_z + 0.05
        pierced, last_z, bmin_all = _ray_pierces_body_bottom(
            hit_pts, z_axis, body_z_range, g["bodies"], 0.05, entities=entities
        )
        through_ray = bool(pierced)
        if trace_lines is not None:
            lz_s = "None" if last_z is None else "%.6f" % last_z
            bm_s = "None" if bmin_all is None else "%.6f" % bmin_all
            tl(
                "[ray] 第一命中面 surface=%s hit_z=%.6f hole_top_z(max z_maxs)=%.6f -> accessible=%s"
                % (surf, hit_z, hole_top_z, is_accessible)
            )
            tl(
                "[ray] 射穿判定: hit_count=%d last_hit_z=%s body_bmin=%s tol_cm=0.05 -> pierced=%s -> through_ray=%s"
                % (hit_pts.count, lz_s, bm_s, pierced, through_ray)
            )
        return is_accessible, through_ray, ray_radius

    pos_groups = {}
    for key, g in groups.items():
        lx, ly, rk = key[0], key[1], key[2]
        pkey = (lx, ly)
        if pkey not in pos_groups:
            pos_groups[pkey] = []
        pos_groups[pkey].append((rk, key, g))

    out = []
    for _, entries in pos_groups.items():
        entries.sort(key=lambda x: x[0])
        # 僅在「兩群半徑差」足夠大時才走沉頭小大徑配對；同徑雙孔（交錯／近距）改走逐群射線。
        if (
            len(entries) == 2
            and (entries[1][0] - entries[0][0]) >= _RAY_PAIR_MIN_RADIUS_DELTA_CM
        ):
            small = entries[0][2]
            large = entries[1][2]
            t_small = [] if trace_through else None
            t_large = [] if trace_through else None
            small_acc, small_through_ray, small_ray_r = analyze_with_ray(small, t_small)
            large_acc, _, large_ray_r = analyze_with_ray(large, t_large)

            c = _count_holes_faces(small['faces'], origin, x_axis, y_axis, pos_tol_mm)
            cb_pair = _is_counterbore_topology(small['faces'], large['faces'])
            tr_small = []
            if trace_through:
                tr_small.extend(t_small or [])
                tr_small.append("[pair] 同 XY 雙半徑: small_r=%.6f large_r=%.6f cb_topology=%s" % (small["radius"], large["radius"], cb_pair))
            if cb_pair:
                depths = [v[1] - v[0] for v in body_z_range.values()]
                small_depth = (max(depths) * 10.0) if depths else ((max(small["z_maxs"]) - min(small["z_mins"])) * 10.0)
                small_through = True
                if trace_through:
                    tr_small.append("[pair] 沉頭拓樸成立 -> small through 強制 True")
            else:
                small_through = small_through_ray
                if trace_through:
                    tr_small.append(
                        "[pair] 非沉頭拓樸: small_through = small_through_ray (%r)" % (small_through_ray,)
                    )
                if not large_acc and not small_through:
                    if trace_through:
                        tr_small.append("[pair] 捨棄此組（large 不可達且 small 非通）")
                    continue
                if small_through:
                    small_depth = _through_depth_mm_custom_ray(small, body_z_range)
                    if trace_through:
                        tr_small.append(
                            "[depth] depth_mm=%.3f（通孔：優先圓柱群沿加工 Z 之投影跨度）" % small_depth
                        )
                else:
                    small_depth = (min(small["depths"]) * 10.0) if small.get("depths") else (
                        (max(small["z_maxs"]) - min(small["z_mins"])) * 10.0
                    )
            row_small = {
                "diameter_mm": round(small["radius"] * 20.0, 3),
                "through": bool(small_through),
                "depth_mm": round(small_depth, 3),
                "face_count": len(small["faces"]),
                "count": c,
                "faces": small["faces"],
                "dir": ("Z+" if (small_acc or small_through) else "Z-"),
                "ray_radius_mm": round(small_ray_r * 10.0, 4),
                "is_countersink_large": False,
                "is_countersink_small": False,
                "source": "custom-ray",
                "accessibilityHint": ("Z+" if (small_acc or small_through) else "Z-"),
                "needsReview": False,
            }
            if trace_through:
                row_small["throughTrace"] = tr_small
            out.append(row_small)
            if large_acc and include_countersink_large and cb_pair:
                large_depth = (max(large["z_maxs"]) - min(large["z_mins"])) * 10.0
                tr_lg = []
                if trace_through:
                    tr_lg.extend(t_large or [])
                    tr_lg.append("[pair/large] 沉頭大徑列: through=False（規則）")
                row_large = {
                    "diameter_mm": round(large["radius"] * 20.0, 3),
                    "through": False,
                    "depth_mm": round(large_depth, 3),
                    "face_count": len(large["faces"]),
                    "count": c,
                    "faces": large["faces"],
                    "dir": "Z+",
                    "ray_radius_mm": round(large_ray_r * 10.0, 4),
                    "is_countersink_large": True,
                    "is_countersink_small": False,
                    "source": "custom-ray",
                    "accessibilityHint": "Z+",
                    "needsReview": False,
                }
                if trace_through:
                    row_large["throughTrace"] = tr_lg
                out.append(row_large)
        else:
            for _, _, g in entries:
                tlog = [] if trace_through else None
                acc, th, ray_r = analyze_with_ray(g, tlog)
                if not acc and not th:
                    if trace_through and tlog is not None:
                        tlog.append("[single] 捨棄（不可達且非通）")
                    continue
                c = _count_holes_faces(g['faces'], origin, x_axis, y_axis, pos_tol_mm)
                if th:
                    depth = _through_depth_mm_custom_ray(g, body_z_range)
                    if trace_through and tlog is not None:
                        tlog.append(
                            "[depth] depth_mm=%.3f（通孔：優先圓柱群沿加工 Z 之投影跨度）" % depth
                        )
                else:
                    depth = (min(g["depths"]) * 10.0) if g.get("depths") else ((max(g["z_maxs"]) - min(g["z_mins"])) * 10.0)
                rd = {
                    "diameter_mm": round(g["radius"] * 20.0, 3),
                    "through": bool(th),
                    "depth_mm": round(depth, 3),
                    "face_count": len(g["faces"]),
                    "count": c,
                    "faces": g["faces"],
                    "dir": ("Z+" if (acc or th) else "Z-"),
                    "ray_radius_mm": round(ray_r * 10.0, 4),
                    "is_countersink_large": False,
                    "is_countersink_small": False,
                    "source": "custom-ray",
                    "accessibilityHint": ("Z+" if (acc or th) else "Z-"),
                    "needsReview": False,
                }
                if trace_through:
                    t2 = list(tlog or [])
                    t2.append(
                        "[single] 列 through=%r 來自射線（True=無命中或射穿至體底）"
                        % (th,)
                    )
                    rd["throughTrace"] = t2
                out.append(rd)

    out = _merge_pocket_and_custom(
        pocket_seed, out, origin, x_axis, y_axis, pos_tol_mm, trace_through
    )
    out = [r for r in out if not _row_is_slot_cap_hole_only(r, z_axis)]
    out = _apply_countersink_user_rules(out, origin, x_axis, y_axis, pos_tol_mm, trace_through)
    if trace_through:
        for row in out:
            row.setdefault("throughTrace", []).append(
                "[merge] pocket+custom 合併後: through=%r source=%s"
                % (row.get("through"), row.get("source"))
            )

    # Enrich with threaded features information
    try:
        threaded_faces_map = _get_threaded_faces_map(design)
        for row in out:
            row_is_threaded = False
            row_thread_desig = ""
            for f in row.get("faces") or []:
                fkey = _brep_face_key(f)
                if fkey in threaded_faces_map:
                    row_is_threaded = True
                    row_thread_desig = threaded_faces_map[fkey]
                    break
            row["is_threaded"] = row_is_threaded
            row["thread_designation"] = row_thread_desig
    except Exception:
        pass

    # ─── 借鑒星空軟體：底孔直徑自動推導螺紋孔語意 (Hole Semantics Inference) ───
    try:
        # 當官方設計螺紋沒有檢測到時，使用底孔直徑進行自適應匹配
        # M3~M16 底孔直徑公差帶判定
        TAP_INFERENCE_TABLE = {
            3.0: {"dia_min": 2.4,  "dia_max": 2.65,  "name": "M3"},
            4.0: {"dia_min": 3.15, "dia_max": 3.45,  "name": "M4"},
            5.0: {"dia_min": 4.05, "dia_max": 4.35,  "name": "M5"},
            6.0: {"dia_min": 4.85, "dia_max": 5.15,  "name": "M6"},
            8.0: {"dia_min": 6.65, "dia_max": 6.95,  "name": "M8"},
            10.0:{"dia_min": 8.35, "dia_max": 8.65,  "name": "M10"},
            12.0:{"dia_min": 10.1, "dia_max": 10.45, "name": "M12"},
            16.0:{"dia_min": 13.8, "dia_max": 14.15, "name": "M16"},
        }
        for row in out:
            # 優先尊重官方 timeline 螺紋標記，只有在 is_threaded 為 False 時才進行推導
            if not row.get("is_threaded"):
                d = float(row.get("diameter_mm", 0.0) or 0.0)
                for tap_dia, rules in TAP_INFERENCE_TABLE.items():
                    if rules["dia_min"] <= d <= rules["dia_max"]:
                        row["is_threaded"] = True
                        row["thread_designation"] = f"{rules['name']} (幾何自適應反推)"
                        row["semantic_type"] = "thread_bottom_hole"
                        break
                        
            # 定位銷孔 (Pin Hole) 語意反推 (直徑帶微量正公差，例如 5.00~5.06 / 8.00~8.06 / 10.00~10.06)
            if not row.get("semantic_type"):
                d = float(row.get("diameter_mm", 0.0) or 0.0)
                for pin_dia in [3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0]:
                    if pin_dia <= d <= pin_dia + 0.06:
                        row["semantic_type"] = "pin_position_hole"
                        break
    except Exception:
        pass

    out.sort(key=lambda x: x["diameter_mm"])

    return out
