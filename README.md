# Smart AI Aegis

> 工具樹：`E:\ollama\cam-helper-tools\`（資料夾名 `cam-helper-tools` 保留，避免破壞路徑）
> 正名說明：`docs\AEGIS_BRANDING.md`  
> 三方校準：`docs\AEGIS_TRIAD_CALIBRATION.md` · 對話直到結論：`docs\AEGIS_TRIAD_DIALOGUE.md`  
> **四方同屏 UI**：`Start-Triad-Chat-UI.bat` → http://127.0.0.1:9880

| 產品 | 角色 | MCP |
|------|------|-----|
| **Smart AI Aegis** | 主腦（Ollama `smart-ai-aegis`） | — |
| **Smart AI CAM Fusion** | Fusion 外掛 | **9877** |
| **Smart AI CAM-NX** | NX 支線 | **9878** |
| **Smart AI CAD** | CAD 核心（讀圖+估價） | **9876** |

## 快速開始（主腦）

1. `Build-Smart-AI-Aegis.bat` — 建立 Ollama 模型 `smart-ai-aegis`
2. `Start-Smart-AI-Aegis.bat` — 對話 REPL
3. **`Start-Aegis-Float.vbs`** 或 **`aegis_float\Start-Aegis-Float.pyw`** — **置頂浮窗**（無黑色命令列；`.bat` 僅轉呼叫 VBS）
4. （可選）`webui\start_webui.bat` — 瀏覽器 UI

## 快速開始

1. 雙擊 `Cam-Helper-Chat.bat` — 主腦 REPL  
2. Fusion：依 `Smart_AI_CAM\DEPLOY_FUSION.md` 載入外掛  
3. 學習庫備份：雙擊 `Sync-Knowledge-Mirror.bat`（或 `python tools\sync_knowledge_mirror.py`）

## 學習庫（合理用法）

- **寫入**：在 Fusion 內執行工序 → `Smart_AI_CAM\Smart_AI\memory\data\`
- **讀取**：主腦 `knowledge_query` / `knowledge_stats` 優先讀上述 live；無則讀 `knowledge\mirror\`
- **備份**：`knowledge\mirror\` 由同步腳本更新，非第二主庫

## 目錄結構

```
E:\ollama\cam-helper-tools\
├── aegis_paths.py              # 路徑與產品正名
├── knowledge_service.py        # 本機學習庫查詢
├── Smart AI CAD\               # CAD 核心（quote_facts + 估價 MCP）
├── Smart_AI_CAM\               # Smart AI CAM Fusion 外掛本體
├── smart_ai_nx\                # NX MCP / 規則
├── knowledge\mirror\           # 學習庫備份
├── store\                      # geo / 案件上傳（Aegis store）
├── agent\cam_helper_agent.py
├── Modelfile
└── tools\sync_knowledge_mirror.py
```

## 建置主腦（正名）

```cmd
Build-Smart-AI-Aegis.bat
```

或：

```cmd
E:\ollama\ollama.exe create smart-ai-aegis -f E:\ollama\cam-helper-tools\Modelfile
set AEGIS_MODEL=smart-ai-aegis
```

舊模型名 `cam-helper` 仍可用：`set CAM_HELPER_MODEL=cam-helper`
