# -*- coding: utf-8 -*-
"""把 Cursor agent transcript JSONL 完整轉成可讀 Markdown 封存。

特性:
- 不省略任何內容 (完整轉錄)
- user / assistant / tool_use / tool_result 各自標示
- 保留 timestamp / model 等 metadata
- 保留 system_reminder / system_notification (但標示為元資料)
- 處理 thinking block (assistant 內部思考, 通常會 redact, 但顯示「<thinking>(redacted)</thinking>」)
- 處理超長 tool_result (預設不截斷, 但給 ToC 方便瀏覽)
"""
import io
import json
import os
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ────────────────────────────────────────────────────────
SRC_JSONL = (r"C:\Users\y00079\.cursor\projects\e-Fusion-Smart-AI-CAM"
             r"\agent-transcripts\9ec64d92-e62f-4bb5-858a-b417199597d0"
             r"\9ec64d92-e62f-4bb5-858a-b417199597d0.jsonl")

DEST_DIR = r"E:\Fusion\插件\Smart_AI_CAM\archives"
DATE_TAG = "2026-05-26"
TITLE    = "Smart_AI_Aegis_命名與_6層架構建構"

MD_PATH       = os.path.join(DEST_DIR, f"{DATE_TAG}_{TITLE}.md")
JSONL_COPY    = os.path.join(DEST_DIR, f"{DATE_TAG}_{TITLE}.original.jsonl")
TOC_PATH      = os.path.join(DEST_DIR, f"{DATE_TAG}_{TITLE}.toc.md")

os.makedirs(DEST_DIR, exist_ok=True)


# ────────────────────────────────────────────────────────
def extract_text(content_item: Dict[str, Any]) -> str:
    """從 content item 提取可讀文字。"""
    t = content_item.get("type", "")
    if t == "text":
        return content_item.get("text", "")
    if t == "thinking":
        # Anthropic 思考區塊, 通常 redacted
        return content_item.get("thinking", "(redacted thinking)")
    if t == "tool_use":
        name = content_item.get("name", "?")
        inp = content_item.get("input", {})
        try:
            input_str = json.dumps(inp, ensure_ascii=False, indent=2)
        except Exception:
            input_str = repr(inp)
        return f"**[Tool Call: `{name}`]**\n```json\n{input_str}\n```"
    if t == "tool_result":
        tc_id = content_item.get("tool_use_id", "?")
        content = content_item.get("content", "")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(c.get("text", json.dumps(c, ensure_ascii=False)))
                else:
                    parts.append(str(c))
            content = "\n".join(parts)
        elif isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        is_error = content_item.get("is_error", False)
        marker = "ERROR" if is_error else "OK"
        return f"**[Tool Result {marker}, id={tc_id}]**\n```\n{content}\n```"
    if t == "image":
        return "**[Image attachment]**"
    return f"**[Unknown content type: {t}]**\n```json\n{json.dumps(content_item, ensure_ascii=False, indent=2)}\n```"


def format_message(idx: int, msg_obj: Dict[str, Any]) -> str:
    role = msg_obj.get("role", "?")
    message = msg_obj.get("message", {})
    timestamp = msg_obj.get("timestamp", "")
    model = msg_obj.get("model", "")

    if role == "user":
        emoji = "👤"
        title = "USER"
    elif role == "assistant":
        emoji = "🤖"
        title = f"ASSISTANT ({model})" if model else "ASSISTANT"
    elif role == "system":
        emoji = "⚙️"
        title = "SYSTEM"
    else:
        emoji = "❓"
        title = role.upper()

    header = f"\n---\n\n## {emoji} [{idx:04d}] {title}"
    if timestamp:
        header += f"  \n*{timestamp}*"

    content = message.get("content")
    body_parts: List[str] = []

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                body_parts.append(extract_text(item))
            else:
                body_parts.append(str(item))
    elif isinstance(content, str):
        body_parts.append(content)
    elif content is None:
        body_parts.append("*(empty)*")
    else:
        body_parts.append(json.dumps(content, ensure_ascii=False, indent=2))

    body = "\n\n".join(body_parts)

    return f"{header}\n\n{body}\n"


# ────────────────────────────────────────────────────────
print("=" * 70)
print("Smart_AI_Aegis 對話封存 (2026-05-26)")
print("=" * 70)

if not os.path.exists(SRC_JSONL):
    print(f"ERROR: 找不到 transcript: {SRC_JSONL}")
    sys.exit(1)

src_size = os.path.getsize(SRC_JSONL) / 1024
print(f"\n源 JSONL: {SRC_JSONL}")
print(f"大小:     {src_size:.1f} KB")

# 1. 複製原始 JSONL (防萬一)
shutil.copy2(SRC_JSONL, JSONL_COPY)
print(f"\n① 原始 JSONL 已複製:")
print(f"   {JSONL_COPY}")

