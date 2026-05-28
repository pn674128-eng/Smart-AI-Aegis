# -*- coding: utf-8 -*-
"""從 V8.702 hole_type 解析結果生成 hole_rules.yaml / .json（僅資料，不含 DLL）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "hole_cam"
PARSED = DATA / "_xk872_parsed.json"
OPER_MAP_YAML = DATA / "xk_oper_map.yaml"
OUT_YAML = DATA / "hole_rules.yaml"
OUT_JSON = DATA / "hole_rules.json"

# xk_index → 繁中名稱（對照 Data_Simpl_chinese / hole_type 順序，供 id 與 name_zh）
XK_NAMES: Dict[int, str] = {
    1: "模板",
    2: "Slot",
    3: "螺纹孔",
    4: "小锥底盲孔",
    5: "大锥底盲孔",
    6: "小平底盲孔",
    7: "大平底盲孔",
    8: "小倒角锥底盲孔",
    9: "大倒角锥底盲孔",
    10: "小倒角平底盲孔",
    11: "大倒角平底盲孔",
    12: "小通镗孔",
    13: "大通镗孔",
    14: "小倒角通镗孔",
    15: "大倒角通镗孔",
    16: "沉头钻孔",
    17: "小盲锥孔",
    18: "大盲锥孔",
    19: "小倒角盲锥孔",
    20: "大倒角盲锥孔",
    21: "盲平面",
    22: "大盲平面",
    23: "倒角盲平面",
    24: "大倒角盲平面",
    25: "通孔",
    26: "大通孔",
    27: "倒角通孔",
    28: "大倒角通孔",
    29: "沉头孔",
    30: "单沉头",
    31: "双沉头",
    32: "沉头盲孔",
    33: "腰型孔",
    34: "倒角腰型孔",
    35: "腰型沉头盲孔",
    36: "平面寻边",
    37: "倒角寻边",
    38: "型腔加工",
    39: "斜孔",
    40: "铣基准角",
    41: "打基准点",
    42: "铣外壁",
    43: "铣内壁",
    44: "层腔铣",
    45: "开粗腔",
    46: "半粗腔",
    47: "开放槽",
    48: "通槽",
    49: "封闭槽",
    50: "封闭型腔",
    51: "开放型腔",
    52: "其他槽",
    53: "倒角",
    54: "曲面",
    55: "多沉头",
}


def _load_oper_map() -> Dict[int, str]:
    from smart_ai_nx.yaml_util import safe_load_file

    path = OPER_MAP_YAML if OPER_MAP_YAML.is_file() else OPER_MAP_YAML.with_suffix(".json")
    raw = safe_load_file(path) or {}
    m = raw.get("map") or {}
    return {int(k): str(v) for k, v in m.items()}


def _slug(name: str, idx: int) -> str:
    if idx == 2 or (name or "").lower() == "slot":
        return "xk_slot_std"
    return f"xk_{idx:03d}"


def _ft(ft: Optional[int]) -> Optional[str]:
    if ft == 0:
        return "hole"
    if ft == 1:
        return "slot"
    return None


def _through_match(th: Optional[int]) -> Dict[str, Any]:
    """星空 THROUGH: 0=盲 1=通 2=不限"""
    if th == 0:
        return {"through": False}
    if th == 1:
        return {"through": True}
    return {}


def _match_specificity(match: Dict[str, Any]) -> int:
    """條件越多越優先（數字越小）。"""
    keys = set(match.keys()) - {"feature_type"}
    score = len(keys) * 5
    if "color_id" in keys:
        score += 8
    if "countersink" in keys:
        score += 6
    if "thread" in keys:
        score += 4
    if "slot_subtype" in keys:
        score += 6
    return score


def _priority_for(row: Dict[str, Any], match: Dict[str, Any]) -> int:
    ops = row.get("cam_oper_ids") or []
    ft = row.get("feature_type")
    th = row.get("through")
    n = len(ops)
    spec = _match_specificity(match)
    if spec == 0:
        return 80
    base = 10 + spec
    if ft == 1:
        return 35 + int(row.get("slot_type") or 0) + spec
    if 4 in ops:
        return 4
    if row.get("slope") not in (0, None):
        return 7 + spec
    if 18 in ops or 19 in ops or 23 in ops:
        return 6 + spec
    if th == 1 and n >= 3:
        return 12 + spec
    if th == 0 and n >= 3:
        return 13 + spec
    if th == 0:
        return 22 + spec
    if th == 1:
        return 18 + spec
    return 25 + spec


def _extra_match(row: Dict[str, Any], name: str, idx: int) -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    if row.get("slope") not in (0, None):
        m["angled"] = True
    if row.get("color_id") is not None:
        m["color_id"] = int(row["color_id"])
    st = row.get("slot_type")
    if st not in (0, None) and row.get("feature_type") == 1:
        m["slot_subtype"] = int(st)
    ops = set(row.get("cam_oper_ids") or [])
    if ops & {18, 19, 23, 66} and idx not in (25, 26, 27, 28):
        m["countersink"] = True
    if 4 in ops or "螺纹" in name:
        m["thread"] = True
    if 2 in ops and 1 in ops:
        m["tolerance_ream"] = True
    if "腰型" in name or 72 in ops:
        m["slotted"] = True
    if row.get("feature_type") == 1 and "型腔" in name:
        m["feature_type"] = "pocket"
    if row.get("feature_type") == 1 and "曲面" in name:
        m["feature_type"] = "surface_shoe"
    return m


def build_rules(rows: List[Dict[str, Any]], oper_map: Dict[int, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_sig: set = set()

    for row in rows:
        idx = int(row.get("xk_index", 0))
        if idx <= 1:
            continue
        name = XK_NAMES.get(idx) or row.get("name_zh") or f"規則{idx}"
        ft = _ft(row.get("feature_type"))
        if not ft:
            continue
        op_ids = row.get("cam_oper_ids") or []
        operations = []
        for oid in op_ids:
            key = oper_map.get(int(oid))
            if key and key not in operations:
                operations.append(key)
        if not operations:
            continue
        match: Dict[str, Any] = {"feature_type": ft}
        match.update(_through_match(row.get("through")))
        match.update(_extra_match(row, name, idx))
        sig = (ft, tuple(match.items()), tuple(operations))
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        rid = _slug(name, idx)
        out.append({
            "id": rid,
            "name_zh": name,
            "priority": _priority_for(row, match),
            "xk_index": idx,
            "match": match,
            "operations": operations,
        })

    out.sort(key=lambda r: (int(r.get("priority", 99)), int(r.get("xk_index", 0))))
    # 保留手寫高優先規則 + V8.702 匯入 + fallback
    manual = [
        {
            "id": "hole_tap",
            "name_zh": "螺紋孔",
            "priority": 4,
            "match": {"feature_type": "hole", "thread": True},
            "operations": ["spot_center", "drill_peck_g83", "tap_rigid"],
        },
        {
            "id": "hole_ream_h7",
            "name_zh": "精密孔鉸",
            "priority": 5,
            "match": {
                "feature_type": "hole",
                "tolerance_ream": True,
                "thread": False,
                "diameter_mm": {"min": 1, "max": 40},
            },
            "operations": ["spot_center", "drill_peck_g83", "drill_ream"],
        },
        {
            "id": "hole_countersink_std",
            "name_zh": "沉頭孔標準",
            "priority": 20,
            "match": {
                "feature_type": "hole",
                "countersink": True,
            },
            "operations": [
                "spot_center",
                "drill_peck_g83",
                "countersink_contour",
            ],
        },
        {
            "id": "through_hole_std",
            "name_zh": "通孔標準",
            "priority": 30,
            "match": {
                "feature_type": "hole",
                "through": True,
                "thread": False,
                "tolerance_ream": False,
                "countersink": False,
                "diameter_mm": {"min": 0.5, "max": 60},
            },
            "operations": ["spot_center", "drill_peck_g83"],
        },
        {
            "id": "blind_hole_std",
            "name_zh": "盲孔標準",
            "priority": 31,
            "match": {
                "feature_type": "hole",
                "through": False,
                "thread": False,
                "tolerance_ream": False,
                "countersink": False,
                "diameter_mm": {"min": 0.5, "max": 60},
            },
            "operations": ["spot_center", "drill_peck_g83"],
        },
        {
            "id": "slot_open",
            "name_zh": "開放槽",
            "priority": 45,
            "match": {"feature_type": "slot"},
            "operations": ["slot_rough", "slot_2d_finish"],
        },
        {
            "id": "face_top",
            "name_zh": "頂面平面",
            "priority": 50,
            "match": {"feature_type": "face_plane"},
            "operations": ["face_rough", "face_finish"],
        },
    ]
    by_id = {r["id"]: r for r in manual}
    for r in out:
        if r["id"] not in by_id:
            by_id[r["id"]] = r
    merged = sorted(by_id.values(), key=lambda r: int(r.get("priority", 9999)))
    merged.append({
        "id": "fallback",
        "name_zh": "未匹配",
        "priority": 9999,
        "match": {},
        "operations": ["manual_review"],
    })
    return merged


def main() -> int:
    sys.path.insert(0, str(ROOT.parent))
    rows = json.loads(PARSED.read_text(encoding="utf-8"))
    oper_map = _load_oper_map()
    rules = build_rules(rows, oper_map)
    doc = {"version": 2, "source": "V8.702 hole_type.txt + manual", "rules": rules}
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import yaml  # type: ignore

        OUT_YAML.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    except ImportError:
        print("PyYAML missing; wrote JSON only", OUT_JSON)
    else:
        print(f"wrote {OUT_YAML} ({len(rules)} rules)")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
