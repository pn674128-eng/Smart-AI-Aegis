# Fusion CAM 特徵辨識 × 工序套用對照（插件實作）

> 對齊 Autodesk CAM API 自動化流程：**Design B-rep 辨識 → 篩選類型 → 對應 CAM Operation → Setup + 參數 → 刀路 → Post**  
> 本插件**法**層負責幾何辨識；**腦**層負責建議；**execute** 仍以既有模板鏈為準（§8.4 baseline）。

---

## 1. 總流程

```
adsk.fusion（B-rep）+ adsk.cam 官方辨識（優先）
    → RecognizedHoleGroup / RecognizedPocket（Manufacturing Extension）
    → recognizers/*（孔射線 / 槽 / 輪廓 / 倒角斜邊 / 平面 — 官方不足時補強）
    → machining_feature_catalog（統一目錄 + cam_operation）
    → vision_snapshot（可選，俯視語意）
    → ai_brain + AIDecisionEngine（建議）
    → 面板 / MCP scan_machining_features
    → _executeFromPalette（使用者確認後）
    → adsk.cam Operations + generateToolpath
```

---

## 2. 辨識範圍（V2.0347）

| 類別 ID | 幾何來源 | 面板 / 資料 | 建議 CAM 工序 | 模板路徑鍵 |
|---------|----------|-------------|---------------|------------|
| `hole` | 圓柱面 + 射線 | 孔表 | `drill` / `ream` / `tap` | `generalHole`, `tapHole`, `locatingHole`, `countersinkHole` |
| `slot` | 開口面 + 內環 | 槽表 | `pocket2d` | `slotHole` |
| `pocket_corner_r` | 槽角 R 圓柱 | 口袋 R 表 | `drill`（小徑） | `generalHole` |
| `face_plane` | 朝上平面叢集 | `flat_depths` | `face` | `topFaceRough`, `topFaceFinish` |
| `outer_contour` | 外輪廓邊（WCS） | `vision.contours` | `contour2d` | `profileRough`, `profileFinish` |
| `chamfer_bevel` | 斜向直邊（倒角） | 目錄 `chamfer_bevel` | `chamfer` / `contour2d` | `holeChamfer`, `contourChamfer` |
| `official_pocket` | **RecognizedPocket**（非圓形） | 面板拆為 **`official_slot_pockets`**（長條孔）與 **`official_pocket_slots`**（口袋槽） | `pocket2d`／`adaptive` 等（依模板） | `slotHole`（2D／3D 下拉共用全庫） |

### 2.1 Setup WCS 平面深度（`flat_depths`，V2.0326+）

**模組**：`Smart_AI/perception/feature_scanner.py` → `_scanFlatDepths()`、`_read_setup_stock_info()`。

**原則**：深度一律在 **Setup WCS**（WCS 原點 Z0），**禁止**用世界座標或混用坯料局部 Z 當「距 Z0 深度」。

| 面板／JSON 欄位 | Fusion Setup 參數 | 語意 |
|-----------------|-------------------|------|
| Setup Z0 基準 | — | 固定 **0**（WCS 原點平面） |
| 坯料尺寸 X×Y×Z | `job_stockFixedX/Y/Z`（或 `stock*High−Low`） | 固定坯料盒尺寸 |
| **頂面胚料厚度** | `job_stockFixedZOffset` | 坯料顶面 → 实体顶面 |
| **WCS Z0→工件底面** | `surfaceZLow` | `-surfaceZLow`（Setup WCS 內模型最低點） |
| **工件厚度** | `surfaceZHigh − surfaceZLow` | 实体顶 ↔ 底 |
| **坯料剩余厚度** | 計算 | `job_stockFixedZOffset + 工件厚度 − job_stockFixedZ` |
| 距 WCS Z0 深度（表格） | 水平面投影 + `surfaceZHigh` 校正 | 各台面在 WCS Z0 下之正深度 |

**2D 轮廓 · 顶面面铣**（`contour_2d_recognizer`，V2.0336+）僅顯示面銑相關：

- **面積** — 主台面 `area_mm2`
- **頂面胚料厚度** — `job_stockFixedZOffset`
- **除顶面坯料体积** — `面積 × 頂面胚料厚度`（mm³；均一水平顶面近似）

