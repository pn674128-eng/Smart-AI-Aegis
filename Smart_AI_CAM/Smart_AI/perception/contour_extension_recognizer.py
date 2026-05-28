"""
contour_extension_recognizer.py
Module for recognizing T-slots and undercut features.
"""

import adsk.core
import adsk.fusion
import math


def _bbox_proj_min_max(bb, axis):
    ax, ay, az = axis.x, axis.y, axis.z
    minx, miny, minz = bb.minPoint.x, bb.minPoint.y, bb.minPoint.z
    maxx, maxy, maxz = bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z
    pmax = (maxx if ax >= 0 else minx) * ax + (maxy if ay >= 0 else miny) * ay + (maxz if az >= 0 else minz) * az
    pmin = (minx if ax >= 0 else maxx) * ax + (miny if ay >= 0 else maxy) * ay + (minz if az >= 0 else maxz) * az
    return pmin, pmax


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


def scan_undercuts_and_tslots(design, setup, visible_only=True) -> list:
    """
    Scans the design bodies for undercut (overhanging) faces and T-slot candidates.
    Returns a list of recognized feature dictionaries.
    """
    features = []
    if not design or not setup:
        return features

    wcs = setup.workCoordinateSystem
    origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()

    bodies_to_scan = []
    for comp in design.allComponents:
        for bi in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(bi)
            if visible_only and (not _is_body_visible(body)):
                continue
            bodies_to_scan.append(body)

    for body_idx, body in enumerate(bodies_to_scan):
        try:
            bbox = body.boundingBox
            if not bbox:
                continue
            bmin_cm, bmax_cm = _bbox_proj_min_max(bbox, z_axis)
            body_z_min = bmin_cm * 10.0  # mm
            body_z_max = bmax_cm * 10.0  # mm
        except Exception:
            continue

        undercut_faces = []
        
        # Iterate over all faces in the body
        for fi in range(body.faces.count):
            try:
                face = body.faces.item(fi)
                if not face or not face.isValid:
                    continue
                
                # Get a point on the face and its outward normal
                point = face.pointOnFace
                surf_eval = face.evaluator
                _, normal = surf_eval.getNormalAtPoint(point)
                
                # Project normal onto WCS Z-axis
                dot = normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z
                
                # If outward normal points downwards (ceiling)
                if dot < -0.05:
                    # Calculate WCS Z-coordinate of this face in mm
                    dx = point.x - origin.x
                    dy = point.y - origin.y
                    dz = point.z - origin.z
                    face_z = (dx * z_axis.x + dy * z_axis.y + dz * z_axis.z) * 10.0
                    
                    # If this downward face is strictly above the absolute bottom of the body (meaning it is an overhang / undercut)
                    if face_z > (body_z_min + 1.0):
                        # Calculate area in sq mm
                        try:
                            area_sqmm = face.area * 100.0
                        except:
                            area_sqmm = 0.0
                            
                        undercut_faces.append({
                            "face": face,
                            "z_mm": round(face_z, 3),
                            "dot": round(dot, 4),
                            "area_sqmm": round(area_sqmm, 1)
                        })
            except Exception:
                continue
        
        if undercut_faces:
            # Let's identify T-slots if we can find close horizontal parallel matching pairs
            # For each undercut face (ceiling), look for another upward-facing horizontal face of the same body
            # located directly below it (smaller Z) but still above body bottom.
            for idx, uf in enumerate(undercut_faces):
                face = uf["face"]
                z_ceiling = uf["z_mm"]
                
                is_tslot = False
                floor_z = None
                
                # Check for standard T-slot floor (upward facing horizontal face nearby)
                for fi in range(body.faces.count):
                    try:
                        other_face = body.faces.item(fi)
                        if other_face == face:
                            continue
                        
                        point = other_face.pointOnFace
                        surf_eval = other_face.evaluator
                        _, normal = surf_eval.getNormalAtPoint(point)
                        
                        dot = normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z
                        
                        # Upward-facing horizontal face
                        if dot > 0.95:
                            dx = point.x - origin.x
                            dy = point.y - origin.y
                            dz = point.z - origin.z
                            z_floor = (dx * z_axis.x + dy * z_axis.y + dz * z_axis.z) * 10.0
                            
                            # If floor is strictly below ceiling, and difference is typical T-slot height (e.g. 1.5mm to 40mm)
                            height = z_ceiling - z_floor
                            if 1.5 < height < 40.0:
                                # Simple proximity check: horizontal XY distance is small
                                p_ceiling = face.pointOnFace
                                p_floor = other_face.pointOnFace
                                dx_xy = (p_ceiling.x - p_floor.x) * 10.0
                                dy_xy = (p_ceiling.y - p_floor.y) * 10.0
                                dist_xy = math.hypot(dx_xy, dy_xy)
                                
                                if dist_xy < 15.0: # within 15mm horizontal offset
                                    is_tslot = True
                                    floor_z = z_floor
                                    break
                    except Exception:
                        continue
                
                kind = "t_slot" if is_tslot else "undercut"
                
                # Calculate center point in WCS
                try:
                    bb = face.boundingBox
                    wx = (bb.minPoint.x + bb.maxPoint.x) / 2.0
                    wy = (bb.minPoint.y + bb.maxPoint.y) / 2.0
                    wz = (bb.minPoint.z + bb.maxPoint.z) / 2.0
                    dx, dy, dz = wx - origin.x, wy - origin.y, wz - origin.z
                    lx = (dx * x_axis.x + dy * x_axis.y + dz * x_axis.z) * 10.0
                    ly = (dx * y_axis.x + dy * y_axis.y + dz * y_axis.z) * 10.0
                    lz = (dx * z_axis.x + dy * z_axis.y + dz * z_axis.z) * 10.0
                except:
                    lx = ly = lz = 0.0
                
                features.append({
                    "feature_id": f"{kind}_{body_idx}_{idx}",
                    "kind": kind,
                    "body_name": body.name,
                    "z_ceiling_mm": round(z_ceiling, 3),
                    "z_floor_mm": round(floor_z, 3) if floor_z is not None else None,
                    "height_mm": round(z_ceiling - floor_z, 3) if floor_z is not None else None,
                    "area_sqmm": uf["area_sqmm"],
                    "cx_mm": round(lx, 3),
                    "cy_mm": round(ly, 3),
                    "cz_mm": round(lz, 3),
                    "token": getattr(face, "entityToken", f"face_{body_idx}_{idx}")
                })

    return features
