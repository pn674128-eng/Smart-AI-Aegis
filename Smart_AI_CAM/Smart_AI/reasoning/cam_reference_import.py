# -*- coding: utf-8 -*-
"""
參考檔 CAM 匯入：工序模板解析、設計掃描幾何、寫入 KnowledgeDB。

須在 Fusion Manufacture 環境呼叫（需 adsk）。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import reference_paths as rp
from Smart_AI.memory.knowledge_db import get_db

PROGRAMMING_MODE_IMPORTED = "imported_f3z"
REFERENCE_EXTENSIONS = (".f3d", ".f3z")

_F3DHSM_RE = re.compile(r"([^/\\]+\.f3dhsm-template)", re.IGNORECASE)
_DIA_IN_NAME_RE = re.compile(r"D\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def load_reference_manifest() -> dict:
    path = rp.reference_manifest_path()
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _iter_reference_files_on_disk():
    lib_dir = rp.reference_f3z_dir()
    if not lib_dir or not os.path.isdir(lib_dir):
        return
    for fn in sorted(os.listdir(lib_dir)):
        low = fn.lower()
        for ext in REFERENCE_EXTENSIONS:
            if low.endswith(ext):
                fp = os.path.join(lib_dir, fn)
                if os.path.isfile(fp):
                    yield {
                        "file_type": ext.lstrip("."),
                        "archive_name": fn,
                        "path": fp,
                        "size_bytes": os.path.getsize(fp),
                    }
                break


def list_reference_f3z() -> dict:
    lib_dir = rp.reference_f3z_dir()
    manifest = load_reference_manifest()
    on_disk = list(_iter_reference_files_on_disk())
    by_type = {}
    for item in on_disk:
        ft = item.get("file_type", "?")
        by_type[ft] = by_type.get(ft, 0) + 1
    return {
        "reference_root": rp.reference_template_root(),
        "library_dir": lib_dir,
        "f3z_dir": lib_dir,
        "manifest": manifest,
        "files_on_disk": on_disk,
        "counts_by_type": by_type,
        "count": len(on_disk),
    }


def list_reference_files() -> dict:
    return list_reference_f3z()


def _norm_label_key(label: str) -> str:
    s = str(label or "").strip()
    if not s:
        return ""
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)[:96]


def _collect_op_param_blob(op) -> str:
    parts = []
    try:
        op_name = str(op.name or "")
        if op_name:
            parts.append(op_name)
    except Exception:
        pass
    try:
        params = op.parameters
        for i in range(int(params.count)):
            p = params.item(i)
            try:
                parts.append(str(p.name or ""))
            except Exception:
                pass
            try:
                parts.append(str(p.expression or ""))
            except Exception:
                pass
            try:
                parts.append(str(p.value))
            except Exception:
                pass
    except Exception:
        pass
    try:
        if op.tool:
            parts.append(str(op.tool.description or ""))
            tparams = op.tool.parameters
            for i in range(int(tparams.count)):
                tp = tparams.item(i)
                try:
                    parts.append(str(tp.name or ""))
                    parts.append(str(tp.expression or ""))
                except Exception:
                    pass
    except Exception:
        pass
    return " ".join(parts)


def _tool_diameter_mm(op) -> Optional[float]:
    try:
        if op.tool:
            v = float(op.tool.parameters.itemByName("tool_diameter").value.value) * 10.0
            if v > 0:
                return round(v, 3)
    except Exception:
        pass
    return None


def _template_label_from_library(op_name: str, tmpl_lib, material: str) -> str:
    """Match operation display name to indexed template leaf (best effort)."""
    if not tmpl_lib or not op_name:
        return ""
    key = _norm_label_key(op_name)
    if not key:
        return ""
    try:
        from smart_ai_cam_templates import template_fs_cache
        from smart_ai_cam_templates.template_service import display_name_from_asset_leaf

        mat = str(material or "AL6061").upper()
        for rel, _mtime in template_fs_cache.iter_indexed_files(mat):
            if not rel.lower().endswith(".f3dhsm-template"):
                continue
            leaf = os.path.basename(rel)
            disp = display_name_from_asset_leaf(leaf.replace(".f3dhsm-template", ""))
            if _norm_label_key(disp) == key or key in _norm_label_key(disp):
                return disp
            if _norm_label_key(leaf) == key:
                return display_name_from_asset_leaf(leaf)
    except Exception:
        pass
    return ""


def extract_operation_template_meta(
    op,
    *,
    tmpl_lib=None,
    material: str = "AL6061",
) -> dict:
    """
    Phase 1: template path/label from parameters, library index, operation name.
    """
    try:
        op_name = str(op.name or "")
    except Exception:
        op_name = ""
    blob = _collect_op_param_blob(op)
    template_path = ""
    template_used = op_name
    m = _F3DHSM_RE.search(blob)
    if m:
        template_path = m.group(1)
        try:
            from smart_ai_cam_templates.template_service import display_name_from_asset_leaf

            template_used = display_name_from_asset_leaf(
                template_path.replace(".f3dhsm-template", "").strip()
            )
        except Exception:
            template_used = template_path.replace(".f3dhsm-template", "")
    if tmpl_lib and op_name and template_used == op_name:
        resolved = _template_label_from_library(op_name, tmpl_lib, material)
        if resolved:
            template_used = resolved
    tool_dia = _tool_diameter_mm(op)
    dia_from_name = None
    mn = _DIA_IN_NAME_RE.search(op_name or "")
    if mn:
        try:
            dia_from_name = float(mn.group(1))
        except Exception:
            pass
    meta = {
        "operation_name": op_name,
        "template_used": template_used or op_name,
        "template_path": template_path,
        "tool_diameter_mm": tool_dia,
        "diameter_from_name_mm": dia_from_name,
    }
    try:
        from .template_resolver import enrich_operation_template_meta

        return enrich_operation_template_meta(meta, material)
    except Exception:
        return meta


def _op_tool_type_str(op) -> str:
    try:
        from smart_ai_cam_machining.operation_builder import getOpToolType

        return str(getOpToolType(op) or "")
    except Exception:
        pass
    try:
        return str(op.operationType or "")
    except Exception:
        return ""


def _feature_type_from_op(op_name: str, tool_type: str) -> str:
    n = (op_name or "").lower()
    t = (tool_type or "").lower()
    if "drill" in n or "drill" in t or "hole" in n:
        return "hole"
    if "tap" in n or "thread" in n:
        return "hole"
    if "chamfer" in n or "倒角" in n:
        return "chamfer"
    if "face" in n or "面铣" in n or "面銑" in n or "face" in t:
        return "face"
    if "contour" in n or "外形" in n or "profile" in n or "contour" in t:
        return "profile"
    if "slot" in n or "槽" in n or "pocket" in n or "pocket" in t:
        return "slot"
    return "hole"


def build_geometry_index_from_scan(scan_ctx: Optional[dict], material: str) -> dict:
    """
    Phase 2: plugin hole/slot scan → geometry buckets for matching.
    """
    if not scan_ctx:
        return {"ok": False, "holes_by_dia": {}, "slots_by_width": {}}
    mat = str(material or "AL6061").upper()
    try:
        rebuild = scan_ctx.get("rebuild_holes")
        if callable(rebuild):
            rebuild(force=True)
    except Exception:
        pass

    from . import ai_training as at

    hole_list: List[dict] = []
    slot_list: List[dict] = []
    build_hole = scan_ctx.get("build_hole_data")
    build_slot = scan_ctx.get("build_slot_data")
    if callable(build_hole):
        try:
            hole_list = list(build_hole(mat) or [])
        except Exception:
            hole_list = []
    if callable(build_slot):
        try:
            slot_list = list(build_slot(mat) or [])
        except Exception:
            slot_list = []

    holes_by_dia: Dict[float, List[dict]] = {}
    for h in hole_list or []:
        if not isinstance(h, dict):
            continue
        geom = at._hole_geometry_for_db(h)
        dia = round(float(geom.get("diameter_mm", 0) or 0), 2)
        if dia <= 0:
            continue
        holes_by_dia.setdefault(dia, []).append(geom)

    slots_by_width: Dict[float, List[dict]] = {}
    for s in slot_list or []:
        if not isinstance(s, dict):
            continue
        geom = at._slot_geometry_for_db(s)
        w = round(float(geom.get("width_mm", 0) or 0), 2)
        if w <= 0:
            continue
        slots_by_width.setdefault(w, []).append(geom)

    return {
        "ok": True,
        "material": mat,
        "hole_row_count": len(hole_list or []),
        "slot_row_count": len(slot_list or []),
        "holes_by_dia": holes_by_dia,
        "slots_by_width": slots_by_width,
    }


def _match_geometry_for_operation(op_row: dict, geom_index: dict) -> dict:
    ft = op_row.get("feature_type", "hole")
    if ft == "hole":
        dia = op_row.get("tool_diameter_mm")
        if dia is None:
            dia = op_row.get("diameter_from_name_mm")
        if dia is not None:
            dia = round(float(dia), 2)
            bucket = (geom_index.get("holes_by_dia") or {}).get(dia)
            if bucket:
                return dict(bucket[0])
        holes = geom_index.get("holes_by_dia") or {}
        if holes and len(holes) == 1:
            only = next(iter(holes.values()))
            if only:
                return dict(only[0])
    if ft == "slot":
        w = op_row.get("tool_diameter_mm")
        if w is not None:
            w = round(float(w), 2)
            bucket = (geom_index.get("slots_by_width") or {}).get(w)
            if bucket:
                return dict(bucket[0])
    return {}


def scan_setup_operations(
    setup,
    *,
    setup_name: str = "",
    tmpl_lib=None,
    material: str = "AL6061",
    geom_index: Optional[dict] = None,
) -> List[dict]:
    rows = []
    if not setup:
        return rows
    try:
        ops = setup.allOperations
        count = int(ops.count)
    except Exception:
        return rows
    sname = setup_name or str(getattr(setup, "name", "") or "")
    for i in range(count):
        try:
            op = ops.item(i)
        except Exception:
            continue
        meta = extract_operation_template_meta(op, tmpl_lib=tmpl_lib, material=material)
        op_name = meta.get("operation_name") or "op_{}".format(i)
        tool_type = _op_tool_type_str(op)
        ft = _feature_type_from_op(op_name, tool_type)
        row = {
            "setup": sname,
            "index": i,
            "name": op_name,
            "tool_type": tool_type,
            "feature_type": ft,
            "template_used": meta.get("template_used") or op_name,
            "template_path": meta.get("template_path") or "",
            "tool_diameter_mm": meta.get("tool_diameter_mm"),
            "diameter_from_name_mm": meta.get("diameter_from_name_mm"),
            "geometry": {},
        }
        if geom_index and geom_index.get("ok"):
            geo = _match_geometry_for_operation(row, geom_index)
            if geo:
                row["geometry"] = geo
                row["geometry_matched"] = True
        rows.append(row)
    return rows


def scan_document_cam(
    cam_obj,
    *,
    active_setup=None,
    all_setups: bool = True,
    tmpl_lib=None,
    material: str = "AL6061",
    geom_index: Optional[dict] = None,
) -> dict:
    if not cam_obj:
        return {"ok": False, "error": "no cam_obj", "operations": []}
    setups_out = []
    all_ops: List[dict] = []
    try:
        setups = cam_obj.setups
        n = int(setups.count)
    except Exception as e:
        return {"ok": False, "error": str(e), "operations": []}

    active_name = ""
    if active_setup is not None:
        try:
            active_name = str(active_setup.name)
        except Exception:
            pass

    for si in range(n):
        try:
            setup = setups.item(si)
        except Exception:
            continue
        sname = str(getattr(setup, "name", "") or "")
        if not all_setups and active_name and sname != active_name:
            continue
        rows = scan_setup_operations(
            setup,
            setup_name=sname,
            tmpl_lib=tmpl_lib,
            material=material,
            geom_index=geom_index,
        )
        setups_out.append({"name": sname, "operation_count": len(rows)})
        all_ops.extend(rows)

    matched = sum(1 for r in all_ops if r.get("geometry_matched"))
    return {
        "ok": True,
        "active_setup": active_name,
        "setups": setups_out,
        "operations": all_ops,
        "operation_count": len(all_ops),
        "geometry_matched_count": matched,
    }


def build_knowledge_records(
    operations: List[dict],
    *,
    material: str,
    source_label: str = "",
) -> List[dict]:
    mat = str(material or "AL6061").upper()
    out = []
    for op in operations or []:
        if not isinstance(op, dict):
            continue
        tmpl = str(op.get("template_used") or op.get("name") or "").strip()
        if not tmpl:
            continue
        out.append(
            {
                "feature_type": op.get("feature_type", "hole"),
                "material": mat,
                "geometry": dict(op.get("geometry") or {}),
                "template_used": tmpl,
                "template_path": str(op.get("template_path") or ""),
                "op_count": 1,
                "programming_mode": PROGRAMMING_MODE_IMPORTED,
                "source": source_label or op.get("setup", ""),
                "operation_name": op.get("name", ""),
            }
        )
    return out


def write_import_snapshot(records: List[dict], *, document_label: str = "") -> str:
    root = rp.reference_template_root()
    if not root:
        return ""
    out_dir = os.path.join(root, "cam匯入快照")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (document_label or "doc"))[:40]
    path = os.path.join(out_dir, "{}_{}.json".format(safe, stamp))
    payload = {
        "version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document": document_label,
        "programming_mode": PROGRAMMING_MODE_IMPORTED,
        "records": records,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def import_records_to_knowledge_db(records: List[dict]) -> dict:
    db = get_db()
    imported = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        tmpl = str(rec.get("template_used", "") or "").strip()
        if not tmpl:
            continue
        tpath = str(rec.get("template_path") or rec.get("resolved_url_str") or "").strip()
        rid = db.record_operation(
            rec.get("feature_type", "hole"),
            rec.get("material", "AL6061"),
            rec.get("geometry") or {},
            tmpl,
            template_path=tpath,
            op_count=int(rec.get("op_count", 1) or 1),
            programming_mode=str(rec.get("programming_mode") or PROGRAMMING_MODE_IMPORTED),
        )
        if rid:
            imported.append(rid)
    if imported:
        db.rebuild_index()
        db.flush()
    return {"imported": len(imported), "record_ids": imported}


def run_import_cam_from_active_document(
    cam_obj,
    *,
    active_setup=None,
    material: str = "AL6061",
    all_setups: bool = True,
    write_db: bool = True,
    save_snapshot: bool = True,
    document_label: str = "",
    scan_geometry: bool = True,
    scan_ctx: Optional[dict] = None,
    tmpl_lib=None,
) -> dict:
    geom_index = None
    if scan_geometry and scan_ctx:
        geom_index = build_geometry_index_from_scan(scan_ctx, material)

    scan = scan_document_cam(
        cam_obj,
        active_setup=active_setup,
        all_setups=all_setups,
        tmpl_lib=tmpl_lib,
        material=material,
        geom_index=geom_index,
    )
    if not scan.get("ok"):
        return {"success": False, "error": scan.get("error", "scan failed"), "data": scan}

    label = document_label or scan.get("active_setup") or "fusion_document"
    records = build_knowledge_records(
        scan.get("operations") or [],
        material=material,
        source_label=label,
    )
    if not records:
        return {
            "success": False,
            "error": "未找到可匯入的 CAM 工序（請確認已開啟含刀路的製造文件）",
            "data": {"scan": scan, "geometry_index": geom_index, "records": []},
        }

    result = {
        "scan": scan,
        "geometry_index": geom_index,
        "records": records,
        "snapshot_path": "",
    }
    if save_snapshot:
        result["snapshot_path"] = write_import_snapshot(records, document_label=label)
    if write_db:
        result["import"] = import_records_to_knowledge_db(records)

    return {
        "success": True,
        "message": "已匯入 {} 筆工序（幾何匹配 {} 筆）".format(
            len(records), scan.get("geometry_matched_count", 0)
        ),
        "data": result,
    }
