# 直覺式編程（Intuitive Programming）

> **適用**：Smart_AI_CAM V2.0315+  
> **產品定位**：使用層 **「有限制的編程」** — 看懂零件 + 套用**已訂製**模板 + 既有 execute  
> **學習**：概念與 KnowledgeDB **持續運作**（與思考式共用學習層）  
> **風險定位**：**低**（本次決策空間封閉，不發明新工序）

---

## 1. 與思考式、學習層的關係

| 層 | 直覺式 | 思考式 |
|----|--------|--------|
| **學習層** | ✓ 辨識、目錄、案例庫持續累積 | ✓ 同一套 |
| **使用層** | **restricted** — 白名單 + 僅已定模板 | **open** — 開放式編程（規劃中） |

直覺式 **不是** 關掉學習，而是 **這次執行** 不超出安全範圍。  
**思考式**以本白名單與加工路徑為 **L0 基底**，再逐層加深 — 見 **`docs/THINKING_PROGRAMMING.md`**。

架構總覽：**`docs/PROGRAMMING_MODES.md`**、**`docs/AI_SYSTEM_ARCHITECTURE.md` §7～8**。

---

## 2. 白名單（預設）

實作常數見 `smart_ai_cam_recognizers/intuitive_programming.py`：

| 項目 | 預設上限 |
|------|----------|
| 官方長條孔 | 0 |
| 官方口袋槽 | 0 |
| 口袋 R | 0 |
| 槽列 | 24 |
| 圓孔列 | 1～256 |
| 朝上平面層數 | 4 |
| 模板 | 材質須已設定頂面或外輪廓模板路徑 |

**不包含**：自動翻面、第二 Setup 劇本（仍須人工）；複雜件請用面板手動。

---

## 3. 操作流程

### 面板

1. **檢查直覺式資格** — 只掃描與白名單，不改面板  
2. **直覺式編程（套用並執行）** — 資格通過 → AI 建議 → 填入面板 → 既有「先2D後3D」execute  

### MCP

| Action | 說明 |
|--------|------|
| `check_intuitive_eligibility` | 回傳 `eligible`、`checks[]`、`report_text` |
| `run_intuitive_one_click` | **P0 推薦**：模板就緒 + 掃描 + 資格 + 套版 + 執行 |
| `run_intuitive_programming` | 閘門 + `get_ai_recommendations` + 可選 execute（`execute: false` 僅套用） |

`run_internal_ai_autopilot` 預設**停用**（無資格閘門）；請用 `run_intuitive_one_click`。腳本需沿用時傳 `allow_legacy=true`。

---

## 4. 驗收（簡單雙面圓孔板）

- [ ] 僅圓孔板：`check_intuitive_eligibility` → `eligible: true`  
- [ ] 含官方長條孔／口袋槽：`eligible: false`，報告說明原因  
- [ ] 直覺式執行後刀路與「② 套用 AI → 手動執行」一致（同 execute 契約）  
- [ ] 未設定模板路徑：`eligible: false`  

---

## 5. 相關文件

- `docs/AI_SYSTEM_ARCHITECTURE.md`  
- `docs/行為準則.md` — execute／孔 baseline 不可擅自改動  
- `docs/AI_TRAINING.md` — 屬思考型長期，非直覺式必備  
