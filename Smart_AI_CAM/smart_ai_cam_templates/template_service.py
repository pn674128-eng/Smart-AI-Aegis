import re
import unicodedata

import adsk.cam

from smart_ai_cam_state.runtime_state import state as runtime_state
from . import template_fs_cache


def ensure_tmpl_lib():
    """取得 Fusion CAM 模板庫；若尚未綁定則寫入 runtime_state.tmpl_lib。"""
    lib = getattr(runtime_state, "tmpl_lib", None)
    if lib:
        return lib
    try:
        mgr = adsk.cam.CAMManager.get().libraryManager
        if mgr:
            lib = mgr.templateLibrary
            if lib:
                runtime_state.tmpl_lib = lib
                return lib
    except Exception:
        pass
    return None


ZH_LEFT = "\u3010"
ZH_RIGHT = "\u3011"
KW_COUNTERSINK = "\u6c89\u982d"
KW_REAM_1 = "\u7d5e\u5b54"
KW_REAM_2 = "\u7d5e\u5200"
KW_REAM_3 = "\u5b9a\u4f4d\u5b54"
KW_REAM_4 = "\u7cbe\u5b54"
KW_REAM_5 = "\u94f0\u5b54"
KW_DRILL_1 = "\u947d\u5b54"
KW_DRILL_2 = "\u9ede\u5b54"
KW_DRILL_3 = "\u947d\u982d"
KW_DRILL_4 = "\u94bb\u5b54"
KW_MILL_BORE_1 = "\u5b54\u92d1"
KW_MILL_BORE_2 = "\u64f4\u5b54"
KW_MILL_BORE_3 = "\u94e3\u5b54"
KW_DRILL_FOLDER = "\u5b54\u52a0\u5de5\u6a21\u584a"
KW_CHAMFER_FOLDER = "\u5012\u89d2\u5200\u6a21\u584a"
KW_COMPLETE = "\u5b8c\u6574"
KW_SLOT_1 = "\u9577\u689d\u5b54"
KW_SLOT_2 = "\u69fd\u5b54"

# 孔徑「分桶」孔倒角（選用）＋ exact 鍵：牙孔 M 展開之底孔徑；**非分桶、非牙孔**時自檔名／路徑擷取 D、Ø、直徑或**純數字資料夾名**（見 `_extract_chamfer_index_diameter_mm`）；若仍無徑鍵但檔名含 **C0.2/C0.3**，則同掛小徑／大徑桶（`_chamfer_items_by_target_dia` 依孔徑只合併一側）。主檔 UI 先依孔徑與分割值選桶，再合併 exact 鍵。
# - 檔名／顯示名／**相對路徑 relpath**／【】tags 任一处含「小於D5.0」「小于D5.0」「小於5.0」「小徑」等 → 小徑桶
# - 同上含「大於D5.0」「大于D5.0」「大於5.0」「大徑」等 → 大徑桶（常見：分桶寫在父資料夾名，檔名僅「倒角C0.2」）
# - 路徑形如「…/孔倒角 【mat】/C0.2/<分桶資料夾>/檔」時，會對 **C0.2／C0.3 下一層資料夾名** 再判斷（見 classify_chamfer_template_bucket）
# - 或含 #CB1-5# / #CB5UP#
# 分桶模板請用 leaf 全名或路徑區分；chamfer_map 的 name 保留【】於資料層，下拉顯示由 display_name_from_asset_leaf／palette 隱藏整段【…】。
CHAMFER_DIAM_BUCKET_SPLIT_MM = 5.0
CHAMFER_BUCKET_SMALL_KEY = "__cbkt_1_5__"
CHAMFER_BUCKET_LARGE_KEY = "__cbkt_gt5__"
CHAMFER_BUCKET_SMALL_MARKER = "#CB1-5#"
CHAMFER_BUCKET_LARGE_MARKER = "#CB5UP#"

# 須與主檔 `ALLOWED_CHAMFER_TAGS`／`_is_allowed_chamfer_name` 一致（NFKC、去空白、大寫子字串）。
_HOLE_CHAMFER_UI_ALLOWED_TAGS = ("C0.2", "C0.3")


def _chamfer_display_name_without_bucket_markers(display_name):
    s = str(display_name or "")
    for m in (CHAMFER_BUCKET_SMALL_MARKER, CHAMFER_BUCKET_LARGE_MARKER):
        s = s.replace(m, "")
    s = s.strip()
    return s if s else str(display_name or "")


def _collapse_ws_for_bucket_match(s):
    """NFKC 後移除所有 Unicode 空白（含 NBSP、全形空白）；供分桶關鍵字連續比對。"""
    try:
        t = unicodedata.normalize("NFKC", str(s or ""))
    except Exception:
        t = str(s or "")
    return re.sub(r"\s+", "", t, flags=re.UNICODE)


def _match_chamfer_bucket_in_text(blob_ns: str, blob_lo: str):
    """由已去空白／全形空白的字串判斷分桶；回傳 'small'、'large' 或 None。"""
    if CHAMFER_BUCKET_SMALL_MARKER in blob_ns or CHAMFER_BUCKET_SMALL_MARKER.lower() in blob_lo:
        return "small"
    if CHAMFER_BUCKET_LARGE_MARKER in blob_ns or CHAMFER_BUCKET_LARGE_MARKER.lower() in blob_lo:
        return "large"

    if ("大於D5.0" in blob_ns) or ("大于D5.0" in blob_ns) or ("大於5.0" in blob_ns) or ("大于5.0" in blob_ns):
        return "large"
    if ("小於D5.0" in blob_ns) or ("小于D5.0" in blob_ns) or ("小於5.0" in blob_ns) or ("小于5.0" in blob_ns):
        return "small"

    if any(k in blob_ns for k in ("小徑", "小桶", "小孔徑")):
        return "small"
    if any(k in blob_ns for k in ("大徑", "大桶", "大孔徑")):
        return "large"
    bup = blob_ns.upper()
    if any(k in bup for k in ("<=5.0", "<=5", "D<=5", "D≤5", "D≤5.0", "LE5MM", "LTE5")):
        return "small"
    if any(k in bup for k in (">5.0", ">5", "D>5", "D>5.0", "D≥5", "GE5MM", "GTE5")):
        return "large"
    return None


