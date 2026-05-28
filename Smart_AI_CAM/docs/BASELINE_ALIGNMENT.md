# 半自動加工選單 基準對照清單

本文件用於鎖定「原始穩定版」辨識邏輯，避免重構或模組拆分後行為漂移。

## 1) 基準來源

- 基準來源：你保留的原始主檔（逐步建立、已實戰驗證）
- 目標：任何新模組（例如 `recognizers/hole_recognizer.py`）必須與基準行為等價

## 2) 核心判定鏈（不可改語義）

1. `rebuildHoleList(...)` 的分組與資料流
2. `_isCounterbore(...)` 沉頭辨識
3. `_isThrough(...)` 通/盲主判斷（孔深 vs 實體上下界）
4. `_getHoleDirection(...)` / `_getCBDirection(...)`
5. `_appendSimpleHole(...)` 深度與方向寫入規則
6. `mergeHoleListByDia(...)` 合併規則

## 3) 射線法定位

- 射線法是輔助辨識訊號，不可單獨取代上述完整判定鏈。
- 若引入射線結果，必須有明確優先級，不可覆蓋基準版已驗證規則。

## 4) 重構對齊表（逐函式）

- [ ] `buildTemplateMaps`：模板映射鍵值與排序保持等價
- [ ] `buildDropItems`：模板組合順序與條件保持等價
- [ ] `makeHoleLabel`：顯示語義保持等價
- [ ] `_isCounterbore`：中心點與拓樸判定保持等價
- [ ] `_isThrough`：容差與邊界判定保持等價
- [ ] `_countHoles`：XY 聚類容差保持等價
- [ ] `_appendSimpleHole`：through/blind 深度寫入保持等價
- [ ] `rebuildHoleList`：分組、雙半徑分支、單分支流程保持等價

## 5) 回歸驗收（每次必跑）

## Setup: `设置1`
- [ ] D3.3 判定正確（通/盲）
- [ ] D4.0 判定正確（通/盲）
- [ ] D5.5 判定正確（通/盲）
- [ ] D10.0（沉頭）判定正確

## Setup: `设置1 (2)`
- [ ] 通/盲分布與基準一致

## Setup: `设置1 (3)`
- [ ] 盲孔深度與數量一致（例如 7.5 / count）

## 6) 變更守則

1. 先比對基準，再改碼。
2. 一次只改一段邏輯，立即回歸。
3. 若與基準不一致，優先回退，不做推測補丁。
4. 對於「看起來更聰明」但改變語義的改法，預設拒絕。

## 7) 任務分工建議

- 原始主檔：語義真值（不可隨意重寫）
- 獨立辨識模組：只做等價抽離與封裝
- 主體流程：呼叫、篩選、整合（不重新定義辨識語義）

---

## 8) AI 機器可讀規範

下面區塊供其他 AI 直接解析。  
規則：若自然語言描述與 YAML 衝突，以 YAML 為準。

```yaml
baseline_spec_version: 1
project: semi_auto_cam
baseline_source: original_main_file

authoritative_pipeline_order:
  - rebuildHoleList
  - _isCounterbore
  - _isThrough
  - _getHoleDirection
  - _getCBDirection
  - _appendSimpleHole
  - mergeHoleListByDia

ray_policy:
  role: auxiliary
  must_not_override_authoritative_pipeline: true
  allowed_usage:
    - accessibility_hint
    - secondary_signal

strict_equivalence_functions:
  - buildTemplateMaps
  - buildDropItems
  - makeHoleLabel
  - _isCounterbore
  - _isThrough
  - _countHoles
  - _appendSimpleHole
  - rebuildHoleList

forbidden_changes_without_explicit_approval:
  - change_through_blind_semantics
  - replace_isThrough_with_ray_only
  - alter_counterbore_branching_logic
  - add_heuristics_overriding_baseline

encoding_requirements:
  file_encoding: UTF-8
  null_bytes_allowed: false

regression_targets:
  - setup: "设置1"
    checks:
      - "D3.3 classification matches baseline"
      - "D4.0 classification matches baseline"
      - "D5.5 classification matches baseline"
      - "D10.0 counterbore classification matches baseline"
  - setup: "设置1 (2)"
    checks:
      - "through/blind distribution matches baseline"
  - setup: "设置1 (3)"
    checks:
      - "blind depth/count matches baseline"

change_process:
  step_order:
    - compare_with_baseline
    - apply_minimal_change
    - run_regression_targets
    - if_mismatch_then_revert
  default_strategy: baseline_first
```

## 9) 文檔同步註記（2026-05-02）

- 已新增完整對話與改動總結：`docs/開發對話與變更.md`
- 本次與 baseline 關聯重點：
  - 未改變 through/blind 權威判定鏈定義
  - 主要修正集中在 UI 顯示同步、模板映射來源、設定持久化
  - 沉頭列顯示策略調整屬 UI 行為收斂，不是語義主判定改寫

