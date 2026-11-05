# -*- coding: utf-8 -*-
"""
NLA Sequencer, Dynamic Curve-Synced Multi-Clip Chaining & Additive Pose Offset Layering
for ActionForge Elf Animation Director Studio v3.0.
"""

import json
import math
import bpy
from mathutils import Euler, Quaternion

from .constants import bind_action_slot
from .database import set_action_cyclic_loop


def _resolve_ctrl_obj(ctrl_or_name):
    if not ctrl_or_name:
        return None
    from .rig_actors import find_character_controller
    if isinstance(ctrl_or_name, str):
        obj = bpy.data.objects.get(ctrl_or_name)
        return find_character_controller(obj) if obj else None
    return find_character_controller(ctrl_or_name)


def _get_armature(ctrl_obj):
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return None
    from .rig_actors import get_character_armature_from_ctrl
    return get_character_armature_from_ctrl(ctrl_obj)


def get_nla_sequence_tracks(arm_obj) -> list:
    """Returns all multi-clip NLA sequence tracks (`AF_Director_Sequence` and `AF_Layer_*`) on `arm_obj`."""
    if not arm_obj or not arm_obj.animation_data:
        return []
    return [
        tr for tr in arm_obj.animation_data.nla_tracks
        if tr.name.startswith("AF_Director_Sequence") or tr.name.startswith("AF_Layer_")
    ]


def _extract_and_remove_additive_track(adt):
    """
    Temporarily removes any `AF_Additive_PoseOffset` track from `adt.nla_tracks` and returns
    its Action so it can be re-appended at the very top of the NLA stack after rebuilding.
    """
    if not adt:
        return None
    saved_act = None
    for tr in list(adt.nla_tracks):
        if tr.name.startswith("AF_Additive_PoseOffset"):
            for s in tr.strips:
                if s.action:
                    saved_act = s.action
            adt.nla_tracks.remove(tr)
    return saved_act


def _append_additive_track_on_top(adt, offset_act):
    """Appends `AF_Additive_PoseOffset` at the very top of `adt.nla_tracks` with `COMBINE` blending."""
    if not adt or not offset_act:
        return None
    for tr in list(adt.nla_tracks):
        if tr.name.startswith("AF_Additive_PoseOffset"):
            adt.nla_tracks.remove(tr)
    add_track = adt.nla_tracks.new()
    add_track.name = "AF_Additive_PoseOffset"
    strip = add_track.strips.new(offset_act.name, 1, offset_act)
    strip.frame_start = 1.0
    strip.frame_end = 10000.0
    strip.blend_type = "COMBINE"
    strip.extrapolation = "HOLD"
    bind_action_slot(strip, offset_act)
    return add_track


def assign_action_with_slot(arm_obj, action, speed_mult=1.0, frame_offset=0, loop_enabled=True) -> bool:
    """
    Assigns `action` to `arm_obj` with Blender 5.0 Action Slot binding, speed scaling,
    and frame offset. Preserves multi-clip NLA sequences and keeps `AF_Additive_PoseOffset` on top.
    """
    if not arm_obj or not action:
        return False

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    adt = arm_obj.animation_data

    set_action_cyclic_loop(action, enabled=loop_enabled)

    # Do not overwrite an active multi-clip NLA sequence
    seq_tracks = get_nla_sequence_tracks(arm_obj)
    if any(len(tr.strips) > 0 for tr in seq_tracks):
        adt.action = None
        return True

    has_additive = any(tr.name.startswith("AF_Additive_PoseOffset") for tr in adt.nla_tracks)
    use_nla_playback = (abs(float(speed_mult) - 1.0) > 1e-3) or (abs(int(frame_offset)) > 0) or has_additive

    for tr in list(adt.nla_tracks):
        if tr.name.startswith("AF_AutoPlayback"):
            adt.nla_tracks.remove(tr)

    if use_nla_playback:
        saved_additive_act = _extract_and_remove_additive_track(adt)
        adt.action = None

        track = adt.nla_tracks.new()
        track.name = "AF_AutoPlayback"
        start_f = max(1, 1 + int(frame_offset))
        strip = track.strips.new(action.name, start_f, action)
        strip.scale = 1.0 / max(0.1, float(speed_mult))
        strip.repeat = 50.0 if loop_enabled else 1.0
        strip.blend_type = "REPLACE"
        strip.extrapolation = "HOLD"
        bind_action_slot(strip, action)

        if saved_additive_act:
            _append_additive_track_on_top(adt, saved_additive_act)
    else:
        adt.action = action
        bind_action_slot(adt, action)

    return True