def classify_chamfer_template_bucket(raw_leaf, relpath="", tags=None):
    """孔倒角分桶：回傳 'small'（孔徑 ≤ 分割）、'large'（> 分割），無標記則 None。

    與 CHAMFER_DIAM_BUCKET_SPLIT_MM 對齊。**分桶關鍵字只看「未經 display_name_from_asset_leaf 剝除【…】」的來源**：
    **完整檔名 raw_leaf**（無副檔名即可）、**relpath**、以及 **extract_tags 所得 tags**（括號內文會出現在 tags，亦併入比對）。
    **不可**把 `display_name_from_asset_leaf` 的結果當主判斷字串——該函式會移除 `【…】` 整段，若「小於D5.0」等僅寫在括號內會被剝掉而誤判。

    另支援「…/孔倒角 【mat】/C0.2/<分桶資料夾>/檔名」路徑。
    """
    tags = tags or []
    leaf_s = str(raw_leaf or "")
    rp = str(relpath or "").replace("\\", "/")
    tag_join = "".join(str(t) for t in tags)
    # 主判斷：不含剝【】後的 display_name，避免「【小於D5.0孔倒角】…」只剩「倒角C0.2」而失配。
    raw = leaf_s + rp + tag_join
    blob_ns = _collapse_ws_for_bucket_match(raw)
    blob_lo = blob_ns.lower()

    hit = _match_chamfer_bucket_in_text(blob_ns, blob_lo)
    if hit:
        return hit

    # …/孔倒角 【AL6061】/C0.2/<分桶資料夾>/xxx.f3dhsm-template；若模板直接在 C0.2 下則改掃檔名（最後一節）。
    try:
        rp2 = unicodedata.normalize("NFKC", str(relpath or "").replace("\\", "/"))
    except Exception:
        rp2 = str(relpath or "").replace("\\", "/")
    parts = [p for p in rp2.split("/") if p.strip()]
    for i, seg in enumerate(parts):
        su = re.sub(r"[\s_]+", "", seg).upper()
        if su in ("C0.2", "C02", "C0.3", "C03"):
            if i + 1 >= len(parts):
                break
            trail = "/".join(parts[i + 1 : -1])
            if not trail:
                trail = parts[-1]
            if not trail:
                break
            t_ns = _collapse_ws_for_bucket_match(trail)
            t_lo = t_ns.lower()
            # 極短資料夾名（僅在 C0.x 子路徑下解讀）
            if t_ns in ("小", "S"):
                return "small"
            if t_ns in ("大", "L"):
                return "large"
            hit2 = _match_chamfer_bucket_in_text(t_ns, t_lo)
            if hit2:
                return hit2
            break
    return None


def _chamfer_map_stored_name(leaf):
    """寫入 chamfer_map 條目的 `name`：保留全形【…】內文（不在此剝除）；僅自檔名移除 #CB 標記。

    下拉／內建表在**顯示層**另隱藏整段【…】（見主檔 `_native_drop_label_display`、palette `hideFullWidthBracketsForDisplay`），
    與「辨識在入池前、呈現在入 UI 後」分工一致。
    """
    base = str(leaf or "").replace(".f3dhsm-template", "").strip()
    if CHAMFER_BUCKET_SMALL_MARKER in base or CHAMFER_BUCKET_LARGE_MARKER in base:
        return _chamfer_display_name_without_bucket_markers(base)
    return base


# 與 NewScript.METRIC_THREAD_TAP_HOLE_SPEC_MM 同步：(內部鍵, 標準徑, +0.1 徑, 牙距 mm)
_METRIC_TAP_HOLE_SPEC_ITEMS = (
    ("M2", 1.6, 1.7, 0.4),
    ("M2.5", 2.1, 2.2, 0.45),
    ("M3", 2.5, 2.6, 0.5),
    ("M4", 3.3, 3.4, 0.7),
    ("M5", 4.2, 4.3, 0.8),
    ("M6", 5.0, 5.1, 1.0),
    ("M6x0.75", 5.3, 5.4, 0.75),
    ("M8", 6.8, 6.9, 1.25),
    ("M8x1.0", 7.0, 7.1, 1.0),
    ("M10", 8.5, 8.6, 1.5),
    ("M12", 10.3, 10.4, 1.75),
)


def _tap_pitch_token(pitch_mm):
    s = "{:.4f}".format(float(pitch_mm)).rstrip("0").rstrip(".")
    return s if s else "0"


def tap_template_display_label(thread_key: str) -> str:
    """模板檔名用：M3 → M3-0.5；M6x0.75 → M6-0.75（與 NewScript 一致）。"""
    k = str(thread_key or "").strip()
    for key, _lo, _hi, pitch in _METRIC_TAP_HOLE_SPEC_ITEMS:
        if key == k:
            base = key.split("x", 1)[0].split("X", 1)[0]
            return "{}-{}".format(base, _tap_pitch_token(pitch))
    return k


