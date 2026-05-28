# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion, adsk.cam
import math
from smart_ai_cam_state.runtime_state import state as runtime_state
from smart_ai_cam_ui.diagnostics import send_diag_log

# Slot pocket compensation configurations
SLOT_POCKET_COMPENSATION_2D_CROSS_INVERT = False
SLOT_POCKET_COMPENSATION_2D_ARC_CROSS = True
SLOT_POCKET_COMPENSATION_HOST_FACE_VS_Z = True
SLOT_POCKET_USE_SCAN_CENTER_FOR_COMP = True


def _bbox_proj_min_max(bb, axis):
    ax = axis.x
    ay = axis.y
    az = axis.z
    minx = bb.minPoint.x
    miny = bb.minPoint.y
    minz = bb.minPoint.z
    maxx = bb.maxPoint.x
    maxy = bb.maxPoint.y
    maxz = bb.maxPoint.z
    pmax = (maxx if ax >= 0 else minx) * ax + \
           (maxy if ay >= 0 else miny) * ay + \
           (maxz if az >= 0 else minz) * az
    pmin = (minx if ax >= 0 else maxx) * ax + \
           (miny if ay >= 0 else maxy) * ay + \
           (minz if az >= 0 else maxz) * az
    return pmin, pmax


def _coalesce_slot_chains_edge_lists(edge_lists, token_lists):
    """
    長條孔：每槽一組邊鏈。若 live BRepEdge 已失效（Fusion 常見），改以同列之
    loop_edge_tokens 經 findEntityByToken 還原後再綁 ChainSelection。
    """
    out = []
    elists = edge_lists or []
    tlists = token_lists or []
    n = max(len(elists), len(tlists))
    for i in range(n):
        lst = elists[i] if i < len(elists) else None
        toks = tlists[i] if i < len(tlists) else None
        sub = []
        for e in (lst or []):
            try:
                if e and getattr(e, 'isValid', True):
                    sub.append(e)
            except Exception:
                pass
        if len(sub) >= 2:
            out.append(sub)
            continue
        sub2 = _resolve_slot_loop_edges_from_tokens(runtime_state.des_obj, toks or [])
        if len(sub2) >= 2:
            out.append(sub2)
            try:
                send_diag_log(
                    '[slot-bind] 槽邊鏈第 %d 組以 entityToken 還原（live edge 不足或無效）' % (i + 1)
                )
            except Exception:
                pass
    return out



def _dist3_sq_pt(a, b):
    try:
        dx = a.x - b.x
        dy = a.y - b.y
        dz = a.z - b.z
        return dx * dx + dy * dy + dz * dz
    except Exception:
        return 1e30


def _ordered_points_from_edge_chain(edges):
    """封閉鏈邊序還原為頂點序列（Fusion 內部長度單位），供有號面積用。"""
    pts = []
    if not edges or len(edges) < 2:
        return pts
    tol_sq = 1e-10
    for e in edges:
        try:
            if not e or not getattr(e, 'isValid', True):
                return []
            sv = e.startVertex
            ev = e.endVertex
            if not sv or not ev:
                return []
            s = sv.geometry
            t = ev.geometry
        except Exception:
            return []
        if not pts:
            pts.append(s)
            pts.append(t)
        else:
            last = pts[-1]
            if _dist3_sq_pt(last, s) <= _dist3_sq_pt(last, t):
                pts.append(t)
            else:
                pts.append(s)
    if len(pts) > 2 and _dist3_sq_pt(pts[0], pts[-1]) < tol_sq:
        pts.pop()
    return pts


