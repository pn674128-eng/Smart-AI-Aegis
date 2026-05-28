# -*- coding: utf-8 -*-
import adsk
import adsk.core, adsk.fusion, adsk.cam
import math
import os
import json
import re
import time
import importlib
import sys
import traceback
from smart_ai_cam_state.runtime_state import state as runtime_state
from smart_ai_cam_ui.diagnostics import send_diag_log
from smart_ai_cam_ui.palette_data_provider import (
    buildDropItems,
    build_simple_drill_drop_items_only,
    _load_ui_defaults,
    _extract_template_diameter_mm,
)
from smart_ai_cam_machining.geometry_utils import _bbox_proj_min_max

def start_scan_session(design, visible_only=True):
    """
    Start a scanning session. Collects all design bodies once and caches them 
    in runtime_state.scan_bodies_cache to avoid redundant COM property queries 
    across multiple recognizers.
    """
    runtime_state.scan_bodies_cache = []
    if not design:
        return
    
    try:
        t0 = time.perf_counter()
        # Traverse design components and build cache
        for comp in design.allComponents:
            try:
                count = comp.bRepBodies.count
            except Exception:
                continue
            for bi in range(count):
                try:
                    body = comp.bRepBodies.item(bi)
                    if not body:
                        continue
                    
                    token = None
                    try:
                        token = body.entityToken
                    except Exception:
                        pass
                    
                    bbox = None
                    try:
                        bbox = body.boundingBox
                    except Exception:
                        pass
                    
                    visible = True
                    try:
                        visible = body.isVisible
                    except Exception:
                        try:
                            visible = body.isLightBulbOn
                        except Exception:
                            pass
                    
                    runtime_state.scan_bodies_cache.append({
                        "body": body,
                        "token": token,
                        "bbox": bbox,
                        "visible": visible,
                        "comp": comp
                    })
                except Exception:
                    continue
        t_elapsed = time.perf_counter() - t0
        send_diag_log(f"[scan_session] Cached {len(runtime_state.scan_bodies_cache)} bodies in {t_elapsed:.4f}s")
    except Exception as ex:
        send_diag_log(f"[scan_session] Failed to build scan_bodies_cache: {ex}")
        runtime_state.scan_bodies_cache = None

def end_scan_session():
    """
    End the scan session and clear the bodies cache.
    """
    if hasattr(runtime_state, "scan_bodies_cache"):
        runtime_state.scan_bodies_cache = None

def _template_cache_key(url_obj=None, fallback=''):
    try:
        if url_obj:
            try:
                s = str(url_obj.toString()).strip()
                if s:
                    return s
            except:
                pass
            try:
                leaf = str(url_obj.leafName or '').strip()
                if leaf:
                    return f'leaf:{leaf}'
            except:
                pass
            try:
                s = str(url_obj).strip()
                if s:
                    return s
            except:
                pass
    except Exception:
        pass
    return fallback

def _recommend_slot_tool_dia(width_mm):
    """Recommend largest feasible tool by D+0.5 <= W <= D*1.8."""
    tools = [2.0, 3.0, 4.0, 6.0, 10.0]
    try:
        w = float(width_mm)
    except:
        return ''
    candidates = [d for d in tools if (d + 0.5) <= w <= (d * 1.8)]
    if not candidates:
        return '無可用刀'
    best = max(candidates)
    return f'ϕ{int(best) if abs(best - int(best)) < 1e-9 else best}'


def _recommend_slot_tool_mm(width_mm):
    """Return recommended tool diameter (mm) as number, or None."""
    tools = [2.0, 3.0, 4.0, 6.0, 10.0]
    try:
        w = float(width_mm)
    except:
        return None
    candidates = [d for d in tools if (d + 0.5) <= w <= (d * 1.8)]
    if not candidates:
        return None
    return float(max(candidates))

# Diagnostic Logging Aliases
_send_diag_log = send_diag_log

# Global module property lookup via __getattr__
def __getattr__(name):
    if name == 'des_obj':
        return runtime_state.des_obj
    if name in ('cam_setup', 'camSetup'):
        return runtime_state.cam_setup
    if name == 'ui':
        return runtime_state.ui
    if name == 'app':
        return runtime_state.app
    if name == 'cam_obj':
        return runtime_state.cam_obj
    if name in ('tmpl_lib', 'tmplLib'):
        return runtime_state.tmpl_lib
    if name in (
        'allDrillMap', 'allChamferMap', 'allCountersinkMap', 'allSlotMap', 'allSlotChamferMap',
        'allTopFaceMap', 'allProfileMap', 'allTopFaceRoughMap', 'allTopFaceFinishMap',
        'allProfileRoughMap', 'allProfileFinishMap'
    ):
        return getattr(runtime_state, name, {})
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _fusion_refs():
    """目前 Design / CAM Setup / CAM 物件（模組內請用此函式，勿 global cam_obj）。"""
    return (
        runtime_state.des_obj,
        runtime_state.cam_setup,
        runtime_state.cam_obj,
        runtime_state.tmpl_lib,
    )


def _safe_cam_from_document(doc):
    """
    取得或建立 CAM 參照。
    """
    if not doc:
        return None
    try:
        p = doc.products.itemByProductType('CAMProductType')
        return adsk.cam.CAM.cast(p) if p else None
    except Exception:
        return None

def _active_document_key(doc):
    if not doc:
        return ""
    try:
        tok = doc.entityToken
        if tok:
            return str(tok)
    except Exception:
        pass
    try:
        return str(doc.name or "")
    except Exception:
        pass
    return str(id(doc))


def _find_setup_by_name(cam, name):
    """Return CAM Setup by display name, or None."""
    setup_name = (name or "").strip()
    if not cam or not setup_name:
        return None
    for i in range(cam.setups.count):
        try:
            s = cam.setups.item(i)
            if s and getattr(s, "isValid", True) and s.name == setup_name:
                return s
        except Exception:
            continue
    return None


def apply_panel_setup(name, *, activate_in_fusion=True):
    """
    Pin add-in scan/vision to a named Setup.
    When activate_in_fusion is True, also call Setup.activate() so Fusion browser stays in sync.
    """
    setup_name = (name or "").strip()
    if not setup_name:
        return None
    cam = runtime_state.cam_obj
    if not cam:
        return None
    target = _find_setup_by_name(cam, setup_name)
    if not target:
        return None
    runtime_state.pending_setup_name = setup_name
    runtime_state.cam_setup = target
    if activate_in_fusion:
        try:
            target.activate()
        except Exception:
            pass
    return target


def _validate_and_refresh_refs():
    try:
        if not runtime_state.app:
            runtime_state.app = adsk.core.Application.get()
        if not runtime_state.ui and runtime_state.app:
            runtime_state.ui = runtime_state.app.userInterface

        doc = runtime_state.app.activeDocument if runtime_state.app else None
        if not doc:
            runtime_state.active_document_token = ""
            return False

        doc_key = _active_document_key(doc)
        if doc_key != (runtime_state.active_document_token or ""):
            runtime_state.active_document_token = doc_key
            runtime_state.des_obj = None
            runtime_state.cam_obj = None
            runtime_state.cam_setup = None
            runtime_state.pending_setup_name = ""
            runtime_state.last_display_signature = ""
            runtime_state.vision_snapshot = None
            runtime_state.holeInfoList = []
            runtime_state.slotInfoList = []
            runtime_state.pocketCornerRInfoList = []
            for _k in (
                "fusion_official_recognition",
                "official_pocket_panel_rows",
                "feature_catalog",
                "contour_2d_recognition",
            ):
                if hasattr(runtime_state, _k):
                    setattr(runtime_state, _k, None)

        try:
            des_p = doc.products.itemByProductType("DesignProductType")
            if des_p:
                runtime_state.des_obj = adsk.fusion.Design.cast(des_p)
        except Exception:
            pass

        try:
            cam_p = _safe_cam_from_document(doc)
            if cam_p:
                runtime_state.cam_obj = cam_p
        except Exception:
            pass

        is_setup_valid = False
        if runtime_state.cam_setup and getattr(runtime_state.cam_setup, "isValid", True):
            try:
                _ = runtime_state.cam_setup.name
                _ = runtime_state.cam_setup.workCoordinateSystem
                if runtime_state.cam_obj:
                    _ = runtime_state.cam_setup.parent
                is_setup_valid = True
            except Exception:
                is_setup_valid = False

        pinned_name = (getattr(runtime_state, "pending_setup_name", "") or "").strip()
        if pinned_name and is_setup_valid and runtime_state.cam_setup:
            try:
                if runtime_state.cam_setup.name != pinned_name:
                    is_setup_valid = False
            except Exception:
                is_setup_valid = False

        if not is_setup_valid:
            runtime_state.cam_setup = None
            if runtime_state.cam_obj and runtime_state.cam_obj.setups.count > 0:
                if pinned_name:
                    target = _find_setup_by_name(runtime_state.cam_obj, pinned_name)
                    if target:
                        try:
                            _ = target.workCoordinateSystem
                            runtime_state.cam_setup = target
                        except Exception:
                            runtime_state.cam_setup = None
                if not runtime_state.cam_setup:
                    active_s = None
                    for i in range(runtime_state.cam_obj.setups.count):
                        s = runtime_state.cam_obj.setups.item(i)
                        try:
                            if s and getattr(s, "isValid", True) and s.isActive:
                                _ = s.name
                                _ = s.workCoordinateSystem
                                active_s = s
                                break
                        except Exception:
                            pass
                    if active_s:
                        runtime_state.cam_setup = active_s
                    else:
                        try:
                            first_s = runtime_state.cam_obj.setups.item(0)
                            _ = first_s.name
                            _ = first_s.workCoordinateSystem
                            runtime_state.cam_setup = first_s
                        except Exception:
                            pass
    except Exception as ex:
        _send_diag_log(f"[refs] 刷新引用失敗: {ex}")

    final_design_valid = False
    if runtime_state.des_obj and getattr(runtime_state.des_obj, "isValid", True):
        try:
            _ = runtime_state.des_obj.rootComponent
            final_design_valid = True
        except Exception:
            pass

    final_setup_valid = False
    if runtime_state.cam_setup and getattr(runtime_state.cam_setup, "isValid", True):
        try:
            _ = runtime_state.cam_setup.name
            _ = runtime_state.cam_setup.workCoordinateSystem
            final_setup_valid = True
        except Exception:
            pass

    try:
        from smart_ai_cam_templates.template_service import ensure_tmpl_lib
        ensure_tmpl_lib()
    except Exception:
        pass

    return final_design_valid and final_setup_valid

def _migrate_runtime_state_fields():
    """Fusion 升級至新版 state 庫，備用擴充。"""
    try:
        if not hasattr(runtime_state, "slot_debug_enabled"):
            setattr(runtime_state, "slot_debug_enabled", False)
        if not hasattr(runtime_state, "vision_mode"):
            setattr(runtime_state, "vision_mode", "FAST_2D")
        if not hasattr(runtime_state, "vision_snapshot"):
            setattr(runtime_state, "vision_snapshot", None)
        if not hasattr(runtime_state, "last_hole_scan_rows_raw"):
            setattr(runtime_state, "last_hole_scan_rows_raw", [])
        if not hasattr(runtime_state, "feature_catalog"):
            setattr(runtime_state, "feature_catalog", None)
        if not hasattr(runtime_state, "last_ai_plan"):
            setattr(runtime_state, "last_ai_plan", None)
        if not hasattr(runtime_state, "contour_2d_recognition"):
            setattr(runtime_state, "contour_2d_recognition", None)
        if not hasattr(runtime_state, "fusion_official_recognition"):
            setattr(runtime_state, "fusion_official_recognition", None)
        if not hasattr(runtime_state, "official_pocket_panel_rows"):
            setattr(runtime_state, "official_pocket_panel_rows", [])
    except Exception:
        pass


def _refresh_fusion_official_recognition():
    """Fusion RecognizedHoleGroup + RecognizedPocket (+ design HoleFeature threads)."""
    des_obj, camSetup, _, _ = _fusion_refs()
    if not des_obj or not camSetup:
        runtime_state.fusion_official_recognition = None
        runtime_state.official_pocket_panel_rows = []
        return
    try:
        from Smart_AI.perception import fusion_official_recognition as fr
    except ImportError:
        runtime_state.fusion_official_recognition = {"ok": False, "reason": "import_failed"}
        runtime_state.official_pocket_panel_rows = []
        return
    try:
        rec = fr.run_official_recognition(design=des_obj, setup=camSetup)
    except Exception as ex:
        runtime_state.fusion_official_recognition = {
            "ok": False,
            "reason": "official_recognition_failed: {}".format(ex),
        }
        runtime_state.official_pocket_panel_rows = []
        try:
            _send_diag_log("[fusion-official] 跳過官方辨識: {}".format(ex))
        except Exception:
            pass
        return
    runtime_state.fusion_official_recognition = rec
    brep_slot_n = len(getattr(runtime_state, "slotInfoList", None) or [])
    panel_rows = []
    slot_n = 0
    pocket_n = 0
    for i, p in enumerate(rec.get("pockets") or []):
        if not isinstance(p, dict):
            continue
        kind = str(p.get("pocket_kind", "pocket") or "pocket").strip().lower()
        if kind not in ("slot", "pocket"):
            kind = "pocket"
        # B-rep 腰形槽掃描為 0 時，不把官方結果當長條孔（避免矩形口袋誤入長條欄）
        if kind == "slot" and brep_slot_n == 0:
            kind = "pocket"
            p = dict(p)
            p["pocket_kind"] = "pocket"
        if kind == "slot":
            slot_n += 1
            label = "官方長條 #{}".format(slot_n)
        else:
            pocket_n += 1
            label = "官方口袋 #{}".format(pocket_n)
        panel_rows.append(
            {
                "index": i,
                "body_token": str(p.get("body_token", "") or ""),
                "pocket_index": int(p.get("pocket_index", 0) or 0),
                "through": bool(p.get("is_through", False)),
                "is_closed": bool(p.get("is_closed", True)),
                "boundary_count": int(p.get("boundary_count", 0) or 0),
                "pocket_kind": kind,
                "width_mm": p.get("width_mm"),
                "length_mm": p.get("length_mm"),
                "depth_mm": p.get("depth_mm"),
                "source": "RecognizedPocket",
                "label": label,
            }
        )
    runtime_state.official_pocket_panel_rows = panel_rows
    excluded = int(rec.get("pockets_excluded_as_holes", 0) or 0)
    if excluded > 0 and not panel_rows:
        try:
            _send_diag_log(
                "[official-pocket] Fusion 回傳 {} 筆已過濾（圓孔/通孔誤判為口袋，本零件無口袋槽）"
                .format(excluded)
            )
        except Exception:
            pass
    elif brep_slot_n == 0 and slot_n == 0 and pocket_n > 0:
        try:
            _send_diag_log(
                "[official-pocket] B-rep 長條槽=0：{} 筆 RecognizedPocket 歸入口袋槽欄"
                .format(pocket_n)
            )
        except Exception:
            pass