# 牙孔模板 leaf 中「牙孔」與全形【 之間的字串 → +0.1 底孔徑（內部鍵與 M3-0.5 等顯示鍵皆可）
TAP_THREAD_CLEAR_DRILL_MM = {}
for _key, _lo, hi, _pitch in _METRIC_TAP_HOLE_SPEC_ITEMS:
    TAP_THREAD_CLEAR_DRILL_MM[_key] = hi
    lbl = tap_template_display_label(_key)
    TAP_THREAD_CLEAR_DRILL_MM[lbl] = hi

# Optional hook: main add-in registers _send_diag_log + Text Commands (see set_template_maps_diag_log).
_diag_template_maps_log = None


def set_template_maps_diag_log(fn):
    """Register a callable(str) for strict vs compat template-map loads (docs/行為準則.md §8.0.1)."""
    global _diag_template_maps_log
    _diag_template_maps_log = fn


def _log_template_maps(msg):
    fn = _diag_template_maps_log
    if not callable(fn):
        return
    try:
        fn(str(msg))
    except Exception:
        pass


def _format_template_rel_path(rel_path, material):
    """展開 TEMPLATE_FOLDER_PATHS 內的材質占位符，供診斷輸出（與 collect_assets 所用路徑一致）。"""
    if rel_path is None or rel_path == "":
        return ""
    s = str(rel_path)
    m = str(material)
    # ASCII 與全形大括號兩種常見占位（避免編輯器／複製貼上造成字元不一致）
    for ph in ("{material}", "\uff5bmaterial\uff5d"):
        if ph in s:
            s = s.replace(ph, m)
    return s


def display_name_from_asset_leaf(leaf):
    """由模板檔 leaf 產生**主孔表／下拉選單用**的精簡顯示名（剝除全形【…】整段）。

    用途：避免選項文字臃腫；**僅在模板已入池、或即將寫入 UI 列 `name` 時**呼叫。
    **不得**用於分桶、牙孔徑鍵展開、或任何須讀取【】內標記的辨識——該類辨識須在帶入 UI 前、
    對 **raw leaf／relpath／extract_tags** 完成（見 `add_to_chamfer_map`／`classify_chamfer_template_bucket`）。
    """
    name = leaf.replace(".f3dhsm-template", "").strip()
    return re.sub(r"\u3010[^\u3011]*\u3011", "", name).strip()


def extract_tags(name):
    return re.findall(r"\u3010([^\u3011]*)\u3011", name or "")


def _nfkc_leaf(leaf):
    try:
        return unicodedata.normalize("NFKC", str(leaf or ""))
    except Exception:
        return str(leaf or "")


# 路徑／檔名中若出現「他材」全形【材質碼】，視為跨材複製誤放，掃描時略過（避免 AL6061／S50C 等混在一起）。
_BRACKET_MATERIAL_CODES = ("AL6061", "S50C")


def _asset_path_has_foreign_bracket_material(relpath, leaf, material):
    mat = str(material or "").strip()
    try:
        blob = unicodedata.normalize(
            "NFKC", f"{str(relpath or '').replace(chr(92), '/')}/{str(leaf or '')}"
        ).lower()
    except Exception:
        blob = f"{str(relpath or '').replace(chr(92), '/')}/{str(leaf or '')}".lower()
    ml = mat.lower()
    for code in _BRACKET_MATERIAL_CODES:
        c = str(code).lower()
        if c == ml:
            continue
        if f"{ZH_LEFT}{c}{ZH_RIGHT}" in blob:
            return True
    return False


def _extract_drill_diameter_mm_from_leaf_d_pattern(leaf):
    """自檔名擷取最後一組 D／d 後的直徑（mm）。

    先 NFKC（全形Ｄ、全形．→半形），再以正則找 `D5.4`、`D 5.0` 等；取**最後一組**以貼近「孔徑 D」語意。
    取代舊式 `if "D" in leaf` + `split("D",1)`，避免全形 D 或緊貼【 時漏判。
    """
    s = _nfkc_leaf(leaf)
    ms = list(re.finditer(r"(?i)d\s*(\d+(?:\.\d+)?)", s))
    if not ms:
        return None
    try:
        return float(ms[-1].group(1))
    except Exception:
        return None


def _hole_chamfer_allowed_tag_in_text(leaf, tags):
    try:
        blob = _nfkc_leaf(str(leaf or "")) + "".join(str(t) for t in (tags or []))
        s = unicodedata.normalize("NFKC", blob).upper().replace(" ", "")
    except Exception:
        s = (str(leaf or "") + "".join(str(t) for t in (tags or []))).upper().replace(" ", "")
    return any(tag in s for tag in _HOLE_CHAMFER_UI_ALLOWED_TAGS)


def _extract_pure_numeric_folder_diameter_mm_from_relpath(relpath):
    """路徑中若有一節為純數字資料夾名（例 …/3.0/倒角…），視為孔徑 mm（由檔案往根方向取最後一個合理值）。"""
    try:
        rp = unicodedata.normalize("NFKC", str(relpath or "").replace("\\", "/"))
    except Exception:
        rp = str(relpath or "").replace("\\", "/")
    segs = [s.strip() for s in rp.split("/") if s.strip()]
    for seg in reversed(segs):
        t = re.sub(r"\s+", "", seg)
        if not re.fullmatch(r"\d+(?:\.\d+)?", t):
            continue
        try:
            v = float(t)
        except Exception:
            continue
        if 0.2 <= v <= 80.0:
            return v
    return None


def _extract_d_mm_from_chamfer_title_brackets(leaf):
    """自 raw 檔名擷取「孔倒角模板」之孔徑鍵（mm）。

    常見命名：`【孔倒角 D3.0】 倒角C0.2 【AL6061】` — 孔徑寫在**全形【】**內，與「倒角」同段；顯示層會隱藏整段【…】，
    **索引／與「定位孔 D3.0」「一般孔 D3.0」對徑時必須用 rawName，不可先剝【】**。

    掃描各 `【…】`：若段內含「倒角」，則取該段內**最後一組** `D`／`d` 後之數字（NFKC）。
    """
    s = _nfkc_leaf(str(leaf or ""))
    dao_jiao = "\u5012\u89d2"
    for m in re.finditer(r"\u3010([^\u3011]*)\u3011", s):
        inner = m.group(1)
        if dao_jiao not in inner:
            continue
        dms = list(re.finditer(r"(?i)d\s*(\d+(?:\.\d+)?)", inner))
        if not dms:
            continue
        try:
            return float(dms[-1].group(1))
        except Exception:
            continue
    return None


def _extract_chamfer_index_diameter_mm(leaf, relpath="", tags=None):
    """自 raw 檔名／路徑擷取孔徑（mm），供 chamfer_map 與主檔 `holeInfo['dia']` 對齊。

    契約（與使用者庫一致）：
    - **定位孔／一般孔**鑽模板：以檔名之 `D數字` 為孔徑（見 `add_to_drill_map`）。
    - **孔倒角**模板：孔徑常寫在 `【孔倒角 D3.0】` 等全形括號內；**顯示會隱藏【…】，索引用 rawName，不得先剝除括號**。
    擷取順序：含「倒角」之【…】內 D → 全字串最後一組 D → Ø／Φ／直徑 → relpath 純數字資料夾名。
    """
    tags = tags or []
    d_title = _extract_d_mm_from_chamfer_title_brackets(str(leaf or ""))
    if d_title is not None:
        return d_title
    try:
        leaf_n = _nfkc_leaf(str(leaf or ""))
    except Exception:
        leaf_n = str(leaf or "")
    try:
        rp = unicodedata.normalize("NFKC", str(relpath or "").replace("\\", "/"))
    except Exception:
        rp = str(relpath or "").replace("\\", "/")
    tag_join = "".join(str(t) for t in tags)
    blob = "/".join(p for p in (leaf_n, rp, tag_join) if p)
    d = _extract_drill_diameter_mm_from_leaf_d_pattern(blob)
    if d is not None:
        return d
    try:
        m = re.search(r"[ØΦ]\s*(\d+(?:\.\d+)?)", blob)
        if m:
            return float(m.group(1))
        m = re.search(r"\u76f4\u5f91\s*(\d+(?:\.\d+)?)", blob)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    d_folder = _extract_pure_numeric_folder_diameter_mm_from_relpath(rp)
    if d_folder is not None:
        return d_folder
    return None


def collect_assets_from_folder_path(tmpl_lib, material, rel_path):
    out = []
    if not tmpl_lib or not rel_path:
        return out
    try:
        entries, _ = template_fs_cache.get_material_fs_entries(material)
        prefix = template_fs_cache.prefix_under_material(rel_path.format(material=material), material)
        for e in template_fs_cache.filter_entries_under_prefix(entries, prefix):
            try:
                leaf = e["leaf"]
                if _asset_path_has_foreign_bracket_material(e.get("relpath"), leaf, material):
                    continue
                u = template_fs_cache.url_join_relative_path(tmpl_lib, material, e["relpath"])
                out.append(
                    {
                        "url": u,
                        "name": display_name_from_asset_leaf(leaf),
                        "rawName": leaf.replace(".f3dhsm-template", "").strip(),
                        "tags": extract_tags(leaf),
                        "relpath": e["relpath"],
                    }
                )
            except Exception:
                continue
        if out:
            out.sort(key=lambda x: x["name"])
            return out
    except Exception:
        pass
    url = tmpl_lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    parts = [p.strip() for p in rel_path.format(material=material).split("/") if p.strip()]
    try:
        for part in parts:
            url = url.join(part)
    except Exception:
        return out
    _scan_folder(tmpl_lib, url, out)
    out.sort(key=lambda x: x["name"])
    return out


def _resolve_library_folder_url(tmpl_lib, material, rel_path):
    if not tmpl_lib or not rel_path:
        return None
    url = tmpl_lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    parts = [p.strip() for p in rel_path.format(material=material).split("/") if p.strip()]
    try:
        for part in parts:
            url = url.join(part)
        return url
    except Exception:
        return None


def _norm_chamfer_tag(s):
    try:
        return re.sub(r"\s+", "", str(s or "").strip().upper())
    except Exception:
        return ""


def _scan_folder_slot_chamfer(tmpl_lib, folder_url, out, bucket_tag, depth):
    """
    在 contourChamfer 根下：子資料夾名稱即為倒角分類（例 C0.2、C0.3），不要求檔名含標籤。
    根目錄直接放的模板 bucket_tag 為 None，仍可用檔名／顯示名對 allowed 標籤做相容（舊習慣）。
    """
    try:
        assets = tmpl_lib.childAssetURLs(folder_url)
    except Exception:
        assets = []
    for a in assets:
        leaf = a.leafName
        out.append(
            {
                "url": a,
                "name": display_name_from_asset_leaf(leaf),
                "rawName": leaf.replace(".f3dhsm-template", "").strip(),
                "tags": extract_tags(leaf),
                "slotChamferBucket": bucket_tag,
            }
        )
    try:
        folders = tmpl_lib.childFolderURLs(folder_url)
    except Exception:
        folders = []
    for f in folders:
        try:
            if f.leafName == "_XRef_":
                continue
        except Exception:
            pass
        try:
            sub_name = str(f.leafName or "").strip()
        except Exception:
            sub_name = ""
        if depth == 0:
            next_tag = sub_name if sub_name else None
        else:
            next_tag = bucket_tag
        _scan_folder_slot_chamfer(tmpl_lib, f, out, next_tag, depth + 1)