def _shoelace_signed_area_uv(points_3d, origin, x_axis, y_axis):
    if len(points_3d) < 3:
        return 0.0
    uvs = []
    try:
        ox, oy, oz = origin.x, origin.y, origin.z
        xx, xy, xz = x_axis.x, x_axis.y, x_axis.z
        yx, yy, yz = y_axis.x, y_axis.y, y_axis.z
    except Exception:
        return 0.0
    for p in points_3d:
        try:
            du = p.x - ox
            dv = p.y - oy
            dw = p.z - oz
            u = du * xx + dv * xy + dw * xz
            v = du * yx + dv * yy + dw * yz
            uvs.append((u, v))
        except Exception:
            return 0.0
    n = len(uvs)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += uvs[i][0] * uvs[j][1] - uvs[j][0] * uvs[i][1]
    return 0.5 * a


def _slot_chain_signed_area_setup_xy(edges, setup):
    if not edges or not setup:
        return 0.0
    try:
        o, xa, ya, za = setup.workCoordinateSystem.getAsCoordinateSystem()
    except Exception:
        return 0.0
    pts = _ordered_points_from_edge_chain(edges)
    if len(pts) < 3:
        return 0.0
    return _shoelace_signed_area_uv(pts, o, xa, ya)


def _slot_center_point_from_scan_mm(cx_mm, cy_mm, setup, z_along_setup_z_cm=None):
    """
    辨識器輸出之 cx_mm／cy_mm 為沿 Setup WCS 之 X、Y 軸之 mm 數值（內部長度 cm＝mm/10）；
    還原為模型空間點，供與邊鏈同一 UV 基底做點在多邊形內判斷。
    """
    try:
        o, xa, ya, za = setup.workCoordinateSystem.getAsCoordinateSystem()
        s = float(cx_mm) / 10.0
        t = float(cy_mm) / 10.0
        px = o.x + xa.x * s + ya.x * t
        py = o.y + xa.y * s + ya.y * t
        pz = o.z + xa.z * s + ya.z * t
        if z_along_setup_z_cm is not None:
            k = float(z_along_setup_z_cm)
            px += za.x * k
            py += za.y * k
            pz += za.z * k
        return adsk.core.Point3D.create(px, py, pz)
    except Exception:
        return adsk.core.Point3D.create(
            float(cx_mm) / 10.0, float(cy_mm) / 10.0, 0.0
        )


def _project_point_to_uv_axes(pt, origin, u_axis, v_axis):
    try:
        ox, oy, oz = origin.x, origin.y, origin.z
        ux, uy, uz = u_axis.x, u_axis.y, u_axis.z
        vx, vy, vz = v_axis.x, v_axis.y, v_axis.z
        du = pt.x - ox
        dv = pt.y - oy
        dw = pt.z - oz
        return (
            du * ux + dv * uy + dw * uz,
            du * vx + dv * vy + dw * vz,
        )
    except Exception:
        return (0.0, 0.0)


def _slot_chain_loop_uvs_axes(edges, origin, u_axis, v_axis):
    pts = _ordered_points_from_edge_chain(edges)
    out = []
    for p in pts:
        out.append(_project_point_to_uv_axes(p, origin, u_axis, v_axis))
    return out


def _point_in_polygon_2d(uvs, pu, pv):
    """非零繞數等價之射線法；uvs 封閉頂點列（不必重複首尾）。"""
    n = len(uvs)
    if n < 3:
        return False
    ins = False
    for i in range(n):
        x1, y1 = uvs[i]
        x2, y2 = uvs[(i + 1) % n]
        c1 = y1 > pv
        c2 = y2 > pv
        if c1 == c2:
            continue
        x_int = x1 + (x2 - x1) * (pv - y1) / ((y2 - y1) if abs(y2 - y1) > 1e-18 else 1e-18)
        if pu < x_int:
            ins = not ins
    return ins


def _slot_pocket_align_chain_winding_flags(chains, setup):
    """
    多條槽邊鏈時，回傳與 chains 等長之 bool 列：第 i 條是否需 **額外反轉邊序**
    （與 slot_chain_reverse_order XOR），使各鏈在 Setup XY 之有號面積與第 0 條同號。
    len(chains)<2 或無法計算時回傳 None。
    """
    if not chains or len(chains) < 2 or not setup:
        return None
    signs = []
    for el in chains:
        try:
            signs.append(float(_slot_chain_signed_area_setup_xy(el, setup)))
        except Exception:
            signs.append(0.0)
    ref = signs[0]
    if abs(ref) < 1e-20:
        return None
    out = []
    for s in signs:
        if abs(s) < 1e-20:
            out.append(False)
        else:
            out.append((s * ref) < 0.0)
    return out


