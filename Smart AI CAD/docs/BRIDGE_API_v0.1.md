# Bridge API v0.1

Smart AI CAD 與外部 Bridge（例如 Antigravity、中望外掛）之間的 HTTP 協作規範。

## Base URL

- `http://127.0.0.1:9876`
- 可由環境變數 `CAD_MCP_HOST` / `CAD_MCP_PORT` 覆寫。

## Transport

- Protocol: HTTP/1.1
- Content-Type: `application/json; charset=utf-8`
- 所有請求採 `POST /` + `action`

## Core Actions

| action | 用途 |
|---|---|
| `set_quote_facts` | 儲存 primary 或 bridge facts |
| `get_merged_facts` | 回傳合併後 facts |
| `run_quote` | 依 facts 執行估價 |
| `clear_quote_facts` | 清空暫存 |
| `load_demo_sample` | 載入示範資料 |
| `assist_create_ticket` | 建立協作 ticket |
| `assist_get_ticket` | 取得 ticket 詳細內容 |
| `assist_list_tickets` | 列出票據摘要 |
| `assist_get_events` | 取得 ticket 事件流（可增量） |
| `assist_watch_tickets` | 輪詢變更的 ticket（UI 通知列） |
| `assist_append_context` | 帶 `if_match_rev` 更新 ticket（含核准） |
| `assist_resolve_ticket` | 結案（必須 `core_approved=true`） |

---

## 1) Health / Manifest

### `GET /health`

回傳服務存活狀態。

**Response**

```json
{
  "ok": true,
  "service": "Smart AI CAD MCP",
  "port": 9876,
  "schema": "quote_facts v0.1"
}
```

### `GET /manifest`

列出版本與支援 actions。

---

## 2) set_quote_facts

Bridge 或核心寫入 `quote_facts`。

### Request

```json
{
  "action": "set_quote_facts",
  "params": {
    "role": "bridge",
    "facts": {
      "schema_version": "0.1",
      "source_id": "zwcad_2d",
      "capabilities": ["2d", "notes"],
      "units": "mm",
      "qty": 100,
      "material": "AL6061",
      "drawing_notes": ["陽極", "去毛刺"],
      "2d": {
        "perimeter_mm": 520.5,
        "block_count": 3
      }
    }
  }
}
```

### Params

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `role` | string | 否 | `primary` 或 `bridge`，預設 `primary` |
| `facts` | object | 是 | 符合 `schema/quote_facts.schema.json` |

### Response

```json
{
  "ok": true,
  "action": "set_quote_facts",
  "result": {
    "stored": "bridge",
    "source_id": "zwcad_2d"
  }
}
```

---

## 3) get_merged_facts

回傳當前 primary + bridge 的合併結果（用於檢查衝突）。

### Request

```json
{
  "action": "get_merged_facts"
}
```

### Response (excerpt)

```json
{
  "ok": true,
  "action": "get_merged_facts",
  "result": {
    "schema_version": "0.1",
    "source_id": "freecad_core",
    "merged_sources": ["freecad_core", "zwcad_2d"],
    "conflicts": []
  }
}
```

---

## 4) run_quote

執行估價。可傳入臨時 facts，也可使用暫存 merged facts。

### Request A: 使用暫存

```json
{
  "action": "run_quote"
}
```

### Request B: 直接帶 facts

```json
{
  "action": "run_quote",
  "params": {
    "facts": {
      "schema_version": "0.1",
      "source_id": "manual",
      "units": "mm",
      "qty": 20,
      "material": "S45C",
      "volume_cm3": 250
    }
  }
}
```

### Response (excerpt)

```json
{
  "ok": true,
  "action": "run_quote",
  "result": {
    "ok": true,
    "currency": "CNY",
    "subtotal": 1234.56,
    "lines": [
      {"item": "材料", "amount": 200.0, "detail": "S45C 1.963 kg/件"},
      {"item": "加工", "amount": 1034.56, "detail": "約 40.0 分/件"}
    ],
    "conflicts": []
  }
}
```

---

## 5) clear_quote_facts

清空記憶體暫存（primary + bridge）。

```json
{
  "action": "clear_quote_facts"
}
```

---

## Error Model

目前服務錯誤回應為：

