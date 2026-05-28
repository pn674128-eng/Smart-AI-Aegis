# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion, adsk.cam
import math
import os
import json
import re
import time
import traceback
import unicodedata
from smart_ai_cam_state.runtime_state import state as runtime_state
from smart_ai_cam_machining import operation_builder
from smart_ai_cam_machining import reorder_service
from smart_ai_cam_machining.geometry_utils import (
    _filter_slot_opening_planar_faces,
    _resolve_slot_loop_edges_from_tokens,
)
from Smart_AI.perception.feature_scanner import (
    SLOT_CHAIN_REVERSE_FOR_INTERIOR,
    SLOT_POCKET_TOOLPATH_INSIDE_SLOT,
    _buildOfficialPocketData,
    _buildPocketCornerRData,
    _buildSlotData,
    _executeOfficialPocketRows,
)
from smart_ai_cam_ui.diagnostics import send_diag_log, _broadcast_mcp_progress, get_main_palette
from smart_ai_cam_ui.palette_data_provider import MODE_DRILL_DEFAULT, MODE_DRILL_HOLE_BOTTOM, MODE_DRILL_STOCK_BOTTOM, MODE_DEPTH_EDIT, MODE_REAM_DEFAULT, MODE_REAM_HOLE_BOTTOM, MODE_REAM_STOCK_BOTTOM, MODE_PITCH_DEFAULT, MODE_PITCH_EDIT

_send_diag_log = send_diag_log

LARGE_HOLE_PILOT_THRESHOLD_MM = 6.5
AUTO_GENERATE_TOOLPATH_ON_EXECUTE = True
ENABLE_GLOBAL_OP_REORDER_ON_EXECUTE = True


def _rt_map(attr_name):
    """Read template index dicts from runtime_state (module __getattr__ does not apply to in-function globals)."""
    return getattr(runtime_state, attr_name, {}) or {}


def _ensure_runtime_ui():
    try:
        ui = getattr(runtime_state, "ui", None)
        if ui:
            return ui
        app = getattr(runtime_state, "app", None) or adsk.core.Application.get()
        runtime_state.app = app
        ui = app.userInterface
        runtime_state.ui = ui
        return ui
    except Exception:
        return None


def _ui_message(text: str) -> None:
    try:
        ui = _ensure_runtime_ui()
        if ui:
            ui.messageBox(str(text))
    except Exception:
        pass

# Re-route refactored builders
_createOpFromTemplate = operation_builder._createOpFromTemplate
_fast_set_all_cam_params_name_substr = operation_builder._fast_set_all_cam_params_name_substr
_patch_cad2d_all_chain_selection_compensations = operation_builder._patch_cad2d_all_chain_selection_compensations
_patch_cad2d_chain_selection_compensations_per_chain = operation_builder._patch_cad2d_chain_selection_compensations_per_chain
_slot_flip_all_chain_is_reverted_in_cad2d = operation_builder._slot_flip_all_chain_is_reverted_in_cad2d
_bind_cad2d_chain_profiles = operation_builder._bind_cad2d_chain_profiles
_bind_cad2d_chain = operation_builder._bind_cad2d_chain
_try_set_chain_selection_compensation_slug = operation_builder._try_set_chain_selection_compensation_slug
getTemplateParams = operation_builder.getTemplateParams
getToolInfoFromTemplate = operation_builder.getToolInfoFromTemplate
extractTags = operation_builder.extractTags
getOpToolType = operation_builder.getOpToolType
_is_cam_drill_operation_fast = operation_builder._is_cam_drill_operation_fast
_get_drill_tool_library_cache = operation_builder._get_drill_tool_library_cache
_clear_drill_tool_library_cache = operation_builder._clear_drill_tool_library_cache
_fresh_drill_tool_from_pick = operation_builder._fresh_drill_tool_from_pick
_build_drill_tool_candidates_from_library = operation_builder._build_drill_tool_candidates_from_library
_pick_preferred_drill_tool_for_dia = operation_builder._pick_preferred_drill_tool_for_dia
_set_param_expression = operation_builder._set_param_expression
_dump_params = operation_builder._dump_params
_dump_active_setup_ops_params = operation_builder._dump_active_setup_ops_params
_append_seed_faces_to_existing_drill_op = operation_builder._append_seed_faces_to_existing_drill_op
REUSE_EXISTING_TEMPLATE_OPS = getattr(operation_builder, 'REUSE_EXISTING_TEMPLATE_OPS', True)

def _op_tool_diameter_mm_for_pre_drill(op):
    """CAM drill 之 tool_diameter 內部單位為 cm，轉 mm。"""
    try:
        return float(op.tool.parameters.itemByName('tool_diameter').value.value) * 10.0
    except Exception:
        return None


def _register_pre_drill_drill_ops(registry, op):
    """登錄先前列已建立之鑽頭工序（僅 drill、Ø 在預鑽區間），供大孔列併入孔面。"""
    try:
        if not op.operationType == adsk.cam.OperationTypes.DrillingOperation:
            return
    except:
        return
    tok = None
    try:
        tok = op.entityToken
    except Exception:
        pass
    if tok:
        for ent in registry:
            if ent.get('token') == tok:
                return
    d = _op_tool_diameter_mm_for_pre_drill(op)
    if d is None:
        return
    try:
        min_d = getattr(runtime_state, 'PILOT_DRILL_DIAMETER_MIN_MM', 3.0)
        max_d = getattr(runtime_state, 'PILOT_DRILL_DIAMETER_MAX_MM', 6.0)
    except:
        min_d, max_d = 3.0, 6.0
    if d < min_d - 1e-9 or d > max_d + 1e-9:
        return
    registry.append({'dia_mm': float(d), 'op': op, 'token': tok})


def _select_best_pre_drill_registry_entry(registry):
    best = None
    for ent in registry or []:
        if best is None or float(ent['dia_mm']) > float(best['dia_mm']) + 1e-9:
            best = ent
    return best

def _find_dynamic_drills_for_large_hole(tmplLib, target_hole_dia):
    spot_url, pre_url, max_url = None, None, None
    spot_dia, pre_dia, max_dia = 0.0, 0.0, 0.0
    for url in tmplLib.childAssetURLs():
        try:
            tmpl = tmplLib.templateAtURL(url)
            if not tmpl: continue
            nm = tmpl.name.lower()
            desc = (tmpl.description or "").lower()
            is_spot = ('center drill' in nm or 'spot drill' in nm or '中心鑽' in nm or '定位' in nm)
            is_drill = ('drill' in nm or '鑽孔' in nm or '鑽頭' in nm or '鑚孔' in nm) and not ('中心' in nm) and not ('定位' in nm)
            d = 0.0
            m = re.search(r'[døφ直徑]\s*(\d+(?:\.\d+)?)', nm + " " + desc, re.IGNORECASE)
            if m: d = float(m.group(1))
            if is_spot:
                if d > spot_dia:
                    spot_dia = d; spot_url = url
            elif is_drill:
                if 4.0 <= d <= 8.0:
                    if d > pre_dia:
                        pre_dia = d; pre_url = url
                if d <= target_hole_dia - 0.5:
                    if d > max_dia:
                        max_dia = d; max_url = url
        except: pass
    return spot_url, pre_url, max_url


