# -*- coding: utf-8 -*-
"""Load YAML with PyYAML; optional JSON sidecar if PyYAML missing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def safe_load_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        pass
    json_path = path.with_suffix(".json")
    if json_path.is_file():
        return json.loads(json_path.read_text(encoding="utf-8"))
    raise RuntimeError(
        f"Cannot load {path.name}: install PyYAML (pip install pyyaml) "
        f"or add {json_path.name}"
    )