def get_nla_sequence_clips(ctrl_obj) -> list:
    """
    Inspects `ctrl_obj` and `arm_obj.animation_data.nla_tracks` for primary (Cycle 0) strips
    and returns an ordered list of clip dictionaries enriched with curve percentage intervals
    (`u_start_pct`, `u_end_pct`, `u_mid_pct`), ground speed (`speed_mps`), and `is_fill` status.
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    arm_obj = _get_armature(ctrl_obj)
    if not arm_obj or not arm_obj.animation_data:
        return []

    seq_tracks = get_nla_sequence_tracks(arm_obj)
    if not seq_tracks:
        return []

    stored_specs = []
    raw_json = ctrl_obj.get("af_nla_sequence_json", "") if ctrl_obj else ""
    if raw_json:
        try:
            stored_specs = json.loads(raw_json)
        except Exception:
            stored_specs = []

    raw_items = []
    for tr in seq_tracks:
        # Take only the first strip on each sequence track (Cycle 0)
        if len(tr.strips) > 0:
            raw_items.append((tr, tr.strips[0]))

    raw_items.sort(key=lambda item: (int(round(item[1].frame_start)), item[0].name))

    from .locomotion import solve_nla_curve_timing_plan
    plan = solve_nla_curve_timing_plan(ctrl_obj, stored_specs) if stored_specs else {"clips": []}
    plan_clips = plan.get("clips", [])

    clips = []
    for idx, (tr, s) in enumerate(raw_items):
        p_info = plan_clips[idx] if idx < len(plan_clips) else {}
        spec_info = stored_specs[idx] if idx < len(stored_specs) else {}
        clips.append({
            "index": idx,
            "track_name": tr.name,
            "strip_name": s.name,
            "action_name": s.action.name if s.action else p_info.get("action", ""),
            "frame_start": int(round(s.frame_start)),
            "frame_end": int(round(s.frame_end)),
            "scale": round(float(s.scale), 3),
            "repeat": round(float(spec_info.get("repeat", s.repeat)), 2),
            "effective_repeat": round(float(p_info.get("effective_repeat", s.repeat)), 2),
            "blend_in": round(float(s.blend_in), 1),
            "mode": str(spec_info.get("mode", p_info.get("mode", "AUTO"))),
            "is_fill": bool(p_info.get("is_fill", False)),
            "speed_mps": float(p_info.get("speed_mps", 0.0)),
            "u_start_pct": float(p_info.get("u_start_pct", 0.0)),
            "u_end_pct": float(p_info.get("u_end_pct", 100.0)),
            "u_mid_pct": float(p_info.get("u_mid_pct", 50.0)),
        })
    return clips


def rebuild_nla_sequence_from_specs(ctrl_obj, clip_specs, sync_curve: bool = True) -> tuple:
    """
    Rebuilds the character's NLA sequence tracks from a list of clip dicts:
    `[{"action": str, "repeat": float, "speed": float, "blend": int, "mode": "AUTO"|"FILL"|"FIXED"}, ...]`:
      - Automatically solves `effective_repeat` for `FILL` locomotion clips (`Jog_Cycle`, `Walk_Steady`,
        `Run_Sprint`, etc.) so fixed event clips (`Walk_Jump`) sit at exact positions along the curve.
      - When `af_loop_anim` is True, tiles multi-cycle loops across the timeline and sets
        `extrapolation = "NOTHING"` on overlay tracks so all cycles play cleanly forever.
      - Automatically updates the character's curve `offset_factor` velocity profile (`sync_curve=True`).
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return False, "Nije odabran kontroler vilenjaka."
    arm_obj = _get_armature(ctrl_obj)
    if not arm_obj:
        return False, f"Armatura nije pronađena za '{ctrl_obj.name}'."

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    adt = arm_obj.animation_data

    normalized = []
    for i, spec in enumerate(clip_specs or []):
        if isinstance(spec, str):
            act_name = spec
            rep = 1.0
            spd = float(ctrl_obj.get("af_anim_speed", 1.0))
            bld = 0 if i == 0 else 12
            mode = "AUTO"
        elif isinstance(spec, dict):
            act_name = spec.get("action") or spec.get("action_name") or spec.get("name") or ""
            rep = float(spec.get("repeat", 1.0))
            spd = float(spec.get("speed", ctrl_obj.get("af_anim_speed", 1.0)))
            bld = int(round(float(spec.get("blend", spec.get("blend_in", 0 if i == 0 else 12)))))
            mode = str(spec.get("mode", "AUTO")).upper()
        else:
            continue

        act = bpy.data.actions.get(act_name)
        if not act:
            continue
        normalized.append({
            "action": act.name,
            "repeat": max(0.1, round(rep, 2)),
            "speed": max(0.1, round(spd, 3)),
            "blend": 0 if len(normalized) == 0 else max(0, bld),
            "mode": mode if mode in ("AUTO", "FILL", "FIXED") else "AUTO",
        })

    if not normalized:
        return False, "Nema valjanih animacija za NLA sekvencu."

    from .locomotion import solve_nla_curve_timing_plan, attach_controller_to_locomotion_curve

    curve_name = ctrl_obj.get("af_attached_curve", "")
    curve_obj = bpy.data.objects.get(curve_name) if curve_name else None

    plan = solve_nla_curve_timing_plan(ctrl_obj, normalized, curve_obj=curve_obj)
    plan_clips = plan["clips"]
    cycle_frames = max(4, int(plan["cycle_frames"]))

    saved_additive_act = _extract_and_remove_additive_track(adt)

    for tr in list(adt.nla_tracks):
        if (
            tr.name.startswith("AF_AutoPlayback")
            or tr.name.startswith("AF_Director_Sequence")
            or tr.name.startswith("AF_Layer_")
        ):
            adt.nla_tracks.remove(tr)

    adt.action = None

    base_offset = max(0, int(ctrl_obj.get("af_frame_offset", 0)))
    start_base = 1 + base_offset
    loop_anim = bool(ctrl_obj.get("af_loop_anim", True))

    # Create 1 NLA track per clip slot in the sequence
    tracks = []
    for idx in range(len(plan_clips)):
        tr = adt.nla_tracks.new()
        tr.name = "AF_Director_Sequence" if idx == 0 else f"AF_Layer_{idx:02d}"
        tracks.append(tr)

    # Number of cycles to tile on NLA tracks when looping is enabled
    if loop_anim:
        num_cycles = max(4, min(16, int(math.ceil(1600.0 / max(10, cycle_frames)))))
    else:
        num_cycles = 1

    for cyc in range(num_cycles):
        cyc_offset = start_base + cyc * cycle_frames
        for idx, pclip in enumerate(plan_clips):
            act = bpy.data.actions.get(pclip["action"])
            if not act:
                continue
            tr = tracks[idx]
            f_start = int(cyc_offset + pclip["tau_start"])
            eff_rep = float(pclip["effective_repeat"])
            eff_bld = int(pclip["eff_blend"]) if idx > 0 else 0

            strip_name = act.name if cyc == 0 else f"{act.name}_Loop{cyc + 1}"
            strip = tr.strips.new(strip_name, f_start, act)
            strip.scale = 1.0 / max(0.1, float(pclip["speed"]))
            strip.repeat = max(0.1, eff_rep)
            strip.blend_type = "REPLACE"

            # CRITICAL: Overlay tracks (idx > 0) use NOTHING extrapolation so they turn off cleanly
            # at the end of their strip and never block Cycle 2, 3, ... on Track 0!
            if idx == 0:
                strip.extrapolation = "HOLD"
            elif not loop_anim and cyc == num_cycles - 1 and idx == len(plan_clips) - 1:
                strip.extrapolation = "HOLD_FORWARD"
            else:
                strip.extrapolation = "NOTHING"

            strip.blend_in = float(eff_bld)
            if loop_anim and idx == len(plan_clips) - 1 and len(plan_clips) > 1:
                # Smooth fade out at the end of the cycle back to Track 0 if needed
                strip.blend_out = 0.0
            else:
                strip.blend_out = 0.0

            bind_action_slot(strip, act)

    if saved_additive_act:
        _append_additive_track_on_top(adt, saved_additive_act)

    ctrl_obj["af_nla_sequence_json"] = json.dumps(normalized)
    ctrl_obj["af_anim_name"] = normalized[0]["action"]

    max_end_frame = start_base + cycle_frames - 1
    try:
        if bpy.context and bpy.context.scene:
            if loop_anim:
                bpy.context.scene.frame_start = 1
                bpy.context.scene.frame_end = max(10, max_end_frame)
            else:
                bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, max_end_frame)
    except Exception:
        pass

    if sync_curve and curve_obj and curve_obj.type == "CURVE":
        attach_controller_to_locomotion_curve(
            bpy.context,
            ctrl_obj=ctrl_obj,
            curve_obj=curve_obj,
            speed_mps=None,
            loop_path=loop_anim,
            flip_forward=bool(ctrl_obj.get("af_flip_curve_dir", False)),
            start_pct=float(ctrl_obj.get("af_curve_start_pct", 0.0)),
            _from_nla_rebuild=True,
        )

    names_str = " -> ".join(
        f"{c['action'].replace('AF_', '')}({c['u_start_pct']:.0f}..{c['u_end_pct']:.0f}% @ {c['speed_mps']:.1f}m/s)"
        for c in plan_clips
    )
    return True, f"NLA ({len(plan_clips)} isječaka, {cycle_frames}f krug): {names_str}"


