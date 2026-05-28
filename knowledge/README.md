# Smart AI Aegis — 學習庫備份

| 路徑 | 說明 |
|------|------|
| `mirror/` | 自 Smart AI CAM Fusion `Smart_AI\memory\data\` 同步的副本 |
| Live 來源 | `..\Smart_AI_CAM\Smart_AI\memory\data\` |

同步：`Sync-Knowledge-Mirror.bat` 或 `python tools\sync_knowledge_mirror.py`

主腦 `knowledge_query` / `knowledge_stats` 優先讀 **live**，其次 **mirror**。