def _slot_face_bucket_key(face: adsk.fusion.BRepFace, idx: int):
    """同物理開口面分桶；無面時每鏈獨立避免誤合併。"""
    if not face or not getattr(face, 'isValid', True):
        return ('iso', int(idx))
    try:
        tid = getattr(face, 'tempId', None)
        if tid is not None:
            return ('t', int(tid))
    except Exception:
        pass
    try:
        bb = face.boundingBox
        a = round(float(face.area), 4)
        return (
            'g',
            a,
            round(bb.minPoint.x, 3),
            round(bb.minPoint.y, 3),
            round(bb.minPoint.z, 3),
        )
    except Exception:
        return ('id', id(face))


def _plane_uv_basis_from_face(face: adsk.fusion.BRepFace):
    """回傳 (origin, u_axis, v_axis)，使 u×v 與面法向同向，供有號面積用。"""
    if not face or not getattr(face, 'isValid', True):
        return None
    try:
        geom = face.geometry
        if int(geom.surfaceType) != int(adsk.core.SurfaceTypes.PlaneSurfaceType):
            return None
        pl = adsk.core.Plane.cast(geom)
        if not pl:
            return None
        n = pl.normal
        o = pl.origin
        ref = adsk.core.Vector3D.create(1, 0, 0)
        if abs(n.dotProduct(ref)) > 0.9:
            ref = adsk.core.Vector3D.create(0, 1, 0)
        u = n.crossProduct(ref)
        if u.length < 1e-12:
            return None
        u.normalize()
        v = n.crossProduct(u)
        v.normalize()
        return (o, u, v)
    except Exception:
        return None


def _slot_chain_signed_area_plane_basis(edges, o, u_axis, v_axis):
    """邊鏈頂點投影到已知 (o,u,v) 平面座標後之有號面積（與 Setup XY 無關）。"""
    pts = _ordered_points_from_edge_chain(edges)
    if len(pts) < 3:
        return 0.0
    try:
        ox, oy, oz = o.x, o.y, o.z
        ux, uy, uz = u_axis.x, u_axis.y, u_axis.z
        vx, vy, vz = v_axis.x, v_axis.y, v_axis.z
    except Exception:
        return 0.0
    uvs = []
    for p in pts:
        du = p.x - ox
        dv = p.y - oy
        dw = p.z - oz
        uvs.append(
            (
                du * ux + dv * uy + dw * uz,
                du * vx + dv * vy + dw * vz,
            )
        )
    n = len(uvs)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += uvs[i][0] * uvs[j][1] - uvs[j][0] * uvs[i][1]
    return 0.5 * a