def _resolve_body_from_entity_token(design, token):
    tok = str(token or "").strip()
    if not tok or not design:
        return None
    try:
        scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
        if scan_bodies is not None:
            for entry in scan_bodies:
                b = entry["body"]
                if str(entry["token"] or "") == tok:
                    return b
        else:
            for comp in design.allComponents:
                for bi in range(comp.bRepBodies.count):
                    b = comp.bRepBodies.item(bi)
                    try:
                        if str(b.entityToken or "") == tok:
                            return b
                    except Exception:
                        pass
    except Exception:
        pass
    return None


def auto_detect_machining_base(design, setup) -> dict | None:
    """
    自動偵測零件基準台面 (Base Face)。
    尋找平行於 WCS Z 軸、Z 高度最低且面積最大的面，並計算 XY 幾何中心與安全防撞退刀高度。
    """
    if not design or not setup:
        return None
    try:
        from vision.snapshot import _get_setup_target_bodies
        bodies = _get_setup_target_bodies(setup, design.rootComponent)
    except Exception:
        bodies = []
        try:
            for comp in design.allComponents:
                for bi in range(comp.bRepBodies.count):
                    b = comp.bRepBodies.item(bi)
                    if b and b.isVisible:
                        bodies.append(b)
        except Exception:
            pass

    if not bodies:
        return None

    try:
        wcs = setup.workCoordinateSystem
        origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()
        
        planar_faces = []
        max_model_z = -9999.0
        
        for body in bodies:
            for fi in range(body.faces.count):
                face = body.faces.item(fi)
                try:
                    # 計算此面片在 WCS 投影下的 Z 軸範圍，找出最高點用於計算退刀安全高度
                    bb = face.boundingBox
                    pmin, pmax = _bbox_proj_min_max(bb, z_axis)
                    pmax_mm = pmax * 10.0
                    if pmax_mm > max_model_z:
                        max_model_z = pmax_mm
                        
                    geom = face.geometry
                    if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                        continue
                        
                    # 檢測平面是否平行於 WCS XY 面 (即法向平行於 Z 軸)
                    normal = adsk.core.Plane.cast(geom).normal
                    ndot = abs(normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z)
                    if ndot > 0.98:  # 高度垂直於 Z 軸
                        area = face.area * 100.0  # 轉為 mm2
                        planar_faces.append({
                            "face": face,
                            "area_mm2": area,
                            "min_z_mm": pmin * 10.0,
                            "max_z_mm": pmax_mm,
                            "normal_dot": ndot
                        })
                except Exception:
                    continue

        if not planar_faces:
            return None

        # 排序基準：Z 高度越低越優先；同高度下，面積越大越優先
        # 容許 0.5mm 高度差內以面積大者優先
        planar_faces.sort(key=lambda x: (round(x["min_z_mm"] / 0.5) * 0.5, -x["area_mm2"]))
        best = planar_faces[0]
        
        # 計算基準面中心
        bb = best["face"].boundingBox
        pt = adsk.core.Point3D.create(
            (bb.minPoint.x + bb.maxPoint.x) / 2.0,
            (bb.minPoint.y + bb.maxPoint.y) / 2.0,
            (bb.minPoint.z + bb.maxPoint.z) / 2.0
        )
        dx, dy = pt.x - origin.x, pt.y - origin.y
        base_cx = (dx * x_axis.x + dy * x_axis.y) * 10.0
        base_cy = (dx * y_axis.x + dy * y_axis.y) * 10.0
        
        safety_height = max_model_z + 10.0  # 最高點再退避 10mm
        
        return {
            "base_z_height_mm": round(best["min_z_mm"], 3),
            "base_center_x": round(base_cx, 3),
            "base_center_y": round(base_cy, 3),
            "safety_height_mm": round(safety_height, 3),
            "area_mm2": round(best["area_mm2"], 1),
            "face_token": best["face"].entityToken if hasattr(best["face"], "entityToken") else ""
        }
    except Exception as ex:
        _send_diag_log(f"[base-detection] auto_detect_machining_base failed: {ex}")
        return None



def _buildOfficialPocketDropLists(mat="AL6061"):
    """長條孔模板庫全列於 2D／3D 下拉（店內 pocket2d／adaptive 命名不一，由操作者指定）。"""
    drop2d = [{"label": "(不使用)", "slotUrl": "", "mode": "不使用"}]
    drop3d = [{"label": "(不使用)", "slotUrl": "", "mode": "不使用"}]
    for x in allSlotMap.get(mat, []) or []:
        nm = str(x.get("name", "") or "")
        su = str(_template_cache_key(x.get("url"), "") or "").strip()
        if not su:
            continue
        it = {"label": nm, "slotUrl": su, "mode": "模板"}
        drop2d.append(it)
        drop3d.append(it)
    return drop2d, drop3d


def _official_pocket_rows_for_kind(kind: str):
    want = str(kind or "").strip().lower()
    rows = list(getattr(runtime_state, "official_pocket_panel_rows", None) or [])
    return [r for r in rows if str(r.get("pocket_kind", "pocket") or "pocket").lower() == want]


def _format_official_pocket_spec(r: dict) -> str:
    kind = str(r.get("pocket_kind", "") or "")
    w = r.get("width_mm")
    ln = r.get("length_mm")
    parts = []
    if kind == "slot":
        if w is not None and ln is not None:
            parts.append("W{:.3f}×L{:.3f}".format(float(w), float(ln)))
        elif w is not None:
            parts.append("W{:.3f}".format(float(w)))
    if r.get("depth_mm") is not None:
        parts.append("Z{:.3f}".format(float(r.get("depth_mm"))))
    if r.get("boundary_count") is not None:
        parts.append("邊界{}".format(int(r.get("boundary_count") or 0)))
    return " · ".join(parts) if parts else "—"


def _buildOfficialPocketDataForKind(mat="AL6061", kind="pocket"):
    rows = _official_pocket_rows_for_kind(kind)
    if not rows:
        return []
    drop2d, drop3d = _buildOfficialPocketDropLists(mat)
    bind_modes = [
        {"value": "auto", "label": "自動"},
        {"value": "2d_only", "label": "僅2D"},
        {"value": "3d_only", "label": "僅3D"},
        {"value": "2d_then_3d", "label": "2D→3D"},
    ]
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "index": i,
                "panel_row_index": int(r.get("index", i)),
                "label": r.get("label", "Fusion 口袋"),
                "spec": _format_official_pocket_spec(r),
                "body_token": str(r.get("body_token", "") or ""),
                "pocket_index": int(r.get("pocket_index", 0) or 0),
                "through": bool(r.get("through", False)),
                "is_closed": bool(r.get("is_closed", True)),
                "boundary_count": int(r.get("boundary_count", 0) or 0),
                "pocket_kind": str(r.get("pocket_kind", kind) or kind),
                "width_mm": r.get("width_mm"),
                "length_mm": r.get("length_mm"),
                "depth_mm": r.get("depth_mm"),
                "dropItems2d": drop2d,
                "dropItems3d": drop3d,
                "bindModes": bind_modes,
                "bindMode": "auto",
                "tmpl2dIdx": 0,
                "tmpl3dIdx": 0,
            }
        )
    return out


def _buildOfficialPocketData(mat="AL6061"):
    """向後相容：合併官方長條孔 + 官方口袋槽。"""
    return _buildOfficialPocketDataForKind(mat, "slot") + _buildOfficialPocketDataForKind(
        mat, "pocket"
    )


def _buildOfficialSlotPocketData(mat="AL6061"):
    return _buildOfficialPocketDataForKind(mat, "slot")


def _buildOfficialPocketSlotData(mat="AL6061"):
    return _buildOfficialPocketDataForKind(mat, "pocket")


def _fusion_official_summary_for_init() -> dict:
    rec = getattr(runtime_state, "fusion_official_recognition", None) or {}
    pockets = rec.get("pockets") or []
    slot_n = sum(
        1 for p in pockets if str(p.get("pocket_kind", "")).lower() == "slot"
    )
    pocket_n = sum(
        1 for p in pockets if str(p.get("pocket_kind", "pocket")).lower() == "pocket"
    )
    return {
        "ok": bool(rec.get("ok")),
        "reason": str(rec.get("reason", "")),
        "hole_group_count": len(rec.get("hole_groups") or []),
        "pocket_count": len(pockets),
        "pockets_excluded_as_holes": int(rec.get("pockets_excluded_as_holes", 0) or 0),
        "official_slot_count": slot_n,
        "official_pocket_slot_count": pocket_n,
        "thread_feature_count": len(rec.get("design_threads") or []),
    }


