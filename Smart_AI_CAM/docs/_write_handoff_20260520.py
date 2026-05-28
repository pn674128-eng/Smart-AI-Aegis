# -*- coding: utf-8 -*-
"""One-shot: refresh docs for 2026-05-20 vision handoff. Run: python _write_handoff_20260520.py"""
from pathlib import Path

DOCS = Path(__file__).resolve().parent


def w(name: str, text: str) -> None:
    p = DOCS / name
    p.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", name, len(text))


VISION_CONTOUR = r"""# 視線法 · 外輪廓與驗證草圖（公司接手主檔）

> **適用版號**：顯示 **V2.0315**（凍結；文件更新不遞增版號）  
> **最後整理**：2026-05-20  
> **狀態**：Phase 1 視線法「眼」已可日常驗證；孔憲法／execute **未改**

本檔給**回公司後第一週**接手的開發者：說明「只有左邊有線」已修、完整外輪廓與槽孔方框已修、如何 MCP 驗證、勿踩的坑。

---

## 1. 架構（眼／法／腦）

| 層 | 模組 | 職責 |
|----|------|------|
| **眼** | `vision/` | 掃描後唯讀 `runtime_state.vision_snapshot` |
| **法** | `recognizers/` | 孔／槽／輪廓辨識（既有，勿破壞 baseline） |
| **腦** | （未做） | 僅建議、不寫 CAM／不覆寫 execute |

主開關：`半自動加工選單【UI穩定版】.py` → `ENABLE_VISION_LAYER = True`（False 時與併入前一致）。

---

## 2. 關鍵檔案對照

| 路徑 | 用途 |
|------|------|
| `vision/snapshot.py` | `build_part_vision_snapshot()`、`_scan_contours(design, setup)` |
| `vision/assist_sketch.py` | `create_recognition_sketch_from_vision()` → 草圖 `SemiAuto_VisionSketch` |
| `vision/modes.py` | `FAST_2D` 等模式正規化 |
| `recognizers/contour_recognizer.py` | 多頂面／完整外輪廓／槽壁 |
| `半自動加工選單【UI穩定版】.py` | `_refresh_vision_snapshot()`、`_handle_draw_vision_sketch_palette()` |
| `ui/palette_controller.py` | `draw_recognition_sketch` 備援（須傳 `setup`） |
| `palette.html` | 「看見整體」「繪製視線法草圖」 |

---

## 3. 外輪廓：問題與現行算法

### 3.1 現象（槽型雙台面件）

- 同一 body、中間有槽 → **頂面被切成兩塊**（左大台、右小台）。
- 舊版只取 **`get_top_face()`（面積最大的一塊）** → 草圖**只有左側**紫色外框（使用者：「只有左邊有線」）。

### 3.2 現行做法（三層）

1. **`get_machining_top_faces_wcs()`** — Setup WCS 下，Z+ 方向、同一頂 Z 帶內**所有**向上平面（面積 ≥ 門檻）。
2. **`get_groove_wall_faces_wcs()`** — 頂 Z 帶內、面積 ≥ 2 cm²、與台面邊界相接的**垂直平面**（槽壁）。
3. **`get_machining_contour_faces_wcs()`** — 上二者合併 → 掃描與繪製共用。
4. **`get_complete_outer_contour_edges(face)`** — 每面：`outer_loop` **加上** 分類為 `outer`／`special` 但未進 loop 的邊。
5. **繪製** — `_draw_vision_contours(..., setup=setup)`，全域 `drawn_tokens` 去重；**必須傳入與掃描相同之 Setup**。

### 3.3 MCP 參考數字（`ZTA52729A91-M14A08`）

| 指標 | 舊（單頂面 loop） | 新（完整） |
|------|-------------------|------------|
| 頂面數 | 1（實際 2） | 2 |
| 輪廓面數（含槽壁） | 2 | **7**（2 台 + 5 壁） |
| 外輪廓邊（去重） | 18 | **41** |
| `contour_outer` 繪製 | 18 | **41** |

平面件（單頂面）應維持約 **8** 段外框，勿退化。

---

## 4. 槽孔：方框問題與現行算法

### 4.1 現象

長條槽（跑道孔）被畫成**矩形四角方框**（`_draw_slot_rects` 四條直線）。

### 4.2 現行做法

1. **優先**：`loop_edges` → `_draw_contour_edge_list` 投影真實 BRep 邊。  
2. **後備**：**膠囊形** `_draw_slot_capsule()`（兩半圓弧 + 兩直邊），**不再畫矩形**。

`snapshot._slots_from_slot_info_list` 已帶入 `loop_edges`（掃描後才有）。

---

## 5. 操作流程（Fusion 內）

1. 開啟含 CAM Setup 之設計。  
2. **停用 → 啟用**外掛（載入新模組）。  
3. 刪除 add-in 下 `__pycache__`（若曾 UTF-16 損壞）。  
4. 面板 **重新掃描**。  
5. **繪製視線法草圖** → 檢查 `SemiAuto_VisionSketch`。  
6. 預期：左右外框、槽緣、槽為跑道形；孔為圓。

若提示無 `hole_instances`：**先掃描**，勿只按繪製。

---

## 6. Palette／熱重載勿踩

| 規則 | 原因 |
|------|------|
| **勿**擴充 `PaletteActionContext` 新欄位 | Fusion 熱重載保留舊 dataclass → `TypeError` |
| `refresh_vision_snapshot_fn` 掛在 `runtime_state` | 避免 context 傳遞膨脹 |
| `draw_recognition_sketch` 在 `notify` **先**處理 | 見主檔 `_handle_draw_vision_sketch_palette()` |
| 繪製必傳 **`setup=camSetup`** | WCS 與掃描一致 |

---

## 7. 編碼（Windows 必讀）

- 所有 `vision/*.py`、`recognizers/contour_recognizer.py` 須為 **UTF-8**（勿 UTF-16）。  
- Fusion 報 `null bytes` / `SyntaxError`：轉 UTF-8 並清 `__pycache__`。  
- MCP 腳本**勿** `open()` 中文路徑檔；用 `import` 模組。

---

## 8. 已知限制

- **`topview_semantic.outer_perimeter_mm`**：仍取周長最大的一列；雙台面時摘要≠兩台加總；**草圖已正確**。  
- **腦／AI 建議層**：未實作。  
- **版號**：V2.0315 凍結期間勿擅自遞增 `ADDIN_VERSION`。

---

## 9. 建議後續

1. 平面件 `ZTA52729S11-S01A01NC` 回歸（單頂面 ~8 段）。  
2. MCP 槽／輪廓檢查納入 `docs/CHECKLIST.md` §13。  
3. 「腦」：只讀 snapshot 輸出建議 JSON。

---

## 10. 相關文件

| 檔案 | 內容 |
|------|------|
| `docs/VISION_SNAPSHOT_v1.md` | 快照 JSON 契約 |
| `docs/RAYVISION_INTEGRATION_PLAN.md` | 併入計畫 |
| `docs/行為準則.md` §11 | 視線法協作約束 |
| `docs/INTEGRATED_HANDOFF.md` | §2（2026-05-20） |
| `docs/開發對話與變更.md` | ## 2026-05-20 |
"""

