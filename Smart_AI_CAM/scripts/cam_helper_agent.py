# -*- coding: utf-8 -*-
"""
Smart AI Aegis Agent v2 — Ollama (smart-ai-aegis / cam-helper) + MCP (127.0.0.1:9877) tool calling.

v2 升級重點:
    * Streaming 輸出（邊生成邊印，UX 大幅改善）
    * 多輪對話記憶（REPL 維持 messages 歷史）
    * 三種 tool_call 格式 fallback（標準 / JSON 嵌入 / [tool_call: xxx] 文字）
    * 彩色 ANSI 輸出（Win10+ 自動支援）
    * 自動重試 Ollama 暫時斷線
    * REPL 指令:
        :q          退出
        :v          切 verbose
        :tools      列出 MCP 工具
        :reset      清空對話歷史
        :save FILE  存對話到檔
        :stream     切 streaming on/off
        :help       顯示說明

執行：
    python scripts\\cam_helper_agent.py
    （啟動互動式 REPL；輸入 :q 或 Ctrl+C 結束）

也可單次提問：
    python scripts\\cam_helper_agent.py "學習庫現在幾筆？"

前提：
    1. Ollama 在 127.0.0.1:11434 跑著 smart-ai-aegis (或 cam-helper) 模型
    2. Fusion 360 已載入 Smart_AI_CAM 外掛（MCP 9877）
       — 若 MCP 離線，Agent 仍會回應，但會明確標示「離線」
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
from typing import Any, Dict, List, Optional, Iterator, Tuple

import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Win10+ enable ANSI escape (no-op on Linux/Mac)
if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# ---------- 設定 ----------

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("CAM_HELPER_MODEL", "smart-ai-aegis")
MCP_HOST = os.environ.get("CAM_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("CAM_MCP_PORT", "9877"))
MAX_TOOL_ROUNDS = 5
MAX_TOOL_RESULT_CHARS = 4000
HTTP_TIMEOUT = 180
RETRY_OLLAMA = 2  # Ollama 連線失敗自動重試次數

# ---------- 顏色 ----------

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    GRAY    = "\033[90m"

def _color(txt: str, c: str) -> str:
    if not sys.stdout.isatty():
        return txt
    return f"{c}{txt}{C.RESET}"


# ---------- MCP Tools 定義 ----------

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_stats",
            "description": "查 Smart_AI_CAM 學習庫統計（總筆數、按材質/特徵類型分布）。不需開啟 Fusion 文件。當使用者問『學習庫幾筆』『有多少資料』時用此工具。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_query",
            "description": "查特定特徵的歷史模板紀錄。不需開啟 Fusion 文件。當使用者要查『AL6061 上 M8 攻牙的歷史』『某直徑某材質的記錄』時用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_type": {
                        "type": "string",
                        "description": "特徵類型，可選: hole / slot / face_plane / outer_contour / chamfer_bevel / pocket_corner_r / official_pocket",
                    },
                    "material": {
                        "type": "string",
                        "description": "材質，常見: AL6061, S50C",
                    },
                    "geometry": {
                        "type": "object",
                        "description": "幾何參數（可選），例: {\"diameter_mm\":8.0,\"hole_type\":\"tap\"}",
                    },
                },
                "required": ["feature_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_addin_info",
            "description": "查 Smart_AI_CAM 版號、當前 Setup 狀態、坯料尺寸等系統資訊。不需文件但有文件時資訊更完整。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cam_agent_manifest",
            "description": "查插件能力清單（支援的特徵類型、MCP actions、模板路徑鍵）。不需開啟 Fusion 文件。當使用者問『插件能做什麼』『有哪些功能』時用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reference_f3z",
            "description": "列出可匯入學習的 .f3z 樣本檔（E:\\Fusion\\參考範本\\f3z已編程）。不需開啟 Fusion 文件。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_machining_features",
            "description": "掃描當前 Fusion 文件，回傳完整 feature_catalog（孔、槽、外輪廓、平面、倒角等）。**需要開啟 Fusion 文件**。當使用者問當前模型有什麼特徵、辨識結果時用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "material": {
                        "type": "string",
                        "description": "材質，預設由 Setup 決定；可指定 AL6061 / S50C",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ai_recommendations",
            "description": "對當前文件取得 AI 完整方案（decisions + panel_apply + recommended_templates）。**需要開啟 Fusion 文件**。當使用者要 AI 建議參數/模板時用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },

    # ────────── ★ 智能切削參數 6 層解析 ──────────
    {
        "type": "function",
        "function": {
            "name": "recommend_smart_cutting",
            "description": (
                "★主入口★ 給材質+刀徑+工法 → 自動套用 6 層解析給最高信賴度 RPM/Feed/AE/AP."
                "順位: L1 本地 preset > L2A GoldCobra (HRC≥48 硬車) > L2B 用戶 5 工法 "
                "(regular_milling, S50C/AL/SUS) > L2C 奇力揚 > L2D 銘九通用 > L3 推斷. "
                "任何 RPM/F/AE/AP 問題, 此為首選."),
            "parameters": {
                "type": "object",
                "properties": {
                    "material":     {"type": "string",
                                     "description": "工件 (AL6061/S50C/SKD11/NAK80/SUS304/Ti-6Al-4V/Inconel...)"},
                    "tool_dia":     {"type": "number",
                                     "description": "刀徑 mm (鑽頭/絞刀用直徑, 攻牙用螺紋外徑)"},
                    "operation":    {"type": "string",
                                     "description": "工法 (面銑/側銑/孔銑/滿刃銑/插銑/contour/adaptive/...). 命中 5 工法之一會啟用 L2B 用戶心法"},
                    "feature_type": {"type": "string",
                                     "description": "Fusion 特徵類型 (hole/face/contour/pocket/ball/chamfer)"},
                    "holder":       {"type": "string",
                                     "description": "刀把: ER/SK/pullback(後拉式)/shrink_fit/hydraulic/weldon. 滿刃銑用 pullback"},
                    "coolant":      {"type": "string",
                                     "description": "flood(切削油, 預設) / air(吹氣) / dry"},
                    "hardness_hrc": {"type": "number",
                                     "description": "工件硬度 HRC (重要! SKD11+HRC60 ≠ SKD11+退火)"},
                    "hole_diameter":{"type": "number",
                                     "description": "孔銑用孔直徑 mm (LLM 算螺旋空間)"},
                    "cutting_pattern": {"type": "string",
                                     "description": "sidewall(側壁, 預設) / face(平面). GoldCobra NXE 兩者 AE/AP 對調"},
                    "mode":         {"type": "string",
                                     "description": "conservative(散件 75/50 折, 預設) / aggressive(量產)"},
                    "teeth":        {"type": "integer",
                                     "description": "刃數 (預設 4)"},
                    "chip_thinning_compensation": {"type": "number",
                                     "description": "0.0~1.0 (側銑動態用), 0=用戶切削油實機(預設), 1=Gemini 動態極限"},
                    "spindle_kw":   {"type": "number",
                                     "description": "主軸功率 kW (預設 7.5)"},
                    "spindle_rpm_max": {"type": "integer",
                                     "description": "主軸 RPM 硬上限 (預設 12000)"},
                },
                "required": ["material", "tool_dia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_tool_holder",
            "description": (
                "依工法推薦最佳刀把 (8 種規格: 熱縮/油壓/後拉/側固/SK/ER/鑽夾頭/攻牙). "
                "用於 LLM 判斷『這個工法該用哪種刀把』."),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string",
                                  "description": "工法: face/side/hole/slot/plunge"},
                },
                "required": ["operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_regular_milling_info",
            "description": (
                "查用戶口傳 5 工法心法 + 8 刀把規格 + Chip Thinning 數學. "
                "mode=list_profiles 列 5 工法 + 材質 Vc 縮放表; "
                "mode=list_holders 列 8 種刀把規格; "
                "mode=compute_hex 算實際切屑厚度 (D/AE/fz); "
                "mode=fz_for_hex 反推 fz_program (D/AE/hex_target)"),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string",
                             "description": "list_profiles / list_holders / compute_hex / fz_for_hex"},
                    "D":  {"type": "number", "description": "compute_hex/fz_for_hex 用: 刀徑"},
                    "AE": {"type": "number", "description": "compute_hex/fz_for_hex 用: AE mm"},
                    "fz": {"type": "number", "description": "compute_hex 用: fz_program mm/tooth"},
                    "hex_target": {"type": "number",
                                   "description": "fz_for_hex 用: 目標切屑厚 mm (S50C 切削油常用 0.034)"},
                },
                "required": ["mode"],
            },
        },
    },
]

ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}


# ---------- MCP 呼叫 ----------

def _mcp_call(action: str, params: Optional[dict] = None, *, timeout: float = 60.0) -> Dict[str, Any]:
    """Send a single JSON-line request to Smart_AI_CAM MCP. Friendly error if offline."""
    payload = {"action": action, "params": params or {}}
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        sock = socket.create_connection((MCP_HOST, MCP_PORT), timeout=5)
    except (ConnectionRefusedError, OSError, socket.timeout) as e:
        return {
            "success": False,
            "error": f"MCP offline ({MCP_HOST}:{MCP_PORT}) - {type(e).__name__}: {e}",
            "hint": "請在 Fusion 360 內 reload Smart_AI_CAM 外掛後重試",
            "offline": True,
        }
    try:
        sock.settimeout(timeout)
        sock.sendall(line.encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(262144)
            if not chunk:
                break
            buf += chunk
        raw = buf.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
        if not raw:
            return {"success": False, "error": "MCP 回傳空資料"}
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"MCP 回應非 JSON: {e}", "raw": buf[:500].decode("utf-8", "replace")}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _truncate_json(obj: Any, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    """大型 JSON 回應截斷後給模型，避免吃掉所有 context。"""
    txt = json.dumps(obj, ensure_ascii=False)
    if len(txt) <= max_chars:
        return txt
    return txt[: max_chars - 80] + f'... (truncated, total {len(txt)} chars)"}}'


# ---------- Tool call 解析 (3 種 fallback 格式) ----------

_INLINE_TOOL_RE = re.compile(
    r"\[tool_call:\s*(\w+)(?:\((.*?)\))?\]",
    re.DOTALL,
)


def _parse_text_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """v4 Modelfile few-shot 教的格式: `[tool_call: name(arg1=val1, ...)]`"""
    if not content:
        return None
    m = _INLINE_TOOL_RE.search(content)
    if not m:
        return None
    name = m.group(1)
    args_str = (m.group(2) or "").strip()
    if name not in ALLOWED_TOOLS:
        return None

    args: Dict[str, Any] = {}
    if args_str:
        try:
            args = json.loads("{" + args_str + "}") if args_str.startswith('"') else {}
        except json.JSONDecodeError:
            args = {}
        if not args:
            for pair in args_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k = k.strip().strip('"').strip("'")
                    v = v.strip().strip('"').strip("'")
                    if k:
                        args[k] = v

    return {
        "id": "text_0",
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def _parse_json_inline_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """qwen2.5-coder 偶爾把 tool call 寫成 JSON 塞 content 裡。"""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name") or obj.get("tool") or obj.get("function")
    args = obj.get("arguments", obj.get("args", obj.get("parameters", {})))
    if not name or name not in ALLOWED_TOOLS:
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    return {
        "id": "inline_0",
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def _detect_tool_calls(msg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """三層 fallback 偵測 tool_calls。回傳 (tool_calls, cleaned_content)"""
    content = msg.get("content", "") or ""
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        return tool_calls, content

    # Fallback 1: JSON inline (整段內容是 JSON)
    inline = _parse_json_inline_tool_call(content)
    if inline:
        return [inline], ""

    # Fallback 2: [tool_call: xxx] 文字格式
    text_tc = _parse_text_tool_call(content)
    if text_tc:
        cleaned = _INLINE_TOOL_RE.sub("", content).strip()
        return [text_tc], cleaned

    return [], content


# ---------- Ollama Chat (streaming + non-streaming) ----------

def _ollama_chat(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
                 stream: bool = False) -> Dict[str, Any]:
    """非串流：一次回完整 dict。"""
    body: Dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.25, "top_p": 0.85},
    }
    if tools:
        body["tools"] = tools
    last_err = None
    for attempt in range(RETRY_OLLAMA + 1):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/chat",
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as e:
            last_err = e
            if attempt < RETRY_OLLAMA:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_err  # type: ignore[misc]


def _ollama_chat_stream(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
                        ) -> Iterator[Dict[str, Any]]:
    """串流：每行 yield 一個 chunk dict。"""
    body: Dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.25, "top_p": 0.85},
    }
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        for line in resp:
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue


def _stream_collect(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                    print_realtime: bool = True) -> Dict[str, Any]:
    """串流並即時印出 + 收集成完整 message dict（含 tool_calls 合併）。"""
    full_content_parts: List[str] = []
    tool_calls_acc: List[Dict[str, Any]] = []
    final = {"message": {"content": "", "tool_calls": []}, "done": False}

    for chunk in _ollama_chat_stream(messages, tools=tools):
        msg = chunk.get("message", {}) or {}
        delta = msg.get("content", "") or ""
        if delta:
            full_content_parts.append(delta)
            if print_realtime:
                sys.stdout.write(delta)
                sys.stdout.flush()
        tcs = msg.get("tool_calls") or []
        if tcs:
            tool_calls_acc.extend(tcs)
        if chunk.get("done"):
            final = chunk
            break

    if print_realtime:
        sys.stdout.write("\n")
        sys.stdout.flush()

    final["message"] = {
        "role": "assistant",
        "content": "".join(full_content_parts),
        "tool_calls": tool_calls_acc,
    }
    return final


# ---------- Agent Loop ----------

def _is_ollama_running() -> bool:
    """輕量級檢測本地 Ollama 服務埠口是否已啟動"""
    import socket
    try:
        # 解析 OLLAMA_URL 中的 host/port (預設 127.0.0.1:11434)
        m = re.search(r'//([^:/]+)(?::(\d+))?', OLLAMA_URL)
        host = m.group(1) if m else "127.0.0.1"
        port = int(m.group(2)) if m and m.group(2) else 11434
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

def _ensure_ollama_running(verbose: bool = False):
    """偵測 Ollama 是否在執行，未執行則嘗試透過桌面捷徑/預設路徑拉起服務"""
    if _is_ollama_running():
        return
    print(_color("[Ollama] 偵測到本機服務未啟動，嘗試透過桌面捷徑/預設路徑自癒喚醒...", C.YELLOW), file=sys.stderr)
    try:
        ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        from Smart_AI.reasoning.reference_paths import resolve_ollama_path
        exe = resolve_ollama_path()
        if exe and os.path.isfile(exe):
            import subprocess
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if verbose:
                print(_color(f"  → 已後台執行: {exe} serve", C.GRAY), file=sys.stderr)
            # 等待最多 5 秒
            for i in range(5):
                time.sleep(1.0)
                if _is_ollama_running():
                    print(_color("[Ollama] 本地服務已成功喚醒！", C.GREEN), file=sys.stderr)
                    break
        else:
            print(_color("⚠️ 無法定位 ollama.exe（請確認桌面 ollama.lnk 捷徑是否有效）", C.RED), file=sys.stderr)
    except Exception as e:
        print(_color(f"⚠️ 嘗試自動啟動 Ollama 發生異常: {e}", C.RED), file=sys.stderr)


def run_agent(user_msg: str, *, history: Optional[List[Dict[str, Any]]] = None,
              verbose: bool = False, stream: bool = True) -> Tuple[str, List[Dict[str, Any]]]:
    """單輪對話 Agent loop。回傳 (最終回答, 更新後的 messages)。
    若傳入 history 則會延續對話。"""
    # 執行前確保 Ollama 已經在運行中
    _ensure_ollama_running(verbose)

    messages: List[Dict[str, Any]] = list(history or [])
    messages.append({"role": "user", "content": user_msg})

    rounds = 0
    final_text = ""

    while rounds < MAX_TOOL_ROUNDS:
        rounds += 1
        if verbose:
            print(_color(f"[round {rounds}] 送 Ollama (stream={stream})...", C.GRAY), file=sys.stderr)


        try:
            if stream:
                resp = _stream_collect(messages, TOOLS, print_realtime=False)
            else:
                resp = _ollama_chat(messages, tools=TOOLS, stream=False)
        except urllib.error.URLError as e:
            err = f"[Ollama 連線失敗] {e}\n請確認 ollama serve 在 {OLLAMA_URL} 跑著"
            return err, messages
        except Exception as e:
            err = f"[Ollama 錯誤] {type(e).__name__}: {e}"
            return err, messages

        msg = resp.get("message", {}) or {}
        tool_calls, content = _detect_tool_calls(msg)

        if not tool_calls:
            final_text = content.strip() or "(模型未產生回應)"
            messages.append({"role": "assistant", "content": final_text})
            return final_text, messages

        # 有 tool calls -> 記錄 assistant + 執行 tools
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            if verbose:
                print(_color(f"  → tool_call: {name}({json.dumps(args, ensure_ascii=False)})",
                             C.CYAN), file=sys.stderr)
            else:
                # 簡短進度
                print(_color(f"  [{name}]", C.CYAN), file=sys.stderr, end="", flush=True)

            if name not in ALLOWED_TOOLS:
                result = {"success": False, "error": f"未知工具 {name}"}
            elif name == "knowledge_query":
                params = {k: args[k] for k in ("feature_type", "material", "geometry") if k in args}
                result = _mcp_call(name, params)
            elif name == "scan_machining_features":
                params = {k: args[k] for k in ("material",) if k in args}
                result = _mcp_call(name, params)
            # ───── ★ 智能切削參數路由 ─────
            elif name == "recommend_smart_cutting":
                # 主入口: query_smart_cutting + 透傳全部參數
                result = _mcp_call("query_smart_cutting", dict(args))
            elif name == "recommend_tool_holder":
                # 刀把推薦 -> query_regular_milling mode=recommend_holder
                result = _mcp_call("query_regular_milling", {
                    "mode": "recommend_holder",
                    "operation": args.get("operation", "face"),
                })
            elif name == "lookup_regular_milling_info":
                # 5 工法 + 刀把 + chip thinning 數學工具
                result = _mcp_call("query_regular_milling", dict(args))
            else:
                result = _mcp_call(name, {})

            tool_payload = _truncate_json(result)
            if verbose:
                preview = tool_payload[:300] + ("..." if len(tool_payload) > 300 else "")
                print(_color(f"    ← result: {preview}", C.DIM), file=sys.stderr)
            elif result.get("offline"):
                print(_color(" [MCP offline]", C.RED), file=sys.stderr, end="", flush=True)
            elif not result.get("success", True):
                print(_color(" [tool error]", C.YELLOW), file=sys.stderr, end="", flush=True)

            messages.append({
                "role": "tool",
                "content": tool_payload,
            })

        if not verbose:
            print("", file=sys.stderr)  # 換行收尾

    final_text = "[達到 tool 呼叫上限，請重新提問]"
    messages.append({"role": "assistant", "content": final_text})
    return final_text, messages


# ---------- CLI ----------

HELP_TEXT = """\
指令：
  :q | :quit          退出
  :v                  切 verbose（看內部 tool 流程）
  :stream             切 streaming on/off
  :tools              列出可用 MCP 工具
  :reset              清空對話歷史
  :save <FILE>        存對話到 JSON 檔
  :help               顯示此說明