def _executeOfficialPocketRows(
    payload_rows,
    ui_rows,
    material,
    done,
    all_new_ops,
    op_clone_cache,
    clone_stats,
    perf_stats,
):
    """Fusion RecognizedPocket → 2D 邊鏈／3D 底面；執行期重新 recognizePockets。"""
    des_obj, camSetup, _, tmplLib = _fusion_refs()
    if not payload_rows or not tmplLib or not camSetup or not des_obj:
        return
    try:
        from Smart_AI.perception.official_pocket_execute import (
            get_recognized_pocket_by_index,
            resolve_pocket_geometry,
            infer_bind_mode,
        )
    except ImportError:
        from .Smart_AI.perception.official_pocket_execute import (
            get_recognized_pocket_by_index,
            resolve_pocket_geometry,
            infer_bind_mode,
        )

    def _resolve_ui_row(prow):
        pri = prow.get("panel_row_index")
        if pri is not None:
            try:
                key = int(pri)
                for ur in ui_rows:
                    if int(ur.get("panel_row_index", -2)) == key:
                        return ur
            except Exception:
                pass
        si = int(prow.get("idx", -1))
        if 0 <= si < len(ui_rows):
            return ui_rows[si]
        return None

    for prow in payload_rows:
        ui_row = _resolve_ui_row(prow)
        if not ui_row:
            continue
        si = int(prow.get("idx", 0))
        body_token = str(prow.get("body_token") or ui_row.get("body_token") or "")
        pocket_index = int(prow.get("pocket_index", ui_row.get("pocket_index", 0)) or 0)
        bind_mode = str(prow.get("bindMode") or ui_row.get("bindMode") or "auto")
        tmpl2d_idx = int(prow.get("tmpl2dIdx", ui_row.get("tmpl2dIdx", 0)) or 0)
        tmpl3d_idx = int(prow.get("tmpl3dIdx", ui_row.get("tmpl3dIdx", 0)) or 0)
        drop2d = ui_row.get("dropItems2d") or []
        drop3d = ui_row.get("dropItems3d") or []
        ch2d = drop2d[tmpl2d_idx] if 0 <= tmpl2d_idx < len(drop2d) else {}
        ch3d = drop3d[tmpl3d_idx] if 0 <= tmpl3d_idx < len(drop3d) else {}
        url2d = str(ch2d.get("slotUrl", "") or "").strip()
        url3d = str(ch3d.get("slotUrl", "") or "").strip()
        if not url2d and not url3d:
            continue
        body = _resolve_body_from_entity_token(des_obj, body_token)
        if not body:
            done.append(f"⚠️ 官方口袋列{si + 1}: 找不到實體（body_token），略過")
            continue
        pocket = get_recognized_pocket_by_index(des_obj, camSetup, body, pocket_index)
        if not pocket:
            done.append(
                f"⚠️ 官方口袋列{si + 1}: recognizePockets 無索引 {pocket_index}（請重掃），略過"
            )
            continue
        geom = resolve_pocket_geometry(pocket, camSetup)
        chains = geom.get("chain_profiles") or []
        bottoms = list(geom.get("bottom_faces") or [])
        pocket_through = bool(geom.get("is_through", False))
        depth_mm = None
        if not pocket_through:
            try:
                depth_mm = round(float(pocket.depth) * 10.0, 3)
            except Exception:
                depth_mm = None
        mode = infer_bind_mode(
            geom,
            user_mode=bind_mode,
            has_2d_url=bool(url2d),
            has_3d_url=bool(url3d),
        )
        steps = []
        if mode == "2d_only" and url2d:
            steps.append(("2d", url2d))
        elif mode == "3d_only" and url3d:
            steps.append(("3d", url3d))
        elif mode == "2d_then_3d":
            if url2d:
                steps.append(("2d", url2d))
            if url3d:
                steps.append(("3d", url3d))
        else:
            if url2d:
                steps.append(("2d", url2d))
            elif url3d:
                steps.append(("3d", url3d))

        for step_kind, url_key in steps:
            lib_url = _slot_palette_url_key_to_library_url(material, url_key, False)
            if not lib_url:
                done.append(f"⚠️ 官方口袋列{si + 1}: 模板無法載入（{step_kind}）")
                continue
            _record_template_name(lib_url, "")
            _tu = time.perf_counter()
            tmpl = tmplLib.templateAtURL(lib_url) if tmplLib else None
            perf_stats["template_at_url_s"] += time.perf_counter() - _tu
            if not tmpl:
                done.append(f"⚠️ 官方口袋列{si + 1}: templateAtURL 失敗（{step_kind}）")
                continue
            if step_kind == "2d":
                if not chains or not any(len(c) >= 2 for c in chains):
                    done.append(
                        f"⚠️ 官方口袋列{si + 1}: 無可用邊鏈（edges={geom.get('edge_count', 0)}），2D 略過"
                    )
                    continue
                new_ops = _createOpFromTemplate(
                    camSetup,
                    tmpl,
                    [],
                    isThrough=pocket_through,
                    holeDepthMM=(None if pocket_through else depth_mm),
                    template_url=f"{camSetup.name}|official-pocket-2d|{_template_cache_key(lib_url, str(si))}",
                    clone_cache=op_clone_cache,
                    clone_stats=clone_stats,
                    bind_all_faces=False,
                    select_same_diameter=False,
                    slot_profile_edges=None,
                    perf_stats=perf_stats,
                    slot_chain_profiles=chains,
                    slot_chain_token_profiles=None,
                    slot_chains_only=True,
                    slot_chain_reverse_order=(
                        SLOT_POCKET_TOOLPATH_INSIDE_SLOT and SLOT_CHAIN_REVERSE_FOR_INTERIOR
                    ),
                )
                tag = "2D"
            else:
                bind_faces = bottoms if bottoms else []
                if not bind_faces:
                    walls = list(geom.get("wall_faces") or [])
                    bind_faces = walls[:1] if walls else []
                if not bind_faces:
                    done.append(f"⚠️ 官方口袋列{si + 1}: 無底面／側壁可綁 3D，略過")
                    continue
                new_ops = _createOpFromTemplate(
                    camSetup,
                    tmpl,
                    bind_faces,
                    isThrough=pocket_through,
                    holeDepthMM=(None if pocket_through else depth_mm),
                    template_url=f"{camSetup.name}|official-pocket-3d|{_template_cache_key(lib_url, str(si))}",
                    clone_cache=op_clone_cache,
                    clone_stats=clone_stats,
                    bind_all_faces=True,
                    select_same_diameter=False,
                    perf_stats=perf_stats,
                )
                tag = "3D"
            if new_ops:
                all_new_ops.extend(new_ops)
                done.append(
                    f"官方口袋列{si + 1}（{mode}/{tag}）: 已建立 {len(new_ops)} 道"
                )
            else:
                done.append(f"⚠️ 官方口袋列{si + 1}（{tag}）: 模板未產生工序")




def _refresh_contour_2d_recognition():
    """Top face + outer contour recognition for 2D template row (read-only)."""
    refresh_fn = getattr(runtime_state, "refresh_vision_snapshot_fn", None)
    if callable(refresh_fn):
        try:
            refresh_fn()
        except Exception:
            pass
    des_obj, camSetup, _, _ = _fusion_refs()
    if not des_obj or not camSetup:
        runtime_state.contour_2d_recognition = None
        return
    try:
        from Smart_AI.perception import contour_2d_recognizer as c2d
    except ImportError:
        runtime_state.contour_2d_recognition = None
        return
    mat = getattr(runtime_state, "current_material", "AL6061")
    setup_name = ""
    try:
        setup_name = camSetup.name
    except Exception:
        pass
    tf_rough = [x.get("name", x) if isinstance(x, dict) else x for x in allTopFaceRoughMap.get(mat, [])]
    tf_finish = [x.get("name", x) if isinstance(x, dict) else x for x in allTopFaceFinishMap.get(mat, [])]
    pf_rough = [x.get("name", x) if isinstance(x, dict) else x for x in allProfileRoughMap.get(mat, [])]
    pf_finish = [x.get("name", x) if isinstance(x, dict) else x for x in allProfileFinishMap.get(mat, [])]
    runtime_state.contour_2d_recognition = c2d.build_contour_2d_recognition(
        flat_depths=_scanFlatDepths(),
        vision_snapshot=getattr(runtime_state, "vision_snapshot", None),
        feature_catalog=getattr(runtime_state, "feature_catalog", None),
        top_face_rough_names=tf_rough,
        top_face_finish_names=tf_finish,
        profile_rough_names=pf_rough,
        profile_finish_names=pf_finish,
        material=mat,
        setup_name=setup_name,
    )
def _refresh_feature_catalog():
    """Unified B-rep → CAM feature catalog (read-only, post scan)."""
    des_obj, camSetup, _, _ = _fusion_refs()
    if not des_obj or not camSetup:
        runtime_state.feature_catalog = None
        return
    try:
        from Smart_AI.reasoning import machining_feature_catalog as mfc
    except ImportError:
        runtime_state.feature_catalog = None
        return
    mat = getattr(runtime_state, "current_material", "AL6061")
    try:
        # 1. 零件基準台自動幾何定位 (Auto Machining Base Detection)
        try:
            base_info = auto_detect_machining_base(des_obj, camSetup)
            setattr(runtime_state, "machining_base_info", base_info)
            if base_info:
                _send_diag_log("[base-detection] 成功定位基準面：Z={:.3f} mm, 安全防撞高度: {:.3f} mm".format(
                    base_info["base_z_height_mm"], base_info["safety_height_mm"]
                ))
        except Exception as _bex:
            _send_diag_log("[base-detection] 基準台定位異常: {}".format(_bex))

        # Run the feature collaboration pipeline first!
        try:
            from Smart_AI.perception.feature_collaboration import FeatureCollaborationManager
            holes_raw = list(getattr(runtime_state, "holeInfoList", []) or [])
            slots_raw = list(getattr(runtime_state, "slotInfoList", []) or [])
            flat_depths = _scanFlatDepths()
            official_pockets = _buildOfficialPocketData(mat)
            
            collab = FeatureCollaborationManager(
                holes=holes_raw,
                slots=slots_raw,
                official_pockets=official_pockets,
                flat_depths=flat_depths,
                design=des_obj,
                setup=camSetup
            )
            collab_result = collab.execute_collaboration_pipeline()
            
            # Write back the enriched and calibrated features
            runtime_state.holeInfoList = collab_result["holes"]
            runtime_state.slotInfoList = collab_result["slots"]
            runtime_state.machining_dependencies = collab_result["dependencies"]
            
            _send_diag_log("[feature_collaboration] 協同處理完成：嵌套孔校正數: {}, 去重槽數: {}, 依賴關係長度: {}".format(
                sum(1 for h in collab_result["holes"] if "nested_in" in h),
                len(slots_raw) - len(collab_result["slots"]),
                len(collab_result["dependencies"])
            ))
        except Exception as _cex:
            _send_diag_log("[feature_collaboration] 協同處理發生異常: {}".format(_cex))

        runtime_state.feature_catalog = mfc.build_feature_catalog(
            design=des_obj,
            setup=camSetup,
            holes=_buildHoleData(mat),
            slots=_buildSlotData(mat),
            pocket_corner_r=_buildPocketCornerRData(mat),
            flat_depths=_scanFlatDepths(),
            vision_snapshot=getattr(runtime_state, "vision_snapshot", None),
            fusion_recognition=getattr(runtime_state, "fusion_official_recognition", None),
        )
    except Exception as ex:
        runtime_state.feature_catalog = {
            "ok": False,
            "reason": "feature_catalog_failed: {}".format(ex),
            "feature_count": 0,
        }
        _send_diag_log("[feature_catalog] refresh failed: {}".format(ex))


def _refresh_vision_snapshot():
    """Build read-only vision snapshot after hole/slot scan (eye layer)."""
    des_obj, camSetup, _, _ = _fusion_refs()
    _holes = list(
        getattr(runtime_state, 'holeInfoList', None) or holeInfoList or []
    )
    _slots = list(
        getattr(runtime_state, 'slotInfoList', None) or slotInfoList or []
    )
    if not ENABLE_VISION_LAYER or not des_obj or not camSetup:
        runtime_state.vision_snapshot = None
        return
    try:
        import importlib
        import sys

        for _m in (
            "smart_ai_cam_vision.snapshot",
            "smart_ai_cam_vision",
        ):
            if _m in sys.modules:
                try:
                    importlib.reload(sys.modules[_m])
                except Exception:
                    pass

        from smart_ai_cam_vision import build_part_vision_snapshot

        runtime_state.vision_snapshot = build_part_vision_snapshot(
            design=des_obj,
            setup=camSetup,
            vision_mode=getattr(runtime_state, "vision_mode", "FAST_2D"),
            holes_rows=getattr(runtime_state, "last_hole_scan_rows_raw", None)
            or runtime_state.last_hole_scan_rows_debug,
            slot_info_list=_slots,
            hole_list_count=len(_holes),
        )
    except Exception as ex:
        runtime_state.vision_snapshot = {
            "ok": False,
            "reason": "vision_refresh_failed: {}".format(ex),
            "vision_mode": getattr(runtime_state, "vision_mode", "FAST_2D"),
        }
        _send_diag_log("[vision] refresh failed: {}".format(ex))


def _bind_vision_refresh_hook():
    """Avoid PaletteActionContext schema churn; palette reads this from runtime_state."""
    try:
        runtime_state.refresh_vision_snapshot_fn = _refresh_vision_snapshot
    except Exception:
        pass


def _send_vision_sketch_palette_result(result):
    """Push vision sketch draw result to palette HTML (no PaletteActionContext)."""
    import json

    global _palette
    level = "ok" if result.get("ok") else "err"
    msg = str(result.get("message", "") or "")
    if result.get("ok"):
        msg = "{} — {}".format(result.get("sketch_name", "草圖"), msg)
    status_payload = json.dumps({"msg": msg, "level": level}, ensure_ascii=False)
    payload = json.dumps(result, ensure_ascii=False)
    pal = _palette
    if not pal:
        try:
            from smart_ai_cam_ui.diagnostics import get_main_palette
            pal = get_main_palette()
        except Exception:
            pass
    if not pal:
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            pal = ui.palettes.itemById("holeProcessPalette")
        except Exception:
            pal = None
    if pal:
        try:
            pal.sendInfoToHTML("status", status_payload)
            pal.sendInfoToHTML("recognition_sketch_result", payload)
        except Exception:
            pass
    try:
        adsk.doEvents()
    except Exception:
        pass


def _handle_draw_vision_sketch_palette():
    """Draw SemiAuto_VisionSketch from vision_snapshot; always reply to HTML."""
    global _isExecutingPalette

    des_obj, camSetup, _, _ = _fusion_refs()

    if _isExecutingPalette:
        _send_vision_sketch_palette_result(
            {"ok": False, "message": "執行加工中，請稍後再繪製", "sketch_name": ""}
        )
        return
    result = {"ok": False, "message": "unknown", "sketch_name": ""}
    try:
        refresh_fn = getattr(runtime_state, "refresh_vision_snapshot_fn", None)
        if callable(refresh_fn):
            refresh_fn()
        import importlib
        import sys

        for _m in [
            "Smart_AI.perception.contour_recognizer",
            "smart_ai_cam_vision.snapshot",
            "smart_ai_cam_vision.assist_sketch",
            "vision"
        ]:
            if _m in sys.modules:
                try:
                    importlib.reload(sys.modules[_m])
                except Exception:
                    pass

        from smart_ai_cam_vision.assist_sketch import create_recognition_sketch_from_vision

        snap = getattr(runtime_state, "vision_snapshot", None)
        feats = (snap or {}).get("recognized_features") or {}
        if not snap or not snap.get("ok") or not feats.get("hole_instances"):
            result = {
                "ok": False,
                "message": "視線法快照無效或缺少孔實例，請先按「重新掃描」",
                "sketch_name": "",
            }
        else:
            result = create_recognition_sketch_from_vision(snap, setup=camSetup)
    except Exception as ex:
        import traceback

        result = {
            "ok": False,
            "message": str(ex),
            "sketch_name": "",
            "trace": traceback.format_exc()[-600:],
        }
    try:
        _send_diag_log(
            "[vision-sketch] ok={} {}".format(result.get("ok"), result.get("message", ""))
        )
    except Exception:
        pass
    _send_vision_sketch_palette_result(result)


_migrate_runtime_state_fields()
_bind_vision_refresh_hook()

# 外掛版本：與 manifest / palette.html 顯示一致；規則見 docs/VERSIONING.md、docs/版本紀錄.md；開發日誌見 docs/開發對話與變更.md。
# 顯示 V{整數}.{四位小數}（例 V1.0307）。辨識擴展 +0.01、細修 +0.0001；新增一整條模板+刀路族時數值 +1.0（例 V1.0310→V2.0310，累加不覆蓋小數段，見 docs/VERSIONING.md §1）。
ADDIN_VERSION = 'V2.0358'  # V2.0357 +0.0001 L2 加深（驗證／孔指紋／劇本持久化）；見 docs/版本紀錄.md

