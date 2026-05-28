# 本機雙 SDK 協作橋

Antigravity（探索）→ Cursor SDK（實作改檔）→ Antigravity（覆核）→ Aegis（主持）  
全程寫入 **CAD MCP :9876** 協作票 `discussion[]`，避免 IDE 內各說各話。

## 前置

1. `Start-Smart-AI-CAD-MCP.bat` 或讓橋自動啟動 9876  
2. `ollama serve` + `smart-ai-aegis`（Aegis 主持輪）  
3. 可選 SDK：
   - `pip install cursor-sdk` + `set CURSOR_API_KEY=...`
   - `pip install google-antigravity` + `set GEMINI_API_KEY=...`（Windows 可能僅 WSL 有 wheel）

預設為**嚴格模式**：非 Aegis 通道（Cursor/Antigravity）若 SDK 不可用會直接 `blocked`，不再用 Ollama 假補位。
如需舊行為可設定 `BRIDGE_STRICT_NON_AEGIS=0` 允許 fallback。

### Windows + cursor-sdk WinError 10038

本機 `local` bridge 在部分 Windows 會於 `selector.select` 失敗（10038）。**不是你的 key 壞掉。**

可行做法：

1. **Cloud agent**（repo 在 GitHub）：  
   `set CURSOR_CLOUD_REPO=https://github.com/你的帳號/你的repo`  
   `set BRIDGE_CURSOR_RUNTIME=cloud`
2. **本 Cursor 對話窗**直接改 `E:\ollama\cam-helper-tools`（最穩）
3. **協作票流程**：`BRIDGE_CURSOR_MODE=ollama`（有討論、無自動改檔）

## 一鍵執行

```bat
Run-Local-AI-Bridge.bat "E:\ollama\cam-helper-tools\Smart_AI_CAM_Tools" "你的協同修改任務"
```

或：

```bat
python -m bridge run -w "E:\ollama\cam-helper-tools\Smart_AI_CAM_Tools" -t "任務描述"
```

## 環境變數

| 變數 | 用途 |
|------|------|
| `CURSOR_API_KEY` | Cursor 實作輪 |
| `GEMINI_API_KEY` | Antigravity 探索/覆核 |
| `BRIDGE_CURSOR_MODE` | `sdk`（預設）或 `ollama` |
| `BRIDGE_CURSOR_RUNTIME` | `local` / `cloud` / `auto`（**Windows 若 local 出 10038，用 `cloud` 或 `auto`+`CURSOR_CLOUD_REPO`**） |
| `CURSOR_CLOUD_REPO` | GitHub 等遠端 repo URL（cloud 實作輪用） |
| `BRIDGE_AG_MODE` | `sdk`（預設）或 `ollama` |
| `BRIDGE_STRICT_NON_AEGIS` | `1`（預設，SDK 壞就阻塞）/ `0`（允許 fallback） |
| `BRIDGE_REQUIRE_FILE_CHANGE` | `1`（預設，實作輪後必須有 git 檔案變更證據）/ `0`（關閉檢查） |
| `CURSOR_SDK_MODEL` | 預設 `composer-2.5` |
| `CAD_MCP_URL` | 預設 `http://127.0.0.1:9876/` |

## 結案

橋跑完後用 Aegis / 四方 UI：

- `assist_collab_status` 確認三方已發言  
- `assist_propose_conclusion` → 師父認可 → `core_approved` → `assist_resolve_ticket`

### 目標路徑命中檢查（建議）

若工單 `payload` 帶了以下任一欄位：

- `target_paths`
- `target_files`
- `expected_files`

橋會在實作輪後驗證 git 變更是否命中至少一個目標路徑；未命中會 `blocked_target_paths`，不可進結案。

## 四方 UI

`POST /api/bridge/run`  
Body: `{"workspace":"...","task":"..."}`
