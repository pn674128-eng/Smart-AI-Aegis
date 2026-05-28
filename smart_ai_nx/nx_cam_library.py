# -*- coding: utf-8 -*-
"""Read NX 1953 company cut_methods / material hints (ASCII library)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import NX_CAM_LIBRARY_ASCII


def list_cut_method_names(limit: int = 80) -> List[str]:
    path = NX_CAM_LIBRARY_ASCII / "cut_methods.dat"
    if not path.is_file():
        return []
    names: List[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # NAME field lines often quoted in dat files
        m = re.search(r'"([^"]{2,60})"', line)
        if m and "HSM" in m.group(1).upper() or "ROUGH" in m.group(1).upper():
            names.append(m.group(1))
        if len(names) >= limit:
            break
    return names


def library_status() -> Dict[str, Any]:
    ascii_dir = NX_CAM_LIBRARY_ASCII
    files = ["cut_methods.dat", "part_materials.dat", "machining_data.dat", "feeds_speeds.dat"]
    present = {f: (ascii_dir / f).is_file() for f in files}
    return {
        "ascii_dir": str(ascii_dir),
        "files": present,
        "ok": all(present.values()),
        "sample_cut_methods": list_cut_method_names(15),
    }


def recommend_cut_method(
    material_profile: str,
    *,
    stage: str = "rough",
    tool_diameter_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """Map material_profile + stage to company library cut method name."""
    from .material_profiles import get_profile

    prof = get_profile(material_profile)
    defaults = prof.get("cut_method_defaults") or {}
    method = defaults.get(stage, defaults.get("rough", "HSM_ROUGH"))
    return {
        "material_profile": material_profile,
        "nx_part_material_hint": prof.get("nx_part_material_hint"),
        "resolver_material": prof.get("resolver_material"),
        "cut_method": method,
        "tool_diameter_mm": tool_diameter_mm,
        "library_path": str(NX_CAM_LIBRARY_ASCII),
        "note": "在 NX 工序導覽器雙擊加工方法 → 設置加工資料；完整查表待接 NX Open",
    }
