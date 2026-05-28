import json

from smart_ai_cam_vision.snapshot import vision_snapshot_json_string
from .palette_context import PaletteActionContext

FIXED_PALETTE_WIDTH = 1280


def _send_sketch_result_to_palette(context: PaletteActionContext, result: dict):
    """Push sketch result to HTML; always use status (known-good) plus dedicated action."""
    payload = json.dumps(result, ensure_ascii=False)
    level = "ok" if result.get("ok") else "err"
    msg = str(result.get("message", "") or "")
    if result.get("ok"):
        msg = "{} — {}".format(result.get("sketch_name", "草圖"), msg)
    status_payload = json.dumps({"msg": msg, "level": level}, ensure_ascii=False)

    pal = None
    try:
        pal = context.palette()
    except Exception:
        pal = None
    if not pal:
        try:
            pal = context.ui.palettes.itemById("holeProcessPalette")
        except Exception:
            pal = None
    if pal:
        try:
            pal.sendInfoToHTML("status", status_payload)
            pal.sendInfoToHTML("recognition_sketch_result", payload)
        except Exception:
            pass
    try:
        context.adsk.doEvents()
    except Exception:
        pass


def _emit_text_command(context: PaletteActionContext, msg: str):
    """Best-effort: mirror key diagnostics to Fusion Text Commands."""
    try:
        ui = context.adsk.core.Application.get().userInterface
        tp = ui.palettes.itemById("TextCommands")
        if tp:
            tp.writeText(str(msg))
    except Exception:
        pass


def _generate_and_send_thought_to_ui(context: PaletteActionContext, action: str, material: str):
    try:
        from Smart_AI.reasoning import thought_reasoning
        from Smart_AI.memory.thought_db import get_thought_db
        import json
        import re

        holes = context.holeInfoList() or []
        slots = getattr(context.runtime_state, "slotInfoList", []) or []

        feature_type = "hole"
        geometry = {"diameter_mm": 5.0, "depth_mm": 15.0}
        best_template = "一般鑽孔模板"

        if holes:
            main_hole = holes[0]
            feature_type = "hole"
            depth = 15.0
            try:
                depth_str = str(main_hole.get("depth", "15.0"))
                depth = float(re.findall(r"[\d\.]+", depth_str)[0])
            except:
                pass
            dia = 5.0
            try:
                dia_str = str(main_hole.get("dia", "5.0"))
                dia = float(re.findall(r"[\d\.]+", dia_str)[0])
            except:
                pass
            geometry = {
                "diameter_mm": dia,
                "depth_mm": depth,
                "hole_type": "tap" if main_hole.get("isTap") else "general"
            }
            drop_items = main_hole.get("dropItems", [])
            if drop_items:
                best_template = drop_items[0].get("name", "孔加工模板")
        elif slots:
            main_slot = slots[0]
            feature_type = "slot"
            w = 6.0
            try:
                w_str = str(main_slot.get("width", "6.0"))
                w = float(re.findall(r"[\d\.]+", w_str)[0])
            except:
                pass
            geometry = {"width_mm": w}
            drop_items = main_slot.get("dropItems", [])
            if drop_items:
                best_template = drop_items[0].get("name", "長條孔槽模板")

        active_machine = getattr(context.runtime_state, "active_machine", "未指定機台 (常規 12,000 RPM)")
        thought_data = thought_reasoning.generate_thought(
            feature_type=feature_type,
            material=material,
            geometry=geometry,
            best_template=best_template,
            machine=active_machine
        )

        db = get_thought_db()
        context_dict = {
            "feature_type": feature_type,
            "material": material,
            "geometry": geometry,
            "action_trigger": action
        }
        decision_dict = {
            "recommended_template": best_template,
            "parameters_override": {
                "feedrate": "AUTO",
                "rpm": "AUTO"
            }
        }
        thought_id = db.record_thought(
            context=context_dict,
            cognitive_path=thought_data,
            decision=decision_dict,
            session_id=action
        )
        db.flush()

        pal = context.palette()
        if pal:
            full_thought_dict = dict(thought_data)
            full_thought_dict["thought_id"] = thought_id
            pal.sendInfoToHTML("ai_thought_track", json.dumps(full_thought_dict, ensure_ascii=False))
    except Exception as e:
        try:
            context.send_diag_log(f"[_generate_and_send_thought_to_ui] Error: {e}")
        except:
            pass


