# -*- coding: utf-8 -*-
"""
Agent-First Python SDK (`import elf_director as ed`)
for ActionForge Elf Animation Director Studio v3.0.

Provides a clean, high-level, self-documenting Python API for AI Agents and scripts
to spawn rigged Elves, assign/chain animations, create zero-slip locomotion curves,
toggle accessories, apply additive pose offsets, and run automated scene diagnostics.
"""

import inspect
import math
import bpy
from mathutils import Vector

from .constants import (
    RIGGED_ELF_ROSTER,
    TEMPLATE_COLLECTION_NAME,
    ACTORS_COLLECTION_NAME,
    PATHS_COLLECTION_NAME,
    ensure_collection,
)
from .database import (
    ensure_library_loaded,
    import_and_bake_animation_file,
    scan_dropin_animations,
    remove_animation_from_library,
    save_database_to_disk,
)
from .nla_sequencer import (
    get_nla_sequence_clips,
    append_animation_to_nla,
    chain_animations_on_controller,
    remove_nla_clip_at_index,
    move_nla_clip,
    clear_nla_sequence,
    apply_additive_pose_offset,
    clear_additive_pose_offset,
)
from .human_tools import (
    apply_stored_settings_to_character,
    snap_controller_to_ground,
    turn_controller_towards,
    set_character_scale_with_stride,
    _call_attach_curve,
)


def _resolve_ctrl(ctrl_or_name):
    """Resolves a `CTRL_*` object from a Blender Object, child mesh/armature, or string name."""
    from .rig_actors import find_character_controller, get_active_character_controller

    if ctrl_or_name is None:
        return get_active_character_controller(bpy.context)
    if isinstance(ctrl_or_name, str):
        obj = bpy.data.objects.get(ctrl_or_name)
        return find_character_controller(obj) if obj else None
    return find_character_controller(ctrl_or_name)


def _resolve_curve(curve_or_name):
    """Resolves a `CURVE` object from a Blender Object or string name."""
    if curve_or_name is None:
        return None
    if isinstance(curve_or_name, str):
        obj = bpy.data.objects.get(curve_or_name)
        return obj if (obj and obj.type == "CURVE") else None
    return curve_or_name if getattr(curve_or_name, "type", None) == "CURVE" else None


def integrate_into_scene(spawn_demo: bool = False) -> dict:
    """
    One-call integration into any Blender scene:
    1. Appends missing 7 rigged Elf templates + 24+ `AF_*` animations from `database/elf_assets_library.blend`.
    2. Scans `database/animations_dropin/` for any drop-in `.glb`/`.fbx` animations.
    3. Ensures scene collections and registers the `Elf Director` N-panel UI & operators.
    4. Optionally spawns a demo character if `spawn_demo=True`.
    """
    lib_status = ensure_library_loaded(load_templates=True, load_actions=True)
    dropin_imported = scan_dropin_animations(save_to_db=False)

    ensure_collection(TEMPLATE_COLLECTION_NAME)
    ensure_collection(ACTORS_COLLECTION_NAME)
    ensure_collection(PATHS_COLLECTION_NAME)

    try:
        from .operators_ui import register
        register()
    except Exception as e:
        print(f"[ElfDirector] Warning during UI registration: {e}")

    from .rig_actors import get_all_scene_character_controllers
    if spawn_demo and len(get_all_scene_character_controllers()) == 0:
        crv = create_walk_curve(
            name="Demo_Walk_Path",
            points=[(-3.0, -2.0, 0.0), (0.0, 0.0, 0.0), (3.0, -1.5, 0.0)],
            cyclic=False,
        )
        ctrl = spawn(elf_id="ELF10", location=(0.0, 0.0, 0.0), animation="AF_01_Walk_Steady")
        if ctrl and crv:
            follow_curve(ctrl, crv, start_pct=0.0, loop=True)

    return {
        "ok": True,
        **lib_status,
        "dropin_imported": dropin_imported,
        "actors_in_scene": len(get_all_scene_character_controllers()),
    }