VISION_SNAPSHOT = r"""# vision_snapshot v1（半自動 × 視線法）

## 用途

- 掃描後唯讀摘要，供面板「看見整體」與未來 AI（腦）建議層。
- 執行期：`runtime_state.vision_snapshot`（init JSON 亦帶 `vision` 區塊）。

## 摘要欄位（init JSON `vision`）

| 欄位 | 說明 |
|------|------|
| `enabled`, `ok`, `reason`, `vision_mode`, `setup_name` | 開關與模式 |
| `counts` | `holes_scan`, `holes_list`, `slots`, `slots_active`, `contours` |
| `outer_perimeter_mm` | 俯視最大周長一列（雙台面時≠兩台加總） |
| `errors[]` | 掃描警告 |

## 完整快照（記憶體／除錯）

建構：`vision/snapshot.py` → `build_part_vision_snapshot(design, setup, holes_rows, slot_info_list)`。

| 區塊 | 來源 | 備註 |
|------|------|------|
| `hole_instances` | `last_hole_scan_rows_raw` | 與面板孔表同源 |
| `slots[]` | `slotInfoList` | 含 **`loop_edges`**（繪製用） |
| `contour_rows[]` | `get_machining_contour_faces_wcs` + `get_complete_outer_contour_edges` | 每輪廓面一列 |
| `topview_semantic` | 衍生摘要 | `outer_perimeter_mm` 見限制 |

## 輪廓掃描（2026-05-20）

- 不再只用 `get_top_face()` 單面。
- `_scan_contours(design, setup)` 使用 **`get_machining_contour_faces_wcs`** 與 **`get_complete_outer_contour_edges`**。
- Setup WCS 須與繪製草圖時相同。

## 驗證草圖

- `vision/assist_sketch.py` → `create_recognition_sketch_from_vision(snap, setup=...)`
- 草圖名：`SemiAuto_VisionSketch`
- 圖層語意：`contour_outer`、孔圓、槽（`loop_edges` 或膠囊）

## 開關

- `ENABLE_VISION_LAYER` in 主檔（預設 True；False = 併入前行為）

## 詳細操作

見 **`docs/VISION_CONTOUR_AND_SKETCH.md`**。
"""