handlers = []
holeInfoList = []
slotInfoList = []
pocketCornerRInfoList = []

class DynamicMapProxy(object):
    def __init__(self, name):
        self._name = name
    def get(self, key, default=None):
        m = getattr(runtime_state, self._name, {})
        return m.get(key, default)
    def keys(self):
        m = getattr(runtime_state, self._name, {})
        return m.keys()
    def __getitem__(self, key):
        m = getattr(runtime_state, self._name, {})
        return m[key]
    def __contains__(self, key):
        m = getattr(runtime_state, self._name, {})
        return key in m
    def __len__(self):
        m = getattr(runtime_state, self._name, {})
        return len(m)
    def __bool__(self):
        m = getattr(runtime_state, self._name, {})
        return bool(m)

allDrillMap = DynamicMapProxy('allDrillMap')
allChamferMap = DynamicMapProxy('allChamferMap')
allCountersinkMap = DynamicMapProxy('allCountersinkMap')
allSlotMap = DynamicMapProxy('allSlotMap')
allSlotChamferMap = DynamicMapProxy('allSlotChamferMap')
allTopFaceMap = DynamicMapProxy('allTopFaceMap')
allProfileMap = DynamicMapProxy('allProfileMap')
allTopFaceRoughMap = DynamicMapProxy('allTopFaceRoughMap')
allTopFaceFinishMap = DynamicMapProxy('allTopFaceFinishMap')
allProfileRoughMap = DynamicMapProxy('allProfileRoughMap')
allProfileFinishMap = DynamicMapProxy('allProfileFinishMap')
bodyZRange_ref = {}
root_comp_ref = None
_palette = None
_diag_palette = None
_isExecutingPalette = False
# 射線法設定（mm）。None 表示自動；有值時代表「射線直徑比孔徑小多少」。
_hole_recognizer_mod = None
_hole_recognizer_error = ''
_slot_recognizer_mod = None
_slot_recognizer_error = ''
_slot_ui_logic_rev = 'slot-ui-v3-recognizer-dedup-faces'
FIXED_PALETTE_WIDTH = 1280
# 全局 moveAfter 排序（依 getToolOrder）；每次面板執行結束後執行。工序極多時較慢，改 False 可略過。
ENABLE_GLOBAL_OP_REORDER_ON_EXECUTE = True
AUTO_GENERATE_TOOLPATH_ON_EXECUTE = True
REUSE_EXISTING_TEMPLATE_OPS = True
# True＝鑽孔工序在 createFromCAMTemplate 之後，再從本機 SG/HSS/鑽頭 庫掃描並嘗試換「同徑（±0.05mm）」庫刀。
# False＝一律保留模板內定刀具（模板已固定刀號／刀庫引用時建議關閉）。
ENABLE_DRILL_LIBRARY_TOOL_MATCH = False
# ---------------------------------------------------------------------------
# 長條孔：目標為 **刀路在槽內挖料**（清角箭頭朝槽內、不啃外側大面）。
# False＝槽列仍建工序，但不再強制邊序／compensation（交還模板預設）。
# ---------------------------------------------------------------------------
SLOT_POCKET_TOOLPATH_INSIDE_SLOT = True
# 長條孔 ChainSelection：內環 coEdge 順序寫入後，CAM 對「加工側」解讀依版本而異。
# 僅在 SLOT_POCKET_TOOLPATH_INSIDE_SLOT 為真時，會與 execute 一併啟用。
SLOT_CHAIN_REVERSE_FOR_INTERIOR = True
# 長條孔 pocket2d：綁定邊鏈後覆寫 compensation。空字串 ''＝不覆寫。
# Fusion 實測：同模型內環 coEdge 順序下 **'left' 易穩定出刀路**；'right' 常需搭配邊鏈反轉。
SLOT_POCKET_COMPENSATION_OVERRIDE = "'left'"
# True＝依邊鏈有號面積（內環空腔）對表 B-rep→CAM，每條 ChainSelection 動態選 'left'／'right'（見 _resolve_slot_pocket_compensation_slug）。
# False＝一律使用 SLOT_POCKET_COMPENSATION_OVERRIDE（向後相容）。
SLOT_POCKET_COMPENSATION_AUTO = True
# True＝腰形槽 pocket2d 優先用 **2D 叉積**：兩弧圓心中點 vs「封閉鏈走訪方向」上最長邊段（直邊）之方向（Setup XY 平面）。
# cross≤0（槽心在行進方向右側或與最長直邊之幾何關係為此符號）→'left'，否則 'right'；避免全落在 'right' 觸發 SLOT_POCKET_INVERT_CHAIN_WHEN_COMP_RIGHT 把 bucket-xor 整列翻掉。
# 不用 edge.start/end 當行進方向（未必等於 coEdge 走向）。失敗時再退回 HOST_FACE_VS_Z／Shoelace。設 False 可關閉。
SLOT_POCKET_COMPENSATION_2D_ARC_CROSS = True
# True＝上列叉積得到之 'left'/'right' 再對調（除錯用；幾何正確仍與模板預期相反時改）。
SLOT_POCKET_COMPENSATION_2D_CROSS_INVERT = False
# True＝自動補償時以辨識槽心 (cx_mm,cy_mm) 與開口 Z 為參考：內環空腔時槽心應落在邊鏈 UV 多邊形內，否則反號有號面積再對表。
SLOT_POCKET_USE_SCAN_CENTER_FOR_COMP = True
# True＝有宿主開口面（host_opening_face／opening_face）且為平面內環時，pocket2d compensation **僅**依
# 「面法向·Setup WCS +Z」：dot>0→'left'，否則 'right'。跳過 Shoelace／槽心反號（同向多片開口面、
# coEdge 繞向與面片無關時仍一致）。|dot|<0.01 時退回下方 Shoelace 路徑。設 False 可恢復舊自動對表。
SLOT_POCKET_COMPENSATION_HOST_FACE_VS_Z = True
# 覆寫為 **right** 且向內模式開啟時，僅 pocket 邊鏈再反轉一次（與上一行反轉疊加），減輕 NoToolpath。
SLOT_POCKET_INVERT_CHAIN_WHEN_COMP_RIGHT = True
# 同列多槽：各槽內環 coEdge 在 Setup XY 投影之有號面積符號可能正負交錯，導致相同 compensation 卻一半朝外一半朝內。
# True＝以第一條鏈為基準，對符號相反者單獨反轉邊序再綁 ChainSelection。
SLOT_ALIGN_MULTI_CHAIN_WINDING = True
# True＝繞向對齊改為「依各槽開口面分桶」：桶內用該開口平面 UV 之有號面積對齊；桶間再以首桶平面為共用基底比對首鏈，必要時整桶反轉。
# 修正多腰孔落在兩張以上平行開口面時，僅用 Setup XY 會全為同號、卻 pocket 一半朝外一半朝內的情況。
SLOT_ALIGN_WINDING_USE_OPENING_FACE = True
# ---------------------------------------------------------------------------
# 2D 輪廓 · 內輪廓加工（pocket2d／contour2d 等 CadContours2d 封閉鏈）
# 綁定完成後整批翻轉 isReverted：適用「刀具應在輪廓內側、模板／預設卻偏外」之系統性偏差。
# 長條孔 execute 路徑為首個落地處；往後其它「僅綁 2D 輪廓、且為內輪廓」的工序可沿用同一後處理。
# ---------------------------------------------------------------------------
CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND = True
# 相容舊名（與 CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND 為同一布林值）。
SLOT_FLIP_ALL_CHAIN_IS_REVERTED_AFTER_SLOT_BIND = CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND

# 視線法（RayVision 眼）：掃描後產生唯讀 vision_snapshot，不影響孔憲法 execute。
ENABLE_VISION_LAYER = True




def _load_local_recognizer_module(module_basename, required_attr, spec_label):
    """
    載入 hole_recognizer / slot_recognizer。
    Smart_AI_CAM：smart_ai_cam_recognizers/<name>.py
    舊版半自動：smart_ai_cam_recognizers/recognizers/<name>.py 或 add-in/recognizers/
    """
    errors = []
    pkg_name = 'Smart_AI.perception.%s' % module_basename
    try:
        mod = importlib.import_module(pkg_name)
        if hasattr(mod, required_attr):
            return mod
        errors.append('package import ok but %s missing on %s' % (required_attr, pkg_name))
    except Exception as e:
        errors.append('package import failed: %s' % e)

    addin_dir = os.path.dirname(os.path.abspath(__file__))
    addin_root = os.path.dirname(addin_dir)
    file_candidates = [
        os.path.join(addin_dir, '%s.py' % module_basename),
        os.path.join(addin_dir, 'recognizers', '%s.py' % module_basename),
        os.path.join(addin_root, 'recognizers', '%s.py' % module_basename),
    ]
    for mod_path in file_candidates:
        if not os.path.isfile(mod_path):
            errors.append('file not found: %s' % mod_path)
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                '%s_%s' % (spec_label, module_basename),
                mod_path,
            )
            if not spec or not spec.loader:
                errors.append('spec/loader unavailable: %s' % mod_path)
                continue
            mod_b = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod_b)
            if hasattr(mod_b, required_attr):
                return mod_b
            errors.append('file import ok but %s missing: %s' % (required_attr, mod_path))
        except Exception as e:
            errors.append('file import failed (%s): %s' % (mod_path, e))
    raise RuntimeError('; '.join(errors[-4:]))


def _get_hole_recognizer_module():
    """Load hole_recognizer (scan_holes_by_ray)."""
    global _hole_recognizer_mod, _hole_recognizer_error
    if _hole_recognizer_mod is not None:
        return _hole_recognizer_mod
    _hole_recognizer_error = ''
    try:
        _hole_recognizer_mod = _load_local_recognizer_module(
            'hole_recognizer', 'scan_holes_by_ray', 'smart_ai_cam_hole'
        )
        return _hole_recognizer_mod
    except Exception as e:
        _hole_recognizer_error = str(e)
        return None


def _get_slot_recognizer_module():
    """Load slot_recognizer (scan_slots)."""
    global _slot_recognizer_mod, _slot_recognizer_error
    if _slot_recognizer_mod is not None:
        return _slot_recognizer_mod
    _slot_recognizer_error = ''
    try:
        _slot_recognizer_mod = _load_local_recognizer_module(
            'slot_recognizer', 'scan_slots', 'smart_ai_cam_slot'
        )
        return _slot_recognizer_mod
    except Exception as e:
        _slot_recognizer_error = str(e)
        return None


def _calcDisplaySignature():
    """計算當前環境簽名，用於判斷是否需要重新掃描孔位。"""
    if not _validate_and_refresh_refs():
        return ''
    cam_setup = runtime_state.cam_setup
    des = runtime_state.des_obj
    if not cam_setup or not des:
        return ''
    try:
        wcs = cam_setup.workCoordinateSystem
        (origin, xAxis, yAxis, zAxis) = wcs.getAsCoordinateSystem()
        wcs_str = (
            f"{origin.x:.3f},{origin.y:.3f},{origin.z:.3f}|"
            f"{xAxis.x:.3f},{xAxis.y:.3f},{xAxis.z:.3f}|"
            f"{zAxis.x:.3f},{zAxis.y:.3f},{zAxis.z:.3f}"
        )
        body_count = 0
        for comp in des.allComponents:
            for i in range(comp.bRepBodies.count):
                body = comp.bRepBodies.item(i)
                if _isBodyVisible(body):
                    body_count += 1
        return f"{cam_setup.name}|{wcs_str}|bodies:{body_count}"
    except Exception:
        return ''


def _isBodyVisible(body):
    try:
        return bool(body.isVisible)
    except Exception:
        pass
    try:
        return bool(body.isLightBulbOn)
    except Exception:
        pass
    return True


def _countHoles(faces, origin, xAxis, yAxis, tol=0.05):
    """WCS XY 聚類計數（與 hole_recognizer._count_holes_faces 等價）。"""
    rec = _get_hole_recognizer_module()
    if rec and hasattr(rec, '_count_holes_faces'):
        try:
            return int(rec._count_holes_faces(faces, origin, xAxis, yAxis, tol))
        except Exception:
            pass
    seen = set()
    for f in faces or []:
        try:
            bb = f.boundingBox
            wx = (bb.minPoint.x + bb.maxPoint.x) / 2
            wy = (bb.minPoint.y + bb.maxPoint.y) / 2
            wz = (bb.minPoint.z + bb.maxPoint.z) / 2
            dx = wx - origin.x
            dy = wy - origin.y
            dz = wz - origin.z
            lx = dx * xAxis.x + dy * xAxis.y + dz * xAxis.z
            ly = dx * yAxis.x + dy * yAxis.y + dz * yAxis.z
            cx = round(round(lx / tol) * tol, 4)
            cy = round(round(ly / tol) * tol, 4)
            seen.add((cx, cy))
        except Exception:
            pass
    return max(len(seen), 1)


