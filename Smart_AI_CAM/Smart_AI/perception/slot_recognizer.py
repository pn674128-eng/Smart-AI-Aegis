# -*- coding: utf-8 -*-
# slot_recognizer.py — 長條孔（腰形：2 弧 + 2 直線）loop 辨識
#
# 深度與通槽（定案；內部 cm，輸出 mm 為數值 ×10）
# 1) loop 開口面 Z：face_z = fz_max if dot_z > 0 else fz_min
# 2) 槽壁圓柱 Z：只收與此 loop 共邊（coEdges）且 CylinderSurfaceType 的鄰面 bbox 在 WCS Z 的 min/max
# 3) 槽深：頂面開口 dot_z>0 → depth = face_z - slot_z_min；底面開口 → depth = slot_z_max - face_z
# 4) 通槽：through = abs(slot_z_min - body_z_bot) < through_tol
#
# 加工用篩選（見 filter_slots_for_machining）：
#   - 只保留開口層：slot_z_max_mm ≈ face_z_wcs_mm，且 depth_mm > 0（頂面開口盲槽等）
#   - depth≈0 或其它層的 loop 仍留在 scan_slots 全量結果，供展層／背面參考

"""Racetrack slot recognizer from planar inner loops (2 arcs + 2 lines).

Depth / through (final spec, internal cm; *_mm fields are cm*10):
  face_z = fz_max if dot_z > 0 else fz_min
  slot Z from adjacent CylinderSurfaceType faces on loop coEdges
  if dot_z > 0: depth_cm = face_z - slot_z_min
  else: depth_cm = slot_z_max - face_z
  through = abs(slot_z_min - body_z_bot) < through_tol
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

import adsk.cam
import adsk.core
import adsk.fusion
from smart_ai_cam_state.runtime_state import state as runtime_state


def _is_body_visible(body: adsk.fusion.BRepBody) -> bool:
    try:
        return bool(body.isVisible)
    except Exception:
        pass
    try:
        return bool(body.isLightBulbOn)
    except Exception:
        pass
    return True


def _bbox_proj_min_max(bb: adsk.core.BoundingBox3D, axis: adsk.core.Vector3D) -> Tuple[float, float]:
    ax, ay, az = axis.x, axis.y, axis.z
    pmax = (bb.maxPoint.x if ax >= 0 else bb.minPoint.x) * ax + (
        bb.maxPoint.y if ay >= 0 else bb.minPoint.y
    ) * ay + (bb.maxPoint.z if az >= 0 else bb.minPoint.z) * az
    pmin = (bb.minPoint.x if ax >= 0 else bb.maxPoint.x) * ax + (
        bb.minPoint.y if ay >= 0 else bb.maxPoint.y
    ) * ay + (bb.minPoint.z if az >= 0 else bb.maxPoint.z) * az
    return pmin, pmax


def _to_local_xy(
    pt: adsk.core.Point3D,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
) -> Tuple[float, float]:
    dx = pt.x - origin.x
    dy = pt.y - origin.y
    dz = pt.z - origin.z
    lx = dx * x_axis.x + dy * x_axis.y + dz * x_axis.z
    ly = dx * y_axis.x + dy * y_axis.y + dz * y_axis.z
    return lx, ly


def _loop_edges(loop: adsk.fusion.BRepLoop) -> List[adsk.fusion.BRepEdge]:
    out: List[adsk.fusion.BRepEdge] = []
    for i in range(loop.coEdges.count):
        out.append(loop.coEdges.item(i).edge)
    return out


def _slot_wall_cylinder_z_range(
    loop: adsk.fusion.BRepLoop,
    z_axis: adsk.core.Vector3D,
) -> Optional[Tuple[float, float, List[float]]]:
    cyl_z_vals: List[float] = []
    seen_tok: Set[Any] = set()
    for i in range(loop.coEdges.count):
        edge = loop.coEdges.item(i).edge
        for j in range(edge.faces.count):
            af = edge.faces.item(j)
            try:
                tok = af.entityToken
            except Exception:
                tok = id(af)
            if tok in seen_tok:
                continue
            seen_tok.add(tok)
            try:
                if af.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                    continue
            except Exception:
                continue
            czmin, czmax = _bbox_proj_min_max(af.boundingBox, z_axis)
            cyl_z_vals.extend([czmin, czmax])
    if not cyl_z_vals:
        return None
    return min(cyl_z_vals), max(cyl_z_vals), cyl_z_vals


def _opening_face_entity_token_from_loop(host_face: adsk.fusion.BRepFace, loop: adsk.fusion.BRepLoop) -> Optional[str]:
    """
    部分 Fusion 版本下 BRepFace.entityToken 為 None；內環 coEdge 之邊所鄰接平面中，
    以法向平行 + 面積接近 host_face 者取 token（與 loop_edge_tokens 同一幾何上下文）。
    """
    try:
        hg = host_face.geometry
        if hg.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            return None
        pl_h = adsk.core.Plane.cast(hg)
        if not pl_h:
            return None
        nh = pl_h.normal
        ar_h = float(host_face.area)
    except Exception:
        return None
    for i in range(loop.coEdges.count):
        try:
            ed = loop.coEdges.item(i).edge
        except Exception:
            continue
        try:
            for j in range(ed.faces.count):
                ff = ed.faces.item(j)
                if not ff:
                    continue
                try:
                    if ff is host_face:
                        tok = ff.entityToken
                        if tok is not None:
                            st = tok if isinstance(tok, str) else str(tok)
                            if st.strip():
                                return st
                except Exception:
                    pass
                try:
                    g = ff.geometry
                    if g.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                        continue
                    plf = adsk.core.Plane.cast(g)
                    if not plf:
                        continue
                    nf = plf.normal
                    dot = abs(nf.x * nh.x + nf.y * nh.y + nf.z * nh.z)
                    if dot < 0.99:
                        continue
                    ar_f = float(ff.area)
                    if abs(ar_f - ar_h) > max(1e-10, 1e-5 * max(abs(ar_f), abs(ar_h), 1.0)):
                        continue
                    tok = ff.entityToken
                    if tok is None:
                        continue
                    st = tok if isinstance(tok, str) else str(tok)
                    if st.strip():
                        return st
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _slot_from_loop(
    loop: adsk.fusion.BRepLoop,
    face: adsk.fusion.BRepFace,
    body_z_bot: float,
    body_z_top: float,
    origin: adsk.core.Point3D,
    x_axis: adsk.core.Vector3D,
    y_axis: adsk.core.Vector3D,
    z_axis: adsk.core.Vector3D,
    radius_tol_cm: float = 0.002,
    through_tol: float = 0.05,
) -> Optional[Dict[str, Any]]:
    geom = face.geometry
    if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
        return None
    plane = adsk.core.Plane.cast(geom)
    if not plane:
        return None
    dot_z = plane.normal.dotProduct(z_axis)
    if abs(abs(dot_z) - 1.0) > 0.01:
        return None

    edges = _loop_edges(loop)
    arcs: List[adsk.fusion.BRepEdge] = []
    lines: List[adsk.fusion.BRepEdge] = []
    for e in edges:
        try:
            ct = e.geometry.curveType
        except Exception:
            continue
        if ct == adsk.core.Curve3DTypes.Arc3DCurveType:
            arcs.append(e)
        elif ct == adsk.core.Curve3DTypes.Line3DCurveType:
            lines.append(e)

    if len(arcs) != 2 or len(lines) != 2:
        return None

    a1g = adsk.core.Arc3D.cast(arcs[0].geometry)
    a2g = adsk.core.Arc3D.cast(arcs[1].geometry)
    if not a1g or not a2g:
        return None
    if abs(a1g.radius - a2g.radius) > radius_tol_cm:
        return None
    r = a1g.radius

    c1 = _to_local_xy(a1g.center, origin, x_axis, y_axis, z_axis)
    c2 = _to_local_xy(a2g.center, origin, x_axis, y_axis, z_axis)
    cx = (c1[0] + c2[0]) * 0.5
    cy = (c1[1] + c2[1]) * 0.5
    dx = c2[0] - c1[0]
    dy = c2[1] - c1[1]
    center_dist = math.hypot(dx, dy)
    length_cm = center_dist + 2.0 * r
    angle_deg = round(math.degrees(math.atan2(dy, dx)), 1) if (dx != 0.0 or dy != 0.0) else 0.0

    fz_min, fz_max = _bbox_proj_min_max(face.boundingBox, z_axis)
    face_z = fz_max if dot_z > 0 else fz_min

    cyl_range = _slot_wall_cylinder_z_range(loop, z_axis)
    if cyl_range is None:
        return None
    slot_z_min, slot_z_max, _ = cyl_range

    if dot_z > 0:
        depth_cm = face_z - slot_z_min
    else:
        depth_cm = slot_z_max - face_z

    through = abs(slot_z_min - body_z_bot) < through_tol

    depth_mm_out = round(depth_cm * 10.0, 3)
    if abs(depth_mm_out) < 1e-6:
        depth_mm_out = 0.0

    faces_out: List[adsk.fusion.BRepFace] = []
    seen_f: Set[Any] = set()
    for e in edges:
        for j in range(e.faces.count):
            f = e.faces.item(j)
            try:
                tok = f.entityToken
            except Exception:
                tok = id(f)
            if tok in seen_f:
                continue
            seen_f.add(tok)
            faces_out.append(f)

    # Fusion 下 BRepEdge 置於 dict 內有時會變成空參考；另存 entityToken 供 execute 以 Design.findEntityByToken 還原。
    loop_edge_tokens: List[Any] = []
    for e in edges:
        try:
            t = e.entityToken
            loop_edge_tokens.append(t if isinstance(t, str) else str(t))
        except Exception:
            loop_edge_tokens.append(None)

    opening_face_token: Optional[str] = None
    for _src in (loop, face):
        if opening_face_token:
            break
        try:
            if not _src or not hasattr(_src, "entityToken"):
                continue
            ft = _src.entityToken
            if ft is None:
                continue
            st = ft if isinstance(ft, str) else str(ft)
            if st.strip():
                opening_face_token = st
                break
        except Exception:
            continue

    if not opening_face_token:
        opening_face_token = _opening_face_entity_token_from_loop(face, loop)

    # 多數環境下 BRepFace.entityToken 仍為空；內環邊 token 可用，供診斷／穩定錨點（非面 token）。
    opening_anchor_edge_token: Optional[str] = None
    for t in loop_edge_tokens:
        if t is None:
            continue
        ts = t if isinstance(t, str) else str(t)
        if ts.strip():
            opening_anchor_edge_token = ts
            break

    out: Dict[str, Any] = {
        "width_mm": round(r * 2.0 * 10.0, 3),
        "length_mm": round(length_cm * 10.0, 3),
        "depth_mm": depth_mm_out,
        "through": bool(through),
        "cx": round(cx * 10.0, 3),
        "cy": round(cy * 10.0, 3),
        "angle_deg": angle_deg,
        "face_z_wcs_mm": round(face_z * 10.0, 3),
        "top_z_wcs_mm": round(body_z_top * 10.0, 3),
        "bot_z_wcs_mm": round(body_z_bot * 10.0, 3),
        "slot_z_min_mm": round(slot_z_min * 10.0, 3),
        "slot_z_max_mm": round(slot_z_max * 10.0, 3),
        "faces": faces_out,
        # 承載此 inner loop 的 BRep 面（_slot_from_loop 的 face 參數）；execute 應以此為 opening_face，勿以同高最大面積猜測。
        # pocket2d compensation 可僅依「此法向·Setup +Z」（見主檔 SLOT_POCKET_COMPENSATION_HOST_FACE_VS_Z），與 coEdge 在兩片同向面上的差異脫鉤。
        "host_opening_face": face,
        # 開口內環 2 弧+2 直線之邊（coEdge 順序），供 CAM pocket2d／contour2d 以 ChainSelection 綁 2D 輪廓
        "loop_edges": list(edges),
        "loop_edge_tokens": loop_edge_tokens,
        # 內環所屬平面（掃描時之 host face）；多內環大面時供診斷，execute 仍以 loop 邊鏈綁 pocket2d。
        "opening_face_token": opening_face_token,
    }
    if not opening_face_token:
        out["opening_face_token_diag"] = "BRepFace.entityToken 不可用（本機 API）；見開口錨點邊Token"
        if opening_anchor_edge_token:
            out["opening_anchor_edge_token"] = opening_anchor_edge_token
    return out


def filter_slots_for_machining(
    slots: List[Dict[str, Any]],
    depth_min_mm: float = 1e-6,
    require_opening_layer: bool = True,
    opening_layer_tol_mm: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    實際用於加工：只保留「開口層」loop。

    - depth_mm > depth_min_mm：對應頂面開口且 depth>0（例如 w=5.5、depth=5）。
    - require_opening_layer 為 True 時：要求 loop 在開口層。
      為兼容不同 Setup/WCS 方向，接受：
        slot_z_max_mm ≈ face_z_wcs_mm 或 slot_z_min_mm ≈ face_z_wcs_mm

    scan_slots() 仍回傳全量；depth≈0 或其它層可留給展層／背面策略參考。
    """
    out: List[Dict[str, Any]] = []
    for s in slots:
        try:
            depth = float(s.get("depth_mm", 0.0))
        except (TypeError, ValueError):
            depth = 0.0
        if depth <= depth_min_mm:
            continue
        if require_opening_layer:
            try:
                face_z = float(s.get("face_z_wcs_mm", 0.0))
                slot_z_max = float(s.get("slot_z_max_mm", 0.0))
                slot_z_min = float(s.get("slot_z_min_mm", 0.0))
            except (TypeError, ValueError):
                continue
            is_open_layer = (
                abs(slot_z_max - face_z) <= opening_layer_tol_mm
                or abs(slot_z_min - face_z) <= opening_layer_tol_mm
            )
            if not is_open_layer:
                continue
        out.append(s)
    return out


