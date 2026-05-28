# Smart AI CAM Fusion — Fusion 360 載入說明

外掛本體位於：

`E:\ollama\cam-helper-tools\Smart_AI_CAM\`

## 方式 A（建議）：junction 到 Fusion AddIns

以系統管理員 PowerShell：

```powershell
$src = "E:\ollama\cam-helper-tools\Smart_AI_CAM"
$dst = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\Smart_AI_CAM"
if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null }
cmd /c mklink /J "$dst" "$src"
```

重啟 Fusion → **附加模組** 中應出現 **Smart AI CAM Fusion**。

## 方式 B：複製

將整個 `Smart_AI_CAM` 資料夾複製到 Fusion AddIns 目錄（更新時需手動再複製）。

## MCP

載入後本機 **127.0.0.1:9877**；主腦 **Smart AI Aegis** 在 `E:\ollama\cam-helper-tools\`。

## 學習庫

- **Live**：`Smart_AI\memory\data\`（執行工序後自動寫入）
- **Mirror**：`E:\ollama\cam-helper-tools\knowledge\mirror\`（執行 `python tools\sync_knowledge_mirror.py`）
