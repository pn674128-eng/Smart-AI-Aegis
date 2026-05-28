# Semi-Auto Machining Add-In Regression Checklist

## Preconditions
- [ ] Fusion 360 starts normally
- [ ] A test Design document is open
- [ ] Switched to Manufacture workspace
- [ ] At least one Setup exists
- [ ] Add-in button is visible

## 1) Startup and Init
- [ ] Open panel without errors
- [ ] Setup dropdown has valid active setup
- [ ] Default material is correct
- [ ] Hole/slot list renders expected state

## 2) Setup and Rescan
- [ ] setup_change refreshes hole/slot list
- [ ] rescan rebuilds list from current geometry
- [ ] sync_display does not rescan when unchanged
- [ ] sync_display rescans when geometry changes

## 3) Material and Templates
- [ ] material_change updates template options
- [ ] tmpl_change updates row visibility correctly
- [ ] Missing template paths show warning

## 4) Depth and Calculations
- [ ] depth_change updates calc message correctly
- [ ] Through-hole rows skip depth calc
- [ ] Reamer-related calc appears only when applicable

## 5) Settings and Persistence
- [ ] settings_update applies panel size
- [ ] save_defaults persists values after reopen
- [ ] rayDiameterDeltaMM affects recognition after rescan

## 6) Diagnostics
- [ ] diag_toggle opens diagnostic panel
- [ ] hole_debug_toggle emits raw/merged logs
- [ ] debug off stops verbose output
- [ ] dump_op_params outputs active setup params

## 7) Execute
- [ ] execute runs without crash
- [ ] Success path shows completion message
- [ ] Failure path shows readable error message

## 8) Stability and Edge Cases
- [ ] No-hole model handled safely
- [ ] Large model remains responsive
- [ ] Document switch and return still works
- [ ] Restart Fusion and re-verify baseline

## Minimal Suite Per Change
- [ ] Section 1
- [ ] Section 2
- [ ] Section 3
- [ ] Section 7
- [ ] Section 6
- [ ] Section 13 — when changing `vision/`, `recognizers/contour_recognizer.py`, or draw-vision-sketch path
- [ ] Section 12 — when changing `templates/template_fs_cache.py`, `templates/template_service.py`, or palette rescan / reload paths that affect template lists

---

## 2026-05-02 Supplement (UI/Template Stabilization)

### 9) UI Switching (countersink-focused)
- [ ] Countersink row does not show drill-depth controls unexpectedly
- [ ] Switching template does not leave stale depth/pitch controls
- [ ] Row-level visibility stays stable after repeated template toggles

### 10) Template Mapping Accuracy
- [ ] Through-hole rows do not include countersink templates
- [ ] `D6.5` style missing-drill case shows clear per-diameter warning
- [ ] Slot templates remain isolated from normal hole template list

### 11) Settings Persistence
- [ ] Chamfer interference values survive `rescan`
- [ ] `save_defaults` persists across add-in restart
- [ ] Execute uses current UI values, not stale defaults

### 12) V1.0303 — Local `CAM360\templates` index (`template_fs_cache`)
- [ ] With templates under `%AppData%\Roaming\Autodesk\CAM360\templates\{material}\…`, slot and contour-chamfer dropdowns list the same `.f3dhsm-template` files you see on disk (after **full rescan** or first full palette load for that material)
- [ ] Change material in the panel: drill/chamfer/slot options refresh; no crash if a material folder is missing
- [ ] **Second palette open** when the main drill map is already cached (code path that only reloads slot / contour chamfer): after adding or renaming a template file on disk, reopening the panel shows the updated list (cache invalidated on that path)
- [ ] **Fallback**: if the `CAM360\templates` tree is absent or does not contain the configured subfolders, template lists still populate via Fusion API / prior scan behavior (no empty silent failure)

### 13) Vision layer — contour sketch (2026-05-20)
- [ ] `ENABLE_VISION_LAYER=True`: rescan then init JSON shows `vision.ok` and contour counts
- [ ] Grooved dual-pad part: `SemiAuto_VisionSketch` has **both** left and right outer contours (not left-only)
- [ ] Grooved part: slot drawn as loop or capsule, **not** rectangle box around racetrack
- [ ] Flat single-top part: outer contour still ~8 edges (no regression)
- [ ] `ENABLE_VISION_LAYER=False`: hole list / execute unchanged vs baseline
- [ ] After code change: disable/enable add-in; clear `__pycache__`; Python sources UTF-8 (no Fusion `null bytes`)
- [ ] Draw sketch without prior rescan shows message requiring scan first

### Reference
- Release notes: `docs/版本紀錄.md`（**V1.0303** 與後續版節）
- Vision handoff: `docs/VISION_CONTOUR_AND_SKETCH.md`
- 開發過程與（若有）英文紀要：**`docs/開發對話與變更.md`** — 依日期 **`## YYYY-MM-DD`**；同日若有英文摘要，見該檔文末 **English notes** 區塊（單檔連續維護，無另開 `CHAT_AND_CHANGELOG_*.md`）。
