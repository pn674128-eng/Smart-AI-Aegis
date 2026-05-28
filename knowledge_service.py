# -*- coding: utf-8 -*-
"""
學習庫查詢：優先讀本機 JSON（live → mirror），Fusion MCP 僅補「當前文件」類動作。

合理用法：執行在 Smart AI CAM Fusion 寫入；主腦（Aegis）用此模組讀取。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from aegis_paths import FUSION_ADDIN_DIR, KNOWLEDGE_LIVE_DIR, KNOWLEDGE_MIRROR_DIR

_DB_SINGLETON = None
_DB_DATA_DIR: Optional[str] = None


def resolve_knowledge_data_dir() -> Optional[Path]:
    live = KNOWLEDGE_LIVE_DIR / "feature_records.json"
    mirror = KNOWLEDGE_MIRROR_DIR / "feature_records.json"
    if live.is_file():
        return KNOWLEDGE_LIVE_DIR
    if mirror.is_file():
        return KNOWLEDGE_MIRROR_DIR
    return None


def ensure_mirror() -> None:
    """若仅有 live、尚无 mirror，自动同步一次。"""
    if (KNOWLEDGE_LIVE_DIR / "feature_records.json").is_file():
        if not (KNOWLEDGE_MIRROR_DIR / "feature_records.json").is_file():
            sync_mirror_from_live()


def _get_db():
    global _DB_SINGLETON, _DB_DATA_DIR
    ensure_mirror()
    data_dir = resolve_knowledge_data_dir()
    if not data_dir:
        return None
    ds = str(data_dir)
    if _DB_SINGLETON is not None and _DB_DATA_DIR == ds:
        return _DB_SINGLETON
    if not FUSION_ADDIN_DIR.is_dir():
        return None
    root = str(FUSION_ADDIN_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    import Smart_AI.memory.knowledge_db as kd

    kd._knowledge_dir = lambda: ds  # type: ignore[attr-defined]
    _DB_SINGLETON = kd.get_db()
    _DB_DATA_DIR = ds
    return _DB_SINGLETON


def knowledge_stats_local() -> Optional[Dict[str, Any]]:
    db = _get_db()
    if not db:
        return None
    return {
        "success": True,
        "data": db.get_statistics(),
        "source": "knowledge_local",
        "data_dir": _DB_DATA_DIR,
    }


def knowledge_query_local(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db = _get_db()
    if not db:
        return None
    mat = params.get("material", "AL6061")
    ft = params.get("feature_type", "hole")
    geom = params.get("geometry") or {}
    best = db.query_best_template(ft, mat, geom)
    return {
        "success": True,
        "data": best or {},
        "source": "knowledge_local",
        "data_dir": _DB_DATA_DIR,
    }


def sync_mirror_from_live() -> Dict[str, Any]:
    """將 live 學習庫複製到 knowledge/mirror（備份供主腦離線讀）。"""
    names = ("feature_records.json", "pattern_index.json", "session_log.json")
    live = KNOWLEDGE_LIVE_DIR
    mirror = KNOWLEDGE_MIRROR_DIR
    copied = []
    missing = []
    for name in names:
        src = live / name
        if not src.is_file():
            if name != "session_log.json":
                missing.append(name)
            continue
        dst = mirror / name
        dst.write_bytes(src.read_bytes())
        copied.append(name)
    meta = {
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(live),
        "dest": str(mirror),
        "copied": copied,
        "missing": missing,
    }
    (mirror / "sync_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta
