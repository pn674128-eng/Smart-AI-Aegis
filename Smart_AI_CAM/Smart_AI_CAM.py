# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion, adsk.cam, traceback, json, re, time, os, importlib.util, sys, shutil, unicodedata, socket, threading, queue

# 確保增益集目錄在 sys.path 中
_addin_dir = os.path.dirname(os.path.abspath(__file__))
if _addin_dir not in sys.path:
    sys.path.insert(0, _addin_dir)

_modules_to_reload = [
    "smart_ai_cam_state.runtime_state",
    "smart_ai_cam_templates.template_service",
    "smart_ai_cam_ui.palette_context",
    "smart_ai_cam_ui.palette_controller",
    "smart_ai_cam_ui.palette_data_provider",
    "Smart_AI.reasoning.ai_decision_engine",
    "Smart_AI.perception.hole_recognizer",
    "Smart_AI.perception.slot_recognizer",
    "Smart_AI.perception.contour_recognizer",
    "Smart_AI.perception.contour_extension_recognizer",
    "Smart_AI.reasoning.ai_brain",
    "Smart_AI.reasoning.machining_feature_catalog",
    "Smart_AI.reasoning.ai_panel_apply",
    "Smart_AI.perception.contour_2d_recognizer",
    "Smart_AI.perception.fusion_official_recognition",
    "Smart_AI.perception.official_pocket_execute",
    "Smart_AI.reasoning.feature_apply",
    "Smart_AI.reasoning.ai_recommendations",
    "Smart_AI.reasoning.programming_modes",
    "Smart_AI.reasoning.intuitive_programming",
    "Smart_AI.reasoning.thinking_programming",
    "Smart_AI.reasoning.thinking_l2_plan",
    "Smart_AI.reasoning.cam_depth_plan",
    "smart_ai_cam_machining.cam_operation_tuning",
    "Smart_AI.reasoning.reference_paths",
    "Smart_AI.reasoning.cam_reference_import",
    "Smart_AI.reasoning.reference_batch_import",
    "Smart_AI.reasoning.ai_training",
    "Smart_AI.reasoning.ai_template_picker",
    "Smart_AI.reasoning.template_resolver",
    "Smart_AI.memory.knowledge_db",
    "Smart_AI.memory.knowledge_bootstrap",
    "Smart_AI.memory.thought_db",
    "Smart_AI.reasoning.thought_reasoning",
    "Smart_AI.perception.feature_scanner",
    "smart_ai_cam_machining.geometry_utils",
    "smart_ai_cam_machining.operation_builder",
    "smart_ai_cam_machining.reorder_service",
    "smart_ai_cam_machining.execute",
    "smart_ai_cam_ui.diagnostics",
    "smart_ai_cam_vision.snapshot",
    "smart_ai_cam_vision.assist_sketch",
]
import importlib
for _mod_name in _modules_to_reload:
    if _mod_name in sys.modules:
        try:
            importlib.reload(sys.modules[_mod_name])
        except Exception:
            pass

from smart_ai_cam_templates import template_service
from smart_ai_cam_ui import palette_controller, palette_data_provider
from smart_ai_cam_ui.palette_context import PaletteActionContext
from smart_ai_cam_state.runtime_state import state as runtime_state
from smart_ai_cam_machining import reorder_service, geometry_utils, operation_builder, execute
from Smart_AI.perception import feature_scanner
from smart_ai_cam_ui import diagnostics

ADDIN_VERSION = 'V2.0458'
ADDIN_DISPLAY_NAME = 'Smart AI CAM Fusion'
PANEL_ID = 'CAMJobPanel'
ADDIN_DIR = _addin_dir
_html_path = os.path.join(ADDIN_DIR, 'palette.html')

app = None
ui = None
handlers = []
holeInfoList = []
slotInfoList = []
pocketCornerRInfoList = []
camSetup = None
tmplLib = None
allDrillMap = {}
allChamferMap = {}
allTopFaceMap = {}
allProfileMap = {}
allSlotMap = {}
allSlotChamferMap = {}
allTopFaceRoughMap = {}
allTopFaceFinishMap = {}
allProfileRoughMap = {}
allProfileFinishMap = {}
allCountersinkMap = {}
cam_obj = None
des_obj = None
bodyZRange_ref = {}
root_comp_ref = None
_palette = None
_diag_palette = None
_isExecutingPalette = False

ALLOWED_CHAMFER_TAGS = ('C0.2', 'C0.3')
TEMPLATE_FOLDER_PATHS = {
    'topFaceRough': '{material}/面銑刀模塊 【{material}】/粗加工【{material}】',
    'topFaceFinish': '{material}/面銑刀模塊 【{material}】/精加工【{material}】',
    'topFaceLegacy': '{material}/面銑刀模塊 【{material}】',
    'profileRough': '{material}/銑刀模塊 【{material}】/外輪廓加工 【{material}】/粗加工 【{material}】',
    'profileFinish': '{material}/銑刀模塊 【{material}】/外輪廓加工 【{material}】/精加工 【{material}】',
    'profileLegacy': '{material}/銑刀模塊 【{material}】/外輪廓加工 【{material}】',
    'generalHole': '{material}/孔加工模塊 【{material}】/一般孔 【{material}】',
    'tapHole': '{material}/孔加工模塊 【{material}】/牙孔 【{material}】',
    'locatingHole': '{material}/孔加工模塊 【{material}】/定位孔 【{material}】',
    'countersinkHole': '{material}/孔加工模塊 【{material}】/沉頭孔 【{material}】',
    'slotHole': '{material}/孔加工模塊 【{material}】/長條孔 【{material}】',
    'holeChamfer': '{material}/倒角刀模塊 【{material}】/孔倒角 【{material}】',
    'contourChamfer': '{material}/倒角刀模塊 【{material}】/輪廓倒角 【{material}】',
}

def _get_template_paths():
    paths = dict(TEMPLATE_FOLDER_PATHS)
    try:
        from smart_ai_cam_ui import palette_data_provider
        import os
        import re
        defs = palette_data_provider._load_ui_defaults()
        
        # 載入持久化保存的自訂外部根目錄
        custom_root = defs.get("customTemplatesRoot", "")
        if custom_root and os.path.exists(custom_root):
            runtime_state.custom_templates_root = os.path.normpath(custom_root).replace("\\", "/")
            
        appdata = os.environ.get("APPDATA", "")
        templates_root = os.path.normpath(os.path.join(appdata, "Autodesk", "CAM360", "templates")).replace("\\", "/").lower()
        
        for k in TEMPLATE_FOLDER_PATHS.keys():
            if k in defs and defs[k]:
                val = str(defs[k]).strip().replace("\\", "/")
                
                # 如果包含碟符絕對路徑，先進行自訂外部根路徑提取
                if ":" in val or val.startswith("/") or os.path.isabs(val):
                    val_norm = os.path.normpath(val).replace("\\", "/")
                    for tag in ["/al6061", "/s50c", "/{material}"]:
                        idx = val_norm.lower().find(tag)
                        if idx != -1:
                            ext_root = val_norm[:idx]
                            if os.path.exists(ext_root):
                                runtime_state.custom_templates_root = os.path.normpath(ext_root).replace("\\", "/")
                                try:
                                    palette_data_provider._save_ui_defaults({"customTemplatesRoot": runtime_state.custom_templates_root})
                                except:
                                    pass
                                val = val_norm[idx:].strip("/")
                                break
                                
                # 預設 C 槽本地庫去頭
                val_lower = val.lower()
                if val_lower.startswith(templates_root):
                    val = val[len(templates_root):].strip("/")
                elif "cam360/templates/" in val_lower:
                    idx = val_lower.find("cam360/templates/")
                    val = val[idx + len("cam360/templates/"):].strip("/")
                    
                # 防禦性將可能寫死的材料名自動替換回動態佔位符 {material}
                for mat_tag in ["AL6061", "S50C", "al6061", "s50c"]:
                    if mat_tag in val:
                        val = re.sub(re.escape(mat_tag), "{material}", val, flags=re.IGNORECASE)
                        
                paths[k] = val
    except:
        pass
    runtime_state.template_paths = paths
    return paths


# Dynamic sharing with runtime_state
def _sync_maps_to_runtime_state():
    runtime_state.allDrillMap = allDrillMap
    runtime_state.allChamferMap = allChamferMap
    runtime_state.allSlotMap = allSlotMap
    runtime_state.allSlotChamferMap = allSlotChamferMap
    runtime_state.allCountersinkMap = allCountersinkMap
    runtime_state.allTopFaceMap = allTopFaceMap
    runtime_state.allProfileMap = allProfileMap
    runtime_state.allTopFaceRoughMap = allTopFaceRoughMap
    runtime_state.allTopFaceFinishMap = allTopFaceFinishMap
    runtime_state.allProfileRoughMap = allProfileRoughMap
    runtime_state.allProfileFinishMap = allProfileFinishMap
    runtime_state.holeInfoList = holeInfoList
    try:
        from Smart_AI.reasoning.template_resolver import invalidate_name_url_index

        invalidate_name_url_index()
    except Exception:
        pass

def _validate_and_refresh_refs():
    global app, ui, cam_obj, des_obj, camSetup, tmplLib
    ok = feature_scanner._validate_and_refresh_refs()
    app = runtime_state.app
    ui = runtime_state.ui
    cam_obj = runtime_state.cam_obj
    des_obj = runtime_state.des_obj
    camSetup = runtime_state.cam_setup
    tmplLib = runtime_state.tmpl_lib
    return ok

def _safe_cam_from_document(doc):
    return feature_scanner._safe_cam_from_document(doc)

