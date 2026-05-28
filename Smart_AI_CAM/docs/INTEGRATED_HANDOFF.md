# 半自動加工選單 整合交接（整合至 2026-05-20）

本文件整合 **2026-04-25** 至 **2026-04-28** 的定案與驗收紀錄，以及 **2026-05-01 ~ 2026-05-02** 的 UI／模板／執行路徑穩定化要點，並補 **2026-05-04** 之**版號累加定案**與 **2D 內輪廓參考文件**，作為**單一接手入口**，避免只讀舊檔而與現行程式行為脫節。  
**程式級細節、常數名與取捨**：見 **`docs/開發對話與變更.md`**（**## 2026-05-04**、**## 2026-05-02** 兩節及文末 **English notes**）；本檔負責**脈絡、不可踩線與回歸順序**。

---

## 0. 與其他文件的關係（請先對齊）

| 檔案 | 讀取時機 |
|------|----------|
| **`docs/行為準則.md`** | **改碼前必讀**：協作門檻、鑽孔核心與預鑽定案、更動原程式碼前須說明影響並取得同意；**孔加工模板**之路徑鍵、載入、直徑索引、篩選與 **`buildDropItems`** 組合順序以 **§8.0～§8.4（尤其 §8.4）** 為完整契約。 |
| **`docs/AI_閱讀順序.md`** | AI／代理載入專案時的建議順序（第一步即行為準則）。 |
| **`docs/VERSIONING.md`** | 升版、`ADDIN_VERSION` 與 `.manifest`／`palette.html` 同步規則。 |
| **`docs/版本紀錄.md`** | 正式版號與功能／辨識範圍語意（**最新章節在最上方**）。 |
| **`docs/開發對話與變更.md`** | **單一連續開發日誌**：**## 2026-05-04**（+1.0000、當日 md、2D 索引）、**## 2026-05-02**（預鑽、CAM、`run()`、刀路、訊息、未採納項、MCP、版號 §8～11）、文末 **English notes**；**勿**再新建分日期平行檔。 |
| **`docs/REF_2D內輪廓_loop_edges順序.md`** | **暫定參考**：2D 輪廓工法 × **槽 inner loop** → **反轉 `loop_edges`**；**`docs/行為準則.md` §8.5** 連結至此（非 §8.0～8.4 契約）。 |
| **`docs/BASELINE_ALIGNMENT.md`** | baseline-first 與變更節奏。 |
| **`docs/VISION_CONTOUR_AND_SKETCH.md`** | **2026-05-20 視線法接手主檔**：多台面外輪廓、槽膠囊草圖、MCP、UTF-8、勿擴 `PaletteActionContext`。 |
| **`docs/VISION_SNAPSHOT_v1.md`** | `vision_snapshot`／init JSON `vision` 契約。 |
| **`docs/RAYVISION_INTEGRATION_PLAN.md`** | RayVision 併入三層；Phase 1 完成。 |
| **`docs/CHECKLIST.md`** | 回歸清單；**§9–§13**（§13 視線法草圖，2026-05-20）。 |

---

## 1. 專案目標與工作範圍

- 專案：`半自動加工選單`
- 主軸：
  - 孔加工辨識與模板套用穩定化
  - 長條孔（slot/racetrack）辨識與加工語義整合
  - RayVision `FAST_2D` 投影流程穩定化（Fusion 原生 `project`）
- 核心要求：
  - 保留已驗證語義
  - 小步驟可回退
  - 不做破壞性重構

---

## 2. 依日期整合時間線

### 2026-05-20（視線法 Phase 1 · 外輪廓與驗證草圖）

- **接手主檔**：`docs/VISION_CONTOUR_AND_SKETCH.md`（改 `vision/`、`contour_recognizer.py` 前必讀）。
- **已修**：槽型雙台面「只有左邊有線」；槽草圖矩形方框 → `loop_edges` 或膠囊。
- **API**：`get_machining_contour_faces_wcs`、`get_complete_outer_contour_edges`；掃描與 `assist_sketch` 共用。
- **流程**：重新掃描 → `_refresh_vision_snapshot()` → 繪製 `SemiAuto_VisionSketch`（須先掃描）。
- **勿踩**：不擴 `PaletteActionContext`；`ENABLE_VISION_LAYER=False` 回歸；**V2.0315 凍結**不擅自升版。
- **編碼**：`vision/*.py` 須 UTF-8；`null bytes` → 轉碼 + 清 `__pycache__`。
- **日誌**：`docs/開發對話與變更.md` **## 2026-05-20**。