def list_available_elves() -> list:
    """Returns metadata for all 7 rigged Elves in the studio roster."""
    result = []
    for e in RIGGED_ELF_ROSTER:
        arm = bpy.data.objects.get(e["arm_name"])
        result.append({
            "id": e["id"],
            "code": e.get("code", ""),
            "title": e["title"],
            "template_armature": e["arm_name"],
            "collection": e["col_name"],
            "loaded": arm is not None,
            "has_hat": bool(e.get("has_hat", False)),
            "has_glasses": bool(e.get("has_glasses", False)),
        })
    return result


def list_available_animations(category: str = None) -> list:
    """
    Lists all available `AF_*` animations in `bpy.data.actions` (auto-loading from the
    library if needed), optionally filtered by `category` (e.g. `'LOCOMOTION'`, `'IDLE'`, `'WORK'`, `'TALK'`).
    """
    has_af = any(
        a.name.startswith("AF_") and not a.name.startswith("AF_PoseOffset_")
        for a in bpy.data.actions
    )
    if not has_af:
        ensure_library_loaded(load_templates=False, load_actions=True)

    cat_filter = category.strip().upper() if category else None
    items = []
    for act in sorted(bpy.data.actions, key=lambda a: a.name):
        if act.name.startswith("PathAnim_") or act.name.startswith("AF_PoseOffset_"):
            continue
        if not (act.name.startswith("AF_") or act.get("af_category")):
            continue
        act_cat = str(act.get("af_category", "CUSTOM")).upper()
        if cat_filter and act_cat != cat_filter:
            continue
        frames = max(1, int(round(act.frame_range[1] - act.frame_range[0])) + 1)
        items.append({
            "name": act.name,
            "category": act_cat,
            "is_locomotion": bool(act.get("af_is_locomotion", False)),
            "speed_mps": round(float(act.get("af_speed_mps", 0.0)), 4),
            "is_backwards": bool(act.get("af_is_backwards", False)),
            "frames": frames,
        })
    return items


