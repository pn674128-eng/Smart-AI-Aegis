# -*- coding: utf-8 -*-
"""
AI 學習資料庫核心模組 (KnowledgeDB)
=====================================
• 自動記錄每次加工操作的特徵→模板映射
• 依歷史記錄計算信心分數並推薦最佳模板
• 提供 MCP 接口，讓外部 AI 可查詢、匯出、回饋學習資料
• 資料存放於插件目錄下的 knowledge/ 資料夾（JSON 格式）

資料結構：
    knowledge/
    ├── feature_records.json   ← 歷史加工記錄（主資料庫）
    ├── pattern_index.json     ← 快速查詢索引（自動重建）
    └── session_log.json       ← 本次工作階段日誌
"""
from __future__ import annotations

import json
import os
import re
import time
import traceback
import unicodedata
import uuid
from typing import Any, Dict, List, Optional

# Fusion 複製模板常見後綴：「鑽頭 (2)」
_FUSION_DUP_SUFFIX_RE = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


# ─────────────────────────────────────────────
#  路徑設定
# ─────────────────────────────────────────────

def _plugin_dir() -> str:
    """取得插件根目錄（本檔案在 Smart_AI/memory/ 下）。"""
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _knowledge_dir() -> str:
    return os.path.join(_plugin_dir(), "Smart_AI", "memory", "data")


def _records_path() -> str:
    return os.path.join(_knowledge_dir(), "feature_records.json")


def _index_path() -> str:
    return os.path.join(_knowledge_dir(), "pattern_index.json")


def _session_log_path() -> str:
    return os.path.join(_knowledge_dir(), "session_log.json")


# ─────────────────────────────────────────────
#  信心分數演算法
# ─────────────────────────────────────────────

_FULL_CONFIDENCE_COUNT = 10   # 達到此使用次數即視為滿信心
_DEFAULT_SUCCESS_RATE  = 0.80  # 無用戶回饋時預設成功率


def _calc_confidence(count: int, success_rate: float, material_match: float = 1.0) -> float:
    """
    信心分數 = 使用次數權重 × 成功率 × 材料匹配度

    - 使用次數權重：min(1.0, count / _FULL_CONFIDENCE_COUNT)
    - 成功率：用戶保留率，無回饋時使用預設值
    - 材料匹配度：完全匹配=1.0，跨材料=0.5
    """
    weight = min(1.0, count / _FULL_CONFIDENCE_COUNT)
    score  = weight * success_rate * material_match
    return round(min(1.0, max(0.0, score)), 4)


# ─────────────────────────────────────────────
#  JSON 工具函式
# ─────────────────────────────────────────────

def _load_json(path: str, default) -> Any:
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path: str, data: Any) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


# ─────────────────────────────────────────────
#  幾何特徵正規化（供索引鍵使用）
# ─────────────────────────────────────────────

def canonical_template_name(name: str) -> str:
    """合併學習庫用：去掉 (2) 等複製後綴並 NFKC。"""
    s = str(name or "").strip()
    if not s:
        return ""
    prev = None
    while prev != s:
        prev = s
        s = _FUSION_DUP_SUFFIX_RE.sub("", s).strip()
    try:
        s = unicodedata.normalize("NFKC", s)
    except Exception:
        pass
    return s


def _template_merge_key(name: str) -> str:
    s = canonical_template_name(name).lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)[:120]


def _aggregate_index_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    """將同一語意模板（含 (2)(3) 變體）合併計數。"""
    if not bucket:
        return {}
    groups: Dict[str, Dict[str, Any]] = {}
    for tmpl, entry in bucket.items():
        if not tmpl:
            continue
        mk = _template_merge_key(tmpl)
        if mk not in groups:
            groups[mk] = {
                "display_name": tmpl,
                "display_count": int(entry.get("count", 0) or 0),
                "count": 0,
                "kept_count": 0,
                "total_rating": 0.0,
                "rating_count": 0,
                "last_used": "",
                "aliases": [],
            }
        g = groups[mk]
        if tmpl != g["display_name"] and tmpl not in g["aliases"]:
            g["aliases"].append(tmpl)
        c = int(entry.get("count", 0) or 0)
        g["count"] += c
        g["kept_count"] += int(entry.get("kept_count", 0) or 0)
        g["total_rating"] += float(entry.get("total_rating", 0.0) or 0.0)
        g["rating_count"] += int(entry.get("rating_count", 0) or 0)
        lu = str(entry.get("last_used", "") or "")
        if lu > g["last_used"]:
            g["last_used"] = lu
        if c > g["display_count"]:
            g["display_count"] = c
            if tmpl != g["display_name"] and g["display_name"] not in g["aliases"]:
                g["aliases"].append(g["display_name"])
            g["display_name"] = tmpl
    merged: Dict[str, Any] = {}
    for g in groups.values():
        name = g.pop("display_name")
        g.pop("display_count", None)
        aliases = g.pop("aliases", [])
        if aliases:
            g["merged_aliases"] = aliases
        merged[name] = g
    return merged