def _slot_pocket_align_chain_winding_with_opening_faces(chains, setup, opening_faces):
    """
    多腰孔落在多張開口平面時：先依開口面分桶，桶內以該面 UV 對齊繞向；桶間以首桶平面為共用基底比較各桶首鏈，
    符號相反則整桶 XOR 反轉。無法取得面或長度不符時退回僅 Setup XY 之 _slot_pocket_align_chain_winding_flags。
    """
    n = len(chains) if chains else 0
    if n < 2 or not setup:
        return None
    if not opening_faces or len(opening_faces) != n:
        return _slot_pocket_align_chain_winding_flags(chains, setup)
    xor_full = [False] * n
    bucket_keys = []
    key_to_indices = {}
    for i in range(n):
        k = _slot_face_bucket_key(opening_faces[i], i)
        if k not in key_to_indices:
            bucket_keys.append(k)
            key_to_indices[k] = []
        key_to_indices[k].append(i)
    for k in bucket_keys:
        inds = key_to_indices[k]
        if len(inds) < 2:
            continue
        ref_i = inds[0]
        ref_face = opening_faces[ref_i]
        b = _plane_uv_basis_from_face(ref_face)
        if not b:
            ref_s = float(_slot_chain_signed_area_setup_xy(chains[ref_i], setup))
            if abs(ref_s) < 1e-20:
                continue
            for idx in inds[1:]:
                s = float(_slot_chain_signed_area_setup_xy(chains[idx], setup))
                if abs(s) < 1e-20:
                    continue
                xor_full[idx] = (s * ref_s) < 0.0
            continue
        o, ua, va = b
        ref_s = float(_slot_chain_signed_area_plane_basis(chains[ref_i], o, ua, va))
        if abs(ref_s) < 1e-20:
            ref_s = float(_slot_chain_signed_area_setup_xy(chains[ref_i], setup))
        if abs(ref_s) < 1e-20:
            continue
        for idx in inds[1:]:
            s = float(_slot_chain_signed_area_plane_basis(chains[idx], o, ua, va))
            if abs(s) < 1e-20:
                s = float(_slot_chain_signed_area_setup_xy(chains[idx], setup))
            if abs(s) < 1e-20:
                continue
            xor_full[idx] = (s * ref_s) < 0.0
    if len(bucket_keys) < 2:
        return xor_full
    b0_i = key_to_indices[bucket_keys[0]][0]
    b0_face = opening_faces[b0_i]
    basis0 = _plane_uv_basis_from_face(b0_face)
    if not basis0:
        return xor_full
    o0, u0, v0 = basis0
    s0 = float(_slot_chain_signed_area_plane_basis(chains[b0_i], o0, u0, v0))
    if abs(s0) < 1e-20:
        s0 = float(_slot_chain_signed_area_setup_xy(chains[b0_i], setup))
    if abs(s0) < 1e-20:
        return xor_full
    for k in bucket_keys[1:]:
        inds = key_to_indices[k]
        j = inds[0]
        sj = float(_slot_chain_signed_area_plane_basis(chains[j], o0, u0, v0))
        if abs(sj) < 1e-20:
            sj = float(_slot_chain_signed_area_setup_xy(chains[j], setup))
        if abs(sj) < 1e-20:
            continue
        if (s0 * sj) < 0.0:
            for idx in inds:
                xor_full[idx] = not xor_full[idx]
    return xor_full


def _slot_pt_to_setup_xy(pt, origin, x_ax, y_ax):
    """模型空間點投影到 Setup WCS 之 XY 平面座標（沿 X、Y 軸分量，原點為 setup 原點）。"""
    try:
        du = pt.x - origin.x
        dv = pt.y - origin.y
        dw = pt.z - origin.z
        return (
            du * x_ax.x + dv * x_ax.y + dw * x_ax.z,
            du * y_ax.x + dv * y_ax.y + dw * y_ax.z,
        )
    except Exception:
        return (0.0, 0.0)


def _slot_two_arc_midpoint_xy(chain_edges, origin, x_ax, y_ax):
    """腰形槽兩半圓弧圓心在 Setup XY 上之中點；弧數不足則 None。"""
    centers = []
    for e in chain_edges or []:
        try:
            if not e or not getattr(e, 'isValid', True):
                continue
            g = e.geometry
            if not g or g.curveType != adsk.core.Curve3DTypes.Arc3DCurveType:
                continue
            arc = adsk.core.Arc3D.cast(g)
            if not arc or not arc.center:
                continue
            centers.append(_slot_pt_to_setup_xy(arc.center, origin, x_ax, y_ax))
        except Exception:
            continue
    if len(centers) >= 2:
        return (
            0.5 * (centers[0][0] + centers[1][0]),
            0.5 * (centers[0][1] + centers[1][1]),
        )
    if len(centers) == 1:
        return centers[0]
    return None


