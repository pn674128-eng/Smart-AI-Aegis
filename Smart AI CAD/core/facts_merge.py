# -*- coding: utf-8 -*-
"""合併 Core 與 Bridge 產出的 quote_facts。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def merge_quote_facts(
    primary: Dict[str, Any],
    *others: Dict[str, Any],
) -> Dict[str, Any]:
    """
    primary 通常為 3D / freecad_core；others 為 2D bridge 等。
  回傳新 dict，不修改輸入。
    """
    out = deepcopy(primary)
    out.setdefault("schema_version", "0.1")
    out.setdefault("conflicts", [])
    caps: List[str] = list(out.get("capabilities") or [])
    sources: List[str] = [str(out.get("source_id", "unknown"))]

    for extra in others:
        if not extra:
            continue
        sid = str(extra.get("source_id", "bridge"))
        sources.append(sid)
        for c in extra.get("capabilities") or []:
            if c not in caps:
                caps.append(c)

        # 2D 區塊：以 bridge 補齊
        if extra.get("2d"):
            out["2d"] = {**(out.get("2d") or {}), **extra["2d"]}

        # 文字註記：合併去重
        notes = list(out.get("drawing_notes") or [])
        for n in extra.get("drawing_notes") or []:
            if n and n not in notes:
                notes.append(n)
        if notes:
            out["drawing_notes"] = notes

        # 材質：若 primary 無、extra 有則採用
        if not out.get("material") and extra.get("material"):
            out["material"] = extra["material"]
        elif out.get("material") and extra.get("material") and out["material"] != extra["material"]:
            out["conflicts"].append(
                {"field": "material", "values": [out["material"], extra["material"], sid]}
            )

        # 數量：取較大者並記 conflict（估價常用較保守）
        if extra.get("qty"):
            pq, eq = int(out.get("qty") or 1), int(extra["qty"])
            if pq != eq:
                out["conflicts"].append({"field": "qty", "values": [pq, eq, sid]})
            out["qty"] = max(pq, eq)

    out["capabilities"] = caps
    out["merged_sources"] = sources
    return out