def _round_dia(dia_mm: float) -> str:
    """孔徑依 0.1mm 精度正規化，作為索引鍵。"""
    try:
        return str(round(float(dia_mm), 1))
    except Exception:
        return "0.0"


def _feature_key(feature_type: str, material: str, geometry: dict) -> str:
    """產生唯一的特徵查詢鍵。"""
    ft = str(feature_type or "unknown").lower()
    mat = str(material or "").upper()
    if ft == "hole":
        dia = _round_dia(geometry.get("diameter_mm", 0))
        htype = str(geometry.get("hole_type", "general")).lower()
        return f"{ft}|{mat}|{dia}|{htype}"
    elif ft == "slot":
        w = _round_dia(geometry.get("width_mm", 0))
        return f"{ft}|{mat}|w{w}"
    elif ft == "face":
        return f"{ft}|{mat}"
    elif ft == "profile":
        return f"{ft}|{mat}"
    elif ft == "chamfer":
        dia = _round_dia(geometry.get("diameter_mm", 0))
        tag = str(geometry.get("chamfer_tag", "")).upper()
        return f"{ft}|{mat}|{dia}|{tag}"
    else:
        return f"{ft}|{mat}"


# ─────────────────────────────────────────────
#  KnowledgeDB 主類別
# ─────────────────────────────────────────────