def collect_slot_chamfer_assets(tmpl_lib, material, rel_path):
    """掃描輪廓倒角樹並附帶 slotChamferBucket（子資料夾名）；供長條孔倒角下拉。"""
    out = []
    try:
        entries, _ = template_fs_cache.get_material_fs_entries(material)
        prefix = template_fs_cache.prefix_under_material(rel_path.format(material=material), material)
        for e in template_fs_cache.filter_entries_under_prefix(entries, prefix):
            try:
                leaf = e["leaf"]
                if _asset_path_has_foreign_bracket_material(e.get("relpath"), leaf, material):
                    continue
                u = template_fs_cache.url_join_relative_path(tmpl_lib, material, e["relpath"])
                bucket, _ = template_fs_cache.slot_chamfer_bucket_from_relpath(material, e["relpath"])
                out.append(
                    {
                        "url": u,
                        "name": display_name_from_asset_leaf(leaf),
                        "rawName": leaf.replace(".f3dhsm-template", "").strip(),
                        "tags": extract_tags(leaf),
                        "slotChamferBucket": bucket,
                    }
                )
            except Exception:
                continue
        if out:
            out.sort(key=lambda x: x["name"])
            return out
    except Exception:
        pass
    url = _resolve_library_folder_url(tmpl_lib, material, rel_path)
    if not url:
        return out
    _scan_folder_slot_chamfer(tmpl_lib, url, out, None, 0)
    out.sort(key=lambda x: x["name"])
    return out


def _scan_folder(tmpl_lib, folder_url, out):
    try:
        assets = tmpl_lib.childAssetURLs(folder_url)
    except Exception:
        assets = []
    for a in assets:
        leaf = a.leafName
        out.append(
            {
                "url": a,
                "name": display_name_from_asset_leaf(leaf),
                "rawName": leaf.replace(".f3dhsm-template", "").strip(),
                "tags": extract_tags(leaf),
                "relpath": "",
            }
        )
    try:
        folders = tmpl_lib.childFolderURLs(folder_url)
    except Exception:
        folders = []
    for f in folders:
        try:
            if f.leafName == "_XRef_":
                continue
        except Exception:
            pass
        _scan_folder(tmpl_lib, f, out)


def validate_configured_template_paths(tmpl_lib, materials, template_folder_paths):
    missing = []
    check_keys = [
        "topFaceRough",
        "topFaceFinish",
        "profileRough",
        "profileFinish",
        "generalHole",
        "tapHole",
        "locatingHole",
        "holeChamfer",
        "countersinkHole",
        "slotHole",
        "contourChamfer",
    ]
    for mat in materials:
        for key in check_keys:
            rel = template_folder_paths.get(key, "")
            if rel and not template_folder_exists(tmpl_lib, mat, rel):
                missing.append(f"[{mat}] {key}: {rel.format(material=mat)}")
    return missing


def template_folder_exists(tmpl_lib, material, rel_path):
    if not rel_path:
        return False
    try:
        if template_fs_cache.fs_folder_exists(material, rel_path):
            return True
    except Exception:
        pass
    if not tmpl_lib:
        return False
    url = tmpl_lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    parts = [p.strip() for p in rel_path.format(material=material).split("/") if p.strip()]
    try:
        for part in parts:
            url = url.join(part)
        tmpl_lib.childAssetURLs(url)
        return True
    except Exception:
        return False


def merge_template_items(primary, legacy):
    seen = set()
    merged = []
    for item in (primary or []) + (legacy or []):
        key = (item.get("name", ""), str(item.get("url", "")))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def load_2d_template_maps(tmpl_lib, material, template_folder_paths):
    tf_rough = collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths["topFaceRough"])
    tf_finish = collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths["topFaceFinish"])
    tf_legacy = collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths["topFaceLegacy"])
    pf_rough = collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths["profileRough"])
    pf_finish = collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths["profileFinish"])
    pf_legacy = collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths["profileLegacy"])
    top_rough = merge_template_items(tf_rough, tf_legacy if not tf_rough else [])
    top_finish = merge_template_items(tf_finish, tf_legacy if not tf_finish else [])
    profile_rough = merge_template_items(pf_rough, pf_legacy if not pf_rough else [])
    profile_finish = merge_template_items(pf_finish, pf_legacy if not pf_finish else [])
    profile_all = merge_template_items(profile_rough, profile_finish)
    top_all = merge_template_items(top_rough, top_finish)
    return top_rough, top_finish, profile_rough, profile_finish, top_all, profile_all


def load_countersink_templates(tmpl_lib, material, template_folder_paths):
    return collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths.get("countersinkHole", "")) or []


def load_slot_templates(tmpl_lib, material, template_folder_paths):
    return collect_assets_from_folder_path(tmpl_lib, material, template_folder_paths.get("slotHole", "")) or []