def mergeHoleListByDia(hole_list):
    """同直徑列合併（通/盲、沉頭大徑、盲孔深度分桶）。"""
    merged = {}
    for info in hole_list or []:
        through = bool(info.get('through', True))
        depth_bucket = ''
        if not through:
            try:
                depth_bucket = str(round(float(info.get('depth', 0) or 0), 1))
            except Exception:
                depth_bucket = str(info.get('depth', '') or '')
        key = (info['dia'], through, bool(info.get('isCBLarge', False)), depth_bucket)
        if key not in merged:
            merged[key] = dict(info)
        else:
            dst = merged[key]
            dst['count'] += info['count']
            dst['faces'].extend(info.get('faces') or [])
            dst['smallFaces'].extend(info.get('smallFaces') or [])
            dst['cbFaces'].extend(info.get('cbFaces') or [])
    return list(merged.values())


def _sanitize_hole_row_for_debug(row):
    if not isinstance(row, dict):
        return {'raw': str(row)}
    try:
        faces = row.get('faces', []) or []
        face_count = int(row.get('face_count', len(faces)))
    except Exception:
        face_count = 0
    return {
        'diameter_mm': row.get('diameter_mm'),
        'through': bool(row.get('through', False)),
        'dir': row.get('dir', 'Z+'),
        'depth_mm': row.get('depth_mm'),
        'ray_radius_mm': row.get('ray_radius_mm'),
        'count': row.get('count'),
        'face_count': face_count,
        'is_countersink_large': bool(row.get('is_countersink_large', False)),
        'is_countersink_small': bool(row.get('is_countersink_small', False)),
    }


def _emit_hole_debug_dump(source='scan'):
    if not getattr(runtime_state, 'hole_debug_enabled', False):
        return
    try:
        n_rows = len(runtime_state.last_hole_scan_rows_debug or [])
        n_merged = len(holeInfoList or [])
        _send_diag_log(f'[hole-debug] 來源={source} 掃描列數={n_rows} 合併孔數={n_merged}')
    except Exception:
        pass


def _emit_slot_diag_dump(source='scan'):
    if not getattr(runtime_state, 'slot_debug_enabled', False):
        return
    try:
        _send_diag_log(f'[slot-debug] 來源={source} 槽列數={len(slotInfoList or [])}')
    except Exception:
        pass


def _scanAndBuildHoleInfo(force=False):
    """
    掃描並建立孔位資訊。
    force: 是否強制重新掃描（忽略簽名檢查）
    """
    global holeInfoList, bodyZRange_ref, root_comp_ref
    des_obj = runtime_state.des_obj
    camSetup = runtime_state.cam_setup
    if not des_obj or not camSetup:
        return False

    if not _validate_and_refresh_refs():
        return False
    des_obj = runtime_state.des_obj
    camSetup = runtime_state.cam_setup

    # 1. 檢查簽名，決定是否跳過掃描
    current_sig = _calcDisplaySignature()
    if not force and current_sig == runtime_state.last_display_signature and len(holeInfoList) > 0:
        return True
    
    # 開始掃描
    holeInfoList = []
    root_comp_ref = des_obj.rootComponent
    wcs = camSetup.workCoordinateSystem
    (origin, xAxis, yAxis, zAxis) = wcs.getAsCoordinateSystem()

    # 嚴格使用獨立辨識模組（smart_ai_cam_recognizers/hole_recognizer.py）
    rec_mod = _get_hole_recognizer_module()
    if not rec_mod or not hasattr(rec_mod, 'scan_holes_by_ray'):
        raise RuntimeError(f'hole_recognizer unavailable: {_hole_recognizer_error}')

    bodyZRange_ref = {}
    for comp in des_obj.allComponents:
        for bi in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(bi)
            if not _isBodyVisible(body):
                continue
            bodyZRange_ref[body.entityToken] = _bbox_proj_min_max(body.boundingBox, zAxis)

    try:
        rows = rec_mod.scan_holes_by_ray(
            design=des_obj,
            setup=camSetup,
            runtime_state=runtime_state,
            ray_diameter_delta_mm=runtime_state.ray_diameter_delta_mm,
        )
    except TypeError:
        rows = rec_mod.scan_holes_by_ray(
            design=des_obj,
            setup=camSetup,
            ray_diameter_delta_mm=runtime_state.ray_diameter_delta_mm,
        )
    runtime_state.last_hole_scan_rows_raw = list(rows or [])
    runtime_state.last_hole_scan_rows_debug = [_sanitize_hole_row_for_debug(r) for r in runtime_state.last_hole_scan_rows_raw]
    import builtins
    _round = builtins.round
    holeInfoList = []
    for r in (rows or []):
        faces = list(r.get('faces', []) or [])
        count = _countHoles(faces, origin, xAxis, yAxis) if faces else max(int(r.get('face_count', 1)), 1)
        try:
            depth_mm = float(r.get('depth_mm', 0.0))
        except:
            depth_mm = 0.0
        try:
            cb_top_dia = float(r.get('cbTopDia', 0.0))
        except:
            cb_top_dia = 0.0
        try:
            cb_depth = float(r.get('cbDepth', 0.0))
        except:
            cb_depth = 0.0
        is_threaded = bool(r.get('is_threaded', False))
        thread_designation = str(r.get('thread_designation', ''))
        holeInfoList.append({
            'dia': str(_round(float(r.get('diameter_mm', 0.0)), 1)),
            'cbTopDia': str(_round(cb_top_dia, 1)) if cb_top_dia > 0 else '',
            'type': 'Simple',
            'dir': str(r.get('dir', 'Z+')),
            'through': bool(r.get('through', False)),
            'depth': str(_round(depth_mm, 1)),
            'cbDepth': str(_round(cb_depth, 1)) if cb_depth > 0 else '',
            'count': count,
            'faces': faces,
            'smallFaces': [],
            'cbFaces': [],
            'isCBLarge': bool(r.get('is_countersink_large', False)),
            'isCBSmall': bool(r.get('is_countersink_small', False)),
            'cbSmallZMax': None,
            'dropItems': [],
            'isThreaded': is_threaded,
            'threadDesignation': thread_designation
        })
    holeInfoList.sort(key=lambda x: float(x['dia']))
    holeInfoList = mergeHoleListByDia(holeInfoList)
    runtime_state.holeInfoList = list(holeInfoList)
    runtime_state.bodyZRange_ref = bodyZRange_ref
    _emit_hole_debug_dump(source='scan')
    runtime_state.last_display_signature = current_sig
    return len(holeInfoList) > 0

def _scanAndBuildSlotInfo(invoked_from='rebuild'):
    """Secondary layer: scan racetrack slots for UI display.

    invoked_from: 'rebuild' | 'full_rescan' — 寫入 [slot-debug] 的 source，便於區分
    輕量重建與「重新快取模板 / 完全重掃」觸發的 full_rescan。
    """
    global slotInfoList
    slotInfoList = []
    if not _validate_and_refresh_refs():
        return False
    des_obj = runtime_state.des_obj
    camSetup = runtime_state.cam_setup
    if not des_obj or not camSetup:
        return False
    rec_mod = _get_slot_recognizer_module()
    if not rec_mod or not hasattr(rec_mod, 'scan_slots'):
        _send_diag_log(f'slot_recognizer unavailable: {_slot_recognizer_error}')
        return False
    try:
        rows = rec_mod.scan_slots(design=des_obj, setup=camSetup, visible_only=True, through_tol=0.05) or []
        active_rows = rec_mod.filter_slots_for_machining(rows) if hasattr(rec_mod, 'filter_slots_for_machining') else rows
    except Exception as e:
        _send_diag_log(f'slot_recognizer scan failed: {e}')
        return False
    out = []
    for i, r in enumerate(rows):
        try:
            _row = {
                'idx': i,
                'width_mm': float(r.get('width_mm', 0.0)),
                'length_mm': float(r.get('length_mm', 0.0)),
                'depth_mm': float(r.get('depth_mm', 0.0)),
                'through': bool(r.get('through', False)),
                'cx': float(r.get('cx', 0.0)),
                'cy': float(r.get('cy', 0.0)),
                'angle_deg': float(r.get('angle_deg', 0.0)),
                'face_z_wcs_mm': float(r.get('face_z_wcs_mm', 0.0)),
                'top_z_wcs_mm': float(r.get('top_z_wcs_mm', 0.0)),
                'bot_z_wcs_mm': float(r.get('bot_z_wcs_mm', 0.0)),
                'slot_z_min_mm': float(r.get('slot_z_min_mm', 0.0)),
                'slot_z_max_mm': float(r.get('slot_z_max_mm', 0.0)),
                'active': False,
                # 與 recognizers/slot_recognizer 一致：loop 相關 BRepFace，供執行階段帶入 CAM 模板。
                'faces': list(r.get('faces') or []),
                'host_opening_face': r.get('host_opening_face'),
                'loop_edges': list(r.get('loop_edges') or []),
                'loop_edge_tokens': list(r.get('loop_edge_tokens') or []),
                'opening_face_token': r.get('opening_face_token'),
                'opening_anchor_edge_token': r.get('opening_anchor_edge_token'),
                'opening_face_token_diag': r.get('opening_face_token_diag'),
            }
            try:
                if r.get('_debug_body'):
                    _row['dbg_body'] = str(r.get('_debug_body'))
                if r.get('_debug_occurrence'):
                    _row['dbg_occ'] = str(r.get('_debug_occurrence'))
            except Exception:
                pass
            out.append(_row)
        except:
            pass
    active_keys = set()
    for r in (active_rows or []):
        try:
            key = (
                round(float(r.get('cx', 0.0)), 3),
                round(float(r.get('cy', 0.0)), 3),
                round(float(r.get('width_mm', 0.0)), 3),
                round(float(r.get('length_mm', 0.0)), 3),
                round(float(r.get('depth_mm', 0.0)), 3),
            )
            active_keys.add(key)
        except:
            pass
    for row in out:
        k = (
            round(float(row.get('cx', 0.0)), 3),
            round(float(row.get('cy', 0.0)), 3),
            round(float(row.get('width_mm', 0.0)), 3),
            round(float(row.get('length_mm', 0.0)), 3),
            round(float(row.get('depth_mm', 0.0)), 3),
        )
        row['active'] = (k in active_keys)
    slotInfoList = out
    runtime_state.slotInfoList = list(slotInfoList)
    _emit_slot_diag_dump(source=invoked_from)
    return len(slotInfoList) > 0


def _scanAndBuildPocketCornerRInfo():
    """掃描口袋槽垂直 R 角，填入 pocketCornerRInfoList（面板「口袋槽辨識」槽內 R 角列）。"""
    global pocketCornerRInfoList
    pocketCornerRInfoList = []
    if not _validate_and_refresh_refs():
        return False
    des_obj = runtime_state.des_obj
    camSetup = runtime_state.cam_setup
    if not des_obj or not camSetup:
        return False
    rec_mod = _get_hole_recognizer_module()
    if not rec_mod or not hasattr(rec_mod, 'collect_pocket_corner_r_rows'):
        return False
    try:
        rows = rec_mod.collect_pocket_corner_r_rows(
            design=des_obj,
            setup=camSetup,
            visible_only=True,
        )
    except Exception:
        rows = []
    for r in rows or []:
        try:
            pocketCornerRInfoList.append({
                'r_mm': float(r.get('r_mm', 0.0)),
                'cylinder_diameter_mm': float(r.get('cylinder_diameter_mm', 0.0)),
                'cylinder_area_ratio': float(r.get('cylinder_area_ratio', 0.0)),
                'lx_mm': float(r.get('lx_mm', 0.0)),
                'ly_mm': float(r.get('ly_mm', 0.0)),
                'lz_mm': float(r.get('lz_mm', 0.0)),
                'cx_wcs_mm': float(r.get('cx_wcs_mm', 0.0)),
                'cy_wcs_mm': float(r.get('cy_wcs_mm', 0.0)),
                'cz_wcs_mm': float(r.get('cz_wcs_mm', 0.0)),
                'dir': str(r.get('dir', 'Z+')),
                'count': int(r.get('count', 1)),
                'face_count': int(r.get('face_count', len(r.get('faces') or []))),
                'faces': list(r.get('faces') or []),
            })
        except Exception:
            continue
    runtime_state.pocketCornerRInfoList = list(pocketCornerRInfoList)
    return len(pocketCornerRInfoList) > 0




