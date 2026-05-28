# 用 Fusion AI + MCP 做插件缺口稽核

目的：**不執行編程**，只讓 **Autodesk Assistant** 對照「Smart_AI_CAM 能做什麼」與「Fusion CAM／API 一般能做什麼」，列出不足與優先補強項。

---

## 前置

1. Fusion 開啟設計或 CAM 文件  
2. **工具 → 附加模組 → Smart_AI_CAM** 勾選並執行（MCP `127.0.0.1:9877` 才會開）  
3. 可選：開啟含孔的零件，稽核掃描結果更準  

---

## 方式 A — 本機腳本（Cursor / PowerShell）

```powershell
cd "E:\Fusion\插件\Smart_AI_CAM"
python scripts\run_gap_audit_mcp.py
```

產物：

- `docs/_gap_audit_pack.json` — 完整能力清單 + 學習庫統計  
- `docs/_gap_audit_brief.md` — 給人看的摘要  

把 JSON 與 `assistant_prompt_zh` 貼到 Fusion Assistant 即可。

---

## 方式 B — Fusion Assistant（Script Execute）

在 **文字指令** 或 Assistant 請它執行（路徑改成你的增益集目錄）：

```python
import sys
addin = r"E:\Fusion\插件\Smart_AI_CAM"
if addin not in sys.path:
    sys.path.insert(0, addin)
from scripts.fusion_ai_bridge import gap_audit_pack
import json
pack = gap_audit_pack()
if not pack.get("success"):
    raise RuntimeError(pack.get("error", pack))
data = pack.get("data") or pack
ui = adsk.core.Application.get().userInterface
ui.messageBox("稽核包已就緒。請將 Text Commands 輸出的 JSON 複製到 Assistant。\n版本: " + str((data.get("manifest") or {}).get("plugin", {}).get("version")))
print(json.dumps(data, ensure_ascii=False, indent=2))
```

然後對 Assistant 說：

> 我貼上的 JSON 是 Smart_AI_CAM 的 MCP 能力包。請依照其中的 `assistant_prompt_zh` 做繁體中文缺口報告。

---

## 方式 C — 直接 MCP（單行測試）

```powershell
python scripts\fusion_ai_bridge.py get_fusion_ai_gap_audit_pack
```

（需 Fusion 已載入增益集。）

---

## MCP 動作

| action | 說明 |
|--------|------|
| `get_cam_agent_manifest` | 僅能力清單（可不開文件） |
| `get_fusion_ai_gap_audit_pack` | 清單 + 學習庫 live 統計 + 稽核提示詞 |

**稽核時不要呼叫**：`execute_machining_plan`、`run_intuitive_*`、`execute_python_code`（會改 CAM）。

---

## Assistant 應產出的報告結構

1. 插件已覆蓋且合理  
2. Fusion 有、插件未做（對照 `fusion_cam_not_covered`）  
3. 插件有、Fusion 原生較弱或需 ME  
4. 建議優先補強 TOP 5  
5. 可用哪個 MCP action 驗證  

---

## 與 Cursor MCP 的關係

- **同一埠 9877**：Cursor 的 MCP 客戶端與 `fusion_ai_bridge.py` 都是客戶端。  
- **Fusion AI** 沒有直接連 9877 的按鈕，需透過 **Script Execute** 跑橋接腳本。  
- 你若在 Cursor 裡問缺口，可執行 `run_gap_audit_mcp.py` 再把 JSON 給模型分析（不必經 Assistant）。

---

## 相關檔案

- `smart_ai_cam_mcp/agent_manifest.py` — 清單來源  
- `scripts/fusion_ai_bridge.py` — Assistant 橋接  
- `docs/CAM_FEATURE_RECOGNITION_MAP.md` — 辨識對照  