### 2026-04-25（slot 架構與規則定案）

- 孔辨識為第一層主判定，slot 辨識為第二層補充，不可覆蓋孔流程語義。
- slot 規則定案：
  - 開口面：`face_z = fz_max if dot_z > 0 else fz_min`
  - 深度：
    - top opening：`depth = face_z - slot_z_min`
    - bottom opening：`depth = slot_z_max - face_z`
  - 通孔：`abs(slot_z_min - body_z_bot) < through_tol`
  - 移除舊定義：`body_z_top - face_z` 不再作為 slot 深度
- UI 與模板：
  - **孔表顯示（歷史述詞＋後續定案）**：04-25 當時以「前側為主」描述；**04-28 起**已定案為 **通孔** 可 **Z+／Z−** 皆列入（見本檔 **§10.3～10.4**）；**盲孔**仍僅 **Z+**；**背面沉頭**排除。  
  - slot 區塊在孔區塊下方
  - slot 使用單一下拉：`模板+倒角 / 倒角 / 不使用`
  - 刀徑可行性：`D + 0.5 <= W <= D * 1.8`，刀徑集合 `2,3,4,6,10`
- 驗證對照：
  - `设置1`：`5.5 / 深5 / 通 / 4`
  - `设置1 (2)`：`10.0 / 深5 / 盲 / 4`、`5.5 / 深10 / 通 / 4`

### 2026-04-27（模組化穩定化 + 深度流程定案 + FAST_2D 修正）

- 架構穩定化：
  - 模組化拆分：`ui/`、`machining/`、`templates/`、`state/`
  - 新增集中狀態：`state/runtime_state.py`
  - UI 事件集中至 `ui/palette_controller.py`，使用 action context
  - 補上 add-in 啟動 import fallback（`ModuleNotFoundError` 防護）
- UI/行為修正：
  - Palette **寬度**固定 **800**（`FIXED_PALETTE_WIDTH`）；開啟面板時 Fusion API 另帶**高度**參數 **900**（與預設 JSON 內 `paletteHeight`／`mainHeight` 一致），**勿**將「900」誤記為寬度。並支援載入/更新/存檔預設
  - 孔面模板回歸「同孔單面」而非 all faces
- 盲孔絞刀流程最終定案：
  - 只在有絞刀時，由絞深驅動鑽深
  - 公式保留：`鑽深 = 絞深 + 鑽尖高度 + 0.5`
  - 移除直徑插值鑽尖長度方案
  - UI 初次開啟自動觸發計算（盲孔 + 絞刀）
  - 有絞刀 + 盲孔時，鑽深欄顯示「依計算結果」，模式下拉鎖定
  - execute 期修正：
    - 計算值回填 `drillDepthMM`
    - 覆蓋寫入 `bottomHeight_offset`
    - `drillTipThroughBottom=true` 時，drill/ream 強制 `bottomHeight_offset=0`
- RayVision / FAST_2D（同日）：
  - `sketch.project(edge)` 可用，但需避免 proxy/native context 混用
  - `setup.models` 映射到 `root.bRepBodies` 後投影穩定
  - 支援 setup 多 body，不再假設單一 body
  - 最新觀測：
    - `body_edges=211`
    - `visible_edges=52`
    - `top_loop_edges=52`
    - `投影段=44`
    - `project_fail=0`
    - `FAST_2D contours=2`（多實體語意已生效）

### 2026-05-01 ~ 2026-05-02（UI／模板／預鑽／CAM／execute 尾段）

以下為**現行接手必知**摘要；**實作細節與常數**請讀 **`docs/開發對話與變更.md`** 對應章節。

