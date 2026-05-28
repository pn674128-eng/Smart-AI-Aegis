# Smart AI Aegis 三方校準（Triad Calibration）

> 算力合理分配：師父講理論，Antigravity + Cursor 拆解並落地，Aegis 裁決封存。

## 角色

| 角色 | 做什麼 | 不做什麼 |
|------|--------|----------|
| **師父（張丞輝）** | 原則、現場真理、驗收 | 不必手動拆解給 AI |
| **Antigravity** | 探索、原型、Bridge 草案 | 定案核心規則、私自結案 |
| **Cursor** | 收斂、改碼、schema/API、測試 | 繞過 Aegis 上線 |
| **Aegis** | 開票、記錄理論、核准、結案、對外一致 | 假裝已改程式 |

## 三輪流程

```text
① 探索（Antigravity）→ assist_append_context(owner=antigravity)
② 收斂（Cursor）     → assist_append_context(owner=cursor)
③ 裁決（Aegis）      → core_approved=true → assist_resolve_ticket
```

## 一鍵口令：開始AI協作

在 **Ollama** 或 **Aegis REPL** 對主腦說：

```text
開始AI協作
```

主腦會呼叫 `start_ai_collaboration`：

1. 啟動（若未啟動）CAD MCP `:9876`
2. 建立協作會話 ticket
3. 嘗試開啟 **Cursor**（`cam-helper-tools` 專案）
4. 嘗試開啟 **Antigravity**（需設 `ANTIGRAVITY_EXE` 若未自動找到）

師父**繼續在 Ollama 說話即可**；不必手動切 Cursor。

重建模型後生效：`Build-Smart-AI-Aegis.bat`

---

## 簡化版：師父不必一直切換介面

| 你平常只用 | 何時用 |
|------------|--------|
| **Ollama `smart-ai-aegis`** 或 **Aegis REPL** | 問加工、講理論、開協作單、核准結案 |
| **Cursor（本 repo）** | 只有要改程式時打開；說「處理最新協作單」即可 |

一鍵背景服務：`Start-Smart-AI-Workspace.bat`（啟動 9876，不必開黑窗）。

協作單會自動寫入：

- `store/inbox/latest_ticket.json`
- `store/inbox/LATEST_FOR_CURSOR.md`

Cursor 開專案時會依 `.cursor/rules/smart-ai-triad.mdc` 自動看到待辦。

**Antigravity**：非日常必開；做 2D Bridge 原型時再用，結果可貼給 Cursor 或 POST 9876。

---

## 在 Aegis REPL 怎麼用

1. 執行 `Start-Smart-AI-Workspace.bat` 或 `Start-Smart-AI-CAD-MCP.bat`（9876）
2. 啟動 `Start-Smart-AI-Aegis.bat`（或只用 Ollama）
3. 對 Aegis 說需求，例如：
   - 「幫我改 Fusion 插件 XXX」
   - 「校準硬車理解：Z 長吃 XY 薄吃」
4. Aegis 會 `assist_create_ticket` 並給 **ticket_id**
5. 到 **Cursor** 說：`請處理 ticket tkt_xxxxxxxx`
6. 完成後回 Aegis 核准結案

## 重建模型（改 Modelfile 後）

```cmd
Build-Smart-AI-Aegis.bat
```

## 相關文件

- `Smart AI CAD/docs/AEGIS_CORE_GOVERNANCE.md`
- `Smart AI CAD/docs/BRIDGE_API_v0.1.md`
