# 思考式編程（Thinking Programming）

> **設計原則**：以 **直覺式編程** 為啟發與基底 —— 先沿用其加工方式，再在此之上往深層探索。  
> **模組**：`Smart_AI/reasoning/thinking_programming.py`、`Smart_AI/reasoning/thinking_l2_plan.py`

---

## 1. 為什麼「直覺式優先」

| 問題 | 做法 |
|------|------|
| 思考式若從零發明刀路 | 風險高、難驗收、與店規脫節 |
| 直覺式已驗證的路徑 | 掃描 → 已定模板 → execute |
| 思考式應做什麼 | **在相同基底上** 擴特徵、排程、多 Setup，而非重寫底層 |

```text
直覺式（種子）
   │  相同：辨識、panel_apply、execute 契約
   ▼
思考式 L0 — 加工結果與直覺式一致，標記 thinking 供學習
   ▼
思考式 L1 — 放寬特徵（口袋 R、官方槽／口袋、多階台面 Z）
   ▼
思考式 L2 — 雙 Setup 劇本：Setup1 頂面+孔+2D/3D → 翻面 → Setup2 背面通孔
```

學習層（概念、KnowledgeDB）兩者 **共用**；差異在使用層 **能探索多深**。

---

## 2. 層級定義

| 層級 | 代號 | 狀態 | 說明 |
|------|------|------|------|
| **L0** | `L0_intuitive_baseline` | **已實作** | 須通過直覺式白名單；加工與直覺式相同；`programming_mode=thinking` |
| **L1** | `L1_extended_features` | **已實作** | 在 L0 的 plan 上允許更多特徵（口袋 R、官方槽／口袋、多階台面），仍僅用已定模板 |
| **L2** | `L2_deeper_plan` | **已實作** | 須 **L0 + L1 資格** 且存在 **Z− 通孔**；產生雙 Setup JSON 劇本，Setup1 後 **人工翻面** |

**L0 不是「簡化版思考式」**，而是 **「思考式的可靠地基」**。

---

## 3. L2 多 Setup 流程（V2.0358+）

1. **資格**：`check_thinking_eligibility` + `thinking_layer=L2_deeper_plan`  
   - L0 直覺式白名單  
   - L1 擴展白名單（L2 建議走 L1 AI 計劃）  
   - 至少一個 **Z− 通孔**（不含 Z−(CB) 背面沉頭）

2. **Setup1**（`run_thinking_programming`，預設）：  
   - 以 **L1** 取得 AI 建議 → **validate_panel_apply + 2D 模板驗證**  
   - 產生 `multi_setup_plan`（含 `hole_identity` 綁定）  
   - 執行頂面 Setup：**Z+ 孔 + 全部 2D/3D**  
   - 劇本 **持久化** 至 `Smart_AI/memory/data/l2_plans/`

3. **翻面檢查點**：暫停；使用者翻面並設定 **AI_Setup_Bottom** WCS。

4. **Setup2**（`resume_from_sequence=2` + `confirm_flip=true`）：  
   - 可從磁碟重載劇本（`get_multi_setup_plan`）  
   - 重掃後以 **孔指紋** 重映射 `rows`  
   - 僅執行 **Z− 通孔**（無 2D/3D）

---

## 4. MCP / 面板

| Action | 說明 |
|--------|------|
| `check_thinking_eligibility` | 可傳 `thinking_layer`：`L0_intuitive_baseline` / `L1_extended_features` / `L2_deeper_plan` |
| `run_thinking_programming` | L2 Setup1；Setup2 傳 `resume_from_sequence=2`、`multi_setup_plan_id`、`confirm_flip=true` |
| `get_thinking_layers` | 已實作層級與 L2 參數說明 |
| `get_multi_setup_plan` | 讀取快取或磁碟上的 L2 劇本 JSON |

面板：**思考式 L2 Setup1** / **L2 繼續 Setup2**（翻面確認後帶 `confirm_flip`）。

直覺式按鈕仍為 **日常預設**；思考式供「同一套加工、另一條使用層標記 + 加深探索」。

---

## 5. 實作路線

1. **L0**（已完成）— 與直覺式刀路一致，標記 thinking。  
2. **L1**（已完成）— 擴展特徵 + 多階台面 + CAM 深度上下文。  
3. **L2**（進行中）— 雙 Setup 劇本、孔指紋重映射、磁碟持久化、WCS 確認閘門。  
4. **後續** — 外部 LLM plan 增量 + `apply_l2_plan_delta` 驗證 API（規劃）。

每一層都必須回答：**若 L0 失敗，本層不得執行。** L2 另需 **L1 通過**。

---

## 6. 相關文件

- `docs/PROGRAMMING_MODES.md` — 學習層 vs 使用層  
- `docs/INTUITIVE_PROGRAMMING.md` — 直覺式白名單（L0 必過）  
- `docs/AI_SYSTEM_ARCHITECTURE.md` §7  