- **設定與 UI**：「套用／重新檢測／存成預設值」路徑一致；沉頭列避免鑽深欄位誤顯；`pitch` 預設優先讀模板（含 `pitchMM`）。
- **模板路徑**：一般孔／牙孔／定位孔 與 沉頭／長條孔 **嚴格分流**；缺模板改為**依直徑**可讀警告。  
  - **鑽／孔倒角載入、直徑模糊對表（0.2 mm）、白名單倒角標、`buildDropItems` 一般列與沉頭大孔列之篩選與輸出順序**：權威敘述見 **`docs/行為準則.md` §8.4**（與 **§8.0** 防擅自更動約定）；本檔 §10.5 僅摘要槽孔誤入修復。  
  - **V1.0303**：**`template_fs_cache`** 整包掃 **`CAM360\templates\{材質}`** 建索引；**`collect_assets_from_folder_path`／`collect_slot_chamfer_assets`** 優先索引＋**`join`** 還原 **`url`**，失敗則 API 後備；**`full_rescan`**／面板槽與輪廓倒角重載時 **`invalidate_all`**（見 **`docs/版本紀錄.md` V1.0303**）。  
  - **V1.0302**：主孔表 **`chamferMap`** 於嚴格模式下**僅**自 **`TEMPLATE_FOLDER_PATHS["holeChamfer"]`**（**`…/孔倒角 【{material}】`**）蒐集，**不再**掃描整個 **`倒角刀模塊 【{material}】`**（見 **`docs/版本紀錄.md` V1.0302**、**`docs/行為準則.md` §8.2**）。
- **大孔通孔預鑽**：孔徑 **嚴格大於 6.5 mm** 之通孔（且非 `isCBLarge` 沉頭大孔列），種子面併入既有 **[2.6, 5.5] mm 內直徑最大** 之 **drill** 工序；**不再**自函式庫另挑小徑預鑽模板（見對話紀錄 §1）。
- **CAM 與啟動**：無製造產品時 `_safe_cam_from_document` 不崩潰；`run()` **先註冊** command／工具列再檢查文件，避免 `stop()` 後圖示消失（§2）。
- **刀路與排序**：有新建工序時以 **整個 setup** 的 `ObjectCollection` 呼叫 `generateToolpath`，再執行全局工序排序；曾試作「條件式排序／執行次數快取」**已撤銷**（§3）。
- **完成訊息**：精簡 `messageBox`，保留總耗時一行（§4）。
- **曾討論但未採納的優化**：見對話紀錄 §5（改動前須寫清副作用與驗證）。
- **版號**：細修步長 **+0.0001**、四位小數顯示；見 `docs/VERSIONING.md` 與對話紀錄 §8。

### 2026-05-04（版號累加、文件、2D 內輪廓參考）

- **版號**：**`V2.0310`**（**`V1.0310 + 1.0000`**，小數段**不**覆蓋重置）；**`docs/VERSIONING.md`** §1、**`docs/行為準則.md`** §7、**`ADDIN_VERSION`**／**`.manifest`**／**`palette.html`** 已同步。  
- **對話紀錄**：**`docs/開發對話與變更.md`**。  
- **2D 內輪廓（暫定參考）**：**`docs/REF_2D內輪廓_loop_edges順序.md`** — **§0.0** **Fusion 工法的幾何依據**（2D：Chain／Loop + 行進方向 + **compensation**；3D：**BRepFace** + 法向 + 材料側；特徵對照表；辨識器／工法分工）；**§0** 歸納 **行進方向 ↔ left／right**、**inner loop `coEdge`／B-rep** 等；**§0.1** **`is_inner_loop`** 表；實作 **`reversed()`** 或 **`isReverted`** 勿雙重反轉。  
- **行為準則**：**§8.5** 僅為**參考連結**，**不**擴充 §8.0～8.4 契約。

---

## 3. 不可偏移的基準規範（Baseline）

基準文件：`docs/BASELINE_ALIGNMENT.md`