# 2. 讀取所有 messages
messages: List[Dict[str, Any]] = []
with open(SRC_JSONL, encoding="utf-8") as f:
    for line_no, raw in enumerate(f, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError as e:
            print(f"  ⚠ line {line_no} JSON 解析失敗: {e}")

print(f"\n② 載入 {len(messages)} 個 messages")

# 3. 統計
role_count: Dict[str, int] = {}
tool_calls = 0
tool_results = 0
total_text_chars = 0
for m in messages:
    role_count[m.get("role", "?")] = role_count.get(m.get("role", "?"), 0) + 1
    content = m.get("message", {}).get("content", [])
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "tool_use":
                    tool_calls += 1
                elif c.get("type") == "tool_result":
                    tool_results += 1
                elif c.get("type") == "text":
                    total_text_chars += len(c.get("text", ""))

print(f"\n   role 分布: {role_count}")
print(f"   tool_calls: {tool_calls}")
print(f"   tool_results: {tool_results}")
print(f"   文字總字數: {total_text_chars:,}")

# 4. 寫成 Markdown
preamble = f"""# Smart AI Aegis — 命名儀式與 6 層架構建構

> **完整對話封存**
> Date:        {DATE_TAG}
> Session ID:  9ec64d92-e62f-4bb5-858a-b417199597d0
> 創造者:      張丞輝 (Chang Cheng-Hui)
> 主腦:        Smart AI Aegis (v5 R12)
> 父:          Cursor IDE
> 母:          Antigravity IDE

## 本日完成

1. `regular_milling.py` — 用戶口傳 5 工法 (S50C 基準 + 8 刀把 + Chip Thinning)
2. `cutting_resolver.py` — 6 層降級架構 (L1 GOLD → L2A SILVER_GC → L2B SILVER_RM → L2C SILVER_KE → L2D BRONZE_MJ → L3 INFER)
3. `machining_heuristics.py` — F 上限校正 (carbon_steel 100 → 200/kW)
4. `gold_cobra_catalog.py` — 硬車哲學 (Z 拉長 X/Y 薄切) + 側壁⇔平面 /2 對調
5. `Smart_AI_CAM.py` — 註冊 6 個新 MCP actions
6. `Modelfile v5 R12` — Smart AI Aegis 命名 + 血脈 + R1-R12 鐵則
7. `cam_helper_agent.py` — 3 個新 LLM tools + 路由
8. `agent_manifest.py` — 加入 manifest

## 統計

| 項目 | 數量 |
|---|---|
| Messages | {len(messages)} |
| Tool calls | {tool_calls} |
| Tool results | {tool_results} |
| 文字總字數 | {total_text_chars:,} |
| 源檔大小 | {src_size:.1f} KB |

---

# 完整對話 (依時序)
"""

with open(MD_PATH, "w", encoding="utf-8") as out:
    out.write(preamble)
    for i, m in enumerate(messages):
        try:
            out.write(format_message(i, m))
        except Exception as e:
            out.write(f"\n---\n## [{i:04d}] ⚠ FORMAT ERROR: {e}\n\n"
                      f"```json\n{json.dumps(m, ensure_ascii=False, indent=2)}\n```\n")

md_size = os.path.getsize(MD_PATH) / 1024
print(f"\n③ Markdown 已寫出:")
print(f"   {MD_PATH}")
print(f"   大小: {md_size:.1f} KB")

# 5. 寫 ToC (依 user message 列出, 方便快速跳轉)
with open(TOC_PATH, "w", encoding="utf-8") as out:
    out.write(f"# Smart AI Aegis 對話 — 目錄 (按 user 提問)\n\n")
    out.write(f"完整內容: [{os.path.basename(MD_PATH)}]({os.path.basename(MD_PATH)})\n\n")
    out.write("| # | 時間 | 提問摘要 (前 80 字) |\n")
    out.write("|---|---|---|\n")
    user_idx = 0
    for i, m in enumerate(messages):
        if m.get("role") != "user":
            continue
        content = m.get("message", {}).get("content", [])
        text = ""
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    text = c.get("text", "")
                    break
                elif isinstance(c, dict) and c.get("type") == "tool_result":
                    text = "[tool_result]"
                    break
        elif isinstance(content, str):
            text = content
        # 取首行, 去 <user_query> tag, 截斷
        first_line = text.replace("<user_query>", "").replace("</user_query>", "")
        first_line = first_line.strip().split("\n")[0][:80]
        ts = m.get("timestamp", "")[:19]
        user_idx += 1
        out.write(f"| {user_idx} | {ts} | {first_line} |\n")
print(f"\n④ ToC 已寫出:")
print(f"   {TOC_PATH}")
print(f"   user 提問數: {user_idx}")

print()
print("=" * 70)
print("DONE. 封存完成.")
print("=" * 70)