def perform_retrospective_check(context: PaletteActionContext):
    try:
        from Smart_AI.memory.thought_db import get_thought_db
        import json

        db = get_thought_db()
        pending_thoughts = [t for t in db._thoughts.values() if t.get("reflection", {}).get("user_action") is None]
        if not pending_thoughts:
            return

        cam = context.cam_obj()
        if not cam:
            return

        current_ops = {}
        for i in range(cam.setups.count):
            setup = cam.setups.item(i)
            for j in range(setup.allOperations.count):
                op = setup.allOperations.item(j)
                current_ops[op.name] = op

        for t in pending_thoughts:
            tid = t["thought_id"]
            gen_ops = t.get("decision", {}).get("generated_ops", [])
            if not gen_ops:
                continue

            deleted_count = 0
            modified_count = 0
            kept_count = 0
            reasons = []

            for op_info in gen_ops:
                name = op_info.get("name")
                if name not in current_ops:
                    deleted_count += 1
                    reasons.append(f"工序 '{name}' 被使用者刪除。")
                else:
                    op = current_ops[name]
                    original_feed = op_info.get("feedrate")
                    original_speed = op_info.get("speed")
                    current_feed = ""
                    current_speed = ""
                    try:
                        current_feed = op.parameters.itemByName("tool_feedcutting").expression
                        current_speed = op.parameters.itemByName("tool_spindleSpeed").expression
                    except:
                        pass
                    if (original_feed and current_feed and original_feed != current_feed) or \
                       (original_speed and current_speed and original_speed != current_speed):
                        modified_count += 1
                        reasons.append(f"工序 '{name}' 的參數被修改 (原切削進給:{original_feed}->現:{current_feed}，原轉速:{original_speed}->現:{current_speed})。")
                    else:
                        kept_count += 1

            if deleted_count > 0:
                db.submit_reflection(
                    thought_id=tid,
                    user_action="delete",
                    user_rating=2,
                    user_comment="; ".join(reasons)
                )
                context.send_diag_log(f"[Retrospective] 偵測到思維軌跡 {tid} 的工序被使用者刪除，已完成自我反思學習。")
            elif modified_count > 0:
                db.submit_reflection(
                    thought_id=tid,
                    user_action="modify",
                    user_rating=3,
                    user_comment="; ".join(reasons)
                )
                context.send_diag_log(f"[Retrospective] 偵測到思維軌跡 {tid} 的工序被使用者修改，已學習修改後參數。")
            elif kept_count > 0:
                db.submit_reflection(
                    thought_id=tid,
                    user_action="keep",
                    user_rating=5,
                    user_comment="所有生成的工序均被保留且無修改。"
                )
                context.send_diag_log(f"[Retrospective] 偵測到思維軌跡 {tid} 的工序完全被保留，思維驗證成功。")
        db.flush()
    except Exception as e:
        try:
            context.send_diag_log(f"[perform_retrospective_check] Error: {e}")
        except:
            pass