RAYVISION = r"""# 視線法 × 半自動加工選單 — 併入計畫

> **狀態**：**Phase 1 已完成**（2026-05-20 驗收：多台面外輪廓、槽膠囊、驗證草圖）  
> **目的**：將 RayVisionMain（眼）併入半自動加工選單（法），預留腦層只讀 `vision_snapshot`。  
> **硬約束**：**不修改** 行為準則 §3.1／§8.4 孔加工契約；視線法唯讀、可關閉。

---

## 1. 三層定位

| 層 | 模組 | 職責 |
|----|------|------|
| **眼** | `vision/`（自 RayVisionMain 抽出） | 俯視／孔／槽／輪廓 → `vision_snapshot` |
| **法** | 主檔 + `recognizers/` + execute | 辨識、合併、模板、刀路（既有） |
| **腦** | 未來 `ai/`（規劃） | 讀 snapshot 建議；**不**寫 execute |

原則：**掃描一次、面板以半自動為準**；視線法不重新定義孔／槽／沉頭語義。

---

## 2. 目標（原計畫 vs 現況）

| 項目 | 狀態 |
|------|------|
| 抽出 `vision/snapshot.py`、`modes.py` | ✅ |
| `assist_sketch.py` 驗證草圖 | ✅（2026-05-20 多顶面+槽壁+膠囊） |
| `runtime_state.vision_snapshot` | ✅ |
| 面板「看見整體」init JSON | ✅ |
| 不改 `mergeHoleListByDia`、`_isThrough`、`holeFaces` | ✅ |
| 自動改 holeInfoList / execute | ❌ 不做 |
| LLM 建議層 | ❌ 未做 |

---

## 3. 目錄結構（現行）

```
半自動加工選單【UI穩定版】/
├── recognizers/          # 法：含 contour_recognizer 多顶面 API
├── vision/               # 眼
│   ├── snapshot.py
│   ├── modes.py
│   └── assist_sketch.py
├── state/runtime_state.py
├── palette.html
└── docs/
    ├── RAYVISION_INTEGRATION_PLAN.md  # 本檔
    ├── VISION_SNAPSHOT_v1.md
    └── VISION_CONTOUR_AND_SKETCH.md   # 公司接手主檔
```

---

## 4. 資料流（Phase 1）

```
重新掃描 / requestInit
  → _rebuildHoleListForPalette
      → scan 孔 / 槽 / pocket R
      → _refresh_vision_snapshot()  → runtime_state.vision_snapshot
      → mergeHoleListByDia
  → init JSON 帶 vision 摘要

使用者按「繪製視線法草圖」
  → notify 先處理 draw_recognition_sketch
  → create_recognition_sketch_from_vision(snap, setup=camSetup)
```

---

## 5. 2026-05-20 技術增量（摘要）

### 外輪廓

- `get_machining_top_faces_wcs` — 全部顶面（非單一 max area）
- `get_groove_wall_faces_wcs` — 槽壁垂直面
- `get_complete_outer_contour_edges` — loop + 遺漏 outer 邊
- 修復：槽型件「只有左邊有線」

### 槽繪製

- 優先 `loop_edges`；後備 `_draw_slot_capsule`（非矩形）

### 接手注意

- UTF-8 源碼；reload add-in；`ENABLE_VISION_LAYER=False` 回歸基線
- 詳見 **`docs/VISION_CONTOUR_AND_SKETCH.md`**

---

## 6. Phase 2+（規劃，未實作）

- 腦層：只讀 snapshot → 建議 JSON
- `topview_semantic` 雙台面周長加總（可選）
- 與 FAST_2D 投影工法更深整合（不取代 §8.5 REF）
"""