def get_scene_manifest() -> dict:
    """
    Returns a complete JSON-serializable manifest of all spawned Elf actors,
    active animations, NLA sequences, locomotion curves, accessories, and pose offsets.
    """
    from .rig_actors import (
        get_all_scene_character_controllers,
        get_character_armature_from_ctrl,
        get_actor_part_meshes,
    )
    from .locomotion import compute_curve_true_1d_length

    deps = bpy.context.evaluated_depsgraph_get() if bpy.context else None
    actors_info = []

    for ctrl in get_all_scene_character_controllers():
        arm = get_character_armature_from_ctrl(ctrl)
        parts = get_actor_part_meshes(ctrl)
        eval_ctrl = ctrl.evaluated_get(deps) if deps else ctrl
        loc = eval_ctrl.matrix_world.translation
        rot_z_deg = round(math.degrees(eval_ctrl.matrix_world.to_euler("XYZ").z), 2)

        hat_mesh = parts.get("HAT")
        glasses_mesh = parts.get("GLASSES")
        if isinstance(hat_mesh, list):
            hat_mesh = hat_mesh[0] if hat_mesh else None
        if isinstance(glasses_mesh, list):
            glasses_mesh = glasses_mesh[0] if glasses_mesh else None
        show_hat = bool(ctrl.get("af_show_hat", not hat_mesh.hide_viewport if hat_mesh else False))
        show_glasses = bool(ctrl.get("af_show_glasses", not glasses_mesh.hide_viewport if glasses_mesh else False))

        actors_info.append({
            "name": ctrl.name,
            "elf_id": ctrl.get("af_elf_id", "ELF10"),
            "elf_title": ctrl.get("af_elf_title", ""),
            "armature": arm.name if arm else "",
            "location": [round(float(loc.x), 4), round(float(loc.y), 4), round(float(loc.z), 4)],
            "rotation_z_deg": rot_z_deg,
            "scale": round(float(ctrl.get("af_char_scale", ctrl.scale.z)), 3),
            "active_animation": ctrl.get("af_anim_name", ""),
            "anim_speed": round(float(ctrl.get("af_anim_speed", 1.0)), 3),
            "frame_offset": int(ctrl.get("af_frame_offset", 0)),
            "loop": bool(ctrl.get("af_loop_anim", True)),
            "nla_clips": get_nla_sequence_clips(ctrl),
            "attached_curve": ctrl.get("af_attached_curve", ""),
            "curve_start_pct": round(float(ctrl.get("af_curve_start_pct", 0.0)), 2),
            "walk_speed_mps": round(float(ctrl.get("af_walk_speed", 0.0)), 4),
            "show_hat": show_hat,
            "show_glasses": show_glasses,
            "pose_offsets": {
                "head_yaw": round(float(ctrl.get("af_pose_head_yaw", 0.0)), 2),
                "head_pitch": round(float(ctrl.get("af_pose_head_pitch", 0.0)), 2),
                "torso_bend": round(float(ctrl.get("af_pose_torso_bend", 0.0)), 2),
                "torso_twist": round(float(ctrl.get("af_pose_torso_twist", 0.0)), 2),
                "arms_raise": round(float(ctrl.get("af_pose_arms_raise", 0.0)), 2),
            },
        })

    curves_info = []
    paths_col = bpy.data.collections.get(PATHS_COLLECTION_NAME)
    if paths_col:
        for obj in sorted(paths_col.all_objects, key=lambda o: o.name):
            if obj.type == "CURVE" and obj.data:
                is_cyclic = any(s.use_cyclic_u for s in obj.data.splines)
                curves_info.append({
                    "name": obj.name,
                    "length_m": round(float(compute_curve_true_1d_length(obj)), 3),
                    "cyclic": is_cyclic,
                    "path_duration": int(obj.data.path_duration),
                })

    templates_loaded = sum(1 for e in RIGGED_ELF_ROSTER if bpy.data.objects.get(e["arm_name"]) is not None)
    anims_loaded = len(list_available_animations())

    scn = bpy.context.scene if bpy.context else None
    return {
        "actors_count": len(actors_info),
        "actors": actors_info,
        "curves_count": len(curves_info),
        "curves": curves_info,
        "templates_loaded": templates_loaded,
        "animations_loaded": anims_loaded,
        "frame_range": [scn.frame_start, scn.frame_end] if scn else [1, 180],
        "fps": scn.render.fps if scn else 30,
    }


def spawn(
    elf_id: str = "ELF10",
    location=(0.0, 0.0, 0.0),
    rotation_z_deg: float = 0.0,
    scale: float = 1.0,
    animation: str = "AF_01_Walk_Steady",
    frame_offset: int = 0,
    show_hat=None,
    show_glasses=None,
):
    """
    Spawns a rigged Elf character wrapped inside a Master Floor Ring Gizmo (`CTRL_*`).
    Automatically loads `database/elf_assets_library.blend` if templates/animations are not yet in the scene.
    """
    ensure_library_loaded(load_templates=True, load_actions=True)
    from .rig_actors import spawn_elf_actor, set_actor_accessories

    sig = inspect.signature(spawn_elf_actor)
    kwargs = {
        "elf_id": elf_id,
        "location": location,
        "initial_action_name": animation,
        "frame_offset": int(frame_offset),
    }
    if "rotation_z_deg" in sig.parameters:
        kwargs["rotation_z_deg"] = float(rotation_z_deg)
    if "scale" in sig.parameters:
        kwargs["scale"] = float(scale)
    if "show_hat" in sig.parameters:
        kwargs["show_hat"] = show_hat
    if "show_glasses" in sig.parameters:
        kwargs["show_glasses"] = show_glasses

    ctrl = spawn_elf_actor(bpy.context, **kwargs)
    if not ctrl:
        return None

    if "rotation_z_deg" not in sig.parameters and abs(float(rotation_z_deg)) > 1e-4:
        ctrl.rotation_mode = "XYZ"
        ctrl.rotation_euler.z = math.radians(float(rotation_z_deg))

    if abs(float(scale) - 1.0) > 1e-4:
        set_character_scale_with_stride(bpy.context, ctrl, float(scale))
    else:
        ctrl["af_char_scale"] = 1.0

    if show_hat is not None or show_glasses is not None:
        set_actor_accessories(ctrl, show_hat=show_hat, show_glasses=show_glasses)

    return ctrl


