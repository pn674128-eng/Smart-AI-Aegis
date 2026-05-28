# Smart AI CAM — 內部 AI 訓練說明

> **編程模式**：學習層始終累積概念與案例；使用層分 **直覺式（restricted）**／**思考式（open）**。見 **`docs/PROGRAMMING_MODES.md`**。

## 兩層 AI

| 層級 | 模組 | 是否可訓練 |
|------|------|------------|
| 規則+物理 | ai_decision_engine.py | 否（改材質庫/刀具庫） |
| 學習庫 | knowledge_db.py | 是（執行記錄+回饋；含 `programming_mode`） |

## 訓練流程

1. 掃描 → AI 分析/套用建議 → 檢查面板 → 執行
2. 執行成功後自動寫入 knowledge/
3. 可選 MCP knowledge_feedback 標記保留/評分
4. 下次 get_ai_recommendations 會採用高信心歷史（>=35%）；2D 頂面／外輪廓亦會經 `ai_template_picker` 依學習庫與關鍵字評分選模板

## MCP 動作

- knowledge_stats / knowledge_feedback / knowledge_export
- knowledge_import / knowledge_rebuild_index / knowledge_query
- knowledge_merge_duplicates（合併 (2)(3) 等同義模板索引）
- knowledge_resolve_templates（模板名 → 本機 url 對照）
- get_ai_recommendations

資料目錄: Smart_AI_CAM/knowledge/

## 已編程 `.f3z` 範本

可作為學習資料（工序 + 模板 ground truth），但需匯入管線；現版請先手動開檔比對或 `knowledge_import`。  
詳見 **`docs/F3Z_LEARNING.md`**。