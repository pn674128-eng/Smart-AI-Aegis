# AI／代理程式載入本專案時的閱讀順序

本檔給 **Cursor 等 AI 編輯器** 在**第一次**或**隔一段時間後**接手本外掛時使用：依序讀取可還原版號語意、近期定案與驗收方式，再進程式碼。  
**文件位置**：**所有 Markdown 僅在 `docs/`**；外掛根目錄**不**放 `.md`，避免重複與過期索引。文中 **`docs/…`** 以外掛根目錄為起點。  
**人類開發者**可略過本檔，但仍建議閱讀 **`docs/行為準則.md`** 與 `docs/版本紀錄.md`、`docs/VERSIONING.md`。

**動手改程式碼前**，必讀 **`docs/行為準則.md`**（含：**§1** 變更前須說明影響並取得同意；若任務涉及**孔加工模板載入、下拉選項、鑽／倒角組合**，必讀 **§8.0～§8.4**，**§8.4** 為技術全文；若任務涉及 **`palette.html` 倒角三選項或「僅倒角模板」**，必讀 **§2.1**）。

---

## 建議順序（由先到後）

1. **`docs/行為準則.md`**（全文；孔模板相關改動時 **§8.4** 不可略）  
   - 取得：協作門檻、鑽孔／預鑽產品原則、訊息與排序等約定；**任何更動原程式碼前須先說明影響並取得同意**。  
   - **§8.0～§8.4**：`TEMPLATE_FOLDER_PATHS`（含 **`holeChamfer`** 孔倒角專用路徑）、**`build_template_maps`**／**`buildDropItems`** 之篩選、**0.2 mm** 直徑容差、**`ALLOWED_CHAMFER_TAGS`**、一般列與 **`isCBLarge`** 列輸出順序等**完整契約**（與 **`docs/版本紀錄.md`** **V1.0303**／**V1.0302**／**V1.0301** 索引、`docs/INTEGRATED_HANDOFF.md` 對齊）；**§8.0.1** 為「每特徵指定資料夾、不以模糊搜尋作主路徑」之產品定案。  
   - 若任務涉及 **槽／CadContours2d／內輪廓**：讀 **§8.5** 與 **`docs/REF_2D內輪廓_loop_edges順序.md`**（**§0.0** **幾何依據**（2D 線／3D 面、特徵對照）；**參考**，非 §8.0～8.4 契約）。  
   - 若任務涉及 **`palette.html` 之 `C0.2`／`C0.3`／不指定倒角** 或 **「僅倒角模板」**：必讀 **§2.1**（全域設定、互斥、與未來外／內輪廓擴充之契約；**不得**擅自縮小範圍或拆語意）。

2. **`docs/VERSIONING.md`**（全文，尤其 §4 升版檢查清單、§7 專案內 Markdown 對照）  
   - 取得：`ADDIN_VERSION` 與 `.manifest`／`palette.html` 的同步規則、辨識刻度（+0.01）、細修（+0.0001）、新增一整條模板＋刀路族時之 **`+1.0000` 數值累加**（例 **`V1.0310`→`V2.0310`**，見 §1）。

3. **`docs/版本紀錄.md`**（從檔案**最上方**往下讀到與當前任務相關的版號為止）  
   - 取得：目前正式版號對應的**功能與辨識範圍**；索引列出的對話紀錄檔名。  
   - **V1.0303**：**`CAM360\templates\{材質}`** 整包索引快取（**`template_fs_cache`**），**`collect_assets_from_folder_path`／`collect_slot_chamfer_assets`** 優先走索引再以 **`templateLibrary.join`** 還原 **`url`**（見 **`docs/版本紀錄.md` V1.0303**、**`docs/行為準則.md` §8.2**）。  
   - **V1.0302**：孔倒角**僅**讀 **`holeChamfer`** 路徑（**`docs/行為準則.md` §8.2**）。  
   - **V1.0301**：「孔加工模板完整契約」**索引表**（細節回 **`docs/行為準則.md` §8.4**）。

4. **`docs/INTEGRATED_HANDOFF.md`**（時間線與定案脈絡：**04-25 ~ 05-04**；與現行 execute／刀路行為對齊）  
   - 取得：baseline 不可踩線、回歸順序與時間線準據。**程式細節**再銜接步驟 5。

