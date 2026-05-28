# -*- coding: utf-8 -*-
"""
Smart_AI 記憶與反思層 — 思想庫 (ThoughtDB)
=========================================
• 自動記錄每次加工編程決策的「思考軌跡 (Chain of Thought)」
• 支援雙迴路人機反思 (Retrospective)，讓 AI 能反省自身的思維錯誤並演化
• 思想數據持久化存檔於 memory/data/thoughts.json
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────
#  路徑設定
# ─────────────────────────────────────────────

def _brain_dir() -> str:
    """取得 Smart_AI 大腦核心根目錄。"""
    return os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _data_dir() -> str:
    """記憶存放區。"""
    return os.path.join(_brain_dir(), "memory", "data")


def _thoughts_path() -> str:
    return os.path.join(_data_dir(), "thoughts.json")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


# ─────────────────────────────────────────────
#  JSON 工具
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


# ─────────────────────────────────────────────
#  ThoughtDB 思想庫管理器
# ─────────────────────────────────────────────

class ThoughtDB:
    """
    AI 思想庫管理器，負責思維軌跡的 CRUD 與反思演化。
    """

    def __init__(self) -> None:
        self._thoughts: Dict[str, Any] = {}  # thought_id -> thought_record
        self._dirty = False
        self._load()

    def _load(self) -> None:
        raw = _load_json(_thoughts_path(), {"version": "1.0", "thoughts": []})
        ts = raw.get("thoughts", [])
        self._thoughts = {t["thought_id"]: t for t in ts if isinstance(t, dict) and "thought_id" in t}

    def _save(self) -> bool:
        if not self._dirty:
            return True
        ok = _save_json(_thoughts_path(), {
            "version": "1.0",
            "last_updated": _now_iso(),
            "thought_count": len(self._thoughts),
            "thoughts": list(self._thoughts.values()),
        })
        if ok:
            self._dirty = False
        return ok

    def record_thought(
        self,
        context:        dict,
        cognitive_path: dict,
        decision:       dict,
        session_id:     str = "",
    ) -> str:
        """
        記錄一次決策的思維軌跡。

        Args:
            context:        情境變量 {"feature_type", "material", "geometry"}
            cognitive_path: 思考鏈 {"intent", "observations", "hypothesis", "reasoning_steps"}
            decision:       決策方案 {"recommended_template", "parameters_override"}
            session_id:     會話 ID

        Returns:
            生成的 thought_id
        """
        try:
            tid = "t-" + str(uuid.uuid4())[:8]
            record = {
                "thought_id":     tid,
                "timestamp":      _now_iso(),
                "session_id":     str(session_id or ""),
                "context":        dict(context or {}),
                "cognitive_path": dict(cognitive_path or {}),
                "decision":       dict(decision or {}),
                "reflection": {
                    "user_action":  None,   # None=未執行, "keep"=保留, "modify"=修改, "delete"=刪除
                    "user_rating":  None,   # 1~5 星
                    "retrospective": "等待使用者執行加工工序。"
                }
            }
            self._thoughts[tid] = record
            self._dirty = True
            return tid
        except Exception:
            return ""

    def submit_reflection(
        self,
        thought_id:     str,
        user_action:    str,  # "keep" / "modify" / "delete"
        user_rating:    Optional[int] = None,
        user_comment:   Optional[str] = None,
    ) -> bool:
        """
        雙迴路反思：當使用者在 UI/CAM 刪改工序時，回溯該 thought 並進行反省學習。
        """
        try:
            t = self._thoughts.get(thought_id)
            if not t:
                return False
            
            ref = t.setdefault("reflection", {})
            ref["user_action"] = str(user_action).strip().lower()
            if user_rating is not None:
                ref["user_rating"] = max(1, min(5, int(user_rating)))
            
            # AI 根據回饋自動撰寫 Retrospective (自我反省)
            comment = str(user_comment or "").strip()
            action_s = ref["user_action"]
            
            if action_s == "keep":
                retro = f"思維驗證成功。此加工特徵的物理約束與 API 事實推理完全正確。"
            elif action_s == "delete":
                retro = f"思維失敗反省：使用者完全刪除了此工序！可能原因：餘量判斷過於保守，或大平面無需二次精加工。AI 應在下次減少對類似特徵的重複生成。用戶評語：{comment}"
            elif action_s == "modify":
                retro = f"思維微調反省：使用者修改了加工參數。我們推薦的模板或切削速度被微調。應汲取此修改參數作為高優先權參考。用戶評語：{comment}"
            else:
                retro = f"收到用戶回饋：{action_s}。{comment}"
                
            ref["retrospective"] = retro
            self._dirty = True
            return True
        except Exception:
            return False

    def query_thought_history(
        self,
        feature_type: str,
        material:     str,
    ) -> List[dict]:
        """查詢特定特徵和材料下的歷史思考與反省日誌。"""
        out = []
        ft = str(feature_type).lower()
        mat = str(material).upper()
        for t in self._thoughts.values():
            ctx = t.get("context") or {}
            if str(ctx.get("feature_type")).lower() == ft and str(ctx.get("material")).upper() == mat:
                out.append(t)
        return sorted(out, key=lambda x: x.get("timestamp", ""), reverse=True)

    def get_thinking_statistics(self) -> dict:
        """統計 AI 的思維健康狀態與反思率。"""
        total = len(self._thoughts)
        reflected = 0
        success = 0
        by_intent: Dict[str, int] = {}
        
        for t in self._thoughts.values():
            cp = t.get("cognitive_path") or {}
            intent = cp.get("intent", "未定義意圖")
            by_intent[intent] = by_intent.get(intent, 0) + 1
            
            ref = t.get("reflection") or {}
            if ref.get("user_action") is not None:
                reflected += 1
                if ref.get("user_action") == "keep":
                    success += 1
                    
        return {
            "total_thoughts":     total,
            "reflected_thoughts": reflected,
            "reflection_rate":    round((reflected / total) if total > 0 else 0, 4),
            "success_rate":       round((success / reflected) if reflected > 0 else 0, 4),
            "intents_distribution": by_intent,
        }

    def flush(self) -> bool:
        """強制儲存思想庫至硬碟。"""
        return self._save()


# ─────────────────────────────────────────────
#  單例存取
# ─────────────────────────────────────────────

_thought_db_instance: Optional[ThoughtDB] = None

def get_thought_db() -> ThoughtDB:
    global _thought_db_instance
    if _thought_db_instance is None:
        _thought_db_instance = ThoughtDB()
    return _thought_db_instance
