# Smart_AI_CAM 完整能力清單（manifest 解碼）

> 來源：`MCP get_cam_agent_manifest` (port 9877)
> 採集時間：2026-05-26
> 位置：`recon\get_cam_agent_manifest.json` (11.3 KB)

## 1. 插件基本資訊

| 項目 | 值 |
|---|---|
| Name | Smart_AI_CAM |
| Version | V2.0358 |
| Role | 半自動 CAM：B-rep/官方辨識 → 模板工序 → 學習庫建議 |
| Materials | AL6061, S50C |
| Add-in dir | `E:\Fusion\插件\Smart_AI_CAM` |
| Reference lib | `E:\Fusion\參考範本\f3z已編程` (117 檔) |
| MCP | 127.0.0.1:9877, JSON line per request |

### 內部文檔（4 份）

```
docs/CAM_FEATURE_RECOGNITION_MAP.md
docs/AI_SYSTEM_ARCHITECTURE.md
docs/PROGRAMMING_MODES.md
docs/F3Z_LEARNING.md
```

## 2. 5 種編程模式

| 模式 | 說明 | 觸發 MCP |
|---|---|---|
| `panel_manual` | 面板手動：用戶親選模板 | 各種 panel_apply |
| `ai_recommendations_apply` | AI 建議套用 | `get_ai_recommendations` |
| `intuitive_restricted` | 直覺式（受限） | `run_intuitive_one_click` / `run_intuitive_programming` |
| `thinking_L0` | 思考式 L0/L1/L2 | `run_thinking_programming` |
| `imported_f3z_learning` | 匯入 f3z 學習 | `batch_import_reference_library` |

## 3. 7 大特徵分類

### hole（孔）
- 來源: B-rep 射線 / RecognizedHoleGroup（需 Manufacturing Extension）
- 模板鍵: `generalHole`, `tapHole`, `locatingHole`, `countersinkHole`, `holeChamfer`
- 幾何索引: `diameter_mm`, `hole_type`

### slot（槽）
- 來源: 開口面 B-rep
- 模板鍵: `slotHole`
- 幾何索引: `width_mm`

### pocket_corner_r（槽角 R）
- 來源: 槽角 R 圓柱
- 模板鍵: `generalHole`（diameter_mm = 2R）

### face_plane（平面）
- 來源: 朝上平面叢集 / `flat_depths`
- 模板鍵: `topFaceRough`, `topFaceFinish`
- 索引: material only

### outer_contour（外輪廓）
- 來源: 外輪廓 WCS / `contour_2d_recognizer`
- 模板鍵: `profileRough`, `profileFinish`
- 索引: material only

### chamfer_bevel（倒角斜邊）
- 來源: 斜邊
- 模板鍵: `holeChamfer`, `contourChamfer`
- 索引: `diameter_mm`, `chamfer_tag`

### official_pocket（官方口袋）
- 來源: RecognizedPocket（需 ME）
- 模板鍵: `slotHole`
- 註: 腰形 vs 封閉口袋；2D/3D 綁定

## 4. 完整 MCP Actions 清單（40 個）

### 唯讀類 (destructive=false)

#### 不需文件
```
get_cam_agent_manifest        完整能力清單（給 Fusion AI 對照）
get_fusion_ai_gap_audit_pack  manifest+stats+稽核 prompt 一鍵包
get_addin_info                插件版號 / Setup / 材質
knowledge_stats               學習庫總筆數+分布
knowledge_query               查特定特徵歷史模板
knowledge_export              學習庫匯出
knowledge_import              學習庫匯入
knowledge_rebuild_index       重建索引
knowledge_merge_duplicates    合併重複
knowledge_resolve_templates   解析 template_path
get_knowledge_stats           （別名）
query_best_template           查最佳模板
query_all_recommendations     查所有建議
list_reference_f3z            列 f3z 樣本（117 檔）
list_reference_files          列參考檔
scan_reference_library        掃描參考庫
get_multi_setup_plan          讀 L2 雙 Setup 腳本
get_thinking_layers           列思考式層級
```

#### 需要 Fusion 文件
```
scan_machining_features       掃描特徵目錄（孔/槽/平面/口袋）
recognize_contour_2d          2D 頂面/輪廓/倒角辨識 → recommended_templates
refresh_vision_snapshot       重建 vision_snapshot (FAST_2D / FULL_3D)
get_vision_snapshot           讀 runtime vision_snapshot (含 points_3d)
get_ai_recommendations        AI 完整方案（decisions + panel_apply）
get_cam_depth_plan            flat_depths → CAM 高度／切深計劃
verify_cam_depth_plan         驗收切深 + AI 建議
verify_tool_library           驗收刀具庫
get_machining_report          加工報告
check_intuitive_eligibility   檢查直覺式可行性
check_thinking_eligibility    檢查思考式可行性
import_cam_from_active_document 從當前文件匯入
```