def _current_specs_from_controller(ctrl_obj) -> list:
    """Extracts editable clip specs from `af_nla_sequence_json` or existing NLA tracks on `ctrl_obj`."""
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return []
    raw_json = ctrl_obj.get("af_nla_sequence_json", "")
    if raw_json:
        try:
            data = json.loads(raw_json)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass

    clips = get_nla_sequence_clips(ctrl_obj)
    specs = []
    for idx, c in enumerate(clips):
        scale_val = max(0.05, float(c.get("scale", 1.0)))
        specs.append({
            "action": c["action_name"],
            "repeat": float(c.get("repeat", 1.0)),
            "speed": round(1.0 / scale_val, 3),
            "blend": 0 if idx == 0 else int(round(float(c.get("blend_in", 12.0)))),
            "mode": str(c.get("mode", "AUTO")),
        })
    return specs


def append_animation_to_nla(ctrl_obj, action_name, blend_frames=12, repeat=1.0, speed_mult=None, mode="AUTO") -> tuple:
    """
    Appends `action_name` to the character's NLA sequence and dynamically recalculates
    both the NLA strip repeats (`FILL` vs `FIXED`) and the curve velocity profile!
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return False, "Odaberi vilenjaka u sceni."
    act = bpy.data.actions.get(action_name)
    if not act:
        return False, f"Animacija '{action_name}' nije pronađena."

    specs = _current_specs_from_controller(ctrl_obj)
    default_spd = float(ctrl_obj.get("af_anim_speed", 1.0))

    if not specs:
        first_anim = ctrl_obj.get("af_anim_name", "")
        if first_anim and bpy.data.actions.get(first_anim) and first_anim != act.name:
            specs.append({
                "action": first_anim,
                "repeat": 1.0,
                "speed": default_spd,
                "blend": 0,
                "mode": "AUTO",
            })

    specs.append({
        "action": act.name,
        "repeat": float(repeat),
        "speed": float(speed_mult if speed_mult is not None else default_spd),
        "blend": int(blend_frames) if len(specs) > 0 else 0,
        "mode": str(mode).upper(),
    })
    return rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)


def toggle_nla_clip_fill_mode(ctrl_obj, clip_index: int) -> tuple:
    """
    Toggles NLA clip at `clip_index` between `"FILL"` (Auto-Stretch along Curve) and
    `"FIXED"` (1x Fixed Event) and rebuilds the NLA sequence + curve path!
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    specs = _current_specs_from_controller(ctrl_obj)
    idx = int(clip_index)
    if not (0 <= idx < len(specs)):
        return False, f"Nevažeći indeks NLA isječka ({idx})."

    clips_info = get_nla_sequence_clips(ctrl_obj)
    cur_is_fill = clips_info[idx]["is_fill"] if idx < len(clips_info) else False
    new_mode = "FIXED" if cur_is_fill else "FILL"
    specs[idx]["mode"] = new_mode
    specs[idx]["repeat"] = 1.0
    return rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)


