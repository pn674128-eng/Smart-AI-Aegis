# -*- coding: utf-8 -*-
"""
參考範本批次 CAM 匯入（Phase 3）：依 manifest 逐檔開啟並匯入。

須在 Fusion 內呼叫；每步建議 max_files=1，避免 UI 長時間凍結。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import cam_reference_import as cri
from . import reference_paths as rp

STATE_VERSION = 1


def batch_state_path() -> str:
    root = rp.reference_template_root()
    if not root:
        return ""
    return os.path.join(root, "batch_import_state.json")


def load_batch_state() -> dict:
    path = batch_state_path()
    if not path or not os.path.isfile(path):
        return {"version": STATE_VERSION, "completed": [], "failed": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": STATE_VERSION, "completed": [], "failed": []}
        data.setdefault("completed", [])
        data.setdefault("failed", [])
        return data
    except Exception:
        return {"version": STATE_VERSION, "completed": [], "failed": []}


def save_batch_state(state: dict) -> str:
    path = batch_state_path()
    if not path:
        return ""
    state["version"] = STATE_VERSION
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


def _norm_path(p: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    except Exception:
        return str(p or "")


def list_pending_files(*, reset: bool = False) -> List[dict]:
    if reset:
        save_batch_state({"version": STATE_VERSION, "completed": [], "failed": []})
    state = load_batch_state()
    done = {_norm_path(p) for p in (state.get("completed") or [])}
    failed_paths = {_norm_path(f.get("path", "")) for f in (state.get("failed") or []) if isinstance(f, dict)}

    manifest = cri.load_reference_manifest()
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    files: List[dict] = []
    if isinstance(entries, list) and entries:
        for ent in entries:
            if not isinstance(ent, dict):
                continue
            fp = ent.get("path") or ""
            if fp and os.path.isfile(fp):
                files.append(ent)
    if not files:
        listing = cri.list_reference_files()
        files = list(listing.get("files_on_disk") or [])

    pending = []
    for ent in files:
        fp = _norm_path(ent.get("path") or "")
        if not fp or fp in done:
            continue
        if fp in failed_paths and not reset:
            continue
        pending.append(ent)
    return pending


def close_document_no_save(app, doc=None) -> dict:
    """關閉文件且不儲存（用於批次匯入產生的 Untitled 設計）。"""
    target = doc
    if target is None:
        try:
            target = app.activeDocument
        except Exception:
            target = None
    if not target:
        return {"ok": True, "skipped": True}
    name = ""
    try:
        name = str(target.name or "")
    except Exception:
        pass
    try:
        target.close(False)
        return {"ok": True, "closed": name}
    except Exception as e:
        return {"ok": False, "error": str(e), "closed": name}


def _is_batch_import_doc_name(name: str) -> bool:
    n = str(name or "").strip()
    if not n:
        return False
    if n.startswith("Untitled") or n.startswith("未命名"):
        return True
    return False


def close_imported_untitled_documents(app, *, keep_active: bool = True) -> dict:
    """
    關閉批次 importToNewDocument 產生的 Untitled 分頁，避免記憶體與 UI 卡死。
    不關閉一般已命名專案檔（例如雲端同步件）。
    """
    closed = []
    errors = []
    active = None
    try:
        active = app.activeDocument
    except Exception:
        active = None
    try:
        docs = app.documents
        count = int(docs.count)
    except Exception:
        return {"ok": False, "closed": closed, "errors": ["no documents"]}
    for i in range(count - 1, -1, -1):
        try:
            doc = docs.item(i)
        except Exception:
            continue
        try:
            name = str(doc.name or "")
        except Exception:
            name = ""
        if not _is_batch_import_doc_name(name):
            continue
        if keep_active and active and doc == active:
            continue
        res = close_document_no_save(app, doc)
        if res.get("ok"):
            closed.append(name)
        else:
            errors.append(res.get("error") or name)
    if not keep_active and active:
        try:
            name = str(active.name or "")
            if _is_batch_import_doc_name(name):
                res = close_document_no_save(app, active)
                if res.get("ok"):
                    closed.append(name)
        except Exception:
            pass
    return {"ok": not errors, "closed": closed, "errors": errors}


def _active_doc_path(app) -> str:
    try:
        doc = app.activeDocument
        if not doc:
            return ""
        for attr in ("dataFile", "fullPath", "path"):
            try:
                val = getattr(doc, attr, None)
                if val:
                    return _norm_path(str(val))
            except Exception:
                pass
        return _norm_path(str(doc.name or ""))
    except Exception:
        return ""


def open_reference_file(app, file_path: str) -> dict:
    """
    開啟參考檔。本機 .f3d 須用 ImportManager（documents.open 僅支援雲端 DataFile）。
    """
    fp = os.path.abspath(file_path)
    if not os.path.isfile(fp):
        return {"ok": False, "error": "檔案不存在: {}".format(fp)}
    active = _active_doc_path(app)
    if active and active == _norm_path(fp):
        return {"ok": True, "opened": False, "path": fp, "message": "已是作用中文件"}
    ext = os.path.splitext(fp)[1].lower()
    try:
        if ext == ".f3d":
            imp_mgr = app.importManager
            opts = imp_mgr.createFusionArchiveImportOptions(fp)
            if not opts:
                return {"ok": False, "error": "無法建立 FusionArchiveImportOptions", "path": fp}
            doc = imp_mgr.importToNewDocument(opts)
            if doc:
                try:
                    app.activeDocument = doc
                except Exception:
                    pass
            return {"ok": True, "opened": True, "path": fp, "method": "importToNewDocument"}
        if ext == ".f3z":
            return {
                "ok": False,
                "error": ".f3z 需雲端 DataFile 或手動開啟；批次目前僅支援 .f3d",
                "path": fp,
            }
        return {"ok": False, "error": "不支援的副檔名: {}".format(ext), "path": fp}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": fp}


def run_batch_import_step(
    app,
    cam_obj,
    *,
    active_setup=None,
    material: str = "AL6061",
    max_files: int = 1,
    open_file: bool = True,
    scan_geometry: bool = True,
    scan_ctx: Optional[dict] = None,
    tmpl_lib=None,
    refresh_doc_refs: Optional[Callable[[], None]] = None,
    reset: bool = False,
    retry_failed: bool = False,
    close_after_import: bool = True,
) -> dict:
    """
    Process up to max_files reference entries from manifest (pending queue).
    """
    if max_files < 1:
        max_files = 1
    state = load_batch_state()
    if reset:
        state = {"version": STATE_VERSION, "completed": [], "failed": []}
        save_batch_state(state)
    if retry_failed:
        state["failed"] = []
        save_batch_state(state)

    pending = list_pending_files()
    total = len(pending) + len(state.get("completed") or [])
    if not pending:
        return {
            "success": True,
            "message": "批次匯入已完成，無待處理檔案",
            "data": {
                "pending_count": 0,
                "completed_count": len(state.get("completed") or []),
                "failed_count": len(state.get("failed") or []),
                "total_in_queue": total,
                "state_path": batch_state_path(),
            },
        }

    steps = []
    processed = 0
    while processed < max_files and pending:
        ent = pending.pop(0)
        fp = ent.get("path") or ""
        label = ent.get("archive_name") or os.path.basename(fp)
        step = {"path": fp, "label": label, "import": None, "open": None}

        cam_local = cam_obj
        if open_file and close_after_import:
            step["close_before"] = close_imported_untitled_documents(app, keep_active=False)

        if open_file:
            step["open"] = open_reference_file(app, fp)
            if not step["open"].get("ok"):
                state.setdefault("failed", []).append(
                    {"path": fp, "label": label, "error": step["open"].get("error", "open failed")}
                )
                save_batch_state(state)
                steps.append(step)
                processed += 1
                continue
            if callable(refresh_doc_refs):
                try:
                    refreshed = refresh_doc_refs()
                    if isinstance(refreshed, dict) and refreshed.get("cam_obj") is not None:
                        cam_local = refreshed.get("cam_obj")
                    elif refreshed is not None:
                        cam_local = refreshed
                except Exception as e:
                    step["refresh_error"] = str(e)

        if not cam_local:
            err = "無 CAM 產品（請確認參考檔含製造刀路）"
            state.setdefault("failed", []).append({"path": fp, "label": label, "error": err})
            save_batch_state(state)
            step["import"] = {"success": False, "error": err}
            steps.append(step)
            processed += 1
            continue

        try:
            setup_count = int(cam_local.setups.count)
        except Exception:
            setup_count = 0
        if setup_count < 1:
            err = "文件中無 CAM Setup"
            state.setdefault("failed", []).append({"path": fp, "label": label, "error": err})
            save_batch_state(state)
            step["import"] = {"success": False, "error": err}
            steps.append(step)
            processed += 1
            continue

        imp = cri.run_import_cam_from_active_document(
            cam_local,
            active_setup=active_setup,
            material=material,
            all_setups=True,
            write_db=True,
            save_snapshot=True,
            document_label=label,
            scan_geometry=scan_geometry,
            scan_ctx=scan_ctx,
            tmpl_lib=tmpl_lib,
        )
        step["import"] = imp
        if imp.get("success"):
            state.setdefault("completed", []).append(fp)
            state["last_success"] = {
                "path": fp,
                "label": label,
                "at": datetime.now(timezone.utc).isoformat(),
                "records": len((imp.get("data") or {}).get("records") or []),
            }
        else:
            state.setdefault("failed", []).append(
                {
                    "path": fp,
                    "label": label,
                    "error": imp.get("error", "import failed"),
                }
            )
        save_batch_state(state)
        if open_file and close_after_import:
            step["close_after"] = close_imported_untitled_documents(app, keep_active=False)
            if callable(refresh_doc_refs):
                try:
                    refresh_doc_refs()
                except Exception:
                    pass
        steps.append(step)
        processed += 1

    remaining = len(list_pending_files())
    return {
        "success": True,
        "message": "本步處理 {} 檔，剩餘 {} 檔".format(processed, remaining),
        "data": {
            "steps": steps,
            "processed_this_call": processed,
            "pending_count": remaining,
            "completed_count": len(state.get("completed") or []),
            "failed_count": len(state.get("failed") or []),
            "state_path": batch_state_path(),
        },
    }


def get_batch_import_status() -> dict:
    state = load_batch_state()
    pending = list_pending_files()
    return {
        "state_path": batch_state_path(),
        "pending_count": len(pending),
        "completed_count": len(state.get("completed") or []),
        "failed_count": len(state.get("failed") or []),
        "last_success": state.get("last_success"),
        "failed": state.get("failed") or [],
    }