def _slot_pocket_compensation_from_arc_line_cross_xy(chain_edges, origin, x_ax, y_ax):
    """
    腰形槽 2D 叉積補償（與 loop 走訪一致）：

    - 槽心：兩條 Arc3D 圓心在 Setup XY 之中點（辨識幾何與腰形對稱一致）。
    - 參考直邊：_ordered_points_from_edge_chain 還原之封閉頂點序（與 coEdge 鏈走向一致），
      在頂點折線上取 **最長邊段** 為直邊方向（腰形兩直邊長於半圓弦長）。
    - 叉積 (dx,dy)×(cx-sx,cy-sy)：cross≤0 → 'left'，否則 'right'（本模型四鏈 cross 同號時須與手動 pocket2d 一致；仍可用 SLOT_POCKET_COMPENSATION_2D_CROSS_INVERT 對調）。
    """
    if not chain_edges or not origin or not x_ax or not y_ax:
        return None
    mid = _slot_two_arc_midpoint_xy(chain_edges, origin, x_ax, y_ax)
    if mid is None:
        return None
    cx, cy = float(mid[0]), float(mid[1])
    pts3d = _ordered_points_from_edge_chain(chain_edges)
    if len(pts3d) < 3:
        return None
    pts_xy = [_slot_pt_to_setup_xy(p, origin, x_ax, y_ax) for p in pts3d]
    n = len(pts_xy)
    best_i = 0
    best_len2 = -1.0
    for i in range(n):
        j = (i + 1) % n
        dx = pts_xy[j][0] - pts_xy[i][0]
        dy = pts_xy[j][1] - pts_xy[i][1]
        l2 = dx * dx + dy * dy
        if l2 > best_len2:
            best_len2 = l2
            best_i = i
    if best_len2 < 1e-20:
        return None
    i = best_i
    j = (i + 1) % n
    sx, sy = float(pts_xy[i][0]), float(pts_xy[i][1])
    dx = float(pts_xy[j][0]) - sx
    dy = float(pts_xy[j][1]) - sy
    cross = dx * (cy - sy) - dy * (cx - sx)
    if abs(cross) < 1e-20:
        return None
    slug = 'left' if cross <= 0.0 else 'right'
    if SLOT_POCKET_COMPENSATION_2D_CROSS_INVERT:
        slug = 'left' if slug == 'right' else 'right'
    return slug