def handle_action(action, data, context: PaletteActionContext):
    # 雙迴路反思：在執行任何操作時主動檢查工序刪改狀態
    perform_retrospective_check(context)

    cam_obj = context.cam_obj
    hole_info_list = context.holeInfoList
    palette = context.palette
    runtime_state = context.runtime_state

    # Some Fusion HTML bridge stacks emit a synthetic "response" action.
    # Treat it as a no-op to keep diagnostics clean.
    action_norm = str(action or "").strip()
    action_norm = action_norm.strip("'\"").strip()
    action_norm_lc = action_norm.lower()
    if "response" in action_norm_lc:
        return True

    if action == "get_ai_recommendations":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        if context.process_mcp_request:
            res = context.process_mcp_request("get_ai_recommendations", {"material": mat})
            pal = palette()
            if pal:
                if res.get("success"):
                    pal.sendInfoToHTML("ai_recommendations", json.dumps(res["data"], ensure_ascii=False))
                else:
                    err_payload = {
                        "overall_report": "AI 分析失敗：\n" + str(res.get("error") or "未知錯誤"),
                        "panel_apply": None,
                        "success": False,
                    }
                    pal.sendInfoToHTML("ai_recommendations", json.dumps(err_payload, ensure_ascii=False))
        _generate_and_send_thought_to_ui(context, action, mat)
        return True

    if action == "check_intuitive_eligibility":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        if context.process_mcp_request and palette():
            res = context.process_mcp_request("check_intuitive_eligibility", {"material": mat})
            payload = res.get("data") or {}
            payload["success"] = bool(res.get("success"))
            if not res.get("success"):
                payload["error"] = res.get("error", "")
            palette().sendInfoToHTML(
                "intuitive_eligibility", json.dumps(payload, ensure_ascii=False)
            )
        _generate_and_send_thought_to_ui(context, action, mat)
        return True

    if action == "run_intuitive_one_click":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        do_exec = bool(data.get("execute", True))
        if context.process_mcp_request and palette():
            res = context.process_mcp_request(
                "run_intuitive_one_click",
                {"material": mat, "execute": do_exec},
            )
            out = dict(res.get("data") or {})
            out["success"] = bool(res.get("success"))
            out["error"] = res.get("error", "")
            out["message"] = res.get("message", "")
            palette().sendInfoToHTML(
                "intuitive_programming", json.dumps(out, ensure_ascii=False)
            )
        _generate_and_send_thought_to_ui(context, action, mat)
        return True

    if action == "run_intuitive_programming":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        do_exec = bool(data.get("execute", True))
        if context.process_mcp_request and palette():
            res = context.process_mcp_request(
                "run_intuitive_programming",
                {"material": mat, "execute": do_exec},
            )
            out = dict(res.get("data") or {})
            out["success"] = bool(res.get("success"))
            out["error"] = res.get("error", "")
            out["message"] = res.get("message", "")
            palette().sendInfoToHTML(
                "intuitive_programming", json.dumps(out, ensure_ascii=False)
            )
        _generate_and_send_thought_to_ui(context, action, mat)
        return True

    if action == "check_thinking_eligibility":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        layer = data.get("thinking_layer") or data.get("layer") or ""
        if context.process_mcp_request and palette():
            res = context.process_mcp_request(
                "check_thinking_eligibility",
                {"material": mat, "thinking_layer": layer},
            )
            payload = res.get("data") or {}
            payload["success"] = bool(res.get("success"))
            if not res.get("success"):
                payload["error"] = res.get("error", "")
            palette().sendInfoToHTML(
                "thinking_eligibility", json.dumps(payload, ensure_ascii=False)
            )
        _generate_and_send_thought_to_ui(context, action, mat)
        return True

    if action == "run_thinking_programming":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        do_exec = bool(data.get("execute", True))
        layer = data.get("thinking_layer") or data.get("layer") or ""
        mcp_params = {
            "material": mat,
            "execute": do_exec,
            "thinking_layer": layer,
        }
        if data.get("resume_from_sequence") is not None:
            mcp_params["resume_from_sequence"] = data.get("resume_from_sequence")
        if data.get("multi_setup_plan_id"):
            mcp_params["multi_setup_plan_id"] = data.get("multi_setup_plan_id")
        if data.get("bottom_setup_name"):
            mcp_params["bottom_setup_name"] = data.get("bottom_setup_name")
        if context.process_mcp_request and palette():
            res = context.process_mcp_request("run_thinking_programming", mcp_params)
            out = dict(res.get("data") or {})
            out["success"] = bool(res.get("success"))
            out["error"] = res.get("error", "")
            out["message"] = res.get("message", "")
            palette().sendInfoToHTML(
                "thinking_programming", json.dumps(out, ensure_ascii=False)
            )
        _generate_and_send_thought_to_ui(context, action, mat)
        return True

    if action == "recognize_contour_2d":
        mat = data.get("material", runtime_state.current_material or "AL6061")
        apply_flag = bool(data.get("apply", False))
        if context.process_mcp_request:
            res = context.process_mcp_request("recognize_contour_2d", {"material": mat})
            if res.get("success") and palette():
                payload = res.get("data") or {}
                try:
                    from Smart_AI.perception.contour_2d_recognizer import recognition_summary_for_init

                    full_rec = getattr(runtime_state, "contour_2d_recognition", None)
                    summary = recognition_summary_for_init(full_rec)
                except Exception:
                    summary = payload.get("contour2dRecognition") or {}
                out = {
                    "contour2dRecognition": summary,
                    "recommended_templates": payload.get("recommended_templates") or {},
                    "applyTemplates": apply_flag,
                }
                palette().sendInfoToHTML("contour_2d_recognition", json.dumps(out, ensure_ascii=False))
        return True

    if action == "setup_change":
        setup_name = (data.get("setup") or "").strip()
        if setup_name:
            from Smart_AI.perception.feature_scanner import apply_panel_setup

            target = apply_panel_setup(setup_name, activate_in_fusion=True)
            if target:
                context.set_cam_setup(target)
        context.rebuild(force=True)
        if palette():
            palette().sendInfoToHTML("init", context.build_init_data())
            snap = getattr(runtime_state, "vision_snapshot", None)
            if snap:
                palette().sendInfoToHTML(
                    "vision_snapshot", vision_snapshot_json_string(snap)
                )
        return True

    if action == "vision_mode_change":
        mode = data.get("mode", "FAST_2D")
        skip_rescan = bool(data.get("skip_rescan", False))
        prev_mode = getattr(runtime_state, "vision_mode", "FAST_2D")
        runtime_state.vision_mode = mode
        refresh_fn = getattr(runtime_state, "refresh_vision_snapshot_fn", None)
        if skip_rescan:
            if prev_mode != mode and callable(refresh_fn):
                refresh_fn()
        elif prev_mode != mode:
            context.full_rescan()
        if palette():
            snap = getattr(runtime_state, "vision_snapshot", None)
            if snap:
                palette().sendInfoToHTML("vision_snapshot", vision_snapshot_json_string(snap))
        return True

    if action == "material_change":
        mat = data.get("material", "AL6061")
        runtime_state.current_material = mat
        # Material switch should fully refresh UI + template mapping paths.
        context.full_rescan()
        return True

    if action == "machine_change":
        mac = data.get("machine", "未指定機台 (常規 12,000 RPM)")
        runtime_state.active_machine = mac
        # Machine switch should fully refresh parameters and thought track.
        context.full_rescan()
        return True

    if action == "tmpl_change":
        idx = data.get("idx", -1)
        tmpl_idx = data.get("tmplIdx", 0)
        if 0 <= idx < len(hole_info_list()) and palette():
            info = hole_info_list()[idx]
            items = info.get("dropItems", [])
            if 0 <= tmpl_idx < len(items):
                chosen = items[tmpl_idx]
                cycle_type = str(chosen.get("cycleType", "") or "").strip().lower()
                tool_type = str(chosen.get("toolType", "") or "").strip().lower()
                has_drill = chosen.get("hasDrill", False)
                show_reamer_control = chosen.get("hasReamer", False)
                drill_url_obj = chosen.get("drillUrl", None)
                has_drill_url = (drill_url_obj is not None) and (str(drill_url_obj).strip() != "")
                show_pitch = chosen.get("hasMillBore", False) or (
                    bool(info.get("isCBLarge", False)) and has_drill_url
                )
                # Prefer cycleType/toolType as UI visibility source when available.
                if cycle_type == "bore-milling" or tool_type == "flat end mill":
                    show_pitch = True
                elif cycle_type == "reaming" or tool_type == "reamer":
                    show_reamer_control = True
                    has_drill = True
                elif cycle_type == "deep-drilling" or tool_type == "drill":
                    has_drill = True
                is_large_hole_z_minus = (
                    info.get("cbTopDia", "") == ""
                    and info.get("cbDepth", "") == ""
                    and info.get("dir", "") == "Z-"
                    and info.get("through", True) is False
                )
                if is_large_hole_z_minus:
                    has_drill = False
                    show_reamer_control = False
                    show_pitch = False
                palette().sendInfoToHTML(
                    "updateRowVisibility",
                    json.dumps(
                        {
                            "idx": idx,
                            "hasDrill": has_drill,
                            "showReamerControl": show_reamer_control,
                            "showPitch": show_pitch,
                        }
                    ),
                )
        return True

    if action == "draw_recognition_sketch" or action_norm_lc == "draw_recognition_sketch":
        if context.is_executing():
            _send_sketch_result_to_palette(
                context,
                {"ok": False, "message": "執行加工中，請稍後再繪製", "sketch_name": ""},
            )
            return True
        result = {"ok": False, "message": "unknown", "sketch_name": ""}
        try:
            refresh_fn = getattr(
                context.runtime_state, "refresh_vision_snapshot_fn", None
            )
            if callable(refresh_fn):
                refresh_fn()
            import importlib
            import sys

            for _m in [
                "Smart_AI.perception.contour_recognizer",
                "smart_ai_cam_vision.snapshot",
                "smart_ai_cam_vision.assist_sketch",
                "vision"
            ]:
                if _m in sys.modules:
                    try:
                        importlib.reload(sys.modules[_m])
                    except Exception:
                        pass

            from smart_ai_cam_vision.assist_sketch import create_recognition_sketch_from_vision

            snap = getattr(context.runtime_state, "vision_snapshot", None)
            feats = (snap or {}).get("recognized_features") or {}
            if not snap or not snap.get("ok") or not feats.get("hole_instances"):
                result = {
                    "ok": False,
                    "message": "視線法快照無效或缺少孔實例，請先按「重新掃描」",
                    "sketch_name": "",
                }
            else:
                setup = getattr(context.runtime_state, "cam_setup", None)
                if not setup:
                    pinned = (
                        getattr(context.runtime_state, "pending_setup_name", "") or ""
                    ).strip()
                    cam = context.cam_obj()
                    if pinned and cam:
                        from Smart_AI.perception.feature_scanner import (
                            _find_setup_by_name,
                        )

                        setup = _find_setup_by_name(cam, pinned)
                    if not setup and cam and cam.setups.count > 0:
                        setup = cam.setups.item(0)
                result = create_recognition_sketch_from_vision(snap, setup=setup)
        except Exception as ex:
            import traceback

            result = {
                "ok": False,
                "message": "{}".format(ex),
                "sketch_name": "",
                "trace": traceback.format_exc()[-800:],
            }
        try:
            context.send_diag_log(
                "[vision-sketch] ok={} {}".format(
                    result.get("ok"), result.get("message", "")
                )
            )
        except Exception:
            pass
        _send_sketch_result_to_palette(context, result)
        return True

    if action == "requestInit":
        # 開面板：優先幾何孔槽掃描（rebuild），避免每次 full_rescan 重載模板導致孔表空白或逾時
        try:
            context.rebuild(force=True)
        except Exception as ex:
            try:
                context.send_diag_log("[requestInit] rebuild failed: {}".format(ex))
            except Exception:
                pass
        if palette():
            palette().sendInfoToHTML("init", context.build_init_data())
            snap = getattr(runtime_state, "vision_snapshot", None)
            if snap:
                palette().sendInfoToHTML("vision_snapshot", vision_snapshot_json_string(snap))
        return True

    if action == "rescan":
        reason = str(data.get("reason", "") or "").strip()
        if reason == "template_cache":
            # 使用者若曾關閉診斷視窗，closed handler 會把全域 _diag_palette 清成 None，
            # 此處先預建/取回 palette 物件，否則 send_diag_log 會靜默丟棄。
            try:
                context.ensure_diag_palette(visible=False, only_bind=True)
            except Exception:
                pass
            context.send_diag_log(
                "[template-cache] UI：重新快取模板（走 refresh_template_cache：invalidate + buildTemplateMaps + rebuild 孔表 + init）"
            )
            _emit_text_command(
                context,
                "[template-cache] UI：重新快取模板（refresh_template_cache）；失敗時後備 full_rescan",
            )
            refresh_fn = getattr(context, "refresh_template_cache", None)
            ok = bool(refresh_fn()) if callable(refresh_fn) else False
            if not ok:
                context.send_diag_log("[template-cache] refresh_template_cache 回傳 False 或不存在，改走 full_rescan")
                context.full_rescan(data.get("setup", ""))
            if palette():
                palette().sendInfoToHTML(
                    "status",
                    json.dumps(
                        {
                            "msg": "模板磁碟索引與映射已重建" if ok else "模板重建已改走完全重掃，請看診斷",
                            "level": "ok" if ok else "warn",
                        },
                        ensure_ascii=False,
                    ),
                )
            return True
        else:
            # 與「調整 → 重新快取模板」分開：主面板「重新掃描」不會帶 template_cache。
            # 關閉診斷視窗後 _diag_palette 會被清掉，需先取回物件否則此行不會出現在診斷裡。
            try:
                context.ensure_diag_palette(visible=False, only_bind=True)
            except Exception:
                pass
            full = bool(data.get("full", False))
            context.send_diag_log(
                f"[rescan] 一般面板掃描（非 template_cache） full={full} reason={reason!r}"
            )
        setup_name = (data.get("setup") or "").strip()
        if setup_name:
            runtime_state.pending_setup_name = setup_name
        context.full_rescan(setup_name)
        if palette():
            snap = getattr(runtime_state, "vision_snapshot", None)
            if snap:
                palette().sendInfoToHTML("vision_snapshot", vision_snapshot_json_string(snap))
        return True

    if action == "sync_display":
        if context.is_executing():
            return True
        current_sig = context.calc_display_signature()
        last_sig = runtime_state.last_display_signature
        if current_sig != last_sig:
            context.rebuild()
        return True

    if action == "diag_toggle":
        enabled = bool(data.get("enabled", False))
        diag = context.ensure_diag_palette(visible=enabled)
        if enabled and diag:
            context.send_diag_log("診斷視窗已啟用")
        return True

    if action == "hole_debug_toggle":
        enabled = bool(data.get("enabled", False))
        runtime_state.hole_debug_enabled = enabled
        try:
            context.ensure_diag_palette(visible=False, only_bind=True)
        except Exception:
            pass
        context.send_diag_log(f'孔辨識除錯={"開啟" if enabled else "關閉"}')
        if enabled:
            context.emit_hole_debug_dump(source="toggle")
        return True

    if action == "slot_debug_toggle":
        enabled = bool(data.get("enabled", False))
        setattr(runtime_state, "slot_debug_enabled", enabled)
        try:
            context.ensure_diag_palette(visible=False, only_bind=True)
        except Exception:
            pass
        context.send_diag_log(f'口袋槽辨識除錯={"開啟" if enabled else "關閉"}')
        if enabled:
            context.emit_slot_diag_dump(source="toggle")
        return True

    if action == "depth_change":
        idx = data.get("idx", -1)
        dep_mm = data.get("depth", 0)
        tmpl_idx = data.get("tmplIdx", 0)
        if 0 <= idx < len(hole_info_list()) and palette():
            info = hole_info_list()[idx]
            if info.get("through", False):
                return True
            d_items = info.get("dropItems", [])
            if d_items:
                chosen = d_items[tmpl_idx] if 0 <= tmpl_idx < len(d_items) else d_items[0]
                if chosen.get("hasReamer", False) and chosen.get("drillUrl"):
                    t_info = context.get_tool_info_from_template(chosen["drillUrl"])
                    if t_info and dep_mm > 0:
                        tip_h = t_info["tipHeightMM"]
                        ream_used = dep_mm
                        drill_d = ream_used + tip_h + 0.5
                        msg = f"依絞深計算 / 刀尖{round(tip_h,3)}mm / 鑽需{round(drill_d,3)}mm"
                        palette().sendInfoToHTML(
                            "calcResult",
                            json.dumps({"idx": idx, "msg": msg, "calcMM": round(drill_d, 3), "reamMMUsed": round(ream_used, 3)}),
                        )
        return True

    if action == "browse_template_path":
        key = data.get("key", "")
        current_val = data.get("current", "")
        try:
            import adsk.core
            import os
            app = adsk.core.Application.get()
            ui = app.userInterface
            folderDlg = ui.createFolderDialog()
            folderDlg.title = '請選擇模板資料夾路徑'
            
            # Auto-resolve initial directory
            init_dir = ""
            appdata = os.environ.get("APPDATA", "")
            templates_root = os.path.normpath(os.path.join(appdata, "Autodesk", "CAM360", "templates"))
            if current_val:
                mat = runtime_state.current_material or "AL6061"
                sub_path = current_val.format(material=mat)
                full_init = os.path.normpath(os.path.join(templates_root, sub_path))
                if os.path.exists(full_init):
                    init_dir = full_init
                elif os.path.exists(templates_root):
                    init_dir = templates_root
            elif os.path.exists(templates_root):
                init_dir = templates_root
                
            if init_dir:
                folderDlg.initialDirectory = init_dir
                
            dialogResult = folderDlg.showDialog()
            if dialogResult == adsk.core.DialogResults.DialogOK:
                chosen = folderDlg.folder
                mat = runtime_state.current_material or "AL6061"
                
                # Convert chosen absolute path to relative placeholder format
                abs_path_norm = os.path.normpath(chosen).replace("\\", "/")
                templates_root_norm = templates_root.replace("\\", "/")
                if abs_path_norm.lower().startswith(templates_root_norm.lower()):
                    rel = abs_path_norm[len(templates_root_norm):].strip("/")
                else:
                    rel = abs_path_norm
                    
                materials_to_check = [mat, "AL6061", "S50C"]
                seen = set()
                unique_materials = []
                for m in materials_to_check:
                    if m and m not in seen:
                        seen.add(m)
                        unique_materials.append(m)
                for m in unique_materials:
                    if m in rel:
                        rel = rel.replace(m, "{material}")
                        
                if palette():
                    palette().sendInfoToHTML(
                        "template_path_selected",
                        json.dumps({"key": key, "path": rel}, ensure_ascii=False)
                    )
        except Exception as ex:
            try:
                context.send_diag_log(f"[browse_template_path] Error: {ex}")
            except:
                pass
        return True


    if action == "palette_fullscreen":
        pal = palette()
        if pal:
            try:
                adsk_core = context.adsk.core
                enable = bool(data.get("enable", False))
                w = int(float(data.get("width", FIXED_PALETTE_WIDTH)))
                h = int(float(data.get("height", 950)))
                if enable:
                    try:
                        pal.dockingOption = adsk_core.PaletteDockingOptions.PaletteDockOptionsToVerticalOnly
                        pal.dockingState = adsk_core.PaletteDockingStates.PaletteDockStateFloating
                    except Exception:
                        pass
                    pal.width = max(960, w)
                    pal.height = max(720, h)
                else:
                    pal.width = max(360, w)
                    pal.height = max(360, h)
            except Exception:
                pass
        return True

    if action == "settings_update":
        _handle_settings_update(data, context)
        return True

    if action == "save_defaults":
        # Keep runtime state in sync with the newly saved defaults.
        # Otherwise, next init may still emit stale runtime values and
        # visually "overwrite" the just-saved defaults.
        current_ray = runtime_state.ray_diameter_delta_mm
        parsed_ray = _parse_ray_delta(data, current_ray)
        runtime_state.ray_diameter_delta_mm = parsed_ray
        runtime_state.chamfer_interference_tool_dia_mm = _parse_positive_float(
            data.get("chamferInterferenceToolDiaMM", None),
            getattr(runtime_state, "chamfer_interference_tool_dia_mm", None),
            min_value=0.1,
        )
        runtime_state.chamfer_interference_top_delta_tol_mm = _parse_positive_float(
            data.get("chamferInterferenceTopDeltaTolMM", None),
            getattr(runtime_state, "chamfer_interference_top_delta_tol_mm", None),
            min_value=0.0,
        )
        runtime_state.hole_top_height_mode = _parse_hole_top_height_mode(
            data.get("holeTopHeightMode", None),
            getattr(runtime_state, "hole_top_height_mode", "from surface top"),
        )
        context.save_ui_defaults(
            {
                "mainWidth": data.get("mainWidth", None),
                "mainHeight": data.get("mainHeight", None),
                "paletteWidth": FIXED_PALETTE_WIDTH,
                "paletteHeight": data.get("paletteHeight", None),
                "colHoleWidth": data.get("colHoleWidth", None),
                "colTemplateWidth": data.get("colTemplateWidth", None),
                "colCountWidth": data.get("colCountWidth", None),
                "colDepthWidth": data.get("colDepthWidth", None),
                "colDrillModeWidth": data.get("colDrillModeWidth", None),
                "colDrillDepthWidth": data.get("colDrillDepthWidth", None),
                "colReamModeWidth": data.get("colReamModeWidth", None),
                "colReamDepthWidth": data.get("colReamDepthWidth", None),
                "colPitchWidth": data.get("colPitchWidth", None),
                "colCalcWidth": data.get("colCalcWidth", None),
                "rayDiameterDeltaMM": data.get(
                    "rayDiameterDeltaMM",
                    runtime_state.ray_diameter_delta_mm,
                ),
                "chamferInterferenceToolDiaMM": data.get(
                    "chamferInterferenceToolDiaMM",
                    runtime_state.chamfer_interference_tool_dia_mm,
                ),
                "chamferInterferenceTopDeltaTolMM": data.get(
                    "chamferInterferenceTopDeltaTolMM",
                    runtime_state.chamfer_interference_top_delta_tol_mm,
                ),
                "holeTopHeightMode": data.get(
                    "holeTopHeightMode",
                    runtime_state.hole_top_height_mode,
                ),
            }
        )
        # 立即觸發模板快取刷新與重新掃描，讓路徑變更即刻生效！
        try:
            context.refresh_template_cache()
        except Exception:
            pass

        if palette():
            palette().sendInfoToHTML("status", json.dumps({"msg": "已覆蓋預設值並重建模板快取", "level": "ok"}, ensure_ascii=False))
        return True

    if action == "regression_check":
        context.send_diag_log("回歸健檢開始")
        passed = context.run_regression_check()
        if palette():
            palette().sendInfoToHTML(
                "status",
                json.dumps(
                    {
                        "msg": "回歸健檢通過" if passed else "回歸健檢有失敗項目，請看診斷視窗",
                        "level": "ok" if passed else "err",
                    }
                ),
            )
        return True

    if action == "dump_op_params":
        context.send_diag_log("開始傾印目前 Setup 工序參數")
        dumped = context.dump_active_setup_ops_params(max_ops=8)
        if palette():
            palette().sendInfoToHTML(
                "status",
                json.dumps({"msg": "已輸出工序參數到診斷視窗" if dumped else "傾印失敗，請先確認目前有有效 Setup", "level": "ok" if dumped else "err"}),
            )
        return True

    if action == "refresh_template_cache":
        try:
            context.ensure_diag_palette(visible=False, only_bind=True)
        except Exception:
            pass
        context.send_diag_log("開始重新快取模板（不重啟外掛）")
        refresh_fn = getattr(context, "refresh_template_cache", None)
        if callable(refresh_fn):
            ok = bool(refresh_fn())
        else:
            # Compatibility fallback for stale context schema in cache.
            context.send_diag_log("refresh_template_cache callback 不存在，改用 full_rescan 後備路徑")
            context.full_rescan()
            ok = True
        if palette():
            palette().sendInfoToHTML(
                "status",
                json.dumps(
                    {
                        "msg": "模板快取已重新建立" if ok else "模板快取重建失敗，請看診斷輸出",
                        "level": "ok" if ok else "err",
                    }
                ),
            )
        return True

    if action == "execute":
        material = data.get("material", runtime_state.current_material or "AL6061")
        try:
            dlg = context.adsk.core
            result = context.ui.messageBox(
                f"即將執行加工流程。\n目前模板材質：{material}\n\n是否確認繼續？",
                "執行前材質確認",
                dlg.MessageBoxButtonTypes.YesNoButtonType,
                dlg.MessageBoxIconTypes.QuestionIconType,
            )
            if result != dlg.DialogResults.DialogYes:
                if palette():
                    palette().sendInfoToHTML(
                        "status",
                        json.dumps({"msg": "已取消執行（材質未確認）", "level": "warn"}),
                    )
                return True
        except Exception:
            # If confirmation dialog fails unexpectedly, keep previous behavior.
            pass
        context.execute_from_palette(data)
        return True

    if action == "open_api_reference_page":
        filename = data.get("filename", "reference.html")
        try:
            import importlib.util
            import os
            addin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            script_path = os.path.join(addin_dir, "docs", "fusion_api_reference", "fusion_api_reference.py")
            if os.path.exists(script_path):
                spec = importlib.util.spec_from_file_location("fusion_api_reference", script_path)
                ref_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ref_mod)
                if hasattr(ref_mod, 'run_file'):
                    ref_mod.run_file(filename)
                else:
                    ref_mod.run(None)
            else:
                context.send_diag_log(f"[open_api_reference_page] 找不到參考手冊腳本: {script_path}")
        except Exception as e:
            try:
                context.send_diag_log(f"[open_api_reference_page] 錯誤: {e}")
            except:
                pass
        return True

    if action:
        shown_action = action_norm if action_norm else str(action)
        msg = f"[palette] 未識別的 action={shown_action!r}"
        try:
            context.ensure_diag_palette(visible=False, only_bind=True)
        except Exception:
            pass
        try:
            context.send_diag_log(msg)
        except Exception:
            pass
        _emit_text_command(context, msg)
    return False


