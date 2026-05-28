# -*- coding: utf-8 -*-
"""雙擊此 .pyw 啟動浮窗（Windows 不開黑色命令列）。"""
import os
import runpy
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AEGIS_MODEL", "smart-ai-aegis")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

runpy.run_path(
    os.path.join(os.path.dirname(__file__), "aegis_float_app.py"),
    run_name="__main__",
)