- 權威判定鏈（語義與順序不可改）：
  1. `rebuildHoleList(...)`
  2. `_isCounterbore(...)`
  3. `_isThrough(...)`
  4. `_getHoleDirection(...)` / `_getCBDirection(...)`
  5. `_appendSimpleHole(...)`
  6. `mergeHoleListByDia(...)`
- 射線法定位規則：
  - 僅可做輔助訊號（secondary signal）
  - 不可覆蓋權威判定鏈
  - 不可替代 `through/blind` 主語義
- 必須嚴格等價抽離的函式：
  - `buildTemplateMaps`
  - `buildDropItems`（篩選條件、**A／B 分支輸出順序**、**0.2** 直徑容差、**`ALLOWED_CHAMFER_TAGS`** 白名單等，以 **`docs/行為準則.md` §8.4** 為契約；抽離時**不得**改語意）
  - `makeHoleLabel`
  - `_isCounterbore`
  - `_isThrough`
  - `_countHoles`
  - `_appendSimpleHole`
  - `rebuildHoleList`
- 未明確核准前禁止：
  - 改變通/盲語義
  - 用 ray-only 取代 `_isThrough`
  - 更改沉頭分支邏輯
  - 新增會覆蓋 baseline 的 heuristics

---

## 4. 回歸驗收整合（必跑）

基礎清單來源：`docs/CHECKLIST.md` + `docs/BASELINE_ALIGNMENT.md`

- 啟動與初始化：
  - 面板可開啟且無錯誤
  - setup/material 預設正確
  - hole/slot 清單正常渲染
- setup 與重掃描：
  - `setup_change` 可刷新
  - `rescan` 與 `sync_display` 行為正確（含幾何變更判定）
- 模板與顯示：
  - `material_change` / `tmpl_change` 正常
  - 模板缺失有可讀警告
- 深度與計算：
  - `depth_change` 訊息正確
  - 通孔跳過深度計算
  - 絞刀相關計算只在適用情境出現
- 診斷與執行：
  - 診斷面板與 debug 開關正常
  - `dump_op_params` 可輸出
  - `execute` 成功/失敗路徑皆可讀且無崩潰
- baseline 對照 setup：
  - `设置1`：D3.3 / D4.0 / D5.5 / D10.0（沉頭）判定一致
  - `设置1 (2)`：通/盲分布一致
  - `设置1 (3)`：盲孔深度與 count 一致

**2026-05-02 補強**：務必加跑 **`docs/CHECKLIST.md`** 的 **「2026-05-02 Supplement」§9–§11**（沉頭列 UI、模板分流、設定持久化）。

---

## 5. 目前狀態判讀（截至 2026-05-04）

- **功能面**：在 **V1.03 辨識刻度** 下，04 月底已定案的通孔／沉頭／槽孔模板隔離與 D9 等行為仍有效；05-02 補強 **設定套用鏈、模板路徑分流、大孔預鑽併入、CAM 安全載入、`run()` 註冊順序、execute 尾段刀路觸發與排序、訊息精簡**。**2026-05-04** 起顯示版號 **V2.0310**：**第二族（槽）**端到端可帶模板並生成工序／刀路（見 **`docs/版本紀錄.md` V2.0310**）。權威語意未改寫 baseline 鏈（見 `docs/BASELINE_ALIGNMENT.md` 2026-05-02 註記）。
- **規範面**：baseline-first 不變；execute 尾段**刀路觸發與排序**以 **§2 的 05-02 小節** 與 **`docs/開發對話與變更.md` §3** 為準（整個 setup `generateToolpath` 後再全局排序）。**版號**以 **`docs/VERSIONING.md`**（**`+1.0000`** 累加）與 **`docs/開發對話與變更.md`** 為準。
- **槽／2D 內輪廓**：**`docs/REF_2D內輪廓_loop_edges順序.md`** 與 **`docs/行為準則.md` §8.5** 為**暫定參考**；改槽或 CadContours2d 綁定前應讀，**不**自動升格為 §8.0～8.4 契約。
- **風險面**：觸及 `_isThrough`、沉頭、`rebuildHoleList`、**預鑽併入**、**`generateToolpath` 範圍**、全局排序、`material_change`／`full_rescan` 者，必跑 **§4** 與 **CHECKLIST 最小集 + §9–§11**。