5. **`docs/開發對話與變更.md`**（**單一連續**開發日誌；新內容加在檔案**最上方**日期區塊）  
   - **## 2026-05-04**：版號 **`+1.0000`** 累加、當日 **Markdown** 清單、**`docs/REF_2D內輪廓_loop_edges順序.md`** 與 **`docs/行為準則.md` §8.5**。  
   - **## 2026-05-02**：預鑽、CAM、刀路、訊息、未採納優化、MCP、版號 **§8～11**；文末 **English notes**。

6. **`docs/CHECKLIST.md`**（在要改行為或 UI 時，對照「Minimal Suite Per Change」與 §9–§11）  
   - 取得：回歸驗收項；避免改壞已穩定的面板／模板／持久化路徑。

7. **`docs/BASELINE_ALIGNMENT.md`**（當變更牽涉「與既有判定／基線是否一致」時再讀）  
   - 取得：baseline 心智模型與 2026-05-02 文檔同步註記。

8. **`docs/版本紀錄.md`** 內 **## V1.03（2026-05-01）**（歷史凍結敘述；不再另建封存檔）

### 任務含視線法／驗證草圖／`vision/` 時（加讀）

在步驟 1（行為準則）之後、改碼前追加：

1. **`docs/VISION_CONTOUR_AND_SKETCH.md`**（全文）— 多台面外輪廓、槽膠囊、MCP、熱重載約束。  
2. **`docs/VISION_SNAPSHOT_v1.md`** — `vision_snapshot` 欄位與資料來源。  
3. **`docs/RAYVISION_INTEGRATION_PLAN.md`** — Phase 1 狀態與勿改 execute 邊界。  
4. **`docs/開發對話與變更.md`** — **## 2026-05-20**。

### 任務含 AI 系統／腦層／`get_ai_recommendations` 時（加讀）

1. **`docs/PROGRAMMING_MODES.md`** — 學習層 vs 使用層、直覺式 vs 思考式。  
2. **`docs/AI_SYSTEM_ARCHITECTURE.md`**（全文）— 眼／法／腦、MCP。  
3. **`docs/INTUITIVE_PROGRAMMING.md`** — 直覺式白名單、面板與 MCP。  
3b. **`docs/INTUITIVE_VALIDATION_PARTS.md`** — 簡單件驗收登錄表。  
3c. **`docs/F3Z_LEARNING.md`** — 已編程 `.f3z` 作學習資料（規劃）。  
4. **`docs/THINKING_PROGRAMMING.md`** — 思考式 L0（直覺式基底）→ L1/L2。  
5. **`docs/AI_TRAINING.md`** — 學習庫、`knowledge_*` MCP（兩種使用模式共用）。  
6. **`programming_modes.py`**、`intuitive_programming.py`、`thinking_programming.py`、`ai_brain.py`…  
7. **`docs/行為準則.md` §11** — 視線法不得改 execute／baseline。

---

## 讀完後再進程式碼時

- 版號與 Fusion 載入：`半自動加工選單【UI穩定版】.py`（`ADDIN_VERSION`）、`半自動加工選單【UI穩定版】.manifest`、`palette.html`。  
- 若新增「單日大量」對話紀錄：請在 **`docs/開發對話與變更.md` 最上方**新增 `## YYYY-MM-DD` 區塊（**勿**新建平行 `變更紀錄_開發對話_*.md`）；並在 `docs/版本紀錄.md` 索引處補一句指向該日期區塊；**`docs/INTEGRATED_HANDOFF.md`** 時間線亦應補摘要。

---

## 與其他文件的關係

- **`docs/行為準則.md`**：協作與變更門檻（**步驟 1**；含「更動原程式碼前先說明影響並取得同意」）；孔加工模板細節以 **§8.4** 為準據。  
- **`docs/VERSIONING.md` §7**：專案內所有 Markdown 的**用途一覽**（本檔負責**閱讀先後**）。  
- **`docs/INTEGRATED_HANDOFF.md`**：時間線與「現在以何為準」的**單一敘事主檔**（與步驟 4 相同）。  
- **`docs/開發對話與變更.md`**：與其他 md 的**交叉索引**置於各日期區塊開頭（與本檔互補）。
