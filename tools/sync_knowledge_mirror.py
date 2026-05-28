# -*- coding: utf-8 -*-
"""同步 Smart AI CAM Fusion 學習庫 → Ollama knowledge/mirror。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge_service import sync_mirror_from_live


def main() -> int:
    meta = sync_mirror_from_live()
    print("sync_knowledge_mirror:", meta)
    if "feature_records.json" in meta.get("missing", []):
        print("WARN: no live feature_records — run after Fusion has recorded ops, or copy JSON manually.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