def adjust_nla_clip_repeat(ctrl_obj, clip_index: int, delta: float) -> tuple:
    """Adjusts the repeat/weight of NLA clip at `clip_index` by `delta` and rebuilds."""
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    specs = _current_specs_from_controller(ctrl_obj)
    idx = int(clip_index)
    if not (0 <= idx < len(specs)):
        return False, f"Nevažeći indeks NLA isječka ({idx})."

    cur_rep = float(specs[idx].get("repeat", 1.0))
    specs[idx]["repeat"] = max(0.5, round(cur_rep + float(delta), 2))
    return rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)


def chain_animations_on_controller(ctrl_obj, clip_specs, default_blend_frames=12) -> tuple:
    """
    Chains a list of animation names or clip spec dicts on `ctrl_obj` with smooth NLA crossfades
    and dynamic curve speed synchronization.
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return False, "Kontroler vilenjaka nije pronađen."
    if not clip_specs:
        return False, "Popis animacija za NLA sekvencu je prazan."

    default_spd = float(ctrl_obj.get("af_anim_speed", 1.0))
    normalized = []
    for idx, item in enumerate(clip_specs):
        if isinstance(item, str):
            normalized.append({
                "action": item,
                "repeat": 1.0,
                "speed": default_spd,
                "blend": 0 if idx == 0 else int(default_blend_frames),
                "mode": "AUTO",
            })
        elif isinstance(item, dict):
            act_name = item.get("action") or item.get("action_name") or item.get("name") or ""
            normalized.append({
                "action": act_name,
                "repeat": float(item.get("repeat", 1.0)),
                "speed": float(item.get("speed", default_spd)),
                "blend": 0 if idx == 0 else int(item.get("blend", item.get("blend_in", default_blend_frames))),
                "mode": str(item.get("mode", "AUTO")).upper(),
            })
    return rebuild_nla_sequence_from_specs(ctrl_obj, normalized, sync_curve=True)


def remove_nla_clip_at_index(ctrl_obj, clip_index: int) -> tuple:
    """Removes the NLA clip at `clip_index`; clears sequence if empty, else rebuilds."""
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    specs = _current_specs_from_controller(ctrl_obj)
    if not (0 <= int(clip_index) < len(specs)):
        return False, f"Nevažeći indeks NLA isječka ({clip_index})."

    removed = specs.pop(int(clip_index))
    if not specs:
        clear_nla_sequence(ctrl_obj)
        return True, f"Uklonjen '{removed['action']}' — NLA sekvenca očišćena."

    specs[0]["blend"] = 0
    ok, msg = rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)
    return ok, f"Uklonjen '{removed['action']}'. {msg}"


def move_nla_clip(ctrl_obj, clip_index: int, direction="UP") -> tuple:
    """Moves NLA clip at `clip_index` UP (`-1`) or DOWN (`+1`) and rebuilds the NLA sequence."""
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    specs = _current_specs_from_controller(ctrl_obj)
    idx = int(clip_index)
    if not (0 <= idx < len(specs)):
        return False, f"Nevažeći indeks NLA isječka ({idx})."

    target_idx = idx - 1 if str(direction).upper() == "UP" else idx + 1
    if not (0 <= target_idx < len(specs)):
        return False, "Isječak je već na rubu NLA sekvence."

    default_blend = 12
    for s in specs:
        if s.get("blend", 0) > 0:
            default_blend = int(s["blend"])
            break

    specs[idx], specs[target_idx] = specs[target_idx], specs[idx]
    for i, s in enumerate(specs):
        if i == 0:
            s["blend"] = 0
        elif s.get("blend", 0) <= 0:
            s["blend"] = default_blend

    return rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)


def clear_nla_sequence(ctrl_obj) -> bool:
    """
    Removes `AF_Director_Sequence` and `AF_Layer_*` tracks, resets `af_nla_sequence_json`,
    and restores the character's single base animation + curve locomotion while preserving `AF_Additive_PoseOffset`.
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return False
    arm_obj = _get_armature(ctrl_obj)
    if not arm_obj or not arm_obj.animation_data:
        ctrl_obj["af_nla_sequence_json"] = "[]"
        return False

    adt = arm_obj.animation_data
    for tr in list(adt.nla_tracks):
        if tr.name.startswith("AF_Director_Sequence") or tr.name.startswith("AF_Layer_"):
            adt.nla_tracks.remove(tr)

    ctrl_obj["af_nla_sequence_json"] = "[]"

    anim_name = ctrl_obj.get("af_anim_name", "AF_01_Walk_Steady")
    act = bpy.data.actions.get(anim_name)
    if act:
        assign_action_with_slot(
            arm_obj,
            act,
            speed_mult=float(ctrl_obj.get("af_anim_speed", 1.0)),
            frame_offset=int(ctrl_obj.get("af_frame_offset", 0)),
            loop_enabled=bool(ctrl_obj.get("af_loop_anim", True)),
        )

    curve_name = ctrl_obj.get("af_attached_curve", "")
    curve_obj = bpy.data.objects.get(curve_name) if curve_name else None
    if curve_obj and curve_obj.type == "CURVE":
        from .locomotion import attach_controller_to_locomotion_curve
        attach_controller_to_locomotion_curve(
            bpy.context,
            ctrl_obj=ctrl_obj,
            curve_obj=curve_obj,
            speed_mps=None,
            loop_path=bool(ctrl_obj.get("af_loop_anim", True)),
            flip_forward=bool(ctrl_obj.get("af_flip_curve_dir", False)),
            start_pct=float(ctrl_obj.get("af_curve_start_pct", 0.0)),
            _from_nla_rebuild=True,
        )
    return True