"""


def _print_tools():
    print(_color(f"  共 {len(TOOLS)} 個 MCP 工具：", C.BOLD))
    for t in TOOLS:
        f = t["function"]
        print(f"  {_color(f['name'], C.CYAN)} - {f['description'][:80]}")


def _repl():
    print(_color("Smart AI Aegis — 值得信任的智能體 (v2 + MCP)", C.BOLD + C.MAGENTA))
    print(_color(f"  Ollama: {OLLAMA_URL}  |  Model: {MODEL}  |  MCP: {MCP_HOST}:{MCP_PORT}", C.GRAY))
    print(_color("  輸入問題後按 Enter；:help 查指令；:q 結束", C.GRAY))
    print()

    verbose = False
    stream = True
    history: List[Dict[str, Any]] = []

    while True:
        try:
            q = input(_color("你> ", C.GREEN + C.BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not q:
            continue

        if q.lower() in (":q", ":quit", "exit"):
            break
        if q.lower() == ":v":
            verbose = not verbose
            print(_color(f"[verbose = {verbose}]", C.YELLOW))
            continue
        if q.lower() == ":stream":
            stream = not stream
            print(_color(f"[stream = {stream}]", C.YELLOW))
            continue
        if q.lower() == ":tools":
            _print_tools()
            continue
        if q.lower() == ":reset":
            history = []
            print(_color("[對話歷史已清空]", C.YELLOW))
            continue
        if q.lower() == ":help":
            print(_color(HELP_TEXT, C.GRAY))
            continue
        if q.lower().startswith(":save"):
            parts = q.split(maxsplit=1)
            fname = parts[1].strip() if len(parts) > 1 else "agent_chat.json"
            try:
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                print(_color(f"[已存 {fname} ({len(history)} 條訊息)]", C.YELLOW))
            except Exception as e:
                print(_color(f"[存檔失敗: {e}]", C.RED))
            continue

        t0 = time.time()
        try:
            ans, history = run_agent(q, history=history, verbose=verbose, stream=stream)
        except Exception as e:
            ans = f"[Agent 錯誤] {type(e).__name__}: {e}"
        dt = time.time() - t0
        print()
        print(_color("助理>", C.BLUE + C.BOLD), ans)
        print()
        print(_color(f"[{dt:.1f}s, history={len(history)} msgs]", C.GRAY))
        print()


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        question = " ".join(sys.argv[1:])
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        stream = "--no-stream" not in sys.argv
        ans, _ = run_agent(question, verbose=verbose, stream=stream)
        print(ans)
    else:
        _repl()


if __name__ == "__main__":
    main()
