# 視線法 · 外輪廓與驗證草圖（公司接手主檔）

> **適用版號**：**V2.0347**  
> **最後整理**：2026-05-20  
> **狀態**：Phase 1 眼可驗證; execute 未改

回公司後請讀本檔。

---

## 1. 架構（眼/法/腦）

| 層 | 模組 |
|---|---|
| **眼** | `vision/` | `vision_snapshot` |
| **法** | `recognizers/` | baseline |
| **腦** | - | 建議層 |

`ENABLE_VISION_LAYER=False` 與併入前一致

---

## 3. 外輪廓 (2026-05-20)

槽分雙台面: 與版只有左邊有線

- `get_machining_top_faces_wcs`
- `get_groove_wall_faces_wcs`
- `get_machining_contour_faces_wcs`
- `get_complete_outer_contour_edges`

MCP `ZTA52729A91-M14A08`: 7 面輪, 41 邊輪邊

---

## 4. 槽草圖

`loop_edges` 優先; 膠囊後備; 禁止矩形

---

## 5. 流程

停用 -> 啟用 -> 重新掃描 -> 繪製草圖

---

## 6. 勿踩

PaletteActionContext; UTF-8; `setup`

---

## 7. 相關

- `docs/VISION_SNAPSHOT_v1.md`
- `docs/RAYVISION_INTEGRATION_PLAN.md`
- `docs/行為準則.md` section 11
- `docs/開發對話與變更.md` ## 2026-05-20
- `docs/CHECKLIST.md` section 13
