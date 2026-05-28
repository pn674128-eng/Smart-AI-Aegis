# -*- coding: utf-8 -*-
"""
Smart AI Aegis 置頂浮窗小助手 — 輕量對話，不需開瀏覽器。
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import scrolledtext
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_AGENT_DIR = ROOT / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

import cam_helper_agent as agent  # noqa: E402

STATE_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "SmartAIAegis"
STATE_FILE = STATE_DIR / "float_window.json"

WIN_W, WIN_H = 420, 580
_PLACEHOLDER = "發消息…"

# —— 設計 token（靛紫 + 柔和灰）——
C = {
    "header": "#5b4bb7",
    "header_hi": "#7c6cf0",
    "header_fg": "#ffffff",
    "header_muted": "#e0e7ff",
    "shell": "#eef1f8",
    "chat": "#f4f6fb",
    "card": "#ffffff",
    "border": "#dde3ef",
    "border_focus": "#7c6cf0",
    "text": "#1e293b",
    "text_soft": "#64748b",
    "text_faint": "#94a3b8",
    "accent": "#6366f1",
    "accent_hi": "#4f46e5",
    "user_bg": "#e8ecff",
    "user_fg": "#3730a3",
    "bot_bg": "#ffffff",
    "bot_fg": "#334155",
    "system_fg": "#94a3b8",
    "pin_on": "#fef08a",
    "send": "#6366f1",
    "send_hi": "#4f46e5",
    "pill_off": "#e8ecf4",
    "pill_on": "#ddd6fe",
    "pill_fg": "#5b21b6",
}


def _load_window_state() -> Dict[str, Any]:
    try:
        if STATE_FILE.is_file():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_window_state(geo: str, pinned: bool) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps({"geometry": geo, "pinned": pinned}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


class _IconBtn(tk.Label):
    """標題列圖示按鈕（Label + hover）。"""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        bg: str,
        fg: str = C["header_fg"],
        active_bg: str = C["header_hi"],
        size: int = 11,
        padx: int = 8,
    ) -> None:
        super().__init__(
            parent,
            text=text,
            font=("Segoe UI Symbol", size),
            bg=bg,
            fg=fg,
            cursor="hand2",
            padx=padx,
            pady=4,
        )
        self._cmd = command
        self._bg = bg
        self._active_bg = active_bg
        self._fg = fg
        self.bind("<Button-1>", lambda _e: self._cmd())
        self.bind("<Enter>", lambda _e: self.configure(bg=self._active_bg))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._bg))

    def set_colors(self, bg: str, fg: Optional[str] = None) -> None:
        self._bg = bg
        self.configure(bg=bg)
        if fg is not None:
            self._fg = fg
            self.configure(fg=fg)


class AegisFloatApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Smart AI Aegis")
        self.root.configure(bg=C["shell"])
        self.root.minsize(340, 420)
        try:
            self.root.attributes("-alpha", 0.98)
        except Exception:
            pass

        saved = _load_window_state()
        self._pinned = bool(saved.get("pinned", True))
        geo = saved.get("geometry")
        self.root.geometry(geo if geo else f"{WIN_W}x{WIN_H}+100+60")

        self._history: List[Dict[str, Any]] = []
        self._busy = False
        self._quick_mode = False
        self._thinking_mark: Optional[str] = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._placeholder_active = True

        fam = "Microsoft YaHei UI"
        self._font = tkfont.Font(family=fam, size=10)
        self._font_sm = tkfont.Font(family=fam, size=9)
        self._font_xs = tkfont.Font(family=fam, size=8)
        self._font_title = tkfont.Font(family=fam, size=11, weight="bold")
        self._font_sub = tkfont.Font(family=fam, size=8)
        self._font_bold_sm = tkfont.Font(family=fam, size=9, weight="bold")
        self._font_send = tkfont.Font(family=fam, size=10, weight="bold")

        self._build_ui()
        self._setup_chat_tags()
        self._apply_topmost()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_configure_debounced)

        warn = agent.check_ollama_startup()
        if warn:
            self._append_system(warn.replace("\n", " "))
        else:
            self._append_system(f"已就緒 · {agent.MODEL}")

        self._poll_ui_queue()

    def _setup_chat_tags(self) -> None:
        t = self._chat
        t.tag_configure("user_name", font=self._font_bold_sm, foreground=C["user_fg"], spacing1=10)
        t.tag_configure(
            "user_body",
            font=self._font,
            foreground=C["user_fg"],
            background=C["user_bg"],
            lmargin1=36,
            lmargin2=36,
            rmargin=14,
            spacing3=4,
        )
        t.tag_configure("bot_name", font=self._font_bold_sm, foreground=C["accent_hi"], spacing1=10)
        t.tag_configure(
            "bot_body",
            font=self._font,
            foreground=C["bot_fg"],
            background=C["bot_bg"],
            lmargin1=14,
            lmargin2=14,
            rmargin=24,
            spacing3=4,
        )
        t.tag_configure(
            "system",
            font=self._font_xs,
            foreground=C["system_fg"],
            justify="center",
            spacing1=8,
            spacing3=8,
        )
        t.tag_configure(
            "thinking",
            font=self._font_sm,
            foreground=C["text_faint"],
            justify="center",
            spacing1=6,
        )

    def _build_ui(self) -> None:
        # —— 標題列 ——
        header = tk.Frame(self.root, bg=C["header"], height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        self._header = header

        badge = tk.Canvas(header, width=32, height=32, bg=C["header"], highlightthickness=0)
        badge.place(x=12, y=10)
        badge.create_oval(2, 2, 30, 30, fill=C["header_hi"], outline=C["header_muted"])
        badge.create_text(16, 16, text="A", fill="#ffffff", font=("Segoe UI", 12, "bold"))

        title_block = tk.Frame(header, bg=C["header"])
        title_block.place(x=50, y=8)
        tk.Label(
            title_block,
            text="Smart AI Aegis",
            font=self._font_title,
            fg=C["header_fg"],
            bg=C["header"],
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="加工主腦 · 置頂助手",
            font=self._font_sub,
            fg=C["header_muted"],
            bg=C["header"],
        ).pack(anchor="w")

        tools = tk.Frame(header, bg=C["header"])
        tools.place(relx=1.0, rely=0.5, anchor="e", x=-6)
        self._btn_min = _IconBtn(tools, "—", self._minimize, bg=C["header"], size=12, padx=6)
        self._btn_min.pack(side=tk.LEFT)
        self._btn_pin = _IconBtn(tools, "📌", self._toggle_pin, bg=C["header"], padx=6)
        self._btn_pin.pack(side=tk.LEFT)
        self._btn_new = _IconBtn(tools, "↻", self._new_chat, bg=C["header"], padx=6)
        self._btn_new.pack(side=tk.LEFT)

        # —— 對話區 ——
        chat_wrap = tk.Frame(self.root, bg=C["chat"], padx=10, pady=8)
        chat_wrap.pack(fill=tk.BOTH, expand=True)

        self._chat = scrolledtext.ScrolledText(
            chat_wrap,
            wrap=tk.WORD,
            font=self._font,
            bg=C["chat"],
            fg=C["text"],
            relief=tk.FLAT,
            padx=4,
            pady=4,
            state=tk.DISABLED,
            cursor="arrow",
            borderwidth=0,
            highlightthickness=0,
        )
        self._chat.pack(fill=tk.BOTH, expand=True)

        # —— 底部輸入卡片 ——
        footer = tk.Frame(self.root, bg=C["shell"], padx=12, pady=(0, 12))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        card_border = tk.Frame(footer, bg=C["border"], padx=1, pady=1)
        card_border.pack(fill=tk.X)
        card = tk.Frame(card_border, bg=C["card"], padx=10, pady=10)
        card.pack(fill=tk.X)

        self._input = tk.Text(
            card,
            height=2,
            font=self._font,
            relief=tk.FLAT,
            bg=C["card"],
            fg=C["text_faint"],
            wrap=tk.WORD,
            padx=4,
            pady=4,
            highlightthickness=0,
            borderwidth=0,
        )
        self._input.pack(fill=tk.X)
        self._input.insert("1.0", _PLACEHOLDER)
        self._input.bind("<FocusIn>", self._on_input_focus_in)
        self._input.bind("<FocusOut>", self._on_input_focus_out)
        self._input.bind("<KeyRelease>", self._on_input_key)
        self._input.bind("<Return>", self._on_return)

        bar = tk.Frame(card, bg=C["card"])
        bar.pack(fill=tk.X, pady=(8, 0))

        self._pill_quick = tk.Label(
            bar,
            text="  快速  ",
            font=self._font_sm,
            bg=C["pill_off"],
            fg=C["text_soft"],
            cursor="hand2",
            padx=4,
            pady=3,
        )
        self._pill_quick.pack(side=tk.LEFT)
        self._pill_quick.bind("<Button-1>", lambda _e: self._toggle_quick())

        self._status = tk.Label(
            bar,
            text="Enter 發送",
            font=self._font_xs,
            fg=C["text_faint"],
            bg=C["card"],
        )
        self._status.pack(side=tk.LEFT, padx=(10, 0))

        self._send_btn = tk.Label(
            bar,
            text="  發送  ",
            font=self._font_send,
            bg=C["send"],
            fg="#ffffff",
            cursor="hand2",
            padx=14,
            pady=5,
        )
        self._send_btn.pack(side=tk.RIGHT)
        self._send_btn.bind("<Button-1>", lambda _e: self._send())
        self._send_btn.bind("<Enter>", lambda _e: self._send_btn.configure(bg=C["send_hi"]))
        self._send_btn.bind("<Leave>", lambda _e: self._send_btn.configure(bg=C["send"]))

        self._update_pin_style()
        self._update_quick_pill()

    def _update_pin_style(self) -> None:
        if self._pinned:
            self._btn_pin.set_colors(C["pin_on"], C["accent_hi"])
        else:
            self._btn_pin.set_colors(C["header"], C["header_fg"])

    def _update_quick_pill(self) -> None:
        if self._quick_mode:
            self._pill_quick.configure(bg=C["pill_on"], fg=C["pill_fg"])
        else:
            self._pill_quick.configure(bg=C["pill_off"], fg=C["text_soft"])

    def _toggle_quick(self) -> None:
        self._quick_mode = not self._quick_mode
        self._update_quick_pill()
        self._set_status("快速 · 純聊天" if self._quick_mode else "完整 · 含 MCP")

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", self._pinned)

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        self._apply_topmost()
        self._update_pin_style()
        _save_window_state(self.root.geometry(), self._pinned)

    def _minimize(self) -> None:
        self.root.iconify()

    def _new_chat(self) -> None:
        if self._busy:
            return
        self._history = []
        self._chat.configure(state=tk.NORMAL)
        self._chat.delete("1.0", tk.END)
        self._chat.configure(state=tk.DISABLED)
        self._append_system("新對話已開始")

    def _on_input_focus_in(self, _event=None) -> None:
        if self._placeholder_active:
            self._input.delete("1.0", tk.END)
            self._input.configure(fg=C["text"])
            self._placeholder_active = False
        card_border = self._input.master.master
        card_border.configure(bg=C["border_focus"])

    def _on_input_focus_out(self, _event=None) -> None:
        card_border = self._input.master.master
        card_border.configure(bg=C["border"])
        if not self._input.get("1.0", "end-1c").strip():
            self._input.insert("1.0", _PLACEHOLDER)
            self._input.configure(fg=C["text_faint"])
            self._placeholder_active = True

    def _on_input_key(self, _event=None) -> None:
        if self._placeholder_active:
            return
        self._input.configure(fg=C["text"])

    def _on_return(self, event) -> Optional[str]:
        if event.state & 0x1:
            return None
        self._send()
        return "break"

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self._send_btn.configure(bg=C["text_faint"], cursor="watch")
            self._input.configure(state=tk.DISABLED)
        else:
            self._send_btn.configure(bg=C["send"], cursor="hand2")
            self._input.configure(state=tk.NORMAL)

    def _set_status(self, text: str) -> None:
        self._status.configure(text=text)

    def _append_message(self, role: str, text: str) -> None:
        self._chat.configure(state=tk.NORMAL)
        if role == "user":
            self._chat.insert(tk.END, "你\n", "user_name")
            self._chat.insert(tk.END, text.strip() + "\n", "user_body")
        elif role == "assistant":
            self._chat.insert(tk.END, "Aegis\n", "bot_name")
            self._chat.insert(tk.END, text.strip() + "\n", "bot_body")
        elif role == "thinking":
            self._chat.insert(tk.END, "✦ " + text + "\n", "thinking")
        else:
            self._chat.insert(tk.END, text + "\n", "system")
        self._chat.insert(tk.END, "\n")
        self._chat.see(tk.END)
        self._chat.configure(state=tk.DISABLED)

    def _append_system(self, text: str) -> None:
        self._append_message("system", "— " + text + " —")

    def _remove_thinking_line(self) -> None:
        if not self._thinking_mark:
            return
        self._chat.configure(state=tk.NORMAL)
        self._chat.delete(self._thinking_mark, tk.END)
        self._thinking_mark = None
        self._chat.configure(state=tk.DISABLED)

    def _send(self) -> None:
        if self._busy:
            return
        raw = self._input.get("1.0", "end-1c").strip()
        if not raw or (self._placeholder_active and raw == _PLACEHOLDER):
            return
        self._input.delete("1.0", tk.END)
        self._placeholder_active = False
        self._input.configure(fg=C["text"])

        self._append_message("user", raw)
        self._chat.configure(state=tk.NORMAL)
        self._thinking_mark = self._chat.index(tk.END)
        self._chat.insert(tk.END, "✦ 思考中…\n", "thinking")
        self._chat.see(tk.END)
        self._chat.configure(state=tk.DISABLED)

        self._set_busy(True)
        self._set_status("思考中…")
        threading.Thread(
            target=self._worker,
            args=(raw, not self._quick_mode),
            daemon=True,
        ).start()

    def _worker(self, text: str, use_tools: bool) -> None:
        t0 = time.time()
        try:
            ans, hist = agent.run_agent(
                text,
                history=self._history,
                verbose=False,
                stream=False,
                use_tools=use_tools,
            )
            self._history = hist
            self._ui_queue.put(("ok", ans, time.time() - t0))
        except Exception as e:
            self._ui_queue.put(("err", str(e), 0.0))

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                kind, payload, elapsed = self._ui_queue.get_nowait()
                self._remove_thinking_line()
                if kind == "ok":
                    self._append_message("assistant", payload)
                    self._set_status(f"完成 · {elapsed:.1f}s")
                else:
                    self._append_message("assistant", f"連線異常：{payload}")
                    self._set_status("請檢查 Ollama")
                self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_ui_queue)

    _cfg_timer: Optional[str] = None

    def _on_configure_debounced(self, _event=None) -> None:
        if self._cfg_timer:
            self.root.after_cancel(self._cfg_timer)
        self._cfg_timer = self.root.after(400, self._persist_geometry)

    def _persist_geometry(self) -> None:
        _save_window_state(self.root.geometry(), self._pinned)

    def _on_close(self) -> None:
        _save_window_state(self.root.geometry(), self._pinned)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    AegisFloatApp().run()


if __name__ == "__main__":
    main()
