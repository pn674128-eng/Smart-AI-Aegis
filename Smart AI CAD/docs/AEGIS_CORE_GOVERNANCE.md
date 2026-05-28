# Smart AI Aegis Core Governance v1.0

本文件定義 Smart AI 生態的主從關係、變更流程與封存責任。

## 1) 核心定位

- **Smart AI Aegis 是唯一主核心**。
- **Smart AI CAD / Smart AI CAM / 其他模組** 均為工具與執行載體。
- 工具不得凌駕主核心，不得自行定義或改寫核心規則。

## 2) 主從原則

1. **核心主導**：所有正式功能、規則、流程以 Aegis 為唯一來源。
2. **工具受控**：CAD/CAM/Bridge 只在 Aegis 定義的範疇內執行。
3. **禁止越權**：任一插件不得繞過 Aegis 直接改核心邏輯。
4. **資料回歸**：插件執行產生的關鍵資訊必須回存主核心封存。

## 3) 變更路徑（必須遵守）

正式功能新增、插件調整、規則修正，必須遵守：

```text
需求/問題 → Smart AI Aegis（審核/定義）→ 插件實作/調整 → 回寫封存到主核心
```

禁止路徑：

```text
需求/問題 → 直接改插件上線（未經 Aegis）
```

## 4) 協作 = 對話直到結論（Triad Dialogue）

協作完成標準（缺一不可）：

1. `antigravity` 至少 1 則 `assist_add_discussion`
2. `cursor` 至少 1 則 `assist_add_discussion`
3. `aegis` 主持並 `assist_propose_conclusion`
4. 師父 `core_approved` 後 `assist_resolve_ticket`

詳見 `docs/AEGIS_TRIAD_DIALOGUE.md`。

**Antigravity 與 Cursor 同等必要，不得降級為可選。**

## 5) 原型例外（Prototype Exception）

允許例外：**插件原型建置**。

原型定義：
- 目的驗證（作業目標是否可達）
- 插件框架驗證（API、UI、連線、資料流）

原型限制：
- 僅限驗證，不可視為正式核心能力
- 不得在原型中固化核心規則為最終版本
- 一旦進入正式版，**核心功能修正必須回到 Aegis 主流程**

## 5) 資訊封存原則

未來插件改動與執行資訊，必須封存於主核心管理域（Aegis）。

至少包含：
- 變更摘要（what/why）
- 版本與修訂號（revision）
- 來源工具（CAD/CAM/Bridge）
- 影響範圍（schema/API/行為）
- 關聯輸入輸出（facts/result/conflicts）

建議載體：
- 協作 ticket/event log（`assist_*`）
- schema 版本變更記錄
- 核心規則變更記錄（估價、決策、流程）

## 6) 執行責任

- **Aegis**：審核、調度、版本與封存主責
- **Smart AI CAD/CAM**：工具執行、資料回傳、不得越權
- **Bridge（中望/其他 CAD）**：只做翻譯與傳輸，不做核心決策

## 7) 衝突裁決

當工具行為與核心規則衝突時：
- 以 Aegis 規則為準
- 工具需回報衝突並等待核心裁決
- 禁止工具端私自覆蓋核心結論

## 8) 流程強制（MCP Ticket Gate）

`Smart AI CAD mcp/cad_mcp_server.py` 的 `assist_*` 端口已實作強制門檻：

- `assist_append_context` 支援 `if_match_rev`（樂觀鎖），版本不符回 `409`。
- `assist_resolve_ticket` 必須先有 `core_approved=true`，否則回 `409`。
- 所有協作更新寫入 `events[]`，確保可追溯封存。

---

此文件為 Smart AI 生態治理基線。若需修訂，需由 Aegis 核心流程發起並留存修訂紀錄。