def _get_template_name_cache():
    cache = getattr(runtime_state, 'template_name_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(runtime_state, 'template_name_cache', cache)
    return cache

def _clear_template_name_cache():
    _get_template_name_cache().clear()

def _clear_drill_tool_library_cache():
    if hasattr(operation_builder, '_clear_drill_tool_library_cache'):
        operation_builder._clear_drill_tool_library_cache()

def _clear_pocket_cache():
    try:
        runtime_state.pocket_cache_sig = ''
        runtime_state.pocket_cache_rows = []
    except:
        pass

def _clear_op_clone_cache():
    cache = getattr(runtime_state, 'op_clone_cache', None)
    if isinstance(cache, dict):
        cache.clear()

def _clear_feature_face_cache():
    cache = getattr(runtime_state, 'feature_face_cache', None)
    if isinstance(cache, dict):
        cache.clear()

def _clear_op_name_cache():
    cache = getattr(runtime_state, 'op_name_cache', None)
    if isinstance(cache, dict):
        cache.clear()

def _load_countersink_templates(material):
    return template_service.load_countersink_templates(tmplLib, material, _get_template_paths())

def _load_slot_templates(material):
    return template_service.load_slot_templates(tmplLib, material, _get_template_paths())

def _load_slot_chamfer_templates(material):
    return template_service.load_slot_chamfer_templates(tmplLib, material, _get_template_paths(), ALLOWED_CHAMFER_TAGS)

def _load_2d_template_maps(material):
    return template_service.load_2d_template_maps(tmplLib, material, _get_template_paths())

def _validate_configured_template_paths(materials):
    return template_service.validate_configured_template_paths(tmplLib, materials, _get_template_paths())

def buildTemplateMaps(material):
    return operation_builder.buildTemplateMaps(material)

def _template_map_load_log(msg):
    diagnostics.send_diag_log(msg)

def _send_diag_log(msg):
    diagnostics.send_diag_log(msg)

def _broadcast_mcp_progress(percentage, status_text):
    diagnostics._broadcast_mcp_progress(percentage, status_text)

def _ensure_diag_palette(visible=False, only_bind=False):
    global _diag_palette
    pal = palette_data_provider._ensure_diag_palette(visible=visible, only_bind=only_bind)
    if pal:
        _diag_palette = pal
    return pal

def _save_ui_defaults(data):
    palette_data_provider._save_ui_defaults(data)

def _apply_fixed_palette_size(pal):
    palette_data_provider._apply_fixed_palette_size(pal)

def _run_regression_check():
    try:
        return diagnostics._run_regression_check()
    except Exception as e:
        _send_diag_log(f"Regression check failed to run: {e}")
        return False

def _dump_active_setup_ops_params(max_ops=8):
    return operation_builder._dump_active_setup_ops_params(max_ops)

def getToolInfoFromTemplate(tmpl_url):
    return operation_builder.getToolInfoFromTemplate(tmpl_url)

def _emit_hole_debug_dump(source='scan'):
    try:
        diagnostics._emit_hole_debug_dump(source)
    except:
        pass

def _emit_slot_diag_dump(source='scan'):
    try:
        diagnostics._emit_slot_diag_dump(source)
    except:
        pass

def _calcDisplaySignature():
    return feature_scanner._calcDisplaySignature()

def _scanAndBuildHoleInfo(force=False):
    feature_scanner._scanAndBuildHoleInfo(force)
    global holeInfoList
    holeInfoList = list(
        getattr(feature_scanner, 'holeInfoList', None)
        or getattr(runtime_state, 'holeInfoList', [])
        or []
    )
    runtime_state.holeInfoList = holeInfoList
    _sync_maps_to_runtime_state()

def _scanAndBuildSlotInfo(invoked_from='rebuild'):
    feature_scanner._scanAndBuildSlotInfo(invoked_from)
    global slotInfoList
    slotInfoList = list(
        getattr(feature_scanner, 'slotInfoList', None)
        or getattr(runtime_state, 'slotInfoList', [])
        or []
    )
    runtime_state.slotInfoList = slotInfoList
    _sync_maps_to_runtime_state()

def _scanAndBuildPocketCornerRInfo():
    feature_scanner._scanAndBuildPocketCornerRInfo()
    global pocketCornerRInfoList
    pocketCornerRInfoList = list(
        getattr(feature_scanner, 'pocketCornerRInfoList', None)
        or getattr(runtime_state, 'pocketCornerRInfoList', [])
        or []
    )
    runtime_state.pocketCornerRInfoList = pocketCornerRInfoList
    _sync_maps_to_runtime_state()

def _refresh_vision_snapshot():
    feature_scanner._refresh_vision_snapshot()


def _push_vision_snapshot_to_palette():
    if not _palette:
        return
    snap = getattr(runtime_state, "vision_snapshot", None)
    if snap:
        from smart_ai_cam_vision.snapshot import vision_snapshot_json_string

        _palette.sendInfoToHTML("vision_snapshot", vision_snapshot_json_string(snap))

def _refresh_fusion_official_recognition():
    feature_scanner._refresh_fusion_official_recognition()

def _refresh_feature_catalog():
    feature_scanner._refresh_feature_catalog()

def _refresh_contour_2d_recognition():
    feature_scanner._refresh_contour_2d_recognition()

def _buildInitData():
    return feature_scanner._buildInitData()

def _buildHoleData(mat='AL6061'):
    return feature_scanner._buildHoleData(mat)

def _buildSlotData(mat='AL6061'):
    return feature_scanner._buildSlotData(mat)

def _buildPocketCornerRData(mat='AL6061'):
    return feature_scanner._buildPocketCornerRData(mat)

def _scanFlatDepths():
    return feature_scanner._scanFlatDepths()

def _handle_draw_vision_sketch_palette():
    feature_scanner._handle_draw_vision_sketch_palette()

def _send_vision_sketch_palette_result(result):
    feature_scanner._send_vision_sketch_palette_result(result)

def _buildOfficialPocketData(mat='AL6061'):
    return feature_scanner._buildOfficialPocketData(mat)


def _buildOfficialSlotPocketData(mat='AL6061'):
    return feature_scanner._buildOfficialSlotPocketData(mat)


def _buildOfficialPocketSlotData(mat='AL6061'):
    return feature_scanner._buildOfficialPocketSlotData(mat)

def _contour2d_summary_for_mcp():
    try:
        from Smart_AI.perception.contour_2d_recognizer import recognition_summary_for_init
        return recognition_summary_for_init(getattr(runtime_state, "contour_2d_recognition", None))
    except Exception as ex:
        return {"ok": False, "reason": str(ex)}


def _contour_chamfer_template_names(mat):
    global tmplLib
    rel = _get_template_paths().get("contourChamfer", "")
    if not tmplLib or not rel:
        return []
    try:
        items = template_service.collect_assets_from_folder_path(tmplLib, mat, rel)
        return [str(x.get("name", "")) for x in (items or []) if x.get("name")]
    except Exception:
        return []


def _build_ai_rec_context():
    _sync_maps_to_runtime_state()
    return {
        "rebuild_holes": _rebuildHoleListForPalette,
        "build_hole_data": _buildHoleData,
        "build_slot_data": _buildSlotData,
        "build_pocket_corner_r_data": _buildPocketCornerRData,
        "scan_flat_depths": _scanFlatDepths,
        "refresh_fusion_official": _refresh_fusion_official_recognition,
        "refresh_feature_catalog": _refresh_feature_catalog,
        "refresh_contour_2d": _refresh_contour_2d_recognition,
        "refresh_vision": _refresh_vision_snapshot,
        "build_official_pocket_data": _buildOfficialPocketData,
        "build_official_slot_pocket_data": _buildOfficialSlotPocketData,
        "build_official_pocket_slot_data": _buildOfficialPocketSlotData,
        "contour_chamfer_names": _contour_chamfer_template_names,
        "top_face_rough_map": allTopFaceRoughMap,
        "top_face_finish_map": allTopFaceFinishMap,
        "profile_rough_map": allProfileRoughMap,
        "profile_finish_map": allProfileFinishMap,
        "cam_obj": cam_obj,
        "des_obj": des_obj,
        "cam_setup": camSetup,
    }

def _set_cam_setup(setup):
    global camSetup
    camSetup = setup
    runtime_state.cam_setup = setup


def _sync_module_lists_from_runtime_state():
    global holeInfoList, slotInfoList, pocketCornerRInfoList
    holeInfoList = list(getattr(runtime_state, "holeInfoList", []) or [])
    slotInfoList = list(getattr(runtime_state, "slotInfoList", []) or [])
    pocketCornerRInfoList = list(getattr(runtime_state, "pocketCornerRInfoList", []) or [])


def _ensure_template_maps_loaded():
    """模板庫就緒且映射為空時補載（外掛啟動／換文件後，無須先開面板）。"""
    global tmplLib, allDrillMap, allChamferMap, allCountersinkMap, allSlotMap, allSlotChamferMap
    global allTopFaceMap, allProfileMap, allTopFaceRoughMap, allTopFaceFinishMap
    global allProfileRoughMap, allProfileFinishMap
    try:
        lib = template_service.ensure_tmpl_lib()
        if not lib:
            return False
        tmplLib = lib
        stale = (
            not allDrillMap
            or not allDrillMap.get("AL6061")
            or not allDrillMap.get("S50C")
        )
        if not stale:
            return True
        _get_template_paths()
        for _mat in ["AL6061", "S50C"]:
            _dm, _cm = buildTemplateMaps(_mat)
            allDrillMap[_mat] = _dm
            allChamferMap[_mat] = _cm
            allCountersinkMap[_mat] = _load_countersink_templates(_mat)
            allSlotMap[_mat] = _load_slot_templates(_mat)
            allSlotChamferMap[_mat] = _load_slot_chamfer_templates(_mat)
            tf_r, tf_f, pf_r, pf_f, tf_all, pf_all = _load_2d_template_maps(_mat)
            allTopFaceRoughMap[_mat] = tf_r
            allTopFaceFinishMap[_mat] = tf_f
            allProfileRoughMap[_mat] = pf_r
            allProfileFinishMap[_mat] = pf_f
            allTopFaceMap[_mat] = tf_all
            allProfileMap[_mat] = pf_all
        _sync_maps_to_runtime_state()
        return True
    except Exception:
        return False


def _refreshPaletteForActiveDocument(force=True):
    """切換文件／產品（設計↔製造）後：重綁引用、重掃、推送完整 init 至面板。"""
    global _palette, holeInfoList, slotInfoList, pocketCornerRInfoList
    try:
        if not _validate_and_refresh_refs():
            if _palette:
                try:
                    _palette.sendInfoToHTML("init", _buildInitData())
                except Exception:
                    pass
            return
        _ensure_template_maps_loaded()
        runtime_state.template_params_cache.clear()
        runtime_state.tool_info_cache.clear()
        _clear_template_name_cache()
        _clear_drill_tool_library_cache()
        _clear_pocket_cache()
        _clear_op_clone_cache()
        _clear_feature_face_cache()
        _clear_op_name_cache()
        if force:
            runtime_state.last_display_signature = ""
        _scanAndBuildHoleInfo(force=force)
        _scanAndBuildSlotInfo("rebuild")
        _scanAndBuildPocketCornerRInfo()
        _refresh_vision_snapshot()
        _refresh_fusion_official_recognition()
        _refresh_feature_catalog()
        _refresh_contour_2d_recognition()
        _sync_module_lists_from_runtime_state()
        _sync_maps_to_runtime_state()
        if _palette:
            _palette.sendInfoToHTML("init", _buildInitData())
            _send_diag_log(
                "[doc-switch] 已刷新面板："
                + str(getattr(runtime_state, "active_document_token", "") or "")[:48]
            )
    except Exception:
        _send_diag_log("[doc-switch] 刷新失敗:\n" + traceback.format_exc())


def _sendHoles():
    if not _palette: return
    try:
        _palette.sendInfoToHTML('holes', json.dumps({
            'holes': _buildHoleData(runtime_state.current_material),
            'slots': _buildSlotData(runtime_state.current_material),
            'pocket_corner_r': _buildPocketCornerRData(runtime_state.current_material),
            'flat_depths': _scanFlatDepths(),
        }))
    except Exception as e:
        _send_diag_log(f"[palette] sendHoles failed: {e}")

def _sendMaterialData(mat):
    if not _palette: return
    tf = [x['name'] for x in allTopFaceMap.get(mat, [])]
    pf = [x['name'] for x in allProfileMap.get(mat, [])]
    tf_rough = [x['name'] for x in allTopFaceRoughMap.get(mat, [])]
    tf_finish = [x['name'] for x in allTopFaceFinishMap.get(mat, [])]
    pf_rough = [x['name'] for x in allProfileRoughMap.get(mat, [])]
    pf_finish = [x['name'] for x in allProfileFinishMap.get(mat, [])]
    try:
        _palette.sendInfoToHTML('material_data', json.dumps({
            'material': mat,
            'topFace': tf, 'profile': pf,
            'topFaceRough': tf_rough, 'topFaceFinish': tf_finish,
            'profileRough': pf_rough, 'profileFinish': pf_finish
        }))
    except Exception as e:
        _send_diag_log(f"[palette] sendMaterialData failed: {e}")

def _rebuildHoleListForPalette(force=False):
    global camSetup, des_obj, cam_obj, holeInfoList, slotInfoList, pocketCornerRInfoList
    try:
        if not _validate_and_refresh_refs():
            return
        
        # 清除緩存並重新掃描幾何
        runtime_state.template_params_cache.clear()
        runtime_state.tool_info_cache.clear()
        _clear_template_name_cache()
        _clear_drill_tool_library_cache()
        _clear_pocket_cache()
        _clear_op_clone_cache()
        _clear_feature_face_cache()
        _clear_op_name_cache()
        
        _scanAndBuildHoleInfo(force=force)
        _scanAndBuildSlotInfo('rebuild')
        _scanAndBuildPocketCornerRInfo()

        # 刷新本機 maps 引用（孔表優先推送，避免後續 vision/official 失敗導致孔表空白）
        holeInfoList = list(getattr(runtime_state, 'holeInfoList', []))
        slotInfoList = list(getattr(runtime_state, 'slotInfoList', []))
        pocketCornerRInfoList = list(getattr(runtime_state, 'pocketCornerRInfoList', []))
        _sync_maps_to_runtime_state()
        _sendHoles()

        try:
            _refresh_vision_snapshot()
        except Exception as _vex:
            _send_diag_log('[rebuild] vision refresh failed: {}'.format(_vex))
        _push_vision_snapshot_to_palette()
        try:
            _refresh_fusion_official_recognition()
        except Exception as _foe:
            _send_diag_log('[rebuild] fusion official refresh failed: {}'.format(_foe))
        try:
            _refresh_feature_catalog()
        except Exception as _fce:
            _send_diag_log('[rebuild] feature catalog refresh failed: {}'.format(_fce))
        try:
            _refresh_contour_2d_recognition()
        except Exception as _c2e:
            _send_diag_log('[rebuild] contour2d refresh failed: {}'.format(_c2e))
    except Exception:
        _err = traceback.format_exc()
        _send_diag_log('[rebuild] _rebuildHoleListForPalette 失敗:\n' + _err)
        try:
            if _palette:
                _palette.sendInfoToHTML(
                    'status',
                    json.dumps(
                        {
                            'msg': '孔/槽掃描失敗（已寫入診斷日誌）。請開啟診斷視窗或查看彈出訊息。',
                            'level': 'err',
                        },
                        ensure_ascii=False,
                    ),
                )
        except Exception:
            pass
        try:
            _ui = runtime_state.ui or adsk.core.Application.get().userInterface
            _ui.messageBox('孔/槽掃描失敗：\n' + _err[:1800])
        except Exception:
            pass

def _fullRescanForPalette(target_setup_name=''):
    global camSetup, des_obj, cam_obj, holeInfoList, slotInfoList, pocketCornerRInfoList
    try:
        if not _validate_and_refresh_refs():
            return
        
        # 重新整理自訂模板路徑配置
        _get_template_paths()
        
        # 優先級重新尋找 Setup（面板選擇 > 參數 > pending_setup_name）
        _apply_setup = (target_setup_name or "").strip() or (
            getattr(runtime_state, "pending_setup_name", "") or ""
        ).strip()
        if _apply_setup:
            try:
                from Smart_AI.perception.feature_scanner import apply_panel_setup

                _picked = apply_panel_setup(_apply_setup, activate_in_fusion=True)
                if _picked:
                    camSetup = _picked
            except Exception:
                for _i in range(cam_obj.setups.count):
                    if cam_obj.setups.item(_i).name == _apply_setup:
                        camSetup = cam_obj.setups.item(_i)
                        runtime_state.cam_setup = camSetup
                        runtime_state.pending_setup_name = _apply_setup
                        try:
                            camSetup.activate()
                        except Exception:
                            pass
                        break
        
        # 重新載入模板庫與映射
        mgr = adsk.cam.CAMManager.get().libraryManager
        tmplLib = mgr.templateLibrary
        runtime_state.tmpl_lib = tmplLib
        try:
            from smart_ai_cam_templates import template_fs_cache as _tfc
            _tfc.invalidate_all()
        except Exception:
            pass
        
        allDrillMap.clear(); allChamferMap.clear(); allCountersinkMap.clear(); allSlotMap.clear(); allSlotChamferMap.clear()
        allTopFaceMap.clear(); allProfileMap.clear()
        allTopFaceRoughMap.clear(); allTopFaceFinishMap.clear()
        allProfileRoughMap.clear(); allProfileFinishMap.clear()
        
        for _mat in ['AL6061', 'S50C']:
            _dm, _cm = buildTemplateMaps(_mat)
            allDrillMap[_mat] = _dm
            allChamferMap[_mat] = _cm
            allCountersinkMap[_mat] = _load_countersink_templates(_mat)
            allSlotMap[_mat] = _load_slot_templates(_mat)
            allSlotChamferMap[_mat] = _load_slot_chamfer_templates(_mat)
            tf_r, tf_f, pf_r, pf_f, tf_all, pf_all = _load_2d_template_maps(_mat)
            allTopFaceRoughMap[_mat] = tf_r
            allTopFaceFinishMap[_mat] = tf_f
            allProfileRoughMap[_mat] = pf_r
            allProfileFinishMap[_mat] = pf_f
            allTopFaceMap[_mat] = tf_all
            allProfileMap[_mat] = pf_all
            
        _sync_maps_to_runtime_state()
        missing = _validate_configured_template_paths(['AL6061', 'S50C'])
        if missing:
            runtime_state.ui.messageBox('以下模板路徑不存在：\n' + '\n'.join(missing))
            
        # 清除緩存並重新掃描幾何
        runtime_state.template_params_cache.clear()
        runtime_state.tool_info_cache.clear()
        _clear_template_name_cache()
        _clear_drill_tool_library_cache()
        _clear_pocket_cache()
        _clear_op_clone_cache()
        _clear_feature_face_cache()
        _clear_op_name_cache()
        runtime_state.last_display_signature = ''
        
        _scanAndBuildHoleInfo(force=True)
        _scanAndBuildSlotInfo('full_rescan')
        _scanAndBuildPocketCornerRInfo()

        # 刷新本機 maps 引用
        holeInfoList = list(getattr(runtime_state, 'holeInfoList', []))
        slotInfoList = list(getattr(runtime_state, 'slotInfoList', []))
        pocketCornerRInfoList = list(getattr(runtime_state, 'pocketCornerRInfoList', []))
        _sync_maps_to_runtime_state()

        try:
            _refresh_vision_snapshot()
        except Exception as _vex:
            _send_diag_log('[full_rescan] vision refresh failed: {}'.format(_vex))
        try:
            _refresh_fusion_official_recognition()
        except Exception as _foe:
            _send_diag_log('[full_rescan] fusion official refresh failed: {}'.format(_foe))
        try:
            _refresh_feature_catalog()
        except Exception as _fce:
            _send_diag_log('[full_rescan] feature catalog refresh failed: {}'.format(_fce))
        try:
            _refresh_contour_2d_recognition()
        except Exception as _c2e:
            _send_diag_log('[full_rescan] contour2d refresh failed: {}'.format(_c2e))

        if _palette:
            _palette.sendInfoToHTML('init', _buildInitData())
            _push_vision_snapshot_to_palette()
    except Exception as _e:
        try:
            runtime_state.ui.messageBox('Rescan 錯誤:\n' + traceback.format_exc())
        except: pass

def _refreshTemplateCacheForPalette():
    global tmplLib, allDrillMap, allChamferMap, allCountersinkMap, allSlotMap, allSlotChamferMap
    global allTopFaceMap, allProfileMap, allTopFaceRoughMap, allTopFaceFinishMap, allProfileRoughMap, allProfileFinishMap
    try:
        _ensure_diag_palette(visible=False, only_bind=True)
        if not _validate_and_refresh_refs():
            return False
            
        # 重新整理自訂模板路徑配置
        _get_template_paths()
            
        mgr = adsk.cam.CAMManager.get().libraryManager
        tmplLib = mgr.templateLibrary
        runtime_state.tmpl_lib = tmplLib
        try:
            from smart_ai_cam_templates import template_fs_cache as _tfc
            _tfc.invalidate_all()
        except Exception:
            pass

        allDrillMap.clear(); allChamferMap.clear(); allCountersinkMap.clear(); allSlotMap.clear(); allSlotChamferMap.clear()
        allTopFaceMap.clear(); allProfileMap.clear()
        allTopFaceRoughMap.clear(); allTopFaceFinishMap.clear()
        allProfileRoughMap.clear(); allProfileFinishMap.clear()

        for _mat in ['AL6061', 'S50C']:
            _dm, _cm = buildTemplateMaps(_mat)
            allDrillMap[_mat] = _dm
            allChamferMap[_mat] = _cm
            allCountersinkMap[_mat] = _load_countersink_templates(_mat)
            allSlotMap[_mat] = _load_slot_templates(_mat)
            allSlotChamferMap[_mat] = _load_slot_chamfer_templates(_mat)
            tf_r, tf_f, pf_r, pf_f, tf_all, pf_all = _load_2d_template_maps(_mat)
            allTopFaceRoughMap[_mat] = tf_r
            allTopFaceFinishMap[_mat] = tf_f
            allProfileRoughMap[_mat] = pf_r
            allProfileFinishMap[_mat] = pf_f
            allTopFaceMap[_mat] = tf_all
            allProfileMap[_mat] = pf_all

        _sync_maps_to_runtime_state()
        missing = _validate_configured_template_paths(['AL6061', 'S50C'])
        if missing:
            runtime_state.ui.messageBox('以下模板路徑不存在：\n' + '\n'.join(missing))

        _rebuildHoleListForPalette(force=True)
        if _palette:
            _palette.sendInfoToHTML('init', _buildInitData())
        _send_diag_log('[template-cache] 已重新快取模板並刷新面板')
        return True
    except Exception:
        _send_diag_log('[template-cache] 重建失敗:\n' + traceback.format_exc())
        return False

def _executeFromPalette(data):
    global _isExecutingPalette, app, ui, cam_obj, des_obj, camSetup, tmplLib
    try:
        _isExecutingPalette = True
        _validate_and_refresh_refs()
        _sync_maps_to_runtime_state()
        execute._executeFromPalette(data)
    finally:
        _isExecutingPalette = False

# ===========================================================================
# HTML & Command Listeners
# ===========================================================================

class PaletteHTMLHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _palette, cam_obj, des_obj, camSetup, holeInfoList, allDrillMap, allChamferMap, allTopFaceMap, allProfileMap, allSlotMap, allSlotChamferMap, bodyZRange_ref, root_comp_ref
        action_norm_lc = ""
        try:
            raw_action = str(args.action or "")
            raw_data = str(args.data or "")
            action = raw_action.strip()
            action_norm = action.strip("'\"").strip().lower()
            action_norm_lc = action_norm
            
            if "response" in action_norm:
                return
            if action_norm_lc == "draw_recognition_sketch":
                _handle_draw_vision_sketch_palette()
                return
                
            data = json.loads(raw_data) if raw_data else {}
            context = PaletteActionContext(
                adsk=adsk,
                ui=ui,
                cam_obj=lambda: cam_obj,
                set_cam_setup=_set_cam_setup,
                holeInfoList=lambda: holeInfoList,
                palette=lambda: _palette,
                is_executing=lambda: _isExecutingPalette,
                runtime_state=runtime_state,
                rebuild=_rebuildHoleListForPalette,
                send_material_data=_sendMaterialData,
                full_rescan=_fullRescanForPalette,
                build_init_data=_buildInitData,
                calc_display_signature=_calcDisplaySignature,
                ensure_diag_palette=_ensure_diag_palette,
                send_diag_log=_send_diag_log,
                emit_hole_debug_dump=_emit_hole_debug_dump,
                emit_slot_diag_dump=_emit_slot_diag_dump,
                get_tool_info_from_template=getToolInfoFromTemplate,
                save_ui_defaults=_save_ui_defaults,
                run_regression_check=_run_regression_check,
                dump_active_setup_ops_params=_dump_active_setup_ops_params,
                refresh_template_cache=_refreshTemplateCacheForPalette,
                execute_from_palette=_executeFromPalette,
                process_mcp_request=process_mcp_request,
            )
            palette_controller.handle_action(action, data, context)
        except Exception:
            tb = traceback.format_exc()
            if action_norm_lc == "draw_recognition_sketch":
                try:
                    _send_vision_sketch_palette_result(
                        {
                            "ok": False,
                            "message": tb.splitlines()[-1] if tb else "draw failed",
                            "sketch_name": "",
                        }
                    )
                except Exception:
                    pass
                return
            ui.messageBox(tb)

class PaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _palette
        _palette = None
        diagnostics.register_main_palette(None)

class DiagPaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _diag_palette
        _diag_palette = None
        try:
            if _palette:
                _palette.sendInfoToHTML('diag_closed', '{}')
        except: pass

class DocumentActivatedHandler(adsk.core.DocumentEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            _refreshPaletteForActiveDocument(force=True)
        except Exception:
            pass

class ActiveProductChangedHandler(adsk.core.ApplicationEventHandler):
    """同一文件內切換設計／製造等工作區時刷新。"""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            _refreshPaletteForActiveDocument(force=True)
        except Exception:
            pass

class WindowActivatedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            if _palette and _palette.isVisible:
                _refreshPaletteForActiveDocument(force=False)
        except Exception:
            pass

class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        pass

class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _palette, _diag_palette, camSetup, cam_obj, des_obj, tmplLib
        global allDrillMap, allChamferMap, allTopFaceMap, allProfileMap
        global allTopFaceRoughMap, allTopFaceFinishMap, allProfileRoughMap, allProfileFinishMap
        global allCountersinkMap, allSlotMap, allSlotChamferMap
        try:
            # 重設過期面板參照，避免靜態持有失效控制項導致 sendInfoToHTML RuntimeError 崩齊
            _palette = None
            _diag_palette = None
            
            _doc = adsk.core.Application.get().activeDocument
            if not _validate_and_refresh_refs():
                return
            
            mgr = adsk.cam.CAMManager.get().libraryManager
            tmplLib = mgr.templateLibrary
            runtime_state.tmpl_lib = tmplLib
            
            # If allDrillMap is empty or contains empty dicts (due to startup loading before tmpl_lib was ready), force load.
            is_empty_or_stale = not allDrillMap or not allDrillMap.get('AL6061') or not allDrillMap.get('S50C')
            if is_empty_or_stale:
                for _mat in ['AL6061', 'S50C']:
                    _dm, _cm = buildTemplateMaps(_mat)
                    allDrillMap[_mat] = _dm
                    allChamferMap[_mat] = _cm
                    allCountersinkMap[_mat] = _load_countersink_templates(_mat)
                    allSlotMap[_mat] = _load_slot_templates(_mat)
                    allSlotChamferMap[_mat] = _load_slot_chamfer_templates(_mat)
                    tf_r, tf_f, pf_r, pf_f, tf_all, pf_all = _load_2d_template_maps(_mat)
                    allTopFaceRoughMap[_mat] = tf_r
                    allTopFaceFinishMap[_mat] = tf_f
                    allProfileRoughMap[_mat] = pf_r
                    allProfileFinishMap[_mat] = pf_f
                    allTopFaceMap[_mat] = tf_all
                    allProfileMap[_mat] = pf_all
            else:
                try:
                    from smart_ai_cam_templates import template_fs_cache as _tfc
                    _tfc.invalidate_all()
                except Exception:
                    pass
                for _mat in ['AL6061', 'S50C']:
                    allSlotMap[_mat] = _load_slot_templates(_mat)
                    allSlotChamferMap[_mat] = _load_slot_chamfer_templates(_mat)
            
            _sync_maps_to_runtime_state()
            _rebuildHoleListForPalette(force=True)
            
            palettes = adsk.core.Application.get().userInterface.palettes
            pal = palettes.itemById('holeProcessPalette')
            if pal:
                pal.isVisible = True
                _apply_fixed_palette_size(pal)
                pal.sendInfoToHTML('init', _buildInitData())
                _palette = pal
                diagnostics.register_main_palette(_palette)
            else:
                from pathlib import Path
                _html_url = Path(_html_path).as_uri() + '?v=' + ADDIN_VERSION
                pal = palettes.add('holeProcessPalette', f'{ADDIN_DISPLAY_NAME} {ADDIN_VERSION}', _html_url, True, True, True, 1440, 950)
                pal.dockingOption = adsk.core.PaletteDockingOptions.PaletteDockOptionsToVerticalOnly
                pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
                _apply_fixed_palette_size(pal)
                
                onHTML = PaletteHTMLHandler()
                pal.incomingFromHTML.add(onHTML)
                handlers.append(onHTML)
                
                onClosed = PaletteClosedHandler()
                pal.closed.add(onClosed)
                handlers.append(onClosed)
                _palette = pal
                diagnostics.register_main_palette(_palette)
                
            _ensure_diag_palette(visible=False)
        except Exception as e:
            adsk.core.Application.get().userInterface.messageBox(traceback.format_exc())

# ===========================================================================
# MCP socket server thread (Port 9877)
# ===========================================================================

MCP_PORT = 9877
mcp_keep_running = threading.Event()
mcp_server_thread = None
mcp_event_id = 'HoleProcessMCPEventId'
mcp_custom_event = None
mcp_event_handler = None
mcp_response_queue = queue.Queue()

def mcp_tcp_server_worker():
    global mcp_keep_running
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('127.0.0.1', MCP_PORT))
        server_socket.listen(5)
        server_socket.settimeout(1.0)
        
        while mcp_keep_running.is_set():
            try:
                client_socket, addr = server_socket.accept()
            except socket.timeout:
                continue
            except Exception as e:
                break
                
            client_socket.settimeout(5.0)
            buffer = ""
            while mcp_keep_running.is_set():
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    buffer += data.decode('utf-8')
                    if "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if not line.strip():
                            continue
                        
                        try:
                            request_payload = json.loads(line)
                        except Exception as parse_err:
                            err_resp = {"success": False, "error": f"JSON parse error: {str(parse_err)}"}
                            client_socket.sendall((json.dumps(err_resp) + "\n").encode('utf-8'))
                            continue
                            
                        while not mcp_response_queue.empty():
                            mcp_response_queue.get_nowait()
                            
                        # Post request to Fusion 360 main UI thread
                        adsk.core.Application.get().fireCustomEvent(mcp_event_id, json.dumps(request_payload))

                        _slow_mcp_actions = {
                            "batch_import_reference_library",
                            "import_cam_from_active_document",
                            "run_intuitive_one_click",
                            "run_intuitive_programming",
                            "run_thinking_programming",
                            "get_ai_recommendations",
                            "scan_machining_features",
                            "refresh_vision_snapshot",
                        }
                        _mcp_action = request_payload.get("action") or ""
                        _mcp_wait = 900.0 if _mcp_action in _slow_mcp_actions else 45.0
                        if _mcp_action == "batch_import_reference_library" and (request_payload.get("params") or {}).get("status_only"):
                            _mcp_wait = 45.0

                        try:
                            response = mcp_response_queue.get(timeout=_mcp_wait)
                        except queue.Empty:
                            response = {"success": False, "error": "Fusion 360 main thread execution timed out."}
                            
                        client_socket.sendall((json.dumps(response) + "\n").encode('utf-8'))
                except socket.timeout:
                    continue
                except Exception as e:
                    break
            client_socket.close()
    except Exception as e:
        pass
    finally:
        server_socket.close()

def process_mcp_request(action, params):
    global camSetup, des_obj, cam_obj, app
    _mcp_ok_without_active_doc = action in (
        "batch_import_reference_library",
        "list_reference_f3z",
        "list_reference_files",
        "scan_reference_library",
        "get_addin_info",
        "get_cam_agent_manifest",
        "get_fusion_ai_gap_audit_pack",
        "knowledge_stats",
        "knowledge_query",
        "knowledge_export",
        "knowledge_rebuild_index",
        "knowledge_merge_duplicates",
        "knowledge_resolve_templates",
        "query_material_physics",
        "query_tool_library",
        "query_keili_catalog",
    )
    if _mcp_ok_without_active_doc:
        try:
            if not app:
                app = adsk.core.Application.get()
                runtime_state.app = app
            _validate_and_refresh_refs()
        except Exception:
            pass
    elif not _validate_and_refresh_refs():
        return {"success": False, "error": "No active document context found."}

    if action == "get_addin_info":
        setups = []
        if cam_obj:
            for i in range(cam_obj.setups.count):
                setups.append(cam_obj.setups.item(i).name)
        return {
            "success": True,
            "data": {
                "version": ADDIN_VERSION,
                "active_document": app.activeDocument.name if app.activeDocument else "None",
                "setups": setups,
                "current_setup": camSetup.name if camSetup else "None",
                "current_material": getattr(runtime_state, "current_material", "AL6061")
            }
        }

    elif action == "get_cam_agent_manifest":
        try:
            from smart_ai_cam_mcp.agent_manifest import build_agent_manifest

            live = None
            try:
                from Smart_AI.memory.knowledge_db import get_db

                live = get_db().get_statistics()
            except Exception:
                pass
            return {
                "success": True,
                "data": build_agent_manifest(
                    addin_version=ADDIN_VERSION,
                    addin_dir=_addin_dir,
                    live_stats=live,
                ),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "get_fusion_ai_gap_audit_pack":
        try:
            from smart_ai_cam_mcp.agent_manifest import build_gap_audit_pack

            return {
                "success": True,
                "data": build_gap_audit_pack(
                    addin_version=ADDIN_VERSION,
                    addin_dir=_addin_dir,
                    include_live_knowledge=True,
                ),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}
        
    elif action == "scan_machining_features":
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        runtime_state.current_material = material
        
        _rebuildHoleListForPalette(force=True)
        
        holes_data = _buildHoleData(material)
        slots_data = _buildSlotData(material)
        pocket_corner_r_data = _buildPocketCornerRData(material)
        flat_depths = _scanFlatDepths()
        _refresh_fusion_official_recognition()
        _refresh_feature_catalog()
        _refresh_contour_2d_recognition()
        _refresh_vision_snapshot()
        
        feat_cat = getattr(runtime_state, "feature_catalog", None)
        try:
            from Smart_AI.reasoning.machining_feature_catalog import catalog_summary_for_init
        except ImportError:
            from .Smart_AI.reasoning.machining_feature_catalog import catalog_summary_for_init
        feat_summary = catalog_summary_for_init(feat_cat)

        c2d = getattr(runtime_state, "contour_2d_recognition", None) or {}
        rec_templates = dict(c2d.get("recommended_templates") or {})
        try:
            from Smart_AI.reasoning.feature_apply import merge_contour_chamfer_template

            chamfer_n = int((feat_cat or {}).get("counts_by_category", {}).get("chamfer_bevel", 0) or 0)
            rec_templates = merge_contour_chamfer_template(
                rec_templates,
                chamfer_bevel_count=chamfer_n,
                contour_chamfer_names=_contour_chamfer_template_names(material),
            )
        except Exception:
            pass
        c2d_summary = _contour2d_summary_for_mcp()
        if rec_templates:
            c2d_summary = dict(c2d_summary)
            c2d_summary["recommended_templates"] = rec_templates

        try:
            from smart_ai_cam_vision import vision_summary_for_init

            vision_summary = vision_summary_for_init(
                getattr(runtime_state, "vision_snapshot", None)
            )
        except Exception:
            vision_summary = None

        cam_depth_ctx = None
        try:
            from Smart_AI.reasoning.cam_depth_plan import build_cam_depth_context

            cam_depth_ctx = build_cam_depth_context(flat_depths)
        except Exception:
            pass
        
        return {
            "success": True,
            "data": {
                "holes": holes_data,
                "slots": slots_data,
                "pocket_corner_r": pocket_corner_r_data,
                "flat_depths": flat_depths,
                "cam_depth_context": cam_depth_ctx,
                "feature_catalog": feat_cat,
                "feature_catalog_summary": feat_summary,
                "fusion_official_recognition": getattr(runtime_state, "fusion_official_recognition", None),
                "official_pockets": _buildOfficialPocketData(material),
                "official_slot_pockets": _buildOfficialSlotPocketData(material),
                "official_pocket_slots": _buildOfficialPocketSlotData(material),
                "contour2dRecognition": c2d_summary,
                "recommended_templates": rec_templates,
                "vision": vision_summary,
            }
        }

    elif action == "refresh_vision_snapshot":
        mode = str(params.get("vision_mode") or getattr(runtime_state, "vision_mode", "FAST_2D")).strip()
        if mode:
            runtime_state.vision_mode = mode
        if bool(params.get("rescan_holes", False)):
            _rebuildHoleListForPalette(force=True)
        _refresh_vision_snapshot()
        snap = getattr(runtime_state, "vision_snapshot", None)
        try:
            from smart_ai_cam_vision import vision_summary_for_init

            summary = vision_summary_for_init(snap)
        except Exception:
            summary = None
        points_n = 0
        preview_source = ""
        if isinstance(snap, dict):
            feats = snap.get("recognized_features") or {}
            points_n = len(feats.get("points_3d") or [])
            preview_source = str(
                ((snap.get("scan_diagnostics") or {}).get("spherical_scan") or {}).get(
                    "preview_source", ""
                )
            )
        return {
            "success": True,
            "data": {
                "vision_mode": getattr(runtime_state, "vision_mode", "FAST_2D"),
                "points_3d_count": points_n,
                "preview_source": preview_source,
                "vision": summary,
                "vision_snapshot": snap,
            },
        }

    elif action == "get_vision_snapshot":
        snap = getattr(runtime_state, "vision_snapshot", None)
        if not snap:
            return {"success": False, "error": "vision_snapshot is empty; call refresh_vision_snapshot first."}
        try:
            from smart_ai_cam_vision import vision_summary_for_init

            summary = vision_summary_for_init(snap)
        except Exception:
            summary = None
        return {
            "success": True,
            "data": {
                "vision": summary,
                "vision_snapshot": snap,
            },
        }
        
    elif action == "recognize_contour_2d":
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        runtime_state.current_material = material
        rescan = bool(params.get("rescan", False))
        try:
            from Smart_AI.perception.contour_2d_recognizer import run_recognize_contour_2d_flow

            flow = run_recognize_contour_2d_flow(
                material, _build_ai_rec_context(), rescan_holes=rescan
            )
            return {"success": True, "data": flow}
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}
        
    elif action == "execute_machining_plan":
        plan_data = params.get("data", {})
        if not plan_data:
            return {"success": False, "error": "No plan data provided."}
        _executeFromPalette(plan_data)
        return {"success": True, "message": "CAM Machining operations generated successfully."}
        
    elif action == "verify_tool_library":
        tools = []
        if cam_obj:
            try:
                doc_library = cam_obj.documentToolLibrary
                for i in range(doc_library.count):
                    tool = doc_library.item(i)
                    t_info = {
                        "index": i, "number": -1, "diameter_mm": 0.0,
                        "flute_length_mm": 0.0, "type": "Unknown", "label": ""
                    }
                    try: t_info["number"] = int(tool.number)
                    except Exception:
                        try: t_info["number"] = int(tool.parameters.itemByName('tool_number').value.value)
                        except Exception: pass
                    try: t_info["diameter_mm"] = float(tool.parameters.itemByName('tool_diameter').value.value) * 10.0
                    except Exception:
                        try: t_info["diameter_mm"] = float(tool.diameter) * 10.0
                        except Exception: pass
                    try: t_info["flute_length_mm"] = float(tool.parameters.itemByName('tool_fluteLength').value.value) * 10.0
                    except Exception: pass
                    try: t_info["type"] = str(tool.parameters.itemByName('tool_type').value.value)
                    except Exception:
                        try: t_info["type"] = str(tool.type)
                        except Exception: pass
                    try: t_info["label"] = str(tool.parameters.itemByName('tool_description').value.value)
                    except Exception:
                        try: t_info["label"] = str(tool.description)
                        except Exception: pass
                    tools.append(t_info)
            except Exception as e:
                pass
        return {"success": True, "tools": tools}
        
    elif action == "auto_create_cam_setup":
        if not cam_obj:
            return {"success": False, "error": "CAM environment not active."}
        try:
            setup_name = str(params.get("name") or params.get("setup_name") or "AI_Auto_Setup").strip()
            setup_input = cam_obj.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
            new_setup = cam_obj.setups.add(setup_input)
            new_setup.name = setup_name
            camSetup = new_setup
            runtime_state.cam_setup = new_setup
            _rebuildHoleListForPalette(force=True)
            return {
                "success": True,
                "message": "Created CAM Setup '{}'.".format(new_setup.name),
                "setup_name": new_setup.name
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create Setup: {str(e)}"}
            
    elif action == "get_machining_report":
        if not camSetup:
            return {"success": False, "error": "No active CAM Setup found."}
        try:
            needs_gen = []
            for op in camSetup.allOperations:
                if not op.isGenerationCompleted:
                    needs_gen.append(op)
            if needs_gen:
                cam_obj.generateToolpath(camSetup)
                import time
                start_wait = time.time()
                while time.time() - start_wait < 5.0:
                    adsk.doEvents()
                    all_done = True
                    for op in camSetup.allOperations:
                        if not op.isGenerationCompleted:
                            all_done = False
                            break
                    if all_done:
                        break
                    time.sleep(0.2)
            
            total_time_seconds = 0.0
            operations_info = []
            warnings_and_errors = []
            
            for op in camSetup.allOperations:
                op_time = 0.0
                if op.isGenerationCompleted:
                    try:
                        op_time = float(op.estimatedMachiningTime)
                        total_time_seconds += op_time
                    except:
                        pass
                
                op_status = "Completed" if op.isGenerationCompleted else "Generating"
                if op.hasErrors:
                    op_status = "Error"
                elif op.hasWarnings:
                    op_status = "Warning"
                    
                err_msg = ""
                warn_msg = ""
                if op.hasErrors:
                    try: err_msg = str(op.error)
                    except: err_msg = "Unknown error"
                    warnings_and_errors.append({
                        "type": "Error", "operation": op.name, "message": err_msg
                    })
                if op.hasWarnings:
                    try: warn_msg = str(op.warning)
                    except: warn_msg = "Unknown warning"
                    warnings_and_errors.append({
                        "type": "Warning", "operation": op.name, "message": warn_msg
                    })
                    
                operations_info.append({
                    "name": op.name, "status": op_status,
                    "machining_time_seconds": round(op_time, 2),
                    "has_errors": bool(op.hasErrors), "has_warnings": bool(op.hasWarnings)
                })
                
            hours = int(total_time_seconds // 3600)
            minutes = int((total_time_seconds % 3600) // 60)
            seconds = int(total_time_seconds % 60)
            time_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
            
            return {
                "success": True,
                "data": {
                    "setup_name": camSetup.name,
                    "total_machining_time_seconds": round(total_time_seconds, 2),
                    "formatted_machining_time": time_str,
                    "operations": operations_info,
                    "warnings_and_errors": warnings_and_errors
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get report: {str(e)}"}
            
    elif action == "get_cam_depth_plan":
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        runtime_state.current_material = material
        try:
            flat_depths = _scanFlatDepths()
            decisions = {}
            if params.get("include_ai_tuning"):
                from Smart_AI.reasoning import ai_recommendations

                rec = ai_recommendations.run_get_ai_recommendations(params, _build_ai_rec_context())
                if rec.get("success"):
                    decisions = (rec.get("data") or {}).get("decisions") or {}
            from Smart_AI.reasoning.cam_depth_plan import build_cam_depth_context

            ctx = build_cam_depth_context(flat_depths, ai_decisions=decisions)
            return {
                "success": True,
                "data": {
                    "material": material,
                    "flat_depths": flat_depths,
                    "cam_depth_context": ctx,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "verify_cam_depth_plan":
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        try:
            from Smart_AI.reasoning import ai_recommendations
            from Smart_AI.reasoning.cam_depth_plan import build_cam_depth_context

            flat_depths = _scanFlatDepths()
            rec = ai_recommendations.run_get_ai_recommendations(
                {"material": material, "thinking_layer": params.get("thinking_layer", "L1_extended_features")},
                _build_ai_rec_context(),
            )
            ai_data = rec.get("data") or {}
            ctx = ai_data.get("cam_depth_context") or build_cam_depth_context(
                flat_depths, ai_decisions=ai_data.get("decisions")
            )
            rough = ctx.get("top_face_rough") or {}
            checks = [
                {
                    "id": "stock_remove",
                    "ok": float(rough.get("stock_remove_mm", 0) or 0) >= 0,
                    "value": rough.get("stock_remove_mm"),
                },
                {
                    "id": "top_height_stock_top",
                    "ok": rough.get("topHeight_mode") == "from stock top",
                    "value": rough.get("topHeight_mode"),
                },
                {
                    "id": "bottom_height_surface_top",
                    "ok": rough.get("bottomHeight_mode") == "from surface top",
                    "value": rough.get("bottomHeight_mode"),
                },
                {
                    "id": "ai_recommendations",
                    "ok": bool(rec.get("success")),
                    "value": rec.get("success"),
                },
            ]
            all_ok = all(c.get("ok") for c in checks)
            return {
                "success": True,
                "data": {
                    "verified": all_ok,
                    "checks": checks,
                    "cam_depth_context": ctx,
                    "recommended_templates": ai_data.get("recommended_templates"),
                    "terrace_face_ops": (ai_data.get("panel_apply") or {}).get("terrace_face_ops"),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "get_ai_recommendations":
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        runtime_state.current_material = material
        try:
            from Smart_AI.reasoning import ai_recommendations

            return ai_recommendations.run_get_ai_recommendations(params, _build_ai_rec_context())
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action in (
        "knowledge_stats",
        "knowledge_feedback",
        "knowledge_export",
        "knowledge_import",
        "knowledge_rebuild_index",
        "knowledge_merge_duplicates",
        "knowledge_resolve_templates",
        "knowledge_query",
    ):
        try:
            from Smart_AI.reasoning import ai_training

            return ai_training.handle_knowledge_mcp(action, params)
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action in ("list_reference_f3z", "list_reference_files"):
        try:
            from Smart_AI.reasoning import cam_reference_import

            return {"success": True, "data": cam_reference_import.list_reference_files()}
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "scan_reference_library":
        try:
            script = os.path.join(_addin_dir, "scripts", "scan_reference_library.py")
            spec = importlib.util.spec_from_file_location("scan_reference_library", script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.scan_reference_dir()
            if res.get("ok"):
                return {"success": True, "data": res.get("manifest"), "manifest_path": res.get("manifest_path")}
            return {"success": False, "error": res.get("error", "scan failed")}
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "import_cam_from_active_document":
        if not cam_obj:
            return {"success": False, "error": "請先進入 Manufacture 並開啟含 CAM 的文件"}
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        all_setups = bool(params.get("all_setups", True))
        write_db = bool(params.get("write_db", True))
        save_snapshot = bool(params.get("save_snapshot", True))
        doc_label = ""
        try:
            if des_obj:
                doc_label = str(des_obj.parentDocument.name or "")
        except Exception:
            pass
        try:
            from Smart_AI.reasoning import cam_reference_import

            scan_geometry = bool(params.get("scan_geometry", True))
            scan_ctx = _build_ai_rec_context() if scan_geometry else None
            _ensure_template_maps_loaded()
            return cam_reference_import.run_import_cam_from_active_document(
                cam_obj,
                active_setup=camSetup,
                material=material,
                all_setups=all_setups,
                write_db=write_db,
                save_snapshot=save_snapshot,
                document_label=doc_label,
                scan_geometry=scan_geometry,
                scan_ctx=scan_ctx,
                tmpl_lib=tmplLib,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "batch_import_reference_library":
        try:
            from Smart_AI.reasoning import reference_batch_import as rbi

            def _batch_refresh():
                global des_obj, cam_obj, camSetup, tmplLib
                _validate_and_refresh_refs()
                _ensure_template_maps_loaded()
                doc = app.activeDocument if app else None
                if doc:
                    try:
                        des_obj = adsk.fusion.Design.cast(
                            doc.products.itemByProductType("DesignProductType")
                        )
                    except Exception:
                        des_obj = None
                    cam_obj = _safe_cam_from_document(doc)
                    runtime_state.cam_obj = cam_obj
                    runtime_state.des_obj = des_obj
                    camSetup = None
                    if cam_obj and int(cam_obj.setups.count) > 0:
                        for _i in range(cam_obj.setups.count):
                            _s = cam_obj.setups.item(_i)
                            if getattr(_s, "isActive", False):
                                camSetup = _s
                                break
                        if camSetup is None:
                            camSetup = cam_obj.setups.item(0)
                    runtime_state.cam_setup = camSetup
                tmplLib = runtime_state.tmpl_lib
                return {"cam_obj": cam_obj, "des_obj": des_obj, "cam_setup": camSetup}

            material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
            max_files = int(params.get("max_files", 1) or 1)
            open_file = bool(params.get("open_file", True))
            scan_geometry = bool(params.get("scan_geometry", True))
            reset = bool(params.get("reset", False))
            retry_failed = bool(params.get("retry_failed", False))
            close_after_import = bool(params.get("close_after_import", True))

            if bool(params.get("status_only", False)):
                return {"success": True, "data": rbi.get_batch_import_status()}

            _ensure_template_maps_loaded()
            if open_file:
                _batch_refresh()
            return rbi.run_batch_import_step(
                app,
                cam_obj,
                active_setup=camSetup,
                material=material,
                max_files=max_files,
                open_file=open_file,
                scan_geometry=scan_geometry,
                scan_ctx=_build_ai_rec_context() if scan_geometry else None,
                tmpl_lib=tmplLib,
                refresh_doc_refs=_batch_refresh,
                reset=reset,
                retry_failed=retry_failed,
                close_after_import=close_after_import,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "check_intuitive_eligibility":
        try:
            from Smart_AI.reasoning import intuitive_programming

            return intuitive_programming.run_check_intuitive_eligibility(
                params, _build_ai_rec_context()
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "run_intuitive_one_click":
        try:
            from Smart_AI.reasoning import intuitive_programming
            from Smart_AI.reasoning import ai_recommendations

            def _ensure_setup_oc():
                if camSetup:
                    return {"success": True}
                return process_mcp_request("auto_create_cam_setup", {})

            _ensure_template_maps_loaded()
            return intuitive_programming.run_intuitive_one_click(
                params,
                _build_ai_rec_context(),
                get_recommendations=ai_recommendations.run_get_ai_recommendations,
                execute_from_palette=_executeFromPalette,
                ensure_cam_setup=_ensure_setup_oc,
                ensure_template_maps=_ensure_template_maps_loaded,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "run_intuitive_programming":
        try:
            from Smart_AI.reasoning import intuitive_programming
            from Smart_AI.reasoning import ai_recommendations

            def _ensure_setup():
                if camSetup:
                    return {"success": True}
                return process_mcp_request("auto_create_cam_setup", {})

            return intuitive_programming.run_intuitive_programming(
                params,
                _build_ai_rec_context(),
                get_recommendations=ai_recommendations.run_get_ai_recommendations,
                execute_from_palette=_executeFromPalette,
                ensure_cam_setup=_ensure_setup,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "check_thinking_eligibility":
        try:
            from Smart_AI.reasoning import thinking_programming

            return thinking_programming.run_check_thinking_eligibility(
                params, _build_ai_rec_context()
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "get_thinking_layers":
        try:
            from Smart_AI.reasoning import thinking_programming

            return {"success": True, "data": thinking_programming.describe_layers()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action == "run_thinking_programming":
        try:
            from Smart_AI.reasoning import thinking_programming
            from Smart_AI.reasoning import ai_recommendations

            def _ensure_setup_thinking():
                if camSetup:
                    return {"success": True}
                return process_mcp_request("auto_create_cam_setup", {})

            return thinking_programming.run_thinking_programming(
                params,
                _build_ai_rec_context(),
                get_recommendations=ai_recommendations.run_get_ai_recommendations,
                execute_from_palette=_executeFromPalette,
                ensure_cam_setup=_ensure_setup_thinking,
                full_rescan=_fullRescanForPalette,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "get_multi_setup_plan":
        try:
            from Smart_AI.reasoning import thinking_l2_plan as l2

            pid = str(params.get("plan_id") or params.get("multi_setup_plan_id") or "").strip()
            plan = l2.get_cached_multi_setup_plan(pid or None)
            if not plan and pid:
                plan = l2.load_persisted_multi_setup_plan(pid)
            if not plan:
                return {"success": False, "error": "No cached L2 multi-setup plan."}
            return {"success": True, "data": plan}
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    elif action == "run_internal_ai_autopilot":
        if not params.get("allow_legacy"):
            return {
                "success": False,
                "error": (
                    "run_internal_ai_autopilot 已停用（無直覺式資格閘門）。"
                    "請改用 run_intuitive_one_click 或 run_intuitive_programming；"
                    "腳本若必須沿用請傳 allow_legacy=true。"
                ),
                "deprecated": True,
                "prefer_action": "run_intuitive_one_click",
            }
        material = params.get("material", getattr(runtime_state, "current_material", "AL6061"))
        if not camSetup:
            res_setup = process_mcp_request("auto_create_cam_setup", {})
            if not res_setup.get("success"):
                return {"success": False, "error": res_setup.get("error", "Setup failed")}
        res_ai = process_mcp_request("get_ai_recommendations", {"material": material})
        if not res_ai.get("success"):
            return res_ai
        ai_data = res_ai.get("data", {})
        try:
            from Smart_AI.reasoning import intuitive_programming

            autopilot_plan = intuitive_programming.build_execute_plan_from_ai(
                ai_data,
                setup_name=camSetup.name if camSetup else "",
                material=material,
            )
        except Exception:
            panel = ai_data.get("panel_apply") or {}
            rec = ai_data.get("recommended_templates") or {}
            hole_rows = []
            for pr in panel.get("hole_rows") or []:
                if isinstance(pr, dict):
                    hole_rows.append({"idx": pr.get("idx"), "tmplIdx": pr.get("tmplIdx", 0)})
            autopilot_plan = {
                "setup": camSetup.name if camSetup else "",
                "material": material,
                "topFaceRough": rec.get("topFaceRough", "(不使用)"),
                "topFaceFinish": rec.get("topFaceFinish", "(不使用)"),
                "profileRough": rec.get("profileRough", "(不使用)"),
                "profileFinish": rec.get("profileFinish", "(不使用)"),
                "rows": hole_rows,
                "slotRows": panel.get("slot_rows") or [],
                "pocketCornerRRows": panel.get("pocket_corner_r_rows") or [],
                "mode": "all",
            }
        _executeFromPalette(autopilot_plan)
        return {"success": True, "message": "Autopilot execute triggered", "plan": autopilot_plan}

    elif action == "execute_python_code":
        code_to_run = params.get("code", "")
        if not code_to_run:
            return {"success": False, "error": "No python code provided."}
            
        import io

        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output
        
        local_vars = {
            "app": app, "ui": ui, "adsk": adsk,
            "design": des_obj, "cam_obj": cam_obj, "camSetup": camSetup,
            "holeInfoList": holeInfoList, "slotInfoList": slotInfoList, "result": None
        }
        
        try:
            exec(code_to_run, globals(), local_vars)
            sys.stdout = old_stdout
            stdout_str = redirected_output.getvalue()
            return {
                "success": True, "stdout": stdout_str, "result": str(local_vars.get("result", None))
            }
        except Exception as exec_err:
            sys.stdout = old_stdout
            return {
                "success": False, "error": f"Execution error:\n{traceback.format_exc()}",
                "stdout": redirected_output.getvalue()
            }
            
    # ── 材質物理引擎 MCP 接口 (cam-helper 專用) ───────────────────────
    elif action == "query_material_physics":
        # 提供 cam-helper 等外部 AI 直接呼叫 Smart_AI_CAM 內部材質物理引擎
        # mode == "lookup"   : 只查 MATERIAL_DATABASE 取材質物性 (預設)
        # mode == "calculate": 同時計算最佳 RPM/Feed (需 tool_dia)
        # params:
        #   material:    材質鍵 (AL6061/S50C/SUS304/Brass/Plastics)，未指定則回傳全部
        #   tool_dia:    刀具直徑 mm (calculate 模式必填)
        #   teeth:       刀刃數 (預設 4)
        #   is_drill:    bool (預設 False)
        #   is_tap:      bool (預設 False)
        #   pitch:       螺距 mm (攻牙時用，預設 1.0)
        #   mode:        "lookup" | "calculate" (預設依 tool_dia 自動判斷)
        try:
            try:
                from Smart_AI.reasoning.ai_decision_engine import (
                    MATERIAL_DATABASE,
                    calculate_feeds_and_speeds,
                )
            except ImportError:
                from .Smart_AI.reasoning.ai_decision_engine import (
                    MATERIAL_DATABASE,
                    calculate_feeds_and_speeds,
                )

            material = params.get("material")
            tool_dia = params.get("tool_dia")
            mode = (params.get("mode") or
                    ("calculate" if tool_dia is not None else "lookup")).lower()

            # ── 查表模式 ──────────────────────────────────────────────
            if mode == "lookup":
                if material:
                    if material not in MATERIAL_DATABASE:
                        return {
                            "success": False,
                            "error": f"材質 '{material}' 不在資料庫中",
                            "available": list(MATERIAL_DATABASE.keys()),
                        }
                    mat = MATERIAL_DATABASE[material]
                    return {
                        "success": True,
                        "data": {
                            "material": material,
                            "name": mat.get("name"),
                            "density_g_cm3": mat.get("density_g_cm3"),
                            "base_vc_m_min": mat.get("base_vc_m_min"),
                            "base_fz_mm_t": mat.get("base_fz_mm_t"),
                            "specific_energy_GPa": mat.get("specific_energy"),
                            "hardness_hb": mat.get("hardness_hb"),
                            "extra_damping": mat.get("extra_damping", 1.0),
                            "desc": mat.get("desc"),
                            "physics_model": {
                                "ref_density_g_cm3": 2.70,
                                "k_density_formula": "k = 2.70 / density",
                                "v_scale_formula":   "v_scale = k^0.55",
                                "f_scale_formula":   "f_scale = k^0.35",
                                "vc_formula":        "vc = base_vc * v_scale * extra_damping",
                                "fz_formula":        "fz = base_fz * f_scale * extra_damping",
                                "drill_correction":  "is_drill: vc *= 0.75, fz *= 0.85",
                                "tap_correction":    "is_tap:   vc *= 0.30, F = N * pitch",
                                "rpm_bounds":        [500, 18000],
                                "feed_bounds":       [50,  6000],
                            },
                        },
                    }
                else:
                    # 全部材質 (給 cam-helper 一次取完)
                    all_mats = {}
                    for k, v in MATERIAL_DATABASE.items():
                        all_mats[k] = {
                            "name": v.get("name"),
                            "density_g_cm3": v.get("density_g_cm3"),
                            "base_vc_m_min": v.get("base_vc_m_min"),
                            "base_fz_mm_t": v.get("base_fz_mm_t"),
                            "specific_energy_GPa": v.get("specific_energy"),
                            "hardness_hb": v.get("hardness_hb"),
                            "extra_damping": v.get("extra_damping", 1.0),
                            "desc": v.get("desc"),
                        }
                    return {
                        "success": True,
                        "data": {
                            "materials": all_mats,
                            "count": len(all_mats),
                        },
                    }

            # ── 計算模式 ──────────────────────────────────────────────
            elif mode == "calculate":
                if not material:
                    return {"success": False, "error": "calculate 模式需指定 material"}
                if tool_dia is None:
                    return {"success": False, "error": "calculate 模式需指定 tool_dia"}
                if material not in MATERIAL_DATABASE:
                    return {
                        "success": False,
                        "error": f"材質 '{material}' 不在資料庫中",
                        "available": list(MATERIAL_DATABASE.keys()),
                    }
                try:
                    tool_dia_f = float(tool_dia)
                except (TypeError, ValueError):
                    return {"success": False, "error": f"tool_dia 必須是數字，得到: {tool_dia!r}"}
                teeth = int(params.get("teeth", 4) or 4)
                is_drill = bool(params.get("is_drill", False))
                is_tap = bool(params.get("is_tap", False))
                pitch = float(params.get("pitch", 1.0) or 1.0)

                result = calculate_feeds_and_speeds(
                    material, tool_dia_f, teeth,
                    is_drill=is_drill, is_tap=is_tap, pitch_mm=pitch,
                )
                mat = MATERIAL_DATABASE[material]
                return {
                    "success": True,
                    "data": {
                        "material": material,
                        "material_name": mat.get("name"),
                        "density_g_cm3": mat.get("density_g_cm3"),
                        "tool_dia_mm": tool_dia_f,
                        "teeth": teeth,
                        "is_drill": is_drill,
                        "is_tap": is_tap,
                        "pitch_mm": pitch if is_tap else None,
                        "rpm": result["rpm"],
                        "feed_mm_min": result["feed"],
                        "vc_m_min": result["vc_m_min"],
                        "fz_mm_tooth": result["fz_mm_t"],
                        "k_density": result["k_density"],
                        "explanation": (
                            f"{material} (密度 {mat['density_g_cm3']} g/cm³) + "
                            f"D{tool_dia_f}mm × {teeth} 刃"
                            + (" 鑽孔" if is_drill else (" 攻牙" if is_tap else " 銑削"))
                            + f"：vc={result['vc_m_min']} m/min, "
                            f"S={result['rpm']} rpm, F={result['feed']} mm/min, "
                            f"fz={result['fz_mm_t']} mm/tooth"
                        ),
                    },
                }
            else:
                return {
                    "success": False,
                    "error": f"未知 mode: {mode}",
                    "valid_modes": ["lookup", "calculate"],
                }

        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 奇力揚目錄 MCP 接口 (廠商推薦切削參數) ────────────────────────
    elif action == "query_keili_catalog":
        # 提供 cam-helper 等外部 AI 查詢奇力揚 (KEILI) 刀具廠商 2023 目錄
        # 三系列：CIB 鋼用重切削 / CAVN 不鏽鋼鈦合金 / CLUS 鋁用鏡面
        # 廠商推薦值優先於物理引擎 (用戶實機驗證過更準)
        # mode:
        #   list_series:  三系列總覽 (預設)
        #   get_series:   單系列詳細 (需 series)
        #   list_tools:   列舉系列刀具 (需 series, 可選 diameter_mm 過濾)
        #   recommend:    ★主要 API★ 給材質+刀徑 → 計算廠商推薦 RPM/Feed
        try:
            try:
                from smart_ai_cam_mcp.keili_catalog import dispatch as _keili_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.keili_catalog import dispatch as _keili_dispatch
            return _keili_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ─────────────────────────────────────────────────────────────────
    # ★ 智能切削參數 6 層解析器 (cutting_resolver.py) — 主入口
    # ─────────────────────────────────────────────────────────────────
    # L1 GOLD (本地 preset) > L2A (GoldCobra 硬車) > L2B (用戶 5 工法)
    # > L2C (奇力揚) > L2D (銘九通用) > L3 (推斷引擎)
    # 給定 material + tool_dia + operation → 一鍵拿到最高信賴度的切削參數
    elif action == "query_smart_cutting":
        try:
            try:
                from smart_ai_cam_mcp.cutting_resolver import dispatch as _resolver_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.cutting_resolver import dispatch as _resolver_dispatch
            return _resolver_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 用戶口傳 5 工法 + 8 刀把 + Chip Thinning (regular_milling) ──────
    # mode:
    #   recommend       (預設) S50C/AL/SUS 等常規 5 工法計算
    #   list_profiles   5 工法清單 + Vc 縮放表
    #   list_holders    8 種刀把規格全表
    #   recommend_holder 工法 → 推薦刀把
    #   compute_hex / fz_for_hex  Chip Thinning 數學工具
    elif action == "query_regular_milling":
        try:
            try:
                from smart_ai_cam_mcp.regular_milling import dispatch as _rm_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.regular_milling import dispatch as _rm_dispatch
            return _rm_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── GoldCobra 硬車鋼專用 (gold_cobra_catalog) ──────────────────────
    # 「Z 軸長吃, X/Y 軸薄吃」+ 側壁⇔平面 /2 對調
    # mode: recommend / list_series / list_bands / convert_apae
    elif action == "query_gold_cobra":
        try:
            try:
                from smart_ai_cam_mcp.gold_cobra_catalog import dispatch as _gcc_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.gold_cobra_catalog import dispatch as _gcc_dispatch
            return _gcc_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 銘九通用切削表 (general_catalog) + sanity_check 防護層 ──────────
    # mode: recommend / sanity_check / list_routes
    elif action == "query_general_catalog":
        try:
            try:
                from smart_ai_cam_mcp.general_catalog import dispatch as _gc_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.general_catalog import dispatch as _gc_dispatch
            return _gc_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 推斷引擎 + 物理上限 (machining_heuristics) ──────────────────────
    # mode: list_rules / operation_factors / vc_ceiling / feed_ceiling /
    #       substitute / apply_ceilings / derive / estimate_tool_geometry
    elif action == "query_heuristics":
        try:
            try:
                from smart_ai_cam_mcp.machining_heuristics import dispatch as _mh_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.machining_heuristics import dispatch as _mh_dispatch
            return _mh_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 刀把規格表 (tool_holders) — 機台 RPM 軟上限 ─────────────────────
    elif action == "query_tool_holders":
        try:
            try:
                from smart_ai_cam_mcp.tool_holders import dispatch as _th_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.tool_holders import dispatch as _th_dispatch
            return _th_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 本地刀具庫 MCP 接口 (cam-helper 專用) ─────────────────────────
    elif action == "query_tool_library":
        # 提供 cam-helper 等外部 AI 查詢/搜尋/最佳匹配 Fusion 360 本地刀具庫
        # 路徑預設: %APPDATA%\Autodesk\CAM360\libraries\Local\加工刀具
        # 可由 params.library_path 覆蓋 (或環境變數 SMART_AI_CAM_TOOL_LIB)
        # mode:
        #   stats:     150 把刀總覽、分類分布、材質分布、直徑分布
        #   list:      列舉特定分類 (params.category) 所有刀
        #   search:    依條件搜尋 (diameter_mm/category/material_target/teeth)
        #   find_best: 加工需求 → 最佳刀推薦 (feature_type+material_target+diameter)
        try:
            try:
                from smart_ai_cam_mcp.tool_library_query import dispatch as _tlq_dispatch
            except ImportError:
                from .smart_ai_cam_mcp.tool_library_query import dispatch as _tlq_dispatch
            return _tlq_dispatch(params or {})
        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

    # ── 知識庫 MCP 接口 ────────────────────────────────────────────────
    elif action == "get_knowledge_stats":
        try:
            from Smart_AI.memory.knowledge_db import get_db
            stats = get_db().get_statistics()
            return {"success": True, "data": stats}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action == "query_best_template":
        # params: {feature_type, material, geometry}
        try:
            from Smart_AI.memory.knowledge_db import get_db
            ft  = params.get("feature_type", "hole")
            mat = params.get("material", "AL6061")
            geo = params.get("geometry", {})
            result = get_db().query_best_template(ft, mat, geo)
            if result:
                return {"success": True, "data": result}
            else:
                return {"success": True, "data": None, "message": "歷史記錄不足，暫無推薦"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action == "query_all_recommendations":
        # params: {material, min_confidence}
        try:
            from Smart_AI.memory.knowledge_db import get_db
            mat  = params.get("material", "AL6061")
            minc = float(params.get("min_confidence", 0.3))
            recs = get_db().query_all_recommendations(mat, minc)
            return {"success": True, "data": recs, "count": len(recs)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action == "export_knowledge":
        # params: {max_records}
        try:
            from Smart_AI.memory.knowledge_db import get_db
            max_r = int(params.get("max_records", 500))
            data  = get_db().export_for_mcp(max_r)
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action == "import_ai_feedback":
        # params: {feedback_list: [{record_id, user_kept, rating, ai_comment}, ...]}
        try:
            from Smart_AI.memory.knowledge_db import get_db
            fb_list = params.get("feedback_list", [])
            result  = get_db().import_ai_feedback(fb_list)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action == "run_knowledge_bootstrap":
        # 強制重新從代碼引導知識庫（params: {force: true/false}）
        try:
            from Smart_AI.memory.knowledge_db import get_db
            from Smart_AI.memory.knowledge_bootstrap import bootstrap_knowledge
            force  = bool(params.get("force", False))
            result = bootstrap_knowledge(get_db(), force=force)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    else:
        return {"success": False, "error": f"Unknown MCP action: '{action}'"}

class AddInMCPCustomEventHandler(adsk.core.CustomEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            data_str = args.additionalInfo
            request = json.loads(data_str)
            action = request.get("action")
            params = request.get("params", {})
            
            res = process_mcp_request(action, params)
            mcp_response_queue.put(res)
        except Exception as e:
            mcp_response_queue.put({"success": False, "error": f"MCP Handler error: {str(e)}"})

# ===========================================================================
# Lifecycle Methods
# ===========================================================================

def run(context):
    global app, ui, camSetup, tmplLib, allDrillMap, allChamferMap, allTopFaceMap, allProfileMap, cam_obj, des_obj
    global allTopFaceRoughMap, allTopFaceFinishMap, allProfileRoughMap, allProfileFinishMap
    global allCountersinkMap
    global mcp_keep_running, mcp_server_thread, mcp_custom_event, mcp_event_handler
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        
        # Register and start MCP CustomEvent & Socket server
        try:
            app.unregisterCustomEvent(mcp_event_id)
        except Exception:
            pass
        try:
            mcp_custom_event = app.registerCustomEvent(mcp_event_id)
            mcp_event_handler = AddInMCPCustomEventHandler()
            mcp_custom_event.add(mcp_event_handler)
            
            mcp_keep_running.set()
            mcp_server_thread = threading.Thread(target=mcp_tcp_server_worker)
            mcp_server_thread.daemon = True
            mcp_server_thread.start()
        except Exception as mcp_err:
            pass
            
        try:
            template_service.set_template_maps_diag_log(_template_map_load_log)
        except Exception:
            pass
            
        runtime_state.template_params_cache.clear()
        runtime_state.tool_info_cache.clear()
        _clear_template_name_cache()
        _clear_drill_tool_library_cache()
        _clear_pocket_cache()
        _clear_op_clone_cache()
        _clear_feature_face_cache()
        _clear_op_name_cache()

        cmdDefs = ui.commandDefinitions
        cmdDef = cmdDefs.itemById('holeProcessCmd')
        if cmdDef:
            try:
                cmdDef.deleteMe()
                cmdDef = None
            except:
                pass
                
        if not cmdDef:
            resDir = os.path.join(ADDIN_DIR, 'resources')
            try:
                cmdDef = cmdDefs.addButtonDefinition(
                    'holeProcessCmd',
                    ADDIN_DISPLAY_NAME,
                    '自動化編程',
                    resDir,
                )
            except Exception as e_add:
                cmdDef = cmdDefs.itemById('holeProcessCmd')
                if not cmdDef:
                    raise e_add
        onCreated = CommandCreatedHandler()
        cmdDef.commandCreated.add(onCreated)
        handlers.append(onCreated)
        
        try:
            panel = ui.allToolbarPanels.itemById(PANEL_ID)
            if not panel:
                panel = ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
            if panel:
                if not panel.controls.itemById('holeProcessCmd'):
                    ctrl = panel.controls.addCommand(cmdDef)
                    ctrl.isVisible = True
                    ctrl.isPromoted = True
                    ctrl.isPromotedByDefault = True
        except:
            pass

        # Try to resolve core objects silently
        try:
            doc = app.activeDocument
            if doc:
                des_obj = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
                cam_obj = _safe_cam_from_document(doc)
        except Exception:
            pass

        # Defer template loading to lazy-load on command click or MCP request
        try:
            mgr = adsk.cam.CAMManager.get().libraryManager
            if mgr:
                tmplLib = mgr.templateLibrary
                runtime_state.tmpl_lib = tmplLib
        except Exception as e_mgr:
            print(f"Failed to access template library manager: {e_mgr}")

        # Set default active setup
        try:
            camSetup = None
            if cam_obj:
                if runtime_state.pending_setup_name:
                    for _i in range(cam_obj.setups.count):
                        if cam_obj.setups.item(_i).name == runtime_state.pending_setup_name:
                            camSetup = cam_obj.setups.item(_i)
                            break
                    runtime_state.pending_setup_name = ''
                if camSetup is None:
                    for _i in range(cam_obj.setups.count):
                        _s = cam_obj.setups.item(_i)
                        if _s.isActive:
                            camSetup = _s
                            break
                if camSetup is None and cam_obj.setups.count > 0:
                    camSetup = cam_obj.setups.item(0)
            runtime_state.cam_setup = camSetup
        except Exception:
            pass

        # Register event handlers
        try:
            docHandler = DocumentActivatedHandler()
            app.documentActivated.add(docHandler)
            handlers.append(docHandler)
        except Exception:
            pass

        try:
            prodHandler = ActiveProductChangedHandler()
            app.activeProductChanged.add(prodHandler)
            handlers.append(prodHandler)
        except Exception:
            pass
        
        try:
            if hasattr(ui, 'userInterfaceActivated'):
                winHandler = WindowActivatedHandler()
                ui.userInterfaceActivated.add(winHandler)
                handlers.append(winHandler)
        except Exception:
            pass

        adsk.autoTerminate(False)

        # ── 知識庫引導（背景執行，不阻塞 UI 啟動）──────────────────────
        def _run_knowledge_bootstrap():
            try:
                from Smart_AI.memory.knowledge_db import get_db
                from Smart_AI.memory.knowledge_bootstrap import bootstrap_knowledge
                _db = get_db()
                result = bootstrap_knowledge(_db, force=False)
                msg = result.get('message', '')
                inj  = result.get('total_injected', 0)
                if inj:
                    print(f'[KnowledgeDB] 引導完成：注入 {inj} 筆預置知識。{msg}')
                else:
                    print(f'[KnowledgeDB] {msg}')
            except Exception as _kb_err:
                print(f'[KnowledgeDB] 引導失敗（不影響插件功能）: {_kb_err}')

        try:
            import threading as _threading
            _kb_thread = _threading.Thread(target=_run_knowledge_bootstrap)
            _kb_thread.daemon = True
            _kb_thread.start()
        except Exception:
            pass
        # ─────────────────────────────────────────────────────────────────

    except Exception as _run_e:
        import traceback as _tb
        _msg = _tb.format_exc()
        try:
            _app = adsk.core.Application.get()
            _app.userInterface.messageBox('run() 錯誤:\n' + _msg)
        except Exception:
            pass

def stop(context):
    global handlers, mcp_keep_running, mcp_custom_event, mcp_event_handler, _palette, _diag_palette
    # 儲存學習資料庫與思想庫
    try:
        from Smart_AI.memory.knowledge_db import get_db
        get_db().flush()
    except Exception:
        pass
    try:
        from Smart_AI.memory.thought_db import get_thought_db
        get_thought_db().flush()
    except Exception:
        pass
    
    # 釋放全域面板參照
    _palette = None
    _diag_palette = None
    try:
        # Stop background MCP socket server
        mcp_keep_running.clear()
        if mcp_custom_event:
            try:
                mcp_custom_event.remove(mcp_event_handler)
                adsk.core.Application.get().unregisterCustomEvent(mcp_event_id)
            except Exception:
                pass
                
        app_local = adsk.core.Application.get()
        ui_local = app_local.userInterface
        panel = ui_local.allToolbarPanels.itemById(PANEL_ID)
        if not panel:
            panel = ui_local.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        if panel:
            ctrl = panel.controls.itemById('holeProcessCmd')
            if ctrl: ctrl.deleteMe()
        cmdDef = ui_local.commandDefinitions.itemById('holeProcessCmd')
        if cmdDef: cmdDef.deleteMe()
        pal = ui_local.palettes.itemById('holeProcessPalette')
        if pal: pal.deleteMe()
        dpal = ui_local.palettes.itemById('holeProcessDiagPalette')
        if dpal: dpal.deleteMe()
        handlers.clear()
    except Exception:
        pass