def _buildHoleData(mat='AL6061'):
    dm = allDrillMap.get(mat, {})
    cm = allChamferMap.get(mat, {})
    cs = allCountersinkMap.get(mat, [])
    def _pitch_default_mm_from_item(item):
        try:
            u = item.get('drillUrl', None) if isinstance(item, dict) else None
            if not u:
                return None
            p = getTemplateParams(u) or {}
            vmm = p.get('pitchMM', None)
            if vmm is not None:
                vv = float(vmm)
                return vv if vv > 0 else None
            raw = str(p.get('pitch', '') or '')
            if not raw:
                return None
            v = float(re.sub(r'[^0-9.]', '', raw))
            return v if v > 0 else None
        except:
            return None
    rows = []
    for info in holeInfoList:
        # Through holes are machinable regardless of side.
        # Non-through rows keep front-side-only policy, and backside countersink is non-machinable.
        _through = bool(info.get('through', False))
        _dir = str(info.get('dir', 'Z+'))
        if (not _through) and (_dir != 'Z+'):
            continue
        _is_backside_countersink = (_dir == 'Z-(CB)') or (
            _dir == 'Z-' and bool(info.get('isCBLarge', False) or info.get('isCBSmall', False))
        )
        if _is_backside_countersink:
            continue
        items = buildDropItems(info['dia'], dm, cm, info, cs)
        info['dropItems'] = items

        # --- 孔加工邏輯庫 (KnowledgeDB) 自動套用預設值 ---
        kb_tmpl_idx = 0
        try:
            from Smart_AI.memory.knowledge_db import get_db as _get_kb
            from Smart_AI.reasoning.ai_training import _hole_geometry_for_db as _hg, find_tmpl_idx_by_label as _ftl
            _kb = _get_kb()
            _geom = _hg(info)
            _best = _kb.query_best_template('hole', mat, _geom)
            if _best and float(_best.get('confidence', 0)) >= 0.35:
                _tidx = _ftl(items, _best.get('template_name', ''))
                if _tidx >= 0:
                    kb_tmpl_idx = _tidx
        except Exception:
            pass

        # 決定初始 UI 顯示（優先使用邏輯庫推薦索引）
        firstItem = items[kb_tmpl_idx] if items and kb_tmpl_idx < len(items) else (items[0] if items else {})
        hasDrill = firstItem.get('hasDrill', False)
        showReamerControl = firstItem.get('hasReamer', False)
        showPitch = firstItem.get('hasMillBore', False) or (
            bool(info.get('isCBLarge', False)) and bool(firstItem.get('drillUrl', None))
        )

        # 處理背面沉頭孔
        isLargeHoleZMinus = (info.get('cbTopDia', '') == '' and
                            info.get('cbDepth', '') == '' and
                            info.get('dir', '') == 'Z-' and
                            info.get('through', True) == False)
        if isLargeHoleZMinus:
            hasDrill = False
            showReamerControl = False
            showPitch = False

        rows.append({
            'dia': info['dia'],
            'cbTopDia': info.get('cbTopDia', ''),
            'cbDepth': info.get('cbDepth', ''),
            'through': info['through'],
            'dir': info['dir'],
            'isCBLarge': info.get('isCBLarge', False),
            'depth': info['depth'],
            'count': info['count'],
            'dropItems': [{
                'label': x.get('label', ''),
                'listDisplay': str(x.get('listDisplay', '') or ''),
                'hasDrill': bool(x.get('drillUrl')),
                'hasChamfer': bool(x.get('chamferUrl')),
                'hasReamer': bool(x.get('hasReamer', False)),
                'hasMillBore': bool(x.get('hasMillBore', False)),
                'drillUrl': (str(x.get('drillUrl')) if x.get('drillUrl') else ''),
                'chamferUrl': (str(x.get('chamferUrl')) if x.get('chamferUrl') else ''),
                'cycleType': str(x.get('cycleType', '') or ''),
                'toolType': str(x.get('toolType', '') or ''),
                'pitchDefaultMM': _pitch_default_mm_from_item(x),
            } for x in items],
            'hasDrill': hasDrill,
            'showReamerControl': showReamerControl,
            'showPitch': showPitch,
            'drillTip': info['through'],
            'reamTip': info['through'],
            'tmplIdx': kb_tmpl_idx,
        })
    return rows


def _read_cam_setup_param_mm(setup, name, default=None):
    """Read a Fusion CAM setup parameter value in mm (internal storage is cm)."""
    if not setup:
        return default
    try:
        params = setup.parameters
        if not params:
            return default
        p = params.itemByName(name)
        if not p or not p.value:
            return default
        return round(float(p.value.value) * 10.0, 3)
    except Exception:
        return default


def _read_setup_stock_info(setup):
    """坯料／工件 Z 範圍：以 Setup CAM 參數為準（Setup WCS，非世界座標）。"""
    info = {
        "stock_mode": None,
        "fixed_x_mm": _read_cam_setup_param_mm(setup, "job_stockFixedX"),
        "fixed_y_mm": _read_cam_setup_param_mm(setup, "job_stockFixedY"),
        "fixed_z_mm": _read_cam_setup_param_mm(setup, "job_stockFixedZ"),
        "fixed_x_offset_mm": _read_cam_setup_param_mm(setup, "job_stockFixedXOffset"),
        "fixed_y_offset_mm": _read_cam_setup_param_mm(setup, "job_stockFixedYOffset"),
        "fixed_z_offset_mm": _read_cam_setup_param_mm(setup, "job_stockFixedZOffset"),
        "stock_z_high_mm": _read_cam_setup_param_mm(setup, "stockZHigh"),
        "stock_z_low_mm": _read_cam_setup_param_mm(setup, "stockZLow"),
        "stock_x_high_mm": _read_cam_setup_param_mm(setup, "stockXHigh"),
        "stock_x_low_mm": _read_cam_setup_param_mm(setup, "stockXLow"),
        "stock_y_high_mm": _read_cam_setup_param_mm(setup, "stockYHigh"),
        "stock_y_low_mm": _read_cam_setup_param_mm(setup, "stockYLow"),
        "surface_z_high_mm": _read_cam_setup_param_mm(setup, "surfaceZHigh"),
        "surface_z_low_mm": _read_cam_setup_param_mm(setup, "surfaceZLow"),
    }
    try:
        mode_p = setup.parameters.itemByName("job_stockMode")
        if mode_p and mode_p.value:
            info["stock_mode"] = str(mode_p.value.value or mode_p.expression or "")
    except Exception:
        pass

    def _span(hi, lo):
        if hi is None or lo is None:
            return None
        return round(abs(float(hi) - float(lo)), 3)

    info["size_x_mm"] = info.get("fixed_x_mm") or _span(
        info.get("stock_x_high_mm"), info.get("stock_x_low_mm")
    )
    info["size_y_mm"] = info.get("fixed_y_mm") or _span(
        info.get("stock_y_high_mm"), info.get("stock_y_low_mm")
    )
    info["size_z_mm"] = info.get("fixed_z_mm") or _span(
        info.get("stock_z_high_mm"), info.get("stock_z_low_mm")
    )
    info["job_stock_fixed_z_offset_mm"] = info.get("fixed_z_offset_mm")
    return info


def _project_point_setup_z_mm(pt, origin, z_axis):
    dx = pt.x - origin.x
    dy = pt.y - origin.y
    dz = pt.z - origin.z
    z_cm = dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
    return round(z_cm * 10.0, 3)


def _body_setup_z_extents_mm(bodies, origin, z_axis):
    z_vals = []
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
                z_vals.append(
                    _project_point_setup_z_mm(
                        adsk.core.Point3D.create(x, y, z), origin, z_axis
                    )
                )
        except Exception:
            pass
    if not z_vals:
        return None, None
    return min(z_vals), max(z_vals)


def _setup_z_calibration_offset_mm(body_z_max_mm, stock_info):
    """
    將幾何投影 Z 對齊 Fusion Setup 的 surfaceZHigh（與 stockZHigh 同一 WCS）。
    避免 WCS origin API 與 CAM 坯料 Z0 不一致（例如 10× 偏差）。
    """
    surface_high = stock_info.get("surface_z_high_mm")
    if surface_high is None or body_z_max_mm is None:
        return 0.0
    delta = round(float(surface_high) - float(body_z_max_mm), 3)
    if abs(delta) <= 0.05:
        return 0.0
    # 常見 API 單位／基準偏差：僅在差異顯著時校正
    if abs(delta) >= 1.0:
        return delta
    return 0.0


def _depth_below_setup_z0_mm(signed_z_mm):
    """Setup WCS Z+ 向上時，Z0 下方為負 Z → 正深度 = -signed_z。"""
    if signed_z_mm is None:
        return None
    z = float(signed_z_mm)
    if z <= 0.001:
        return round(max(0.0, -z), 3)
    return 0.0


def _stock_top_to_part_top_mm(stock_info):
    """坯料顶面→实体顶面：優先 job_stockFixedZOffset（Setup CAM 常駐參數）。"""
    off = stock_info.get("job_stock_fixed_z_offset_mm")
    if off is None:
        off = stock_info.get("fixed_z_offset_mm")
    if off is not None:
        return round(abs(float(off)), 3)
    return _depth_below_setup_z0_mm(stock_info.get("surface_z_high_mm"))


def _stock_remaining_thickness_mm(stock_info, part_thickness_mm):
    """
    坯料剩余厚度 = job_stockFixedZOffset + 工件厚度 − job_stockFixedZ
    """
    offset = _stock_top_to_part_top_mm(stock_info)
    fixed_z = stock_info.get("fixed_z_mm")
    if offset is None or part_thickness_mm is None or fixed_z is None:
        return None
    return round(float(offset) + float(part_thickness_mm) - float(fixed_z), 3)


def _setup_z_depth_metrics(stock_info, body_z_min=None, body_z_max=None, z_cal=0.0):
    """
    加工深度以 Setup WCS 為準（Z0 = WCS 原點平面，非坯料局部 Z）：
    - 坯料顶面→实体顶面 = job_stockFixedZOffset（坯料參數，獨立顯示）
    - WCS Z0→工件底面 = -surfaceZLow（Fusion Setup WCS 內模型最低點）
    - 工件厚度 = |surfaceZHigh − surfaceZLow|
    - 坯料剩余厚度 = job_stockFixedZOffset + 工件厚度 − job_stockFixedZ
    """
    sh = stock_info.get("surface_z_high_mm")
    sl = stock_info.get("surface_z_low_mm")
    if sh is None and body_z_max is not None:
        sh = round(float(body_z_max) + float(z_cal), 3)
    if sl is None and body_z_min is not None:
        sl = round(float(body_z_min) + float(z_cal), 3)

    part_thickness = None
    if sh is not None and sl is not None:
        part_thickness = round(abs(float(sh) - float(sl)), 3)

    stock_to_part_top = _stock_top_to_part_top_mm(stock_info)

    # WCS Z0→底面：直接取 surfaceZLow 相對 Setup WCS 原點的深度
    z0_to_bottom = _depth_below_setup_z0_mm(sl)
    if z0_to_bottom is None and body_z_min is not None:
        z0_to_bottom = _depth_below_setup_z0_mm(float(body_z_min) + float(z_cal))

    stock_remaining = _stock_remaining_thickness_mm(stock_info, part_thickness)

    return {
        "surface_z_high_mm": sh,
        "surface_z_low_mm": sl,
        "job_stock_fixed_z_offset_mm": stock_info.get("job_stock_fixed_z_offset_mm"),
        "job_stock_fixed_z_mm": stock_info.get("fixed_z_mm"),
        "stock_to_part_top_mm": stock_to_part_top,
        "z0_to_part_bottom_mm": z0_to_bottom,
        "part_thickness_mm": part_thickness,
        "stock_remaining_thickness_mm": stock_remaining,
    }


def _flat_depths_empty(stock_info=None):
    stock_info = stock_info or {}
    offset = _stock_top_to_part_top_mm(stock_info) or 0.0
    z_metrics = _setup_z_depth_metrics(stock_info)
    return {
        "z_reference": "setup_wcs_z0",
        "max_z_mm": 0.0,
        "job_stock_fixed_z_offset_mm": stock_info.get("job_stock_fixed_z_offset_mm"),
        "stock_to_part_top_mm": offset,
        "z0_to_part_bottom_mm": z_metrics.get("z0_to_part_bottom_mm") or 0.0,
        "part_thickness_mm": z_metrics.get("part_thickness_mm") or 0.0,
        "stock_remaining_thickness_mm": z_metrics.get("stock_remaining_thickness_mm"),
        "z_span_mm": z_metrics.get("part_thickness_mm") or 0.0,
        "stock": stock_info,
        "planes": [],
    }


