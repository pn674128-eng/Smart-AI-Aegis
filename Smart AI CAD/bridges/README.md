# CAD Bridges（延伸模組）

各商業 CAD **只產出 `quote_facts`**，不實作估價公式。

| Bridge | 狀態 | 能力 |
|--------|------|------|
| `zwcad_2d/` | Phase 2 | DWG/DXF 圖元、圖框、塊屬性 |
| `autocad_2d/` | 規劃 | 同上 |
| `solidworks_3d/` | 規劃 | 質量屬性、孔特徵（簡化） |

## 開發檢查清單

- [ ] `source_id` 唯一
- [ ] 輸出通過 `schema/quote_facts.schema.json`
- [ ] 透過 MCP `set_quote_facts` role=`bridge` 送入
- [ ] 不在 Bridge 內呼叫 `run_quote` 以外之金額邏輯