def set_animation(
    ctrl_or_name,
    animation_name: str,
    speed: float = 1.0,
    frame_offset: int = 0,
    loop: bool = True,
) -> bool:
    """Assigns a single animation (with speed & frame offset) to the specified character controller."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False
    ensure_library_loaded(load_templates=False, load_actions=True)
    act = bpy.data.actions.get(animation_name)
    if not act:
        return False

    if get_nla_sequence_clips(ctrl):
        clear_nla_sequence(ctrl)

    ctrl["af_anim_name"] = act.name
    ctrl["af_anim_speed"] = float(speed)
    ctrl["af_frame_offset"] = int(frame_offset)
    ctrl["af_loop_anim"] = bool(loop)
    apply_stored_settings_to_character(bpy.context, ctrl)
    return True


def chain_animations(ctrl_or_name, clips: list, blend_frames: int = 12) -> tuple:
    """
    Chains multiple animations in NLA with smooth crossfades.
    `clips` may be a list of action names `["AF_01_Walk_Steady", "AF_18_Work_UseTool"]`
    or dicts `[{"action": "AF_01_Walk_Steady", "repeat": 2.0, "speed": 1.0, "blend": 12}, ...]`.
    """
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False, f"Kontroler '{ctrl_or_name}' nije pronađen."
    ensure_library_loaded(load_templates=False, load_actions=True)
    return chain_animations_on_controller(ctrl, clips, default_blend_frames=int(blend_frames))


def remove_nla_clip(ctrl_or_name, clip_index: int) -> tuple:
    """Removes the NLA clip at `clip_index` from the character's NLA sequence."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False, f"Kontroler '{ctrl_or_name}' nije pronađen."
    return remove_nla_clip_at_index(ctrl, int(clip_index))


def clear_nla(ctrl_or_name) -> bool:
    """Clears the multi-clip NLA sequence and returns the character to single-animation mode."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False
    return clear_nla_sequence(ctrl)


def create_walk_curve(name: str = "Walk_Path", points=None, cyclic: bool = False):
    """Creates a resampled uniform-arclength 3D Bezier locomotion curve from a list of `(x, y, z)` points."""
    from .locomotion import create_walk_curve_from_points
    sig = inspect.signature(create_walk_curve_from_points)
    if "context" in sig.parameters:
        return create_walk_curve_from_points(bpy.context, name=name, points=points, cyclic=cyclic)
    return create_walk_curve_from_points(name=name, points=points, cyclic=cyclic)


def follow_curve(
    ctrl_or_name,
    curve_or_name,
    start_pct: float = 0.0,
    speed_mps=None,
    loop: bool = True,
    flip_dir: bool = False,
) -> tuple:
    """
    Attaches `ctrl_or_name` to follow `curve_or_name` at the exact biomechanical stride speed
    (0% foot sliding), starting at `start_pct` (0..100%) along the curve.
    """
    ctrl = _resolve_ctrl(ctrl_or_name)
    curve = _resolve_curve(curve_or_name)
    if not ctrl or not curve:
        return False, "Valjani kontroler vilenjaka ili krivulja nisu pronađeni."

    ctrl["af_curve_start_pct"] = float(start_pct)
    ctrl["af_loop_anim"] = bool(loop)
    ctrl["af_flip_curve_dir"] = bool(flip_dir)

    return _call_attach_curve(
        bpy.context,
        ctrl_obj=ctrl,
        curve_obj=curve,
        speed_mps=speed_mps,
        loop_path=bool(loop),
        flip_forward=bool(flip_dir),
        start_pct=float(start_pct),
    )


def detach_curve(ctrl_or_name) -> bool:
    """Detaches `ctrl_or_name` from its locomotion curve while preserving its current world transform."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False
    from .locomotion import detach_controller_from_curve
    sig = inspect.signature(detach_controller_from_curve)
    if "context" in sig.parameters:
        res = detach_controller_from_curve(bpy.context, ctrl)
    else:
        res = detach_controller_from_curve(ctrl)
    return bool(res[0]) if isinstance(res, tuple) else bool(res)