def _scanFlatDepths():
    camSetup = runtime_state.cam_setup
    des_obj = runtime_state.des_obj
    stock_info = _read_setup_stock_info(camSetup) if camSetup else {}
    if not camSetup or not des_obj:
        return _flat_depths_empty(stock_info)

    try:
        wcs = camSetup.workCoordinateSystem
        origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()

        bodies_to_scan = []
        try:
            from smart_ai_cam_vision.snapshot import _get_setup_target_bodies

            root = des_obj.rootComponent
            bodies_to_scan = list(_get_setup_target_bodies(camSetup, root) or [])
        except Exception:
            bodies_to_scan = []

        if not bodies_to_scan:
            scan_bodies = getattr(runtime_state, "scan_bodies_cache", None)
            if scan_bodies is not None:
                for entry in scan_bodies:
                    if not entry["visible"]:
                        continue
                    bodies_to_scan.append(entry["body"])
            else:
                for comp in des_obj.allComponents:
                    for bi in range(comp.bRepBodies.count):
                        body = comp.bRepBodies.item(bi)
                        try:
                            if not _isBodyVisible(body):
                                continue
                        except Exception:
                            pass
                        bodies_to_scan.append(body)

        body_z_min, body_z_max = _body_setup_z_extents_mm(bodies_to_scan, origin, z_axis)
        z_cal = _setup_z_calibration_offset_mm(body_z_max, stock_info)

        flat_faces = []
        z_values = []
        for body in bodies_to_scan:
            for fi in range(body.faces.count):
                face = body.faces.item(fi)
                try:
                    geom = face.geometry
                    if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                        continue
                    plane = adsk.core.Plane.cast(geom)
                    if not plane:
                        continue

                    normal = plane.normal
                    dot = normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z
                    if abs(dot) < 0.99:
                        continue

                    bb = face.boundingBox
                    use_max = dot >= 0.0
                    ref_z = bb.maxPoint.z if use_max else bb.minPoint.z
                    ref_y = bb.maxPoint.y if use_max else bb.minPoint.y
                    ref_x = bb.maxPoint.x if use_max else bb.minPoint.x
                    pt = adsk.core.Point3D.create(ref_x, ref_y, ref_z)
                    z_mm = _project_point_setup_z_mm(pt, origin, z_axis) + z_cal

                    area_mm2 = round(face.area * 100.0, 2)
                    flat_faces.append({"z_mm": z_mm, "area_mm2": area_mm2})
                    z_values.append(z_mm)
                except Exception:
                    pass

        surface_high = stock_info.get("surface_z_high_mm")
        surface_low = stock_info.get("surface_z_low_mm")
        z_metrics = _setup_z_depth_metrics(
            stock_info, body_z_min=body_z_min, body_z_max=body_z_max, z_cal=z_cal
        )
        z0_to_bottom = z_metrics.get("z0_to_part_bottom_mm") or 0.0
        stock_to_top = z_metrics.get("stock_to_part_top_mm")
        if stock_to_top is None:
            stock_to_top = 0.0
        part_thickness = z_metrics.get("part_thickness_mm")
        job_z_offset = z_metrics.get("job_stock_fixed_z_offset_mm")
        stock_remaining = z_metrics.get("stock_remaining_thickness_mm")

        if not z_values:
            out = _flat_depths_empty(stock_info)
            out["stock_to_part_top_mm"] = float(stock_to_top)
            out["job_stock_fixed_z_offset_mm"] = job_z_offset
            out["z0_to_part_bottom_mm"] = z0_to_bottom
            out["part_thickness_mm"] = part_thickness or 0.0
            out["stock_remaining_thickness_mm"] = z_metrics.get("stock_remaining_thickness_mm")
            out["z_span_mm"] = part_thickness or 0.0
            out["surface_z_high_mm"] = surface_high
            out["surface_z_low_mm"] = surface_low
            return out

        buckets = {}
        for f in flat_faces:
            key = round(f["z_mm"], 1)
            buckets[key] = buckets.get(key, 0.0) + f["area_mm2"]

        planes_list = []
        for z_key, area in buckets.items():
            planes_list.append({"z_height_mm": z_key, "area_mm2": round(area, 2)})
        planes_list.sort(key=lambda x: x["z_height_mm"], reverse=True)

        top_z_wcs = max(z_values)
        bottom_z_wcs = min(z_values)
        z_span = round(top_z_wcs - bottom_z_wcs, 3)
        if part_thickness is not None and part_thickness > 0:
            z_span = part_thickness

        for p in planes_list:
            z_wcs = float(p["z_height_mm"])
            # Setup WCS Z0 下方深度（與 surfaceZ 同一座標系，不加坯料 offset）
            p["depth_from_z0_mm"] = round(max(0.0, -z_wcs), 3)
            p["relative_depth_mm"] = round(top_z_wcs - z_wcs, 2)

        return {
            "z_reference": "setup_wcs_z0",
            "max_z_mm": 0.0,
            "job_stock_fixed_z_offset_mm": job_z_offset,
            "stock_to_part_top_mm": float(stock_to_top),
            "z0_to_part_bottom_mm": z0_to_bottom,
            "part_thickness_mm": part_thickness or z_span,
            "stock_remaining_thickness_mm": stock_remaining,
            "job_stock_fixed_z_mm": z_metrics.get("job_stock_fixed_z_mm"),
            "surface_z_high_mm": surface_high,
            "surface_z_low_mm": surface_low,
            "z_span_mm": z_span,
            "stock": stock_info,
            "z_calibration_mm": z_cal,
            "planes": planes_list,
        }
    except Exception as e:
        return {"error": str(e), "stock": stock_info, "planes": []}


def _buildPocketCornerRData(mat='AL6061', include_faces=False):
    """口袋槽 R 角獨立表列：R、深度、僅一般鑽模板下拉；預設選 (不使用)。include_faces 僅供本機 execute。"""
    import builtins

    _round = builtins.round
    global pocketCornerRInfoList, bodyZRange_ref
    dm = allDrillMap.get(mat, {}) or {}
    bzr = bodyZRange_ref if isinstance(bodyZRange_ref, dict) else {}

    def _pitch_default_mm_from_item(item):
        try:
            u = item.get('drillUrl', None) if isinstance(item, dict) else None
            if not u:
                return None
            p = getTemplateParams(u) or {}
            vmm = p.get('pitchMM', None)
            if vmm is not None:
                vv = float(vmm)
                return vv if vv > 0 else None
            raw = str(p.get('pitch', '') or '')
            if not raw:
                return None
            v = float(re.sub(r'[^0-9.]', '', raw))
            return v if v > 0 else None
        except Exception:
            return None

    merge_groups = {}
    for pr in list(pocketCornerRInfoList or []):
        faces = list(pr.get('faces') or [])
        if not faces:
            continue
        try:
            r_mm = float(pr.get('r_mm', 0.0) or 0.0)
            ddir = str(pr.get('dir', 'Z+'))
            depth_mm = 12.0
            try:
                _tok = faces[0].body.entityToken
                if _tok in bzr:
                    _b0, _b1 = bzr[_tok]
                    depth_mm = (_b1 - _b0) * 10.0
            except Exception:
                pass
            if depth_mm <= 0:
                depth_mm = 12.0
            depth_mm = float(_round(depth_mm, 3))
            gkey = (float(_round(r_mm, 3)), depth_mm, ddir)
            if gkey not in merge_groups:
                merge_groups[gkey] = {
                    'r_mm': float(_round(r_mm, 3)),
                    'depth_mm': depth_mm,
                    'dir': ddir,
                    'count': 0,
                    'faces': [],
                    'dia_mm': float(pr.get('cylinder_diameter_mm', 0.0) or 0.0),
                }
            g = merge_groups[gkey]
            g['count'] += int(pr.get('count', 1) or 1)
            seen_ftok = {getattr(f, 'entityToken', id(f)) for f in g['faces']}
            for f in faces:
                try:
                    ftok = getattr(f, 'entityToken', id(f))
                except Exception:
                    ftok = id(f)
                if ftok in seen_ftok:
                    continue
                seen_ftok.add(ftok)
                g['faces'].append(f)
        except Exception:
            continue

    out = []
    for g in sorted(merge_groups.values(), key=lambda x: (x['r_mm'], x['depth_mm'], x['dir'])):
        faces = list(g.get('faces') or [])
        if not faces:
            continue
        try:
            dia_mm = float(g.get('dia_mm', 0.0) or 0.0)
            if dia_mm <= 0:
                cyl0 = adsk.core.Cylinder.cast(faces[0].geometry)
                if cyl0:
                    dia_mm = round(cyl0.radius * 20.0, 3)
            dia_s = str(_round(dia_mm, 1))
            items = build_simple_drill_drop_items_only(dia_s, dm)
            unused_idx = 0
            for _ii, _it in enumerate(items):
                if str(_it.get('label', '') or '') == '(不使用)':
                    unused_idx = _ii
                    break
            else:
                unused_idx = max(0, len(items) - 1)
            ser_items = [{
                'label': x.get('label', ''),
                'listDisplay': str(x.get('listDisplay', '') or ''),
                'hasDrill': bool(x.get('drillUrl')),
                'hasChamfer': bool(x.get('chamferUrl')),
                'hasReamer': bool(x.get('hasReamer', False)),
                'hasMillBore': bool(x.get('hasMillBore', False)),
                'drillUrl': (str(x.get('drillUrl')) if x.get('drillUrl') else ''),
                'chamferUrl': (str(x.get('chamferUrl')) if x.get('chamferUrl') else ''),
                'cycleType': str(x.get('cycleType', '') or ''),
                'toolType': str(x.get('toolType', '') or ''),
                'pitchDefaultMM': _pitch_default_mm_from_item(x),
            } for x in items]
            row = {
                'r_mm': g['r_mm'],
                'depth_mm': g['depth_mm'],
                'through': True,
                'dir': g['dir'],
                'count': int(g.get('count', 0) or 0),
                'dia': dia_s,
                'tmplIdx': int(unused_idx),
                'dropItems': ser_items,
                'hasDrill': False,
                'showReamerControl': False,
                'showPitch': False,
                'drillTip': True,
                'reamTip': True,
            }
            if include_faces:
                row['faces'] = faces
            out.append(row)
        except Exception:
            continue
    return out


