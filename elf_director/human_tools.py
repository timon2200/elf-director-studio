# -*- coding: utf-8 -*-
"""
Human Viewport Tools, Raycast Ground Snapping, Look-At Orientation & Scale/Stride Sync
for ActionForge Elf Animation Director Studio v3.0.
"""

import inspect
import math
import bpy
from mathutils import Vector

from .constants import TEMPLATE_COLLECTION_NAME, ACTORS_COLLECTION_NAME
from .nla_sequencer import (
    assign_action_with_slot,
    get_nla_sequence_clips,
    rebuild_nla_sequence_from_specs,
    apply_additive_pose_offset,
)


def _call_attach_curve(context, ctrl_obj, curve_obj, speed_mps, loop_path, flip_forward, start_pct=0.0):
    """Calls `attach_controller_to_locomotion_curve` with optional `start_pct` compatibility."""
    from .locomotion import attach_controller_to_locomotion_curve
    sig = inspect.signature(attach_controller_to_locomotion_curve)
    kwargs = {
        "ctrl_obj": ctrl_obj,
        "curve_obj": curve_obj,
        "speed_mps": speed_mps,
        "loop_path": loop_path,
        "flip_forward": flip_forward,
    }
    if "start_pct" in sig.parameters:
        kwargs["start_pct"] = float(start_pct)
    return attach_controller_to_locomotion_curve(context, **kwargs)


def apply_stored_settings_to_character(context, ctrl_obj):
    """
    Applies the character's stored properties (`af_anim_name`, `af_anim_speed`,
    `af_frame_offset`, `af_loop_anim`, `af_char_scale`, `af_show_hat`, `af_show_glasses`,
    curve locomotion, and additive pose offsets) to its Armature, Meshes & Curve.
    """
    if not ctrl_obj:
        return

    from .rig_actors import get_character_armature_from_ctrl, set_actor_accessories
    from .locomotion import get_character_exact_stride_speed

    arm_obj = get_character_armature_from_ctrl(ctrl_obj)
    if not arm_obj:
        return

    if context is None:
        context = bpy.context

    # 1. Scale
    char_scale = float(ctrl_obj.get("af_char_scale", ctrl_obj.scale.z if ctrl_obj.scale.z > 0.05 else 1.0))
    char_scale = max(0.2, min(5.0, char_scale))
    ctrl_obj["af_char_scale"] = char_scale
    ctrl_obj.scale = (char_scale, char_scale, char_scale)

    # 2. Accessories (Hat / Glasses)
    show_hat = ctrl_obj.get("af_show_hat", None)
    show_glasses = ctrl_obj.get("af_show_glasses", None)
    if show_hat is not None or show_glasses is not None:
        set_actor_accessories(
            ctrl_obj,
            show_hat=bool(show_hat) if show_hat is not None else None,
            show_glasses=bool(show_glasses) if show_glasses is not None else None,
        )

    # 3. Base Animation (unless a multi-clip NLA sequence is active)
    anim_name = ctrl_obj.get("af_anim_name", "AF_01_Walk_Steady")
    anim_speed = float(ctrl_obj.get("af_anim_speed", 1.0))
    frame_offset = int(ctrl_obj.get("af_frame_offset", 0))
    loop_anim = bool(ctrl_obj.get("af_loop_anim", True))
    flip_dir = bool(ctrl_obj.get("af_flip_curve_dir", False))
    start_pct = float(ctrl_obj.get("af_curve_start_pct", 0.0))

    act = bpy.data.actions.get(anim_name)
    nla_clips = get_nla_sequence_clips(ctrl_obj)
    if nla_clips:
        specs = []
        for idx, c in enumerate(nla_clips):
            specs.append({
                "action": c["action_name"],
                "repeat": float(c.get("repeat", 1.0)),
                "speed": anim_speed,
                "blend": 0 if idx == 0 else int(round(float(c.get("blend_in", 12.0)))),
                "mode": str(c.get("mode", "AUTO")),
            })
        rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)
    elif act:
        assign_action_with_slot(
            arm_obj,
            act,
            speed_mult=anim_speed,
            frame_offset=frame_offset,
            loop_enabled=loop_anim,
        )

    if act:
        base_stride = float(act.get("af_speed_mps", 0.0))
        if base_stride > 0.1:
            ctrl_obj["af_walk_speed"] = get_character_exact_stride_speed(ctrl_obj, act)

    # 4. Curve Locomotion (single-animation mode; NLA sequence already synced above)
    curve_name = ctrl_obj.get("af_attached_curve", "")
    curve_obj = bpy.data.objects.get(curve_name) if curve_name else None
    if not nla_clips and curve_obj and (any(c.type == "FOLLOW_PATH" for c in ctrl_obj.constraints) or ctrl_obj.get("af_attached_curve")):
        _call_attach_curve(
            context,
            ctrl_obj=ctrl_obj,
            curve_obj=curve_obj,
            speed_mps=float(ctrl_obj.get("af_walk_speed", 1.42)),
            loop_path=loop_anim,
            flip_forward=flip_dir,
            start_pct=start_pct,
        )

    # 5. Additive Pose Offsets
    pose_vals = (
        float(ctrl_obj.get("af_pose_head_yaw", 0.0)),
        float(ctrl_obj.get("af_pose_head_pitch", 0.0)),
        float(ctrl_obj.get("af_pose_torso_bend", 0.0)),
        float(ctrl_obj.get("af_pose_torso_twist", 0.0)),
        float(ctrl_obj.get("af_pose_arms_raise", 0.0)),
    )
    if any(abs(v) > 1e-3 for v in pose_vals):
        apply_additive_pose_offset(ctrl_obj)


