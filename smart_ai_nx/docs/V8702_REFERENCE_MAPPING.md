# 星空 V8.702 → Smart AI CAM 主幹 / NX YAML 欄位對照

僅供設計參考，不複製商業程式。

## hole_type.txt → hole_rules.yaml

| 星空 `hole_type` | Smart AI `match` / 欄位 | 備註 |
|------------------|-------------------------|------|
| `FEATURE_TYPE=0` | `feature_type: hole` | 孔 |
| `FEATURE_TYPE=1` | `feature_type: slot` | 槽 |
| `THROUGH=0/1/2` | `through: false/true`（2=不限制則省略） | |
| `SLOPE=0` | `match.angled: true` | |
| `COLOR_ID` | `match.color_id` | 星空依 NX 顏色分組 |
| `DIA` / `MAX_DIA` | `diameter_mm: {min,max}` | |
| `FACE_TYPES` | 待擴 `face_types` | |
| `ATTR_NAME/VALUE` | `attr_name` / `attr_value` | |
| `CAM_OPERS` | `operations: [oper_keys]` | 對 `oper_templates` 鍵 |
| `MATCHING_METHOD` | 規則 `priority` + 多條件 | 簡化為 YAML 順序 |
| `NAME` | `id` + `name_zh` | |

## oper_type_new.txt → oper_templates.yaml

| 星空 | Smart AI |
|------|----------|
| `GY_NAME` | `gy_name_zh` |
| `TEMPLATE_NAME` | `template_name` |
| `TOOL_TYPE` | `tool_type` |
| `TOOL_NAME` | `tool_name_pattern` |
| `DEPTH_TYPE` / `DEPTH_VALUE` | `depth_type` / 參數 |
| `OPER_SORT_NO` | `oper_sort` |
| `THRU_CLEARANCE` | 可擴 `thru_clearance_mm` |

## type_number.txt → 工序語意

星空編號 `0=點孔, 1=鑽孔, 4=攻牙, 28=槽開粗…` 對應 UG 模板族；NX 側用 `oper_key` 抽象，執行期映射 `TEMPLATE_NAME`。

## config.ini → plugin_config.yaml

| 星空區塊 | Smart AI |
|----------|----------|
| `AUTO_CAM_*` | `plugin_config.yaml` + schemes |
| `TOOL_PARAMETER_LIBRARY` | `nx_library_status` + 公司庫 |
| 材質模板 PRT | `material_profiles.yaml` |

## Fusion 主幹（優先於星空 UI）

| Fusion palette | 星空 | NX 實作 |
|----------------|------|---------|
| `material_sel` | config 材質 | `material_profile` |
| 孔表欄位 | hole CAM 對話框 | `nx_palette` 孔表 |
| `run_intuitive_*` | 零件自動編程 | `get_semi_auto_plan` |
| `query_smart_cutting` | 刀庫+模板內建 F/S | bridge 6 層 |

**結論**：特徵分類邏輯可參考星空 txt；**互動與 AI 流程以 Smart AI CAM 為準**。

## 已匯入（v0.3+）

- `data/hole_cam/_xk872_parsed.json`：自 V8.702 `hole_type.txt` 結構解析（55 條）
- `tools/build_hole_rules_from_xk.py` → `hole_rules.json`（約 54 條有效規則 + fallback）
- `data/hole_cam/xk_oper_map.json`：`type_number` 編號 → `oper_templates` 鍵
- 重跑匯入：`python smart_ai_nx/tools/build_hole_rules_from_xk.py`