---

## 6. 下一步建議（按優先序）

1. 依 **`docs/AI_閱讀順序.md`** 或本檔 **§0** 載入其餘 md。
2. 跑 **`docs/CHECKLIST.md`**「Minimal Suite Per Change」+ **§9–§11**。
3. 跑 baseline 三組 setup（`设置1` 系列）。
4. 若有差異，先回退到上一可用點，不做推測型補丁。
5. 若要新增優化，先讀 **`docs/開發對話與變更.md` §5**（未採納項與原因），並以可觀測性／可關閉為優先。

---

## 7. 參考來源

- `docs/AI_閱讀順序.md`
- `docs/VERSIONING.md`
- `docs/版本紀錄.md`
- `docs/開發對話與變更.md`
- `docs/BASELINE_ALIGNMENT.md`
- `docs/CHECKLIST.md`
- `docs/版本紀錄.md（## V1.03）`（僅 V1.03 凍結封存對照）

---

## 8. 刷新紀錄（2026-04-27 夜間）

- 孔辨識主流程調整為 `RecognizedPocket` 優先，ray 降級為 hint，不再做「ray 失敗即刪孔」。
- `hole_recognizer.py` 保留 `recognize_holes_by_pocket` 相容 wrapper，避免外部腳本相依斷裂。
- 高低落差孔案例完成定位：`D9` 候選存在，原本在 ray 可達性階段被排除；後續改為保留孔列。
- `execute` 前新增材質確認對話框（需人工確認後才執行）。
- `execute` 後新增模板材質檢測，並優化為輕量規則：
  - 只看模板名稱是否含 `【AL6061】` 或 `【S50C】`
  - 不做模板內工序檢查
  - 不再跳第二個阻塞警告視窗，改併入結果訊息
- 修正材質檢測誤報：優先用模板 URL 的 `leafName` 判定，取不到名稱則不判異常。
- 修正材質切換一致性：
  - `material_change` 改為 `full_rescan()`，刷新 UI + 模板映射路徑
  - `_executeFromPalette` 執行前強制以當前材質重建 `dropItems`，避免沿用舊快取
- 修正深度欄顯示：
  - `鑽深預設` / `鉸深預設` 模式下隱藏輸入欄
  - 修補初次載入顯示不一致（`updateDrillDepthDisplay` 覆寫問題）

---

## 9. （歷史）2026-04-28 開工待辦

以下為 **2026-04-28 當日 backlog**，**多數已完成**；**勿當作現行待辦單**。現行驗收以 **§4、§5** 與 **`docs/CHECKLIST.md`** 為準。

1. 先驗證材質切換流程：切換 `AL6061 <-> S50C`，確認 `full_rescan()` 後孔模板下拉立即更新。
2. 驗證快速執行情境：切材質後立即按執行，確認實際套用模板與 UI 材質一致。
3. 跑孔辨識重點回歸：確認高低落差孔（含 `D9` 類）不再因 ray 判定被刪除。
4. 跑最小穩定性清單：啟動、rescan、execute、刀路生成、診斷輸出。
5. 若時間允許，補一條診斷輸出：每列顯示 `source/accessibilityHint/needsReview` 便於現場判讀。

---

## 10. 刷新紀錄（2026-04-28 凌晨，穩定版前驗收）

### 10.1 MCP 驗證（功能完整性）

- 驗證目標：
  - 孔加工關鍵參數可寫入（含 `bottomHeight_offset`、`breakThroughDepth`、`bottomHeight_mode`、`drillTipThroughBottom`）。
  - 鑽尖相關能力（`tool_tipAngle` 計算與參數帶入）。
  - 初始化模板載入與材質切換模板映射（`AL6061` / `S50C`）。
- 驗證方式：
  - 使用 Fusion MCP 直接讀取活動文件與 setup。
  - 以「可回復寫入」方式測試參數（寫入 -> 回讀 -> 還原）。
  - 直接載入 add-in 主檔，呼叫 `buildTemplateMaps` 與 `_load_2d_template_maps` 檢查模板映射。