def scan_slots(
    design: adsk.fusion.Design,
    setup: adsk.cam.Setup,
    visible_only: bool = True,
    through_tol: float = 0.05,
) -> List[Dict[str, Any]]:
    if not design or not setup:
        return []

    wcs = setup.workCoordinateSystem
    origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()

    results: List[Dict[str, Any]] = []
    seen: Set[Tuple[float, float, float, float]] = set()

    bodies_to_scan = []
    scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
    if scan_bodies is not None:
        for entry in scan_bodies:
            if visible_only and (not entry["visible"]):
                continue
            bodies_to_scan.append((entry["body"], entry["bbox"]))
    else:
        for comp in design.allComponents:
            for bi in range(comp.bRepBodies.count):
                body = comp.bRepBodies.item(bi)
                if visible_only and not _is_body_visible(body):
                    continue
                bodies_to_scan.append((body, body.boundingBox))

    for body, bbox in bodies_to_scan:
        if bbox is None:
            continue
        body_z_bot, body_z_top = _bbox_proj_min_max(bbox, z_axis)

        for fi in range(body.faces.count):
            face = body.faces.item(fi)
            geom = face.geometry
            if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                continue
            plane = adsk.core.Plane.cast(geom)
            if not plane:
                continue
            dot_z = plane.normal.dotProduct(z_axis)
            if abs(abs(dot_z) - 1.0) > 0.01:
                continue

            for li in range(face.loops.count):
                loop = face.loops.item(li)
                try:
                    if loop.isOuter:
                        continue
                except Exception:
                    continue

                slot = _slot_from_loop(
                    loop,
                    face,
                    body_z_bot,
                    body_z_top,
                    origin,
                    x_axis,
                    y_axis,
                    z_axis,
                    through_tol=through_tol,
                )
                if not slot:
                    continue

                key = (
                    round(float(slot["cx"]), 1),
                    round(float(slot["cy"]), 1),
                    float(slot["width_mm"]),
                    float(slot["depth_mm"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append(slot)

    results.sort(key=lambda x: (x["width_mm"], x["depth_mm"]))
    return results