class KnowledgeDB:
    """
    AI 學習資料庫管理器。

    Usage（單例模式）：
        from Smart_AI.memory.knowledge_db import get_db
        db = get_db()
        db.record_operation(...)
        best = db.query_best_template("hole", "AL6061", {"diameter_mm": 5.0, "hole_type": "general"})
    """

    def __init__(self) -> None:
        self._records: Dict[str, Any] = {}   # id → record
        self._index:   Dict[str, Any] = {}   # feature_key → summary
        self._session_id = str(uuid.uuid4())[:8]
        self._session_ops: List[dict] = []
        self._dirty = False
        self._load()

    # ── 載入 / 儲存 ────────────────────────────

    def _load(self) -> None:
        raw = _load_json(_records_path(), {"version": "1.0", "records": []})
        recs = raw.get("records", [])
        self._records = {r["id"]: r for r in recs if isinstance(r, dict) and "id" in r}
        self._index   = _load_json(_index_path(), {})

    def _save(self) -> bool:
        if not self._dirty:
            return True
        ok1 = _save_json(_records_path(), {
            "version": "1.0",
            "last_updated": _now_iso(),
            "record_count": len(self._records),
            "records": list(self._records.values()),
        })
        ok2 = _save_json(_index_path(), self._index)
        if ok1 and ok2:
            self._dirty = False
        return ok1 and ok2

    def _save_session_log(self) -> None:
        try:
            prev = _load_json(_session_log_path(), {"sessions": []})
            sessions = prev.get("sessions", [])
            sessions.append({
                "session_id": self._session_id,
                "timestamp":  _now_iso(),
                "ops":        self._session_ops,
            })
            # 只保留最近 50 個 session
            _save_json(_session_log_path(), {"sessions": sessions[-50:]})
        except Exception:
            pass

    # ── 記錄加工操作 ────────────────────────────

    def record_operation(
        self,
        feature_type:        str,
        material:            str,
        geometry:            dict,
        template_used:       str,
        template_path:       str  = "",
        parameters_override: dict = None,
        op_count:            int  = 1,
        programming_mode:    str  = "",
    ) -> str:
        """
        記錄一次加工操作。

        Args:
            feature_type:        特徵類型（"hole"/"slot"/"face"/"profile"/"chamfer"）
            material:            材料代碼（"AL6061"/"S50C"）
            geometry:            幾何參數字典（diameter_mm/depth_mm/hole_type 等）
            template_used:       使用的模板名稱（display name）
            template_path:       模板相對路徑（可選）
            parameters_override: 使用者覆寫的參數（可選）
            op_count:            實際產生的工序數量
            programming_mode:    使用層模式 intuitive / thinking / manual（學習層標記）

        Returns:
            記錄的唯一 ID。
        """
        try:
            rec_id = str(uuid.uuid4())[:12]
            pm = str(programming_mode or "").strip().lower()
            try:
                from Smart_AI.reasoning.programming_modes import usage_tier_for_mode

                usage_tier = usage_tier_for_mode(pm) if pm else ""
            except Exception:
                usage_tier = ""
            record = {
                "id":                   rec_id,
                "timestamp":            _now_iso(),
                "session_id":           self._session_id,
                "programming_mode":     pm,
                "usage_tier":           usage_tier,
                "material":             str(material or "").upper(),
                "feature_type":         str(feature_type or "").lower(),
                "geometry":             dict(geometry or {}),
                "template_used":        str(template_used or ""),
                "template_path":        str(template_path or ""),
                "parameters_overridden": dict(parameters_override or {}),
                "op_count":             int(op_count),
                "outcome": {
                    "applied":    True,
                    "user_kept":  None,   # None = 尚無回饋
                    "rating":     None,   # 1~5 星，None = 尚無評分
                },
            }
            self._records[rec_id] = record
            self._session_ops.append({
                "id":           rec_id,
                "feature_type": record["feature_type"],
                "material":     record["material"],
                "template":     record["template_used"],
            })
            self._dirty = True
            self._update_index(record)
            return rec_id
        except Exception:
            return ""

    # ── 更新索引 ────────────────────────────────

    def _update_index(self, record: dict) -> None:
        """用新記錄更新 pattern_index。"""
        try:
            fkey = _feature_key(
                record["feature_type"],
                record["material"],
                record["geometry"],
            )
            tmpl = record["template_used"]
            if not tmpl:
                return

            if fkey not in self._index:
                self._index[fkey] = {}
            bucket = self._index[fkey]

            if tmpl not in bucket:
                bucket[tmpl] = {
                    "count":        0,
                    "kept_count":   0,
                    "total_rating": 0.0,
                    "rating_count": 0,
                    "last_used":    "",
                }
            entry = bucket[tmpl]
            entry["count"]    += 1
            entry["last_used"] = record["timestamp"]

            # 更新成功率（若有回饋）
            outcome = record.get("outcome") or {}
            if outcome.get("user_kept") is True:
                entry["kept_count"] = entry.get("kept_count", 0) + 1
            if outcome.get("rating") is not None:
                entry["total_rating"] = entry.get("total_rating", 0.0) + float(outcome["rating"])
                entry["rating_count"] = entry.get("rating_count", 0) + 1
        except Exception:
            pass

    # ── 查詢最佳推薦模板 ────────────────────────

    def query_best_template(
        self,
        feature_type: str,
        material:     str,
        geometry:     dict,
    ) -> Optional[dict]:
        """
        依歷史記錄推薦最佳模板。

        Returns:
            {
                "template_name": str,
                "confidence":    float (0~1),
                "use_count":     int,
                "basis":         str,   # 推薦依據說明
            }
            或 None（歷史資料不足）。
        """
        try:
            fkey = _feature_key(feature_type, material, geometry)
            bucket = _aggregate_index_bucket(self._index.get(fkey, {}))
            if not bucket:
                # 嘗試跨材料查詢（降低信心分數）
                return self._cross_material_query(feature_type, material, geometry)

            best_tmpl = None
            best_conf  = -1.0
            best_count = 0
            merged_aliases: List[str] = []

            for tmpl, entry in bucket.items():
                count = entry.get("count", 0)
                kept  = entry.get("kept_count", 0)
                r_cnt = entry.get("rating_count", 0)
                r_tot = entry.get("total_rating", 0.0)

                # 計算成功率
                if count > 0 and kept > 0:
                    success_rate = kept / count
                elif r_cnt > 0:
                    success_rate = (r_tot / r_cnt) / 5.0
                else:
                    success_rate = _DEFAULT_SUCCESS_RATE

                conf = _calc_confidence(count, success_rate, 1.0)
                if conf > best_conf or (conf == best_conf and count > best_count):
                    best_conf  = conf
                    best_tmpl  = tmpl
                    best_count = count
                    merged_aliases = list(entry.get("merged_aliases") or [])

            if not best_tmpl or best_conf <= 0:
                return None

            basis = f"歷史記錄 {best_count} 次（已合併變體名），信心 {best_conf:.0%}"
            if merged_aliases:
                basis += "；變體 {} 筆".format(len(merged_aliases))
            return {
                "template_name": best_tmpl,
                "confidence":    best_conf,
                "use_count":     best_count,
                "basis":         basis,
                "merged_aliases": merged_aliases,
            }
        except Exception:
            return None

    def _cross_material_query(
        self,
        feature_type: str,
        material:     str,
        geometry:     dict,
    ) -> Optional[dict]:
        """在其他材料中尋找相似特徵的記錄（信心分數打折）。"""
        try:
            for mat_alt in ("AL6061", "S50C"):
                if mat_alt.upper() == str(material or "").upper():
                    continue
                fkey = _feature_key(feature_type, mat_alt, geometry)
                bucket = _aggregate_index_bucket(self._index.get(fkey, {}))
                if not bucket:
                    continue
                best_tmpl  = max(bucket, key=lambda k: bucket[k].get("count", 0))
                entry      = bucket[best_tmpl]
                count      = entry.get("count", 0)
                conf       = _calc_confidence(count, _DEFAULT_SUCCESS_RATE, 0.5)
                if conf > 0:
                    return {
                        "template_name": best_tmpl,
                        "confidence":    conf,
                        "use_count":     count,
                        "basis":         f"跨材料 ({mat_alt}) 推薦，信心分數 {conf:.0%}",
                    }
        except Exception:
            pass
        return None

    # ── 用戶回饋 ────────────────────────────────

    def submit_feedback(
        self,
        record_id:  str,
        user_kept:  Optional[bool] = None,
        rating:     Optional[int]  = None,
    ) -> bool:
        """
        接收用戶對某次加工結果的回饋。

        Args:
            record_id: record_operation() 回傳的 ID
            user_kept: True=保留工序, False=刪除工序, None=未知
            rating:    1~5 星評分（可選）
        """
        try:
            rec = self._records.get(record_id)
            if not rec:
                return False
            outcome = rec.setdefault("outcome", {})
            if user_kept is not None:
                outcome["user_kept"] = bool(user_kept)
            if rating is not None:
                outcome["rating"] = max(1, min(5, int(rating)))
            self._dirty = True
            self._update_index(rec)    # 重新以回饋更新索引
            return True
        except Exception:
            return False

    # ── 統計資訊 ────────────────────────────────

    def get_statistics(self) -> dict:
        """取得學習資料庫統計摘要。"""
        try:
            total   = len(self._records)
            by_type: Dict[str, int] = {}
            by_mat:  Dict[str, int] = {}
            rated   = 0
            kept    = 0

            for rec in self._records.values():
                ft  = rec.get("feature_type", "unknown")
                mat = rec.get("material",     "UNKNOWN")
                by_type[ft]  = by_type.get(ft, 0)  + 1
                by_mat[mat]  = by_mat.get(mat, 0)   + 1
                outcome = rec.get("outcome") or {}
                if outcome.get("rating") is not None:
                    rated += 1
                if outcome.get("user_kept") is True:
                    kept  += 1

            top_templates: Dict[str, int] = {}
            for rec in self._records.values():
                tmpl = rec.get("template_used", "")
                if tmpl:
                    top_templates[tmpl] = top_templates.get(tmpl, 0) + 1
            top5 = sorted(top_templates.items(), key=lambda x: x[1], reverse=True)[:5]

            return {
                "total_records":      total,
                "rated_records":      rated,
                "kept_records":       kept,
                "by_feature_type":    by_type,
                "by_material":        by_mat,
                "top_5_templates":    [{"name": t, "count": c} for t, c in top5],
                "pattern_keys":       len(self._index),
                "session_id":         self._session_id,
                "session_ops_count":  len(self._session_ops),
            }
        except Exception:
            return {"error": traceback.format_exc()}

    # ── MCP 接口：匯出 / 匯入 ───────────────────

    def export_for_mcp(self, max_records: int = 200) -> dict:
        """
        匯出學習資料供外部 AI 使用。

        Returns:
            包含 records、pattern_index、statistics 的字典。
        """
        try:
            all_recs = sorted(
                self._records.values(),
                key=lambda r: r.get("timestamp", ""),
                reverse=True,
            )[:max_records]
            return {
                "version":       "1.0",
                "exported_at":   _now_iso(),
                "statistics":    self.get_statistics(),
                "pattern_index": self._index,
                "recent_records": all_recs,
            }
        except Exception:
            return {"error": traceback.format_exc()}

    def import_ai_feedback(self, feedback_list: List[dict]) -> dict:
        """
        接收外部 AI 回饋並更新資料庫。

        Args:
            feedback_list: 列表，每項包含：
                {
                    "record_id":  str,
                    "user_kept":  bool (optional),
                    "rating":     int  (optional),
                    "ai_comment": str  (optional),
                }

        Returns:
            {"updated": int, "skipped": int}
        """
        updated = 0
        skipped = 0
        for fb in (feedback_list or []):
            try:
                rid = str(fb.get("record_id", "")).strip()
                if not rid or rid not in self._records:
                    skipped += 1
                    continue
                kept   = fb.get("user_kept")
                rating = fb.get("rating")
                if self.submit_feedback(rid, kept, rating):
                    # 附加 AI 評語
                    comment = str(fb.get("ai_comment", "")).strip()
                    if comment:
                        self._records[rid].setdefault("ai_notes", []).append({
                            "timestamp": _now_iso(),
                            "comment":   comment,
                        })
                    updated += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
        if updated:
            self._save()
        return {"updated": updated, "skipped": skipped}

    # ── 列出所有推薦 ────────────────────────────

    def query_all_recommendations(
        self,
        material: str,
        min_confidence: float = 0.3,
    ) -> List[dict]:
        """
        列出某材料下所有高信心推薦（供 MCP 外部 AI 建立加工計畫）。

        Returns:
            [{"feature_key", "template_name", "confidence", "use_count"}, ...]
        """
        out = []
        mat = str(material or "").upper()
        try:
            for fkey, bucket in self._index.items():
                if f"|{mat}|" not in fkey and not fkey.endswith(f"|{mat}"):
                    continue
                for tmpl, entry in bucket.items():
                    count = entry.get("count", 0)
                    kept  = entry.get("kept_count", 0)
                    sr    = (kept / count) if count > 0 and kept > 0 else _DEFAULT_SUCCESS_RATE
                    conf  = _calc_confidence(count, sr, 1.0)
                    if conf >= min_confidence:
                        out.append({
                            "feature_key":   fkey,
                            "template_name": tmpl,
                            "confidence":    conf,
                            "use_count":     count,
                        })
        except Exception:
            pass
        return sorted(out, key=lambda x: x["confidence"], reverse=True)

    # ── 重建索引 ────────────────────────────────

    def merge_pattern_index_duplicates(self) -> dict:
        """合併 pattern_index 內同語意模板名（含 (2)(3) 後綴）。回傳統計。"""
        before = sum(len(b) for b in self._index.values())
        new_index: Dict[str, Any] = {}
        merged_groups = 0
        for fkey, bucket in self._index.items():
            merged = _aggregate_index_bucket(bucket)
            if len(merged) < len(bucket):
                merged_groups += 1
            new_index[fkey] = merged
        self._index = new_index
        after = sum(len(b) for b in self._index.values())
        self._dirty = True
        self._save()
        return {
            "feature_keys": len(self._index),
            "template_slots_before": before,
            "template_slots_after": after,
            "keys_with_merges": merged_groups,
        }

    def rebuild_index(self, merge_duplicates: bool = True) -> int:
        """從所有記錄重建 pattern_index。回傳更新的特徵鍵數量。"""
        self._index = {}
        for rec in self._records.values():
            try:
                self._update_index(rec)
            except Exception:
                pass
        if merge_duplicates:
            self.merge_pattern_index_duplicates()
        else:
            self._dirty = True
            self._save()
        return len(self._index)

    # ── 儲存並關閉 ──────────────────────────────

    def flush(self) -> bool:
        """強制寫入磁碟並儲存 session log。"""
        ok = self._save()
        self._save_session_log()
        return ok


# ─────────────────────────────────────────────
#  單例存取
# ─────────────────────────────────────────────

_db_instance: Optional[KnowledgeDB] = None


def get_db() -> KnowledgeDB:
    """取得全局唯一的 KnowledgeDB 實例。"""
    global _db_instance
    if _db_instance is None:
        _db_instance = KnowledgeDB()
    return _db_instance


def reset_db() -> None:
    """重置單例（主要供測試用）。"""
    global _db_instance
    _db_instance = None