def load_slot_chamfer_templates(tmpl_lib, material, template_folder_paths, allowed_chamfer_tags):
    """
    長條孔用輪廓倒角模板。

    contourChamfer 鍵僅指向「…/倒角刀模塊 【mat】/輪廓倒角 【mat】」；C0.2／C0.3 為其**下一層**子資料夾。
    以子資料夾名對應 allowed_chamfer_tags（例：`…/輪廓倒角 【S50C】/C0.2/*.template`），不要求檔名含 C0.2。
    根目錄上的模板若無 bucket，仍可用檔名／顯示名含標籤納入（舊相容）。
    """
    items = collect_slot_chamfer_assets(tmpl_lib, material, template_folder_paths.get("contourChamfer", ""))
    tags_norm = [_norm_chamfer_tag(t) for t in (allowed_chamfer_tags or ()) if _norm_chamfer_tag(t)]
    if not tags_norm:
        return list(items or [])
    out = []
    for x in items or []:
        try:
            bucket = _norm_chamfer_tag(x.get("slotChamferBucket"))
            name_up = _norm_chamfer_tag(x.get("name", ""))
            matched = False
            for t in tags_norm:
                if bucket:
                    if bucket == t:
                        matched = True
                        break
                else:
                    if t in name_up:
                        matched = True
                        break
            if matched:
                out.append(x)
        except Exception:
            pass
    return out