def set_accessories(ctrl_or_name, hat=None, glasses=None) -> dict:
    """Toggles Hat (`HAT`) and Glasses (`GLASSES`) visibility (viewport & render) on `ctrl_or_name`."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return {"ok": False}
    from .rig_actors import set_actor_accessories
    return set_actor_accessories(ctrl, show_hat=hat, show_glasses=glasses)


def snap_to_ground(ctrl_or_name) -> tuple:
    """Raycasts downward and snaps `ctrl_or_name` onto the floor mesh below it."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False, f"Kontroler '{ctrl_or_name}' nije pronađen."
    return snap_controller_to_ground(bpy.context, ctrl)


def look_at(ctrl_or_name, target="CAMERA") -> tuple:
    """
    Rotates `ctrl_or_name` on Z to face `target`.
    `target` can be `"CAMERA"`, `"CURSOR"`, an object name, a `bpy.types.Object`, or an `(x, y, z)` tuple/list.
    """
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False, f"Kontroler '{ctrl_or_name}' nije pronađen."

    if isinstance(target, (tuple, list, Vector)) and len(target) >= 2:
        pt = (float(target[0]), float(target[1]), float(target[2]) if len(target) > 2 else 0.0)
        return turn_controller_towards(bpy.context, ctrl, target_mode="POINT", target_point=pt)
    if hasattr(target, "name"):
        return turn_controller_towards(bpy.context, ctrl, target_mode="OBJECT", target_obj_name=target.name)
    if isinstance(target, str) and target.upper() in ("CAMERA", "CURSOR"):
        return turn_controller_towards(bpy.context, ctrl, target_mode=target.upper())
    return turn_controller_towards(bpy.context, ctrl, target_mode="OBJECT", target_obj_name=str(target))


