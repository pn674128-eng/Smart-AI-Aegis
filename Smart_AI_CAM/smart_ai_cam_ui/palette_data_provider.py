# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion, adsk.cam
import os
import json
import re
import shutil
import unicodedata
from smart_ai_cam_state.runtime_state import state as runtime_state
from smart_ai_cam_ui import diagnostics
from smart_ai_cam_templates import template_service

# Configuration Constants
FIXED_PALETTE_WIDTH = 1440
MODE_DRILL_DEFAULT = '鑽深預設'
MODE_DRILL_HOLE_BOTTOM = '鑽過孔底部'
MODE_DRILL_STOCK_BOTTOM = '鑽過毛坯底部'
MODE_DEPTH_EDIT = '修改深度'
MODE_REAM_DEFAULT = '鉸深預設'
MODE_REAM_HOLE_BOTTOM = '鉸過孔底部'
MODE_REAM_STOCK_BOTTOM = '鉸過毛坯底部'
MODE_PITCH_DEFAULT = '預設'
MODE_PITCH_EDIT = '修改節距'
ALLOWED_CHAMFER_TAGS = ('C0.2', 'C0.3')

# Helper: Module path mappings
ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ui_settings_path = os.path.join(ADDIN_DIR, 'ui_defaults.json')


def _migrate_ui_defaults_from_addin_data_if_needed():
    """若先前已寫在 AddInData，而外掛目錄尚無 ui_defaults.json，則複製回外掛目錄一次。"""
    try:
        if os.path.isfile(_ui_settings_path):
            return
        base = (os.environ.get('APPDATA') or '').strip()
        if not base:
            return
        ext = os.path.normpath(
            os.path.join(
                base,
                'Autodesk',
                'Autodesk Fusion 360',
                'API',
                'AddInData',
                '半自動加工選單',
                'ui_defaults.json',
            )
        )
        if os.path.isfile(ext):
            shutil.copy2(ext, _ui_settings_path)
    except Exception:
        pass


_migrate_ui_defaults_from_addin_data_if_needed()


