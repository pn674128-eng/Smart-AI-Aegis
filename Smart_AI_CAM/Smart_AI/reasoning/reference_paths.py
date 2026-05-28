# -*- coding: utf-8 -*-
"""
Fusion 桌面捷徑與參考範本路徑（學習用檔案庫，與插件目錄分離）。

桌面 Fusion.lnk → E:\\Fusion
參考範本 → E:\\Fusion\\參考範本
"""

from __future__ import annotations

import os

_DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
FUSION_LNK = os.path.join(_DESKTOP, "Fusion.lnk")
PROGRAM_SHEET_LNK = os.path.join(_DESKTOP, "程序單.lnk")
OLLAMA_LNK = os.path.join(_DESKTOP, "ollama.lnk")

# 相對於 Fusion 根目錄（E:\Fusion）
REFERENCE_TEMPLATE_FOLDER_NAME = "參考範本"
F3Z_SUBFOLDER_NAME = "f3z已編程"


def resolve_shortcut_target(lnk_path: str) -> str:
    if not lnk_path or not os.path.isfile(lnk_path):
        return ""
    try:
        import win32com.client  # type: ignore

        sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(os.path.abspath(lnk_path))
        return str(sc.TargetPath or "").strip()
    except Exception:
        pass
    return ""


def resolve_ollama_path() -> str:
    """Resolve Ollama executable path from ollama.lnk on the desktop, else use fallback paths."""
    target = resolve_shortcut_target(OLLAMA_LNK)
    if target and os.path.isfile(target):
        return target
    # Fallback to default install locations
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        default_path = os.path.join(local_appdata, "Ollama", "ollama.exe")
        if os.path.isfile(default_path):
            return default_path
    return ""


def fusion_root_from_desktop() -> str:
    """E:\\Fusion from Fusion.lnk, else E:\\Fusion if exists."""
    target = resolve_shortcut_target(FUSION_LNK)
    if target and os.path.isdir(target):
        return os.path.normpath(target)
    fallback = r"E:\Fusion"
    if os.path.isdir(fallback):
        return fallback
    return ""



def reference_template_root() -> str:
    root = fusion_root_from_desktop()
    if not root:
        return ""
    return os.path.join(root, REFERENCE_TEMPLATE_FOLDER_NAME)


def reference_f3z_dir() -> str:
    base = reference_template_root()
    if not base:
        return ""
    return os.path.join(base, F3Z_SUBFOLDER_NAME)


def reference_manifest_path() -> str:
    base = reference_template_root()
    if not base:
        return ""
    return os.path.join(base, "manifest.json")
