"""
本機 CAM360\\templates\\{材質} 整包掃描索引，供模板清單快取。

- 以檔案 mtime 組簽章，磁碟有變才重掃目錄。
- 仍透過 templateLibrary.join(...) 還原 Fusion 資產 URL，工序套用不繞過 API。
"""
from __future__ import annotations

import hashlib
import os

ZH_LEFT = "\u3010"
ZH_RIGHT = "\u3011"

_CACHE: dict[str, dict] = {}


def templates_root() -> str:
    # 預設路徑
    default_root = os.path.normpath(
        os.path.join(os.environ.get("APPDATA", ""), "Autodesk", "CAM360", "templates")
    )
    return default_root



def material_fs_root(material: str) -> str:
    return os.path.normpath(os.path.join(templates_root(), str(material or "").strip()))


def invalidate_all() -> None:
    _CACHE.clear()


def invalidate_material(material: str) -> None:
    _CACHE.pop(str(material or "").strip(), None)


def _signature(entries: list[dict]) -> str:
    h = hashlib.md5()
    for e in entries:
        h.update(
            f"{e['relpath']}\0{e.get('mtime_ns', 0)}\0{e.get('size', 0)}\n".encode(
                "utf-8", errors="replace"
            )
        )
    return h.hexdigest()


def _scan_disk(material: str) -> list[dict]:
    root = material_fs_root(material)
    out: list[dict] = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "_XRef_"]
        for fn in filenames:
            if not fn.lower().endswith(".f3dhsm-template"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                rel = os.path.relpath(full, root).replace("\\", "/")
            except Exception:
                continue
            try:
                st = os.stat(full)
                mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
                size = int(getattr(st, "st_size", 0))
            except Exception:
                mtime_ns = 0
                size = 0
            out.append({"relpath": rel, "mtime_ns": mtime_ns, "size": size, "leaf": fn})
    out.sort(key=lambda x: x["relpath"])
    return out


def get_material_fs_entries(material: str) -> tuple[list[dict], str]:
    """回傳 (entries, signature)；優先使用記憶體快取避免 I/O 延遲。"""
    mat = str(material or "").strip()
    if not mat:
        return [], ""
    prev = _CACHE.get(mat)
    if prev:
        return prev["entries"], prev["sig"]
    entries = _scan_disk(mat)
    sig = _signature(entries)
    _CACHE[mat] = {"sig": sig, "entries": entries}
    return entries, sig



def prefix_under_material(rel_path_formatted: str, material: str) -> str:
    """TEMPLATE_FOLDER_PATHS 展開後，去掉第一層材質目錄，得到相對於材質根的路徑前綴。"""
    parts = [p.strip() for p in rel_path_formatted.split("/") if p.strip()]
    if parts and parts[0] == material:
        return "/".join(parts[1:])
    return "/".join(parts)


def filter_entries_under_prefix(entries: list[dict], prefix_posix: str) -> list[dict]:
    prefix = prefix_posix.strip("/")
    if not prefix:
        return list(entries)
    out = []
    for e in entries:
        rp = e["relpath"]
        if rp == prefix or rp.startswith(prefix + "/"):
            out.append(e)
    return out


def url_join_relative_path(tmpl_lib, material: str, relpath_posix: str):
    import adsk.cam
    import adsk.core
    
    # 預設本地 HSM 本地庫路徑
    url = tmpl_lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation).join(material)
    for seg in relpath_posix.replace("\\", "/").split("/"):
        s = seg.strip()
        if not s:
            continue
        url = url.join(s)
    return url


def contour_folder_leaf(material: str) -> str:
    return f"\u8f2a\u5ed3\u5012\u89d2 {ZH_LEFT}{material}{ZH_RIGHT}"


def slot_chamfer_bucket_from_relpath(material: str, relpath_posix: str):
    """
    與 _scan_folder_slot_chamfer 一致：輪廓倒角根下第一層子資料夾名為 bucket（C0.2/C0.3），
    檔案直接放在輪廓倒角根下則為 None。
    """
    segs = [s for s in relpath_posix.replace("\\", "/").split("/") if s.strip()]
    leaf = segs[-1] if segs else ""
    folder = contour_folder_leaf(material)
    try:
        ix = segs.index(folder)
    except ValueError:
        return None, leaf
    rest = segs[ix + 1 : -1]
    if not rest:
        return None, leaf
    return rest[0], leaf


def fs_folder_exists(material: str, rel_path_formatted: str) -> bool:
    """不依 Fusion API，僅檢查 CAM360\\templates 下資料夾是否存在。"""
    mat = str(material or "").strip()
    if not mat or not rel_path_formatted:
        return False
    parts = [p.strip() for p in rel_path_formatted.format(material=mat).split("/") if p.strip()]
    if not parts:
        return False
    p = os.path.join(templates_root(), *parts)
    try:
        return os.path.isdir(p)
    except Exception:
        return False