def _load_ui_defaults():
    defaults = {
        'mainWidth': 650,
        'mainHeight': 900,
        'paletteWidth': FIXED_PALETTE_WIDTH,
        'paletteHeight': 900,
        'colHoleWidth': 150,
        'colTemplateWidth': 170,
        'colCountWidth': 50,
        'colDepthWidth': 70,
        'colDrillModeWidth': 120,
        'colDrillDepthWidth': 85,
        'colReamModeWidth': 120,
        'colReamDepthWidth': 85,
        'colPitchWidth': 90,
        'colCalcWidth': 120,
        'rayDiameterDeltaMM': getattr(runtime_state, 'ray_diameter_delta_mm', None),
        'chamferInterferenceToolDiaMM': (
            getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None)
            if getattr(runtime_state, 'chamfer_interference_tool_dia_mm', None) is not None
            else 6.0
        ),
        'chamferInterferenceTopDeltaTolMM': (
            getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None)
            if getattr(runtime_state, 'chamfer_interference_top_delta_tol_mm', None) is not None
            else 0.05
        ),
        'holeTopHeightMode': getattr(runtime_state, 'hole_top_height_mode', 'from surface top'),
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
        'customTemplatesRoot': getattr(runtime_state, 'custom_templates_root', ''),
    }
    try:
        if not os.path.isfile(_ui_settings_path):
            return defaults
        with open(_ui_settings_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            defaults.update(data)
            defaults['paletteWidth'] = FIXED_PALETTE_WIDTH
    except:
        pass
    return defaults


def _save_ui_defaults(data):
    try:
        old = _load_ui_defaults()
        old.update(data or {})
        old['paletteWidth'] = FIXED_PALETTE_WIDTH
        with open(_ui_settings_path, 'w', encoding='utf-8') as f:
            json.dump(old, f, ensure_ascii=False, indent=2)
    except:
        pass


def _apply_fixed_palette_size(pal):
    if not pal:
        return
    try:
        pal.width = FIXED_PALETTE_WIDTH
    except:
        pass


def _ensure_diag_palette(visible=False, only_bind=False):
    """
    取得或建立診斷面板並寫入全域 _diag_palette。
    """
    try:
        palettes = adsk.core.Application.get().userInterface.palettes
        dpal = palettes.itemById('holeProcessDiagPalette')
        if not dpal:
            # 建立診斷面板！
            _diag_html_path = os.path.join(ADDIN_DIR, 'diag_palette.html')
            if os.path.exists(_diag_html_path):
                # 導入版本號作為快取消除參數
                try:
                    from Smart_AI.perception.feature_scanner import ADDIN_VERSION
                    ver = ADDIN_VERSION
                except Exception:
                    ver = "2.0358"
                from pathlib import Path
                _diag_url = Path(_diag_html_path).as_uri() + '?v=' + ver
                dpal = palettes.add(
                    'holeProcessDiagPalette',
                    'Smart AI CAM Diagnostics',
                    _diag_url,
                    visible,
                    True,
                    False,
                    400,
                    600
                )
                dpal.dockingOption = adsk.core.PaletteDockingOptions.PaletteDockOptionsToVerticalOnly
                dpal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        if dpal:
            if not only_bind:
                dpal.isVisible = visible
            diagnostics.register_diag_palette(dpal)
            return dpal
    except Exception:
        pass
    return None


def _mask_fullwidth_bracket_segments(text):
    """顯示用：移除全形【…】整段（含【】括號），畫面上不保留括號。"""
    try:
        return re.sub(r"\u3010[^\u3011]*\u3011", "", str(text or "")).strip()
    except Exception:
        return str(text or "").strip()


def _display_name_from_asset_leaf(leaf):
    name = leaf.replace('.f3dhsm-template', '').strip()
    return _mask_fullwidth_bracket_segments(name)


def _extract_template_diameter_mm(name):
    s = str(name or '')
    patterns = [
        r'[Dd]\s*(\d+(?:\.\d+)?)',
        r'[ØΦ]\s*(\d+(?:\.\d+)?)',
        r'直徑\s*(\d+(?:\.\d+)?)',
    ]
    for p in patterns:
        m = re.search(p, s, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
    return None


def _extract_item_diameter_mm(item):
    if not item:
        return None
    d = _extract_template_diameter_mm(item.get('rawName', ''))
    if d is not None:
        return d
    tags = item.get('tags', [])
    if tags:
        d = _extract_template_diameter_mm(' '.join([str(t) for t in tags]))
        if d is not None:
            return d
    return _extract_template_diameter_mm(item.get('name', ''))


def _filter_templates_by_diameter(items, dia_text, tol_mm=0.31):
    try:
        target = float(dia_text)
    except:
        return list(items or [])
    matched = []
    for it in (items or []):
        d = _extract_item_diameter_mm(it)
        if d is None:
            continue
        if abs(d - target) <= tol_mm:
            matched.append(it)
    return matched


def _chamfer_items_by_target_dia(chamferMap, dia_text):
    """孔倒角下拉：有分桶模板時先依孔徑與分割值選桶，再併入該徑 exact。"""
    try:
        s = str(dia_text or "").strip().replace(",", ".")
        target = round(float(s), 1)
    except Exception:
        return []
    key_exact = str(target)
    cm = chamferMap or {}
    try:
        _sk = getattr(template_service, "CHAMFER_BUCKET_SMALL_KEY", None) or "__cbkt_1_5__"
        _lk = getattr(template_service, "CHAMFER_BUCKET_LARGE_KEY", None) or "__cbkt_gt5__"
        _split = float(getattr(template_service, "CHAMFER_DIAM_BUCKET_SPLIT_MM", 5.0))
    except Exception:
        _sk, _lk, _split = "__cbkt_1_5__", "__cbkt_gt5__", 5.0

    b_small = list(cm.get(_sk) or [])
    b_large = list(cm.get(_lk) or [])
    has_buckets = bool(b_small) or bool(b_large)

    out = []
    seen = set()

    def _add(arr):
        for it in arr or []:
            k = (str(it.get("name", "")), str(it.get("url", "") or ""))
            if k in seen:
                continue
            seen.add(k)
            out.append(it)

    if has_buckets:
        if target <= _split + 1e-9:
            _add(b_small)
        else:
            _add(b_large)

    _add(list(cm.get(key_exact) or []))
    return out


def _drill_items_by_target_dia(drillMap, dia_text):
    try:
        target = round(float(dia_text), 1)
    except:
        return []
    key_exact = str(target)
    out = []
    if key_exact in drillMap:
        out.extend(drillMap.get(key_exact, []))
        
    best = []
    best_diff = 1e9
    for k, arr in (drillMap or {}).items():
        try:
            kv = float(k)
        except:
            continue
        diff = abs(kv - target)
        if diff < best_diff:
            best_diff = diff
            best = list(arr)
            
    if best_diff <= 0.2:
        for b in best:
            if b not in out:
                out.append(b)
                
    # 針對大孔或找不到相近鑽頭的特例：
    # 如果孔徑較大（如 >12mm）或完全找不到鑽頭，允許抓取小於該孔徑的「銑孔 (Bore-Milling)」模板來加工大圓孔
    if not out or target >= 12.0:
        for k, arr in (drillMap or {}).items():
            try:
                kv = float(k)
            except:
                continue
            # 確保銑孔平底刀的直徑小於要加工的圓孔直徑（留一點安全空間）
            if kv <= target - 0.5:
                for item in arr:
                    if item.get('hasMillBore', False) and item not in out:
                        out.append(item)
                        
    return out
def _countersink_folder_asset_as_drill_row_local(tmpl_lib, asset_dict):
    try:
        asset_url = asset_dict.get("url")
        if not asset_url or not tmpl_lib:
            return None
        leaf = str(asset_dict.get("rawName", "") or "")
        tags = list(asset_dict.get("tags") or [])
        display_name = str(asset_dict.get("name") or "").strip()
        if not display_name:
            leaf_clean = leaf.replace(".f3dhsm-template", "").strip()
            display_name = template_service.display_name_from_asset_leaf(leaf_clean)
        desc = ""
        try:
            desc = str((tmpl_lib.templateAtURL(asset_url).description or "")).lower()
        except Exception:
            desc = ""
        tag_str = " ".join(str(t) for t in tags)
        search_str = (desc + " " + tag_str + " " + display_name).lower()
        _ream_kw = ("絞孔", "絞刀", "定位孔", "精孔", "鏜孔", "reamer")
        _drill_kw = ("鑽孔", "點孔", "鑽頭", "鑚孔", "drill")
        _mill_kw = ("孔銑", "擴孔", "鏜孔")
        has_reamer = any(kw in search_str for kw in _ream_kw)
        has_drill = any(kw in search_str for kw in _drill_kw)
        has_mill_bore = any(kw in search_str for kw in _mill_kw)
        _infer = getattr(template_service, "_infer_cycle_and_tool_type", None)
        if callable(_infer):
            cycle_type, tool_type = _infer(has_drill, has_reamer, has_mill_bore)
        elif has_mill_bore:
            cycle_type, tool_type = "bore-milling", "flat end mill"
        elif has_reamer:
            cycle_type, tool_type = "reaming", "reamer"
        elif has_drill:
            cycle_type, tool_type = "deep-drilling", "drill"
        else:
            cycle_type, tool_type = "", ""
        return {
            "url": asset_url,
            "name": display_name,
            "hasDrill": has_drill,
            "hasReamer": has_reamer,
            "hasMillBore": has_mill_bore,
            "fromMillBoreFolder": has_mill_bore,
            "isCountersinkTemplate": True,
            "cycleType": cycle_type,
            "toolType": tool_type,
        }
    except Exception:
        return None


def _is_allowed_chamfer_name(name):
    try:
        s = unicodedata.normalize("NFKC", str(name or "")).upper().replace(" ", "")
    except Exception:
        s = (name or "").upper().replace(" ", "")
    return any(tag in s for tag in ALLOWED_CHAMFER_TAGS)


def _native_drop_label_display(label):
    return _mask_fullwidth_bracket_segments(label)


def _finalize_drop_item_display_labels(items):
    if not items:
        return
    bases = [_mask_fullwidth_bracket_segments(str(x.get("label") or "")) for x in items]
    try:
        from collections import Counter
        freq = Counter(bases)
    except Exception:
        freq = {}
    seen = {}
    for i, x in enumerate(items):
        if not isinstance(x, dict):
            continue
        b = bases[i]
        try:
            n_dup = int(freq.get(b, 1))
        except Exception:
            n_dup = 1
        if n_dup <= 1:
            x["listDisplay"] = b
        else:
            n = seen.get(b, 0) + 1
            seen[b] = n
            x["listDisplay"] = b if n == 1 else ("%s (%d)" % (b, n))


def _drop_list_display_label(item):
    if isinstance(item, dict) and "listDisplay" in item:
        return str(item["listDisplay"])
    return _native_drop_label_display(item.get("label") if isinstance(item, dict) else item)


def buildDropItems(dia, drillMap, chamferMap, holeInfo=None, countersinkItems=None):
    drillItems = _drill_items_by_target_dia(drillMap, dia)
    base_chamfer = _chamfer_items_by_target_dia(chamferMap, dia)
    if not base_chamfer:
        try:
            key_str = str(round(float(dia), 1))
            base_chamfer = chamferMap.get(key_str, [])
        except:
            base_chamfer = []
    chamferItems = [c for c in (base_chamfer or []) if _is_allowed_chamfer_name(c.get('name', ''))]
    is_cb_large = bool((holeInfo or {}).get('isCBLarge', False))
    items = []

    if not is_cb_large:
        _filtered = []
        for _d in (drillItems or []):
            try:
                _is_cs = bool(_d.get('isCountersinkTemplate', False))
                _nm = str(_d.get('name', '')).lower()
                if _is_cs or ('沉頭' in _nm) or ('countersink' in _nm):
                    continue
            except:
                pass
            _filtered.append(_d)
        drillItems = _filtered

    if is_cb_large:
        target_dia = dia
        cs_drill = [d for d in _drill_items_by_target_dia(drillMap, target_dia) if d.get('isCountersinkTemplate', False)]
        if not cs_drill:
            cs_drill = [d for d in (drillItems or []) if d.get('isCountersinkTemplate', False)]
        if not cs_drill and countersinkItems:
            _matched_cs = _filter_templates_by_diameter(countersinkItems, str(target_dia), tol_mm=0.2)
            if not _matched_cs:
                _matched_cs = _filter_templates_by_diameter(countersinkItems, str(target_dia), tol_mm=0.31)
            for _asset in _matched_cs:
                _fn = getattr(template_service, "countersink_folder_asset_as_drill_row", None)
                _row = (_fn(runtime_state.tmpl_lib, _asset) if callable(_fn) else None) or _countersink_folder_asset_as_drill_row_local(
                    runtime_state.tmpl_lib, _asset
                )
                if _row:
                    cs_drill.append(_row)
        source = _chamfer_items_by_target_dia(chamferMap, target_dia)
        source = [c for c in (source or []) if _is_allowed_chamfer_name(c.get('name', ''))]
        if not source:
            source = list(chamferItems or [])
        for d in cs_drill:
            for c in source:
                items.append({'label': d['name'] + ' + ' + c['name'], 'drillUrl': d['url'], 'chamferUrl': c['url'], 'hasDrill': d.get('hasDrill', False), 'hasReamer': d.get('hasReamer', False), 'hasMillBore': d.get('hasMillBore', False), 'hasChamfer': True})
        for d in cs_drill:
            items.append({'label': d['name'], 'drillUrl': d['url'], 'chamferUrl': None, 'hasDrill': d.get('hasDrill', False), 'hasReamer': d.get('hasReamer', False), 'hasMillBore': d.get('hasMillBore', False), 'hasChamfer': False})
        for c in source:
            items.append({'label': c['name'], 'drillUrl': None, 'chamferUrl': c['url'], 'hasDrill': False, 'hasReamer': False, 'hasMillBore': False, 'hasChamfer': True})
        items.append({'label': '(不使用)', 'drillUrl': None, 'chamferUrl': None, 'hasDrill': False, 'hasReamer': False, 'hasMillBore': False, 'hasChamfer': False})
        _finalize_drop_item_display_labels(items)
        return items

    for d in drillItems:
        for c in chamferItems:
            items.append({'label': d['name'] + ' + ' + c['name'], 'drillUrl': d['url'], 'chamferUrl': c['url'], 'hasDrill': d.get('hasDrill', False), 'hasReamer': d.get('hasReamer', False), 'hasMillBore': d.get('hasMillBore', False), 'hasChamfer': True})
    for c in chamferItems:
        items.append({'label': c['name'], 'drillUrl': None, 'chamferUrl': c['url'], 'hasDrill': False, 'hasReamer': False, 'hasMillBore': False, 'hasChamfer': True})
    for d in drillItems:
        items.append({'label': d['name'], 'drillUrl': d['url'], 'chamferUrl': None, 'hasDrill': d.get('hasDrill', False), 'hasReamer': d.get('hasReamer', False), 'hasMillBore': d.get('hasMillBore', False), 'hasChamfer': False})
    items.append({'label': '(不使用)', 'drillUrl': None, 'chamferUrl': None, 'hasDrill': False, 'hasReamer': False, 'hasMillBore': False, 'hasChamfer': False})
    _finalize_drop_item_display_labels(items)
    return items


def build_simple_drill_drop_items_only(dia, drillMap):
    """口袋槽 R 角列專用：僅一般鑽孔模板。"""
    drill_items = drillMap.get(dia, []) or []
    items = []
    for _d in drill_items:
        try:
            if bool(_d.get('isCountersinkTemplate', False)):
                continue
            _nm = str(_d.get('name', '')).lower()
            if ('沉頭' in _nm) or ('countersink' in _nm):
                continue
        except Exception:
            pass
        if bool(_d.get('hasMillBore')):
            continue
        if bool(_d.get('hasReamer')):
            continue
        if not bool(_d.get('hasDrill', True)):
            continue
        try:
            ct = str(_d.get('cycleType', '') or '').lower()
            if 'ream' in ct or 'bore-milling' in ct:
                continue
        except Exception:
            pass
        items.append({
            'label': _d['name'],
            'drillUrl': _d['url'],
            'chamferUrl': None,
            'hasDrill': True,
            'hasReamer': False,
            'hasMillBore': False,
            'hasChamfer': False,
            'cycleType': _d.get('cycleType', ''),
            'toolType': _d.get('toolType', ''),
        })
    items.append({
        'label': '(不使用)',
        'drillUrl': None,
        'chamferUrl': None,
        'hasDrill': False,
        'hasReamer': False,
        'hasMillBore': False,
        'hasChamfer': False,
    })
    _finalize_drop_item_display_labels(items)
    return items
