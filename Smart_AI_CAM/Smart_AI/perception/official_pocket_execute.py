# -*- coding: utf-8 -*-
"""
Execute Fusion RecognizedPocket via existing template + chain/face binding.

Supports flexible bind modes (templates vary per shop):
  - 2d_only: pocket2d / contour2d on boundary chain
  - 3d_only: pocket/adaptive on bottom faces (blind) or chain+faces fallback
  - 2d_then_3d: 2D contour then 3D rough (two templates)
  - auto: through -> 2d; blind with bottom -> 2d_then_3d if both URLs else 2d or 3d
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import math

import adsk.cam
import adsk.core
import adsk.fusion


def _setup_search_vector(setup) -> adsk.core.Vector3D:
    try:
        wcs = setup.workCoordinateSystem
        _o, _x, _y, z_axis = wcs.getAsCoordinateSystem()
        return adsk.core.Vector3D.create(-z_axis.x, -z_axis.y, -z_axis.z)
    except Exception:
        return adsk.core.Vector3D.create(0, 0, -1)


def _edge_token(edge) -> str:
    try:
        return edge.entityToken or str(id(edge))
    except Exception:
        return str(id(edge))


def _collect_pocket_faces(pocket: adsk.cam.RecognizedPocket) -> List[adsk.fusion.BRepFace]:
    out = []
    try:
        for f in pocket.faces:
            if f and getattr(f, "isValid", True):
                out.append(f)
    except Exception:
        pass
    return out


def _pocket_bottom_and_wall_faces(
    pocket: adsk.cam.RecognizedPocket, search_vec: adsk.core.Vector3D
) -> Tuple[List[adsk.fusion.BRepFace], List[adsk.fusion.BRepFace]]:
    """Fusion sample logic: normal parallel to search vector -> bottom."""
    bottoms, walls = [], []
    for face in _collect_pocket_faces(pocket):
        try:
            _, n = face.evaluator.getNormalAtPoint(face.pointOnFace)
            if n.isParallelTo(search_vec):
                bottoms.append(face)
            else:
                walls.append(face)
        except Exception:
            walls.append(face)
    return bottoms, walls


def _edges_from_pocket_faces(pocket: adsk.cam.RecognizedPocket) -> List:
    """
    Collect B-rep edges from pocket face loops (official pocket.faces).
    Prefer inner loops on wall faces; dedupe by entityToken.
    """
    seen = set()
    edges = []
    for face in _collect_pocket_faces(pocket):
        try:
            for li in range(face.loops.count):
                loop = face.loops.item(li)
                for ci in range(loop.coEdges.count):
                    co = loop.coEdges.item(ci)
                    e = co.edge
                    key = _edge_token(e)
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(e)
        except Exception:
            continue
    return edges


def _order_edges_into_chains(edges: List) -> List[List]:
    """Greedy chain from edge connectivity (single pocket boundary)."""
    if not edges:
        return []
    remaining = list(edges)
    chains = []

    def _endpoints(edge):
        try:
            sp, ep = edge.evaluator.getEndPoints()
            return sp, ep
        except Exception:
            return None, None

    def _pt_key(p, tol=0.02):
        if p is None:
            return None
        return (round(p.x / tol), round(p.y / tol), round(p.z / tol))

    while remaining:
        chain = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            sp0, ep0 = _endpoints(chain[-1])
            for i, e in enumerate(remaining):
                sp, ep = _endpoints(e)
                k_ep = _pt_key(ep0)
                k_sp = _pt_key(sp)
                k_ep2 = _pt_key(ep)
                if k_ep is None:
                    continue
                if k_sp == k_ep:
                    chain.append(e)
                    remaining.pop(i)
                    changed = True
                    break
                if k_ep2 == k_ep:
                    chain.insert(0, e)
                    remaining.pop(i)
                    changed = True
                    break
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def resolve_pocket_geometry(
    pocket: adsk.cam.RecognizedPocket, setup
) -> dict:
    search_vec = _setup_search_vector(setup)
    bottoms, walls = _pocket_bottom_and_wall_faces(pocket, search_vec)
    edges = _edges_from_pocket_faces(pocket)
    chains = _order_edges_into_chains(edges)
    if not chains and len(edges) >= 2:
        chains = [edges]
    return {
        "chain_profiles": chains,
        "bottom_faces": bottoms,
        "wall_faces": walls,
        "edge_count": len(edges),
        "is_through": bool(getattr(pocket, "isThrough", False)),
        "is_closed": bool(getattr(pocket, "isClosed", True)),
    }


def get_recognized_pocket_by_index(
    design: adsk.fusion.Design, setup, body, pocket_index: int
) -> Optional[adsk.cam.RecognizedPocket]:
    if not body or pocket_index < 0:
        return None
    try:
        vec = _setup_search_vector(setup)
        pockets = adsk.cam.RecognizedPocket.recognizePockets(body, vec)
        if pocket_index >= pockets.count:
            return None
        return pockets.item(pocket_index)
    except Exception:
        return None


def infer_bind_mode(
    geom: dict,
    *,
    user_mode: str = "auto",
    has_2d_url: bool = False,
    has_3d_url: bool = False,
) -> str:
    mode = str(user_mode or "auto").strip().lower()
    if mode in ("2d", "2d_only", "pure_2d"):
        return "2d_only"
    if mode in ("3d", "3d_only", "pure_3d"):
        return "3d_only"
    if mode in ("2d_3d", "2d+3d", "2d_then_3d", "both"):
        return "2d_then_3d"
    # auto
    if has_2d_url and has_3d_url and not geom.get("is_through") and geom.get("bottom_faces"):
        return "2d_then_3d"
    if has_3d_url and not has_2d_url and geom.get("bottom_faces"):
        return "3d_only"
    if has_2d_url:
        return "2d_only"
    if has_3d_url:
        return "3d_only"
    return "2d_only"


def _project_point_setup_xy_mm(point, setup) -> Tuple[float, float]:
    try:
        wcs = setup.workCoordinateSystem
        origin, x_axis, y_axis, _z = wcs.getAsCoordinateSystem()
        v = adsk.core.Vector3D.create(
            point.x - origin.x,
            point.y - origin.y,
            point.z - origin.z,
        )
        return (
            round((v.x * x_axis.x + v.y * x_axis.y + v.z * x_axis.z) * 10.0, 3),
            round((v.x * y_axis.x + v.y * y_axis.y + v.z * y_axis.z) * 10.0, 3),
        )
    except Exception:
        return 0.0, 0.0


def _chain_setup_xy_extents_mm(edges: List, setup) -> Tuple[float, float, float, float]:
    xs, ys = [], []
    for e in edges or []:
        try:
            sp, ep = e.evaluator.getEndPoints()
            for p in (sp, ep):
                if p:
                    x, y = _project_point_setup_xy_mm(p, setup)
                    xs.append(x)
                    ys.append(y)
        except Exception:
            continue
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), max(xs), min(ys), max(ys)


def _edge_curve_kind(edge) -> str:
    try:
        ct = edge.geometry.curveType
        if ct == adsk.core.Curve3DTypes.Arc3DCurveType:
            return "arc"
        if ct == adsk.core.Curve3DTypes.Line3DCurveType:
            return "line"
    except Exception:
        pass
    return "other"


def _is_obround_slot_chain(chain: List, setup, *, min_aspect: float = 1.35) -> bool:
    """
    與 slot_recognizer 一致：腰形槽 = 封閉環 **2 弧 + 2 直線**，兩弧同徑，長寬比明顯。
    矩形口袋（4 直線）、圓槽、多邊口袋一律不算長條孔。
    """
    if not chain or len(chain) != 4:
        return False
    arcs = 0
    lines = 0
    radii_cm = []
    centers_xy = []
    for e in chain:
        kind = _edge_curve_kind(e)
        if kind == "arc":
            arcs += 1
            try:
                ag = adsk.core.Arc3D.cast(e.geometry)
                if ag:
                    radii_cm.append(float(ag.radius))
                    c = ag.center
                    centers_xy.append(_project_point_setup_xy_mm(c, setup))
            except Exception:
                return False
        elif kind == "line":
            lines += 1
        else:
            return False
    if arcs != 2 or lines != 2:
        return False
    if len(radii_cm) != 2 or abs(radii_cm[0] - radii_cm[1]) > 0.02:
        return False
    r_mm = radii_cm[0] * 10.0
    if r_mm < 0.05:
        return False
    if len(centers_xy) != 2:
        return False
    dx = centers_xy[1][0] - centers_xy[0][0]
    dy = centers_xy[1][1] - centers_xy[0][1]
    center_dist_mm = math.hypot(dx, dy)
    length_mm = center_dist_mm + 2.0 * r_mm
    width_mm = 2.0 * r_mm
    if width_mm < 0.05:
        return False
    aspect = length_mm / width_mm
    return aspect >= min_aspect


def _pocket_is_circular_flag(pocket: adsk.cam.RecognizedPocket) -> bool:
    try:
        if hasattr(pocket, "isCircular"):
            return bool(pocket.isCircular)
    except Exception:
        pass
    return False


def _chain_is_circular_hole_profile(chain: List) -> bool:
    """圓孔開口常為全弧邊（無直線段），非腰形槽。"""
    if not chain or len(chain) < 2:
        return False
    arcs = 0
    lines = 0
    for e in chain:
        k = _edge_curve_kind(e)
        if k == "arc":
            arcs += 1
        elif k == "line":
            lines += 1
    if lines == 0 and arcs >= 1:
        return True
    return False


def should_exclude_recognized_pocket_from_panel(
    pocket: adsk.cam.RecognizedPocket, setup
) -> bool:
    """
    RecognizedPocket 常把圓孔／沉頭誤列為口袋。
    純孔件（如僅圓孔板）應不進「官方長條／口袋槽」表。
    保留：腰形長條孔、明確非圓孔之盲口袋（非通孔、非圓柱為主）。
    """
    if _pocket_is_circular_flag(pocket):
        return True

    geom = resolve_pocket_geometry(pocket, setup)
    chains = list(geom.get("chain_profiles") or [])
    if not chains:
        edges = _edges_from_pocket_faces(pocket)
        chains = _order_edges_into_chains(edges)

    for chain in chains:
        if _is_obround_slot_chain(chain, setup):
            return False

    is_through = bool(getattr(pocket, "isThrough", False))
    if is_through:
        return True

    faces = _collect_pocket_faces(pocket)
    if not faces:
        return True

    n_cyl = 0
    n_plane = 0
    for f in faces:
        try:
            st = f.geometry.surfaceType
            if st == adsk.core.SurfaceTypes.CylinderSurfaceType:
                n_cyl += 1
            elif st == adsk.core.SurfaceTypes.PlaneSurfaceType:
                n_plane += 1
        except Exception:
            pass

    for chain in chains:
        if _chain_is_circular_hole_profile(chain):
            return True

    n_faces = len(faces)
    if n_cyl >= 1 and n_cyl >= max(2, int(n_faces * 0.55)):
        return True

    bottoms, walls = _pocket_bottom_and_wall_faces(pocket, _setup_search_vector(setup))
    if not bottoms and n_cyl >= 1 and n_plane <= 1:
        return True

    return False


def classify_recognized_pocket_kind(
    pocket: adsk.cam.RecognizedPocket, setup
) -> str:
    """
    RecognizedPocket → UI 分欄：
      - ``slot``：僅腰形（2 弧 + 2 直線，同徑，長 > 寬）
      - ``pocket``：其餘官方口袋（預設）
    """
    geom = resolve_pocket_geometry(pocket, setup)
    chains = geom.get("chain_profiles") or []
    if not chains:
        edges = _edges_from_pocket_faces(pocket)
        chains = _order_edges_into_chains(edges)

    for chain in chains:
        if _is_obround_slot_chain(chain, setup):
            return "slot"
    return "pocket"


def pocket_display_spec_mm(pocket: adsk.cam.RecognizedPocket, setup, pocket_kind: str) -> dict:
    """Setup XY 包絡與深度，供面板「規格」欄。"""
    out = {"width_mm": None, "length_mm": None, "depth_mm": None}
    try:
        geom = resolve_pocket_geometry(pocket, setup)
        chains = geom.get("chain_profiles") or []
        main = max(chains, key=len) if chains else []
        if main:
            minx, maxx, miny, maxy = _chain_setup_xy_extents_mm(main, setup)
            span_x = max(0.0, maxx - minx)
            span_y = max(0.0, maxy - miny)
            out["width_mm"] = round(min(span_x, span_y), 3)
            out["length_mm"] = round(max(span_x, span_y), 3)
        if not bool(getattr(pocket, "isThrough", False)):
            try:
                out["depth_mm"] = round(float(pocket.depth) * 10.0, 3)
            except Exception:
                pass
    except Exception:
        pass
    if pocket_kind == "slot" and out["width_mm"] is None:
        out["width_mm"] = 0.0
    return out


def classify_template_bind_hint(label: str, url_key: str = "") -> str:
    """Heuristic: template name -> 2d vs 3d pocket strategy."""
    s = (str(label or "") + " " + str(url_key or "")).lower()
    if any(k in s for k in ("adaptive", "3d", "rough", "粗", "残", "残量")):
        return "3d"
    if any(k in s for k in ("pocket", "口袋", "2d", "槽", "slot", "contour", "輪廓")):
        return "2d"
    return "2d"