def set_scale(ctrl_or_name, scale: float = 1.0) -> float:
    """Sets character scale (`[0.2, 5.0]`) and automatically recalculates exact biomechanical stride speed."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return 1.0
    return set_character_scale_with_stride(bpy.context, ctrl, float(scale))


def set_pose_offset(
    ctrl_or_name,
    head_yaw: float = 0.0,
    head_pitch: float = 0.0,
    torso_bend: float = 0.0,
    torso_twist: float = 0.0,
    arms_raise: float = 0.0,
) -> bool:
    """Applies non-destructive additive NLA bone offsets (in degrees) on top of the active animation."""
    ctrl = _resolve_ctrl(ctrl_or_name)
    if not ctrl:
        return False
    return apply_additive_pose_offset(
        ctrl,
        head_yaw_deg=float(head_yaw),
        head_pitch_deg=float(head_pitch),
        torso_bend_deg=float(torso_bend),
        torso_twist_deg=float(torso_twist),
        arms_raise_deg=float(arms_raise),
    )


def import_animation(
    filepath: str,
    action_name: str = None,
    in_place=None,
    category: str = "CUSTOM",
    save_to_db: bool = False,
):
    """Imports and bakes an external `.glb`/`.fbx` animation onto the canonical ActionForge Elf rig."""
    act = import_and_bake_animation_file(
        filepath=filepath,
        action_name=action_name,
        in_place=in_place,
        category=category,
        save_to_db=save_to_db,
    )
    return act.name if act else None


def remove_animation(action_name: str, save_to_db: bool = False) -> tuple:
    """Removes `action_name` from the library (protecting `AF_06_Idle_Breathing`) and optionally updates disk DB."""
    return remove_animation_from_library(action_name, save_to_db=save_to_db)


def verify_scene() -> dict:
    """
    Runs automated verification diagnostics on all Elf actors in the scene:
    1. Verifies every `CTRL_*` has a valid child armature and `BODY` + `HEAD` meshes.
    2. Samples pose bone positions at frames 1 and 25 to verify skeletal animation is active.
    3. Samples world translation at frames 1, 20, 40, 60 for curve-following actors and verifies
       world displacement > 0.20 m (proving the character is moving along the curve and not stuck).
    """
    from .rig_actors import (
        get_all_scene_character_controllers,
        get_character_armature_from_ctrl,
        get_actor_part_meshes,
    )

    scn = bpy.context.scene
    orig_frame = scn.frame_current
    ctrls = get_all_scene_character_controllers()

    issues = []
    details = []

    try:
        # Sample positions across frames 1, 20, 25, 40, 60
        sample_frames = (1, 20, 25, 40, 60)
        ctrl_world_pos = {c.name: {} for c in ctrls}
        bone_pose_pos = {c.name: {} for c in ctrls}

        for f in sample_frames:
            scn.frame_set(f)
            deps = bpy.context.evaluated_depsgraph_get()
            for c in ctrls:
                eval_c = c.evaluated_get(deps)
                ctrl_world_pos[c.name][f] = eval_c.matrix_world.translation.copy()
                arm = get_character_armature_from_ctrl(c)
                if arm:
                    eval_arm = arm.evaluated_get(deps)
                    b_pts = []
                    for bname in ("Head", "hand_l", "hand_r", "foot_l", "foot_r", "pelvis"):
                        pb = eval_arm.pose.bones.get(bname)
                        if pb:
                            b_pts.append(pb.head.copy())
                    bone_pose_pos[c.name][f] = b_pts

        for c in ctrls:
            arm = get_character_armature_from_ctrl(c)
            parts = get_actor_part_meshes(c)
            body_part = parts.get("BODY")
            head_part = parts.get("HEAD")
            has_body = bool(body_part)
            has_head = bool(head_part)

            actor_issues = []
            if not arm:
                actor_issues.append("Missing child armature")
            if not has_body:
                actor_issues.append("Missing BODY mesh")
            if not has_head:
                actor_issues.append("Missing HEAD mesh")

            # Pose motion check between frame 1 and frame 25
            pts_f1 = bone_pose_pos[c.name].get(1, [])
            pts_f25 = bone_pose_pos[c.name].get(25, [])
            pose_delta = 0.0
            if pts_f1 and pts_f25 and len(pts_f1) == len(pts_f25):
                pose_delta = sum((a - b).length for a, b in zip(pts_f1, pts_f25))
            if pose_delta < 1e-4:
                actor_issues.append(f"Pose static between frame 1 and 25 (delta={pose_delta:.5f})")

            # Curve locomotion check across frames 1, 20, 40, 60
            attached_curve = c.get("af_attached_curve", "")
            curve_disp = 0.0
            if attached_curve and any(con.type == "FOLLOW_PATH" for con in c.constraints):
                p1 = ctrl_world_pos[c.name][1]
                max_d = max((ctrl_world_pos[c.name][sf] - p1).length for sf in (20, 40, 60))
                curve_disp = float(max_d)
                if curve_disp <= 0.20:
                    actor_issues.append(
                        f"Curve follower '{c.name}' on '{attached_curve}' moved only {curve_disp:.3f}m (< 0.20m threshold)"
                    )

            for iss in actor_issues:
                issues.append(f"{c.name}: {iss}")

            details.append({
                "name": c.name,
                "elf_id": c.get("af_elf_id", ""),
                "has_armature": arm is not None,
                "has_body": has_body,
                "has_head": has_head,
                "pose_delta_1_to_25": round(float(pose_delta), 4),
                "attached_curve": attached_curve,
                "curve_displacement_m": round(float(curve_disp), 4),
                "ok": len(actor_issues) == 0,
                "issues": actor_issues,
            })
    finally:
        scn.frame_set(orig_frame)

    return {
        "ok": len(issues) == 0,
        "actors_checked": len(ctrls),
        "issues": issues,
        "details": details,
    }
