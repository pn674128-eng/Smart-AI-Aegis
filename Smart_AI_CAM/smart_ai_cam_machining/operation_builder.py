# -*- coding: utf-8 -*-
import adsk
import adsk.core, adsk.fusion, adsk.cam
import math
import os
import json
import re
import time
from smart_ai_cam_state.runtime_state import state as runtime_state
from smart_ai_cam_ui.diagnostics import send_diag_log, template_map_load_log
from smart_ai_cam_templates import template_service
from smart_ai_cam_machining.geometry_utils import (
    _coalesce_slot_chains_edge_lists,
    _resolve_slot_pocket_compensation_slug,
    _slot_pocket_align_chain_winding_with_opening_faces,
    _slot_pocket_align_chain_winding_flags,
    _filter_slot_opening_planar_faces,
    _resolve_brep_face_from_token,
    _count_brep_face_inner_loops,
    _slot_face_bucket_key
)

# Diagnostic Logging Aliases
_send_diag_log = send_diag_log
_template_map_load_log = template_map_load_log

# Configurations & Constants
TAP_DIA_MAP = {
    'M2.5-0.45':  (2.05, 2.1),
    'M3-0.5':  (2.5, 2.5),
    'M4-0.7':  (3.3, 3.3),
    'M5-0.8':  (4.2, 4.2),
    'M6-1.0':  (5.0, 5.1),
    'M8-1.0':  (7.0, 7.0),
    'M8-1.25': (6.8, 6.8),
}

TAP_SHORT_MAP = {
    'M2.5-0.45':  'M2.5',
    'M3-0.5':  'M3',
    'M4-0.7':  'M4',
    'M5-0.8':  'M5',
    'M6-1.0':  'M6',
    'M8-1.0':  'M8',
    'M8-1.25': 'M8',
}

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

REUSE_EXISTING_TEMPLATE_OPS = True
ENABLE_DRILL_LIBRARY_TOOL_MATCH = False
DRILL_LIBRARY_PRIORITY = ('SG鑽頭', 'HSS鑽頭')
SLOT_POCKET_TOOLPATH_INSIDE_SLOT = True
SLOT_POCKET_COMPENSATION_AUTO = True
SLOT_POCKET_COMPENSATION_OVERRIDE = "'left'"
SLOT_POCKET_INVERT_CHAIN_WHEN_COMP_RIGHT = True
SLOT_ALIGN_MULTI_CHAIN_WINDING = True
SLOT_ALIGN_WINDING_USE_OPENING_FACE = True
CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND = True
CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND = True

# Helper Functions
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
    except:
        pass
    try:
        f = str(fallback or '').strip()
        if f:
            return f
    except:
        pass
    return ''


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


def _mask_fullwidth_bracket_segments(text):
    try:
        return re.sub(r"\u3010[^\u3011]*\u3011", "", str(text or "")).strip()
    except Exception:
        return str(text or "").strip()


# Dynamic Module property loading via Python 3.7+ __getattr__ fallback
def __getattr__(name):
    if name == 'camSetup':
        return runtime_state.cam_setup
    if name == 'tmplLib':
        return runtime_state.tmpl_lib
    if name == 'des_obj':
        return runtime_state.des_obj
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def getToolInfoFromTemplate(tmpl_url):
    import math
    tmpl_lib = runtime_state.tmpl_lib
    cam_setup = runtime_state.cam_setup
    if not tmpl_lib or not cam_setup:
        return {}
    cacheKey = _cam_url_identity(tmpl_url)
    if cacheKey in runtime_state.tool_info_cache:
        return runtime_state.tool_info_cache[cacheKey]
    result = {}
    try:
        tmpl = tmpl_lib.templateAtURL(tmpl_url)
        ops  = cam_setup.createFromCAMTemplate(tmpl)
        if ops:
            for op in ops:
                if op.tool and getOpToolType(op) == 'drill':
                    dia   = op.tool.parameters.itemByName('tool_diameter').value.value
                    angle = op.tool.parameters.itemByName('tool_tipAngle').value.value
                    r     = dia / 2.0
                    tipH  = r / math.tan(math.radians(angle / 2.0))
                    dia_mm = round(dia * 10, 3)
                    tip_geom_mm = round(tipH * 10, 4)
                    result = {
                        'drillDia':    dia_mm,
                        'tipAngle':    round(angle, 1),
                        'tipHeightMM': tip_geom_mm,
                        'tipHeightGeomMM': tip_geom_mm,
                    }
                op.deleteMe()
    except:
        pass
    runtime_state.tool_info_cache[cacheKey] = result
    return result

def extractTags(name):
    return re.findall(r'【([^】]*)】', name)

def getToolOrder(op):
    if not op.tool:
        return (99, 99)
    toolType = ''
    try:
        j = json.loads(op.tool.toJson())
        toolType = j.get('type', '')
    except:
        pass
    try:
        dia = op.tool.parameters.itemByName('tool_diameter').value.value
    except:
        dia = 0
    opName = str(op.name or '')
    opUpper = opName.upper()

    # 精準對應模板命名（依使用者提供的實際名稱規則）
    is_face_rough_top = ('面銑刀' in opName and '粗' in opName and '頂面' in opName)
    is_face_finish_top = ('面銑刀' in opName and '精' in opName and '頂面' in opName)
    is_d10_endmill = ('端銑刀' in opName and re.search(r'D\s*10(?:\.0+)?', opUpper) is not None)
    is_d10_rough_outer = (is_d10_endmill and '粗' in opName and '外輪廓' in opName)
    is_d10_finish_outer = (is_d10_endmill and '精' in opName and '外輪廓' in opName)

    # 1) 【面銑刀】【粗】【頂面】
    if is_face_rough_top:
        return (1, dia)
    # 2) D10【端銑刀】【粗】【外輪廓】
    if is_d10_rough_outer:
        return (2, dia)
    # 3) center drill
    if toolType == 'center drill':
        return (3, dia)
    # 4) drill
    if toolType == 'drill':
        return (4, dia)
    # 9) 【面銑刀】【精】【頂面】（名稱標籤優先於一般刀具分類）
    if is_face_finish_top:
        return (9, dia)
    # 10) D10【端銑刀】【精】【外輪廓】（名稱標籤優先於一般刀具分類）
    if is_d10_finish_outer:
        return (10, dia)
    # 5) 一般 flat end mill（排除 D10 粗/精外輪廓固定位）
    if toolType == 'flat end mill' and not (is_d10_rough_outer or is_d10_finish_outer):
        return (5, dia)
    # 6) 其他
    if toolType not in ['chamfer mill', 'reamer']:
        return (6, dia)
    # 7) chamfer mill
    if toolType == 'chamfer mill':
        return (7, dia)
    # 8) reamer
    if toolType == 'reamer':
        return (8, dia)
    # 11) 其他最後
    return (11, dia)

def getOpToolType(op):
    try:
        j = json.loads(op.tool.toJson())
        return j.get('type', '')
    except:
        return ''




def _is_cam_drill_operation_fast(op):
    """
    判斷是否為鑽孔工序。優先用 DrillOperation.cast，避免 getOpToolType 的 tool.toJson()
    （在大量模板工序上極慢）；cast 失敗時才退回 toJson。
    """
    if not op:
        return False
    try:
        _DrillOp = getattr(adsk.cam, 'DrillOperation', None)
        if _DrillOp is not None and _DrillOp.cast(op):
            return True
    except Exception:
        pass
    return getOpToolType(op) == 'drill'