### 寫入類 (destructive=true) ⚠️ 需用戶確認

```
execute_machining_plan        執行加工計劃
auto_create_cam_setup         自動建立 Setup
run_intuitive_one_click       一鍵直覺式
run_intuitive_programming     直覺式編程
run_thinking_programming      思考式編程 (L0/L1/L2, L2 supports resume_from_sequence=2)
run_internal_ai_autopilot     內部 AI autopilot
batch_import_reference_library 批次匯入參考庫
```

### 除錯類（不建議）
```
execute_python_code           任意 Python 執行（稽核時不建議）
```

## 5. 模板庫機制

| 項目 | 內容 |
|---|---|
| 來源 | 本機 `.f3dhsm`（`TEMPLATE_FOLDER_PATHS`） |
| 每筆欄位 | `name`, `url`, `hasDrill`, `drillUrl`, `chamferUrl`, `toolDia`, `cycleType` |
| 解析器 | `template_resolver`（名稱→URL） |
| 參數快照 | `getTemplateParams`（少數欄位：底面高度、pitch 等） |

## 6. 學習庫即時統計（採集時刻）

```
總筆數:       2272
評分過:       0
保留筆數:     792
Pattern keys: 195
Session ID:   2b42b901
Session ops:  0

按特徵類型:
  hole:               1283  (56.5%)
  chamfer:            548   (24.1%)
  face:               229   (10.1%)
  slot:               108   (4.8%)
  system_feature:     58
  profile:            41
  material_knowledge: 5

按材質:
  AL6061: 1849 (81.4%)
  S50C:   423  (18.6%)

Top 5 模板:
  倒角刀         67 次
  倒角刀 (2)     52
  倒角刀 (3)     50
  中心鑽         50
  倒角刀 (4)     46
```

## 7. Fusion API 使用情況

```
adsk.fusion Design B-rep (faces, edges, bodies)
adsk.cam setups.add (MillingOperation)
adsk.cam createFromCAMTemplate + template library URL
adsk.cam generateToolpath
Manufacturing: recognize holes/pockets (optional, ME extension)
CustomEvent + palette HTML (UI)
TCP localhost MCP bridge (port 9877)
```

## 8. Fusion CAM 沒覆蓋的部分（fusion_cam_not_covered）

| 領域 | 狀態 | 替代方案 |
|---|---|---|
| 5_axis | 未納入模板路徑與 execute 預設流程 | Fusion 原生 CAM 手動建 |
| probing | 無探測工序自動化 | 手動建 probe operation |
| adaptive_clearing | API 可建；插件未預設 Adaptive 全自動策略 | Fusion 原生 |
| turning | 僅銑削 Setup（MillingOperation） | 換 Fusion Turning |
| wire_edm | 未支援 | - |
| additive_cam | 未支援 | - |
| nest_sheet | 未支援 | - |
| post_processor_editor | 僅 generateToolpath；後處理不在插件內 | Fusion CAM Post Library |
| toolpath_simulation_ui | 可透過 API 觸發；插件未包裝完整模擬 UI 流程 | Fusion 內建模擬器 |
| machine_connect | 未支援 | - |
| any_operation_without_local_template | 依本機 .f3dhsm 模板庫；無對應 URL 則無法 createFromCAMTemplate | 先在模板庫加對應 URL |

## 9. 已知限制

1. 官方孔/口袋 API 需 Manufacturing Extension；失敗時自動回退 B-rep
2. 思考式 L2 雙 Setup 已實作（Setup1 後需人工翻面再 `resume_from_sequence=2`）
3. UI 未顯示 `knowledge_confidence` / `reason`（後端已有此資料）
4. 參考 f3z 匯入時 `template_path` 常為空，靠工序名 + resolver
5. Autodesk Assistant 無直接呼叫 Add-In 的 API；需 MCP 橋接腳本

## 10. Gap Audit Prompt（給 Fusion AI 對照）

`get_fusion_ai_gap_audit_pack` 會回傳：
- A: Smart_AI_CAM 插件能力清單（manifest）
- B: 學習庫統計
- C: 預設 prompt 模板，請 Fusion AI 輸出：
  1. 插件已覆蓋且合理：與 Fusion 標準流程對齊的部分
  2. Fusion 有、插件明確未做：補充遺漏項
  3. 插件有、但 Fusion 原生較弱或需 ME：例如 RecognizedPocket、學習庫
  4. 建議優先補強 TOP 5：依「常用銑削件」優先級排序
  5. MCP 可驗證項：建議用哪個 action 在實機驗證