def clear_additive_pose_offset(ctrl_obj) -> bool:
    """Removes the `AF_Additive_PoseOffset` NLA track and resets stored pose offset angles to 0."""
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return False

    for key in (
        "af_pose_head_yaw",
        "af_pose_head_pitch",
        "af_pose_torso_bend",
        "af_pose_torso_twist",
        "af_pose_arms_raise",
        "af_pose_arms_forward",
        "af_pose_arms_inward",
        "af_pose_elbows_bend",
        "af_pose_pelvis_z_cm",
    ):
        ctrl_obj[key] = 0.0

    arm_obj = _get_armature(ctrl_obj)
    if arm_obj and arm_obj.animation_data:
        adt = arm_obj.animation_data
        for tr in list(adt.nla_tracks):
            if tr.name.startswith("AF_Additive_PoseOffset"):
                adt.nla_tracks.remove(tr)

    offset_act_name = f"AF_PoseOffset_{ctrl_obj.name}"
    old_act = bpy.data.actions.get(offset_act_name)
    if old_act:
        try:
            bpy.data.actions.remove(old_act)
        except Exception:
            pass

    if arm_obj:
        for bname in (
            "Head", "neck_01", "spine_01", "spine_02", "spine_03",
            "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
            "lowerarm_l", "lowerarm_r", "pelvis",
        ):
            pb = arm_obj.pose.bones.get(bname)
            if pb:
                pb.rotation_quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
                if bname == "pelvis":
                    pb.location = (0.0, 0.0, 0.0)

        if not get_nla_sequence_tracks(arm_obj):
            act = bpy.data.actions.get(ctrl_obj.get("af_anim_name", "AF_01_Walk_Steady"))
            if act:
                assign_action_with_slot(
                    arm_obj,
                    act,
                    speed_mult=float(ctrl_obj.get("af_anim_speed", 1.0)),
                    frame_offset=int(ctrl_obj.get("af_frame_offset", 0)),
                    loop_enabled=bool(ctrl_obj.get("af_loop_anim", True)),
                )
    return True


