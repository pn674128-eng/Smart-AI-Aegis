# Smart AI Aegis — 主幹架構（Smart AI CAM Fusion + V8.702 參照）

## 原則

| 角色 | 產品/來源 | 說明 |
|------|-----------|------|
| **主幹** | **Smart AI CAM Fusion** | `E:\ollama\cam-helper-tools\Smart_AI_CAM\` — UI、MCP 9877、學習庫 live |
| **主腦** | **Smart AI Aegis** | `cam-helper-tools\` — Ollama、本機學習庫讀取、`knowledge\mirror` 備份 |
| **參照** | **星空 QuickCAM V8.702** | 僅參考 hole_type / oper_type 結構（NX YAML） |
| **NX** | **Smart AI CAM-NX** | MCP 9878、規則 YAML；NX Open 執行（Phase 2） |

**不複製**星空 DLL、不繞授權。

---

## 三層架構圖

```
                    Ollama + Aegis Store
                           ▲
                           │ 上傳/讀取（唯一入口）
                           │
    ┌──────────────────────┴──────────────────────┐
    │           Smart AI CAM Fusion 主幹            │
    │  palette.html │ MCP 9877 │ feature_scanner   │
    │  semi_auto / intuitive / cutting_resolver     │
    └───────────────┬─────────────────┬─────────────┘
                    │ 唯讀 bridge      │ 對照欄位/方案
                    ▼                  ▼
    ┌───────────────────────┐   ┌─────────────────────┐
    │ Smart AI CAM-NX       │   │ V8.702 參照（文字）   │
    │ MCP 9878              │   │ hole_type.txt       │
    │ hole_rules.yaml       │   │ oper_type_new.txt   │
    │ nx_palette (UI)       │   │ config.ini 結構     │
    │ NX Journal / 未來 DLL │   │ 不執行 XK_Main      │
    └───────────────────────┘   └─────────────────────┘
                    │
                    ▼
              NX 1953 + 公司 NX_CAM_Library
```

---

## Smart AI CAM 主幹（Fusion）— 對 NX 的契約

### UI 區塊（`palette.html`）

| 區塊 | 主幹行為 | NX 對應 |
|------|----------|---------|
| 共用設定 | Setup / 材質 / 機台 | `material_profile` + `scheme_id` |
| 孔表 | 直徑、深度、模板、數量 | `features[]` → `get_semi_auto_plan` |
| 直覺式編程 | eligibility → one_click | `check_semi_auto_eligibility` |
| MCP 進度 | 進度條 + 狀態字 | `nx_palette` 進度區 |
| 6 層切削查表 | query_smart_cutting | `query_smart_cutting`（bridge） |

### MCP 主幹 actions（9877 → NX 9878 對照）

見 `data/platform_parity.yaml`。

### 特徵辨識主幹

Fusion：`feature_scanner` + `machining_feature_catalog` + 射線/官方孔。

NX：`scan_machining_features`（Phase 2 NX Open）+ 同一 `feature_identity` / `hole_id`。

---

## V8.702 參照層（僅資料與流程）

| 星空 | 自有 NX |
|------|---------|
| `Hole_CAM/hole_type.txt` | `data/hole_cam/hole_rules.yaml` |
| `Hole_CAM/oper_type_new.txt` | `data/hole_cam/oper_templates.yaml` |
| `type_number.txt` | `oper_sort` + `gy_name_zh` |
| 加工方案 UI | `data/schemes/*.yaml` |
| `config.ini` | `plugin_config.yaml` |
| `ACTIONS XK_Main` | Journal / 未來 `SmartAINX.dll` |

欄位對照：`docs/V8702_REFERENCE_MAPPING.md`。

---

## 目錄（實作）

```
E:\ollama\cam-helper-tools\
  smart_ai_nx/                 ← NX 實作根
    docs/MASTER_ARCHITECTURE.md
    data/platform_parity.yaml
    data/hole_cam/
    ui/nx_palette.html
    ui/panel_server.py
  store/                       ← Aegis
E:\Fusion\插件\Smart_AI_CAM\   ← 主幹（唯讀）
C:\Users\y00079\NX_CUSTOM\smart_ai_nx\  ← NX 殼
```

---

## 啟動順序（NX 日常使用）

1. `Start-Smart-AI-NX-MCP.bat` — MCP **9878**
2. `Start-SmartAI-NX-Panel.bat` — 側邊 UI（主幹風格）**9879**
3. NX → Smart AI Aegis NX 功能表 / Journal
4. Agent：`Cam-Helper-Chat.bat` — 與 Fusion 共用 Agent，埠不同

---

## 開發優先序

1. ✅ YAML 規則 + MCP semi_auto（已完成）
2. 🔄 NX 側欄 UI `nx_palette`（主幹視覺）
3. ⏳ NX Open 特徵掃描 → 填入孔表
4. ⏳ `run_semi_auto_programming` 建立 UG 工序
5. ⏳ Block UI / DLL 一鍵（可選）
