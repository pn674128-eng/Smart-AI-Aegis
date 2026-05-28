# Smart AI CAD

> 開源可自訂的 **CAD 主核心**（讀圖 + 估價），不做 CAM。  
> 商業 CAD（中望、AutoCAD 等）以 **Bridge 延伸** 接入，不取代核心。

## 定位

| 層級 | 角色 |
|------|------|
| **Smart AI Aegis** | 估價大腦、規則、LLM（工具樹根目錄） |
| **Smart AI CAD（本目錄）** | CAD 核心：3D/檔案讀取、`quote_facts`、估價 MCP |
| **`*_bridge_*`** | 各廠 CAD 只負責翻譯圖面 → `quote_facts` |

## 目錄

```
Smart AI CAD/
├── README.md
├── docs/ARCHITECTURE.md
├── schema/quote_facts.schema.json
├── core/quote_engine.py      # 估價公式（確定性）
├── core/facts_merge.py       # 多來源 facts 合併
├── mcp/cad_mcp_server.py     # 本機 MCP（預設 :9876）
└── bridges/
    ├── README.md
    └── zwcad_2d/             # 中望 2D 延伸（Phase 2）
```

## 快速開始

```bat
cd /d E:\ollama\cam-helper-tools
python "Smart AI CAD\mcp\cad_mcp_server.py"
```

測試（需先啟動 MCP）：

```bat
curl -s http://127.0.0.1:9876/health
```

## MCP 埠

- **9876** — Smart AI CAD（本專案）
- 9877 — Smart AI CAM Fusion
- 9878 — Smart AI CAM-NX

## Bridge 對接文件

- `docs/BRIDGE_API_v0.1.md` — 給 Antigravity / 中望 / 其他 CAD Bridge 的 API 協議
- `schema/quote_facts.schema.json` — `quote_facts` JSON 契約
- `docs/AEGIS_CORE_GOVERNANCE.md` — Aegis 主核心治理原則（主從關係、變更路徑、封存要求）

## 授權說明

- 本核心程式碼：專案自有（Bridge 可另授權）。
- 若基於 FreeCAD 客製發行，須遵守 FreeCAD / LGPL 相關義務（見 `docs/ARCHITECTURE.md`）。
