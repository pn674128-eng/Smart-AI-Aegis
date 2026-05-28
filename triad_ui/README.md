# Smart AI 四方協作 UI

同屏四欄：**Antigravity | Cursor | Aegis | 師父**

## 啟動

1. Ollama 運行中（`smart-ai-aegis`）
2. 雙擊 `Start-Triad-Chat-UI.bat`
3. 瀏覽器開啟 http://127.0.0.1:9880/

## 使用

1. **開始協作** — 建立 ticket + 開場
2. 下方輸入 → **發送 · 四方一輪** — 三欄 AI 同輪回覆，訊息寫入 9876 討論串
3. 可多輪直到滿意，再在 Ollama 對 Aegis 說「提出結論草案 / 核准結案」

## 埠

- **9880** — 本 UI
- **9876** — 協作 ticket（自動背景啟動）

## 模型（可選環境變數）

- `AEGIS_MODEL` / `ANTIGRAVITY_MODEL` / `CURSOR_MODEL`
