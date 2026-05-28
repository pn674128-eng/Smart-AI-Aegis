from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class PaletteActionContext:
    adsk: Any
    ui: Any
    cam_obj: Callable[[], Any]
    set_cam_setup: Callable[[Any], None]
    holeInfoList: Callable[[], list]
    palette: Callable[[], Any]
    is_executing: Callable[[], bool]
    runtime_state: Any
    rebuild: Callable[..., Any]
    send_material_data: Callable[[str], None]
    full_rescan: Callable[..., Any]
    build_init_data: Callable[[], str]
    calc_display_signature: Callable[[], str]
    ensure_diag_palette: Callable[..., Any]
    send_diag_log: Callable[[str], None]
    emit_hole_debug_dump: Callable[..., Any]
    emit_slot_diag_dump: Callable[..., Any]
    get_tool_info_from_template: Callable[..., dict]
    save_ui_defaults: Callable[[dict], None]
    run_regression_check: Callable[[], bool]
    dump_active_setup_ops_params: Callable[..., Any]
    refresh_template_cache: Callable[[], bool]
    execute_from_palette: Callable[[dict], None]
    process_mcp_request: Callable[[str, dict], dict] = None