def _buildSlotData(mat='AL6061', include_features=False):
    # 1) Collapse multi-loop rows to unique slot features by center + width + through.
    # 2) Convert to machining depth:
    #    - through => stock thickness (top_z - bot_z)
    #    - blind   => max(depth_mm, slot_z_max-slot_z_min)
    # 3) Group by (width, length, machining_depth, through) — 同尺寸合併為一列。
    # include_features=True 時附帶 slot_features（每槽一面列），僅供本機執行；勿序列化到 JSON。
    feature_map = {}
    for s in (slotInfoList or []):
        try:
            if s.get('active') is False:
                continue
            cx = round(float(s.get('cx', 0.0)), 3)
            cy = round(float(s.get('cy', 0.0)), 3)
            w = round(float(s.get('width_mm', 0.0)), 3)
            t = bool(s.get('through', False))
            fkey = (cx, cy, w, t)
            if fkey not in feature_map:
                feature_map[fkey] = []
            feature_map[fkey].append(s)
        except:
            pass

    groups = {}
    for _, rows in feature_map.items():
        try:
            sample = rows[0]
            w = round(float(sample.get('width_mm', 0.0)), 3)
            t = bool(sample.get('through', False))
            topz = float(sample.get('top_z_wcs_mm', 0.0))
            botz = float(sample.get('bot_z_wcs_mm', 0.0))
            thickness = abs(topz - botz)
            depth_candidates = []
            for r in rows:
                try:
                    d_raw = float(r.get('depth_mm', 0.0))
                except:
                    d_raw = 0.0
                try:
                    zmin = float(r.get('slot_z_min_mm', 0.0))
                    zmax = float(r.get('slot_z_max_mm', 0.0))
                    z_span = abs(zmax - zmin)
                except:
                    z_span = 0.0
                depth_candidates.append(max(d_raw, z_span))
            if t:
                d = round(thickness, 3)
            else:
                d = round(max(depth_candidates) if depth_candidates else 0.0, 3)
            if d <= 0.0:
                continue
            try:
                l_mm = round(float(sample.get('length_mm', 0.0)), 3)
            except Exception:
                l_mm = 0.0
            gkey = (w, l_mm, d, t)
            if gkey not in groups:
                groups[gkey] = {
                    'width_mm': w,
                    'length_mm': l_mm,
                    'depth_mm': d,
                    'through': t,
                    'count': 0,
                    'tool_dia': _recommend_slot_tool_dia(w),
                }
            groups[gkey]['count'] += 1
            if include_features:
                merged_faces = []
                seen_tok = set()
                merged_edges = []
                seen_etok = set()
                merged_edge_tokens = []
                seen_tok_str = set()
                for r in rows:
                    for f in (r.get('faces') or []):
                        if not f:
                            continue
                        try:
                            tok = getattr(f, 'entityToken', None) or id(f)
                        except Exception:
                            tok = id(f)
                        if tok in seen_tok:
                            continue
                        seen_tok.add(tok)
                        merged_faces.append(f)
                    for e in (r.get('loop_edges') or []):
                        if not e:
                            continue
                        try:
                            etok = getattr(e, 'entityToken', None) or id(e)
                        except Exception:
                            etok = id(e)
                        if etok in seen_etok:
                            continue
                        seen_etok.add(etok)
                        merged_edges.append(e)
                    for t in (r.get('loop_edge_tokens') or []):
                        if t is None:
                            continue
                        try:
                            ts = t if isinstance(t, str) else str(t)
                        except Exception:
                            continue
                        if not ts or ts in seen_tok_str:
                            continue
                        seen_tok_str.add(ts)
                        merged_edge_tokens.append(ts)
                fz0 = None
                try:
                    fz0 = float(rows[0].get('face_z_wcs_mm', 0.0))
                except Exception:
                    fz0 = None
                op_tok = None
                for _r in rows:
                    try:
                        t = _r.get('opening_face_token')
                        if t:
                            op_tok = t if isinstance(t, str) else str(t)
                            break
                    except Exception:
                        pass
                feat_dict = {
                    'faces': merged_faces,
                    'loop_edges': merged_edges,
                    'loop_edge_tokens': merged_edge_tokens,
                }
                try:
                    _host = None
                    for _r in rows:
                        _hf = _r.get('host_opening_face')
                        if _hf and getattr(_hf, 'isValid', True):
                            _host = _hf
                            break
                    if _host is not None:
                        feat_dict['host_opening_face'] = _host
                except Exception:
                    pass
                if fz0 is not None:
                    feat_dict['face_z_wcs_mm'] = fz0
                if op_tok:
                    feat_dict['opening_face_token'] = op_tok
                try:
                    _s0 = rows[0]
                    feat_dict['cx_mm'] = float(_s0.get('cx', 0.0))
                    feat_dict['cy_mm'] = float(_s0.get('cy', 0.0))
                except Exception:
                    pass
                groups[gkey].setdefault('slot_features', []).append(feat_dict)
        except:
            pass

    out = list(groups.values())
    out.sort(key=lambda x: (x['width_mm'], x['depth_mm'], x['through']))

    # Composite-slot display normalization (CNC-oriented):
    # If one setup yields exactly:
    #   - larger width: through
    #   - smaller width: blind
    # with same count, merge to smaller-width row and mark through.
    # This matches machining intent for the setup face.
    if len(out) == 2:
        a, b = out[0], out[1]
        same_count = int(a.get('count', 0)) == int(b.get('count', 0))
        if same_count:
            # case: smaller blind + larger through  => keep smaller as through
            if (not a.get('through', False)) and b.get('through', False) and float(a.get('width_mm', 0.0)) < float(b.get('width_mm', 0.0)):
                merged_sf = []
                if include_features:
                    merged_sf = (a.get('slot_features') or []) + (b.get('slot_features') or [])
                out = [{
                    'width_mm': a.get('width_mm', 0.0),
                    'depth_mm': a.get('depth_mm', 0.0),
                    'through': True,
                    'count': a.get('count', 0),
                    'tool_dia': _recommend_slot_tool_dia(a.get('width_mm', 0.0)),
                    **({'slot_features': merged_sf} if include_features and merged_sf else {}),
                }]
            # symmetric ordering guard
            if (not b.get('through', False)) and a.get('through', False) and float(b.get('width_mm', 0.0)) < float(a.get('width_mm', 0.0)):
                merged_sf = []
                if include_features:
                    merged_sf = (b.get('slot_features') or []) + (a.get('slot_features') or [])
                out = [{
                    'width_mm': b.get('width_mm', 0.0),
                    'depth_mm': b.get('depth_mm', 0.0),
                    'through': True,
                    'count': b.get('count', 0),
                    'tool_dia': _recommend_slot_tool_dia(b.get('width_mm', 0.0)),
                    **({'slot_features': merged_sf} if include_features and merged_sf else {}),
                }]

    slot_items = allSlotMap.get(mat, []) or []
    chamfer_items = allSlotChamferMap.get(mat, []) or []
    slot_drop_items = [{'label': '(不使用)', 'url': '', 'toolDia': None}]
    for x in slot_items:
        nm = str(x.get('name', ''))
        dia = _extract_template_diameter_mm(nm)
        slot_drop_items.append({
            'label': nm,
            'url': _template_cache_key(x.get('url'), ''),
            'toolDia': (round(float(dia), 1) if dia is not None else None),
        })
    for row in out:
        rec_mm = _recommend_slot_tool_mm(row.get('width_mm', 0.0))
        # Keep only templates matching recommended cutter diameter.
        filtered_slot_items = [slot_drop_items[0]]
        if rec_mm is not None:
            for it in slot_drop_items[1:]:
                td = it.get('toolDia', None)
                if td is None:
                    continue
                if abs(float(td) - float(rec_mm)) <= 0.11:
                    filtered_slot_items.append(it)
        # 與 buildDropItems（孔）一致：先「槽×輪廓倒角」全組合，再純倒角、再純槽，最後 (不使用)。
        # 槽模板僅保留與推薦刀徑相符者（同列多個檔名時一併列入，不再只鎖第一個）。
        slot_candidates = []
        for it in filtered_slot_items[1:]:
            u = str(it.get('url', '') or '').strip()
            if not u:
                continue
            slot_candidates.append(it)

        chamfer_norm = []
        seen_chamfer_url = set()
        for chosen_chamfer in chamfer_items or []:
            try:
                chamfer_name = str(chosen_chamfer.get('name', '') or '')
                _uobj = chosen_chamfer.get('url')
                chamfer_url = _template_cache_key(_uobj, '')
            except Exception:
                chamfer_name, chamfer_url = '', ''
            if not chamfer_url:
                continue
            if chamfer_url in seen_chamfer_url:
                continue
            seen_chamfer_url.add(chamfer_url)
            try:
                _buck = chosen_chamfer.get('slotChamferBucket')
                chamfer_bucket = str(_buck).strip() if _buck is not None else ''
            except Exception:
                chamfer_bucket = ''
            chamfer_norm.append((chamfer_name, chamfer_url, chamfer_bucket))

        combined_items = []
        for s in slot_candidates:
            su = str(s.get('url', '') or '').strip()
            sn = str(s.get('label', '') or '')
            for chamfer_name, chamfer_url, chamfer_bucket in chamfer_norm:
                combined_items.append({
                    'label': sn + ' + ' + chamfer_name,
                    'slotUrl': su,
                    'chamferUrl': chamfer_url,
                    'hasSlot': True,
                    'hasChamfer': True,
                    'chamferBucket': chamfer_bucket,
                    'mode': '模板+倒角',
                })
        for chamfer_name, chamfer_url, chamfer_bucket in chamfer_norm:
            combined_items.append({
                'label': chamfer_name,
                'slotUrl': '',
                'chamferUrl': chamfer_url,
                'hasSlot': False,
                'hasChamfer': True,
                'chamferBucket': chamfer_bucket,
                'mode': '倒角',
            })
        for s in slot_candidates:
            su = str(s.get('url', '') or '').strip()
            sn = str(s.get('label', '') or '')
            combined_items.append({
                'label': sn,
                'slotUrl': su,
                'chamferUrl': '',
                'hasSlot': True,
                'hasChamfer': False,
                'chamferBucket': '',
                'mode': '模板',
            })
        combined_items.append({
            'label': '(不使用)',
            'slotUrl': '',
            'chamferUrl': '',
            'hasSlot': False,
            'hasChamfer': False,
            'chamferBucket': '',
            'mode': '不使用',
        })
        row['dropItems'] = combined_items

        # --- 槽加工邏輯庫 (KnowledgeDB) 自動套用預設值 ---
        slot_kb_idx = 0
        try:
            from Smart_AI.memory.knowledge_db import get_db as _get_kb_s
            from Smart_AI.reasoning.ai_training import _slot_geometry_for_db as _sg, find_tmpl_idx_by_label as _ftl_s
            _kbs = _get_kb_s()
            _sgeom = _sg(row)
            _sbest = _kbs.query_best_template('slot', mat, _sgeom)
            if _sbest and float(_sbest.get('confidence', 0)) >= 0.35:
                _tidx_s = _ftl_s(combined_items, _sbest.get('template_name', ''))
                if _tidx_s >= 0:
                    slot_kb_idx = _tidx_s
        except Exception:
            pass
        row['tmplIdx'] = slot_kb_idx

        row['tool_dia'] = (f'D{int(rec_mm)}' if rec_mm is not None and abs(rec_mm - int(rec_mm)) < 1e-9 else (f'D{rec_mm}' if rec_mm is not None else ''))
    return out


def _buildInitData():
    import json
    des_obj, camSetup, cam_obj, _ = _fusion_refs()
    setups = []
    if cam_obj:
        try:
            setups = [
                cam_obj.setups.item(i).name for i in range(cam_obj.setups.count)
            ]
        except Exception:
            setups = []
    pinned = (getattr(runtime_state, 'pending_setup_name', '') or '').strip()
    if pinned and pinned in setups:
        active = pinned
    elif camSetup:
        try:
            active = camSetup.name
        except Exception:
            active = setups[0] if setups else ''
    else:
        active = setups[0] if setups else ''
    mat = runtime_state.current_material
    tf = [x['name'] for x in allTopFaceMap.get(mat, [])]
    pf = [x['name'] for x in allProfileMap.get(mat, [])]
    tf_rough = [x['name'] for x in allTopFaceRoughMap.get(mat, [])]
    tf_finish = [x['name'] for x in allTopFaceFinishMap.get(mat, [])]
    pf_rough = [x['name'] for x in allProfileRoughMap.get(mat, [])]
    pf_finish = [x['name'] for x in allProfileFinishMap.get(mat, [])]
    hole_rows = _buildHoleData(mat)
    slot_rows = _buildSlotData(mat)
    pcr_rows = _buildPocketCornerRData(mat)
    ui_defaults = _load_ui_defaults()
    _drill_map = allDrillMap.get(mat, {}) or {}
    _chamfer_map = allChamferMap.get(mat, {}) or {}
    _has_hole_templates = any(bool(v) for v in _drill_map.values()) if isinstance(_drill_map, dict) else False
    _has_chamfer_templates = any(bool(v) for v in _chamfer_map.values()) if isinstance(_chamfer_map, dict) else False
    _template_warnings = []
    if not _has_hole_templates:
        _template_warnings.append('【未搜尋到孔加工模板】')
    if not _has_chamfer_templates:
        _template_warnings.append('【未搜尋到倒角模板】')
    _vision_payload = {}
    if ENABLE_VISION_LAYER:
        try:
            from smart_ai_cam_vision import vision_summary_for_init

            _vision_payload = vision_summary_for_init(runtime_state.vision_snapshot)
        except Exception as _vex:
            _vision_payload = {'enabled': True, 'ok': False, 'reason': str(_vex)}
    _feature_catalog_payload = {}
    try:
        from Smart_AI.reasoning.machining_feature_catalog import catalog_summary_for_init

        _feature_catalog_payload = catalog_summary_for_init(
            getattr(runtime_state, "feature_catalog", None)
        )
    except Exception as _fcx:
        _feature_catalog_payload = {'ok': False, 'reason': str(_fcx)}
    _contour2d_payload = {}
    try:
        from Smart_AI.perception.contour_2d_recognizer import recognition_summary_for_init

        _contour2d_payload = recognition_summary_for_init(
            getattr(runtime_state, "contour_2d_recognition", None)
        )
    except Exception as _c2x:
        _contour2d_payload = {'ok': False, 'reason': str(_c2x)}
    return json.dumps({
        'addinVersion': ADDIN_VERSION,
        'vision': _vision_payload,
        'featureCatalog': _feature_catalog_payload,
        'contour2dRecognition': _contour2d_payload,
        'fusionOfficial': _fusion_official_summary_for_init(),
        'official_pockets': _buildOfficialPocketData(mat),
        'official_slot_pockets': _buildOfficialSlotPocketData(mat),
        'official_pocket_slots': _buildOfficialPocketSlotData(mat),
        'setups': setups, 'activeSetup': active,
        'materials': list(allDrillMap.keys()), 'material': mat,
        'machines': [
            "未指定機台 (常規 12,000 RPM)", 
            "Centra 14MiB BT30 (最高 24,000 RPM)", 
            "Centra 21MiB BT30 (最高 24,000 RPM)", 
            "Victor VCP76 BBT40 (最高 12,000 RPM)", 
            "Mazak VARIAXIS i-600 BBT40 (最高 12,000 RPM)"
        ],
        'machine': getattr(runtime_state, "active_machine", "未指定機台 (常規 12,000 RPM)"),
        'topFace': tf, 'profile': pf,
        'topFaceRough': tf_rough, 'topFaceFinish': tf_finish,
        'profileRough': pf_rough, 'profileFinish': pf_finish,
        'holes': hole_rows,
        'slots': slot_rows,
        'pocket_corner_r': pcr_rows,
        'flat_depths': _scanFlatDepths(),
        'templateWarnings': _template_warnings,
        'settings': {
            'rayDiameterDeltaMM': (
                getattr(runtime_state, 'ray_diameter_delta_mm', None)
                if getattr(runtime_state, 'ray_diameter_delta_mm', None) is not None
                else ui_defaults.get('rayDiameterDeltaMM')
            ),
            'chamferInterferenceToolDiaMM': (
                float(getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None))
                if getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None) is not None
                else float(ui_defaults.get('chamferInterferenceToolDiaMM', 6.0))
            ),
            'chamferInterferenceTopDeltaTolMM': (
                float(getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None))
                if getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None) is not None
                else float(ui_defaults.get('chamferInterferenceTopDeltaTolMM', 0.05))
            ),
            'holeTopHeightMode': str(
                getattr(runtime_state, 'hole_top_height_mode', ui_defaults.get('holeTopHeightMode', 'from surface top'))
            ),
            'holeRecognitionDebug': getattr(runtime_state, "hole_debug_enabled", False),
            'slotRecognitionDebug': getattr(runtime_state, "slot_debug_enabled", False),
            'paletteWidth': FIXED_PALETTE_WIDTH,
            'paletteHeight': (_palette.height if _palette else ui_defaults.get('paletteHeight', 900)),
            'mainWidth': ui_defaults.get('mainWidth', 650),
            'mainHeight': ui_defaults.get('mainHeight', 900),
            'colHoleWidth': ui_defaults.get('colHoleWidth', 150),
            'colTemplateWidth': ui_defaults.get('colTemplateWidth', 170),
            'colCountWidth': ui_defaults.get('colCountWidth', 50),
            'colDepthWidth': ui_defaults.get('colDepthWidth', 70),
            'colDrillModeWidth': ui_defaults.get('colDrillModeWidth', 120),
            'colDrillDepthWidth': ui_defaults.get('colDrillDepthWidth', 85),
            'colReamModeWidth': ui_defaults.get('colReamModeWidth', 120),
            'colReamDepthWidth': ui_defaults.get('colReamDepthWidth', 85),
            'colPitchWidth': ui_defaults.get('colPitchWidth', 90),
            'colCalcWidth': ui_defaults.get('colCalcWidth', 120),
            'topFaceRough': ui_defaults.get('topFaceRough', ''),
            'topFaceFinish': ui_defaults.get('topFaceFinish', ''),
            'topFaceLegacy': ui_defaults.get('topFaceLegacy', ''),
            'profileRough': ui_defaults.get('profileRough', ''),
            'profileFinish': ui_defaults.get('profileFinish', ''),
            'profileLegacy': ui_defaults.get('profileLegacy', ''),
            'generalHole': ui_defaults.get('generalHole', ''),
            'tapHole': ui_defaults.get('tapHole', ''),
            'locatingHole': ui_defaults.get('locatingHole', ''),
            'countersinkHole': ui_defaults.get('countersinkHole', ''),
            'slotHole': ui_defaults.get('slotHole', ''),
            'holeChamfer': ui_defaults.get('holeChamfer', ''),
            'contourChamfer': ui_defaults.get('contourChamfer', ''),
        }
    })

