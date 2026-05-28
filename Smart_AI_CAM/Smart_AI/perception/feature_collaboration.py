# -*- coding: utf-8 -*-
"""
Perception Collaboration Layer: Unify and cross-reference holes, slots, official pockets.
Allows individual recognizers to assist each other, refining depth and mapping dependencies.
"""
import math
import adsk.core
import adsk.fusion

class FeatureCollaborationManager:
    def __init__(self, holes, slots, official_pockets, flat_depths=None, design=None, setup=None):
        """
        holes: List[dict] - Individual scanned hole rows (before merging).
        slots: List[dict] - Scanned slot rows.
        official_pockets: List[dict] - Recognized official pockets.
        flat_depths: dict - Flat depths data.
        design: adsk.fusion.Design - Current Fusion 360 Design.
        setup: adsk.cam.CAMSetup - Current Fusion 360 CAM Setup.
        """
        self.holes = holes or []
        self.slots = slots or []
        self.official_pockets = official_pockets or []
        self.flat_depths = flat_depths or {}
        self.design = design
        self.setup = setup
        self.wcs_z_axis = None
        self._init_wcs_axes()

    def _init_wcs_axes(self):
        if self.setup:
            try:
                wcs = self.setup.workCoordinateSystem
                _, _, _, z_axis = wcs.getAsCoordinateSystem()
                self.wcs_z_axis = z_axis
            except Exception:
                pass

    def execute_collaboration_pipeline(self):
        """執行特徵協同核心管線"""
        # 1. 跨軌特徵去重與融合 (Deduplicate slots & official pockets)
        fused_slots, remaining_pockets = self.fuse_slots_and_official_pockets()
        
        # 2. 嵌套分析 (Analyze hole nesting in slots or pockets)
        calibrated_holes = self.analyze_and_calibrate_nested_holes(fused_slots, remaining_pockets)
        
        # 3. 建立加工順序依賴圖 (Establish machining dependency graph)
        dependency_graph = self.build_machining_dependency_graph(calibrated_holes, fused_slots, remaining_pockets)
        
        return {
            "holes": calibrated_holes,
            "slots": fused_slots,
            "official_pockets": remaining_pockets,
            "dependencies": dependency_graph
        }

    def _get_official_pocket_center(self, pocket):
        """從官方口袋的面片動態計算其 Setup WCS XY 中心點 (mm)"""
        faces = self._get_official_pocket_faces(pocket)
        if not faces or not self.setup:
            return 9999.0, 9999.0
        try:
            wcs = self.setup.workCoordinateSystem
            origin, x_axis, y_axis, _ = wcs.getAsCoordinateSystem()
            pts = []
            for f in faces:
                try:
                    bb = f.boundingBox
                    for pt in (bb.minPoint, bb.maxPoint):
                        dx, dy, dz = pt.x - origin.x, pt.y - origin.y, pt.z - origin.z
                        cx = (dx * x_axis.x + dy * x_axis.y + dz * x_axis.z) * 10.0
                        cy = (dx * y_axis.x + dy * y_axis.y + dz * y_axis.z) * 10.0
                        pts.append((cx, cy))
                except Exception:
                    pass
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        except Exception:
            pass
        return 9999.0, 9999.0

    def fuse_slots_and_official_pockets(self):
        """將自研槽與官方 RecognizedPocket 進行重合比對與融合，避免重複編程"""
        fused_slots = []
        used_pocket_indices = set()
        
        for slot in self.slots:
            scx = slot.get("cx", 0.0)
            scy = slot.get("cy", 0.0)
            sw = slot.get("width_mm", 0.0)
            
            matched_pocket = None
            for p_idx, pocket in enumerate(self.official_pockets):
                if p_idx in used_pocket_indices:
                    continue
                # 比對中心點幾何距離 (tol = 1.5 mm)
                pcx = pocket.get("cx")
                pcy = pocket.get("cy")
                if pcx is None or pcy is None:
                    pcx, pcy = self._get_official_pocket_center(pocket)
                    pocket["cx"] = pcx
                    pocket["cy"] = pcy
                    
                dist = math.sqrt((scx - pcx)**2 + (scy - pcy)**2)
                
                # 比對寬度 (tol = 1.0 mm)
                pw = pocket.get("width_mm", 0.0)
                
                if dist < 1.5 and abs(sw - pw) < 1.0:
                    matched_pocket = pocket
                    used_pocket_indices.add(p_idx)
                    break
            
            if matched_pocket:
                # 進行特徵融合 (Merge resources)
                slot["official_fused"] = True
                slot["pocket_index"] = matched_pocket.get("pocket_index")
                slot["body_token"] = matched_pocket.get("body_token")
                slot["bind_mode"] = matched_pocket.get("bind_mode", "auto")
                # 融合 Face 列表以取得最高保真度，利用 entityToken / id() 安全去重，避免 SWIG BRepFace unhashable 崩潰
                matched_faces = self._get_official_pocket_faces(matched_pocket)
                all_faces = slot.get("faces", []) + matched_faces
                unique_faces = []
                seen_tokens = set()
                for f in all_faces:
                    try:
                        token = f.entityToken
                    except Exception:
                        token = id(f)
                    if token not in seen_tokens:
                        seen_tokens.add(token)
                        unique_faces.append(f)
                slot["faces"] = unique_faces
            fused_slots.append(slot)
            
        remaining_pockets = [p for idx, p in enumerate(self.official_pockets) if idx not in used_pocket_indices]
        return fused_slots, remaining_pockets


    def _get_official_pocket_faces(self, pocket):
        """從 body_token 與 pocket_index 動態還原官方 BRepFace 對象"""
        if not self.design or not self.setup:
            return []
        try:
            body_token = pocket.get("body_token")
            pocket_idx = pocket.get("pocket_index")
            if not body_token:
                return []
                
            from Smart_AI.perception.feature_scanner import _resolve_body_from_entity_token
            body = _resolve_body_from_entity_token(self.design, body_token)
            if not body:
                return []
                
            from Smart_AI.perception.fusion_official_recognition import _setup_pocket_search_vector
            search_vec = _setup_pocket_search_vector(self.setup)
            
            pockets = adsk.cam.RecognizedPocket.recognizePockets(body, search_vec)
            if pockets and pocket_idx < pockets.count:
                pocket_obj = pockets.item(pocket_idx)
                return list(pocket_obj.faces)
        except Exception:
            pass
        return []

    def analyze_and_calibrate_nested_holes(self, slots, pockets):
        """
        分析孔是否嵌套在槽或口袋的底面。
        如果是，則校正其 Z 軸起點，優化切深計算。
        """
        calibrated_holes = []
        for hole in self.holes:
            # 處理自研孔 (dict) 或 B-rep 原始孔
            hcx = float(hole.get("diameter_mm", 0.0) or 0.0)
            # 取得中心座標
            faces = hole.get("faces", [])
            
            hole_cx, hole_cy = None, None
            try:
                # 透過圓柱幾何取得中心
                for f in faces:
                    if f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                        cyl = adsk.core.Cylinder.cast(f.geometry)
                        if cyl and self.setup:
                            wcs = self.setup.workCoordinateSystem
                            origin, x_axis, y_axis, _ = wcs.getAsCoordinateSystem()
                            pt = cyl.origin
                            dx, dy, dz = pt.x - origin.x, pt.y - origin.y, pt.z - origin.z
                            hole_cx = (dx * x_axis.x + dy * x_axis.y + dz * x_axis.z) * 10.0
                            hole_cy = (dx * y_axis.x + dy * y_axis.y + dz * y_axis.z) * 10.0
                            break
            except Exception:
                pass
            
            # Fallback coordinate extraction
            if hole_cx is None or hole_cy is None:
                hole_cx = float(hole.get("cx", hole.get("lx_mm", 9999.0)))
                hole_cy = float(hole.get("cy", hole.get("ly_mm", 9999.0)))

            parent_feature = None
            
            # 1. 拓樸鄰接面檢查 (Topological Adjacency - 100% 精準可靠)
            for slot in slots:
                if self._check_topological_adjacency(faces, slot.get("faces", [])):
                    parent_feature = {
                        "type": "slot",
                        "id": slot.get("idx"),
                        "bottom_z": slot.get("bot_z_wcs_mm", slot.get("top_z_wcs_mm", 0.0) - slot.get("depth_mm", 0.0))
                    }
                    break
            
            # 2. 幾何包絡判定 (Geometric Obround Fallback)
            if not parent_feature:
                for slot in slots:
                    scx = slot.get("cx", 0.0)
                    scy = slot.get("cy", 0.0)
                    sw = slot.get("width_mm", 0.0)
                    sl = slot.get("length_mm", 0.0)
                    
                    if self._is_point_inside_obround(hole_cx, hole_cy, scx, scy, sw, sl, slot.get("angle_deg", 0.0)):
                        parent_feature = {
                            "type": "slot",
                            "id": slot.get("idx"),
                            "bottom_z": slot.get("bot_z_wcs_mm", slot.get("top_z_wcs_mm", 0.0) - slot.get("depth_mm", 0.0))
                        }
                        break
                        
            # 3. 官方口袋判定
            if not parent_feature:
                for pocket in pockets:
                    pocket_faces = self._get_official_pocket_faces(pocket)
                    if self._check_topological_adjacency(faces, pocket_faces):
                        parent_feature = {
                            "type": "pocket",
                            "id": pocket.get("pocket_index"),
                            "bottom_z": -float(pocket.get("depth_mm", 0.0) or 0.0)
                        }
                        break

            if parent_feature:
                hole["nested_in"] = parent_feature
                hole["machining_start_height"] = "slot_bottom" if parent_feature["type"] == "slot" else "pocket_bottom"
            
            calibrated_holes.append(hole)
        return calibrated_holes

    def build_machining_dependency_graph(self, holes, slots, pockets):
        """建立工序加工順序依賴圖，提供給 AI 腦層進行工藝流程排序優化"""
        dependencies = []
        
        # 1. 嵌套依賴 (Holes nested inside slots/pockets must be drilled after milling)
        for idx, hole in enumerate(holes):
            if "nested_in" in hole:
                parent = hole["nested_in"]
                p_type = parent["type"]
                p_id = parent["id"]
                dependencies.append({
                    "id": f"dep_nest_{idx}",
                    "predecessor": f"{p_type}_{p_id}",
                    "successor": f"hole_{hole.get('diameter_mm', hole.get('dia', idx))}",
                    "type": "nesting",
                    "reason": f"孔 D{hole.get('diameter_mm', hole.get('dia', ''))} 位於 {p_type} 底面，必須先粗精銑型腔以清除實體毛坯，方可下鑽孔刀。"
                })
                
        # 2. 面銑依賴 (Milling flat face planes before small features)
        has_flat_planes = len(self.flat_depths.get("planes", [])) > 0
        if has_flat_planes:
            for slot in slots:
                if slot.get("active"):
                    dependencies.append({
                        "id": f"dep_face_slot_{slot.get('idx')}",
                        "predecessor": "top_face",
                        "successor": f"slot_{slot.get('idx')}",
                        "type": "plane_rough",
                        "reason": "頂面面銑應在開槽工序之前執行，以保證開槽深度精準且刀具受力均勻。"
                    })
            for idx, hole in enumerate(holes):
                # 僅有 Z+ 朝上方向的孔受頂面依賴約束
                if hole.get("dir", "Z+") == "Z+":
                    dependencies.append({
                        "id": f"dep_face_hole_{idx}",
                        "predecessor": "top_face",
                        "successor": f"hole_{hole.get('diameter_mm', hole.get('dia', idx))}",
                        "type": "plane_rough",
                        "reason": "頂面面銑先將表面胚料銑平，提供完美的定心起點，防止中心鑽或鑽頭打滑。"
                    })

        return dependencies

    def _check_topological_adjacency(self, hole_faces, container_faces):
        """利用 B-rep 拓樸邊界，高精確度判斷孔是否嵌套在型腔/槽底面"""
        if not hole_faces or not container_faces:
            return False
        
        # 收集型腔面的 entityToken
        container_tokens = set()
        for f in container_faces:
            try:
                container_tokens.add(f.entityToken)
            except Exception:
                container_tokens.add(id(f))
                
        # 檢查孔的任何一個面，是否與型腔面共用邊
        for h_face in hole_faces:
            try:
                for edge in h_face.edges:
                    for neighbor in edge.faces:
                        if neighbor.entityToken in container_tokens:
                            return True
            except Exception:
                pass
        return False

    def _is_point_inside_obround(self, px, py, cx, cy, w, l, angle_deg):
        """高精度判斷點是否在 2D 腰形槽內 (Setup XY)"""
        dx = px - cx
        dy = py - cy
        
        # 旋轉至槽的局部座標系
        rad = math.radians(-angle_deg)
        rx = dx * math.cos(rad) - dy * math.sin(rad)
        ry = dx * math.sin(rad) + dy * math.cos(rad)
        
        half_w = w / 2.0
        # 直邊段的半長
        straight_half_l = max(0.0, (l - w) / 2.0)
        
        # 1. 落在直邊矩形段內
        if abs(rx) <= straight_half_l and abs(ry) <= half_w:
            return True
            
        # 2. 落在右側半圓內
        if rx > straight_half_l:
            dist_sq = (rx - straight_half_l)**2 + ry**2
            return dist_sq <= half_w**2
            
        # 3. 落在左側半圓內
        if rx < -straight_half_l:
            dist_sq = (rx + straight_half_l)**2 + ry**2
            return dist_sq <= half_w**2
            
        return False
