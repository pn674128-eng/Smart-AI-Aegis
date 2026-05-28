# vision_snapshot v1（半自動 × 視線法）

## 用途

- 掃描後唯讀摘要，供面板「看見整體」與未來 AI（腦）建議層。
- 執行期：`runtime_state.vision_snapshot`（init JSON 僅帶 `vision` 摘要區塊）。

## 摘要欄位（init JSON `vision`）

| 欄位 | 說明 |
|------|------|
| `enabled`, `ok`, `reason`, `vision_mode`, `setup_name` | 開關與模式 |
| `counts` | `holes_scan`, `holes_list`, `slots`, `slots_active`, `contours` |
| `outer_perimeter_mm` | 俯視周長最大一列（雙台面時 ≠ 兩台加總） |
| `errors[]` | 掃描警告 |

## 完整快照

建構：`vision/snapshot.py` → `build_part_vision_snapshot(design, setup, holes_rows, slot_info_list)`。

| 區塊 | 來源 | 備註 |
|------|------|------|
| `hole_instances` | `last_hole_scan_rows_raw` | 與面板孔表同源 |
| `slots[]` | `slotInfoList` | 含 **`loop_edges`**（繪製用） |
| `contour_rows[]` | `get_machining_contour_faces_wcs` + `get_complete_outer_contour_edges` | 每輪廓面一列 |
| `topview_semantic` | 衍生摘要 | 見限制 |

## 輪廓掃描（2026-05-20）

- 不再只用 `get_top_face()` 單面。
- `_scan_contours(design, setup)` 使用多顶面 + 槽壁 + 完整外輪廓邊。
- Setup WCS 須與繪製草圖時相同。

## 驗證草圖

- `vision/assist_sketch.py` → `create_recognition_sketch_from_vision(snap, setup=...)`
- 草圖名：`SemiAuto_VisionSketch`
- 槽：優先 `loop_edges`；後備膠囊（非矩形）

## 開關

- `ENABLE_VISION_LAYER` in 主檔（預設 True；False = 併入前行為）

## 詳細操作

見 **`docs/VISION_CONTOUR_AND_SKETCH.md`**。
