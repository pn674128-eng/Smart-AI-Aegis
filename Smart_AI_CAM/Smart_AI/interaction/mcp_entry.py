"""
半自動加工選單 — MCP／外部 Fusion 腳本專用孔辨識入口（僅供校驗／對照，非正式 UI 資料管線）。

與指令面板／palette 使用同一套 `recognizers.hole_recognizer.scan_holes_by_ray`
（需作用中文件含 **設計** 與至少一個 **CAM Setup**）。

R 角欄位：`collect_pocket_corner_r_rows`／`scan_active_document_pocket_corner_r`（與孔列分離）。

Fusion「執行腳本」或 Cursor user-fusion 之 `fusion_mcp_execute`（featureType=script）
請在腳本內定義 `def run(_context: str):`，並呼叫本模組之 `scan_active_document_holes`。
傳入 `trace_through=True` 時，每列 JSON 會含 **throughTrace**（通／盲判定時間線）。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, List, Optional, Tuple

import adsk.cam
import adsk.core
import adsk.fusion


def addin_root() -> str:
    """本插件根目錄（含 recognizers/ 之上層）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure_addin_on_path() -> str:
    root = addin_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _pick_active_setup(cam: adsk.cam.CAM) -> Optional[adsk.cam.Setup]:
    if not cam or cam.setups.count < 1:
        return None
    for i in range(cam.setups.count):
        s = cam.setups.item(i)
        try:
            if s.isActive:
                return s
        except Exception:
            continue
    return cam.setups.item(0)


def scan_active_document_holes(
    ray_diameter_delta_mm: Optional[float] = None,
    runtime_state: Any = None,
    trace_through: bool = False,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """
    掃描作用中文件之孔列（與外掛主流程相同之 hole_recognizer）。

    trace_through=True 時，每列含 **throughTrace**（字串時間線），供校驗通／盲判定過程。

    回傳 (rows, error_code)。
    - rows：可 JSON 序列化之摘要（**不含** BRepFace 等 Fusion 物件）。
    - error_code：失敗時簡短代碼字串；成功時為 None。
    """
    ensure_addin_on_path()
    from Smart_AI.perception import hole_recognizer as hr

    app = adsk.core.Application.get()
    if not app:
        return None, "NO_APP"
    doc = app.activeDocument
    if not doc:
        return None, "NO_ACTIVE_DOCUMENT"
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if not des:
        return None, "NO_DESIGN"

    cam = None
    try:
        cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))
    except Exception:
        cam = None

    setup = _pick_active_setup(cam)
    if not setup:
        return None, "NO_CAM_SETUP"

    rdel = ray_diameter_delta_mm
    if runtime_state is not None and rdel is None:
        try:
            rdel = float(getattr(runtime_state, "ray_diameter_delta_mm", 0.0) or 0.0)
        except Exception:
            rdel = 0.0
    if rdel is None:
        rdel = 0.0

    try:
        raw = hr.scan_holes_by_ray(
            design=des,
            setup=setup,
            runtime_state=runtime_state,
            ray_diameter_delta_mm=rdel,
            trace_through=trace_through,
        )
    except TypeError:
        raw = hr.scan_holes_by_ray(
            design=des,
            setup=setup,
            ray_diameter_delta_mm=rdel,
        )

    out: List[dict] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        item = {
            "diameter_mm": r.get("diameter_mm"),
            "through": bool(r.get("through")),
            "depth_mm": r.get("depth_mm"),
            "dir": r.get("dir"),
            "source": r.get("source"),
            "is_countersink_large": bool(r.get("is_countersink_large")),
            "is_countersink_small": bool(r.get("is_countersink_small")),
            "face_count": r.get("face_count"),
            "count": r.get("count"),
            "needsReview": bool(r.get("needsReview")),
            "accessibilityHint": r.get("accessibilityHint"),
        }
        if trace_through:
            item["throughTrace"] = list(r.get("throughTrace") or [])
        out.append(item)
    return out, None


def scan_active_document_pocket_corner_r(
    runtime_state: Any = None,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """
    掃描作用中文件之「口袋槽垂直 R 角」列（與孔表分離）。

    回傳 (rows, error_code)；rows 可 JSON 序列化（**不含** faces）。
    """
    ensure_addin_on_path()
    from Smart_AI.perception import hole_recognizer as hr

    if not hasattr(hr, "collect_pocket_corner_r_rows"):
        return None, "NO_CORNER_R_API"

    app = adsk.core.Application.get()
    if not app:
        return None, "NO_APP"
    doc = app.activeDocument
    if not doc:
        return None, "NO_ACTIVE_DOCUMENT"
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if not des:
        return None, "NO_DESIGN"

    cam = None
    try:
        cam = adsk.cam.CAM.cast(doc.products.itemByProductType("CAMProductType"))
    except Exception:
        cam = None

    setup = _pick_active_setup(cam)
    if not setup:
        return None, "NO_CAM_SETUP"

    try:
        raw = hr.collect_pocket_corner_r_rows(design=des, setup=setup, visible_only=True)
    except Exception as e:
        return None, "SCAN_FAILED:%s" % (e,)

    out: List[dict] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "kind": r.get("kind"),
                "r_mm": r.get("r_mm"),
                "cylinder_diameter_mm": r.get("cylinder_diameter_mm"),
                "cylinder_area_ratio": r.get("cylinder_area_ratio"),
                "lx_mm": r.get("lx_mm"),
                "ly_mm": r.get("ly_mm"),
                "lz_mm": r.get("lz_mm"),
                "cx_wcs_mm": r.get("cx_wcs_mm"),
                "cy_wcs_mm": r.get("cy_wcs_mm"),
                "cz_wcs_mm": r.get("cz_wcs_mm"),
                "dir": r.get("dir"),
                "count": r.get("count"),
                "face_count": r.get("face_count"),
                "source": r.get("source"),
            }
        )
    return out, None


def hole_scan_json(rows: List[dict], indent: Optional[int] = None) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=indent)


def format_hole_scan_text(rows: List[dict]) -> str:
    """人類可讀之多行文字（供 print）。"""
    lines = ["HOLES %d" % len(rows)]
    for r in rows:
        lines.append(
            "D=%s through=%s depth_mm=%s dir=%s src=%s cbL=%s faces=%s count=%s"
            % (
                r.get("diameter_mm"),
                r.get("through"),
                r.get("depth_mm"),
                r.get("dir"),
                r.get("source"),
                r.get("is_countersink_large"),
                r.get("face_count"),
                r.get("count"),
            )
        )
        tr = r.get("throughTrace")
        if tr:
            for t in tr:
                lines.append("  | %s" % t)
    return "\n".join(lines)
