from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RuntimeState:
    # 作用中參照引用對象 (Active Fusion 360 Object Context)
    app: Any = None
    ui: Any = None
    cam_obj: Any = None
    des_obj: Any = None
    cam_setup: Any = None
    tmpl_lib: Any = None
    refresh_vision_snapshot_fn: Any = None
    scan_bodies_cache: Any = None

    # 原有特徵/狀態屬性
    current_material: str = 'AL6061'
    active_machine: str = "未指定機台 (常規 12,000 RPM)"
    pending_setup_name: str = ''
    last_hole_count: int = 0
    last_display_signature: str = ''
    ray_diameter_delta_mm: Optional[float] = None
    chamfer_interference_tool_dia_mm: Optional[float] = None
    chamfer_interference_top_delta_tol_mm: Optional[float] = None
    hole_top_height_mode: str = "from surface top"
    hole_debug_enabled: bool = False
    slot_debug_enabled: bool = False
    last_hole_scan_rows_debug: list = field(default_factory=list)
    last_hole_scan_rows_raw: list = field(default_factory=list)
    template_params_cache: dict = field(default_factory=dict)
    tool_info_cache: dict = field(default_factory=dict)
    template_name_cache: dict = field(default_factory=dict)
    pocket_cache_sig: str = ''
    pocket_cache_rows: list = field(default_factory=list)
    op_clone_cache: dict = field(default_factory=dict)
    feature_face_cache: dict = field(default_factory=dict)
    op_name_cache: dict = field(default_factory=dict)
    vision_mode: str = "FULL_3D"
    vision_snapshot: Any = None
    active_document_token: str = ""
    l2_pending_multi_setup_plan: Any = None
    last_l2_multi_setup_plan: Any = None


state = RuntimeState()
