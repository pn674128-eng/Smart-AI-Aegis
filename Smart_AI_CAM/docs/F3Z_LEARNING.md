# 已編程 `.f3z` 作為學習資料

> **結論**：**可以，且很值得**作為「老師傅範本」；但 **現版插件尚未實作匯入**，需另做 **F3Z／CAM 萃取管線**，並與你店內 **模板顯示名稱** 對齊後才寫入 KnowledgeDB。

---

## 1. `.f3z` 是什麼

- Fusion 360 **封裝專案**（內含設計、常含 **Manufacture／CAM** 資料）。  
- 範例路徑（僅說明用途，插件不會自動讀網路路徑）：

  `\\10.4.0.11\hy\06.製造部\阿和\輝\ZTAA5YP1T11-M01D02-M01B02\雙座標 試加工.f3z`

- 這類檔代表 **「已編好、可上機」的 ground truth**：Setup、工序、刀具、綁定的幾何——正是直覺式／思考式想學的 **「結果單一、工法固定」** 樣本。

---

## 2. 能學到什麼（學習層）

| 可萃取（原則上） | 對插件的價值 |
|------------------|--------------|
| 每個 Setup 的 WCS、工序順序 | L2 雙面劇本、思考式加深 |
| 孔／槽／面銑／輪廓 **工序類型** 與參數 | 對照 `feature_catalog` 概念 |
| 模板來源（`.f3dhsm-template` 名稱或 URL） | 對齊 `dropItems`／KnowledgeDB `template_used` |
| 刀具號、轉速進給（若需） | 輔助 `AIDecisionEngine` 建議區間 |
| 設計幾何簽名（孔徑分佈、通盲孔） | 與掃描結果比對 → 「這類件常選哪模板」 |

**不能**直接把 `.f3z` 當文字丟給 LLM 就當學會——要經 **Fusion API 或批次開檔** 抽出結構化紀錄，再寫入 `knowledge/`。

---

## 3. 現況（插件內）

| 已有 | 尚無 |
|------|------|
| 執行後 `record_execute_training`（面板當次選擇） | 從 `.f3z` 批次匯入 |
| `knowledge_import` MCP（手動餵 JSON 紀錄） | 自動開檔、讀 CAM、對幾何簽名 |
| `knowledge_bootstrap`（規則／MD／模板資料夾掃描） | UNC 路徑監看、`.f3z` 目錄掃描 |

因此：**你提到的試加工.f3z 現在不能一鍵當學習資料**，但可作為 **第一筆人工登錄的驗收件 P02**（見 `INTUITIVE_VALIDATION_PARTS.md`），並作為日後匯入器的標準樣本。

---

## 4. 建議匯入流程（規劃）

```text
.f3z（或已開啟的 Fusion 文件）
    → 解包／Document.open（需在 Fusion 環境或 API）
    → 遍歷 cam.setups → operations
    → 對每工序：特徵類型 + 模板名 + 幾何簽名（孔徑／槽寬…）
    → 名稱對照表（CAM 模板名 ↔ 插件 dropItems.label）
    → knowledge_db.record_operation(..., programming_mode="imported_f3z", confidence=0.85)
    → 可選：與直覺式掃描結果 diff → 寫「教訓」
```

**注意**

1. **網路路徑**：Fusion 須能開啟該 UNC；插件宜支援「使用者選檔」而非寫死 `\\10.4.0.11\...`。  
2. **模板名一致**：範本 CAM 用的模板路徑須與你本機 `CAM360\templates` 一致，否則只能學「工序類型」難學「哪一個下拉」。  
3. **版權／內部資料**：僅公司內網、不離廠學習較合適。  
4. **與直覺式關係**：匯入屬 **學習層**；直覺式執行仍只許 **已定模板**，但建議會更準。

---

## 5. 參考範本資料夾（建議主庫）