def _is_elf_internal_object(obj, ctrl_obj=None) -> bool:
    """Returns True if `obj` belongs to any Elf actor, template, or gizmo controller."""
    if not obj:
        return False
    if (
        obj == ctrl_obj
        or obj.get("af_is_char_controller")
        or obj.get("af_part_type")
        or obj.get("af_controller_name")
        or obj.get("af_is_template")
    ):
        return True
    if obj.parent and (
        obj.parent == ctrl_obj
        or obj.parent.type == "ARMATURE"
        or obj.parent.get("af_is_char_controller")
        or obj.parent.get("af_controller_name")
        or obj.parent.get("af_is_template")
    ):
        return True
    if any(mod.type == "ARMATURE" for mod in getattr(obj, "modifiers", ())):
        return True
    tpl_col = bpy.data.collections.get(TEMPLATE_COLLECTION_NAME)
    if tpl_col and obj.name in tpl_col.all_objects:
        return True
    return False


def snap_controller_to_ground(context, ctrl_obj, max_dist=50.0) -> tuple:
    """
    Casts a downward ray onto scene geometry (excluding character meshes in
    `01_SCENE_ELF_ACTORS` and `00_RIGGED_ELF_TEMPLATES`) and snaps `ctrl_obj.location.z`
    onto the ground surface (falls back to `Z = 0.0` if no floor mesh is hit).
    """
    if not ctrl_obj:
        return False, "Nije odabran kontroler vilenjaka."
    if context is None:
        context = bpy.context

    scene = context.scene
    try:
        context.view_layer.update()
    except Exception:
        pass

    deps = context.evaluated_depsgraph_get()
    pos = ctrl_obj.evaluated_get(deps).matrix_world.translation.copy()
    curr_origin = Vector((pos.x, pos.y, pos.z + 2.5))
    ray_dir = Vector((0.0, 0.0, -1.0))
    rem_dist = float(max_dist)

    ground_hit = False
    ground_loc = None
    ground_obj = None

    for _ in range(24):
        if rem_dist <= 0.001:
            break
        hit, hit_loc, _hit_norm, _hit_idx, hit_obj, _hit_mat = scene.ray_cast(
            deps, curr_origin, ray_dir, distance=rem_dist
        )
        if not hit or hit_obj is None:
            break
        if _is_elf_internal_object(hit_obj, ctrl_obj=ctrl_obj):
            step = max(0.002, (curr_origin.z - hit_loc.z) + 0.002)
            curr_origin.z -= step
            rem_dist -= step
            continue
        ground_hit = True
        ground_loc = hit_loc
        ground_obj = hit_obj
        break

    if ground_hit and ground_obj is not None:
        ctrl_obj.location.z = float(ground_loc.z)
        try:
            context.view_layer.update()
        except Exception:
            pass
        return True, f"'{ctrl_obj.name}' spušten na podlogu '{ground_obj.name}' (Z = {ground_loc.z:.3f} m)."

    ctrl_obj.location.z = 0.0
    try:
        context.view_layer.update()
    except Exception:
        pass
    return True, f"'{ctrl_obj.name}' postavljen na osnovnu razinu tla (Z = 0.000 m)."


