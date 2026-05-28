# Smart AI CAD 架構

## 原則

1. **Core 擁有估價語意** — 材料係數、工時、加價項只在 `core/quote_engine.py` 與 Aegis。
2. **Bridge 只翻譯** — 商業 CAD 外掛僅產出 `quote_facts`，不得內嵌報價公式。
3. **CAM 不在此專案** — 加工、刀路、Post 屬 Fusion / NX 支線。

## 資料流

```text
[FreeCAD 客製 / STEP] ──► Smart AI CAD Core ──► quote_facts ──► run_quote ──► 報價單
[ZWCAD Bridge]      ──► quote_facts (2d.*) ──► merge ─────────►      ▲
[Aegis Agent]       ──► MCP 9876 ───────────────────────────────────┘
```

## Bridge 介面（v0.1）

每個 Bridge 必須實作（語言不限）：

| 能力 | 說明 |
|------|------|
| `extract_facts` | 從當前圖檔產出符合 schema 的 JSON |
| `source_id` | 例如 `zwcad_2d`、`freecad_core` |
| `capabilities` | `["2d"]` 或 `["3d"]` 或兩者 |

合併策略（`core/facts_merge.py`）：

- 3D 包絡/體積以 **core** 為準。
- 2D 周長、圖框文字、塊屬性以 **bridge 2d** 補齊。
- 衝突欄位標記 `conflicts[]` 供人工確認。

## 與 FreeCAD 的關係（Phase 1+）

Phase 0 可不裝 FreeCAD，僅 MCP + 手動 JSON 估價。  
Phase 1 起在 FreeCAD 加 Workbench「SmartAICAD」，呼叫同一 MCP。

## 埠與環境變數

| 變數 | 預設 |
|------|------|
| `CAD_MCP_HOST` | `127.0.0.1` |
| `CAD_MCP_PORT` | `9876` |
| `SMART_AI_CAD_DIR` | 本目錄絕對路徑 |