def _get_drill_tool_library_cache():
    cache = getattr(runtime_state, 'drill_tool_library_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(runtime_state, 'drill_tool_library_cache', cache)
    return cache


def _clear_drill_tool_library_cache():
    _get_drill_tool_library_cache().clear()


def _fresh_drill_tool_from_pick(picked):
    """
    從候選 dict 即時向刀庫取 Tool，避免快取或跨輪次持有 Tool 導致 Invalid transient tool。
    picked 須含 tool_lib_url（URL）、tool_index（int）。
    """
    if not picked:
        return None
    try:
        idx = picked.get('tool_index')
        lib_url = picked.get('tool_lib_url')
        if lib_url is None or idx is None:
            return None
        mgr = adsk.cam.CAMManager.get()
        libs = mgr.libraryManager.toolLibraries
        lib = libs.toolLibraryAtURL(lib_url)
        if not lib:
            return None
        return lib.item(int(idx))
    except Exception:
        return None


def _build_drill_tool_candidates_from_library():
    """
    掃描本機 ToolLibraries，收集 SG/HSS 鑽頭候選。
    回傳 list[dict]：{dia_mm, source, score, tool_lib_url, tool_index}
    （不長期保存 Tool 參考；指派前請用 _fresh_drill_tool_from_pick。）
    """
    out = []
    try:
        mgr = adsk.cam.CAMManager.get()
        libs = mgr.libraryManager.toolLibraries
        root = libs.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
        folders = libs.childFolderURLs(root) or []
    except Exception:
        return out

    def _walk_folder(folder_url, depth=0, max_depth=4):
        if depth > max_depth:
            return
        try:
            asset_urls = libs.childAssetURLs(folder_url) or []
        except Exception:
            asset_urls = []
        for aurl in asset_urls:
            try:
                lib = libs.toolLibraryAtURL(aurl)
            except Exception:
                lib = None
            if not lib:
                continue
            src = ''
            try:
                src = str(aurl.toString() or '')
            except Exception:
                src = ''
            src_l = src.lower()
            # 只收 SG/HSS 鑽頭庫
            if ('sg' not in src_l) and ('hss' not in src_l) and ('鑽頭' not in src):
                continue
            for i in range(getattr(lib, 'count', 0)):
                try:
                    t = lib.item(i)
                    if not t:
                        continue
                    t_json = json.loads(t.toJson())
                    t_type = str(t_json.get('type', '') or '').lower()
                    if t_type != 'drill':
                        continue
                    dia_cm = t.parameters.itemByName('tool_diameter').value.value
                    dia_mm = round(float(dia_cm) * 10.0, 3)
                except Exception:
                    continue
                # score: SG 優先，HSS 次之
                score = 0
                src_u = src.upper()
                if 'SG' in src_u:
                    score = 200
                elif 'HSS' in src_u:
                    score = 100
                out.append({
                    'dia_mm': dia_mm,
                    'source': src,
                    'score': score,
                    'tool_lib_url': aurl,
                    'tool_index': i,
                })

        try:
            sub_folders = libs.childFolderURLs(folder_url) or []
        except Exception:
            sub_folders = []
        for sf in sub_folders:
            _walk_folder(sf, depth + 1, max_depth)

    for f in folders:
        _walk_folder(f, 0, 4)
    return out


def _pick_preferred_drill_tool_for_dia(target_dia_mm):
    """
    依 DRILL_LIBRARY_PRIORITY 從刀具庫挑同直徑鑽頭。
    目前策略：SG 優先，找不到才 HSS；允許 0.05mm 容差。
    """
    try:
        d = round(float(target_dia_mm), 3)
    except Exception:
        return None
    key = f"{d:.3f}"
    cache = _get_drill_tool_library_cache()
    if key in cache:
        return cache[key]

    candidates = _build_drill_tool_candidates_from_library()
    if not candidates:
        cache[key] = None
        return None

    usable = [c for c in candidates if abs(float(c.get('dia_mm', -999)) - d) <= 0.05]
    if not usable:
        cache[key] = None
        return None
    usable.sort(key=lambda x: (-int(x.get('score', 0)), str(x.get('source', ''))))
    picked = usable[0]
    cache[key] = picked
    return picked




def getTemplateParams(tmpl_url):
    tmpl_lib = runtime_state.tmpl_lib
    cam_setup = runtime_state.cam_setup
    if not tmpl_lib or not cam_setup:
        return {}
    cacheKey = _cam_url_identity(tmpl_url)
    if cacheKey in runtime_state.template_params_cache:
        return runtime_state.template_params_cache[cacheKey]
    result = {}
    pitch_expr_from_bore_cycle = None
    pitch_expr_from_mill = None
    pitch_expr_any = None
    pitch_mm_from_bore_cycle = None
    pitch_mm_from_mill = None
    pitch_mm_any = None
    try:
        tmpl    = tmpl_lib.templateAtURL(tmpl_url)
        tmplOps = cam_setup.createFromCAMTemplate(tmpl)
        if not tmplOps:
            runtime_state.template_params_cache[cacheKey] = result
            return result
        for op in tmplOps:
            params = op.parameters
            op_tool_type = getOpToolType(op)
            cycle_type_expr = ''
            try:
                p_cycle = params.itemByName('cycleType') if params else None
                if p_cycle:
                    cycle_type_expr = str(getattr(p_cycle, 'expression', '') or '').lower()
            except:
                cycle_type_expr = ''
            for pname in ['bottomHeight_offset', 'breakThroughDepth', 'bottomHeight_mode', 'pitch']:
                p = params.itemByName(pname)
                if p:
                    try:
                        expr = p.expression
                        if pname == 'pitch':
                            # Prefer milling pitch for UI/default display.
                            v_mm = None
                            try:
                                # API numeric value is in cm; convert to mm.
                                v_mm = float(p.value.value) * 10.0
                            except:
                                v_mm = None
                            is_bore = ('bore-milling' in cycle_type_expr)
                            if not is_bore:
                                try:
                                    is_bore = ('bore' in str(getattr(op, 'strategy', '') or '').lower())
                                except:
                                    is_bore = False
                            if is_bore:
                                if pitch_expr_from_bore_cycle is None:
                                    pitch_expr_from_bore_cycle = expr
                                if (v_mm is not None) and (pitch_mm_from_bore_cycle is None):
                                    pitch_mm_from_bore_cycle = v_mm
                            if op_tool_type == 'flat end mill':
                                if pitch_expr_from_mill is None:
                                    pitch_expr_from_mill = expr
                                if (v_mm is not None) and (pitch_mm_from_mill is None):
                                    pitch_mm_from_mill = v_mm
                            if pitch_expr_any is None:
                                pitch_expr_any = expr
                            if (v_mm is not None) and (pitch_mm_any is None):
                                pitch_mm_any = v_mm
                        else:
                            result[pname] = expr
                    except:
                        pass
            op.deleteMe()
        if pitch_expr_from_bore_cycle is not None:
            result['pitch'] = pitch_expr_from_bore_cycle
        elif pitch_expr_from_mill is not None:
            result['pitch'] = pitch_expr_from_mill
        elif pitch_expr_any is not None:
            result['pitch'] = pitch_expr_any
        if pitch_mm_from_bore_cycle is not None:
            result['pitchMM'] = pitch_mm_from_bore_cycle
        elif pitch_mm_from_mill is not None:
            result['pitchMM'] = pitch_mm_from_mill
        elif pitch_mm_any is not None:
            result['pitchMM'] = pitch_mm_any
    except:
        pass
    runtime_state.template_params_cache[cacheKey] = result
    return result

def buildSingleFolderMap(material, folderBaseName):
    tmpl_lib = template_service.ensure_tmpl_lib()
    if not tmpl_lib:
        return []
    resultMap = []
    localURL = tmpl_lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    matURL = localURL.join(material)
    tag = '【' + material + '】'
    folderName = folderBaseName + ' ' + tag
    try:
        topFolders = tmpl_lib.childFolderURLs(matURL)
    except:
        topFolders = []
    for f in topFolders:
        if f.leafName == folderName:
            try:
                assets = tmpl_lib.childAssetURLs(f)
            except:
                assets = []
            for a in assets:
                leaf = a.leafName
                displayName = _mask_fullwidth_bracket_segments(leaf.replace('.f3dhsm-template', '').strip())
                resultMap.append({'url': a, 'name': displayName})
            break
    return resultMap

def _strip_templates_root_prefix(paths_dict):
    """
    防禦性剝離：將 template_paths 中可能殘留的外部絕對路徑前綴（如 E:/Fusion/templates）
    轉換為相對路徑格式（如 {material}/孔加工模塊...），確保 collect_assets_from_folder_path
    的前綴匹配能正確運作。
    """
    import os, re
    from smart_ai_cam_templates import template_fs_cache
    
    root = template_fs_cache.templates_root()
    root_norm = os.path.normpath(root).replace("\\", "/").rstrip("/")
    default_appdata = os.path.normpath(
        os.path.join(os.environ.get("APPDATA", ""), "Autodesk", "CAM360", "templates")
    ).replace("\\", "/").rstrip("/")
    
    cleaned = {}
    for k, v in paths_dict.items():
        if not v:
            cleaned[k] = v
            continue
        val = str(v).strip().replace("\\", "/")
        val_norm_lower = os.path.normpath(val).replace("\\", "/").lower()
        
        # 若路徑以外部根目錄開頭，剝離之
        if root_norm.lower() != default_appdata.lower():
            if val_norm_lower.startswith(root_norm.lower()):
                val = os.path.normpath(val).replace("\\", "/")[len(root_norm):].strip("/")
        
        # 若路徑仍以預設本地根目錄開頭，也剝離之
        if val_norm_lower.startswith(default_appdata.lower()):
            val = os.path.normpath(val).replace("\\", "/")[len(default_appdata):].strip("/")
        elif "cam360/templates/" in val_norm_lower:
            idx = val_norm_lower.find("cam360/templates/")
            val = os.path.normpath(val).replace("\\", "/")[idx + len("cam360/templates/"):].strip("/")
        
        # 若路徑仍帶有碟符（e:/...），嘗試用 material tag 定位剝離點
        if ":" in val or os.path.isabs(val):
            val_lower = val.lower()
            for tag in ["/al6061", "/s50c", "/{material}"]:
                idx = val_lower.find(tag)
                if idx != -1:
                    val = val[idx:].strip("/")
                    break
        
        # 將寫死的材質名替換回 {material} 佔位符
        for mat_tag in ["AL6061", "S50C"]:
            if mat_tag in val:
                val = re.sub(re.escape(mat_tag), "{material}", val, flags=re.IGNORECASE)
        
        cleaned[k] = val
    return cleaned


def buildTemplateMaps(material):
    # Backward-compatible：舊版 template_service 可能僅 4 參數或僅回傳 (drill_map, chamfer_map)。
    tmpl_lib = template_service.ensure_tmpl_lib()
    if not tmpl_lib:
        _template_map_load_log('[template-map] tmpl_lib 不可用（CAM 模板庫未就緒）')
        return {}, {}
    
    paths = getattr(runtime_state, 'template_paths', None)
    if not paths:
        paths = dict(TEMPLATE_FOLDER_PATHS)
        try:
            from smart_ai_cam_ui import palette_data_provider
            defs = palette_data_provider._load_ui_defaults()
            for k in TEMPLATE_FOLDER_PATHS.keys():
                if k in defs and defs[k]:
                    paths[k] = str(defs[k])
        except:
            pass
    
    # 防禦性剝離：確保傳給 template_service 的路徑都是相對格式
    try:
        paths = _strip_templates_root_prefix(dict(paths))
    except Exception:
        pass

    try:
        res = template_service.build_template_maps(
            tmpl_lib,
            material,
            TAP_DIA_MAP,
            TAP_SHORT_MAP,
            paths,
        )
    except TypeError:
        res = template_service.build_template_maps(
            tmpl_lib,
            material,
            TAP_DIA_MAP,
            TAP_SHORT_MAP,
        )
    if isinstance(res, tuple) and len(res) >= 2:
        return res[0], res[1]
    return res, {}





def _bind_cad2d_chain(
    cad,
    edges_list,
    reverse_edge_order=False,
    per_chain_compensation_slug=None,
    winding_align_xor=False,
):
    """以邊鏈綁定 CadContours2d（pockets／contours 共用 ChainSelection）。"""
    el = [e for e in (edges_list or []) if e and getattr(e, 'isValid', True)]
    if not cad or len(el) < 2:
        return False
    riv = bool(reverse_edge_order) ^ bool(winding_align_xor)
    if riv:
        el = list(reversed(el))
    sels = cad.getCurveSelections()
    if not sels:
        return False
    try:
        sels.clear()
    except Exception:
        pass
    try:
        csel = sels.createNewChainSelection()
        csel.inputGeometry = list(el)
        if per_chain_compensation_slug:
            _try_set_chain_selection_compensation_slug(csel, per_chain_compensation_slug)
    except Exception as ex:
        try:
            _send_diag_log(
                '[face-bind][WARN] chain inputGeometry: %s nin=%s nvalid=%s'
                % (ex, len(edges_list or []), len(el))
            )
        except Exception:
            pass
        return False
    try:
        cad.applyCurveSelections(sels)
    except Exception as ex2:
        try:
            _send_diag_log('[face-bind][WARN] chain applyCurveSelections: %s' % ex2)
        except Exception:
            pass
        return False
    return True


def _try_set_chain_selection_compensation_slug(csel, slug):
    """對單一 ChainSelection 嘗試設補償（多輪廓時須每條鏈各設，否則僅第一條繼承 op 級 compensation）。"""
    if not csel or not slug:
        return False
    s = str(slug).strip().strip("'\"")
    if not s:
        return False
    expr = "'%s'" % s.replace("'", '')
    for pn in (
        'compensation',
        'toolCompensation',
        'cutterCompensation',
        'cutterSideCompensation',
        'cutterSide',
    ):
        if not hasattr(csel, pn):
            continue
        for val in (s, expr):
            try:
                setattr(csel, pn, val)
                return True
            except Exception:
                pass
    try:
        en = getattr(adsk.cam, 'CutterSideCompensations', None)
        if en and hasattr(csel, 'compensation'):
            cand_names = {
                'right': (
                    'RightSideCompensation',
                    'CamRightSideCompensation',
                    'RightCompensation',
                ),
                'center': (
                    'CenterCompensation',
                    'CamCenterCompensation',
                    'OnCenterCompensation',
                ),
                'centre': (
                    'CenterCompensation',
                    'CamCenterCompensation',
                    'OnCenterCompensation',
                ),
                'left': (
                    'LeftSideCompensation',
                    'CamLeftSideCompensation',
                    'LeftCompensation',
                ),
            }
            for akey in cand_names.get(s.lower(), ()):
                ev = getattr(en, akey, None)
                if ev is None:
                    continue
                try:
                    csel.compensation = ev
                    return True
                except Exception:
                    try:
                        setattr(csel, 'compensation', ev)
                        return True
                    except Exception:
                        pass
    except Exception:
        pass
    return False


def _fast_set_all_cam_params_name_substr(params, name_substr, expr):
    """將名稱含 name_substr（不分大小寫）的工序參數一律設為 expr。"""
    n = 0
    if not params or not name_substr:
        return 0
    try:
        cnt = int(params.count)
    except Exception:
        return 0
    sub = name_substr.lower()
    for i in range(cnt):
        try:
            p = params.item(i)
            nm = str(getattr(p, 'name', '') or '').lower()
        except Exception:
            continue
        if sub not in nm:
            continue
        try:
            if str(getattr(p, 'expression', '') or '') == expr:
                continue
        except Exception:
            pass
        try:
            p.expression = expr
            n += 1
        except Exception:
            pass
    return n


def _patch_cad2d_all_chain_selection_compensations(cad_2d, comp_expr):
    """
    綁定後再對 pockets 之 CurveSelections 內每條 ChainSelection 嘗試設補償並 applyCurveSelections。
    comp_expr 須為 expression 形式，例如 \"'right'\"。
    """
    if not cad_2d or not comp_expr:
        return 0
    try:
        sels = cad_2d.getCurveSelections()
    except Exception:
        return 0
    if not sels:
        return 0
    slug = str(comp_expr).strip().strip("'\"")
    n = 0
    for i in range(sels.count):
        try:
            it = sels.item(i)
        except Exception:
            continue
        ch = adsk.cam.ChainSelection.cast(it)
        if not ch:
            continue
        if _try_set_chain_selection_compensation_slug(ch, slug):
            n += 1
    if n > 0:
        try:
            cad_2d.applyCurveSelections(sels)
        except Exception:
            return 0
    return n


def _patch_cad2d_chain_selection_compensations_per_chain(cad_2d, comp_slugs):
    """
    對 pockets 之 CurveSelections 內各 ChainSelection 依序寫入不同 compensation（auto 模式用）。
    comp_slugs: ['left','right',...] 與鏈順序一致。
    """
    if not cad_2d or not comp_slugs:
        return 0
    try:
        sels = cad_2d.getCurveSelections()
    except Exception:
        return 0
    if not sels:
        return 0
    n = 0
    for i in range(sels.count):
        try:
            it = sels.item(i)
        except Exception:
            continue
        ch = adsk.cam.ChainSelection.cast(it)
        if not ch:
            continue
        slug = comp_slugs[i] if i < len(comp_slugs) else comp_slugs[-1]
        if _try_set_chain_selection_compensation_slug(ch, slug):
            n += 1
    if n > 0:
        try:
            cad_2d.applyCurveSelections(sels)
        except Exception:
            return 0
    return n


def _slot_flip_all_chain_is_reverted_in_cad2d(cad_2d):
    """CadContours2d 綁定後整批翻轉各 ChainSelection.isReverted；語意為 2D 內輪廓（腰形槽等為首測路徑）。"""
    if not cad_2d:
        return 0
    try:
        sels = cad_2d.getCurveSelections()
    except Exception:
        return 0
    if not sels:
        return 0
    try:
        n = int(sels.count)
    except Exception:
        return 0
    nfl = 0
    for i in range(n):
        try:
            it = sels.item(i)
            ch = adsk.cam.ChainSelection.cast(it)
            if not ch:
                continue
            ch.isReverted = not bool(ch.isReverted)
            nfl += 1
        except Exception:
            continue
    if nfl <= 0:
        return 0
    try:
        cad_2d.applyCurveSelections(sels)
    except Exception:
        return 0
    return nfl


def _bind_cad2d_chain_profiles(
    cad,
    edge_lists,
    reverse_edge_order=False,
    per_chain_compensation_slug=None,
    per_chain_reverse_xor=None,
):
    """多條封閉邊鏈寫入同一 CadContours2d（同一 pocket2d／chamfer2d 工序之多輪廓）。"""
    if not cad or not edge_lists:
        return False
    sels = cad.getCurveSelections()
    if not sels:
        return False
    added = 0
    try:
        sels.clear()
    except Exception:
        pass
    for idx, edges in enumerate(edge_lists):
        el = [e for e in (edges or []) if e and getattr(e, 'isValid', True)]
        if len(el) < 2:
            continue
        _base_rev = bool(reverse_edge_order)
        _xor_rev = False
        if per_chain_reverse_xor is not None and idx < len(per_chain_reverse_xor):
            _xor_rev = bool(per_chain_reverse_xor[idx])
        riv = _base_rev ^ _xor_rev
        if riv:
            el = list(reversed(el))
        try:
            csel = sels.createNewChainSelection()
            csel.inputGeometry = el
            _slug_one = None
            if per_chain_compensation_slug:
                if isinstance(per_chain_compensation_slug, (list, tuple)):
                    if idx < len(per_chain_compensation_slug):
                        _slug_one = per_chain_compensation_slug[idx]
                else:
                    _slug_one = per_chain_compensation_slug
                if _slug_one:
                    _try_set_chain_selection_compensation_slug(csel, _slug_one)
            try:
                _send_diag_log(
                    '[slot-bind][chain %d] base_rev=%s xor_rev=%s final_rev=%s comp=%s edges=%d'
                    % (
                        idx + 1,
                        str(_base_rev).lower(),
                        str(_xor_rev).lower(),
                        str(riv).lower(),
                        (str(_slug_one) if _slug_one else '-'),
                        len(el),
                    )
                )
            except Exception:
                pass
            added += 1
        except Exception as ex:
            try:
                _send_diag_log(
                    '[face-bind][WARN] multi-chain selection: %s nedges=%s' % (ex, len(el))
                )
            except Exception:
                pass
            continue
    if added == 0:
        return False
    try:
        cad.applyCurveSelections(sels)
    except Exception as ex:
        try:
            _send_diag_log(f'[face-bind][WARN] multi-chain apply: {ex}')
        except Exception:
            pass
        return False
    return True


def _createOpFromTemplate(
    setup,
    tmpl,
    faces,
    isThrough=True,
    holeDepthMM=None,
    useSameTopZ=False,
    template_url='',
    clone_cache=None,
    clone_stats=None,
    bind_all_faces=False,
    select_same_diameter=True,
    slot_profile_edges=None,
    perf_stats=None,
    slot_chain_profiles=None,
    slot_chain_token_profiles=None,
    slot_chains_only=False,
    slot_chain_reverse_order=False,
    slot_chain_opening_faces=None,
    slot_chain_center_ref_mm=None,
):
    """
    從模板創建 CAM 操作並設置基礎參數。
    鑽孔／鉸孔等之 holeFaces 綁定語意與 _append_seed_faces_to_existing_drill_op 一致，見 docs/行為準則.md §4.1；
    長條孔等 **pocket2d**（參數 **pockets**）、**chamfer2d／contour2d**（參數 **contours**）則走
    **CadContours2dParameterValue + applyCurveSelections**（與鑽孔 holeFaces 鏈分開）。
    若傳入 **slot_profile_edges**（腰形槽內環邊，辨識器 **loop_edges**），優先以 **ChainSelection**
    綁 2D 輪廓線；失敗或無邊時再以面綁定（PocketSelection／FaceContourSelection）。
    **slot_chain_profiles**：非空時為多條腰形槽邊鏈（每槽一 list），寫入**同一** pockets／contours 之多輪廓；
    **slot_chain_token_profiles**：與上列平行之 entityToken 串列，綁定前若 live edge 無效則還原；
    **slot_chains_only** 為真時不再以面或 holeFaces 作 2D 後備（長條孔 execute 專用）。
    **slot_chain_reverse_order** 為真時各條邊鏈寫入 ChainSelection 前反轉邊序，使 pocket2d／輪廓刀路在封閉區內側（見 **SLOT_CHAIN_REVERSE_FOR_INTERIOR**）。
    **slot_chain_opening_faces**：與 slot_chain_profiles 等長時，可傳各槽篩選後之開口平面，供多槽繞向依面分桶（見 SLOT_ALIGN_WINDING_USE_OPENING_FACE）。
    **slot_chain_center_ref_mm**：與鏈等長之 (cx_mm, cy_mm, face_z_mm) 選填第三元；供自動補償以辨識槽心校準內外（見 SLOT_POCKET_USE_SCAN_CENTER_FOR_COMP）。
    """
    if not setup or not tmpl:
        return None
    _faces_clean = [f for f in (faces or []) if f]
    _edges_clean = [e for e in (slot_profile_edges or []) if e]
    _slot_profiles_nonempty = bool(slot_chain_profiles) and any(
        (lst and len([e for e in lst if e]) >= 2) for lst in slot_chain_profiles
    )
    _slot_tokens_nonempty = bool(slot_chain_token_profiles) and any(
        (toks and len(toks) >= 2) for toks in (slot_chain_token_profiles or [])
    )
    if (
        not _faces_clean
        and len(_edges_clean) < 2
        and not _slot_profiles_nonempty
        and not _slot_tokens_nonempty
    ):
        return None

    tmplOps = None
    cache_key = _template_cache_key(template_url, '')
    if clone_cache is not None and cache_key and cache_key in clone_cache:
        _copy_t0 = time.perf_counter()
        proto_ops = []
        for p in (clone_cache.get(cache_key, []) or []):
            try:
                if p and getattr(p, 'isValid', True):
                    proto_ops.append(p)
                elif isinstance(clone_stats, dict):
                    clone_stats['invalid_proto'] = int(clone_stats.get('invalid_proto', 0)) + 1
            except:
                if isinstance(clone_stats, dict):
                    clone_stats['invalid_proto'] = int(clone_stats.get('invalid_proto', 0)) + 1
                pass
        if not proto_ops:
            try:
                clone_cache.pop(cache_key, None)
            except:
                pass
        cloned_ops = []
        for proto in proto_ops:
            try:
                new_op = proto.copyAfter(proto)
                if new_op:
                    cloned_ops.append(new_op)
            except:
                if isinstance(clone_stats, dict):
                    clone_stats['copy_errors'] = int(clone_stats.get('copy_errors', 0)) + 1
                cloned_ops = []
                break
        if cloned_ops and len(cloned_ops) == len(proto_ops):
            tmplOps = cloned_ops
            if isinstance(clone_stats, dict):
                clone_stats['copy_hits'] = int(clone_stats.get('copy_hits', 0)) + 1
        elif isinstance(clone_stats, dict):
            clone_stats['copy_miss'] = int(clone_stats.get('copy_miss', 0)) + 1
        if isinstance(perf_stats, dict):
            perf_stats['copy_after_s'] = float(perf_stats.get('copy_after_s', 0.0)) + (time.perf_counter() - _copy_t0)
    elif isinstance(clone_stats, dict):
        clone_stats['cache_miss'] = int(clone_stats.get('cache_miss', 0)) + 1

    if not tmplOps:
        try:
            _create_t0 = time.perf_counter()
            tmplOps = setup.createFromCAMTemplate(tmpl)
            if isinstance(clone_stats, dict):
                clone_stats['create_calls'] = int(clone_stats.get('create_calls', 0)) + 1
            if isinstance(perf_stats, dict):
                perf_stats['create_from_template_s'] = float(perf_stats.get('create_from_template_s', 0.0)) + (time.perf_counter() - _create_t0)
        except:
            return None
        
    if not tmplOps:
        return None
        
    results = []
    for op in tmplOps:
        try:
            _bind_t0 = time.perf_counter()
            params = op.parameters
            opType = ''
            try:
                _DrillOp = getattr(adsk.cam, 'DrillOperation', None)
                if _DrillOp is not None and _DrillOp.cast(op):
                    opType = 'drill'
            except Exception:
                pass
            if not opType:
                opType = getOpToolType(op)
            # Fusion 常將中心鑽工序 cast 成 DrillOperation；以實際刀具型別為準，避免誤走主鑽邏輯。
            try:
                if getOpToolType(op) == 'center drill':
                    opType = 'center drill'
            except Exception:
                pass
            param_cache = {}

            # 鑽孔工序：僅在 ENABLE_DRILL_LIBRARY_TOOL_MATCH 為真時，才從本機庫換同徑 SG/HSS。
            if ENABLE_DRILL_LIBRARY_TOOL_MATCH and opType == 'drill':
                try:
                    dia_cm = op.tool.parameters.itemByName('tool_diameter').value.value
                    dia_mm = round(float(dia_cm) * 10.0, 3)
                    picked = _pick_preferred_drill_tool_for_dia(dia_mm)
                    fresh_tool = _fresh_drill_tool_from_pick(picked) if picked else None
                    if picked and fresh_tool:
                        try:
                            op.tool = fresh_tool
                            _send_diag_log(
                                '[tool-match] drill D'
                                + str(dia_mm)
                                + ' -> '
                                + str((picked.get('source') or '').split('/')[-1])
                            )
                        except Exception:
                            # 某些版本/工序不允許直接指派 tool，保留模板原刀具並給診斷提示。
                            _send_diag_log(
                                '[tool-match] drill D'
                                + str(dia_mm)
                                + ' 找到候選但無法直接套用（保留模板刀具）'
                            )
                    else:
                        _send_diag_log('[tool-match] drill D' + str(dia_mm) + ' 未找到 SG/HSS 同徑刀具')
                except Exception:
                    pass

            def _get_param(name):
                if name in param_cache:
                    return param_cache[name]
                try:
                    p = params.itemByName(name) if params else None
                except:
                    p = None
                param_cache[name] = p
                return p

            def _fast_set(name, expr):
                p = _get_param(name)
                if not p:
                    return False
                try:
                    if str(getattr(p, 'expression', '')) == expr:
                        return True
                except:
                    pass
                try:
                    p.expression = expr
                    return True
                except:
                    return False
            
            # CAM 孔面綁定：與 _append_seed_faces_to_existing_drill_op 同一參數鏈（docs/行為準則.md §4.1、§4.1 末條、整數 V1.0 核心）。
            # 設置孔位選擇模式
            _fast_set('selectSameDiameter', 'true' if select_same_diameter else 'false')
            _fast_set('selectSameDepth', 'false')
            if useSameTopZ and opType == 'chamfer mill':
                _fast_set('selectSameTopZ', 'true')
            else:
                _fast_set('selectSameTopZ', 'false')
            _fast_set('checkForOcclusions', 'true')

            try:
                strat = str(getattr(op, 'strategy', '') or '').lower()
            except Exception:
                strat = ''

            target_faces = []
            if _faces_clean:
                _tf = list(_faces_clean) if bind_all_faces else [_faces_clean[0]]
                target_faces = [f for f in _tf if f]

            bound_2d = False
            chain_edges = _edges_clean if len(_edges_clean) >= 2 else []
            chains_to_bind = []
            if slot_chain_profiles:
                chains_to_bind = _coalesce_slot_chains_edge_lists(
                    slot_chain_profiles,
                    slot_chain_token_profiles,
                )
            elif chain_edges:
                chains_to_bind = [chain_edges]
            try:
                _send_diag_log(
                    '[slot-bind] op=%s opType=%s strat=%s chains=%d slot_chains_only=%s'
                    % (
                        str(getattr(op, 'name', '') or ''),
                        str(opType or ''),
                        str(strat or ''),
                        len(chains_to_bind),
                        str(bool(slot_chains_only)).lower(),
                    )
                )
            except Exception:
                pass
            _slot_walign_xor = None
            if (
                SLOT_ALIGN_MULTI_CHAIN_WINDING
                and slot_chains_only
                and slot_chain_profiles
                and SLOT_POCKET_TOOLPATH_INSIDE_SLOT
                and len(chains_to_bind) > 1
            ):
                try:
                    _ofaces = slot_chain_opening_faces
                    _f_ok = sum(
                        1
                        for f in (_ofaces or [])
                        if f and getattr(f, 'isValid', True)
                    )
                    if (
                        SLOT_ALIGN_WINDING_USE_OPENING_FACE
                        and _ofaces
                        and len(_ofaces) == len(chains_to_bind)
                        and _f_ok >= 2
                    ):
                        _slot_walign_xor = _slot_pocket_align_chain_winding_with_opening_faces(
                            chains_to_bind, setup, _ofaces
                        )
                    else:
                        _slot_walign_xor = _slot_pocket_align_chain_winding_flags(chains_to_bind, setup)
                except Exception:
                    _slot_walign_xor = None
                try:
                    if _slot_walign_xor and len(_slot_walign_xor) == len(chains_to_bind):
                        _nw = sum(1 for x in _slot_walign_xor if x)
                        _mode = (
                            '開口面分桶+UV'
                            if (
                                SLOT_ALIGN_WINDING_USE_OPENING_FACE
                                and slot_chain_opening_faces
                                and len(slot_chain_opening_faces) == len(chains_to_bind)
                                and sum(
                                    1
                                    for f in slot_chain_opening_faces
                                    if f and getattr(f, 'isValid', True)
                                )
                                >= 2
                            )
                            else 'Setup XY'
                        )
                        _send_diag_log(
                            '[slot-bind] 多槽邊鏈繞向（%s）：已檢查 %d 條，%d 條額外反轉邊序'
                            % (_mode, len(chains_to_bind), _nw)
                        )
                    else:
                        _send_diag_log(
                            '[slot-bind] 多槽邊鏈繞向：未套用對齊（無法計算各鏈有號面積或參考過小）'
                        )
                except Exception:
                    pass
            allow_face_fb = not slot_chains_only
            _slot_chain_rev = bool(slot_chain_reverse_order)
            pocket2d_chain_bound = False
            _slot_p_comp_slug = None
            if slot_chains_only and slot_chain_profiles and SLOT_POCKET_TOOLPATH_INSIDE_SLOT:
                if SLOT_POCKET_COMPENSATION_AUTO:
                    try:
                        _ofs_pa = slot_chain_opening_faces
                        _cref = slot_chain_center_ref_mm or []
                        if chains_to_bind:
                            _sl_auto = []
                            for _ci, _chn in enumerate(chains_to_bind):
                                _ofp = (
                                    _ofs_pa[_ci]
                                    if (_ofs_pa and _ci < len(_ofs_pa))
                                    else None
                                )
                                _ctr = _cref[_ci] if _ci < len(_cref) else None
                                _rxy = None
                                _rz = None
                                if _ctr and len(_ctr) >= 2:
                                    try:
                                        _rxy = (float(_ctr[0]), float(_ctr[1]))
                                    except (TypeError, ValueError):
                                        _rxy = None
                                    if len(_ctr) >= 3:
                                        try:
                                            _rz = float(_ctr[2])
                                        except (TypeError, ValueError):
                                            _rz = None
                                _sl_auto.append(
                                    _resolve_slot_pocket_compensation_slug(
                                        _chn,
                                        setup,
                                        _ofp,
                                        True,
                                        ref_center_mm_xy=_rxy,
                                        ref_z_mm=_rz,
                                    )
                                )
                            if _sl_auto:
                                _slot_p_comp_slug = (
                                    _sl_auto if len(_sl_auto) > 1 else _sl_auto[0]
                                )
                                try:
                                    _ncr = len(_cref)
                                    _nrxy = sum(
                                        1
                                        for _ci in range(len(_sl_auto))
                                        if _ci < _ncr
                                        and _cref[_ci]
                                        and len(_cref[_ci]) >= 2
                                    )
                                    _send_diag_log(
                                        '[slot-bind] pocket auto compensation: slugs=%s center_ref元數=%d 含(cx,cy)=%d'
                                        % (_sl_auto, _ncr, _nrxy)
                                    )
                                except Exception:
                                    pass
                    except Exception:
                        _slot_p_comp_slug = None
                if _slot_p_comp_slug is None and SLOT_POCKET_COMPENSATION_OVERRIDE:
                    _slot_p_comp_slug = str(SLOT_POCKET_COMPENSATION_OVERRIDE).strip().strip(
                        "'\""
                    )

            nch_m = len(chains_to_bind)
            wa_m = (
                list(_slot_walign_xor)
                if (_slot_walign_xor and len(_slot_walign_xor) == nch_m)
                else [False] * nch_m
            )
            # 分桶退回：當 opening-face 分桶數>=2，但 align 結果全 False 時，
            # 以「首桶為基準，其它桶整桶 XOR」建立穩定分桶反轉，避免 base_rev 使全部同向。
            if (
                nch_m > 1
                and (not any(wa_m))
                and slot_chain_opening_faces
                and len(slot_chain_opening_faces) == nch_m
            ):
                try:
                    _keys = []
                    _first_idx = {}
                    for _i in range(nch_m):
                        _k = _slot_face_bucket_key(slot_chain_opening_faces[_i], _i)
                        _keys.append(_k)
                        if _k not in _first_idx:
                            _first_idx[_k] = _i
                    _uniq = list(_first_idx.keys())
                    if len(_uniq) >= 2:
                        _k0 = _uniq[0]
                        _wb = [False] * nch_m
                        for _i in range(nch_m):
                            _wb[_i] = (_keys[_i] != _k0)
                        if any(_wb):
                            wa_m = _wb
                            _send_diag_log(
                                '[slot-bind] rev-fallback(bucket-xor): apply=%s buckets=%d'
                                % (list(wa_m), len(_uniq))
                            )
                except Exception:
                    pass
            # 回退：若繞向對齊無結果（全 False），但有 host opening faces，則以 face.normal·Setup+Z 產生每鏈反轉旗標。
            # 目的：避免四鏈全不反轉造成朝外；此路徑只在 align 結果缺失時啟用，不覆蓋正常 XOR。
            if (
                nch_m > 0
                and (not any(wa_m))
                and slot_chain_opening_faces
                and len(slot_chain_opening_faces) == nch_m
            ):
                try:
                    _o_w, _x_w, _y_w, _z_w = setup.workCoordinateSystem.getAsCoordinateSystem()
                    _wa_fb = []
                    _ok = 0
                    for _f in slot_chain_opening_faces:
                        _rv = False
                        try:
                            if _f and getattr(_f, 'isValid', True):
                                _g = _f.geometry
                                if _g and int(_g.surfaceType) == int(adsk.core.SurfaceTypes.PlaneSurfaceType):
                                    _pl = adsk.core.Plane.cast(_g)
                                    if _pl:
                                        _dn = float(_pl.normal.dotProduct(_z_w))
                                        if abs(_dn) >= 0.01:
                                            _rv = (_dn < 0.0)
                                            _ok += 1
                        except Exception:
                            pass
                        _wa_fb.append(_rv)
                    if _ok > 0 and len(_wa_fb) == nch_m and any(_wa_fb):
                        wa_m = _wa_fb
                        _send_diag_log(
                            '[slot-bind] rev-fallback(host_face·Z): apply=%s valid=%d/%d'
                            % (list(wa_m), _ok, nch_m)
                        )
                except Exception:
                    pass
            if SLOT_POCKET_TOOLPATH_INSIDE_SLOT and SLOT_POCKET_INVERT_CHAIN_WHEN_COMP_RIGHT:
                if isinstance(_slot_p_comp_slug, list) and len(_slot_p_comp_slug) == nch_m:
                    for _ii in range(nch_m):
                        if str(_slot_p_comp_slug[_ii]).lower() == 'right':
                            wa_m[_ii] = not wa_m[_ii]
                elif _slot_p_comp_slug and str(_slot_p_comp_slug).lower() == 'right':
                    for _ii in range(nch_m):
                        wa_m[_ii] = not wa_m[_ii]
                    try:
                        _send_diag_log(
                            '[slot-bind] compensation=right：各邊鏈額外反轉（與 SLOT_CHAIN_REVERSE 疊加），避免 NoToolpath'
                        )
                    except Exception:
                        pass
            _slot_bind_rev_xor = wa_m
            try:
                _of_ok = sum(
                    1
                    for _f in (slot_chain_opening_faces or [])
                    if _f and getattr(_f, 'isValid', True)
                )
                _send_diag_log(
                    '[slot-bind] rev-plan: base_rev=%s xor=%s comp=%s chains=%d openFaces_ok=%d'
                    % (
                        str(_slot_chain_rev).lower(),
                        list(_slot_bind_rev_xor),
                        _slot_p_comp_slug,
                        nch_m,
                        _of_ok,
                    )
                )
            except Exception:
                pass

            pockets_p = _get_param('pockets')
            if pockets_p:
                try:
                    _pv = pockets_p.value
                except Exception:
                    _pv = None
                cad_p = adsk.cam.CadContours2dParameterValue.cast(_pv) if _pv else None
                if cad_p:
                    _pocket_rev = _slot_chain_rev

                    if len(chains_to_bind) > 1:
                        try:
                            if _bind_cad2d_chain_profiles(
                                cad_p,
                                chains_to_bind,
                                reverse_edge_order=_pocket_rev,
                                per_chain_compensation_slug=_slot_p_comp_slug,
                                per_chain_reverse_xor=_slot_bind_rev_xor,
                            ):
                                bound_2d = True
                                pocket2d_chain_bound = True
                        except Exception as _pce:
                            _send_diag_log(f'[face-bind][WARN] pockets multi-chain: {_pce}')
                    elif len(chains_to_bind) == 1:
                        try:
                            if _bind_cad2d_chain(
                                cad_p,
                                chains_to_bind[0],
                                reverse_edge_order=_pocket_rev,
                                per_chain_compensation_slug=_slot_p_comp_slug,
                                winding_align_xor=(
                                    bool(_slot_bind_rev_xor[0])
                                    if (_slot_bind_rev_xor and len(_slot_bind_rev_xor) >= 1)
                                    else False
                                ),
                            ):
                                bound_2d = True
                                pocket2d_chain_bound = True
                        except Exception as _pce:
                            _send_diag_log(f'[face-bind][WARN] pockets chain: {_pce}')
                    if (
                        pocket2d_chain_bound
                        and slot_chains_only
                        and slot_chain_profiles
                        and SLOT_POCKET_TOOLPATH_INSIDE_SLOT
                    ):
                        _parts = []
                        if SLOT_POCKET_COMPENSATION_AUTO and _slot_p_comp_slug:
                            if isinstance(_slot_p_comp_slug, list) and _slot_p_comp_slug:
                                _ce0 = str(_slot_p_comp_slug[0]).strip().strip("'\"")
                                _ce_expr = "'%s'" % _ce0.replace("'", '')
                                try:
                                    if _get_param('compensation') and _fast_set(
                                        'compensation', _ce_expr
                                    ):
                                        _parts.append('compensation')
                                except Exception:
                                    pass
                                try:
                                    _nx = _fast_set_all_cam_params_name_substr(
                                        params, 'compens', _ce_expr
                                    )
                                    if _nx:
                                        _parts.append('compens_named_params=%d' % _nx)
                                except Exception:
                                    pass
                                try:
                                    _nc = _patch_cad2d_chain_selection_compensations_per_chain(
                                        cad_p, _slot_p_comp_slug
                                    )
                                    if _nc:
                                        _parts.append('chainSel=%d' % _nc)
                                except Exception:
                                    pass
                                try:
                                    if _parts:
                                        _send_diag_log(
                                            '[slot-bind] pocket2d compensation（auto per-chain）→ %s [%s]'
                                            % (_slot_p_comp_slug, ','.join(_parts))
                                        )
                                    else:
                                        _send_diag_log(
                                            '[slot-bind][WARN] pocket2d auto compensation 未寫入任何欄位（%s）'
                                            % (_slot_p_comp_slug,)
                                        )
                                except Exception:
                                    pass
                            else:
                                _ce0 = str(_slot_p_comp_slug).strip().strip("'\"")
                                _ce_expr = "'%s'" % _ce0.replace("'", '')
                                try:
                                    if _get_param('compensation') and _fast_set(
                                        'compensation', _ce_expr
                                    ):
                                        _parts.append('compensation')
                                except Exception:
                                    pass
                                try:
                                    _nx = _fast_set_all_cam_params_name_substr(
                                        params, 'compens', _ce_expr
                                    )
                                    if _nx:
                                        _parts.append('compens_named_params=%d' % _nx)
                                except Exception:
                                    pass
                                try:
                                    _nc = _patch_cad2d_all_chain_selection_compensations(
                                        cad_p, _ce_expr
                                    )
                                    if _nc:
                                        _parts.append('chainSel=%d' % _nc)
                                except Exception:
                                    pass
                                try:
                                    if _parts:
                                        _send_diag_log(
                                            '[slot-bind] pocket2d compensation（auto）→ %s [%s]'
                                            % (_ce0, ','.join(_parts))
                                        )
                                    else:
                                        _send_diag_log(
                                            '[slot-bind][WARN] pocket2d auto compensation 未寫入（%s）'
                                            % (_ce0,)
                                        )
                                except Exception:
                                    pass
                        elif SLOT_POCKET_COMPENSATION_OVERRIDE:
                            _ce = str(SLOT_POCKET_COMPENSATION_OVERRIDE).strip()
                            try:
                                if _get_param('compensation') and _fast_set(
                                    'compensation', _ce
                                ):
                                    _parts.append('compensation')
                            except Exception:
                                pass
                            try:
                                _nx = _fast_set_all_cam_params_name_substr(
                                    params, 'compens', _ce
                                )
                                if _nx:
                                    _parts.append('compens_named_params=%d' % _nx)
                            except Exception:
                                pass
                            try:
                                _nc = _patch_cad2d_all_chain_selection_compensations(
                                    cad_p, _ce
                                )
                                if _nc:
                                    _parts.append('chainSel=%d' % _nc)
                            except Exception:
                                pass
                            try:
                                if _parts:
                                    _send_diag_log(
                                        '[slot-bind] pocket2d compensation → %s [%s]'
                                        % (_ce, ','.join(_parts))
                                    )
                                else:
                                    _send_diag_log(
                                        '[slot-bind][WARN] pocket2d compensation 未寫入任何欄位（%s），請於 Fusion 內檢查參數名／ChainSelection API）'
                                        % (_ce,)
                                    )
                            except Exception:
                                pass
                    if (
                        CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND
                        and pocket2d_chain_bound
                        and slot_chains_only
                    ):
                        try:
                            _nf = _slot_flip_all_chain_is_reverted_in_cad2d(cad_p)
                            if _nf:
                                _send_diag_log(
                                    '[slot-bind] post-bind flip isReverted (pockets): count=%d' % _nf
                                )
                        except Exception as _fe:
                            try:
                                _send_diag_log(
                                    '[slot-bind][WARN] post-bind flip pockets: %s' % _fe
                                )
                            except Exception:
                                pass
                    if not bound_2d and target_faces and allow_face_fb:
                        try:
                            sels_p = cad_p.getCurveSelections()
                            if sels_p:
                                try:
                                    sels_p.clear()
                                except Exception:
                                    pass
                            psel = sels_p.createNewPocketSelection()
                            try:
                                psel.isSelectingSamePlaneFaces = False
                            except Exception:
                                pass
                            psel.inputGeometry = list(target_faces)
                            cad_p.applyCurveSelections(sels_p)
                            bound_2d = True
                        except Exception as _pe:
                            _send_diag_log(f'[face-bind][WARN] pockets pocket2d: {_pe}')

            if not bound_2d:
                contours_p = _get_param('contours')
                if contours_p:
                    try:
                        _cv = contours_p.value
                    except Exception:
                        _cv = None
                    cad_c = adsk.cam.CadContours2dParameterValue.cast(_cv) if _cv else None
                    if cad_c:
                        if len(chains_to_bind) > 1:
                            try:
                                if _bind_cad2d_chain_profiles(
                                    cad_c,
                                    chains_to_bind,
                                    reverse_edge_order=_slot_chain_rev,
                                    per_chain_compensation_slug=(
                                        _slot_p_comp_slug
                                        if (slot_chains_only and _slot_p_comp_slug)
                                        else None
                                    ),
                                    per_chain_reverse_xor=_slot_bind_rev_xor,
                                ):
                                    bound_2d = True
                                    if (
                                        CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND
                                        and slot_chains_only
                                    ):
                                        try:
                                            _nfc = _slot_flip_all_chain_is_reverted_in_cad2d(cad_c)
                                            if _nfc:
                                                _send_diag_log(
                                                    '[slot-bind] post-bind flip isReverted (contours multi): count=%d'
                                                    % _nfc
                                                )
                                        except Exception as _fce:
                                            try:
                                                _send_diag_log(
                                                    '[slot-bind][WARN] post-bind flip contours multi: %s'
                                                    % _fce
                                                )
                                            except Exception:
                                                pass
                            except Exception as _cce:
                                _send_diag_log(f'[face-bind][WARN] contours multi-chain: {_cce}')
                        elif len(chains_to_bind) == 1:
                            try:
                                _cf_slug = None
                                if slot_chains_only and _slot_p_comp_slug:
                                    if isinstance(_slot_p_comp_slug, (list, tuple)) and _slot_p_comp_slug:
                                        _cf_slug = _slot_p_comp_slug[0]
                                    else:
                                        _cf_slug = _slot_p_comp_slug
                                if _bind_cad2d_chain(
                                    cad_c,
                                    chains_to_bind[0],
                                    reverse_edge_order=_slot_chain_rev,
                                    per_chain_compensation_slug=_cf_slug,
                                    winding_align_xor=(
                                        bool(_slot_bind_rev_xor[0])
                                        if (_slot_bind_rev_xor and len(_slot_bind_rev_xor) >= 1)
                                        else False
                                    ),
                                ):
                                    bound_2d = True
                                    if (
                                        CAM2D_INNER_CONTOUR_FLIP_ALL_CHAINS_AFTER_BIND
                                        and slot_chains_only
                                    ):
                                        try:
                                            _nfc = _slot_flip_all_chain_is_reverted_in_cad2d(cad_c)
                                            if _nfc:
                                                _send_diag_log(
                                                    '[slot-bind] post-bind flip isReverted (contours single): count=%d'
                                                    % _nfc
                                                )
                                        except Exception as _fce:
                                            try:
                                                _send_diag_log(
                                                    '[slot-bind][WARN] post-bind flip contours single: %s'
                                                    % _fce
                                                )
                                            except Exception:
                                                pass
                            except Exception as _cce:
                                _send_diag_log(f'[face-bind][WARN] contours chain: {_cce}')
                        if not bound_2d and target_faces and allow_face_fb:
                            try:
                                sels_c = cad_c.getCurveSelections()
                                if sels_c:
                                    try:
                                        sels_c.clear()
                                    except Exception:
                                        pass
                                fsel = sels_c.createNewFaceContourSelection()
                                if 'contour2d' in strat:
                                    fsel.loopType = adsk.cam.LoopTypes.OnlyInsideLoops
                                else:
                                    fsel.loopType = adsk.cam.LoopTypes.OnlyOutsideLoops
                                fsel.inputGeometry = list(target_faces)
                                cad_c.applyCurveSelections(sels_c)
                                bound_2d = True
                            except Exception as _ce:
                                _send_diag_log(f'[face-bind][WARN] contours chamfer2d/contour2d: {_ce}')

            # 關鍵：預設單面；合併模式可改為綁多面。（已用 pockets/contours 綁 2D 者不再寫 holeFaces）
            if not bound_2d and allow_face_fb:
                holeMode = _get_param('holeMode')
                faceParam = _get_param('holeFaces')
                if holeMode and faceParam and target_faces:
                    try:
                        _fast_set('holeMode', "'selection-faces'")
                        vec = faceParam.value.value
                        for f in target_faces:
                            if not f:
                                continue
                            try:
                                vec.push_back(f)
                            except Exception:
                                try:
                                    vec.add(f)
                                except Exception:
                                    pass
                        faceParam.value.value = vec
                    except Exception:
                        _send_diag_log(f'[face-bind][WARN] {opType}: failed to bind holeFaces')
            
            # 針對鑽孔和鉸孔的深度設置
            if opType in ['drill', 'reamer']:
                drillTip = _get_param('drillTipThroughBottom')
                if isThrough:
                    btp = _get_param('breakThroughDepth')
                    if btp:
                        try: _fast_set('breakThroughDepth', '1.5mm')
                        except: pass
                else:
                    if drillTip:
                        _fast_set('drillTipThroughBottom', 'false')
                    
                    bottomMode = _get_param('bottomHeight_mode')
                    if bottomMode:
                        try: _fast_set('bottomHeight_mode', "'from hole top'")
                        except: pass
                        
                    if holeDepthMM is not None:
                        try:
                            bottomOffset = _get_param('bottomHeight_offset')
                            if bottomOffset:
                                _fast_set('bottomHeight_offset', '-' + str(holeDepthMM) + 'mm')
                        except: pass
            
            results.append(op)
            if isinstance(perf_stats, dict):
                perf_stats['bind_seed_params_s'] = float(perf_stats.get('bind_seed_params_s', 0.0)) + (time.perf_counter() - _bind_t0)
        except:
            # 個別操作失敗不影響整體
            continue
            
    if clone_cache is not None and cache_key and cache_key not in clone_cache and results:
        # 首次模板建立保留為 prototype，供後續 copyAfter 複製。
        clone_cache[cache_key] = list(results)

    return results

def _set_param_expression(params, name, expr, diag_tag=''):
    """Set parameter expression with existence + write verification."""
    try:
        p = params.itemByName(name) if params else None
        if not p:
            _send_diag_log(f"[param-set][MISS] {diag_tag} {name}")
            return False
        p.expression = expr
        actual = str(getattr(p, 'expression', ''))
        ok = (actual == expr)
        if not ok:
            _send_diag_log(f"[param-set][MISMATCH] {diag_tag} {name} want={expr} got={actual}")
        return ok
    except Exception as e:
        _send_diag_log(f"[param-set][ERR] {diag_tag} {name} -> {e}")
        return False

def _dump_params(op, title=''):
    """Emit operation parameters to diagnostics pane."""
    try:
        if not op:
            _send_diag_log(f"[dump_params] {title} op=None")
            return
        params = op.parameters
        op_name = getattr(op, 'name', 'unknown')
        op_type = getOpToolType(op)
        _send_diag_log(f"[dump_params] {title} op={op_name} type={op_type} count={params.count}")
        for i in range(params.count):
            p = params.item(i)
            val_type = type(p.value).__name__
            _send_diag_log(f"[{i:03d}] {p.name} {val_type} expr={p.expression}")
    except Exception as e:
        _send_diag_log(f"[dump_params][ERR] {title} -> {e}")

def _dump_active_setup_ops_params(max_ops=8):
    camSetup = runtime_state.cam_setup
    if not camSetup:
        _send_diag_log("[dump_params] no active setup")
        return False
    try:
        ops = camSetup.allOperations
        n = min(ops.count, max_ops)
        _send_diag_log(f"[dump_params] setup={camSetup.name} total_ops={ops.count} dump_ops={n}")
        for i in range(n):
            _dump_params(ops.item(i), title=f"op#{i}")
        return True
    except Exception as e:
        _send_diag_log(f"[dump_params][ERR] setup dump failed: {e}")
        return False

def _append_seed_faces_to_existing_drill_op(op, faces_one_seed, same_diameter=True):
    """Add seed faces to existing drill operation."""
    if not op or not faces_one_seed:
        return False
    if not _is_cam_drill_operation_fast(op):
        return False
    try:
        params = op.parameters
        if not params:
            return False

        def _gp(name):
            try:
                return params.itemByName(name)
            except Exception:
                return None

        def _set_exp(pv, expr):
            if not pv:
                return False
            try:
                if str(getattr(pv, 'expression', '')) == expr:
                    return True
            except Exception:
                pass
            try:
                pv.expression = expr
                return True
            except Exception:
                return False

        _set_exp(_gp('selectSameDiameter'), 'true' if same_diameter else 'false')
        _set_exp(_gp('selectSameDepth'), 'false')
        _set_exp(_gp('selectSameTopZ'), 'false')
        _set_exp(_gp('checkForOcclusions'), 'true')
        hole_mode = _gp('holeMode')
        face_param = _gp('holeFaces')
        if not (hole_mode and face_param):
            return False
        _set_exp(hole_mode, "'selection-faces'")
        vec = face_param.value.value
        any_new = False
        for f in faces_one_seed:
            if not f:
                continue
            try:
                _tok = f.entityToken
            except Exception:
                _tok = None
            _dup = False
            if _tok:
                try:
                    for _vi in range(vec.count):
                        try:
                            if vec.item(_vi).entityToken == _tok:
                                _dup = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            if _dup:
                continue
            try:
                vec.push_back(f)
                any_new = True
            except Exception:
                try:
                    vec.add(f)
                    any_new = True
                except Exception:
                    return False
        if any_new:
            face_param.value.value = vec
        return True
    except Exception:
        return False