def build_template_maps(tmpl_lib, material, tap_dia_map, tap_short_map, template_folder_paths=None):
    drill_map, chamfer_map = {}, {}
    local_url = tmpl_lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    mat_url = local_url.join(material)
    tag = f"{ZH_LEFT}{material}{ZH_RIGHT}"
    target_drill = f"{KW_DRILL_FOLDER} {tag}"
    target_chamfer = f"{KW_CHAMFER_FOLDER} {tag}"

    def _looks_like_slot_template(text):
        s = str(text or "").lower()
        return any(k in s for k in [KW_SLOT_1, KW_SLOT_2, "slot", "obround", "racetrack"])

    def add_to_chamfer_map(asset_url, leaf, tags, relpath=""):
        """孔倒角入 chamfer_map：先以完整檔名／路徑辨識分桶與牙孔展開，**最後**才產剝【】的 display_name 供下拉顯示。"""
        try:
            if _looks_like_slot_template(" ".join([leaf] + [str(t) for t in (tags or [])])):
                return
            _bucket = classify_chamfer_template_bucket(leaf, relpath=relpath, tags=tags)
            if _bucket == "small":
                _append_chamfer(
                    chamfer_map,
                    CHAMFER_BUCKET_SMALL_KEY,
                    asset_url,
                    _chamfer_map_stored_name(leaf),
                    tags,
                )
                return
            if _bucket == "large":
                _append_chamfer(
                    chamfer_map,
                    CHAMFER_BUCKET_LARGE_KEY,
                    asset_url,
                    _chamfer_map_stored_name(leaf),
                    tags,
                )
                return
            # 牙孔倒角：依 leaf 內 M 規格展開到底孔徑鍵。
            matched_tap = False
            for tap, (dia_min, dia_max) in tap_dia_map.items():
                if tap_short_map.get(tap, tap) not in leaf:
                    continue
                matched_tap = True
                d = dia_min
                while round(d, 1) <= round(dia_max, 1):
                    _append_chamfer(chamfer_map, str(round(d, 1)), asset_url, _chamfer_map_stored_name(leaf), tags)
                    d = round(d + 0.1, 1)
                break
            if not matched_tap:
                d_ch = _extract_chamfer_index_diameter_mm(leaf, relpath=relpath, tags=tags)
                if d_ch is not None:
                    try:
                        _append_chamfer(
                            chamfer_map,
                            str(round(float(d_ch), 1)),
                            asset_url,
                            _chamfer_map_stored_name(leaf),
                            tags,
                        )
                    except Exception:
                        pass
                elif _hole_chamfer_allowed_tag_in_text(leaf, tags):
                    # 有 C0.2/C0.3 但無徑鍵時：同掛小徑／大徑桶，讓 _chamfer_items_by_target_dia 依孔徑只取一側，避免整庫檔案落在 C0.2 子資料夾卻無 D 而全滅。
                    for _bk in (CHAMFER_BUCKET_SMALL_KEY, CHAMFER_BUCKET_LARGE_KEY):
                        _append_chamfer(
                            chamfer_map,
                            _bk,
                            asset_url,
                            _chamfer_map_stored_name(leaf),
                            tags,
                        )
        except Exception:
            pass

    def add_to_drill_map(asset_url, leaf, tags, folder_hint=""):
        display_name = display_name_from_asset_leaf(leaf)
        nf_leaf = _nfkc_leaf(leaf)
        try:
            desc = (tmpl_lib.templateAtURL(asset_url).description or "")
        except Exception:
            desc = ""
        tag_str = " ".join(tags)
        marker_text = (folder_hint + " " + nf_leaf + " " + tag_str + " " + desc).lower()
        if _looks_like_slot_template(marker_text):
            return
        is_countersink = (KW_COUNTERSINK in marker_text) or ("countersink" in marker_text)
        search_str = (desc + " " + tag_str + " " + display_name).lower()
        has_reamer = any(kw in search_str for kw in [KW_REAM_1, KW_REAM_2, KW_REAM_3, KW_REAM_4, KW_REAM_5, "reamer"])
        has_drill = any(kw in search_str for kw in [KW_DRILL_1, KW_DRILL_2, KW_DRILL_3, KW_DRILL_4, "drill"])
        has_mill_bore = any(kw in search_str for kw in [KW_MILL_BORE_1, KW_MILL_BORE_2, KW_MILL_BORE_3])
        if "\u7259\u5b54" in nf_leaf:
            has_drill = True
        cycle_type, tool_type = _infer_cycle_and_tool_type(has_drill, has_reamer, has_mill_bore)
        matched_tap = False
        for tap, (dia_min, dia_max) in tap_dia_map.items():
            if tap not in nf_leaf:
                continue
            d = dia_min
            while round(d, 1) <= round(dia_max, 1):
                _append_drill(
                    drill_map,
                    str(round(d, 1)),
                    asset_url,
                    display_name,
                    has_drill,
                    has_reamer,
                    has_mill_bore,
                    is_countersink,
                    cycle_type,
                    tool_type,
                )
                d = round(d + 0.1, 1)
            matched_tap = True
            break
        if not matched_tap:
            d_part = None
            # 牙孔 M3-0.5【SG】【AL6061】→ 以建議底孔徑入 drill_map
            m_yp = re.search(r"\u7259\u5b54\s*([^\s\u3010]+)", nf_leaf)
            if m_yp:
                tk = m_yp.group(1).strip()
                if tk in TAP_THREAD_CLEAR_DRILL_MM:
                    try:
                        d_part = float(TAP_THREAD_CLEAR_DRILL_MM[tk])
                    except Exception:
                        d_part = None
            # 一般孔 D1.0【SG】【AL6061】；舊名含「鑽孔模板」或「鑽頭直徑」仍相容
            if d_part is None:
                m_bit = re.search(r"\u947d\u982d\u76f4\u5f91(\d+\.?\d*)", nf_leaf)
                if m_bit:
                    try:
                        d_part = float(m_bit.group(1))
                    except Exception:
                        d_part = None
            if d_part is None:
                d_part = _extract_drill_diameter_mm_from_leaf_d_pattern(leaf)
            if d_part is not None:
                try:
                    _append_drill(
                        drill_map,
                        str(round(float(d_part), 1)),
                        asset_url,
                        display_name,
                        has_drill,
                        has_reamer,
                        has_mill_bore,
                        is_countersink,
                        cycle_type,
                        tool_type,
                    )
                except Exception:
                    pass

    # Drill templates: strict folder mapping for through-hole flow.
    # Only include 一般孔 / 牙孔 / 定位孔 to avoid countersink leakage into normal holes.
    strict_loaded = False
    if template_folder_paths:
        strict_keys = ("generalHole", "tapHole", "locatingHole")
        for key in strict_keys:
            rel = template_folder_paths.get(key, "")
            items = collect_assets_from_folder_path(tmpl_lib, material, rel) if rel else []
            if not items:
                continue
            strict_loaded = True
            for it in items:
                add_to_drill_map(
                    it.get("url"),
                    str(it.get("rawName", "")),
                    list(it.get("tags", [])),
                    key,
                )

    if strict_loaded:
        _log_template_maps(
            f"[template-maps][strict] {material} 鑽模板：僅自 generalHole／tapHole／locatingHole 指定資料夾載入（見行為準則 §8.0.1）。"
        )

    # Chamfer templates (strict): only TEMPLATE_FOLDER_PATHS["holeChamfer"] subtree.
    # Do not scan the whole 倒角刀模塊 tree — other subfolders may hold same D10-style names for different flows.
    if strict_loaded:
        if template_folder_paths:
            rel_ch = template_folder_paths.get("holeChamfer", "")
            if rel_ch:
                ch_items = collect_assets_from_folder_path(tmpl_lib, material, rel_ch)
                for it in ch_items or []:
                    add_to_chamfer_map(
                        it.get("url"),
                        str(it.get("rawName", "")),
                        list(it.get("tags", [])),
                        str(it.get("relpath", "") or ""),
                    )
                # 先展開再組字串，避免 f-string / 舊 pyc 快取導致診斷仍顯示未代入的 rel_ch
                rel_ch_for_log = _format_template_rel_path(rel_ch, material)
                _log_template_maps(
                    "[template-maps][strict] "
                    + str(material)
                    + " 孔倒角：僅自 holeChamfer 指定階層「"
                    + rel_ch_for_log
                    + "」載入，資產 "
                    + str(len(ch_items or []))
                    + " 筆。"
                )
            else:
                _log_template_maps(
                    f"[template-maps][compat] {material} holeChamfer 鍵缺失或空字串 → _scan_chamfer_tree_only（整個倒角刀模塊樹）。行為準則 §8.0.1"
                )
                _scan_chamfer_tree_only(tmpl_lib, mat_url, target_chamfer, add_to_chamfer_map)
        else:
            _log_template_maps(
                f"[template-maps][compat] {material} template_folder_paths 未提供 → _scan_chamfer_tree_only。行為準則 §8.0.1"
            )
            _scan_chamfer_tree_only(tmpl_lib, mat_url, target_chamfer, add_to_chamfer_map)
    else:
        # Fallback for backward compatibility: previous full-tree behavior.
        _log_template_maps(
            f"[template-maps][compat] {material} strict_loaded=False（三嚴格鑽資料夾皆無資產）→ _scan_template_tree（整樹相容）。行為準則 §8.0.1"
        )
        _scan_template_tree(tmpl_lib, mat_url, target_drill, target_chamfer, add_to_drill_map, add_to_chamfer_map)
    for key in drill_map:
        drill_map[key].sort(key=lambda x: (1 if x.get("fromMillBoreFolder", False) else 0, 0 if KW_COMPLETE in x["name"] else 1, x["name"]))
    for key in chamfer_map:
        chamfer_map[key].sort(key=lambda x: x["name"])
    return drill_map, chamfer_map