def _resolve_slot_pocket_compensation_slug(
    chain_edges,
    setup,
    opening_face=None,
    is_inner_loop=True,
    ref_center_mm_xy=None,
    ref_z_mm=None,
):
    """
    B-rep 內環（空腔）→ pocket2d compensation 對表（climb、切除空腔側）：

    - 若 SLOT_POCKET_COMPENSATION_2D_ARC_CROSS 且為內環：優先 _slot_pocket_compensation_from_arc_line_cross_xy（兩弧中點／封閉鏈最長段叉積，Setup XY）。
    - 若 SLOT_POCKET_COMPENSATION_HOST_FACE_VS_Z 且傳入平面之 opening_face（宿主內環面）：僅用 n·Setup+Z，
      dot>0→'left'，否則 'right'。|dot| 過小則退回下列。
    - 否則：有號面積在「開口面 UV」上計算（若有 opening_face）；否則用 Setup XY 投影（_slot_chain_signed_area_setup_xy）。
    - 面法向與 Setup WCS +Z 點積為負時，將有號面積反號，使「從 +Z 俯視開口」之 CW/CCW 與直覺一致。
    - 若 SLOT_POCKET_USE_SCAN_CENTER_FOR_COMP 且傳入 ref_center_mm_xy（辨識槽心，單位 mm）：在與面積相同之 UV 基底上
      做點在多邊形內判斷；內環空腔時槽心應在環內，否則將有號面積反號再對表（以幾何中心校準 coEdge 語意）。
    - 空腔（is_inner_loop）：CCW（面積>0）→ 'right'；CW（面積<0）→ 'left'。
    - 外輪廓島（非空腔）：與上列對調。
    """
    if not chain_edges or not setup:
        return 'left'
    try:
        _o, _xa, _ya, z_dir = setup.workCoordinateSystem.getAsCoordinateSystem()
    except Exception:
        return 'left'
    if (
        SLOT_POCKET_COMPENSATION_2D_ARC_CROSS
        and is_inner_loop
    ):
        try:
            _slug_2d = _slot_pocket_compensation_from_arc_line_cross_xy(
                chain_edges, _o, _xa, _ya
            )
            if _slug_2d:
                return _slug_2d
        except Exception:
            pass
    if (
        SLOT_POCKET_COMPENSATION_HOST_FACE_VS_Z
        and is_inner_loop
        and opening_face
        and getattr(opening_face, 'isValid', True)
    ):
        try:
            geom = opening_face.geometry
            if geom and int(geom.surfaceType) == int(adsk.core.SurfaceTypes.PlaneSurfaceType):
                pln = adsk.core.Plane.cast(geom)
                if pln and z_dir:
                    dn = float(pln.normal.dotProduct(z_dir))
                    if abs(dn) >= 0.01:
                        return 'left' if dn > 0.0 else 'right'
        except Exception:
            pass
    a = 0.0
    o_uv = None
    u_uv = None
    v_uv = None
    try:
        if opening_face and getattr(opening_face, 'isValid', True):
            b = _plane_uv_basis_from_face(opening_face)
            if b:
                o_uv, u_uv, v_uv = b
                a = float(_slot_chain_signed_area_plane_basis(chain_edges, o_uv, u_uv, v_uv))
                try:
                    pln = adsk.core.Plane.cast(opening_face.geometry)
                    if pln and z_dir and abs(a) >= 1e-30:
                        if float(pln.normal.dotProduct(z_dir)) < 0.0:
                            a = -a
                except Exception:
                    pass
    except Exception:
        a = 0.0
    if abs(a) < 1e-20:
        a = float(_slot_chain_signed_area_setup_xy(chain_edges, setup))
        o_uv, u_uv, v_uv = _o, _xa, _ya
    if abs(a) < 1e-20:
        return 'left'
    if (
        SLOT_POCKET_USE_SCAN_CENTER_FOR_COMP
        and ref_center_mm_xy
        and is_inner_loop
        and o_uv is not None
        and u_uv is not None
        and v_uv is not None
    ):
        try:
            cx_mm, cy_mm = float(ref_center_mm_xy[0]), float(ref_center_mm_xy[1])
        except (TypeError, ValueError, IndexError):
            cx_mm, cy_mm = 0.0, 0.0
        try:
            z_off_cm = None
            if ref_z_mm is not None:
                try:
                    o_w, _xa, _ya, za_w = setup.workCoordinateSystem.getAsCoordinateSystem()
                    z_tgt_cm = float(ref_z_mm) / 10.0
                    z0_cm = (
                        o_w.x * za_w.x
                        + o_w.y * za_w.y
                        + o_w.z * za_w.z
                        + (float(cx_mm) / 10.0)
                        * (_xa.x * za_w.x + _xa.y * za_w.y + _xa.z * za_w.z)
                        + (float(cy_mm) / 10.0)
                        * (_ya.x * za_w.x + _ya.y * za_w.y + _ya.z * za_w.z)
                    )
                    z_off_cm = z_tgt_cm - z0_cm
                except Exception:
                    z_off_cm = None
            cpt = _slot_center_point_from_scan_mm(cx_mm, cy_mm, setup, z_off_cm)
            uv_poly = _slot_chain_loop_uvs_axes(chain_edges, o_uv, u_uv, v_uv)
            cu, cv = _project_point_to_uv_axes(cpt, o_uv, u_uv, v_uv)
            if len(uv_poly) >= 3 and not _point_in_polygon_2d(uv_poly, cu, cv):
                a = -a
        except Exception:
            pass
    if abs(a) < 1e-20:
        return 'left'
    is_ccw = a > 0.0
    if is_inner_loop:
        return 'right' if is_ccw else 'left'
    return 'left' if is_ccw else 'right'