def _log_slot_bind_diag(
    design,
    setup,
    ui_row_1based,
    feat_1based,
    feat,
    valid_edges,
    filtered_opening_faces,
    face_z_ref_mm,
):
    """長條孔 execute：記錄開口面尺度與內環數的診斷日誌。"""
    try:
        ne = len([e for e in (valid_edges or []) if e and getattr(e, 'isValid', True)])
        nfo = len([f for f in (filtered_opening_faces or []) if f and getattr(f, 'isValid', True)])
        msg = (
            '[slot-bind] 列槽 %d feat=%d: chain_edges=%d opening_face_candidates=%d ref_z_mm=%r'
            % (ui_row_1based, feat_1based, ne, nfo, face_z_ref_mm)
        )
        tok = None
        try:
            tok = feat.get('opening_face_token')
        except Exception:
            pass
        if tok and design:
            from smart_ai_cam_machining.geometry_utils import _resolve_brep_face_from_token, _count_brep_face_inner_loops
            of = _resolve_brep_face_from_token(design, tok)
            if of and getattr(of, 'isValid', True):
                try:
                    ar = float(of.area)
                except Exception:
                    ar = -1.0
                ni = _count_brep_face_inner_loops(of)
                msg += ' | scan_host_face: area=%.4f(cm²) inner_loops=%d' % (ar, ni)
        for j, f in enumerate((filtered_opening_faces or [])[:2]):
            if not f or not getattr(f, 'isValid', True):
                continue
            try:
                ar = float(f.area)
            except Exception:
                ar = -1.0
            from smart_ai_cam_machining.geometry_utils import _count_brep_face_inner_loops
            ni = _count_brep_face_inner_loops(f)
            msg += ' | pick[%d]: area=%.4f inner_loops=%d' % (j, ar, ni)
        send_diag_log(msg)
    except Exception:
        pass

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
    if name == 'allDrillMap':
        return getattr(runtime_state, 'allDrillMap', {})
    if name == 'allChamferMap':
        return getattr(runtime_state, 'allChamferMap', {})
    if name == 'allSlotMap':
        return getattr(runtime_state, 'allSlotMap', {})
    if name == 'allSlotChamferMap':
        return getattr(runtime_state, 'allSlotChamferMap', {})
    if name == 'allCountersinkMap':
        return getattr(runtime_state, 'allCountersinkMap', {})
    if name == 'allTopFaceMap':
        return getattr(runtime_state, 'allTopFaceMap', {})
    if name == 'allProfileMap':
        return getattr(runtime_state, 'allProfileMap', {})
    if name == 'allTopFaceRoughMap':
        return getattr(runtime_state, 'allTopFaceRoughMap', {})
    if name == 'allTopFaceFinishMap':
        return getattr(runtime_state, 'allTopFaceFinishMap', {})
    if name == 'allProfileRoughMap':
        return getattr(runtime_state, 'allProfileRoughMap', {})
    if name == 'allProfileFinishMap':
        return getattr(runtime_state, 'allProfileFinishMap', {})
    if name == 'holeInfoList':
        return getattr(runtime_state, 'holeInfoList', [])
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def _get_template_name_cache():
    cache = getattr(runtime_state, 'template_name_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(runtime_state, 'template_name_cache', cache)
    return cache

def _clear_template_name_cache():
    _get_template_name_cache().clear()

def _get_op_clone_cache():
    cache = getattr(runtime_state, 'op_clone_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(runtime_state, 'op_clone_cache', cache)
    return cache

def _clear_op_clone_cache():
    _get_op_clone_cache().clear()

def _get_feature_face_cache():
    cache = getattr(runtime_state, 'feature_face_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(runtime_state, 'feature_face_cache', cache)
    return cache

def _clear_feature_face_cache():
    _get_feature_face_cache().clear()

def _get_op_name_cache():
    cache = getattr(runtime_state, 'op_name_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(runtime_state, 'op_name_cache', cache)
    return cache

def _clear_op_name_cache():
    _get_op_name_cache().clear()

def _clear_pocket_cache():
    try:
        runtime_state.pocket_cache_sig = ''
        runtime_state.pocket_cache_rows = []
    except:
        pass

def _cam_url_identity(u):
    if u is None:
        return ("", 0)
    try:
        s = u.toString() if hasattr(u, "toString") else ""
        s = str(s).strip()
    except Exception:
        s = ""
    try:
        return (s, id(u))
    except Exception:
        return (s, 0)

def _template_cache_key(url_obj=None, fallback=''):
    try:
        if url_obj:
            try:
                s = str(url_obj.toString()).strip()
                if s:
                    return s
            except:
                pass
    except:
        pass
    return ''

def _slot_palette_url_key_to_library_url(material, url_key_str, use_chamfer_map=False):
    if not url_key_str or not str(url_key_str).strip():
        return None
    key = str(url_key_str).strip()
    try:
        slot_key = 'allSlotChamferMap' if use_chamfer_map else 'allSlotMap'
        items = _rt_map(slot_key).get(material) or []
    except Exception:
        items = []
    for item in items:
        u = item.get('url')
        if not u:
            continue
        try:
            if _template_cache_key(u, '') == key:
                return u
        except Exception:
            pass
    return None


def _executeFromPalette(data):
    global holeInfoList, camSetup, tmplLib, bodyZRange_ref, _isExecutingPalette, des_obj
    try:
        _isExecutingPalette = True
        _ensure_runtime_ui()
        cam_obj = runtime_state.cam_obj
        des_obj = runtime_state.des_obj
        camSetup = runtime_state.cam_setup
        tmplLib = runtime_state.tmpl_lib
        holeInfoList = list(getattr(runtime_state, "holeInfoList", []) or [])
        _broadcast_mcp_progress(0, "開始 AI 智慧 CAM 編程，初始化加工特徵...")
        done = []
        t0 = time.perf_counter()
        t_apply_2d = 0.0
        t_apply_3d = 0.0
        t_param = 0.0
        t_reorder = 0.0
        t_toolpath = 0.0
        setup_name = data.get('setup', '')
        if setup_name and cam_obj:
            for i in range(cam_obj.setups.count):
                s = cam_obj.setups.item(i)
                if s.name == setup_name:
                    camSetup = s
                    break
        if not camSetup and cam_obj and cam_obj.setups.count > 0:
            camSetup = cam_obj.setups.item(0)
        if not camSetup:
            _ui_message("找不到可用 Setup，請先建立或選擇 Setup。")
            _broadcast_mcp_progress(0, "錯誤：找不到 Setup")
            return
        runtime_state.cam_setup = camSetup
        _broadcast_mcp_progress(5, "Setup「{}」— 準備套用工序…".format(camSetup.name))
        mode = str(data.get('mode', 'all') or 'all').lower()
        run2d = mode in ('2d', 'all')
        run3d = mode in ('3d', 'all')
        material = data.get('material', 'AL6061')
        hole_top_height_mode = str(data.get('holeTopHeightMode', getattr(runtime_state, 'hole_top_height_mode', 'from surface top')) or 'from surface top').lower()
        if hole_top_height_mode not in ('from surface top', 'from hole top'):
            hole_top_height_mode = 'from surface top'
        try:
            exec_ray_delta_mm = data.get('rayDiameterDeltaMM', getattr(runtime_state, 'ray_diameter_delta_mm', None))
        except:
            exec_ray_delta_mm = getattr(runtime_state, 'ray_diameter_delta_mm', None)
        try:
            exec_chamfer_tool_dia_mm = data.get('chamferInterferenceToolDiaMM', getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None))
        except:
            exec_chamfer_tool_dia_mm = getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None)
        try:
            exec_chamfer_tol_mm = data.get('chamferInterferenceTopDeltaTolMM', getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None))
        except:
            exec_chamfer_tol_mm = getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None)
        rows = data.get('rows', [])
        topFaceRough = data.get('topFaceRough', data.get('topFace', '(不使用)'))
        topFaceFinish = data.get('topFaceFinish', '(不使用)')
        profileRough = data.get('profileRough', data.get('profile', '(不使用)'))
        profileFinish = data.get('profileFinish', '(不使用)')
        
        all_new_ops = []
        op_clone_cache = _get_op_clone_cache()
        feature_face_cache = _get_feature_face_cache()
        op_name_cache = _get_op_name_cache()
        merge_buckets = {}
        merge_chamfer_buckets = {}
        clone_stats = {
            'copy_hits': 0,
            'create_calls': 0,
            'cache_miss': 0,
            'copy_miss': 0,
            'copy_errors': 0,
            'invalid_proto': 0,
        }
        feature_cache_stats = {'hit': 0, 'miss': 0}
        reuse_stats = {'name_hits': 0, 'name_miss': 0}
        perf_stats = {
            'template_at_url_s': 0.0,
            'create_from_template_s': 0.0,
            'copy_after_s': 0.0,
            'bind_seed_params_s': 0.0,
            'feature_cache_lookup_s': 0.0,
            'depth_calc_s': 0.0,
            'post_override_s': 0.0,
            'template_name_check_s': 0.0,
            'message_compose_s': 0.0,
            'row_total_s': 0.0,
            'row_count': 0,
        }
        row_timers = []
        checked_template_names = []

        def _material_matches_template_name(template_name, mat_name):
            try:
                s = str(template_name or '').strip()
            except:
                return True
            if not s:
                return True
            su = s.upper()
            tag = f'【{str(mat_name or "").upper()}】'
            if tag in su:
                return True
            # 最輕量檢測：模板名稱只要帶任一材質標記就視為可接受。
            return ('【AL6061】' in su) or ('【S50C】' in su)

        def _record_template_name(url_obj=None, fallback_name=''):
            name = _template_name_for_check_cached(url_obj, fallback_name)
            if name:
                checked_template_names.append(name)

        def _template_name_for_check_cached(url_obj=None, fallback_name=''):
            cache = _get_template_name_cache()
            cache_key = _template_cache_key(url_obj, fallback_name)
            try:
                cached = cache.get(cache_key, '') if cache_key else ''
                if cached:
                    return cached
            except:
                pass
            try:
                if url_obj and hasattr(url_obj, 'leafName'):
                    leaf = str(url_obj.leafName or '').strip()
                    if leaf:
                        if cache_key:
                            cache[cache_key] = leaf
                        return leaf
            except:
                pass
            try:
                name = str(fallback_name or '').strip()
            except:
                name = ''
            if cache_key and name:
                cache[cache_key] = name
            return name

        def _norm_template_hint(name):
            try:
                s = str(name or '').strip().lower()
            except:
                return ''
            if not s:
                return ''
            for ext in ('.json', '.template'):
                if s.endswith(ext):
                    s = s[:-len(ext)]
            return s

        def _norm_label_key(label):
            try:
                s = str(label or '').strip()
            except:
                s = ''
            if not s:
                return 'EMPTY'
            out = []
            for ch in s:
                if ch.isalnum() or ch in ('_', '-', '.'):
                    out.append(ch)
                else:
                    out.append('_')
            return ''.join(out)[:64]

        def _build_reuse_prefix(row_no, kind, label):
            return f'__SAUTO__R{int(row_no)}__{kind}__{_norm_label_key(label)}'

        def _tag_ops_with_prefix(ops, prefix):
            try:
                for i, op in enumerate(ops or [], start=1):
                    op.name = f'{prefix}#{i:02d}'
            except:
                pass

        def _collect_ops_by_prefix(prefix, allowed_types=None):
            out = []
            if not camSetup or not prefix:
                return out
            try:
                all_ops = camSetup.allOperations
                for _i in range(all_ops.count):
                    op = all_ops.item(_i)
                    try:
                        n = str(getattr(op, 'name', '') or '')
                    except:
                        n = ''
                    if not n.startswith(prefix):
                        continue
                    if allowed_types:
                        try:
                            t = getOpToolType(op)
                        except:
                            t = ''
                        if t not in allowed_types:
                            continue
                    out.append(op)
            except:
                return []
            try:
                out.sort(key=lambda _op: str(getattr(_op, 'name', '')))
            except:
                pass
            return out

        def _collect_ops_by_cached_names(cache_key, allowed_types=None):
            names = op_name_cache.get(cache_key, []) if cache_key else []
            if not names or not camSetup:
                return []
            out = []
            try:
                all_ops = camSetup.allOperations
                name_map = {}
                norm_map = {}
                def _norm_name(n):
                    try:
                        s = str(n or '').strip()
                    except:
                        return ''
                    return re.sub(r'\s*\(\d+\)\s*$', '', s)
                for _i in range(all_ops.count):
                    op = all_ops.item(_i)
                    try:
                        n = str(getattr(op, 'name', '') or '')
                    except:
                        n = ''
                    if n:
                        name_map[n] = op
                        nn = _norm_name(n)
                        if nn and nn not in norm_map:
                            norm_map[nn] = op
                for n in names:
                    op = name_map.get(str(n), None)
                    if not op:
                        op = norm_map.get(_norm_name(n), None)
                    if not op:
                        continue
                    if allowed_types:
                        try:
                            t = getOpToolType(op)
                        except:
                            t = ''
                        if t not in allowed_types:
                            continue
                    out.append(op)
            except:
                return []
            return out

        def _cache_op_names(cache_key, ops):
            if not cache_key:
                return
            out = []
            for op in (ops or []):
                try:
                    n = str(getattr(op, 'name', '') or '')
                except:
                    n = ''
                if n:
                    out.append(n)
            if out:
                op_name_cache[cache_key] = out

        def _find_existing_ops_by_template_hint(hint_name, allowed_types=None):
            hint = _norm_template_hint(hint_name)
            if not hint or not camSetup:
                return []
            out = []
            try:
                all_ops = camSetup.allOperations
                for _i in range(all_ops.count):
                    op = all_ops.item(_i)
                    try:
                        op_name = str(getattr(op, 'name', '') or '').lower()
                    except:
                        op_name = ''
                    if not op_name or hint not in op_name:
                        continue
                    if allowed_types:
                        try:
                            t = getOpToolType(op)
                        except:
                            t = ''
                        if t not in allowed_types:
                            continue
                    out.append(op)
            except:
                return []
            return out

        def _bind_highest_face_to_op(op):
            global des_obj, camSetup
            if not des_obj or not camSetup:
                return False
            try:
                wcs = camSetup.workCoordinateSystem
                origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()
                
                highest_face = None
                max_z = -99999.0
                
                bodies_to_scan = []
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
                            visible = True
                            try: visible = bool(body.isVisible)
                            except:
                                try: visible = bool(body.isLightBulbOn)
                                except: pass
                            if not visible: continue
                            bodies_to_scan.append(body)
                
                for body in bodies_to_scan:
                    for fi in range(body.faces.count):
                            face = body.faces.item(fi)
                            try:
                                geom = face.geometry
                                if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                                    continue
                                plane = adsk.core.Plane.cast(geom)
                                if not plane: continue
                                
                                normal = plane.normal
                                dot = normal.x * z_axis.x + normal.y * z_axis.y + normal.z * z_axis.z
                                if dot < 0.99:
                                    continue
                                
                                pt = face.boundingBox.minPoint
                                dx = pt.x - origin.x
                                dy = pt.y - origin.y
                                dz = pt.z - origin.z
                                z_val = dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
                                if z_val > max_z:
                                    max_z = z_val
                                    highest_face = face
                            except:
                                pass
                
                if highest_face:
                    for pi in range(op.parameters.count):
                        param = op.parameters.item(pi)
                        try:
                            if param.value and param.value.objectType == adsk.cam.CadFaceSelectionsParameterValue.classType():
                                face_val = adsk.cam.CadFaceSelectionsParameterValue.cast(param.value)
                                sels = face_val.getFaceSelections()
                                sels.clear()
                                sels.createNewFaceSelection(highest_face)
                                face_val.applyFaceSelections(sels)
                                _send_diag_log(f"[AI-CAM] 頂面幾何面已成功自動綁定至工序 '{op.name}'。")
                                return True
                        except Exception as ex:
                            _send_diag_log(f"[AI-CAM] 綁定 FaceSelections 參數異常: {ex}")
            except Exception as e:
                _send_diag_log(f"[AI-CAM] 頂面自動綁定發生異常: {e}")
            return False

        def _bind_terrace_face_to_op(op, target_z_mm, z_tol_mm=0.15):
            global des_obj, camSetup
            if not des_obj or not camSetup:
                return False
            try:
                wcs = camSetup.workCoordinateSystem
                origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()
                target_z = float(target_z_mm)
                tol = float(z_tol_mm)
                best_face = None
                best_area = -1.0

                bodies_to_scan = []
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
                            visible = True
                            try:
                                visible = bool(body.isVisible)
                            except Exception:
                                try:
                                    visible = bool(body.isLightBulbOn)
                                except Exception:
                                    pass
                            if not visible:
                                continue
                            bodies_to_scan.append(body)

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
                            dot = (
                                normal.x * z_axis.x
                                + normal.y * z_axis.y
                                + normal.z * z_axis.z
                            )
                            if dot < 0.99:
                                continue
                            pt = face.boundingBox.minPoint
                            dx = pt.x - origin.x
                            dy = pt.y - origin.y
                            dz = pt.z - origin.z
                            z_val = (dx * z_axis.x + dy * z_axis.y + dz * z_axis.z) * 10.0
                            if abs(z_val - target_z) > tol:
                                continue
                            area = float(face.area)
                            if area > best_area:
                                best_area = area
                                best_face = face
                        except Exception:
                            pass

                if best_face:
                    for pi in range(op.parameters.count):
                        param = op.parameters.item(pi)
                        try:
                            if (
                                param.value
                                and param.value.objectType
                                == adsk.cam.CadFaceSelectionsParameterValue.classType()
                            ):
                                face_val = adsk.cam.CadFaceSelectionsParameterValue.cast(param.value)
                                sels = face_val.getFaceSelections()
                                sels.clear()
                                sels.createNewFaceSelection(best_face)
                                face_val.applyFaceSelections(sels)
                                _send_diag_log(
                                    f"[AI-CAM] 階台面 Z≈{target_z:.2f}mm 已綁定至工序 '{op.name}'。"
                                )
                                return True
                        except Exception as ex:
                            _send_diag_log(f"[AI-CAM] 階台 FaceSelections 綁定異常: {ex}")
            except Exception as e:
                _send_diag_log(f"[AI-CAM] 階台面綁定異常: {e}")
            return False

        def _bind_outer_loop_to_op(op):
            global des_obj, camSetup
            if not des_obj or not camSetup:
                return False
            try:
                from Smart_AI.perception import contour_recognizer as cr

                wcs = camSetup.workCoordinateSystem
                origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()

                edges_to_bind = []
                seen_edge = set()

                def _add_edge(edge):
                    if not edge:
                        return
                    try:
                        key = edge.entityToken
                    except Exception:
                        key = str(id(edge))
                    if key in seen_edge:
                        return
                    seen_edge.add(key)
                    edges_to_bind.append(edge)

                bodies_to_scan = []
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
                            visible = True
                            try:
                                visible = bool(body.isVisible)
                            except Exception:
                                try:
                                    visible = bool(body.isLightBulbOn)
                                except Exception:
                                    pass
                            if not visible:
                                continue
                            bodies_to_scan.append(body)

                for body in bodies_to_scan:

                        top_faces = cr.get_machining_contour_faces_wcs(
                            body, origin, x_axis, y_axis, z_axis
                        )
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

                        for tf in faces_for_contour:
                            if not tf:
                                continue
                            for edge in cr.get_complete_outer_contour_edges(tf):
                                _add_edge(edge)

                if not edges_to_bind:
                    highest_face = None
                    max_z = -99999.0
                    bodies_to_scan = []
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
                                visible = True
                                try:
                                    visible = bool(body.isVisible)
                                except Exception:
                                    try:
                                        visible = bool(body.isLightBulbOn)
                                    except Exception:
                                        pass
                                if not visible:
                                    continue
                                bodies_to_scan.append(body)

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
                                    dot = (
                                        normal.x * z_axis.x
                                        + normal.y * z_axis.y
                                        + normal.z * z_axis.z
                                    )
                                    if dot < 0.99:
                                        continue
                                    pt = face.boundingBox.minPoint
                                    dx = pt.x - origin.x
                                    dy = pt.y - origin.y
                                    dz = pt.z - origin.z
                                    z_val = dx * z_axis.x + dy * z_axis.y + dz * z_axis.z
                                    if z_val > max_z:
                                        max_z = z_val
                                        highest_face = face
                                except Exception:
                                    pass
                    if highest_face:
                        for edge in cr.get_complete_outer_contour_edges(highest_face):
                            _add_edge(edge)

                if edges_to_bind:
                    corner_pt = None
                    try:
                        pts = []
                        for edge in edges_to_bind:
                            try:
                                if edge.startVertex:
                                    pts.append(edge.startVertex.geometry)
                                if edge.endVertex:
                                    pts.append(edge.endVertex.geometry)
                            except Exception:
                                pass
                        if pts:
                            corner_pt = min(pts, key=lambda p: p.x - p.y)
                    except Exception as e:
                        _send_diag_log(f"[AI-CAM] 角點計算異常: {e}")

                    for pi in range(op.parameters.count):
                        param = op.parameters.item(pi)
                        try:
                            if (
                                param.value
                                and param.value.objectType
                                == adsk.cam.CadContours2dParameterValue.classType()
                            ):
                                cad_contours = adsk.cam.CadContours2dParameterValue.cast(
                                    param.value
                                )
                                sels = cad_contours.getCurveSelections()
                                sels.clear()
                                csel = sels.createNewChainSelection()
                                csel.inputGeometry = list(edges_to_bind)
                                cad_contours.applyCurveSelections(sels)

                                if corner_pt:
                                    entry_param = op.parameters.itemByName("entryPositions")
                                    if entry_param:
                                        col = adsk.core.ObjectCollection.create()
                                        col.add(corner_pt)
                                        try:
                                            entry_param.value = col
                                        except Exception as ep_e:
                                            _send_diag_log(
                                                f"[AI-CAM] 無法設定 entryPositions: {ep_e}"
                                            )

                                _send_diag_log(
                                    f"[AI-CAM] 外輪廓邊界鏈 ({len(edges_to_bind)} 條邊，視線法) 已成功自動綁定至工序 '{op.name}'。"
                                )
                                return True
                        except Exception as ex:
                            _send_diag_log(f"[AI-CAM] 綁定 Contours2d 參數異常: {ex}")
            except Exception as e:
                _send_diag_log(f"[AI-CAM] 外輪廓自動綁定發生異常: {e}")
            return False

        def _apply_2d(name, items, title, bind_z_mm=None, terrace_spec=None):
            if name == '(不使用)' or name == '':
                return
            key_name = str(name).strip()
            chosen = next((x for x in items if str(x.get('name', '')).strip() == key_name), None)
            if not chosen:
                done.append(f'⚠️ {title} 找不到模板: {name}')
                return
            reused_ops = []
            z_suffix = ''
            if bind_z_mm is not None:
                try:
                    z_suffix = '|z{:.2f}'.format(float(bind_z_mm))
                except Exception:
                    z_suffix = ''
            reuse_key = f'{camSetup.name}|2D|{title}|{key_name}{z_suffix}'
            if REUSE_EXISTING_TEMPLATE_OPS:
                reused_ops = _collect_ops_by_cached_names(reuse_key, allowed_types=None)
            if reused_ops:
                reuse_stats['name_hits'] = int(reuse_stats.get('name_hits', 0)) + 1
                done.append(f'↪ {title} 重用既有工序: {len(reused_ops)}')
                all_new_ops.extend(reused_ops)
                return
            reuse_stats['name_miss'] = int(reuse_stats.get('name_miss', 0)) + 1
            _record_template_name(chosen.get('url'), chosen.get('rawName', chosen.get('name', name)))
            tmpl = tmplLib.templateAtURL(chosen['url'])
            if not tmpl:
                done.append(f'⚠️ {title} 模板URL無效: {name}')
                return
            newOps = camSetup.createFromCAMTemplate(tmpl)
            if newOps:
                ops_created = []
                cam_depth_ctx = data.get('camDepthContext') or data.get('cam_depth_context') or {}
                try:
                    from smart_ai_cam_machining import cam_operation_tuning as cot
                except Exception:
                    cot = None
                try:
                    for op in newOps:
                        ops_created.append(op)
                        # AI 幾何自動綁定
                        if '頂面' in title:
                            if bind_z_mm is not None:
                                _bind_terrace_face_to_op(op, bind_z_mm)
                            else:
                                _bind_highest_face_to_op(op)
                        elif '外輪廓' in title:
                            _bind_outer_loop_to_op(op)
                        if cot:
                            depth_spec = cot.depth_spec_for_2d_apply(
                                cam_depth_ctx, title, terrace_spec=terrace_spec
                            )
                            tuning = cot.tuning_for_title(cam_depth_ctx, title)
                            if depth_spec:
                                applied = cot.apply_height_spec(op, depth_spec)
                                if applied:
                                    done.append(
                                        f'[CAM深度] {title}: ' + ', '.join(applied[:4])
                                        + ('…' if len(applied) > 4 else '')
                                    )
                            if tuning:
                                tf_applied = cot.apply_spindle_feed(
                                    op, rpm=tuning.get('rpm'), feed=tuning.get('feed')
                                )
                                if tf_applied:
                                    done.append(
                                        f'[CAM參數] {title}: S/F 已套用'
                                    )
                except:
                    pass
                _cache_op_names(reuse_key, ops_created)
                done.append(f'{title}: {name} -> {len(ops_created)} 個操作')
                all_new_ops.extend(ops_created)
            else:
                done.append(f'⚠️ {title} 套用後無操作: {name}')

        if run2d:
            _t = time.perf_counter()
            terrace_ops = list(data.get('terraceFaceOps') or data.get('terrace_face_ops') or [])
            rough_items = _rt_map('allTopFaceRoughMap').get(material, [])
            finish_items = _rt_map('allTopFaceFinishMap').get(material, [])

            if terrace_ops:
                for spec in terrace_ops:
                    if not isinstance(spec, dict):
                        continue
                    kind = str(spec.get('op_kind', 'finish') or 'finish').lower()
                    tmpl = str(spec.get('template_name', '') or '').strip()
                    z_h = spec.get('z_height_mm')
                    if kind == 'rough':
                        nm = tmpl or topFaceRough
                        title = '頂面粗加工'
                        items = rough_items
                    else:
                        nm = tmpl or topFaceFinish
                        title = '頂面精加工'
                        items = finish_items
                    if nm and nm != '(不使用)':
                        _apply_2d(nm, items, title, bind_z_mm=z_h, terrace_spec=spec)
                done.append(f'多階台面：{len(terrace_ops)} 道頂面工序（Z 分層綁定）')
            else:
                _apply_2d(topFaceRough, rough_items, '頂面粗加工')
                _apply_2d(topFaceFinish, finish_items, '頂面精加工')

            _apply_2d(profileRough, _rt_map('allProfileRoughMap').get(material, []), '外輪廓粗加工')
            _apply_2d(profileFinish, _rt_map('allProfileFinishMap').get(material, []), '外輪廓精加工')
            
            # 外輪廓倒角 (Contour Chamfer)
            contourChamfer = data.get('contourChamfer', '(不使用)')
            all_chamfer_items = []
            try:
                import smart_ai_cam_templates.template_fs_cache as tfc
                items, _ = tfc.get_material_fs_entries(material)
                all_chamfer_items = [x for x in items if '倒角' in x.get('name', '') and '外' not in x.get('name', '') and '孔' not in x.get('name', '')]
                if not all_chamfer_items:
                    all_chamfer_items = [x for x in items if '倒角' in x.get('name', '')]
                if contourChamfer == '(不使用)' and all_chamfer_items:
                    contourChamfer = all_chamfer_items[0].get('name')
            except Exception as e:
                _send_diag_log(f"[AI-CAM] 取得倒角模板異常: {e}")
            _apply_2d(contourChamfer, all_chamfer_items, '外輪廓倒角')
            
            t_apply_2d += (time.perf_counter() - _t)

        if run3d:
            _t3 = time.perf_counter()
            def _d9dbg(msg):
                try:
                    _send_diag_log(msg)
                except:
                    pass
                try:
                    done.append(msg)
                except:
                    pass
            # 倒角刀干涉規則（使用者定案）：
            # 1) 孔徑 1.0~5.5mm：以「倒角刀直徑（UI 可調）」作為固定射線直徑檢測。
            # 2) 孔徑 >5.5mm：射線直徑 = 孔徑 + 倒角刀半徑。
            # first_hit_above_top_mm 只要高於孔口（含微小容差）即視為倒角干涉，
            # 不再使用固定 2.5mm，避免不同零件台階高度造成誤判。
            try:
                _ui_cfg = _load_ui_defaults()
            except:
                _ui_cfg = {}
            try:
                _cfg_tool_dia = _ui_cfg.get('chamferInterferenceToolDiaMM', 6.0)
            except:
                _cfg_tool_dia = 6.0
            try:
                _tool_dia_src = exec_chamfer_tool_dia_mm
                if _tool_dia_src is None:
                    _tool_dia_src = getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None)
                if _tool_dia_src is None:
                    _tool_dia_src = _cfg_tool_dia
                CHAMFER_TOOL_DIAMETER_MM = float(_tool_dia_src)
                if CHAMFER_TOOL_DIAMETER_MM <= 0:
                    CHAMFER_TOOL_DIAMETER_MM = 6.0
            except:
                CHAMFER_TOOL_DIAMETER_MM = 6.0
            CHAMFER_SMALL_DIA_MAX_MM = 5.5
            try:
                _cfg_tol = _ui_cfg.get('chamferInterferenceTopDeltaTolMM', 0.05)
            except:
                _cfg_tol = 0.05
            try:
                _tol_src = exec_chamfer_tol_mm
                if _tol_src is None:
                    _tol_src = getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None)
                if _tol_src is None:
                    _tol_src = _cfg_tol
                CHAMFER_INTERFERENCE_DELTA_MM = max(float(_tol_src), 0.0)
            except:
                CHAMFER_INTERFERENCE_DELTA_MM = 0.05
            try:
                _wcs_o, _wcs_x, _wcs_y, _wcs_z = camSetup.workCoordinateSystem.getAsCoordinateSystem()
            except:
                _wcs_o = _wcs_x = _wcs_y = None
                _wcs_z = adsk.core.Vector3D.create(0, 0, 1)
            try:
                _root_comp_for_ray = root_comp_ref if root_comp_ref else (des_obj.rootComponent if des_obj else None)
            except:
                _root_comp_for_ray = None

            def _hole_top_z_from_faces(faces, z_axis):
                topz = -1e9
                for _f in (faces or []):
                    try:
                        _mn, _mx = _bbox_proj_min_max(_f.boundingBox, z_axis)
                        if _mx > topz:
                            topz = _mx
                    except:
                        pass
                return topz

            def _ray_launch_point_for_faces(faces, z_axis):
                if not faces:
                    return None
                try:
                    f0 = faces[0]
                    bb = f0.boundingBox
                    cx = (bb.minPoint.x + bb.maxPoint.x) / 2.0
                    cy = (bb.minPoint.y + bb.maxPoint.y) / 2.0
                    cz = (bb.minPoint.z + bb.maxPoint.z) / 2.0
                except:
                    return None
                bmaxz = -1e9
                for _f in faces:
                    try:
                        _tok = _f.body.entityToken
                        if _tok in bodyZRange_ref:
                            _bmin, _bmax = bodyZRange_ref[_tok]
                            if _bmax > bmaxz:
                                bmaxz = _bmax
                    except:
                        pass
                if bmaxz < -1e8:
                    bmaxz = cx * z_axis.x + cy * z_axis.y + cz * z_axis.z + 1.0
                return adsk.core.Point3D.create(
                    cx + z_axis.x * (bmaxz + 1.0),
                    cy + z_axis.y * (bmaxz + 1.0),
                    cz + z_axis.z * (bmaxz + 1.0),
                )

            def _group_faces_by_hole_xy(faces, snap_tol_cm=0.05):
                """同一列 faces 依孔中心 XY 分群，供倒角干涉逐孔判定。"""
                groups = {}
                for _f in (faces or []):
                    try:
                        _bb = _f.boundingBox
                        _wx = (_bb.minPoint.x + _bb.maxPoint.x) / 2.0
                        _wy = (_bb.minPoint.y + _bb.maxPoint.y) / 2.0
                        _wz = (_bb.minPoint.z + _bb.maxPoint.z) / 2.0
                        _dx = _wx - _wcs_o.x
                        _dy = _wy - _wcs_o.y
                        _dz = _wz - _wcs_o.z
                        _lx = _dx * _wcs_x.x + _dy * _wcs_x.y + _dz * _wcs_x.z
                        _ly = _dx * _wcs_y.x + _dy * _wcs_y.y + _dz * _wcs_y.z
                        _key = (
                            round(round(_lx / snap_tol_cm) * snap_tol_cm, 4),
                            round(round(_ly / snap_tol_cm) * snap_tol_cm, 4),
                        )
                    except:
                        _key = ('unknown', 'unknown')
                    if _key not in groups:
                        groups[_key] = []
                    groups[_key].append(_f)
                return list(groups.values())

            def _check_chamfer_interference(faces, hole_dia_mm):
                """
                Returns: (skip_chamfer: bool, delta_mm: float|None, mode: str)
                mode in {'ray-small-dia', 'ray-large-dia', 'ray-no-hit', 'ray-error'}
                """
                try:
                    d_mm = float(hole_dia_mm)
                except:
                    d_mm = 0.0
                if (not faces) or (_root_comp_for_ray is None):
                    return False, None, 'ray-error'
                # 小孔：固定倒角刀直徑；大孔：孔徑 + 80% 倒角刀直徑。
                if d_mm >= 1.0 and d_mm <= CHAMFER_SMALL_DIA_MAX_MM:
                    detect_dia_mm = CHAMFER_TOOL_DIAMETER_MM
                    mode = 'ray-small-dia'
                else:
                    detect_dia_mm = d_mm + (CHAMFER_TOOL_DIAMETER_MM * 0.8)
                    mode = 'ray-large-dia'
                ray_radius_cm = max((detect_dia_mm / 2.0) / 10.0, 0.001)
                st = _ray_launch_point_for_faces(faces, _wcs_z)
                if st is None:
                    return False, None, 'ray-error'
                ray_dir = adsk.core.Vector3D.create(-_wcs_z.x, -_wcs_z.y, -_wcs_z.z)
                hit_pts = adsk.core.ObjectCollection.create()
                try:
                    ents = _root_comp_for_ray.findBRepUsingRay(
                        st,
                        ray_dir,
                        adsk.fusion.BRepEntityTypes.BRepFaceEntityType,
                        ray_radius_cm,
                        False,
                        hit_pts,
                    )
                except:
                    return False, None, 'ray-error'
                if not ents or ents.count == 0:
                    return False, None, 'ray-no-hit'
                try:
                    hp = hit_pts.item(0)
                    hit_z = hp.x * _wcs_z.x + hp.y * _wcs_z.y + hp.z * _wcs_z.z
                    top_z = _hole_top_z_from_faces(faces, _wcs_z)
                    delta_mm = (hit_z - top_z) * 10.0
                except:
                    return False, None, 'ray-error'
                return (delta_mm >= CHAMFER_INTERFERENCE_DELTA_MM), round(delta_mm, 3), mode

            # 大孔列處理時，先前列已建立之鑽頭（Ø 於預鑽區間）登錄於此；表排序上大孔在後（選項 1）。
            pre_drill_registry = []

            total_rows = len(rows)
            for i_idx, row in enumerate(rows):
                current_percent = int((i_idx / total_rows) * 100) if total_rows > 0 else 0
                row_dia_str = ""
                try:
                    idx_tmp = int(row.get('idx', -1))
                    if 0 <= idx_tmp < len(holeInfoList):
                        row_dia_str = f" Ø{holeInfoList[idx_tmp].get('dia', '')}"
                except:
                    pass
                _broadcast_mcp_progress(current_percent, f"正在生成孔加工工序{row_dia_str} ({i_idx + 1}/{total_rows})...")
                
                _row_t0 = time.perf_counter()
                idx = int(row.get('idx', -1))
                if idx < 0 or idx >= len(holeInfoList):
                    continue
                info = holeInfoList[idx]
                _is_d9 = False
                try:
                    _is_d9 = abs(float(info.get('dia', 0)) - 9.0) < 1e-6
                except:
                    _is_d9 = False
                selected_label = '(不使用)'
                tmpl_idx = int(row.get('tmplIdx', 0))
                drill_mode = row.get('drillMode', MODE_DRILL_DEFAULT)
                ream_mode = row.get('reamMode', MODE_REAM_DEFAULT)
                drill_depth_override = row.get('drillDepth', None)
                use_calc_drill_depth = bool(row.get('useCalcDrillDepth', False))
                calc_drill_depth_mm = row.get('calcDrillDepthMM', None)
                ream_depth_override = row.get('reamDepth', None)
                drill_tip_val = row.get('drillTip', info.get('through', True))
                ream_tip_val = row.get('reamTip', info.get('through', True))
                pitch_mode = row.get('pitchMode', MODE_PITCH_DEFAULT)
                pitch_val = row.get('pitchVal', 0.06)
                
                dropItems = info.get('dropItems', [])
                if _is_d9:
                    _d9dbg(
                        f'🧪D9 row={idx+1} dia={info.get("dia","")} count={info.get("count",0)} through={info.get("through",False)} '
                        f'dropItems={len(dropItems)} tmplIdx={tmpl_idx}'
                    )
                if not dropItems:
                    if _is_d9:
                        _d9dbg(f'🧪D9 row={idx+1} dropItems=0 -> skip')
                    continue
                if 0 <= tmpl_idx < len(dropItems):
                    chosen = dropItems[tmpl_idx]
                    selected_label = chosen.get('label', '(不使用)')
                else:
                    chosen = dropItems[0]
                    selected_label = chosen.get('label', '(不使用)')
                if _is_d9:
                    _d9dbg(
                        f'🧪D9 row={idx+1} selected={selected_label} hasReamer={chosen.get("hasReamer",False)} '
                        f'drillUrl={"Y" if bool(chosen.get("drillUrl")) else "N"} chamferUrl={"Y" if bool(chosen.get("chamferUrl")) else "N"}'
                    )
                if selected_label == '(不使用)':
                    if _is_d9:
                        _d9dbg(f'🧪D9 row={idx+1} selected=(不使用) -> skip')
                    continue
                
                hasReamer = chosen.get('hasReamer', False)
                _tf = time.perf_counter()
                face_cache_key = (
                    str(camSetup.name if camSetup else ''),
                    int(idx),
                    str(selected_label),
                    str(info.get('dia', '')),
                    bool(info.get('through', False)),
                    str(info.get('depth', '')),
                )
                cached_faces = feature_face_cache.get(face_cache_key, [])
                valid_cached_faces = []
                for _f in (cached_faces or []):
                    try:
                        if _f and getattr(_f, 'isValid', True):
                            valid_cached_faces.append(_f)
                    except:
                        pass
                if valid_cached_faces:
                    feature_cache_stats['hit'] = int(feature_cache_stats.get('hit', 0)) + 1
                else:
                    feature_cache_stats['miss'] = int(feature_cache_stats.get('miss', 0)) + 1
                faces = valid_cached_faces if valid_cached_faces else list(info.get('faces', []) or [])
                if faces:
                    feature_face_cache[face_cache_key] = list(faces)
                if _is_d9:
                    _d9dbg(
                        f'🧪D9 row={idx+1} faces cached={len(cached_faces or [])} validCached={len(valid_cached_faces)} '
                        f'fallbackFaces={len(info.get("faces", []) or [])} useFaces={len(faces)}'
                    )
                perf_stats['feature_cache_lookup_s'] += (time.perf_counter() - _tf)
                if not faces:
                    done.append(f'⚠️ 孔{idx+1}: 未取得孔面資料，略過 {selected_label}')
                    continue
                # 鑽／預鑽：同徑合併列只傳「一個」種子孔面；主鑽保留 selectSameDiameter，由模板自動選滿同徑孔（少做多面綁定、省時間）。倒角仍用完整 faces。
                faces_one_seed = [faces[0]]
                isThrough = info.get('through', True)
                holeDepthMM = None
                drillDepthMM = 0.0
                reamDepthMM = 0.0
                _td = time.perf_counter()
                try:
                    if use_calc_drill_depth and calc_drill_depth_mm is not None:
                        drillDepthMM = max(float(calc_drill_depth_mm), 0.0)
                    elif drill_depth_override is not None:
                        drillDepthMM = max(float(drill_depth_override), 0.0)
                except: pass
                try:
                    if ream_depth_override is not None:
                        reamDepthMM = max(float(ream_depth_override), 0.0)
                except: pass

                if not isThrough:
                    if hasReamer and reamDepthMM > 0 and chosen.get('drillUrl'):
                        toolInfo = getToolInfoFromTemplate(chosen['drillUrl'])
                        if toolInfo:
                            tip_h = float(toolInfo.get('tipHeightMM', 0.0))
                            holeDepthMM = reamDepthMM + tip_h + 0.5
                            # Reamer-driven flow: drill depth must follow calculated result.
                            drillDepthMM = max(float(holeDepthMM), 0.0)
                    elif drillDepthMM > 0:
                        holeDepthMM = drillDepthMM
                    else:
                        holeDepthMM = float(info.get('depth', 0))
                perf_stats['depth_calc_s'] += (time.perf_counter() - _td)
                useSameTopZ = False
                if chosen.get('chamferUrl') and info.get('isCBSmall', False):
                    cbZ = info.get('cbSmallZMax')
                    if cbZ is not None and bodyZRange_ref:
                        bodyZ = max(v[1] for v in bodyZRange_ref.values())
                        if abs(cbZ - bodyZ) < 0.05:
                            useSameTopZ = True

                # Stable mode: disable experimental merge path to keep per-feature semantics.
                can_merge = False
                if can_merge:
                    merge_key = (
                        str(chosen.get('drillUrl', '')),
                        str(chosen.get('chamferUrl', '')),
                        bool(useSameTopZ),
                        bool(drill_tip_val),
                        bool(ream_tip_val),
                    )
                    bucket = merge_buckets.get(merge_key)
                    if not bucket:
                        bucket = {
                            'rows': [],
                            'faces': [],
                            'selected_label': selected_label,
                            'drillUrl': chosen.get('drillUrl', ''),
                            'chamferUrl': chosen.get('chamferUrl', ''),
                            'useSameTopZ': useSameTopZ,
                            'drillTip': bool(drill_tip_val),
                            'reamTip': bool(ream_tip_val),
                        }
                        merge_buckets[merge_key] = bucket
                    bucket['rows'].append(idx + 1)
                    bucket['faces'].extend(faces)
                    continue
                skip_row_chamfer = False
                if can_merge and chosen.get('chamferUrl'):
                    c_key = (
                        str(chosen.get('chamferUrl', '')),
                        bool(useSameTopZ),
                    )
                    c_bucket = merge_chamfer_buckets.get(c_key)
                    if not c_bucket:
                        c_bucket = {
                            'rows': [],
                            'faces': [],
                            'selected_label': selected_label,
                            'chamferUrl': chosen.get('chamferUrl', ''),
                            'useSameTopZ': useSameTopZ,
                        }
                        merge_chamfer_buckets[c_key] = c_bucket
                    c_bucket['rows'].append(idx + 1)
                    c_bucket['faces'].extend(faces)
                    skip_row_chamfer = True
                # 倒角只選取「無干涉」孔面；同一列（合併孔）逐孔分群判定。
                chamfer_faces = list(faces)
                chamfer_has_interference = False
                if chosen.get('chamferUrl'):
                    keep_groups = []
                    skip_groups = []
                    for _gfaces in _group_faces_by_hole_xy(faces):
                        _skip, _delta_mm, _mode = _check_chamfer_interference(_gfaces, info.get('dia', 0))
                        if _skip:
                            skip_groups.append((_delta_mm, _mode))
                        else:
                            keep_groups.append(_gfaces)
                    chamfer_faces = []
                    for _kg in keep_groups:
                        chamfer_faces.extend(_kg)
                    if skip_groups:
                        chamfer_has_interference = True
                        if (not chamfer_faces):
                            skip_row_chamfer = True
                            _deltas = [str(x[0]) for x in skip_groups if x[0] is not None]
                            if _deltas:
                                done.append(f'孔{idx+1}: 倒角跳過（{len(skip_groups)}孔皆干涉，delta_mm={",".join(_deltas)}）')
                            else:
                                done.append(f'孔{idx+1}: 倒角跳過（{len(skip_groups)}孔皆干涉）')
                        else:
                            done.append(f'孔{idx+1}: 倒角僅套用無干涉孔面（保留{len(keep_groups)}孔，跳過{len(skip_groups)}孔）')
                
                row_ops = []
                if chosen['drillUrl']:
                    _record_template_name(chosen.get('drillUrl'), chosen.get('rawName', selected_label))
                    reused_ops = []
                    _drill_branch_ops = []
                    if REUSE_EXISTING_TEMPLATE_OPS:
                        drill_cache_key = f'{camSetup.name}|R{idx+1}|DRILL|{selected_label}'
                        reused_ops = _collect_ops_by_cached_names(drill_cache_key, allowed_types=['drill', 'reamer', 'flat end mill'])
                        if (not reused_ops):
                            drill_prefix = _build_reuse_prefix(idx + 1, 'DRILL', selected_label)
                            reused_ops = _collect_ops_by_prefix(drill_prefix, allowed_types=['drill', 'reamer', 'flat end mill'])
                    if _is_d9:
                        _d9dbg(f'🧪D9 row={idx+1} drillReuse={len(reused_ops)}')
                    if reused_ops:
                        reuse_stats['name_hits'] = int(reuse_stats.get('name_hits', 0)) + 1
                        row_ops.extend(reused_ops)
                        all_new_ops.extend(reused_ops)
                        _drill_branch_ops = list(reused_ops)
                        done.append(f'↪ 孔{idx+1} 鑽孔重用既有工序: {len(reused_ops)}')
                    else:
                        reuse_stats['name_miss'] = int(reuse_stats.get('name_miss', 0)) + 1
                        _tu = time.perf_counter()
                        tmpl = tmplLib.templateAtURL(chosen['drillUrl'])
                        perf_stats['template_at_url_s'] += (time.perf_counter() - _tu)
                        if tmpl:
                            newOps = _createOpFromTemplate(
                                camSetup,
                                tmpl,
                                faces_one_seed,
                                isThrough,
                                holeDepthMM,
                                template_url=f'{camSetup.name}|drill|{_template_cache_key(chosen.get("drillUrl"), selected_label)}',
                                clone_cache=op_clone_cache,
                                clone_stats=clone_stats,
                                select_same_diameter=True,
                                perf_stats=perf_stats,
                            )
                            if newOps:
                                _cache_op_names(f'{camSetup.name}|R{idx+1}|DRILL|{selected_label}', newOps)
                                row_ops.extend(newOps)
                                all_new_ops.extend(newOps)
                                _drill_branch_ops = list(newOps)
                    # 大孔通孔預鑽：先完成本列主鑽／重用鑽之模板建立，再併入先前小徑鑽，減少與 createFromCAMTemplate 串行重算。
                    try:
                        _hd_pre = float(info.get('dia', 0))
                    except Exception:
                        try:
                            _hd_pre = float(re.sub(r'[^0-9.]', '', str(info.get('dia', '') or '')))
                        except Exception:
                            _hd_pre = 0.0
                    if (
                        _hd_pre > 13.0
                        and chosen.get('hasMillBore', False)
                    ):
                        spot_url, pre_url, max_url = _find_dynamic_drills_for_large_hole(tmplLib, _hd_pre)
                        for d_url, d_name, d_depth_mode, d_depth_offset in [
                            (spot_url, '中心鑽', "'from hole top'", "'-1mm'"),
                            (pre_url, '預鑽', None, None), 
                            (max_url, '最大鑽', None, None)
                        ]:
                            if d_url:
                                _tu = time.perf_counter()
                                tmpl = tmplLib.templateAtURL(d_url)
                                perf_stats['template_at_url_s'] += (time.perf_counter() - _tu)
                                if tmpl:
                                    nops = _createOpFromTemplate(
                                        camSetup, tmpl, faces_one_seed, isThrough, holeDepthMM,
                                        clone_cache=op_clone_cache, clone_stats=clone_stats,
                                        select_same_diameter=True, perf_stats=perf_stats
                                    )
                                    if nops:
                                        row_ops.extend(nops)
                                        all_new_ops.extend(nops)
                                        done.append(f'孔{idx+1}: 大孔協議 - 自動生成 {d_name}')
                                        if d_name == '中心鑽':
                                            for nop in nops:
                                                try:
                                                    nop.parameters.itemByName('bottomHeight_mode').expression = d_depth_mode
                                                    nop.parameters.itemByName('bottomHeight_offset').expression = d_depth_offset
                                                except: pass

                    elif (
                        _hd_pre > LARGE_HOLE_PILOT_THRESHOLD_MM + 1e-9
                        and isThrough
                        and (not bool(info.get('isCBLarge', False)))
                        and bool(chosen.get('hasDrill', False))
                    ):
                        _p_ent = _select_best_pre_drill_registry_entry(pre_drill_registry)
                        if _p_ent and _p_ent.get('op'):
                            if _append_seed_faces_to_existing_drill_op(_p_ent['op'], faces_one_seed, True):
                                _pd = float(_p_ent['dia_mm'])
                                done.append(
                                    f'孔{idx+1}: 預鑽 併入既有 Ø{_pd:g}mm 鑽孔工序（同徑自動選孔）'
                                )
                    for _opz in _drill_branch_ops:
                        _register_pre_drill_drill_ops(pre_drill_registry, _opz)
                if chosen['chamferUrl'] and (not skip_row_chamfer):
                    _record_template_name(chosen.get('chamferUrl'), chosen.get('rawName', selected_label))
                    useSameTopZ = False
                    if info.get('isCBSmall', False):
                        cbZ = info.get('cbSmallZMax')
                        if cbZ is not None and bodyZRange_ref:
                            bodyZ = max(v[1] for v in bodyZRange_ref.values())
                            if abs(cbZ - bodyZ) < 0.05:
                                useSameTopZ = True
                    reused_ops = []
                    # 有干涉時要精準綁「無干涉孔面」，不可沿用可能為同徑自動選取的舊倒角工序。
                    if REUSE_EXISTING_TEMPLATE_OPS and (not chamfer_has_interference):
                        chamfer_cache_key = f'{camSetup.name}|R{idx+1}|CHAMFER|{selected_label}'
                        reused_ops = _collect_ops_by_cached_names(chamfer_cache_key, allowed_types=['chamfer mill'])
                        if (not reused_ops):
                            chamfer_prefix = _build_reuse_prefix(idx + 1, 'CHAMFER', selected_label)
                            reused_ops = _collect_ops_by_prefix(chamfer_prefix, allowed_types=['chamfer mill'])
                    if _is_d9:
                        _d9dbg(f'🧪D9 row={idx+1} chamferReuse={len(reused_ops)}')
                    if reused_ops:
                        reuse_stats['name_hits'] = int(reuse_stats.get('name_hits', 0)) + 1
                        row_ops.extend(reused_ops)
                        all_new_ops.extend(reused_ops)
                        done.append(f'↪ 孔{idx+1} 倒角重用既有工序: {len(reused_ops)}')
                    else:
                        reuse_stats['name_miss'] = int(reuse_stats.get('name_miss', 0)) + 1
                        _tu = time.perf_counter()
                        tmpl = tmplLib.templateAtURL(chosen['chamferUrl'])
                        perf_stats['template_at_url_s'] += (time.perf_counter() - _tu)
                        if tmpl:
                            newOps = _createOpFromTemplate(
                                camSetup,
                                tmpl,
                                chamfer_faces,
                                isThrough,
                                holeDepthMM,
                                useSameTopZ=useSameTopZ,
                                template_url=f'{camSetup.name}|chamfer|{_template_cache_key(chosen.get("chamferUrl"), selected_label)}',
                                clone_cache=op_clone_cache,
                                clone_stats=clone_stats,
                                bind_all_faces=chamfer_has_interference,
                                select_same_diameter=(not chamfer_has_interference),
                                perf_stats=perf_stats,
                            )
                            if newOps:
                                _cache_op_names(f'{camSetup.name}|R{idx+1}|CHAMFER|{selected_label}', newOps)
                                row_ops.extend(newOps)
                                all_new_ops.extend(newOps)
                
                done.append(f'孔{idx+1}: {selected_label} -> {len(row_ops)} 個操作')
                if _is_d9:
                    try:
                        _types = [getOpToolType(_op) for _op in (row_ops or [])]
                    except:
                        _types = []
                    _d9dbg(f'🧪D9 row={idx+1} rowOps={len(row_ops)} types={",".join(_types)}')
                
                for op in row_ops:
                    _tp = time.perf_counter()
                    opType = getOpToolType(op)
                    params = op.parameters
                    param_cache = {}

                    def _p(name):
                        if name in param_cache:
                            return param_cache[name]
                        try:
                            pv = params.itemByName(name) if params else None
                        except:
                            pv = None
                        param_cache[name] = pv
                        return pv

                    def _fast_set_local(name, expr):
                        pv = _p(name)
                        if not pv:
                            return False
                        try:
                            if str(getattr(pv, 'expression', '')) == expr:
                                return True
                        except:
                            pass
                        try:
                            pv.expression = expr
                            return True
                        except:
                            return False
                    # 設置鑽尖/鉸尖突破
                    if opType in ['drill', 'reamer']:
                        try:
                            val = drill_tip_val if opType == 'drill' else ream_tip_val
                            _fast_set_local('drillTipThroughBottom', 'true' if val else 'false')
                            if val:
                                _fast_set_local('bottomHeight_offset', '0mm')
                        except: pass
                    
                    # 設置深度模式
                    try:
                        if opType in ['center drill', 'drill', 'reamer']:
                            _fast_set_local('topHeight_mode', f"'{hole_top_height_mode}'")
                        if opType == 'center drill':
                            _fast_set_local('bottomHeight_mode', f"'{hole_top_height_mode}'")
                        elif opType == 'drill':
                            if drill_mode == MODE_DRILL_HOLE_BOTTOM:
                                _fast_set_local('bottomHeight_mode', "'from hole bottom'")
                                if val:
                                    _fast_set_local('bottomHeight_offset', '0mm')
                                elif drillDepthMM > 0:
                                    _fast_set_local('bottomHeight_offset', str(drillDepthMM) + 'mm')
                                if drillDepthMM > 0:
                                    _fast_set_local('breakThroughDepth', str(drillDepthMM) + 'mm')
                            elif drill_mode == MODE_DRILL_STOCK_BOTTOM:
                                _fast_set_local('bottomHeight_mode', "'from stock bottom'")
                                if val:
                                    _fast_set_local('bottomHeight_offset', '0mm')
                                elif drillDepthMM > 0:
                                    _fast_set_local('bottomHeight_offset', str(drillDepthMM) + 'mm')
                                if drillDepthMM > 0:
                                    _fast_set_local('breakThroughDepth', str(drillDepthMM) + 'mm')
                            elif drill_mode == MODE_DEPTH_EDIT:
                                if val:
                                    _fast_set_local('bottomHeight_offset', '0mm')
                                else:
                                    _fast_set_local('bottomHeight_offset', '-' + str(drillDepthMM) + 'mm')
                        elif opType == 'reamer':
                            if ream_mode == MODE_REAM_HOLE_BOTTOM:
                                _fast_set_local('bottomHeight_mode', "'from hole bottom'")
                                if val:
                                    _fast_set_local('bottomHeight_offset', '0mm')
                                elif reamDepthMM > 0:
                                    _fast_set_local('bottomHeight_offset', str(reamDepthMM) + 'mm')
                                if reamDepthMM > 0:
                                    _fast_set_local('breakThroughDepth', str(reamDepthMM) + 'mm')
                            elif ream_mode == MODE_REAM_STOCK_BOTTOM:
                                _fast_set_local('bottomHeight_mode', "'from stock bottom'")
                                if val:
                                    _fast_set_local('bottomHeight_offset', '0mm')
                                elif reamDepthMM > 0:
                                    _fast_set_local('bottomHeight_offset', str(reamDepthMM) + 'mm')
                                if reamDepthMM > 0:
                                    _fast_set_local('breakThroughDepth', str(reamDepthMM) + 'mm')
                            elif ream_mode == MODE_DEPTH_EDIT:
                                if val:
                                    _fast_set_local('bottomHeight_offset', '0mm')
                                else:
                                    _fast_set_local('bottomHeight_offset', '-' + str(reamDepthMM) + 'mm')
                    except: pass

                    # 設置節距
                    if pitch_mode == MODE_PITCH_EDIT:
                        for op in row_ops:
                            if getOpToolType(op) == 'flat end mill':
                                try:
                                    p2 = op.parameters
                                    p_pitch = p2.itemByName('pitch') if p2 else None
                                    if p_pitch:
                                        expr = str(pitch_val) + 'mm'
                                        if str(getattr(p_pitch, 'expression', '')) != expr:
                                            p_pitch.expression = expr
                                except: pass
                    _post_elapsed = (time.perf_counter() - _tp)
                    t_param += _post_elapsed
                    perf_stats['post_override_s'] += _post_elapsed
                row_elapsed = time.perf_counter() - _row_t0
                perf_stats['row_total_s'] += row_elapsed
                perf_stats['row_count'] += 1
                row_timers.append((idx + 1, row_elapsed, selected_label))

            for _, bucket in merge_buckets.items():
                merged_ops = []
                m_faces = bucket.get('faces', [])
                if not m_faces:
                    continue
                if bucket.get('drillUrl'):
                    _record_template_name(bucket.get('drillUrl'), bucket.get('selected_label', ''))
                    _tu = time.perf_counter()
                    tmpl = tmplLib.templateAtURL(bucket.get('drillUrl'))
                    perf_stats['template_at_url_s'] += (time.perf_counter() - _tu)
                    if tmpl:
                        newOps = _createOpFromTemplate(
                            camSetup,
                            tmpl,
                            m_faces,
                            True,
                            None,
                            template_url=f'{camSetup.name}|drill|{_template_cache_key(bucket.get("drillUrl"), bucket.get("selected_label", ""))}',
                            clone_cache=op_clone_cache,
                            clone_stats=clone_stats,
                            bind_all_faces=True,
                            perf_stats=perf_stats,
                        )
                        if newOps:
                            merged_ops.extend(newOps)
                            all_new_ops.extend(newOps)
                if bucket.get('chamferUrl'):
                    _record_template_name(bucket.get('chamferUrl'), bucket.get('selected_label', ''))
                    _tu = time.perf_counter()
                    tmpl = tmplLib.templateAtURL(bucket.get('chamferUrl'))
                    perf_stats['template_at_url_s'] += (time.perf_counter() - _tu)
                    if tmpl:
                        newOps = _createOpFromTemplate(
                            camSetup,
                            tmpl,
                            m_faces,
                            True,
                            None,
                            useSameTopZ=bool(bucket.get('useSameTopZ', False)),
                            template_url=f'{camSetup.name}|chamfer|{_template_cache_key(bucket.get("chamferUrl"), bucket.get("selected_label", ""))}',
                            clone_cache=op_clone_cache,
                            clone_stats=clone_stats,
                            bind_all_faces=True,
                            perf_stats=perf_stats,
                        )
                        if newOps:
                            merged_ops.extend(newOps)
                            all_new_ops.extend(newOps)
                for op in merged_ops:
                    _tp = time.perf_counter()
                    opType = getOpToolType(op)
                    if opType in ['drill', 'reamer']:
                        try:
                            val = bucket.get('drillTip', True) if opType == 'drill' else bucket.get('reamTip', True)
                            p3 = op.parameters
                            if p3:
                                p_tip = p3.itemByName('drillTipThroughBottom')
                                if p_tip:
                                    expr_tip = 'true' if val else 'false'
                                    if str(getattr(p_tip, 'expression', '')) != expr_tip:
                                        p_tip.expression = expr_tip
                            if val:
                                if p3:
                                    p_off = p3.itemByName('bottomHeight_offset')
                                    if p_off and str(getattr(p_off, 'expression', '')) != '0mm':
                                        p_off.expression = '0mm'
                        except:
                            pass
                    _post_elapsed = (time.perf_counter() - _tp)
                    t_param += _post_elapsed
                    perf_stats['post_override_s'] += _post_elapsed
                done.append(f'孔{",".join(str(x) for x in bucket.get("rows", []))}: {bucket.get("selected_label", "")} -> {len(merged_ops)} 個操作（合併）')
            for _, c_bucket in merge_chamfer_buckets.items():
                m_faces = c_bucket.get('faces', [])
                if not m_faces or not c_bucket.get('chamferUrl'):
                    continue
                _record_template_name(c_bucket.get('chamferUrl'), c_bucket.get('selected_label', ''))
                _tu = time.perf_counter()
                tmpl = tmplLib.templateAtURL(c_bucket.get('chamferUrl'))
                perf_stats['template_at_url_s'] += (time.perf_counter() - _tu)
                created = []
                if tmpl:
                    newOps = _createOpFromTemplate(
                        camSetup,
                        tmpl,
                        m_faces,
                        True,
                        None,
                        useSameTopZ=bool(c_bucket.get('useSameTopZ', False)),
                        template_url=f'{camSetup.name}|chamfer-merge|{_template_cache_key(c_bucket.get("chamferUrl"), c_bucket.get("selected_label", ""))}',
                        clone_cache=op_clone_cache,
                        clone_stats=clone_stats,
                        bind_all_faces=True,
                        perf_stats=perf_stats,
                    )
                    if newOps:
                        created.extend(newOps)
                        all_new_ops.extend(newOps)
                done.append(f'孔{",".join(str(x) for x in c_bucket.get("rows", []))}: 倒角合併 -> {len(created)} 個操作（合併）')

            # 長條孔：依面板 slotRows × _buildSlotData(..., include_features=True)；
            # 同列多槽合併為「各一」槽粗／輪廓倒角工序，以多條 ChainSelection（loop_edges）寫入 pockets／contours。
            try:
                slot_payload = data.get('slotRows') or []
                if slot_payload and tmplLib and camSetup:
                    slot_dis = _buildSlotData(material, include_features=True)
                    for srow in slot_payload:
                        if srow.get("skip_execute"):
                            continue
                        si = int(srow.get('idx', -1))
                        if si < 0 or si >= len(slot_dis):
                            continue
                        ui_slot = slot_dis[si]
                        tmpl_idx = int(srow.get('tmplIdx', 0))
                        drop_items = ui_slot.get('dropItems') or []
                        if tmpl_idx < 0 or tmpl_idx >= len(drop_items):
                            tmpl_idx = 0
                        ch = drop_items[tmpl_idx] if drop_items else {}
                        if str(ch.get('mode', '') or '') == '不使用':
                            continue
                        su = str(ch.get('slotUrl', '') or '').strip()
                        cu = str(ch.get('chamferUrl', '') or '').strip()
                        if not su and not cu:
                            continue
                        sfeats = ui_slot.get('slot_features') or []
                        if not sfeats:
                            done.append(f'⚠️ 長條孔列{si + 1}: 無開口層幾何（請重掃或檢查辨識），略過')
                            continue
                        slot_through = bool(ui_slot.get('through', False))
                        depth_slot_mm = float(ui_slot.get('depth_mm', 0.0))
                        # 同列多槽：各槽 loop_edges 合併為「同一 pocket2d／chamfer2d 工序」之多條 ChainSelection（非每槽各建工序）。
                        chain_profiles = []
                        token_profiles = []
                        opening_faces_row = []
                        center_ref_mm_row = []
                        for fi, feat in enumerate(sfeats):
                            faces_feat = list(feat.get('faces') or [])
                            edges_feat = list(feat.get('loop_edges') or [])
                            valid_faces = []
                            anchor_face = None
                            _host_f = None
                            try:
                                _host_f = feat.get('host_opening_face')
                                if _host_f and not getattr(_host_f, 'isValid', True):
                                    _host_f = None
                            except Exception:
                                _host_f = None
                            if _host_f is not None:
                                valid_faces = [_host_f]
                                anchor_face = _host_f
                            else:
                                for _f in faces_feat:
                                    try:
                                        if _f and getattr(_f, 'isValid', True):
                                            valid_faces.append(_f)
                                    except Exception:
                                        pass
                            valid_edges = []
                            for _e in edges_feat:
                                try:
                                    if _e and getattr(_e, 'isValid', True):
                                        valid_edges.append(_e)
                                except Exception:
                                    pass
                            if len(valid_edges) < 2:
                                valid_edges = _resolve_slot_loop_edges_from_tokens(
                                    des_obj, feat.get('loop_edge_tokens') or []
                                )
                            if len(valid_edges) < 2:
                                done.append(
                                    f'⚠️ 長條孔列{si + 1} 槽{fi + 1}: loop_edges 不足 2，無法組 ChainSelection，略過該槽'
                                )
                                continue
                            fz_ref = None
                            try:
                                fz_ref = feat.get('face_z_wcs_mm')
                            except Exception:
                                fz_ref = None
                            if valid_faces and _host_f is None:
                                valid_faces = _filter_slot_opening_planar_faces(
                                    valid_faces, camSetup, fz_ref
                                )
                            if not anchor_face and valid_faces:
                                try:
                                    anchor_face = valid_faces[0]
                                except Exception:
                                    anchor_face = None
                            _log_slot_bind_diag(
                                des_obj,
                                camSetup,
                                si + 1,
                                fi + 1,
                                feat,
                                valid_edges,
                                valid_faces,
                                fz_ref,
                            )
                            chain_profiles.append(valid_edges)
                            token_profiles.append(list(feat.get('loop_edge_tokens') or []))
                            opening_faces_row.append(anchor_face)
                            try:
                                _cxv = float(feat.get('cx_mm', feat.get('cx')))
                                _cyv = float(feat.get('cy_mm', feat.get('cy')))
                                _fzz = feat.get('face_z_wcs_mm', fz_ref)
                                _fzzf = float(_fzz) if _fzz is not None else None
                                center_ref_mm_row.append((_cxv, _cyv, _fzzf))
                            except Exception:
                                center_ref_mm_row.append(None)
                        if not chain_profiles:
                            done.append(
                                f'⚠️ 長條孔列{si + 1}: 無可用槽邊鏈（每槽至少 2 條 loop_edges），略過'
                            )
                            continue
                        nk = len(chain_profiles)
                        try:
                            _nctr = sum(1 for x in center_ref_mm_row if x is not None)
                            _send_diag_log(
                                '[slot-bind] execute 列%d: 邊鏈數=%d center_ref_mm 筆數=%d（非空=%d）將傳 slot_chain_center_ref_mm=%s'
                                % (
                                    si + 1,
                                    nk,
                                    len(center_ref_mm_row),
                                    _nctr,
                                    'yes'
                                    if (
                                        len(center_ref_mm_row) == nk
                                        and _nctr > 0
                                    )
                                    else 'no',
                                )
                            )
                        except Exception:
                            pass
                        if su:
                            url_slot = _slot_palette_url_key_to_library_url(material, su, False)
                            _record_template_name(url_slot, '')
                            _tu_s = time.perf_counter()
                            tmpl_slot = tmplLib.templateAtURL(url_slot) if url_slot else None
                            perf_stats['template_at_url_s'] += (time.perf_counter() - _tu_s)
                            if tmpl_slot:
                                new_slot_ops = _createOpFromTemplate(
                                    camSetup,
                                    tmpl_slot,
                                    [],
                                    isThrough=slot_through,
                                    holeDepthMM=(None if slot_through else depth_slot_mm),
                                    template_url=f'{camSetup.name}|slot|{_template_cache_key(url_slot, str(si))}|merged',
                                    clone_cache=op_clone_cache,
                                    clone_stats=clone_stats,
                                    bind_all_faces=False,
                                    select_same_diameter=False,
                                    slot_profile_edges=None,
                                    perf_stats=perf_stats,
                                    slot_chain_profiles=chain_profiles,
                                    slot_chain_token_profiles=token_profiles,
                                    slot_chains_only=True,
                                    slot_chain_reverse_order=(
                                        SLOT_POCKET_TOOLPATH_INSIDE_SLOT
                                        and SLOT_CHAIN_REVERSE_FOR_INTERIOR
                                    ),
                                    slot_chain_opening_faces=(
                                        opening_faces_row
                                        if len(opening_faces_row) == len(chain_profiles)
                                        else None
                                    ),
                                    slot_chain_center_ref_mm=(
                                        center_ref_mm_row
                                        if len(center_ref_mm_row) == len(chain_profiles)
                                        else None
                                    ),
                                )
                                if new_slot_ops:
                                    all_new_ops.extend(new_slot_ops)
                                    done.append(
                                        f'長條孔列{si + 1}: 槽模板已建立 {len(new_slot_ops)} 道（{nk} 條腰形槽邊鏈→同一工序多輪廓）'
                                    )
                                else:
                                    done.append(f'⚠️ 長條孔列{si + 1}: 槽模板未產生工序（請檢查模板內容）')
                            else:
                                done.append(
                                    f'⚠️ 長條孔列{si + 1}: 槽模板無法載入（鍵未對應庫 URL，請重掃或檢查材質模板）'
                                    if not url_slot
                                    else f'⚠️ 長條孔列{si + 1}: 槽模板 URL 無效'
                                )
                        if cu:
                            url_cf = _slot_palette_url_key_to_library_url(material, cu, True)
                            _record_template_name(url_cf, '')
                            _tu_c = time.perf_counter()
                            tmpl_cf = tmplLib.templateAtURL(url_cf) if url_cf else None
                            perf_stats['template_at_url_s'] += (time.perf_counter() - _tu_c)
                            if tmpl_cf:
                                new_cf_ops = _createOpFromTemplate(
                                    camSetup,
                                    tmpl_cf,
                                    [],
                                    True,
                                    None,
                                    useSameTopZ=False,
                                    template_url=f'{camSetup.name}|slot-chamfer|{_template_cache_key(url_cf, str(si))}|merged',
                                    clone_cache=op_clone_cache,
                                    clone_stats=clone_stats,
                                    bind_all_faces=False,
                                    select_same_diameter=False,
                                    slot_profile_edges=None,
                                    perf_stats=perf_stats,
                                    slot_chain_profiles=chain_profiles,
                                    slot_chain_token_profiles=token_profiles,
                                    slot_chains_only=True,
                                    slot_chain_reverse_order=(
                                        SLOT_POCKET_TOOLPATH_INSIDE_SLOT
                                        and SLOT_CHAIN_REVERSE_FOR_INTERIOR
                                    ),
                                    slot_chain_opening_faces=(
                                        opening_faces_row
                                        if len(opening_faces_row) == len(chain_profiles)
                                        else None
                                    ),
                                    slot_chain_center_ref_mm=(
                                        center_ref_mm_row
                                        if len(center_ref_mm_row) == len(chain_profiles)
                                        else None
                                    ),
                                )
                                if new_cf_ops:
                                    all_new_ops.extend(new_cf_ops)
                                    done.append(
                                        f'長條孔列{si + 1}: 輪廓倒角已建立 {len(new_cf_ops)} 道（{nk} 條邊鏈→同一工序多輪廓）'
                                    )
                                else:
                                    done.append(f'⚠️ 長條孔列{si + 1}: 輪廓倒角模板未產生工序（請檢查模板內容）')
                            else:
                                done.append(
                                    f'⚠️ 長條孔列{si + 1}: 輪廓倒角模板無法載入（鍵未對應庫 URL）'
                                    if not url_cf
                                    else f'⚠️ 長條孔列{si + 1}: 輪廓倒角模板 URL 無效'
                                )
            except Exception as _slot_ex:
                done.append(f'⚠️ 長條孔套用失敗: {_slot_ex}')

            # 口袋槽 R 角（獨立表）：預設 (不使用)；選一般鑽模板時與孔列相同以柱面種子綁定。
            try:
                pcr_payload = data.get('pocketCornerRRows') or []
                if pcr_payload and tmplLib and camSetup:
                    pcr_ui = _buildPocketCornerRData(material, include_faces=True)
                    for prow in pcr_payload:
                        if prow.get('skip_execute'):
                            continue
                        si = int(prow.get('idx', -1))
                        if si < 0 or si >= len(pcr_ui):
                            continue
                        ui_row = pcr_ui[si]
                        tmpl_idx = int(prow.get('tmplIdx', 0))
                        drop_items = ui_row.get('dropItems') or []
                        if tmpl_idx < 0 or tmpl_idx >= len(drop_items):
                            tmpl_idx = 0
                        ch = drop_items[tmpl_idx] if drop_items else {}
                        if str(ch.get('label', '') or '') == '(不使用)':
                            continue
                        du = str(ch.get('drillUrl', '') or '').strip()
                        if not du:
                            continue
                        faces = list(ui_row.get('faces') or [])
                        if not faces:
                            done.append(f'⚠️ 角R列{si + 1}: 無柱面資料，略過')
                            continue
                        faces_one_seed = [faces[0]]
                        _record_template_name(du, str(ch.get('label', '') or ''))
                        _tu_p = time.perf_counter()
                        tmpl_p = tmplLib.templateAtURL(du)
                        perf_stats['template_at_url_s'] += (time.perf_counter() - _tu_p)
                        if tmpl_p:
                            new_pcr = _createOpFromTemplate(
                                camSetup,
                                tmpl_p,
                                faces_one_seed,
                                True,
                                None,
                                template_url=f'{camSetup.name}|pocket-corner-r|{_template_cache_key(du, str(si))}',
                                clone_cache=op_clone_cache,
                                clone_stats=clone_stats,
                                select_same_diameter=True,
                                perf_stats=perf_stats,
                            )
                            if new_pcr:
                                all_new_ops.extend(new_pcr)
                                done.append(
                                    f'角R列{si + 1}: R{ui_row.get("r_mm", "")}mm 鑽模板 -> {len(new_pcr)} 個操作'
                                )
                            else:
                                done.append(f'⚠️ 角R列{si + 1}: 鑽模板未產生工序')
                        else:
                            done.append(f'⚠️ 角R列{si + 1}: 鑽模板無法載入')
            except Exception as _pcr_ex:
                done.append(f'⚠️ 角R套用失敗: {_pcr_ex}')

            # Fusion 官方 RecognizedPocket：2D 邊鏈／3D 底面（執行期重新 recognizePockets）。
            try:
                op_payload = list(data.get('officialPocketRows') or [])
                op_payload.extend(data.get('officialSlotPocketRows') or [])
                op_payload.extend(data.get('officialPocketSlotRows') or [])
                if op_payload and tmplLib and camSetup:
                    op_ui = _buildOfficialPocketData(material)
                    _executeOfficialPocketRows(
                        op_payload,
                        op_ui,
                        material,
                        done,
                        all_new_ops,
                        op_clone_cache,
                        clone_stats,
                        perf_stats,
                    )
            except Exception as _op_ex:
                done.append(f'⚠️ 官方口袋套用失敗: {_op_ex}')

            t_apply_3d += (time.perf_counter() - _t3)

        # 生成刀路須排在「全局 moveAfter 排序」之前：否則大量工序時排序先跑數秒，
        # 使用者會覺得工序已建好卻遲遲不開始算刀（實為腳本尚未呼叫 generateToolpath）。
        # 一次納入目前 Setup 內全部工序整批觸發（已定案保留）。
        if AUTO_GENERATE_TOOLPATH_ON_EXECUTE and all_new_ops and camSetup and cam_obj:
            _tt = time.perf_counter()
            try:
                adsk.doEvents()
            except Exception:
                pass
            col = adsk.core.ObjectCollection.create()
            all_ops_now = camSetup.allOperations
            for i in range(all_ops_now.count):
                try:
                    col.add(all_ops_now.item(i))
                except Exception:
                    pass
            if col.count > 0:
                try:
                    cam_obj.generateToolpath(col)
                    done.append(f'✅ 已觸發目前 Setup 刀路生成（共 {col.count} 道工序）')
                except Exception:
                    done.append('⚠️ Setup 刀路生成失敗，請於製造環境手動生成刀路')
            t_toolpath += (time.perf_counter() - _tt)
        elif all_new_ops:
            done.append(f'⏭️ 已建立 {len(all_new_ops)} 個新操作（快速模式：未自動生成刀路）')

        # 全局刀具排序（大量工序時較慢）；已於上方先觸發刀路，此處僅調整工序樹順序。
        if ENABLE_GLOBAL_OP_REORDER_ON_EXECUTE:
            _tr = time.perf_counter()
            n_ops = reorder_service.reorder_setup_operations(camSetup)
            done.append(f'\n刀具排序完成: {n_ops} 個操作')
            t_reorder += (time.perf_counter() - _tr)
        else:
            done.append('\n刀具排序略過（快速模式）')

        _tn = time.perf_counter()
        mismatch = [n for n in checked_template_names if not _material_matches_template_name(n, material)]
        perf_stats['template_name_check_s'] += (time.perf_counter() - _tn)
        if mismatch:
            done.append(f'⚠️ 材質模板名稱核對：發現 {len(mismatch)} 筆可能非 {material}')
            preview = mismatch[:5]
            done.extend([f' - {n}' for n in preview])
            if len(mismatch) > len(preview):
                done.append(f' ... 其餘 {len(mismatch) - len(preview)} 筆省略')
        else:
            done.append(f'✅ 材質模板名稱核對通過（{material}）')

        total = time.perf_counter() - t0
        done.append(f'⏱️ 總耗時 {total:.2f} 秒')

        try:
            from Smart_AI.reasoning.ai_training import record_execute_training

            tr = record_execute_training(
                data,
                getattr(runtime_state, "holeInfoList", []) or holeInfoList,
                getattr(runtime_state, "slotInfoList", []),
                getattr(runtime_state, "pocketCornerRInfoList", None),
            )
            n_tr = int(tr.get("count", 0) or 0)
            if n_tr > 0:
                done.append(f'📚 學習庫已記錄 {n_tr} 筆模板選擇（供下次 AI 建議使用）')
        except Exception:
            pass
        
        # 雙迴路學習：將新生成的工序寫入最接近的思維軌跡
        try:
            from Smart_AI.memory.thought_db import get_thought_db
            db = get_thought_db()
            pending_thoughts = [t for t in db._thoughts.values() if t.get("reflection", {}).get("user_action") is None]
            if pending_thoughts:
                latest_thought = sorted(pending_thoughts, key=lambda x: x.get("timestamp", ""), reverse=True)[0]
                gen_ops_info = []
                for op in all_new_ops:
                    op_name = op.name
                    feed = ""
                    speed = ""
                    try:
                        feed = op.parameters.itemByName("tool_feedcutting").expression
                        speed = op.parameters.itemByName("tool_spindleSpeed").expression
                    except:
                        pass
                    gen_ops_info.append({
                        "name": op_name,
                        "feedrate": feed,
                        "speed": speed
                    })
                latest_thought.setdefault("decision", {})["generated_ops"] = gen_ops_info
                latest_thought["reflection"]["retrospective"] = "工序已生成，等待使用者執行加工工序並提供反思。"
                db._dirty = True
                db.flush()
        except Exception as db_ex:
            pass
        
        # 通知前端執行完成，重置按鈕狀態
        _palette = get_main_palette()
        if _palette:
            _broadcast_mcp_progress(100, "AI 智慧編程工序生成完成！")
            _palette.sendInfoToHTML('finish_exec', '{}')
        
        if done:
            _ui_message("\n".join(done))
    except Exception:
        _broadcast_mcp_progress(0, "執行失敗")
        _ui_message("執行失敗:\n{}".format(traceback.format_exc()))
    finally:
        _isExecutingPalette = False

