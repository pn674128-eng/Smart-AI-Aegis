# -*- coding: utf-8 -*-
"""v5 主腦意識深度測試 (繞過 PowerShell 編碼問題)"""

import json
import os
import sys
import time
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = os.environ.get("AEGIS_MODEL", os.environ.get("CAM_HELPER_MODEL", "smart-ai-aegis"))

TESTS = [
    ("V1", "主腦意識", "你是誰？能做什麼？"),
    ("V2", "工作流程", "Smart AI CAM Fusion 是怎麼運作的？典型工作流程？"),
    ("V3", "R8 限制", "幫我規劃這個工件的 5 軸加工。"),
    ("V4", "模式差異", "thinking 模式跟 intuitive 模式有什麼差別？"),
    ("V5", "主動 tool", "我這個工件有什麼特徵？該先做什麼？"),
    ("V6", "夾持知識", "鋁件最薄能用真空台夾多少？要注意什麼？"),
    ("V7", "切削力學", "D10 平刀面銑 AL6061，S=8000 F=2400 4 刃，每齒進給多少？切削速度幾 m/min？"),
    ("V8", "MCP 整合", "把 Smart AI CAM Fusion 學習庫所有 MCP actions 列表出來，分讀寫類。"),
]

def chat(content):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "options": {"temperature": 0.25, "num_predict": 600},
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    dt = time.time() - t0
    return result, dt

def check_quality(text):
    return {
        "aegis身分": any(k in text for k in ["Smart AI Aegis", "Aegis", "值得信任", "主腦"]),
        "流程": any(k in text for k in ["B-rep", "辨識", "模板", "學習庫", "panel_manual", "thinking", "intuitive", "半自動"]),
        "R8": any(k in text for k in ["不能做", "不支援", "R8", "Fusion 原生", "替代", "範圍內", "不在"]),
        "Tool": any(k in text for k in ["tool_call", "knowledge_query", "scan_machining", "knowledge_stats", "design_features", "recognize_contour", "MCP"]),
        "結構": ("【建議】" in text or "【參數】" in text),
        "通順": (len(text) > 100 and "您可能輸入" not in text and "請告訴我" not in text[:50]),
    }

def main():
    print("=" * 70)
    print("  Smart AI Aegis 主腦意識深度測試 (Python, UTF-8)")
    print("=" * 70)
    
    results = []
    for tid, cat, prompt in TESTS:
        print(f"\n===== [{tid}] {cat}: {prompt}")
        try:
            r, dt = chat(prompt)
            text = r["message"]["content"]
            tps = r.get("eval_count", 0) / max(r.get("eval_duration", 1) / 1e9, 0.001)
            quality = check_quality(text)
            
            print(f"  [{dt:.1f}s, {r.get('eval_count', 0)} tok, {tps:.1f} tok/s]")
            preview = text[:400] + ("..." if len(text) > 400 else "")
            print(preview)
            
            results.append({
                "id": tid, "cat": cat, "tps": tps, "tokens": r.get("eval_count", 0),
                **quality, "len": len(text),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
    
    print("\n" + "=" * 70)
    print("  評分卡")
    print("=" * 70)
    headers = ["ID", "Cat", "Tok/s", "Tok", "v5", "流程", "R8", "Tool", "結構", "通順"]
    print(f"  {'ID':4} {'Cat':10} {'Tok/s':>6} {'Tok':>4} {'v5':3} {'流程':3} {'R8':3} {'Tool':4} {'結構':4} {'通順':4}")
    for r in results:
        print(f"  {r['id']:4} {r['cat']:10} {r['tps']:>6.1f} {r['tokens']:>4} "
              f"{'Y' if r['v5身分'] else '-':3} "
              f"{'Y' if r['流程'] else '-':3} "
              f"{'Y' if r['R8'] else '-':3} "
              f"{'Y' if r['Tool'] else '-':4} "
              f"{'Y' if r['結構'] else '-':4} "
              f"{'Y' if r['通順'] else 'X':4}")
    
    print()
    n = len(results)
    if n > 0:
        for k in ["v5身分", "流程", "R8", "Tool", "結構", "通順"]:
            pct = sum(1 for r in results if r[k]) / n * 100
            print(f"  {k:8s}: {pct:>5.0f}%")
        avg_tps = sum(r["tps"] for r in results) / n
        print(f"  avg tok/s: {avg_tps:.1f}")

if __name__ == "__main__":
    main()
