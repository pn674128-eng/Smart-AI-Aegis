# -*- coding: utf-8 -*-
"""
diagnostics.py
Handles diagnostic logging and temporary D9 debug switches.
"""

from __future__ import annotations
import json
import adsk.core

ENABLE_D9_DEBUG: bool = False
_diag_palette = None

def register_diag_palette(palette) -> None:
    global _diag_palette
    _diag_palette = palette

def send_diag_log(msg) -> None:
    global _diag_palette
    try:
        if _diag_palette:
            _diag_palette.sendInfoToHTML('log', json.dumps({'msg': str(msg)}))
    except:
        pass

def d9_dbg(msg, done_list: list[str] | None = None) -> None:
    if ENABLE_D9_DEBUG:
        send_diag_log(f"[🧪D9] {msg}")
        if done_list is not None:
            done_list.append(f"[🧪D9] {msg}")

def template_map_load_log(msg) -> None:
    send_diag_log(msg)
    try:
        _tp = adsk.core.Application.get().userInterface.palettes.itemById('TextCommands')
        if _tp:
            _tp.writeText(str(msg))
    except:
        pass

_main_palette = None

def register_main_palette(palette) -> None:
    global _main_palette
    _main_palette = palette


def get_main_palette():
    return _main_palette


def _broadcast_mcp_progress(percentage, status_text) -> None:
    global _main_palette
    if _main_palette:
        try:
            payload = {
                "percentage": int(percentage),
                "status": str(status_text)
            }
            _main_palette.sendInfoToHTML('mcp_status', json.dumps(payload))
            try:
                import adsk
                adsk.doEvents()
            except:
                pass
        except:
            pass
