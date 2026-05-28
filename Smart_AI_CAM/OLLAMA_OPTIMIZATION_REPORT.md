# Ollama + Smart_AI_CAM 深度優化報告

> 日期：2026-05-26
> 硬體：Intel + NVIDIA RTX A1000 (4 GB) + Intel UHD 770 (2 GB) + 32 GB RAM
> 模型：cam-helper v4 (FROM qwen2.5:7b, Q4)

---

## 一、優化前 / 優化後對比

| 指標 | 優化前 (v3) | 優化後 (v4) | 變化 |
|---|---|---|---|
| 平均推論速度 | 35.8 tok/s | 36.4 tok/s | +1.5% |
| Tool 主動觸發率 | 60% | **100%** | **+67%** |
| 結構化輸出率 | 0% | 40% | +40% |
| 多輪對話記憶 | 無 | 有（REPL） | ✓ |
| Streaming 輸出 | 無 | 有 | ✓ |
| 三種 tool_call 格式 fallback | 2 種 | 3 種 | +1 |

---

## 二、保留的環境變數（已驗證有效）

```
OLLAMA_HOST              = 127.0.0.1:11434     # loopback only，避 EDR
OLLAMA_MODELS            = E:\Ollama\models    # E 槽存模型
OLLAMA_KEEP_ALIVE        = 24h                 # 模型常駐 24h
OLLAMA_FLASH_ATTENTION   = 1                   # 已證明加速
OLLAMA_GPU_OVERHEAD      = 536870912           # 預留 512MB VRAM 給 Fusion
OLLAMA_NUM_PARALLEL      = 1                   # VRAM 緊，避免 thrashing
OLLAMA_MAX_LOADED_MODELS = 1
```

## 三、實測無效已 Revert 的設定

| 設定 | 理論 | 實測 | 結論 |
|---|---|---|---|
| `OLLAMA_NEW_ENGINE=1` | +5-15% | -10% 以上 | qwen2.5 GGUF 對新引擎不友善 |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | 省 50% KV | 解量化 overhead > 收益 | RTX A1000 算力本就有限 |

→ 兩者均已 revert，回 default。

---

## 四、Modelfile v4 改進重點

1. **tool 決策樹** — 系統提示明確列出「用戶問什麼 → 必呼叫哪個 tool」
2. **R5 規則** — 「呼叫工具時直接呼叫，不要先打字『我來呼叫 XXX 工具』浪費 tokens」
3. **統一回答結構** — 【建議】【參數】【理由】【需確認】4 段
4. **新增 G/M code 速查 + 深徑比經驗法則 + 典型錯誤防範**
5. **新增 6 條 few-shot** — 涵蓋純知識問答、tool 呼叫、G-code 生成、多 tool 並用、表格輸出

## 五、cam_helper_agent.py v2 升級重點

1. **Streaming 輸出** — 邊生成邊印（與 ollama `/api/chat` `stream:true` 整合）
2. **多輪對話歷史** — REPL 模式維持 messages list，模型有記憶
3. **三種 tool_call 格式 fallback**：
   - 標準 `tool_calls` 欄位（ollama 推薦）
   - JSON inline 內嵌 content（qwen2.5-coder 偶爾這樣）
   - 文字格式 `[tool_call: name(args)]`（v4 Modelfile 教的）
4. **彩色 ANSI 輸出** — Win10+ console 自動啟用
5. **進度顯示** — `[knowledge_stats]` 即時顯示後台 tool 呼叫
6. **錯誤恢復** — Ollama 連線失敗自動重試 2 次
7. **REPL 命令** — `:tools` `:reset` `:save` `:stream` `:v` `:help`
8. **CLI 模式** — `python cam_helper_agent.py "問題"` 一次性查詢

---

## 六、實測 multi-turn agent 跑通（重要里程碑）

```
Q: "Smart_AI_CAM 學習庫現在有幾筆資料？"

Round 1 → emit tool_call: knowledge_stats({})
MCP   ← {success:true, total_records:2272, AL6061:1849, S50C:423, hole:1283, ...}
Round 2 → "Smart_AI_CAM 學習庫目前共 2272 筆紀錄，AL6061 約 81%。"
```

**這是 Ollama + MCP + Smart_AI_CAM 三方串通的里程碑。**

---

## 七、未做的優化（與建議）

### B. 模型升級到 14b ❌ **不建議**

| 模型 | 大小 (Q4) | RTX A1000 (4GB) 可行性 |
|---|---|---|
| qwen2.5:7b (現在) | ~4.7 GB | 部分 spillover，36 tok/s |
| qwen2.5:14b | ~9 GB | 大量 spillover，預估 < 10 tok/s |
| deepseek-coder:6.7b | ~4 GB | 適配，但 CAM 知識可能比 qwen2.5 差 |

→ **硬體限制在 7b 區間**，14b 速度會掉到不可用。

### E. KnowledgeDB → LoRA fine-tune ⏸️ **時機未到**

- 學習庫目前 2272 筆，其中 rated_records: 0（沒人工評分）、kept_records: 792
- LoRA fine-tune 需要至少 5000+ 高品質樣本才有顯著改善
- 工程量大（資料前處理、訓練、推論時 load adapter）
- **建議**：先用 Smart_AI_CAM 半年累積到 5000+，再考慮 LoRA

### A. 系統 Python 重裝 ⚠️ **建議補做**

發現 `C:\Users\y00079\AppData\Local\Programs\Python\Python314\` 是空殼安裝（沒 python.exe），先前的清理重裝沒裝完。
目前用 Fusion 內建 Python 跑 cam_helper_agent.py 沒問題，但若要日常 Python 開發、安裝 pip 套件，建議：

```powershell
winget install Python.Python.3.13 --location E:\Python313
```

---

## 八、使用方式

### 互動式 REPL（最常用）

雙擊 `E:\Fusion\插件\Smart_AI_CAM\Cam-Helper-Chat.bat`

或：

```cmd
cd E:\Fusion\插件\Smart_AI_CAM
"C:\Users\y00079\AppData\Local\Autodesk\webdeploy\production\<hash>\Python\python.exe" scripts\cam_helper_agent.py
```

REPL 命令：

```
:help        顯示說明
:tools       列出 7 個 MCP 工具
:reset       清空對話歷史
:save FILE   存對話到 JSON
:stream      切 streaming on/off
:v           切 verbose（看內部 tool 流程）
:q           退出
```

### 一次性查詢

```cmd
python scripts\cam_helper_agent.py "學習庫現在幾筆？"
python scripts\cam_helper_agent.py "AL6061 銑面建議轉速？" --verbose
python scripts\cam_helper_agent.py "問題" --no-stream
```

### 重建 Modelfile（修改 system prompt 後）

```cmd
E:\Ollama\ollama.exe create cam-helper -f "E:\Fusion\插件\Smart_AI_CAM\Modelfile"
```

---

## 九、後續可優化方向（按 ROI 排序）

1. **🟢 高 ROI** - cam_helper_agent.py 加 web UI（FastAPI + 前端，比 REPL 友善）
2. **🟢 高 ROI** - 把 cam_helper_agent.py 整合進 Smart_AI_CAM palette（直接在 Fusion 裡用）
3. **🟡 中 ROI** - Modelfile v5：根據 user 實際對話 log 找出薄弱點再強化
4. **🟡 中 ROI** - MCP 加新 actions：`get_cutting_params`, `simulate_toolpath`, `verify_collision`
5. **🔴 低 ROI** - GPU 升級（RTX 3060 12GB 可跑 14b 或 longer context）
6. **🔴 低 ROI** - LoRA fine-tune（等樣本累積夠再說）
