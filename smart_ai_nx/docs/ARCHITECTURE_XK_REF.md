# Smart AI CAM-NX — 以星空為參照的自有外掛架構

> 僅參考公開可見的目錄與資料**結構**，不複製、不繞過星空授權。

## 對照表

| 星空 QuickCAM | Smart AI CAM-NX（自有） |
|---------------|-------------------------|
| `Startup/QuickCAM.men` | `NX_CUSTOM/smart_ai_nx/startup/smart_ai_nx.men` |
| `ACTIONS XK_Main`（註冊 DLL） | Phase 2：`SmartAINXLauncher.dll`；現階段 `UG_JOURNAL_PLAY` |
| `Data_*/Hole_CAM/hole_type.txt` | `data/hole_cam/hole_rules.yaml` |
| `Data_*/Hole_CAM/oper_type_new.txt` | `data/hole_cam/oper_templates.yaml` |
| 加工方案配置 | `data/schemes/*.yaml` |
| `config.ini`（6000+ 行） | `plugin_config.yaml` + `material_profiles.yaml` |
| 內建規則引擎 | `hole_cam.py` + MCP 9878 |
| 雲端/AI | Ollama + Agent + Fusion bridge（唯讀） |

## 資料流

```
NX 模型 / MCP 傳入 features[]
        ↓
feature_identity.py（孔身分、geo_id）
        ↓
hole_cam.match_rule → oper_templates
        ↓
semi_auto.build_semi_auto_plan → steps[].nx_operations[]
        ↓
（Phase 2）NX Open journal 建立 SPOT/DRILL/FACE…
        ↓
公司 cut_methods.dat + query_smart_cutting 填 F/S
```

## 編輯規則

1. **加一種孔**：在 `hole_rules.yaml` 新增 `match` + `operations` 鍵。
2. **加一道 UG 工序**：在 `oper_templates.yaml` 新增 template，並在規則裡引用。
3. **新加工方案**：複製 `data/schemes/default_part_milling.yaml`。
4. **三類材質**：仍用 `material_profiles.yaml`（對應公司 PRT）。

## MCP 測試

```bat
python E:\ollama\cam-helper-tools\smart_ai_nx\test_mcp.py
```

單特徵：

```json
{"action":"nx_match_feature_cam","params":{"feature":{"category":"hole","diameter_mm":10,"tolerance":"H7"},"material_profile":"carbon_steel"}}
```
