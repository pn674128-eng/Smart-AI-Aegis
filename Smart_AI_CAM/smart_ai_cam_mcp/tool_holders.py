# -*- coding: utf-8 -*-
r"""
刀把 (Tool Holder) Profile - 用戶實機資訊
============================================
散件加工的「真實主軸轉速天花板」由刀把決定，不是機台。
用戶實機:
  ER 刀把 (預設大宗)  - 8000 RPM 軟上限, 可粗/一般精, 不可重切, 精度普通
  SK 刀把 (少部分)    - 24000 RPM 軟上限, 可粗, 不可重切, 精度高
  後拉式 (3 支)       - 無軟上限, 可重切 + 高精, 精度優秀

實務規則:
  - 平常加工不分刀把 → 預設 ER
  - 重切削零件 → 後拉式 (必要剛性)
  - 高尺寸精度零件 → SK 或後拉式

機台 (CNC_MACHINES, 在 Smart_AI/reasoning/physical_tool_engine.py) 只是「機台規格清單」,
用戶實務上不會用「材質-機台」強制配對。cam-helper 計算切削參數時不應該套機台維度。
"""

from typing import Any, Dict, List, Optional


HOLDER_PROFILES: Dict[str, Dict[str, Any]] = {
    "ER": {
        "name": "ER 刀把",
        "name_en": "ER Collet Chuck",
        "rpm_soft_max": 8000,
        "vendor_notes": "用戶大宗使用 (預設)",
        "use_cases": ["粗加工", "一般精加工"],
        "limits": ["不可重加工", "尺寸精度普通"],
        "rigidity": "中",
        "precision": "普通 (約 0.02 mm 級)",
        "comment": "ER 是用戶散件加工的預設刀把, 8000 RPM 是穩定使用軟上限",
    },
    "SK": {
        "name": "SK 刀把",
        "name_en": "SK Side-Lock Holder",
        "rpm_soft_max": 24000,
        "vendor_notes": "少部分使用 (高精/高速場合)",
        "use_cases": ["粗加工"],
        "limits": ["不可重加工"],
        "rigidity": "中高",
        "precision": "高 (尺寸精度佳)",
        "comment": "高轉速能力 24000 RPM, 適合高速加工但抗振性不如後拉式",
    },
    "pullback": {
        "name": "後拉式刀把",
        "name_en": "Pullback / Hydraulic / Heat-Shrink Holder",
        "rpm_soft_max": None,  # 無軟上限 (受機台主軸上限)
        "vendor_notes": "僅 3 支 (用於重切或高精件)",
        "use_cases": ["重加工", "精密加工"],
        "limits": [],
        "rigidity": "極高",
        "precision": "優秀 (μm 級)",
        "comment": "可同時兼顧重切剛性與微米級精度, 但只有 3 支只用在特殊零件",
    },
}


# 散件加工預設折扣 (用戶指定: 轉速 75 折 / 進給 5 折)
CONSERVATIVE_DEFAULTS = {
    "rpm_factor": 0.75,    # 散件轉速 = 廠商上限 × 0.75
    "feed_factor": 0.50,   # 散件進給 = 廠商上限 × 0.50
    "comment": "散件求穩: 廠商上限 V_max × 75 折 + FZ_max × 5 折, 套 holder 軟上限",
}

AGGRESSIVE_DEFAULTS = {
    "rpm_factor": 1.00,    # 量產 = 廠商上限不折
    "feed_factor": 1.00,
    "comment": "量產求快: 廠商上限 V_max + FZ_max, 不套 holder 軟上限",
}


def get_holder(holder_key: Optional[str]) -> Dict[str, Any]:
    """取得指定 holder 規格。預設回 ER。

    支援別名: er/Er/ER → ER, sk/SK → SK,
              pullback/熱套/後拉/液壓/hydraulic/heat_shrink → pullback
    """
    if not holder_key:
        return HOLDER_PROFILES["ER"]
    k = str(holder_key).strip().lower()
    if k in ("er",):
        return HOLDER_PROFILES["ER"]
    if k in ("sk",):
        return HOLDER_PROFILES["SK"]
    if k in ("pullback", "後拉", "後拉式", "熱套", "液壓", "hydraulic",
             "heat_shrink", "heatshrink", "shrink"):
        return HOLDER_PROFILES["pullback"]
    # 未知 holder 直接回原文 (容錯)
    return {**HOLDER_PROFILES["ER"], "warning": f"未知 holder '{holder_key}', 使用 ER 預設"}


def list_holders() -> List[Dict[str, Any]]:
    """列出 3 種 holder 規格, 給 lookup_tool_holders 用。"""
    out = []
    for key, p in HOLDER_PROFILES.items():
        rpm = p["rpm_soft_max"]
        out.append({
            "key": key,
            "name": p["name"],
            "rpm_soft_max": rpm if rpm is not None else "無軟上限",
            "use_cases": p["use_cases"],
            "limits": p["limits"],
            "rigidity": p["rigidity"],
            "precision": p["precision"],
            "vendor_notes": p["vendor_notes"],
            "comment": p["comment"],
        })
    return out


def dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP entry: query_tool_holders。

    params:
      {"mode": "list"}                  → 列 3 種 holder (預設)
      {"mode": "get", "holder": "ER"}   → 單一 holder 詳細
    """
    mode = (params.get("mode") or "list").lower()
    if mode == "list":
        return {
            "success": True,
            "data": {
                "holders": list_holders(),
                "defaults": {
                    "conservative_mode": CONSERVATIVE_DEFAULTS,
                    "aggressive_mode": AGGRESSIVE_DEFAULTS,
                    "default_holder": "ER",
                    "default_mode": "conservative",
                },
                "policy": [
                    "平常加工不分刀把 → 預設 ER",
                    "重切削零件 → 後拉式 (pullback)",
                    "高尺寸精度零件 → SK 或後拉式",
                ],
            },
        }
    elif mode == "get":
        h = params.get("holder") or "ER"
        return {"success": True, "data": get_holder(h)}
    else:
        return {"success": False, "error": f"未知 mode: {mode}",
                "valid_modes": ["list", "get"]}