def turn_controller_towards(context, ctrl_obj, target_mode="CAMERA", target_obj_name="", target_point=None) -> tuple:
    """
    Rotates `ctrl_obj` around Z so its forward direction (`-Y`) faces:
    - `"CAMERA"`: active scene camera
    - `"CURSOR"`: 3D Cursor
    - `"OBJECT"`: `bpy.data.objects.get(target_obj_name)`
    - `"POINT"`: explicit `(x, y, z)` tuple in `target_point`
    """
    if not ctrl_obj:
        return False, "Nije odabran kontroler vilenjaka."
    if context is None:
        context = bpy.context

    scene = context.scene
    try:
        context.view_layer.update()
    except Exception:
        pass
    target_vec = None
    target_label = target_mode

    mode_upper = str(target_mode).upper()
    if target_point is not None:
        target_vec = Vector((float(target_point[0]), float(target_point[1]), float(target_point[2])))
        target_label = f"({target_vec.x:.2f}, {target_vec.y:.2f})"
    elif mode_upper == "CAMERA":
        cam = scene.camera or next((o for o in scene.objects if o.type == "CAMERA"), None)
        if not cam:
            return False, "U sceni nije pronađena kamera."
        target_vec = cam.matrix_world.translation.copy()
        target_label = f"Kamera ({cam.name})"
    elif mode_upper == "CURSOR":
        target_vec = scene.cursor.location.copy()
        target_label = "3D Kursor"
    elif mode_upper == "OBJECT" or target_obj_name:
        t_obj = bpy.data.objects.get(target_obj_name or target_mode)
        if not t_obj:
            return False, f"Ciljni objekt '{target_obj_name or target_mode}' nije pronađen."
        target_vec = t_obj.matrix_world.translation.copy()
        target_label = t_obj.name
    else:
        return False, f"Nepoznat način okretanja: '{target_mode}'."

    deps = context.evaluated_depsgraph_get()
    pos = ctrl_obj.evaluated_get(deps).matrix_world.translation
    dx = float(target_vec.x - pos.x)
    dy = float(target_vec.y - pos.y)

    if math.hypot(dx, dy) < 1e-4:
        return False, "Ciljna točka je na istoj XY poziciji kao i vilenjak."

    # Character forward is -Y -> angle = atan2(dx, -dy)
    yaw_rad = math.atan2(dx, -dy)
    ctrl_obj.rotation_mode = "XYZ"
    ctrl_obj.rotation_euler.z = yaw_rad
    try:
        context.view_layer.update()
    except Exception:
        pass
    yaw_deg = math.degrees(yaw_rad)
    return True, f"'{ctrl_obj.name}' okrenut prema '{target_label}' (Z = {yaw_deg:.1f}°)."


def set_character_scale_with_stride(context, ctrl_obj, new_scale: float) -> float:
    """
    Clamps `new_scale` to `[0.2, 5.0]`, updates `ctrl_obj.scale` and `ctrl_obj["af_char_scale"]`,
    and automatically recalculates the exact biomechanical stride speed and curve locomotion.
    """
    if not ctrl_obj:
        return 1.0
    if context is None:
        context = bpy.context

    from .locomotion import get_character_exact_stride_speed

    clamped = max(0.2, min(5.0, float(new_scale)))
    ctrl_obj.scale = (clamped, clamped, clamped)
    ctrl_obj["af_char_scale"] = clamped

    anim_name = ctrl_obj.get("af_anim_name", "AF_01_Walk_Steady")
    act = bpy.data.actions.get(anim_name)
    exact_spd = get_character_exact_stride_speed(ctrl_obj, act)
    ctrl_obj["af_walk_speed"] = float(exact_spd)

    nla_clips = get_nla_sequence_clips(ctrl_obj)
    if nla_clips:
        specs = [
            {
                "action": c["action_name"],
                "repeat": float(c.get("repeat", 1.0)),
                "speed": float(ctrl_obj.get("af_anim_speed", 1.0)),
                "blend": 0 if idx == 0 else int(round(float(c.get("blend_in", 12.0)))),
                "mode": str(c.get("mode", "AUTO")),
            }
            for idx, c in enumerate(nla_clips)
        ]
        rebuild_nla_sequence_from_specs(ctrl_obj, specs, sync_curve=True)
        return clamped

    curve_name = ctrl_obj.get("af_attached_curve", "")
    curve_obj = bpy.data.objects.get(curve_name) if curve_name else None
    if curve_obj and any(c.type == "FOLLOW_PATH" for c in ctrl_obj.constraints):
        _call_attach_curve(
            context,
            ctrl_obj=ctrl_obj,
            curve_obj=curve_obj,
            speed_mps=exact_spd,
            loop_path=bool(ctrl_obj.get("af_loop_anim", True)),
            flip_forward=bool(ctrl_obj.get("af_flip_curve_dir", False)),
            start_pct=float(ctrl_obj.get("af_curve_start_pct", 0.0)),
        )

    return clamped
