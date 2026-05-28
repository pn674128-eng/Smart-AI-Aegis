# ZWCAD 2D Bridge（規劃）

中望 ZWCAD 外掛：讀取當前 DWG → `quote_facts`（`capabilities: ["2d","notes"]`）。

## 待向中望確認

- 推薦 API（.NET / ZRX / COM）
- 讀取：塊屬性、標註、文字、圖層、外框 polyline

## 送出方式

```json
POST http://127.0.0.1:9876/
{
  "action": "set_quote_facts",
  "params": {
    "role": "bridge",
    "facts": { ... }
  }
}
```