CHANGELOG_20260520 = r"""## 2026-05-20

**交叉索引**：`docs/VISION_CONTOUR_AND_SKETCH.md`（**公司接手主檔**）、`docs/VISION_SNAPSHOT_v1.md`、`docs/RAYVISION_INTEGRATION_PLAN.md`、`docs/行為準則.md` §11、`docs/CHECKLIST.md` §13、`docs/INTEGRATED_HANDOFF.md` §2、`docs/VERSIONING.md` §6.2／§7、`docs/AI_閱讀順序.md`。

**版號**：維持 **V2.0315 凍結**；本日為功能修正 + 文件，**不**遞增 `ADDIN_VERSION`（見 `docs/版本紀錄.md` V2.0315）。

---

### 1. 問題與修正

| 使用者回報 | 根因 | 修正 |
|------------|------|------|
| 只有左邊有線 | 槽分雙台面，只用 `get_top_face()` | `get_machining_top_faces_wcs` + 槽壁 + `get_complete_outer_contour_edges` |
| 要完整外輪廓 | 僅 `outer_loop`；缺 outer 邊與槽壁 | 同上 + 繪製全域去重 |
| 橢圓孔有方框 | `_draw_slot_rects` 畫矩形 | `loop_edges` 優先；後備 `_draw_slot_capsule` |
| 其餘正確 | — | 孔／右側特徵未動 execute 契約 |

### 2. 程式檔案

| 檔案 | 變更 |
|------|------|
| `recognizers/contour_recognizer.py` | 多顶面、槽壁、完整外輪廓邊 API |
| `vision/snapshot.py` | `_scan_contours(design, setup)`；槽帶 `loop_edges` |
| `vision/assist_sketch.py` | 完整輪廓繪製；槽膠囊；須 `setup` |
| `半自動加工選單【UI穩定版】.py` | `_refresh_vision_snapshot`；`draw_recognition_sketch` 早處理 |
| `ui/palette_controller.py` | 繪製傳 `setup` |

### 3. MCP 驗收（`ZTA52729A91-M14A08`）

- 輪廓面 7（2 顶 + 5 壁）；外輪廓邊 41；`contour_outer` 41。
- 孔掃描 17 instances；槽非矩形。

### 4. 文件（本日）

- **新建／重寫 UTF-8**：`VISION_CONTOUR_AND_SKETCH.md`、`VISION_SNAPSHOT_v1.md`、`RAYVISION_INTEGRATION_PLAN.md`
- **更新**：`INTEGRATED_HANDOFF`、`AI_閱讀順序`、`行為準則` §11、`CHECKLIST` §13、`VERSIONING` §6.2／§7

### 5. 接手必做

1. 外掛 **停用→啟用**；清 `__pycache__`。  
2. 確認 `vision/*.py` 為 UTF-8。  
3. 讀 **`docs/VISION_CONTOUR_AND_SKETCH.md`** 再改碼。  
4. `ENABLE_VISION_LAYER=False` 驗證孔 baseline 未退化。

---

"""


def patch_integrated_handoff() -> None:
    p = DOCS / "INTEGRATED_HANDOFF.md"
    t = p.read_text(encoding="utf-8")
    # table row in section 0
    row = (
        "| **`docs/VISION_CONTOUR_AND_SKETCH.md`** | "
        "**2026-05-20 視線法接手主檔**：多台面外輪廓、槽膠囊草圖、MCP、UTF-8、勿擴 `PaletteActionContext`。 |"
    )
    if "VISION_CONTOUR_AND_SKETCH" not in t:
        t = t.replace(
            "| **`docs/BASELINE_ALIGNMENT.md`** | baseline-first 與變更節奏。 |",
            "| **`docs/BASELINE_ALIGNMENT.md`** | baseline-first 與變更節奏。 |\n" + row,
        )
    block = r"""
### 2026-05-20（視線法 Phase 1 · 外輪廓與驗證草圖）

- **接手主檔**：`docs/VISION_CONTOUR_AND_SKETCH.md`（讀此檔再改 `vision/`、`contour_recognizer.py`）。
- **問題已修**：槽型雙台面「只有左邊有線」；槽驗證草圖矩形方框 → `loop_edges` 或膠囊。
- **API**：`get_machining_contour_faces_wcs`、`get_complete_outer_contour_edges`；掃描與 `assist_sketch` 共用。
- **流程**：重新掃描 → `_refresh_vision_snapshot()` → 繪製 `SemiAuto_VisionSketch`（須先掃描才有 `hole_instances`）。
- **勿踩**：不擴 `PaletteActionContext`；`ENABLE_VISION_LAYER=False` 回歸；**V2.0315 凍結**不擅自升版。
- **編碼**：`vision/*.py` 須 UTF-8；Fusion `null bytes` → 轉碼 + 清 `__pycache__`。
- **文件**：`docs/RAYVISION_INTEGRATION_PLAN.md`（Phase 1 ✅）、`docs/VISION_SNAPSHOT_v1.md`、`docs/開發對話與變更.md` ## 2026-05-20。

"""
    if "2026-05-20（視線法" not in t:
        marker = "## 2. 依日期整合時間線"
        t = t.replace(marker, marker + "\n" + block)
    if "整合至 2026-05-04" in t and "2026-05-20" not in t.split("\n", 3)[0]:
        t = t.replace(
            "整合至 2026-05-04",
            "整合至 2026-05-20（含 2026-05-20 視線法外輪廓／草圖）",
            1,
        )
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched INTEGRATED_HANDOFF.md")


