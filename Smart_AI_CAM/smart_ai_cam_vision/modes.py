# -*- coding: utf-8 -*-
"""Vision mode constants (FAST_2D / FULL_3D)."""

VISION_MODES = ("FAST_2D", "FULL_3D")
VISION_DEFAULT_MODE = "FAST_2D"


def normalize_vision_mode(value):
    s = str(value or "").strip().upper()
    return s if s in VISION_MODES else VISION_DEFAULT_MODE


def inference_mode_from_vision_mode(vision_mode):
    return "INCLUDE_5AXIS" if normalize_vision_mode(vision_mode) == "FULL_3D" else "PROJECT_3AXIS"