- 結果重點：
  - drill/center-drill/reamer/chamfer 工序關鍵欄位可寫入與還原。
  - 少數面銑/外輪廓工序 `bottomHeight_mode='from hole bottom'` 失敗屬枚舉不支援（非插件故障）。
  - drill/reamer 的 `bottomHeight_mode` 在 `from hole bottom <-> from stock bottom` 可切換且可還原。
  - `drillTipThroughBottom` true/false 可切換且可還原。
  - 模板載入正常：`AL6061` 與 `S50C` 均可取回 drill/chamfer/2D 模板映射。

### 10.2 鑽尖角計算驗證（最終）

- 依既有公式確認：
  - `tipHeightMM = (tool_diameter / 2) / tan(tool_tipAngle / 2) * 10`
- 實測 drill 工序可得穩定計算值，並可回寫到 `breakThroughDepth` 後還原。
- reamer 若直接以自身 `tool_tipAngle` 計算，可能為 0 導致無效；流程上應以 drill 工具幾何為計算來源（與現有插件邏輯一致）。

### 10.3 D9.0 問題定位與修復

- 現象：
  - 辨識 debug 可見 `D9.0`（`count=2`），但 UI 表格未顯示該列。
- 根因：
  - `_buildHoleData()` 存在 `dir != 'Z+'` 直接排除，導致 `Z-` 通孔被 UI 隱藏。
- 修復：
  - 改為「通孔不分正反面可顯示」。
  - 保留非通孔前側限制（`not through` 且 `dir != 'Z+'` 仍隱藏）。
  - 加上背面沉頭不可加工規則（見 10.4）。

### 10.4 正反面與沉頭最終規則（本次定案）

- 使用者定案：
  - 只要是【通孔】不分正反面都可加工。
  - 背面沉頭不可加工。
- 目前規則落點（`_buildHoleData`）：
  - `through == True`：保留 `Z+` 與 `Z-`。
  - `through == False`：僅保留 `Z+`。
  - 背面沉頭（`dir == 'Z-(CB)'` 或 `dir == 'Z-'` 且 `isCBLarge/isCBSmall=True`）：直接排除。

### 10.5 長條孔模板誤入一般孔（本次修復）

- 現象：
  - 一般孔模板下拉可看到長條孔/槽孔模板，造成誤套用風險。
- 修復位置：
  - `templates/template_service.py` -> `build_template_maps()`
- 修復內容：
  - 新增槽孔模板識別關鍵字（`長條孔`、`槽孔`、`slot`、`obround`、`racetrack`）。
  - 在 `add_to_drill_map` / `add_to_chamfer_map` 遇到槽孔模板時直接跳過。
- 結果：
  - 長條孔模板不再混入一般孔模板池。
- **與主孔表鑽／倒角下拉之關係**：槽孔關鍵字篩選亦作用於 **`chamferMap`** 建池階段；**一般列與沉頭大孔列**如何取用 **`drillMap`／`chamferMap`**、**白名單與組合順序**見 **`docs/行為準則.md` §8.4.2～8.4.6**（**§8.0**：變更須 **`docs/行為準則.md` §1** 並同步文件）。

### 10.6 診斷輔助（臨時）

- 於 `_executeFromPalette` 增加 `🧪D9` 診斷行，協助定位：
  - row 映射、dropItems 數量、模板選擇、面快取命中、reuse 命中、rowOps 輸出。
- 註記：
  - 目前保留於程式中供現場排障；若要出正式乾淨版可再移除。

### 10.7（歷史快照）當時結論（2026-04-28）

- 使用者回報：功能已恢復正常。
- **當時**可視為「穩定候選版」：
  - D9.0 通孔可見且可加工。
  - 背面沉頭不可加工。
  - 長條孔模板不會誤進一般孔流程。
  - 鑽尖角計算與關鍵參數寫入/還原已完成 MCP 驗證。

**之後**至 **2026-05-02** 的增量請以 **本檔 §2（05-02）**、**§5** 與 **`docs/開發對話與變更.md`** 疊加理解。