def patch_ai_reading_order() -> None:
    p = DOCS / "AI_閱讀順序.md"
    t = p.read_text(encoding="utf-8")
    vision_steps = r"""
### 任務含視線法／驗證草圖／`vision/` 時（加讀）

在步驟 1（行為準則）之後、改碼前追加：

1. **`docs/VISION_CONTOUR_AND_SKETCH.md`**（全文）— 多台面外輪廓、槽膠囊、MCP、熱重載約束。  
2. **`docs/VISION_SNAPSHOT_v1.md`** — `vision_snapshot` 欄位與資料來源。  
3. **`docs/RAYVISION_INTEGRATION_PLAN.md`** — Phase 1 狀態與勿改 execute 邊界。  
4. **`docs/開發對話與變更.md`** — **## 2026-05-20**。

"""
    if "VISION_CONTOUR_AND_SKETCH" not in t:
        t = t.replace("## 讀完後再進程式碼時", vision_steps + "\n## 讀完後再進程式碼時")
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched AI_閱讀順序.md")


def patch_behavior_rules() -> None:
    p = DOCS / "行為準則.md"
    t = p.read_text(encoding="utf-8")
    # remove misplaced duplicate ## 9 vision at end
    old_tail = """## 9. 視線法（唯讀，可關閉）

- `ENABLE_VISION_LAYER`（主檔常數，預設 True）關閉時行為與併入前一致。
- `vision/` 模組僅產生 `runtime_state.vision_snapshot`，**不得**改寫 §3.1 孔鏈、§8.4 模板契約或 execute。
- 掃描流程：孔/槽掃描完成後 `_refresh_vision_snapshot()`，重用 `last_hole_scan_rows_raw` 與 `slotInfoList`。"""
    new_tail = """## 11. 視線法（唯讀，可關閉）

- **開關**：`ENABLE_VISION_LAYER`（主檔常數，預設 True）；False 時行為與併入 RayVision 前一致。
- **範圍**：`vision/` 僅產生 `runtime_state.vision_snapshot` 與可選驗證草圖；**不得**改寫 §3.1 孔鏈、§8.4 模板契約或 `execute` 語義。
- **掃描**：孔／槽掃描完成後 `_refresh_vision_snapshot()`，重用 `last_hole_scan_rows_raw` 與 `slotInfoList`（與面板同源）。
- **輪廓（2026-05-20）**：掃描與草圖須用 `get_machining_contour_faces_wcs` + `get_complete_outer_contour_edges`；**禁止**退回到僅 `get_top_face()` 單面外框（槽型雙台面會「只有左邊有線」）。
- **槽草圖**：優先 `loop_edges` 投影；後備膠囊 `_draw_slot_capsule`；**禁止**用矩形 `_draw_slot_rects` 包住跑道槽。
- **繪製**：`create_recognition_sketch_from_vision(snap, setup=...)` 須傳**使用中 CAM Setup**；`draw_recognition_sketch` 在 `notify` 先於 `PaletteActionContext` 處理。
- **熱重載**：**勿**為視線法新增 `PaletteActionContext` 欄位；用 `runtime_state.refresh_vision_snapshot_fn`。
- **詳細**：`docs/VISION_CONTOUR_AND_SKETCH.md`、`docs/VISION_SNAPSHOT_v1.md`。"""
    if "## 11. 視線法" not in t:
        if old_tail in t:
            t = t.replace(old_tail, new_tail)
        else:
            t = t.rstrip() + "\n\n---\n\n" + new_tail + "\n"
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched 行為準則.md")


