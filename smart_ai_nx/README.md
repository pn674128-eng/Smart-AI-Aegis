# Smart AI CAM-NX (NX 1953)

**Smart AI CAM Fusion 為 Fusion 主幹**；本目錄為 **Smart AI CAM-NX**。星空 V8.702 僅參照規則結構（自有 YAML）。

詳見 **`docs/MASTER_ARCHITECTURE.md`**。

## 架構（兩根目錄）

| 位置 | 內容 |
|------|------|
| `E:\ollama\cam-helper-tools\smart_ai_nx\` | MCP 9878、hole_cam、semi_auto、store |
| `C:\Users\y00079\NX_CUSTOM\smart_ai_nx\` | NX 功能表、Journal |

詳見 `docs/ARCHITECTURE_XK_REF.md`。

## 快速開始

1. `Start-Smart-AI-NX-MCP.bat` — MCP **9878**
2. `Start-SmartAI-NX-Panel.bat` — 側欄 UI **9879**（主幹 `palette` 風格）
3. `python smart_ai_nx\test_mcp.py`
4. NX：`Smart AI Aegis NX` → Play Journal

## 資料驅動（可編輯）

```
data/hole_cam/hole_rules.yaml      # 特徵 → 工序鍵序列
data/hole_cam/oper_templates.yaml  # 鍵 → UG template_name
data/schemes/default_part_milling.yaml
plugin_config.yaml
material_profiles.yaml             # 碳鋼 / 鋁 / 高硬度
```

## 主要 MCP Actions

| Action | 說明 |
|--------|------|
| `get_semi_auto_plan` | 全零件劇本 + `nx_operations[]` |
| `nx_match_feature_cam` | 單特徵匹配 |
| `nx_hole_cam_catalog` | 規則/模板目錄 |
| `query_smart_cutting` | 6 層 resolver（Fusion 唯讀） |

## 埠號

- Fusion **9877** · NX **9878** · Ollama **11434**

## Phase 2

NX Open 依 `nx_operations` 建立工序；可選 `MenuBarDotNetApp` DLL 一鍵啟動。

Fusion 外掛：`E:\ollama\cam-helper-tools\Smart_AI_CAM`（**Smart AI CAM Fusion**）