**多階台面**：`feature_apply.build_terrace_2d_templates()` 依 `z_height_mm`（Setup WCS 有號 Z）分層；execute `bind_z_mm` 仍用內部 `z_height_mm`；**V2.0357+** 每階附 `face_depth`（`cam_depth_plan.enrich_terrace_face_ops`）。

### 2.3 CAM 切深計劃（`cam_depth_context`，V2.0357+）

**模組**：`Smart_AI/reasoning/cam_depth_plan.py` → `build_cam_depth_context()`；execute 套用 `smart_ai_cam_machining/cam_operation_tuning.py`。

| 工序 | 高度語意 | 來源 |
|------|----------|------|
| 顶面粗铣 | `topHeight=from stock top` → `bottomHeight=from surface top` | `job_stockFixedZOffset` |
| 顶面精铣 | `from surface top` → `from surface top` | 精加工余量 0 |
| 外轮廓粗/精 | `top=surface top` → `bottom=surface bottom` | `part_thickness_mm` |
| S/F 写回 | `tool_spindleSpeed` / `tool_feedCutting` | `AIDecisionEngine` decisions |

**MCP**：`get_cam_depth_plan`、`verify_cam_depth_plan`；`scan_machining_features` 附 `cam_depth_context`。

---

### 2.2 官方口袋與擴充說明

**官方口袋 execute**（`recognizers/official_pocket_execute.py` + `_executeOfficialPocketRows`）：

- 執行期依 `body_token` + `pocket_index` 重新 `recognizePockets`（不只用 JSON）。
- **綁定模式**：`auto`｜`2d_only`｜`3d_only`｜`2d_then_3d`（面板「綁定」欄）。
- **2D**：`pocket.faces` 邊鏈 → `slot_chain_profiles` + `slot_chains_only`（同長條槽）。
- **3D**：底面法向平行 Setup 攻擊向之面 → `bind_all_faces`；無底面時回退側壁一面。
- 掃描分類：`classify_recognized_pocket_kind` → `slot`（腰形／長條）｜`pocket`（封闭口袋槽）。
- 面板 payload：`officialSlotPocketRows`／`officialPocketSlotRows`（或合併 `officialPocketRows`）；含 `panel_row_index`、`tmpl2dIdx`／`tmpl3dIdx`／`bindMode`。

**官方優先模組**：`recognizers/fusion_official_recognition.py`  
**語意套用**：`recognizers/feature_apply.py` + `ai_panel_apply`（倒角／螺紋／沉頭／多台面）

**不納入（需 Manufacturing Extension 或另案）**：5 軸、探測、Adaptive 全自動策略（API 可建但本插件未預設）。官方孔／口袋 API 亦需 **Manufacturing Extension**；失敗時回退既有 B-rep 掃描。

---

## 3. API 對照

| 階段 | Fusion API | 本插件模組 |
|------|------------|------------|
| 讀 B-rep | `BRepBody.faces/edges` | `hole_recognizer`, `slot_recognizer`, `contour_recognizer` |
| 建 Setup | `cam.setups.add` | `auto_create_cam_setup`（MCP） |
| 建工序 | `setup.operations` + 模板 URL | `_createOpFromTemplate` |
| 幾何綁定 | `FaceSelection`, `ChainSelection`, `CadContours2d` | execute 內槽／輪廓綁定 |
| 刀路 | `generateToolpath` | `AUTO_GENERATE_TOOLPATH_ON_EXECUTE` |

---

## 4. MCP / 面板資料

| 入口 | 輸出 |
|------|------|
| `scan_machining_features` | `holes`, `slots`, `pocket_corner_r`, `flat_depths`, **`feature_catalog`** |
| `get_ai_recommendations` | `decisions.*` + **`panel_apply`** + **`feature_catalog_summary`** |
| init JSON | `featureCatalog`、`contour2dRecognition`（2D 頂面／外輪廓） |
| `recognize_contour_2d` | 重新辨識並回傳建議模板（可 `apply` 帶入面板） |

---

## 5. 擴充辨識時的版號（`docs/VERSIONING.md`）

- 僅新增辨識類別、不改 execute：**+0.01**（例 V2.0316 → V2.0326 → …，累加不覆蓋）  
- 新增一整族可跑通模板刀路：**+1.0000**

---

## 6. 相關文件

- `docs/AI_SYSTEM_ARCHITECTURE.md`
- `docs/VISION_SNAPSHOT_v1.md`
- `docs/行為準則.md` §3.1（孔 baseline）、§11（視線法）