def _append_chamfer(chamfer_map, key, asset_url, display_name, tags):
    chamfer_map.setdefault(key, [])
    if not any(x["name"] == display_name for x in chamfer_map[key]):
        chamfer_map[key].append({"url": asset_url, "name": display_name, "tags": tags})


def _append_drill(
    drill_map,
    key,
    asset_url,
    display_name,
    has_drill,
    has_reamer,
    has_mill_bore,
    is_countersink,
    cycle_type,
    tool_type,
):
    drill_map.setdefault(key, [])
    if not any(x["name"] == display_name for x in drill_map[key]):
        drill_map[key].append(
            {
                "url": asset_url,
                "name": display_name,
                "hasDrill": has_drill,
                "hasReamer": has_reamer,
                "hasMillBore": has_mill_bore,
                "fromMillBoreFolder": has_mill_bore,
                "isCountersinkTemplate": is_countersink,
                "cycleType": cycle_type,
                "toolType": tool_type,
            }
        )


def _infer_cycle_and_tool_type(has_drill, has_reamer, has_mill_bore):
    # UI display should prioritize actual machining cycle behavior.
    if has_mill_bore:
        return "bore-milling", "flat end mill"
    if has_reamer:
        return "reaming", "reamer"
    if has_drill:
        return "deep-drilling", "drill"
    return "", ""


def countersink_folder_asset_as_drill_row(tmpl_lib, asset_dict):
    """
    將 countersinkHole 資料夾掃出的資產轉成與 drill_map 項目相同鍵值。

    strict 模式下鑽模板只來自 generalHole/tapHole/locatingHole，沉頭加工模板改由
    TEMPLATE_FOLDER_PATHS['countersinkHole'] 單獨載入；主檔 buildDropItems（isCBLarge）
    須用本函式把該清單併回 cs_drill，才能再與孔倒角組出「沉頭 + 倒角」選項。
    """
    try:
        asset_url = asset_dict.get("url")
        if not asset_url or not tmpl_lib:
            return None
        leaf = str(asset_dict.get("rawName", "") or "")
        tags = list(asset_dict.get("tags") or [])
        display_name = str(asset_dict.get("name") or "").strip()
        if not display_name:
            display_name = display_name_from_asset_leaf(leaf.replace(".f3dhsm-template", "").strip())
        desc = ""
        try:
            desc = str((tmpl_lib.templateAtURL(asset_url).description or "")).lower()
        except Exception:
            desc = ""
        tag_str = " ".join(str(t) for t in tags)
        search_str = (desc + " " + tag_str + " " + display_name).lower()
        has_reamer = any(kw in search_str for kw in [KW_REAM_1, KW_REAM_2, KW_REAM_3, KW_REAM_4, KW_REAM_5, "reamer"])
        has_drill = any(kw in search_str for kw in [KW_DRILL_1, KW_DRILL_2, KW_DRILL_3, KW_DRILL_4, "drill"])
        has_mill_bore = any(kw in search_str for kw in [KW_MILL_BORE_1, KW_MILL_BORE_2, KW_MILL_BORE_3])
        cycle_type, tool_type = _infer_cycle_and_tool_type(has_drill, has_reamer, has_mill_bore)
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


def _scan_chamfer_tree_only(tmpl_lib, mat_url, target_chamfer, add_to_chamfer_map):
    """Legacy / fallback: recurse entire 倒角刀模塊 【material】.

    常態應只用 TEMPLATE_FOLDER_PATHS['holeChamfer'] 指定子樹（行為準則 §8.0.1）。
    進入本函式時應已由 build_template_maps 寫入 [template-maps][compat] 日誌。
    """
    def scan_folder(url):
        try:
            assets = tmpl_lib.childAssetURLs(url)
        except Exception:
            assets = []
        for a in assets:
            leaf = a.leafName
            tags = extract_tags(leaf)
            add_to_chamfer_map(a, leaf, tags)
        try:
            folders = tmpl_lib.childFolderURLs(url)
        except Exception:
            folders = []
        for f in folders:
            if f.leafName == "_XRef_":
                continue
            scan_folder(f)

    try:
        top_folders = tmpl_lib.childFolderURLs(mat_url)
    except Exception:
        top_folders = []
    for f in top_folders:
        if f.leafName == target_chamfer:
            scan_folder(f)


def _scan_template_tree(tmpl_lib, mat_url, target_drill, target_chamfer, add_to_drill_map, add_to_chamfer_map):
    """Legacy / fallback: scan 孔加工模塊 + 倒角刀模塊整樹（strict 三鑽夾皆空時）。

    非指定資料夾主路徑；見行為準則 §8.0.1。進入前應已寫入 [template-maps][compat] 日誌。
    """
    def scan_folder(url, is_chamfer_folder, breadcrumb=""):
        try:
            assets = tmpl_lib.childAssetURLs(url)
        except Exception:
            assets = []
        current_hint = (breadcrumb + "/" + url.leafName).strip("/")
        for a in assets:
            leaf = a.leafName
            tags = extract_tags(leaf)
            if is_chamfer_folder:
                add_to_chamfer_map(a, leaf, tags)
            else:
                add_to_drill_map(a, leaf, tags, current_hint)
        try:
            folders = tmpl_lib.childFolderURLs(url)
        except Exception:
            folders = []
        for f in folders:
            if f.leafName == "_XRef_":
                continue
            scan_folder(f, is_chamfer_folder, current_hint)

    try:
        top_folders = tmpl_lib.childFolderURLs(mat_url)
    except Exception:
        top_folders = []
    for f in top_folders:
        if f.leafName == target_drill:
            scan_folder(f, False)
        elif f.leafName == target_chamfer:
            scan_folder(f, True)
