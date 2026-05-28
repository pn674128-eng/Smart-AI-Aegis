# -*- coding: utf-8 -*-
"""
編程模式（使用層）— 與「學習層」分離。

學習層（持續）：辨識、特徵目錄、幾何語意、KnowledgeDB、編程概念累積 ——
  不因直覺式／思考式而關閉。

使用層（執行當下）：
  - intuitive  直覺式 = 有限制的編程（白名單 + 僅已定模板 + 資格閘門）
  - thinking   思考式 = 開放式編程（較大決策空間；長期產品線，逐步實作）
  - manual     面板手動執行（未走模式管線時預設標記）

詳見 docs/PROGRAMMING_MODES.md
"""

from __future__ import annotations

MODE_INTUITIVE = "intuitive"
MODE_THINKING = "thinking"
MODE_MANUAL = "manual"

ALL_MODES = (MODE_INTUITIVE, MODE_THINKING, MODE_MANUAL)

# 使用層：執行時決策空間
USAGE_TIER_RESTRICTED = "restricted"
USAGE_TIER_OPEN = "open"
USAGE_TIER_OPERATOR = "operator"


def usage_tier_for_mode(programming_mode: str) -> str:
    m = str(programming_mode or "").strip().lower()
    if m == MODE_THINKING:
        return USAGE_TIER_OPEN
    if m == MODE_INTUITIVE:
        return USAGE_TIER_RESTRICTED
    return USAGE_TIER_OPERATOR


def mode_display_name(programming_mode: str) -> str:
    m = str(programming_mode or "").strip().lower()
    if m == MODE_INTUITIVE:
        return "直覺式"
    if m == MODE_THINKING:
        return "思考式"
    if m == MODE_MANUAL:
        return "手動"
    return m or "—"