```json
{
  "ok": false,
  "error": "message"
}
```

建議 Bridge 端內部轉換為以下錯誤碼：

| code | 說明 |
|---|---|
| `BRIDGE_BAD_REQUEST` | 請求格式錯誤（缺 action/params） |
| `BRIDGE_SCHEMA_INVALID` | facts 不符合 schema |
| `BRIDGE_UPSTREAM_4XX` | Core 回傳 400/404 |
| `BRIDGE_UPSTREAM_5XX` | Core 回傳 500 |
| `BRIDGE_TIMEOUT` | 請求逾時 |

## Collaboration Ticket Rules (Aegis Governance)

為符合 `AEGIS_CORE_GOVERNANCE.md`，ticket 端口強制：

1. 更新建議帶 `if_match_rev`（樂觀鎖）；不一致回 `409`.
2. `assist_resolve_ticket` 前必須已核准：`core_approved=true`。
3. 任何狀態/上下文更新都寫入 `events[]`，供審計追溯。

### create ticket

```json
{
  "action": "assist_create_ticket",
  "params": {
    "source": "aegis",
    "type": "schema",
    "summary": "quote_facts add tolerance field",
    "priority": "high",
    "owner": "cursor"
  }
}
```

### append context with revision lock

```json
{
  "action": "assist_append_context",
  "params": {
    "ticket_id": "tkt_xxx",
    "if_match_rev": 12,
    "by": "cursor",
    "patch": {
      "status": "review",
      "reply": "schema updated, waiting core approval"
    }
  }
}
```

### get events (full or incremental)

```json
{
  "action": "assist_get_events",
  "params": {
    "ticket_id": "tkt_xxx"
  }
}
```

```json
{
  "action": "assist_get_events",
  "params": {
    "ticket_id": "tkt_xxx",
    "since_rev": 12
  }
}
```

### watch tickets (polling / notification feed)

適合 Aegis / Antigravity UI 每 2–5 秒輪詢一次。  
第一次不帶 `since_rev`；之後帶上次回傳的 `cursor_rev`。

```json
{
  "action": "assist_watch_tickets",
  "params": {
    "since_rev": 0,
    "status": "open",
    "include_events": true,
    "limit": 20
  }
}
```

**Response (excerpt)**

```json
{
  "ok": true,
  "action": "assist_watch_tickets",
  "result": {
    "cursor_rev": 18,
    "global_next_rev": 19,
    "count": 2,
    "truncated": false,
    "items": [
      {
        "ticket_id": "tkt_abc",
        "status": "review",
        "rev": 18,
        "last_event_type": "context_appended",
        "summary": "..."
      }
    ]
  }
}
```

### approve and resolve

```json
{
  "action": "assist_append_context",
  "params": {
    "ticket_id": "tkt_xxx",
    "if_match_rev": 13,
    "by": "aegis",
    "patch": {
      "core_approved": true
    }
  }
}
```

```json
{
  "action": "assist_resolve_ticket",
  "params": {
    "ticket_id": "tkt_xxx",
    "if_match_rev": 14,
    "by": "aegis",
    "note": "approved and archived"
  }
}
```

---

## Antigravity / Bridge 實作建議

1. 啟動時先 `GET /health`，失敗則禁用「送出估價」按鈕。
2. 讀圖完成後，送 `set_quote_facts(role=bridge)`。
3. 送出估價前先 `get_merged_facts` 顯示 `conflicts[]` 給使用者確認。
4. 使用者按「估價」再呼叫 `run_quote`。
5. 每筆案件結束時呼叫 `clear_quote_facts` 避免跨案污染。

---

## cURL 範例

```bash
curl -s http://127.0.0.1:9876/health

curl -s http://127.0.0.1:9876/ -H "Content-Type: application/json" -d "{\"action\":\"set_quote_facts\",\"params\":{\"role\":\"bridge\",\"facts\":{\"schema_version\":\"0.1\",\"source_id\":\"zwcad_2d\",\"capabilities\":[\"2d\"],\"units\":\"mm\",\"qty\":50}}}"

curl -s http://127.0.0.1:9876/ -H "Content-Type: application/json" -d "{\"action\":\"run_quote\"}"
```