def _handle_settings_update(data, context: PaletteActionContext):
    palette = context.palette
    runtime_state = context.runtime_state
    current_ray = runtime_state.ray_diameter_delta_mm
    parsed_ray = _parse_ray_delta(data, current_ray)
    runtime_state.ray_diameter_delta_mm = parsed_ray
    current_chamfer_dia = getattr(runtime_state, "chamfer_interference_tool_dia_mm", None)
    runtime_state.chamfer_interference_tool_dia_mm = _parse_positive_float(
        data.get("chamferInterferenceToolDiaMM", None),
        current_chamfer_dia,
        min_value=0.1,
    )
    current_chamfer_tol = getattr(runtime_state, "chamfer_interference_top_delta_tol_mm", None)
    runtime_state.chamfer_interference_top_delta_tol_mm = _parse_positive_float(
        data.get("chamferInterferenceTopDeltaTolMM", None),
        current_chamfer_tol,
        min_value=0.0,
    )
    runtime_state.hole_top_height_mode = _parse_hole_top_height_mode(
        data.get("holeTopHeightMode", None),
        getattr(runtime_state, "hole_top_height_mode", "from surface top"),
    )
    context.save_ui_defaults(
        {
            "mainWidth": data.get("mainWidth", None),
            "mainHeight": data.get("mainHeight", None),
            "paletteWidth": FIXED_PALETTE_WIDTH,
            "paletteHeight": data.get("paletteHeight", None),
            "colHoleWidth": data.get("colHoleWidth", None),
            "colTemplateWidth": data.get("colTemplateWidth", None),
            "colCountWidth": data.get("colCountWidth", None),
            "colDepthWidth": data.get("colDepthWidth", None),
            "colDrillModeWidth": data.get("colDrillModeWidth", None),
            "colDrillDepthWidth": data.get("colDrillDepthWidth", None),
            "colReamModeWidth": data.get("colReamModeWidth", None),
            "colReamDepthWidth": data.get("colReamDepthWidth", None),
            "colPitchWidth": data.get("colPitchWidth", None),
            "colCalcWidth": data.get("colCalcWidth", None),
            "rayDiameterDeltaMM": parsed_ray,
            "chamferInterferenceToolDiaMM": runtime_state.chamfer_interference_tool_dia_mm,
            "chamferInterferenceTopDeltaTolMM": runtime_state.chamfer_interference_top_delta_tol_mm,
            "holeTopHeightMode": runtime_state.hole_top_height_mode,
        }
    )
    try:
        w = FIXED_PALETTE_WIDTH
        h = data.get("paletteHeight", data.get("mainHeight", None))
        if palette():
            try:
                adsk_core = context.adsk.core
                palette().dockingOption = adsk_core.PaletteDockingOptions.PaletteDockOptionsToVerticalOnly
                palette().dockingState = adsk_core.PaletteDockingStates.PaletteDockStateRight
            except Exception:
                pass
        if palette():
            palette().width = FIXED_PALETTE_WIDTH
        if palette() and h is not None:
            hh = int(float(h))
            if hh >= 360:
                palette().height = hh
    except Exception:
        pass


def _parse_ray_delta(data, current_value):
    ray_delta = data.get("rayDiameterDeltaMM", None)
    if ray_delta is None and "rayDiameterMM" in data:
        ray_delta = data.get("rayDiameterMM", None)
    if ray_delta is None or ray_delta == "":
        return None
    try:
        v = float(ray_delta)
        return v if v > 0 else None
    except Exception:
        return current_value if current_value and current_value > 0 else None


def _parse_positive_float(value, current_value, min_value=0.001):
    if value is None or value == "":
        return current_value
    try:
        v = float(value)
        return v if v >= float(min_value) else current_value
    except Exception:
        return current_value


def _parse_hole_top_height_mode(value, current_value):
    allowed = {"from surface top", "from hole top"}
    if value is None:
        return current_value if current_value in allowed else "from surface top"
    v = str(value).strip().lower()
    if v in allowed:
        return v
    return current_value if current_value in allowed else "from surface top"