def _resolve_slot_loop_edges_from_tokens(design, tokens):
    """以 Design.findEntityByToken 還原槽內環邊（loop_edge_tokens）；見 slot_recognizer 註解。"""
    out = []
    if not design or not tokens:
        return out
    for t in tokens:
        if t is None:
            continue
        try:
            st = t if isinstance(t, str) else str(t)
            if not st:
                continue
            arr = design.findEntityByToken(st)
            if not arr:
                continue
            ent = arr[0]
            e = adsk.fusion.BRepEdge.cast(ent)
            if e and getattr(e, 'isValid', True):
                out.append(e)
        except Exception:
            pass
    return out


def _filter_slot_opening_planar_faces(faces, setup, face_z_ref_mm=None):
    """
    長條孔 execute：只保留法向近似平行 Setup WCS Z 軸的平面（槽開口候選），
    排除與內環共邊一併掃進 slot_recognizer「faces」的垂直側壁／圓柱面；
    避免 pocket2d 誤綁大側壁導致 NoToolpath。
    若無合格平面則回傳原始 faces（向後相容）。若有 face_z_wcs_mm 則優先選
    bbox 沿 Z 投影中點最接近辨識開口 Z 的平面。
    """
    if not faces:
        return []
    if not setup:
        return list(faces)
    try:
        wcs = setup.workCoordinateSystem
        _o, _x, _y, z_axis = wcs.getAsCoordinateSystem()
    except Exception:
        return list(faces)
    raw = [f for f in faces if f and getattr(f, 'isValid', True)]
    if not raw:
        return []
    candidates = []
    for f in raw:
        try:
            geom = f.geometry
        except Exception:
            continue
        try:
            if int(geom.surfaceType) != int(adsk.core.SurfaceTypes.PlaneSurfaceType):
                continue
        except Exception:
            continue
        pl = adsk.core.Plane.cast(geom)
        if not pl:
            continue
        n = pl.normal
        dot = abs(n.x * z_axis.x + n.y * z_axis.y + n.z * z_axis.z)
        if dot <= 0.9:
            continue
        try:
            pmin, pmax = _bbox_proj_min_max(f.boundingBox, z_axis)
            zmid_mm = (pmin + pmax) * 5.0
        except Exception:
            zmid_mm = None
        try:
            area = float(f.area)
        except Exception:
            area = float('inf')
        candidates.append((f, zmid_mm, area))
    if not candidates:
        try:
            send_diag_log('[slot-bind] 開口平面篩選無候選，沿用全部 faces（向後相容）')
        except Exception:
            pass
        return list(raw)
    if face_z_ref_mm is not None:
        ref = float(face_z_ref_mm)

        def _sort_key(c):
            zm = c[1]
            if zm is None:
                return (1e9, c[2])
            return (abs(zm - ref), c[2])

        candidates.sort(key=_sort_key)
    else:
        candidates.sort(key=lambda c: c[2])
    best = [candidates[0][0]]
    try:
        send_diag_log(
            '[slot-bind] 開口平面篩選：%d→%d（ref_face_z_mm=%r）'
            % (len(raw), len(best), face_z_ref_mm)
        )
    except Exception:
        pass
    return best


def _count_brep_face_inner_loops(face):
    n = 0
    if not face:
        return 0
    try:
        for i in range(face.loops.count):
            try:
                if not face.loops.item(i).isOuter:
                    n += 1
            except Exception:
                pass
    except Exception:
        pass
    return n


def _resolve_brep_face_from_token(design, token):
    if not design or not token:
        return None
    try:
        st = token if isinstance(token, str) else str(token)
        if not st:
            return None
        arr = design.findEntityByToken(st)
        if not arr:
            return None
        return adsk.fusion.BRepFace.cast(arr[0])
    except Exception:
        return None