def patch_checklist() -> None:
    p = DOCS / "CHECKLIST.md"
    t = p.read_text(encoding="utf-8")
    sec = r"""
### 13) Vision layer — contour sketch (2026-05-20)
- [ ] `ENABLE_VISION_LAYER=True`: rescan then init JSON shows `vision.ok` and contour counts
- [ ] Grooved dual-pad part: `SemiAuto_VisionSketch` has **both** left and right outer contours (not left-only)
- [ ] Grooved part: slot drawn as loop or capsule, **not** rectangle box around racetrack
- [ ] Flat single-top part: outer contour still ~8 edges (no regression)
- [ ] `ENABLE_VISION_LAYER=False`: hole list / execute unchanged vs baseline
- [ ] After code change: disable/enable add-in; clear `__pycache__`; Python sources UTF-8 (no Fusion `null bytes`)
- [ ] Draw sketch without prior rescan shows message requiring scan first

"""
    if "§13" not in t and "### 13)" not in t:
        t = t.replace(
            "- [ ] Section 12 — when changing",
            "- [ ] Section 13 — when changing `vision/`, `contour_recognizer.py`, or draw-vision-sketch path\n"
            "- [ ] Section 12 — when changing",
        )
        if "### 13)" not in t:
            t = t.rstrip() + "\n" + sec
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched CHECKLIST.md")


def patch_versioning() -> None:
    p = DOCS / "VERSIONING.md"
    t = p.read_text(encoding="utf-8")
    sync = r"""
## 6.2 文件同步紀錄（2026-05-20）

- **視線法 Phase 1 文件化**：`docs/VISION_CONTOUR_AND_SKETCH.md`（接手主檔）、`docs/VISION_SNAPSHOT_v1.md`、`docs/RAYVISION_INTEGRATION_PLAN.md`（Phase 1 ✅）。
- **`docs/開發對話與變更.md`** **## 2026-05-20**：多台面外輪廓、槽膠囊草圖、MCP 驗收。
- **`docs/INTEGRATED_HANDOFF.md`**、**`docs/AI_閱讀順序.md`**、**`docs/行為準則.md` §11**、**`docs/CHECKLIST.md` §13**：交叉連結。
- **版號**：功能修正期間維持 **V2.0315 凍結**；文件更新不觸發 §4 升版清單。

"""
    if "6.2 文件同步紀錄（2026-05-20）" not in t:
        t = t.replace("## 7. 專案內 Markdown 對照", sync + "\n## 7. 專案內 Markdown 對照")
    rows = (
        "| **`docs/VISION_CONTOUR_AND_SKETCH.md`** | **2026-05-20 接手主檔**：視線法外輪廓、槽膠囊草圖、MCP、編碼與熱重載約束。 |\n"
        "| **`docs/VISION_SNAPSHOT_v1.md`** | `vision_snapshot` / init JSON `vision` 契約。 |\n"
        "| **`docs/RAYVISION_INTEGRATION_PLAN.md`** | RayVision 併入三層架構；Phase 1 完成狀態。 |\n"
    )
    if "VISION_CONTOUR_AND_SKETCH" not in t:
        t = t.replace(
            "| **`docs/INTEGRATED_HANDOFF.md`** | **主整合交接**",
            rows + "| **`docs/INTEGRATED_HANDOFF.md`** | **主整合交接**",
        )
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched VERSIONING.md")


def patch_changelog() -> None:
    p = DOCS / "開發對話與變更.md"
    t = p.read_text(encoding="utf-8")
    if "## 2026-05-20" not in t:
        insert_at = t.find("---\n\n## 2026-05-04")
        if insert_at < 0:
            insert_at = t.find("## 2026-05-04")
        if insert_at >= 0:
            t = t[:insert_at] + CHANGELOG_20260520 + "\n---\n\n" + t[insert_at:]
        else:
            t = CHANGELOG_20260520 + "\n---\n\n" + t
    p.write_text(t, encoding="utf-8", newline="\n")
    print("patched 開發對話與變更.md")


def main() -> None:
    w("VISION_CONTOUR_AND_SKETCH.md", VISION_CONTOUR.strip() + "\n")
    w("VISION_SNAPSHOT_v1.md", VISION_SNAPSHOT.strip() + "\n")
    w("RAYVISION_INTEGRATION_PLAN.md", RAYVISION.strip() + "\n")
    patch_integrated_handoff()
    patch_ai_reading_order()
    patch_behavior_rules()
    patch_checklist()
    patch_versioning()
    patch_changelog()
    print("done.")


if __name__ == "__main__":
    main()
