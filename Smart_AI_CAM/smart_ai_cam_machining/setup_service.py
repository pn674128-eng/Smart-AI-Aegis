# -*- coding: utf-8 -*-
"""CAM Setup helpers for thinking L2 multi-Setup orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from smart_ai_cam_state.runtime_state import state as runtime_state

DEFAULT_TOP_SETUP_NAME = "AI_Auto_Setup"
DEFAULT_BOTTOM_SETUP_NAME = "AI_Setup_Bottom"


def _cam_obj():
    return getattr(runtime_state, "cam_obj", None)


def list_setup_names() -> List[str]:
    cam = _cam_obj()
    if not cam:
        return []
    out: List[str] = []
    try:
        for i in range(cam.setups.count):
            out.append(str(cam.setups.item(i).name))
    except Exception:
        pass
    return out


def find_setup_by_name(name: str):
    cam = _cam_obj()
    key = str(name or "").strip()
    if not cam or not key:
        return None
    try:
        for i in range(cam.setups.count):
            st = cam.setups.item(i)
            if str(st.name) == key:
                return st
    except Exception:
        pass
    return None


def activate_setup_by_name(name: str) -> Dict[str, Any]:
    st = find_setup_by_name(name)
    if st is None:
        return {"success": False, "error": "Setup not found: {}".format(name)}
    try:
        runtime_state.cam_setup = st
        return {"success": True, "setup_name": str(st.name)}
    except Exception as ex:
        return {"success": False, "error": str(ex)}


def create_milling_setup(name: str) -> Dict[str, Any]:
    cam = _cam_obj()
    nm = str(name or "").strip()
    if not cam:
        return {"success": False, "error": "CAM not active"}
    if not nm:
        return {"success": False, "error": "Empty setup name"}
    if find_setup_by_name(nm):
        return activate_setup_by_name(nm)
    try:
        import adsk.cam

        setup_input = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
        new_setup = cam.setups.add(setup_input)
        new_setup.name = nm
        runtime_state.cam_setup = new_setup
        return {"success": True, "created": True, "setup_name": nm}
    except Exception as ex:
        return {"success": False, "error": str(ex)}


def ensure_setup(name: str, *, create_if_missing: bool = True) -> Dict[str, Any]:
    nm = str(name or "").strip()
    if not nm:
        return {"success": False, "error": "Empty setup name"}
    if find_setup_by_name(nm):
        return activate_setup_by_name(nm)
    if create_if_missing:
        return create_milling_setup(nm)
    return {
        "success": False,
        "error": "Setup missing: {}; create in Fusion with flipped WCS".format(nm),
    }


def resolve_top_setup_name(preferred: Optional[str] = None) -> str:
    if preferred and find_setup_by_name(preferred):
        return preferred
    active = getattr(runtime_state, "cam_setup", None)
    if active is not None:
        try:
            return str(active.name)
        except Exception:
            pass
    names = list_setup_names()
    if names:
        return names[0]
    return DEFAULT_TOP_SETUP_NAME


def resolve_bottom_setup_name(preferred: Optional[str] = None) -> str:
    return str(preferred or DEFAULT_BOTTOM_SETUP_NAME).strip()
