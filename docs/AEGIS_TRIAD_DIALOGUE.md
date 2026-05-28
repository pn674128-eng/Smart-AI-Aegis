# 三方協作：對話直到結論

> 協作 ≠ 開票。協作 = **Antigravity + Cursor + Aegis 在 ticket 上多輪討論**，達成**結論草案**，師父認可後寫入主腦。

## 三方（同等必要）

| 角色 | 討論輪 | 禁止 |
|------|--------|------|
| **Antigravity** | `explore` / `challenge` | 被省略或標為可選 |
| **Cursor** | `converge` | 只改碼不發言 |
| **Aegis** | `facilitate` / 綜述 | 未聽兩方就下結論 |
| **師父** | `theory` | 被迫拆解給 AI |

## 流程

```text
開始AI協作
  → 開 ticket + Aegis 主持開場
  → Antigravity 探索發言（必須）
  → Cursor 收斂發言（必須）
  → （可多輪 challenge / facilitate）
  → Aegis assist_propose_conclusion（三方皆發言後）
  → 師父認可 → core_approved → resolve
```

## 四方同屏 UI（推薦）

雙擊 **`Start-Triad-Chat-UI.bat`** → 瀏覽器 **http://127.0.0.1:9880**

四欄同屏：Antigravity | Cursor | Aegis | 師父。  
輸入一句 → 三欄 AI **同輪回覆**，全部寫入 9876 討論串。

---

## 師父在 Ollama 口令（亦可並用）

| 口令 | 作用 |
|------|------|
| `開始AI協作` | 啟動三方 + 開討論 |
| `協作進度` | 誰還沒發言 |
| `繼續討論` | 讀討論串、推進 |
| `提出結論草案` | Aegis 綜述（需三方已發言） |
| `核准並結案` | 寫入主腦 |

## Antigravity 發言

在 Antigravity 對話說：

```text
參與協作 tkt_xxxxxxxx
探索輪：（你的觀點）
```

或：

```cmd
python tools/antigravity_collab_post.py tkt_xxxxxxxx explore "你的觀點..."
```

## 誠實邊界

目前 **Antigravity / Cursor 不會自動在背景互相聊天**；討論輪需各方各發言一次（或透過腳本 POST）。  
**Aegis 在 Ollama 可讀完整討論串並綜述**，師父只需對 Aegis 說話即可掌握全貌。
