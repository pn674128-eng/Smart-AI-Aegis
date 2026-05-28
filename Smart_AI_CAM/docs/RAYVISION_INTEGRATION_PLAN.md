# 視線法 × 半自動加工選單 — 併入計劃

> **狀態**: Phase 1 完成 (2026-05-20)；**Phase 2 腦層**進行中

---

## Phase 1 — 眼（已完成）

- `vision/snapshot.py`, `modes.py`, `assist_sketch.py`
- `runtime_state.vision_snapshot`
- 外輪廓 + 槽草圖（WCS 俯視平面）
- execute 未改

詳見 `docs/VISION_CONTOUR_AND_SKETCH.md`。

---

## Phase 2 — 腦（AI 系統）

- 主檔：`docs/AI_SYSTEM_ARCHITECTURE.md`
- `recognizers/ai_brain.py`：合併掃描列 + `vision_snapshot`
- `get_ai_recommendations`：輸出 `decisions.slots`、`decisions.vision`
- 面板「一鍵 AI 智能加工優化」自動帶視線摘要

Phase 3（待核准）：建議寫回面板列模板，不覆寫 baseline。