def apply_additive_pose_offset(
    ctrl_obj,
    head_yaw_deg=None,
    head_pitch_deg=None,
    torso_bend_deg=None,
    torso_twist_deg=None,
    arms_raise_deg=None,
    arms_forward_deg=None,
    arms_inward_deg=None,
    elbows_bend_deg=None,
    pelvis_z_cm=None,
) -> bool:
    """
    Applies non-destructive additive NLA bone offsets (`COMBINE` mode) on top of the active
    animation or NLA sequence for head, spine, clavicles, upperarms, lowerarms, and pelvis Z.
    """
    ctrl_obj = _resolve_ctrl_obj(ctrl_obj)
    if not ctrl_obj:
        return False
    arm_obj = _get_armature(ctrl_obj)
    if not arm_obj:
        return False

    if head_yaw_deg is not None:
        ctrl_obj["af_pose_head_yaw"] = float(head_yaw_deg)
    if head_pitch_deg is not None:
        ctrl_obj["af_pose_head_pitch"] = float(head_pitch_deg)
    if torso_bend_deg is not None:
        ctrl_obj["af_pose_torso_bend"] = float(torso_bend_deg)
    if torso_twist_deg is not None:
        ctrl_obj["af_pose_torso_twist"] = float(torso_twist_deg)
    if arms_raise_deg is not None:
        ctrl_obj["af_pose_arms_raise"] = float(arms_raise_deg)
    if arms_forward_deg is not None:
        ctrl_obj["af_pose_arms_forward"] = float(arms_forward_deg)
    if arms_inward_deg is not None:
        ctrl_obj["af_pose_arms_inward"] = float(arms_inward_deg)
    if elbows_bend_deg is not None:
        ctrl_obj["af_pose_elbows_bend"] = float(elbows_bend_deg)
    if pelvis_z_cm is not None:
        ctrl_obj["af_pose_pelvis_z_cm"] = float(pelvis_z_cm)

    hy = float(ctrl_obj.get("af_pose_head_yaw", 0.0))
    hp = float(ctrl_obj.get("af_pose_head_pitch", 0.0))
    tb = float(ctrl_obj.get("af_pose_torso_bend", 0.0))
    tt = float(ctrl_obj.get("af_pose_torso_twist", 0.0))
    ar = float(ctrl_obj.get("af_pose_arms_raise", 0.0))
    af = float(ctrl_obj.get("af_pose_arms_forward", 0.0))
    ai = float(ctrl_obj.get("af_pose_arms_inward", 0.0))
    eb = float(ctrl_obj.get("af_pose_elbows_bend", 0.0))
    pz = float(ctrl_obj.get("af_pose_pelvis_z_cm", 0.0))

    if all(abs(v) < 1e-3 for v in (hy, hp, tb, tt, ar, af, ai, eb, pz)):
        return clear_additive_pose_offset(ctrl_obj)

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    adt = arm_obj.animation_data

    for tr in list(adt.nla_tracks):
        if tr.name.startswith("AF_Additive_PoseOffset"):
            adt.nla_tracks.remove(tr)

    if not get_nla_sequence_tracks(arm_obj) and not any(tr.name.startswith("AF_AutoPlayback") for tr in adt.nla_tracks):
        base_act = adt.action or bpy.data.actions.get(ctrl_obj.get("af_anim_name", "AF_01_Walk_Steady"))
        if base_act:
            adt.action = None
            base_track = adt.nla_tracks.new()
            base_track.name = "AF_AutoPlayback"
            start_f = max(1, 1 + int(ctrl_obj.get("af_frame_offset", 0)))
            b_strip = base_track.strips.new(base_act.name, start_f, base_act)
            b_strip.scale = 1.0 / max(0.1, float(ctrl_obj.get("af_anim_speed", 1.0)))
            b_strip.repeat = 50.0 if bool(ctrl_obj.get("af_loop_anim", True)) else 1.0
            b_strip.blend_type = "REPLACE"
            b_strip.extrapolation = "HOLD"
            bind_action_slot(b_strip, base_act)

    offset_act_name = f"AF_PoseOffset_{ctrl_obj.name}"
    old_act = bpy.data.actions.get(offset_act_name)
    if old_act:
        try:
            bpy.data.actions.remove(old_act)
        except Exception:
            pass

    offset_act = bpy.data.actions.new(name=offset_act_name)
    offset_act.use_fake_user = True

    adt.action = offset_act
    bind_action_slot(adt, offset_act)

    bone_deltas = {
        "Head": Euler((math.radians(hp), math.radians(hy), 0.0), "XYZ").to_quaternion(),
        "neck_01": Euler((math.radians(hp * 0.4), math.radians(hy * 0.4), 0.0), "XYZ").to_quaternion(),
        "spine_01": Euler((math.radians(tb * 0.4), math.radians(tt * 0.4), 0.0), "XYZ").to_quaternion(),
        "spine_02": Euler((math.radians(tb * 0.35), math.radians(tt * 0.35), 0.0), "XYZ").to_quaternion(),
        "spine_03": Euler((math.radians(tb * 0.25), math.radians(tt * 0.25), 0.0), "XYZ").to_quaternion(),
        "clavicle_l": Euler((0.0, 0.0, math.radians(-af * 0.35)), "XYZ").to_quaternion(),
        "clavicle_r": Euler((0.0, 0.0, math.radians(af * 0.35)), "XYZ").to_quaternion(),
        "upperarm_l": Euler((math.radians(ar + af * 0.75), math.radians(-ai * 0.5), math.radians(-ar * 0.35 - ai * 0.65)), "XYZ").to_quaternion(),
        "upperarm_r": Euler((math.radians(ar + af * 0.75), math.radians(ai * 0.5), math.radians(ar * 0.35 + ai * 0.65)), "XYZ").to_quaternion(),
        "lowerarm_l": Euler((math.radians(eb), 0.0, math.radians(-eb * 0.3)), "XYZ").to_quaternion(),
        "lowerarm_r": Euler((math.radians(eb), 0.0, math.radians(eb * 0.3)), "XYZ").to_quaternion(),
    }

    for bname, quat in bone_deltas.items():
        pb = arm_obj.pose.bones.get(bname)
        if not pb:
            continue
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = quat
        pb.keyframe_insert(data_path="rotation_quaternion", frame=1)
        pb.keyframe_insert(data_path="rotation_quaternion", frame=2)

    if abs(pz) > 1e-3:
        pb_pelv = arm_obj.pose.bones.get("pelvis")
        if pb_pelv:
            # In pelvis bone local space, Y is vertical (+Z world)
            pb_pelv.location = (0.0, pz * 0.01, 0.0)
            pb_pelv.keyframe_insert(data_path="location", frame=1)
            pb_pelv.keyframe_insert(data_path="location", frame=2)

    bind_action_slot(adt, offset_act)
    adt.action = None

    _append_additive_track_on_top(adt, offset_act)
    return True