桌面 **`Fusion.lnk`** → **`E:\Fusion`**  
參考檔建議放在：

| 路徑 | 用途 |
|------|------|
| **`E:\Fusion\參考範本\`** | 範本根目錄（`README.md`） |
| **`E:\Fusion\參考範本\f3z已編程\`** | 參考檔：**`.f3d`**（設計，可含 CAM）+ **`.f3z`**（封裝） |
| **`E:\Fusion\參考範本\manifest.json`** | 提取清單 |

程式常數：`smart_ai_cam_recognizers/reference_paths.py`

### 手動放入 .f3d（您目前做法）

將已編程或標準 `.f3d` 複製到 **`f3z已編程`** 後：

```bash
python scripts/scan_reference_library.py
```

或 MCP **`scan_reference_library`** → 更新 `manifest.json`。

### 從 D:\輝 補充 .f3z

```bash
python scripts/extract_f3z_from_shortcut.py --clean
```

`--clean` 只覆寫 `.f3z`，**保留** 所有 `.f3d`。

---

## 6. 從已開檔匯入 CAM（三階段已實作）

### 6.1 單檔匯入

1. 在 Fusion **開啟** `E:\Fusion\參考範本\f3z已編程\` 內任一 `.f3d` / `.f3z`（需含 CAM 刀路）。  
2. MCP **`import_cam_from_active_document`**  
   - `scan_geometry:true`（預設）：先跑插件孔／槽掃描，再依刀徑匹配寫入 `geometry`。  
   - `all_setups:false`：僅作用中 Setup。  
3. 每道工序匯出欄位：  
   - **`template_path`**：參數或 blob 中的 `.f3dhsm-template` 檔名  
   - **`template_used`**：顯示名（庫索引或 leaf 解析）  
   - **`geometry`**：`diameter_mm` / `depth_mm` / `hole_type` 等（匹配成功時）  
4. 寫入 **KnowledgeDB**（`programming_mode: imported_f3z`），並在 **`cam匯入快照\`** 留 JSON v1.1。

### 6.2 批次匯入（manifest 佇列）

MCP **`batch_import_reference_library`**（建議 `max_files:1`，避免 UI 凍結）：

| 參數 | 說明 |
|------|------|
| `max_files` | 本步處理檔數（預設 1） |
| `open_file` | 是否自動開啟下一檔（本機 `.f3d` 用 `importToNewDocument`） |
| `close_after_import` | 每檔匯入後關閉 Untitled 分頁（預設 true，避免開太多檔卡死） |
| `scan_geometry` | 開檔後掃描幾何（預設 true） |
| `reset` | 清空已完成／失敗佇列 |
| `retry_failed` | 重試先前失敗項 |
| `status_only` | 只回傳 `batch_import_state.json` 狀態 |

進度檔：`E:\Fusion\參考範本\batch_import_state.json`。

### 6.3 其他 MCP

- **`list_reference_f3z`** / **`list_reference_files`**：參考庫清單 + manifest  
- **`scan_reference_library`**：更新 `manifest.json`（不需 Fusion）

仍建議新件用 **掃描 + 一鍵直覺式** 對照驗收表 P02；匯入用於**已編程範本**沉澱。

手動 JSON：`knowledge_import`（見 `AI_TRAINING.md`）。

---

## 7. 中期實作建議（P2）

| 項目 | 說明 |
|------|------|
| `template_alias.json` | 廠內模板別名 ↔ 插件 label |
| 批次加速 | 多檔排程／背景化（目前逐步 open） |
| 與 **思考式 L1** 並行 | 範本件越多，L0/L1 越穩 |

---

## 8. 相關文件

- `docs/AI_TRAINING.md` — `knowledge_import` / `knowledge_feedback`  
- `docs/PROGRAMMING_MODES.md` — 學習層 vs 使用層  
- `docs/INTUITIVE_VALIDATION_PARTS.md` — 含雙座標試加工登錄列  
