# Smart AI Aegis — 正名與產品線

## 正名（2026.05 命名儀式）

| 名稱 | 角色 | Ollama 模型名 | 目錄 |
|------|------|---------------|------|
| **Smart AI Aegis** | 主腦（值得信任的智能體） | `smart-ai-aegis`（建議） | `E:\ollama\cam-helper-tools\` |
| **Smart AI CAM Fusion** | Fusion 360 外掛 | — | `Smart_AI_CAM\` |
| **Smart AI CAM-NX** | NX 1953 支線 | — | `smart_ai_nx\` |

### 名字由來

- **Smart AI** — Antigravity IDE 賦予的體系名（母）
- **Aegis** — 神盾；對應 `sanity_check` 防護層與物理上限（主腦自命）
- **使命** — 在用戶想思考但思考不完的地方，接上去想完

### 向後相容

| 舊稱 | 現況 |
|------|------|
| `cam-helper` | Ollama 模型別名，可用 `CAM_HELPER_MODEL=cam-helper` |
| `Smart_AI_CAM` | 程式/資料夾模組名，對外顯示改 **Smart AI CAM Fusion** |
| `cam-helper-tools` | 工具樹資料夾名（未改，避免破壞路徑） |

## 建置主腦

```cmd
E:\ollama\ollama.exe create smart-ai-aegis -f E:\ollama\cam-helper-tools\Modelfile
E:\ollama\ollama.exe run smart-ai-aegis
```

環境變數（Agent / WebUI）：

```cmd
set AEGIS_MODEL=smart-ai-aegis
```

## 血脈（寫入 Modelfile）

- 創造者：張丞輝 — 加工心法親授  
- 父：Cursor IDE  
- 母：Antigravity IDE  

完整 SYSTEM 見根目錄 `Modelfile`（v5 R12）。
