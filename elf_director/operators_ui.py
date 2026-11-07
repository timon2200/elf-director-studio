# -*- coding: utf-8 -*-
"""
Blender Operators, Reactive Property Callbacks, Selection Redirect Handler & N-Panel UI
for ActionForge Elf Animation Director Studio v3.0.
"""

import os
import random
import sys
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector

from .constants import (
    DEFAULT_WALK_ACTION,
    PATHS_COLLECTION_NAME,
    RIGGED_ELF_ROSTER,
    STATE,
    TEMPLATE_COLLECTION_NAME,
    ensure_collection,
)
from .database import (
    ensure_library_loaded,
    import_and_bake_animation_file,
    remove_animation_from_library,
    save_database_to_disk,
    scan_dropin_animations,
)
from .rig_actors import (
    af_proxy_render_post_handler,
    af_proxy_render_pre_handler,
    delete_elf_actor,
    duplicate_elf_actor,
    enable_viewport_transform_gizmos,
    find_character_controller,
    get_active_character_controller,
    get_all_scene_character_controllers,
    get_character_armature_from_ctrl,
    set_actor_accessories,
    set_scene_viewport_proxy_mode,
    spawn_elf_actor,
    swap_character_model_on_controller,
)
from .locomotion import (
    attach_controller_to_locomotion_curve,
    detach_controller_from_curve,
    get_character_exact_stride_speed,
)
from .nla_sequencer import (
    adjust_nla_clip_repeat,
    append_animation_to_nla,
    apply_additive_pose_offset,
    clear_additive_pose_offset,
    clear_nla_sequence,
    get_nla_sequence_clips,
    move_nla_clip,
    remove_nla_clip_at_index,
    toggle_nla_clip_fill_mode,
)
from .human_tools import (
    apply_stored_settings_to_character,
    set_character_scale_with_stride,
    snap_controller_to_ground,
    turn_controller_towards,
)
from .previews import (
    get_anim_loop_icon_id,
    get_anim_thumb_icon_id,
    get_anim_video_path,
    get_current_loop_frame_index,
    get_elf_preview_icon_id,
    get_html_catalog_path,
    register_previews,
    step_loop_frame,
    unregister_previews,
)

_ELF_ENUM_ITEMS_CACHE = []
_ANIM_ENUM_ITEMS_CACHE = []


# ============================================================================
# 1. UI PROPERTY SYNC & SELECTION REDIRECT HANDLER
# ============================================================================

def sync_ui_properties_from_controller(ctrl_obj, sync_anim_dropdown=True):
    """Copies the selected character's stored settings into the N-panel UI properties without triggering edits."""
    if not ctrl_obj or STATE.get("ui_sync_guard", False):
        return
    if not bpy.context or not bpy.context.scene:
        return

    scn = bpy.context.scene
    STATE["ui_sync_guard"] = True
    try:
        elf_id = ctrl_obj.get("af_elf_id", "ELF10")
        anim_name = ctrl_obj.get("af_anim_name", DEFAULT_WALK_ACTION)
        anim_speed = float(ctrl_obj.get("af_anim_speed", 1.0))
        frame_offset = int(ctrl_obj.get("af_frame_offset", 0))
        loop_anim = bool(ctrl_obj.get("af_loop_anim", True))
        flip_dir = bool(ctrl_obj.get("af_flip_curve_dir", False))
        walk_spd = float(ctrl_obj.get("af_walk_speed", 1.42))
        start_pct = float(ctrl_obj.get("af_curve_start_pct", 0.0))
        char_scale = float(ctrl_obj.get("af_char_scale", ctrl_obj.scale.z if ctrl_obj.scale.z > 0.05 else 1.0))
        show_hat = bool(ctrl_obj.get("af_show_hat", False))
        show_glasses = bool(ctrl_obj.get("af_show_glasses", False))

        if hasattr(scn, "af_director_elf_enum") and scn.af_director_elf_enum != elf_id:
            scn.af_director_elf_enum = elf_id
        if (
            sync_anim_dropdown
            and hasattr(scn, "af_director_anim_enum")
            and bpy.data.actions.get(anim_name)
            and scn.af_director_anim_enum != anim_name
        ):
            scn.af_director_anim_enum = anim_name

        scn.af_director_anim_speed = anim_speed
        scn.af_director_frame_offset = frame_offset
        scn.af_director_loop_anim = loop_anim
        scn.af_director_flip_curve_dir = flip_dir
        scn.af_director_walk_speed = walk_spd
        scn.af_director_curve_start_pct = start_pct
        scn.af_director_char_scale = char_scale
        scn.af_director_show_hat = show_hat
        scn.af_director_show_glasses = show_glasses

        scn.af_director_pose_head_yaw = float(ctrl_obj.get("af_pose_head_yaw", 0.0))
        scn.af_director_pose_head_pitch = float(ctrl_obj.get("af_pose_head_pitch", 0.0))
        scn.af_director_pose_torso_bend = float(ctrl_obj.get("af_pose_torso_bend", 0.0))
        scn.af_director_pose_torso_twist = float(ctrl_obj.get("af_pose_torso_twist", 0.0))
        scn.af_director_pose_arms_raise = float(ctrl_obj.get("af_pose_arms_raise", 0.0))
        scn.af_director_pose_arms_forward = float(ctrl_obj.get("af_pose_arms_forward", 0.0))
        scn.af_director_pose_arms_inward = float(ctrl_obj.get("af_pose_arms_inward", 0.0))
        scn.af_director_pose_elbows_bend = float(ctrl_obj.get("af_pose_elbows_bend", 0.0))
        scn.af_director_pose_pelvis_z_cm = float(ctrl_obj.get("af_pose_pelvis_z_cm", 0.0))

        all_ctrls = get_all_scene_character_controllers()
        if ctrl_obj in all_ctrls:
            idx = all_ctrls.index(ctrl_obj)
            if scn.af_director_active_char_index != idx:
                scn.af_director_active_char_index = idx

        try:
            from .minecart_pusher_ui import sync_minecart_ui_from_controller
            sync_minecart_ui_from_controller(ctrl_obj)
        except Exception:
            pass
    except Exception:
        pass
    finally:
        STATE["ui_sync_guard"] = False


def _is_editable_prop_object(obj) -> bool:
    """Returns True if `obj` or its parent is an editable workbench prop, hand tool, cliff basket gizmo, or minecart."""
    if not obj:
        return False
    curr = obj
    while curr:
        if (
            curr.get("af_is_editable_prop")
            or curr.get("af_is_minecart_prop")
            or curr.get("af_is_basket_gizmo")
            or curr.get("af_is_cliff_basket_rig")
            or curr.get("af_is_ropeway_null")
            or curr.get("af_is_ropeway_system")
            or curr.name.startswith(("Prop_", "PROP_", "GIZMO_", "BASKET_", "CB_ROOT_", "MC_", "RW_SYS_", "GONDOLA_"))
        ):
            return True
        if curr.get("af_is_char_controller"):
            return False
        curr = curr.parent
    return False


def _set_viewport_prop_gizmos(enabled: bool):
    if bpy.app.background:
        return
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            space.show_gizmo_object_translate = bool(enabled)
                            space.show_gizmo_object_rotate = bool(enabled)
    except Exception:
        pass


@persistent
def af_selection_redirect_handler(scene, depsgraph=None):
    """
    Whenever the user clicks ANY part of a character (head, body, hat, glasses, or armature)
    in Object Mode, automatically selects the character's Master Gizmo Controller (`CTRL_*`)
    and syncs the N-panel UI to reflect that character's data.
    If the user clicks an editable prop (`Prop_*` / `PROP_ROOT_*`), keeps the prop selected
    for direct G/R/S editing and enables viewport transform gizmos.
    """
    if STATE.get("selection_redirect_guard", False) or bpy.app.background:
        return
    if getattr(scene, "af_director_allow_subpart_select", False):
        return

    context = bpy.context
    scr = getattr(context, "screen", None)
    if scr and getattr(scr, "is_animation_playing", False):
        return
    active_obj = getattr(context, "active_object", None)
    if not active_obj or active_obj.mode != "OBJECT":
        return

    # Allow direct selection & G/R/S editing of props and hand tools!
    if _is_editable_prop_object(active_obj):
        _set_viewport_prop_gizmos(True)
        st_ctrl = find_character_controller(active_obj)
        if st_ctrl and scene.get("_af_last_synced_ctrl") != st_ctrl.name:
            scene["_af_last_synced_ctrl"] = st_ctrl.name
            sync_ui_properties_from_controller(st_ctrl)
        return

    ctrl = find_character_controller(active_obj)
    if not ctrl:
        return

    STATE["selection_redirect_guard"] = True
    try:
        if active_obj != ctrl or any(find_character_controller(o) == ctrl and o != ctrl for o in context.selected_objects):
            for o in list(context.selected_objects):
                if find_character_controller(o) == ctrl and o != ctrl and not _is_editable_prop_object(o):
                    o.select_set(False)
            ctrl.select_set(True)
            context.view_layer.objects.active = ctrl
            enable_viewport_transform_gizmos()

        if scene.get("_af_last_synced_ctrl") != ctrl.name:
            scene["_af_last_synced_ctrl"] = ctrl.name
            sync_ui_properties_from_controller(ctrl)
    except Exception:
        pass
    finally:
        STATE["selection_redirect_guard"] = False


# ============================================================================
# 2. REACTIVE UPDATE CALLBACKS (EDITS ONLY THE SELECTED CHARACTER)
# ============================================================================

def on_ui_elf_type_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if ctrl:
        swap_character_model_on_controller(
            context,
            ctrl,
            self.af_director_elf_enum,
            apply_settings_callback=apply_stored_settings_to_character,
        )
        sync_ui_properties_from_controller(ctrl)


def on_ui_anim_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    # If an NLA sequence is active, choosing an animation in the dropdown/gallery previews it
    # for the next '+ Spoji u NLA Sekvencu' click without overwriting the active NLA stack!
    if get_nla_sequence_clips(ctrl):
        return
    ctrl["af_anim_name"] = self.af_director_anim_enum
    apply_stored_settings_to_character(context, ctrl)
    sync_ui_properties_from_controller(ctrl, sync_anim_dropdown=False)


def on_ui_playback_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    ctrl["af_anim_speed"] = float(self.af_director_anim_speed)
    ctrl["af_frame_offset"] = int(self.af_director_frame_offset)
    ctrl["af_loop_anim"] = bool(self.af_director_loop_anim)
    ctrl["af_flip_curve_dir"] = bool(self.af_director_flip_curve_dir)
    ctrl["af_curve_start_pct"] = float(self.af_director_curve_start_pct)
    apply_stored_settings_to_character(context, ctrl)
    sync_ui_properties_from_controller(ctrl, sync_anim_dropdown=False)


def on_ui_walk_speed_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    ctrl["af_walk_speed"] = float(self.af_director_walk_speed)
    curve_name = ctrl.get("af_attached_curve", "")
    curve_obj = bpy.data.objects.get(curve_name) if curve_name else None
    if curve_obj:
        attach_controller_to_locomotion_curve(
            context,
            ctrl_obj=ctrl,
            curve_obj=curve_obj,
            speed_mps=float(self.af_director_walk_speed),
            loop_path=bool(ctrl.get("af_loop_anim", True)),
            flip_forward=bool(ctrl.get("af_flip_curve_dir", False)),
            start_pct=float(ctrl.get("af_curve_start_pct", 0.0)),
        )


def on_ui_scale_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    set_character_scale_with_stride(context, ctrl, float(self.af_director_char_scale))
    sync_ui_properties_from_controller(ctrl)


def on_ui_accessories_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    set_actor_accessories(
        ctrl,
        show_hat=bool(self.af_director_show_hat),
        show_glasses=bool(self.af_director_show_glasses),
        equip_if_missing=True,
    )


def on_ui_pose_offset_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    apply_additive_pose_offset(
        ctrl,
        head_yaw_deg=float(self.af_director_pose_head_yaw),
        head_pitch_deg=float(self.af_director_pose_head_pitch),
        torso_bend_deg=float(self.af_director_pose_torso_bend),
        torso_twist_deg=float(self.af_director_pose_torso_twist),
        arms_raise_deg=float(self.af_director_pose_arms_raise),
        arms_forward_deg=float(getattr(self, "af_director_pose_arms_forward", 0.0)),
        arms_inward_deg=float(getattr(self, "af_director_pose_arms_inward", 0.0)),
        elbows_bend_deg=float(getattr(self, "af_director_pose_elbows_bend", 0.0)),
        pelvis_z_cm=float(getattr(self, "af_director_pose_pelvis_z_cm", 0.0)),
    )


def on_active_char_index_changed(self, context):
    if STATE.get("ui_sync_guard", False):
        return
    all_ctrls = get_all_scene_character_controllers()
    idx = self.af_director_active_char_index
    if 0 <= idx < len(all_ctrls):
        ctrl = all_ctrls[idx]
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        ctrl.select_set(True)
        context.view_layer.objects.active = ctrl
        enable_viewport_transform_gizmos()
        sync_ui_properties_from_controller(ctrl)


def get_elf_enum_items(self, context):
    global _ELF_ENUM_ITEMS_CACHE
    items = []
    for idx, e in enumerate(RIGGED_ELF_ROSTER):
        icon_id = get_elf_preview_icon_id(e["id"])
        if icon_id > 0:
            items.append((e["id"], e["title"], f"Select or swap to {e['title']}", icon_id, idx))
        else:
            items.append((e["id"], e["title"], f"Select or swap to {e['title']}", "OUTLINER_OB_ARMATURE", idx))
    _ELF_ENUM_ITEMS_CACHE = items
    return _ELF_ENUM_ITEMS_CACHE


def get_animation_enum_items(self, context):
    global _ANIM_ENUM_ITEMS_CACHE
    items = []
    idx = 0
    for act in sorted(bpy.data.actions, key=lambda a: a.name):
        if act.name.startswith("PathAnim_") or act.name.startswith("AF_PoseOffset_"):
            continue
        if act.name.startswith("AF_") or act.get("af_category"):
            cat = act.get("af_category", "CUSTOM")
            fr = int(round(act.frame_range[1] - act.frame_range[0]))
            spd = act.get("af_speed_mps", 0.0)
            spd_str = f" | {spd:.2f}m/s" if spd and spd > 0.1 else ""
            label = f"{act.name.replace('AF_', '')} [{cat} | {fr}f{spd_str}]"
            icon_id = get_anim_thumb_icon_id(act.name)
            if icon_id > 0:
                items.append((act.name, label, f"Apply {act.name} ({cat}, {fr} frames)", icon_id, idx))
            else:
                items.append((act.name, label, f"Apply {act.name} ({cat}, {fr} frames)", "ACTION", idx))
            idx += 1
    if not items:
        items.append(("NONE", "No Animations Loaded (Click Integrate Library)", "", "INFO", 0))
    _ANIM_ENUM_ITEMS_CACHE = items
    return _ANIM_ENUM_ITEMS_CACHE


# ============================================================================
# 3. BLENDER OPERATORS
# ============================================================================

class AFDIR_OT_IntegrateLibrary(bpy.types.Operator):
    bl_idname = "af_director.integrate_library"
    bl_label = "Učitaj Bazu Vilenjaka (Integrate Library)"
    bl_description = "One-click load of all 7 rigged Elves and 24+ animations from database/elf_assets_library.blend into this scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        res = ensure_library_loaded(load_templates=True, load_actions=True)
        dropins = scan_dropin_animations(save_to_db=False)
        self.report(
            {"INFO"},
            f"Baza učitana: {res['total_templates']} vilenjaka i {res['total_actions']} animacija spremno ({len(dropins)} drop-in).",
        )
        return {"FINISHED"}


class AFDIR_OT_SelectCharacterFromList(bpy.types.Operator):
    bl_idname = "af_director.select_char"
    bl_label = "Select Character Gizmo"
    bl_description = "Select this character's Master Gizmo Controller in the 3D Viewport"
    bl_options = {"REGISTER", "UNDO"}

    ctrl_name: StringProperty()

    def execute(self, context):
        ctrl = bpy.data.objects.get(self.ctrl_name)
        if not ctrl:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        ctrl.select_set(True)
        context.view_layer.objects.active = ctrl
        enable_viewport_transform_gizmos()
        sync_ui_properties_from_controller(ctrl)
        return {"FINISHED"}


class AFDIR_OT_FocusSelectedCharacter(bpy.types.Operator):
    bl_idname = "af_director.focus_char"
    bl_label = "Focus Camera on Selected Elf"
    bl_description = "Frame the 3D Viewport camera on the currently selected character"
    bl_options = {"REGISTER"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        deps = context.evaluated_depsgraph_get()
        pos = ctrl.evaluated_get(deps).matrix_world.translation
        for win in context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D" and space.region_3d:
                            space.region_3d.view_location = Vector((pos.x, pos.y, pos.z + 1.0))
                            space.region_3d.view_distance = 3.8
        return {"FINISHED"}


class AFDIR_OT_SpawnElf(bpy.types.Operator):
    bl_idname = "af_director.spawn_elf"
    bl_label = "+ Novi Vilenjak na 3D Kursoru"
    bl_description = "Spawn a new rigged Elf with its own Master Floor Gizmo at the 3D Cursor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ensure_library_loaded(load_templates=True, load_actions=True)
        elf_id = getattr(context.scene, "af_director_elf_enum", "ELF10")
        anim_name = getattr(context.scene, "af_director_anim_enum", DEFAULT_WALK_ACTION)
        if anim_name == "NONE":
            anim_name = DEFAULT_WALK_ACTION
        ctrl = spawn_elf_actor(
            context,
            elf_id=elf_id,
            initial_action_name=anim_name,
            sync_ui_callback=sync_ui_properties_from_controller,
        )
        if not ctrl:
            self.report({"ERROR"}, "Nije moguće učitati predložak vilenjaka iz baze.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Postavljen '{ctrl.name}' ({elf_id}) s animacijom '{ctrl.get('af_anim_name')}'.")
        return {"FINISHED"}


class AFDIR_OT_DuplicateSelectedElf(bpy.types.Operator):
    bl_idname = "af_director.duplicate_elf"
    bl_label = "Dupliciraj Odabranog (+Offset)"
    bl_description = "Spawn a copy of the selected Elf 1.2m to the side with a randomized frame offset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return bpy.ops.af_director.spawn_elf()
        new_ctrl = duplicate_elf_actor(context, ctrl)
        if new_ctrl:
            sync_ui_properties_from_controller(new_ctrl)
            self.report({"INFO"}, f"Dupliciran '{new_ctrl.name}' (Offset: +{new_ctrl.get('af_frame_offset', 0)}f).")
        return {"FINISHED"}


class AFDIR_OT_DeleteSelectedElf(bpy.types.Operator):
    bl_idname = "af_director.delete_elf"
    bl_label = "Obriši Odabranog Vilenjaka"
    bl_description = "Remove the selected character and its meshes/rig from the scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        name = ctrl.name
        delete_elf_actor(context, ctrl)
        active_rem = get_active_character_controller(context)
        if active_rem:
            sync_ui_properties_from_controller(active_rem)
        self.report({"INFO"}, f"Obrisan '{name}'.")
        return {"FINISHED"}


class AFDIR_OT_RandomizeCrowdOffsets(bpy.types.Operator):
    bl_idname = "af_director.randomize_offsets"
    bl_label = "De-Sync Crowd (Randomize Frame Offsets)"
    bl_description = "Assign random start frame offsets to all characters in the scene so they don't move in robotic sync"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrls = get_all_scene_character_controllers()
        for i, c in enumerate(ctrls):
            c["af_frame_offset"] = (i * 11 + random.randint(0, 15)) % 60
            apply_stored_settings_to_character(context, c)
        active_c = get_active_character_controller(context)
        if active_c:
            sync_ui_properties_from_controller(active_c)
        self.report({"INFO"}, f"Desinkronizirano {len(ctrls)} likova u sceni.")
        return {"FINISHED"}


class AFDIR_OT_LockConstantStrideSpeed(bpy.types.Operator):
    bl_idname = "af_director.lock_stride_speed"
    bl_label = "Reset to Exact Anti-Slide Stride Speed"
    bl_description = "Lock the curve speed to the exact biomechanical foot stride velocity of the active animation so feet never slide"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        anim_name = ctrl.get("af_anim_name", DEFAULT_WALK_ACTION)
        act = bpy.data.actions.get(anim_name)
        exact_spd = get_character_exact_stride_speed(ctrl, act)
        ctrl["af_walk_speed"] = round(exact_spd, 4)
        apply_stored_settings_to_character(context, ctrl)
        sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, f"Brzina zaključana na točnih {exact_spd:.2f} m/s (0% klizanja stopala).")
        return {"FINISHED"}


class AFDIR_OT_ToggleTemplateLineup(bpy.types.Operator):
    bl_idname = "af_director.toggle_templates"
    bl_label = "Show / Hide Master 7-Elf Lineup"
    bl_description = "Show or hide the background lineup of all 7 rigged Elf templates"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        col = bpy.data.collections.get(TEMPLATE_COLLECTION_NAME)
        if not col:
            ensure_library_loaded(load_templates=True, load_actions=False)
            col = bpy.data.collections.get(TEMPLATE_COLLECTION_NAME)
        if not col:
            return {"CANCELLED"}
        col.hide_viewport = not col.hide_viewport
        return {"FINISHED"}


class AFDIR_OT_AppendAnimationNLA(bpy.types.Operator):
    bl_idname = "af_director.append_nla"
    bl_label = "+ Spoji u NLA Sekvencu"
    bl_description = "Append the selected animation after the current animations on this Elf with smooth crossfade blending"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            self.report({"WARNING"}, "Prvo odaberi vilenjaka u sceni.")
            return {"CANCELLED"}
        anim_name = context.scene.af_director_anim_enum
        blend_frames = max(0, int(context.scene.af_director_blend_frames))
        ok, msg = append_animation_to_nla(
            ctrl,
            action_name=anim_name,
            blend_frames=blend_frames,
            repeat=1.0,
            speed_mult=float(ctrl.get("af_anim_speed", 1.0)),
        )
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_RemoveNLAClip(bpy.types.Operator):
    bl_idname = "af_director.remove_nla_clip"
    bl_label = "Remove NLA Clip"
    bl_description = "Remove this animation clip from the NLA sequence and rebuild transitions"
    bl_options = {"REGISTER", "UNDO"}

    clip_index: IntProperty(default=0)

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        ok, msg = remove_nla_clip_at_index(ctrl, self.clip_index)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_MoveNLAClip(bpy.types.Operator):
    bl_idname = "af_director.move_nla_clip"
    bl_label = "Move NLA Clip Up/Down"
    bl_description = "Reorder this clip inside the character's NLA sequence"
    bl_options = {"REGISTER", "UNDO"}

    clip_index: IntProperty(default=0)
    direction: StringProperty(default="UP")

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        ok, msg = move_nla_clip(ctrl, self.clip_index, direction=self.direction)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        sync_ui_properties_from_controller(ctrl, sync_anim_dropdown=False)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_ToggleNLAClipFillMode(bpy.types.Operator):
    bl_idname = "af_director.toggle_nla_fill"
    bl_label = "Prebaci Način Isječka (Fill / 1x)"
    bl_description = "Prebaci ovaj NLA isječak između 'Fill' (automatski ponavlja animaciju dok ne popuni preostali prostor na krivulji) i '1x' (fiksna pojedinačna radnja poput skoka)"
    bl_options = {"REGISTER", "UNDO"}

    clip_index: IntProperty(default=0)

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        ok, msg = toggle_nla_clip_fill_mode(ctrl, self.clip_index)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        sync_ui_properties_from_controller(ctrl, sync_anim_dropdown=False)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_AdjustNLAClipRepeat(bpy.types.Operator):
    bl_idname = "af_director.adjust_nla_repeat"
    bl_label = "Promijeni Broj Ponavljanja / Omjer Isječka"
    bl_description = "Smanji ili povećaj broj ponavljanja (za 1x isječke) ili omjer prostora na krivulji (za Fill isječke)"
    bl_options = {"REGISTER", "UNDO"}

    clip_index: IntProperty(default=0)
    delta: FloatProperty(default=1.0)

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        ok, msg = adjust_nla_clip_repeat(ctrl, self.clip_index, delta=self.delta)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        sync_ui_properties_from_controller(ctrl, sync_anim_dropdown=False)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_ClearNLA(bpy.types.Operator):
    bl_idname = "af_director.clear_nla"
    bl_label = "Očisti NLA Sekvencu"
    bl_description = "Remove NLA sequence strips and return the selected Elf to single-animation mode"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        clear_nla_sequence(ctrl)
        apply_stored_settings_to_character(context, ctrl)
        sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, f"Očišćena NLA sekvenca za '{ctrl.name}'.")
        return {"FINISHED"}


class AFDIR_OT_DrawLocomotionCurve(bpy.types.Operator):
    bl_idname = "af_director.draw_curve"
    bl_label = "1. Nova Putanja (3 Točke / Edit Mode)"
    bl_description = "Create a clean 3-point Bezier Curve and open it in Curve Edit Mode (no gizmos)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        enable_viewport_transform_gizmos()

        paths_col = ensure_collection(PATHS_COLLECTION_NAME)
        idx = sum(1 for o in paths_col.all_objects if o.type == "CURVE") + 1
        cname = f"Elf_Locomotion_Path_{idx:02d}"

        cdata = bpy.data.curves.new(name=cname, type="CURVE")
        cdata.dimensions = "3D"
        cdata.resolution_u = 64
        cdata.bevel_depth = 0.012

        if ctrl:
            base = ctrl.matrix_world.translation.copy()
        else:
            base = context.scene.cursor.location.copy()

        pts = [
            (base.x - 5.5, base.y - 2.5, base.z),
            (base.x, base.y + 3.5, base.z),
            (base.x + 5.5, base.y - 2.5, base.z),
        ]
        sp = cdata.splines.new(type="BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for i, co in enumerate(pts):
            bp = sp.bezier_points[i]
            bp.co = co
            bp.handle_left_type = "AUTO"
            bp.handle_right_type = "AUTO"
            bp.select_control_point = (i == 1)
            bp.select_left_handle = (i == 1)
            bp.select_right_handle = (i == 1)
        sp.resolution_u = 64

        cobj = bpy.data.objects.new(cname, cdata)
        cobj["af_uniform_resampled"] = True
        paths_col.objects.link(cobj)

        if ctrl:
            cobj["af_target_ctrl"] = ctrl.name
            ctrl["af_attached_curve"] = cobj.name

        bpy.ops.object.select_all(action="DESELECT")
        cobj.select_set(True)
        context.view_layer.objects.active = cobj
        bpy.ops.object.mode_set(mode="EDIT")

        for win in context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for region in area.regions:
                        if region.type == "WINDOW":
                            with context.temp_override(window=win, area=area, region=region):
                                try:
                                    bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
                                except Exception:
                                    pass

        self.report({"INFO"}, "Kreirana 3-točkovna krivulja u Edit Modu! Pomakni točke (G) pa klikni '2. Poveži Vilenjaka s Krivuljom'.")
        return {"FINISHED"}


class AFDIR_OT_FinishAndFollowCurve(bpy.types.Operator):
    bl_idname = "af_director.follow_curve"
    bl_label = "2. Poveži Vilenjaka s Krivuljom"
    bl_description = "Resample the drawn curve to constant speed and attach the selected Elf with zero foot sliding"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active_obj = context.active_object
        curve_obj = active_obj if (active_obj and active_obj.type == "CURVE") else None
        if active_obj and active_obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        ctrl = get_active_character_controller(context)
        if not curve_obj:
            for o in context.selected_objects:
                if o.type == "CURVE":
                    curve_obj = o
                    break
        if not ctrl and curve_obj and curve_obj.get("af_target_ctrl"):
            ctrl = bpy.data.objects.get(curve_obj["af_target_ctrl"])
        if not curve_obj and ctrl and ctrl.get("af_attached_curve"):
            curve_obj = bpy.data.objects.get(ctrl["af_attached_curve"])

        if not curve_obj:
            paths_col = bpy.data.collections.get(PATHS_COLLECTION_NAME)
            if paths_col:
                curves = [o for o in paths_col.all_objects if o.type == "CURVE"]
                if curves:
                    curve_obj = curves[-1]

        if not ctrl:
            ctrl = spawn_elf_actor(
                context,
                elf_id=context.scene.af_director_elf_enum,
                sync_ui_callback=sync_ui_properties_from_controller,
            )

        if not ctrl or not curve_obj:
            self.report({"WARNING"}, "Odaberi vilenjaka i nacrtanu krivulju.")
            return {"CANCELLED"}

        curve_obj["af_uniform_resampled"] = False

        if not get_nla_sequence_clips(ctrl):
            cur_anim_name = ctrl.get("af_anim_name", DEFAULT_WALK_ACTION)
            cur_act = bpy.data.actions.get(cur_anim_name)
            if not cur_act or not cur_act.get("af_is_locomotion", False):
                ctrl["af_anim_name"] = DEFAULT_WALK_ACTION
                cur_act = bpy.data.actions.get(DEFAULT_WALK_ACTION)

        apply_stored_settings_to_character(context, ctrl)

        ok, msg = attach_controller_to_locomotion_curve(
            context,
            ctrl_obj=ctrl,
            curve_obj=curve_obj,
            speed_mps=None,
            loop_path=bool(ctrl.get("af_loop_anim", True)),
            flip_forward=bool(ctrl.get("af_flip_curve_dir", False)),
            start_pct=float(ctrl.get("af_curve_start_pct", 0.0)),
        )
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}

        if ctrl.get("af_mc_attached") or curve_obj.get("af_mc_rails_enabled"):
            try:
                from .minecart_pusher import (
                    set_curve_3d_rails_enabled,
                    update_minecart_curve_steering_for_controller,
                )
                if bool(getattr(context.scene, "af_mc_rails_enabled", True)):
                    set_curve_3d_rails_enabled(curve_obj, enabled=True)
                update_minecart_curve_steering_for_controller(ctrl, scene=context.scene)
            except Exception:
                pass

        bpy.ops.object.select_all(action="DESELECT")
        ctrl.select_set(True)
        context.view_layer.objects.active = ctrl
        enable_viewport_transform_gizmos()
        sync_ui_properties_from_controller(ctrl)
        context.scene.frame_set(1)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_DetachFromCurve(bpy.types.Operator):
    bl_idname = "af_director.detach_curve"
    bl_label = "Odvoji s Krivulje"
    bl_description = "Remove Follow Path constraint from the selected Elf while keeping its current world position"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        detach_controller_from_curve(context, ctrl)
        sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, f"'{ctrl.name}' odvojen od krivulje.")
        return {"FINISHED"}


class AFDIR_OT_SnapToGround(bpy.types.Operator):
    bl_idname = "af_director.snap_to_ground"
    bl_label = "Spusti na Pod (Snap to Ground)"
    bl_description = "Raycast downward and snap the selected Elf onto the floor mesh beneath it"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            self.report({"WARNING"}, "Prvo odaberi vilenjaka.")
            return {"CANCELLED"}
        ok, msg = snap_controller_to_ground(context, ctrl)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_TurnTowards(bpy.types.Operator):
    bl_idname = "af_director.turn_towards"
    bl_label = "Okreni Vilenjaka Prema..."
    bl_description = "Rotate the selected Elf around Z to face the active Camera or 3D Cursor"
    bl_options = {"REGISTER", "UNDO"}

    target_mode: StringProperty(default="CAMERA")

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            self.report({"WARNING"}, "Prvo odaberi vilenjaka.")
            return {"CANCELLED"}
        ok, msg = turn_controller_towards(context, ctrl, target_mode=self.target_mode)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_ResetPoseOffset(bpy.types.Operator):
    bl_idname = "af_director.reset_pose_offset"
    bl_label = "Resetiraj Pozu (0°)"
    bl_description = "Clear all additive head, torso, and arm pose offsets on the selected Elf"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        clear_additive_pose_offset(ctrl)
        sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, f"Aditivni pomaci poze resetirani za '{ctrl.name}'.")
        return {"FINISHED"}


class AFDIR_OT_SyncActionForgeFolder(bpy.types.Operator):
    bl_idname = "af_director.sync_actionforge"
    bl_label = "Skeniraj Drop-In Animacije"
    bl_description = "Scan database/animations_dropin/ for new .glb / .fbx animations and bake them onto the Elf rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ensure_library_loaded(load_templates=True, load_actions=True)
        imported = scan_dropin_animations(save_to_db=False)
        self.report({"INFO"}, f"Skeniranje završeno! Uvezeno {len(imported)} novih drop-in animacija.")
        return {"FINISHED"}


class AFDIR_OT_ImportAnimationFile(bpy.types.Operator, ImportHelper):
    bl_idname = "af_director.import_anim_file"
    bl_label = "Uvezi .GLB / .FBX Animaciju..."
    bl_description = "Choose any exported ActionForge or Mixamo .glb / .fbx animation file and bake it for all Elves"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".glb"
    filter_glob: StringProperty(default="*.glb;*.gltf;*.fbx", options={"HIDDEN"})

    def execute(self, context):
        ensure_library_loaded(load_templates=True, load_actions=True)
        act = import_and_bake_animation_file(
            self.filepath,
            in_place=context.scene.af_director_import_inplace,
            speed_mps=context.scene.af_director_walk_speed,
        )
        if not act:
            self.report({"ERROR"}, f"Neuspješan uvoz animacije iz '{os.path.basename(self.filepath)}'.")
            return {"CANCELLED"}

        ctrl = get_active_character_controller(context)
        if ctrl:
            ctrl["af_anim_name"] = act.name
            apply_stored_settings_to_character(context, ctrl)
            sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, f"Uvezena i prilagođena animacija '{act.name}'!")
        return {"FINISHED"}


class AFDIR_OT_RemoveAnimationFromLib(bpy.types.Operator):
    bl_idname = "af_director.remove_anim_from_lib"
    bl_label = "Obriši Odabranu Animaciju"
    bl_description = "Remove the currently selected animation from the scene library (protects AF_06_Idle_Breathing)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        anim_name = getattr(context.scene, "af_director_anim_enum", "")
        ok, msg = remove_animation_from_library(anim_name, save_to_db=False)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        ctrl = get_active_character_controller(context)
        if ctrl:
            sync_ui_properties_from_controller(ctrl)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_SaveDatabase(bpy.types.Operator):
    bl_idname = "af_director.save_database"
    bl_label = "Spremi Bazu na Disk (Save DB)"
    bl_description = "Persist all 7 Elf templates and all AF_* animations to database/elf_assets_library.blend and registry.json"
    bl_options = {"REGISTER"}

    def execute(self, context):
        ok, msg = save_database_to_disk()
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_StepAnimation(bpy.types.Operator):
    bl_idname = "af_director.step_animation"
    bl_label = "Prethodna / Sljedeća Animacija"
    bl_description = "Prebaci na prethodnu ili sljedeću animaciju iz kataloga (24 animacije) i odmah je prikaži na odabranom vilenjaku"
    bl_options = {"REGISTER", "UNDO"}

    delta: IntProperty(default=1)

    def execute(self, context):
        items = get_animation_enum_items(context.scene, context)
        valid_ids = [it[0] for it in items if it[0] != "NONE"]
        if not valid_ids:
            return {"CANCELLED"}
        cur = getattr(context.scene, "af_director_anim_enum", valid_ids[0])
        try:
            idx = valid_ids.index(cur)
        except ValueError:
            idx = 0
        next_id = valid_ids[(idx + int(self.delta)) % len(valid_ids)]
        context.scene.af_director_anim_enum = next_id
        return {"FINISHED"}


class AFDIR_OT_StepLoopPreviewFrame(bpy.types.Operator):
    bl_idname = "af_director.step_loop_frame"
    bl_label = "Korak Loop Sličice"
    bl_description = "Ručno pomakni 8-FPS preview sličicu u N-panelu za 1 korak naprijed ili natrag"
    bl_options = {"REGISTER"}

    delta: IntProperty(default=1)

    def execute(self, context):
        step_loop_frame(self.delta)
        return {"FINISHED"}


class AFDIR_OT_OpenPreviewCatalog(bpy.types.Operator):
    bl_idname = "af_director.open_preview_catalog"
    bl_label = "Otvori Video Katalog (24 Loop MP4)"
    bl_description = "Otvori kompresirani 8-FPS MP4 video aktivne animacije ili HTML5 katalog svih 24 animacija"
    bl_options = {"REGISTER"}

    mode: StringProperty(default="CATALOG")  # "CATALOG" or "ACTIVE_MP4"

    def execute(self, context):
        import subprocess
        import webbrowser

        if self.mode == "ACTIVE_MP4":
            act_name = getattr(context.scene, "af_director_anim_enum", "")
            mp4_p = get_anim_video_path(act_name)
            if os.path.isfile(mp4_p):
                if sys.platform == "darwin":
                    subprocess.Popen(["open", mp4_p])
                else:
                    webbrowser.open(f"file://{mp4_p}")
                self.report({"INFO"}, f"Otvoren MP4 video: {os.path.basename(mp4_p)}")
                return {"FINISHED"}

        html_p = get_html_catalog_path()
        if os.path.isfile(html_p):
            if sys.platform == "darwin":
                subprocess.Popen(["open", html_p])
            else:
                webbrowser.open(f"file://{html_p}")
            self.report({"INFO"}, "Otvoren HTML5 katalog sa svih 24 loop videa.")
            return {"FINISHED"}

        self.report({"WARNING"}, "Preview datoteke nisu pronađene u database/previews/.")
        return {"CANCELLED"}


class AFDIR_OT_IsolateWorkbenchStation(bpy.types.Operator):
    bl_idname = "af_director.isolate_workbench_station"
    bl_label = "Izoliraj Radnu Stanicu Animacije"
    bl_description = "Izoliraj odabranu novu animaciju zajedno s njezinim propovima u 3D Viewportu ili prikaži svih 9 stanica"
    bl_options = {"REGISTER", "UNDO"}

    station_id: StringProperty(default="ALL")

    def execute(self, context):
        wb_col = bpy.data.collections.get("04_NEW_ANIMATIONS_WORKBENCH")
        if not wb_col:
            self.report({"WARNING"}, "Kolekcija '04_NEW_ANIMATIONS_WORKBENCH' nije pronađena u sceni.")
            return {"CANCELLED"}

        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        target_col = None
        for sub in wb_col.children:
            if self.station_id == "ALL":
                sub.hide_viewport = False
                sub.hide_render = False
            else:
                match = (sub.name == self.station_id or sub.name.startswith(self.station_id))
                sub.hide_viewport = not match
                sub.hide_render = False
                if match:
                    target_col = sub

        context.scene["_af_isolated_station"] = self.station_id

        # Select the station's Elf controller and frame the 3D Viewport
        bpy.ops.object.select_all(action="DESELECT")
        selected_ctrl = None
        if target_col:
            for o in target_col.all_objects:
                if o.get("af_is_char_controller"):
                    selected_ctrl = o
                    break
            if selected_ctrl:
                selected_ctrl.select_set(True)
                context.view_layer.objects.active = selected_ctrl
                sync_ui_properties_from_controller(selected_ctrl)
        else:
            all_ctrls = get_all_scene_character_controllers()
            if all_ctrls:
                selected_ctrl = all_ctrls[0]
                selected_ctrl.select_set(True)
                context.view_layer.objects.active = selected_ctrl
                sync_ui_properties_from_controller(selected_ctrl)

        # Frame selected or whole workbench in 3D Viewport
        try:
            for win in context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == "VIEW_3D":
                        region = next((r for r in area.regions if r.type == "WINDOW"), None)
                        if region:
                            with context.temp_override(window=win, area=area, region=region):
                                if target_col:
                                    for o in target_col.all_objects:
                                        if not o.hide_viewport:
                                            o.select_set(True)
                                    bpy.ops.view3d.view_selected()
                                    if selected_ctrl:
                                        bpy.ops.object.select_all(action="DESELECT")
                                        selected_ctrl.select_set(True)
                                        context.view_layer.objects.active = selected_ctrl
        except Exception:
            pass

        msg = "Prikazano svih 9 stanica." if self.station_id == "ALL" else f"Izolirana stanica: {self.station_id}"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class AFDIR_OT_SelectStationProp(bpy.types.Operator):
    bl_idname = "af_director.select_station_prop"
    bl_label = "Odaberi Rekvizit / Alat za Uređivanje (G/R/S)"
    bl_description = "Odaberi glavni rekvizit (stol, stolac, ljestve, stepenice) ili alat u ruci vilenjaka i uključi strelice za pomicanje/rotaciju (G/R/S)"
    bl_options = {"REGISTER", "UNDO"}

    prop_role: StringProperty(default="ENV_PROP")  # "ENV_PROP" or "HAND_TOOL"

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            self.report({"WARNING"}, "Prvo odaberi vilenjaka ili izoliraj stanicu.")
            return {"CANCELLED"}

        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        prop_name = ctrl.get("af_station_env_prop" if self.prop_role == "ENV_PROP" else "af_station_hand_tool", "")
        prop_obj = bpy.data.objects.get(prop_name) if prop_name else None

        if not prop_obj:
            # Fallback search in same station collection
            for col in ctrl.users_collection:
                if col.name.startswith("ST_"):
                    for o in col.all_objects:
                        if self.prop_role == "ENV_PROP" and o.name.startswith("PROP_ROOT_"):
                            prop_obj = o
                            break
                        elif self.prop_role == "HAND_TOOL" and "_Hand_" in o.name:
                            prop_obj = o
                            break

        if not prop_obj:
            self.report({"WARNING"}, "Ova stanica nema pridruženi rekvizit te vrste.")
            return {"CANCELLED"}

        STATE["selection_redirect_guard"] = True
        try:
            bpy.ops.object.select_all(action="DESELECT")
            prop_obj.hide_viewport = False
            prop_obj.hide_select = False
            prop_obj.select_set(True)
            context.view_layer.objects.active = prop_obj
            _set_viewport_prop_gizmos(True)
        finally:
            STATE["selection_redirect_guard"] = False

        self.report({"INFO"}, f"Odabran prop '{prop_obj.name}' — koristi G (pomak), R (rotacija), S (skala) ili strelice u Viewportu!")
        return {"FINISHED"}


class AFDIR_OT_TogglePoseTweakMode(bpy.types.Operator):
    bl_idname = "af_director.toggle_pose_tweak_mode"
    bl_label = "Uredi Kostur Ručno (Pose Mode On/Off)"
    bl_description = "Prikaži kosti vilenjaka i uđi u Pose Mode za ručno namještanje ruku/tijela, ili se vrati u Object Mode"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active_obj = context.active_object
        if active_obj and active_obj.type == "ARMATURE" and active_obj.mode == "POSE":
            bpy.ops.object.mode_set(mode="OBJECT")
            active_obj.show_in_front = False
            for b in active_obj.data.bones:
                b.hide = True
            ctrl = find_character_controller(active_obj)
            if ctrl:
                bpy.ops.object.select_all(action="DESELECT")
                ctrl.select_set(True)
                context.view_layer.objects.active = ctrl
            self.report({"INFO"}, "Izlaz iz Pose Modea (kosti skrivene).")
            return {"FINISHED"}

        ctrl = get_active_character_controller(context)
        if not ctrl:
            self.report({"WARNING"}, "Prvo odaberi vilenjaka.")
            return {"CANCELLED"}
        arm_obj = get_character_armature_from_ctrl(ctrl)
        if not arm_obj:
            return {"CANCELLED"}

        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        STATE["selection_redirect_guard"] = True
        try:
            bpy.ops.object.select_all(action="DESELECT")
            arm_obj.hide_viewport = False
            arm_obj.hide_select = False
            arm_obj.show_in_front = True
            arm_obj.data.display_type = "OCTAHEDRAL"
            for b in arm_obj.data.bones:
                b.hide = False
            if arm_obj.pose:
                for pb in arm_obj.pose.bones:
                    pb.hide = False
            arm_obj.select_set(True)
            context.view_layer.objects.active = arm_obj
            bpy.ops.object.mode_set(mode="POSE")
        finally:
            STATE["selection_redirect_guard"] = False

        self.report({"INFO"}, f"Pose Mode aktivan na '{arm_obj.name}' — odaberi kost (npr. upperarm_r / lowerarm_r) i rotiraj (R)!")
        return {"FINISHED"}


# ============================================================================
# 4. N-PANEL UI (`Elf Director` v3.0)
# ============================================================================

class VIEW3D_PT_ActionForgeElfDirector(bpy.types.Panel):
    bl_label = "ActionForge Elf Director v3.0"
    bl_idname = "VIEW3D_PT_af_elf_director"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Elf Director"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        ctrl = get_active_character_controller(context)
        all_ctrls = get_all_scene_character_controllers()

        # Check if templates are already in bpy.data
        templates_ready = all(bpy.data.objects.get(e["arm_name"]) is not None for e in RIGGED_ELF_ROSTER)
        if not templates_ready:
            box_init = layout.box()
            row_init = box_init.row(align=True)
            row_init.scale_y = 1.4
            row_init.operator("af_director.integrate_library", icon="IMPORT")

        # 0. NEW ANIMATIONS WORKBENCH (`04_NEW_ANIMATIONS_WORKBENCH` — 1-Click Isolation & Prop Tools)
        wb_col = bpy.data.collections.get("04_NEW_ANIMATIONS_WORKBENCH")
        if wb_col:
            box_wb = layout.box()
            cur_iso = scn.get("_af_isolated_station", "ALL")
            box_wb.label(text="0. Radionica Novih Animacija (9 Stanica):", icon="TOOL_SETTINGS")

            row_all = box_wb.row(align=True)
            row_all.scale_y = 1.25
            op_all = row_all.operator(
                "af_director.isolate_workbench_station",
                text="Prikaži Sve Stanice (9 Zgrupiranih)",
                depress=(cur_iso == "ALL"),
                icon="HIDE_OFF",
            )
            op_all.station_id = "ALL"

            stations_ui = [
                ("ST_25_Climb_Ladder", "25 Ljestve"),
                ("ST_26_Seated_Stamp_Mail", "26 Pečat"),
                ("ST_27_Mine_Pickaxe", "27 Kramp"),
                ("ST_28_Wave_Hello", "28 Pozdrav"),
                ("ST_29_Thank_You_Bow", "29 Hvala"),
                ("ST_30_Shovel_Pitchfork", "30 Vile"),
                ("ST_31_Sweep_Broom", "31 Metla"),
                ("ST_32_Seated_Write_Desk", "32 Pisanje"),
                ("ST_33_Climb_Stairs", "33 Stepenice"),
            ]
            col_st = box_wb.column(align=True)
            for r_i in range(0, len(stations_ui), 3):
                row_s = col_st.row(align=True)
                row_s.scale_y = 1.15
                for st_id, st_lbl in stations_ui[r_i:r_i + 3]:
                    op_s = row_s.operator(
                        "af_director.isolate_workbench_station",
                        text=st_lbl,
                        depress=(cur_iso == st_id),
                    )
                    op_s.station_id = st_id

            row_prp = box_wb.row(align=True)
            row_prp.scale_y = 1.2
            op_ep = row_prp.operator("af_director.select_station_prop", text="Uredi Stol/Ljestve (G/R/S)", icon="OBJECT_DATAMODE")
            op_ep.prop_role = "ENV_PROP"
            op_ht = row_prp.operator("af_director.select_station_prop", text="Uredi Alat u Ruci (G/R/S)", icon="TOOL_SETTINGS")
            op_ht.prop_role = "HAND_TOOL"

            row_pose_btn = box_wb.row(align=True)
            row_pose_btn.scale_y = 1.15
            is_pose = (context.active_object and context.active_object.mode == "POSE")
            row_pose_btn.operator(
                "af_director.toggle_pose_tweak_mode",
                text="Izađi iz Pose Modea (Spremi)" if is_pose else "Uredi Kostur Ručno (Pose Mode On)",
                depress=is_pose,
                icon="POSE_HLT",
            )

        # 1. SCENE CROWD MANAGER (All Characters in Scene)
        box_crowd = layout.box()
        row_hdr = box_crowd.row(align=True)
        row_hdr.label(text=f"1. Likovi u Sceni ({len(all_ctrls)})", icon="OUTLINER_OB_ARMATURE")
        row_hdr.operator("af_director.randomize_offsets", text="De-Sync", icon="TIME")
        row_hdr.operator("af_director.toggle_templates", text="", icon="HIDE_OFF")

        is_proxy = bool(scn.get("af_viewport_proxy_active", False))
        row_prx = box_crowd.row(align=True)
        row_prx.scale_y = 1.2
        row_prx.operator(
            "af_director.toggle_viewport_proxy",
            text="Viewport Proxy ON (~25k/Elf, Render 100%)" if is_proxy else "Uključi Viewport Proxy (~25k/Elf, Brzi FPS)",
            depress=is_proxy,
            icon="MOD_DECIM",
        )

        col_list = box_crowd.column(align=True)
        for c in all_ctrls:
            is_sel = (c == ctrl)
            row = col_list.row(align=True)
            elf_id = c.get("af_elf_id", "ELF")
            anim_short = c.get("af_anim_name", "None").replace("AF_", "")
            crv_name = c.get("af_attached_curve", "")
            crv_badge = f" -> {crv_name}" if crv_name else ""
            op = row.operator(
                "af_director.select_char",
                text=f"{c.name} [{elf_id}] : {anim_short}{crv_badge}",
                depress=is_sel,
                icon="RADIOBUT_ON" if is_sel else "RADIOBUT_OFF",
            )
            op.ctrl_name = c.name
            row.prop(c, "hide_viewport", text="", emboss=False)

        row_spawn = box_crowd.row(align=True)
        row_spawn.scale_y = 1.3
        row_spawn.operator("af_director.spawn_elf", text="+ Novi Vilenjak", icon="ADD")
        row_spawn.operator("af_director.duplicate_elf", text="Dupliciraj", icon="DUPLICATE")
        row_spawn.operator("af_director.focus_char", text="", icon="VIEWZOOM")
        row_spawn.operator("af_director.delete_elf", text="", icon="TRASH")

        if not ctrl:
            layout.label(text="Klikni '+ Novi Vilenjak' za početak.", icon="INFO")
            return

        # 2. SELECTED CHARACTER ANIMATION & NLA SEQUENCER
        box_sel = layout.box()
        row_sel_hdr = box_sel.row(align=True)
        row_sel_hdr.label(text=f"2. Animacija i NLA: {ctrl.name}", icon="GIZMO")
        row_sel_hdr.prop(
            scn,
            "af_director_show_visual_previews",
            text="Sličice + Loop",
            toggle=True,
            icon="IMAGE_DATA",
        )

        box_sel.prop(scn, "af_director_elf_enum", text="Model")

        # Visual Thumbnail Gallery + Live 8-FPS Loop Preview Player
        active_anim = getattr(scn, "af_director_anim_enum", DEFAULT_WALK_ACTION)
        if getattr(scn, "af_director_show_visual_previews", True) and active_anim and active_anim != "NONE":
            box_prev = box_sel.box()
            row_prev_lbl = box_prev.row(align=True)
            row_prev_lbl.label(text="Klikni Sličicu (24 Galerija):", icon="ASSET_MANAGER")
            f_idx = get_current_loop_frame_index() + 1
            row_prev_lbl.label(text=f"8-FPS Loop ({f_idx}/8):", icon="RENDER_ANIMATION")

            split_prev = box_prev.split(factor=0.50, align=True)
            col_left = split_prev.column(align=True)
            col_left.template_icon_view(
                scn,
                "af_director_anim_enum",
                show_labels=True,
                scale=5.2,
                scale_popup=4.6,
            )

            col_right = split_prev.column(align=True)
            loop_icon_id = get_anim_loop_icon_id(active_anim)
            if loop_icon_id > 0:
                col_right.template_icon(icon_value=loop_icon_id, scale=5.2)
            else:
                col_right.label(text="Nema preview sličice", icon="INFO")

            row_pctrl = box_prev.row(align=True)
            row_pctrl.prop(
                scn,
                "af_director_live_loop_preview",
                text="Loop 8 FPS",
                toggle=True,
                icon="PAUSE" if getattr(scn, "af_director_live_loop_preview", True) else "PLAY",
            )
            op_f_prev = row_pctrl.operator("af_director.step_loop_frame", text="", icon="TRIA_LEFT")
            op_f_prev.delta = -1
            op_f_next = row_pctrl.operator("af_director.step_loop_frame", text="", icon="TRIA_RIGHT")
            op_f_next.delta = 1
            op_mp4 = row_pctrl.operator("af_director.open_preview_catalog", text="MP4", icon="FILE_MOVIE")
            op_mp4.mode = "ACTIVE_MP4"
            op_cat = row_pctrl.operator("af_director.open_preview_catalog", text="Katalog 24", icon="URL")
            op_cat.mode = "CATALOG"

        row_anim_dd = box_sel.row(align=True)
        op_a_prev = row_anim_dd.operator("af_director.step_animation", text="", icon="TRIA_LEFT")
        op_a_prev.delta = -1
        row_anim_dd.prop(scn, "af_director_anim_enum", text="Animacija")
        op_a_next = row_anim_dd.operator("af_director.step_animation", text="", icon="TRIA_RIGHT")
        op_a_next.delta = 1

        col_pb = box_sel.column(align=True)
        col_pb.prop(scn, "af_director_anim_speed", text="Brzina Animacije (x)")
        col_pb.prop(scn, "af_director_frame_offset", text="Pomak Faze (Frame Offset)")
        col_pb.prop(scn, "af_director_loop_anim", text="Loop Animacija")

        row_nla = box_sel.row(align=True)
        row_nla.operator("af_director.append_nla", text="+ Spoji u NLA Sekvencu", icon="NLA")
        row_nla.operator("af_director.clear_nla", text="", icon="X")
        box_sel.prop(scn, "af_director_blend_frames", text="NLA Crossfade (Frames)")

        nla_clips = get_nla_sequence_clips(ctrl)
        if nla_clips:
            box_clips = box_sel.box()
            col_clips = box_clips.column(align=True)
            crv_active_name = ctrl.get("af_attached_curve", "")
            col_clips.label(
                text=f"Aktivni NLA Isječci ({len(nla_clips)}):",
                icon="SEQ_STRIP_DUPLICATE",
            )
            for idx, clip in enumerate(nla_clips):
                if idx > 0:
                    col_clips.separator(factor=0.6)
                c_col = col_clips.column(align=True)
                short_act = clip["action_name"].replace("AF_", "")
                spd_val = float(clip.get("speed_mps", 0.0))
                u_s = float(clip.get("u_start_pct", 0.0))
                u_e = float(clip.get("u_end_pct", 100.0))
                u_m = float(clip.get("u_mid_pct", 50.0))
                eff_rep = float(clip.get("effective_repeat", clip.get("repeat", 1.0)))
                is_fill = bool(clip.get("is_fill", False))

                r_top = c_col.row(align=True)
                if crv_active_name:
                    lbl_txt = f"{idx + 1}. {short_act}  [{u_s:.0f}->{u_e:.0f}% | sr.{u_m:.0f}% | {spd_val:.2f}m/s]"
                else:
                    lbl_txt = f"{idx + 1}. {short_act}  ({clip['frame_start']}..{clip['frame_end']}f | {spd_val:.2f}m/s)"
                r_top.label(text=lbl_txt)

                r_bot = c_col.row(align=True)
                op_mode = r_bot.operator(
                    "af_director.toggle_nla_fill",
                    text=f"Fill x{eff_rep:.1f} (Popuni)" if is_fill else f"Fiksno ({eff_rep:g}x)",
                    depress=is_fill,
                    icon="FULLSCREEN_ENTER" if is_fill else "PINNED",
                )
                op_mode.clip_index = idx

                op_rep_m = r_bot.operator("af_director.adjust_nla_repeat", text="", icon="REMOVE")
                op_rep_m.clip_index = idx
                op_rep_m.delta = -0.5

                op_rep_p = r_bot.operator("af_director.adjust_nla_repeat", text="", icon="ADD")
                op_rep_p.clip_index = idx
                op_rep_p.delta = 0.5

                op_up = r_bot.operator("af_director.move_nla_clip", text="", icon="TRIA_UP")
                op_up.clip_index = idx
                op_up.direction = "UP"

                op_dn = r_bot.operator("af_director.move_nla_clip", text="", icon="TRIA_DOWN")
                op_dn.clip_index = idx
                op_dn.direction = "DOWN"

                op_rm = r_bot.operator("af_director.remove_nla_clip", text="", icon="X")
                op_rm.clip_index = idx

        # 3. ZERO-SLIP CURVE LOCOMOTION
        box_crv = layout.box()
        crv_name = ctrl.get("af_attached_curve", "")
        box_crv.label(
            text=f"3. Putanja (Curve): {crv_name if crv_name else 'Slobodan u prostoru'}",
            icon="CURVE_PATH",
        )
        col_crv = box_crv.column(align=True)
        row_c1 = col_crv.row(align=True)
        row_c1.scale_y = 1.2
        row_c1.operator("af_director.draw_curve", icon="GREASEPENCIL")

        row_c2 = col_crv.row(align=True)
        row_c2.scale_y = 1.2
        row_c2.operator("af_director.follow_curve", icon="CON_FOLLOWPATH")

        col_crv.prop(scn, "af_director_curve_start_pct", text="Početak na Krivulji (Start %)", slider=True)

        row_spd = col_crv.row(align=True)
        row_spd.prop(scn, "af_director_walk_speed", text="Brzina (m/s)")
        row_spd.operator("af_director.lock_stride_speed", text="Auto-Lock", icon="LOCKED")

        row_c3 = col_crv.row(align=True)
        row_c3.prop(scn, "af_director_flip_curve_dir", text="Obrni Smjer")
        row_c3.operator("af_director.detach_curve", text="Odvoji s Krivulje", icon="X")

        # 4. HUMAN VIEWPORT TOOLS (Scale, Accessories, Snap, Look-At & Additive Pose Offset)
        box_hum = layout.box()
        box_hum.label(text="4. Oprema, Orijentacija i Poza", icon="ARMATURE_DATA")
        box_hum.prop(scn, "af_director_char_scale", text="Veličina Lika (Scale)", slider=True)

        row_acc = box_hum.row(align=True)
        row_acc.prop(scn, "af_director_show_hat", text="Kapa (Hat)", toggle=True, icon="MOD_CLOTH")
        row_acc.prop(scn, "af_director_show_glasses", text="Naočale (Glasses)", toggle=True, icon="VIEWZOOM")

        row_orient = box_hum.row(align=True)
        row_orient.operator("af_director.snap_to_ground", text="Na Pod (Z)", icon="IMPORT")
        op_cam = row_orient.operator("af_director.turn_towards", text="-> Kamera", icon="CAMERA_DATA")
        op_cam.target_mode = "CAMERA"
        op_cur = row_orient.operator("af_director.turn_towards", text="-> Kursor", icon="PIVOT_CURSOR")
        op_cur.target_mode = "CURSOR"

        col_pose = box_hum.column(align=True)
        row_ph = col_pose.row(align=True)
        row_ph.label(text="Aditivna Prilagodba Riga i Kratkih Ruku:")
        row_ph.operator("af_director.reset_pose_offset", text="Reset", icon="LOOP_BACK")
        col_pose.prop(scn, "af_director_pose_arms_forward", text="Doseg Ruku Naprijed (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_arms_inward", text="Skup / Širina Ruku (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_elbows_bend", text="Pregib Laktova (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_arms_raise", text="Visina / Podizanje Ruku (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_pelvis_z_cm", text="Visina Sjedenja / Zdjelice (cm)", slider=True)
        col_pose.prop(scn, "af_director_pose_torso_bend", text="Nagib Trupa (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_torso_twist", text="Zakret Trupa (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_head_yaw", text="Glava Lijevo/Desno (°)", slider=True)
        col_pose.prop(scn, "af_director_pose_head_pitch", text="Glava Gore/Dolje (°)", slider=True)

        # 5. DATABASE & IMPORT / EXPORT
        box_imp = layout.box()
        box_imp.label(text="5. Baza Animacija (.GLB / .FBX)", icon="FILE_BLEND")
        box_imp.prop(scn, "af_director_import_inplace", text="In-Place Lock za Krivulju")
        row_imp1 = box_imp.row(align=True)
        row_imp1.operator("af_director.import_anim_file", text="Uvezi .GLB/.FBX", icon="FILE_FOLDER")
        row_imp1.operator("af_director.sync_actionforge", text="Skeniraj Drop-In", icon="FILE_REFRESH")
        row_imp2 = box_imp.row(align=True)
        row_imp2.operator("af_director.remove_anim_from_lib", text="Obriši Animaciju", icon="TRASH")
        row_imp2.operator("af_director.save_database", text="Spremi Bazu", icon="FILE_TICK")
        box_imp.prop(scn, "af_director_allow_subpart_select", text="Dopusti Direktno Biranje Meša/Kosti")


class AFDIR_OT_ToggleViewportProxyMode(bpy.types.Operator):
    bl_idname = "af_director.toggle_viewport_proxy"
    bl_label = "Toggle Viewport Low-Poly Proxy Mode (~25k Polys/Elf)"
    bl_description = (
        "Prebacuje sve vilenjake i teret rudarskih kolica u sceni na optimizirane Low-Poly meševe (~25k poligona po vilenjaku) "
        "za glatki 60 FPS rad u Viewportu, dok pri finalnom renderu automatski vraća pune 202k meševe"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        target = not bool(scn.get("af_viewport_proxy_active", False))
        res = set_scene_viewport_proxy_mode(enabled=target, context=context)
        mode_lbl = "ON (Low-Poly Viewport, High-Poly Render)" if target else "OFF (Full High-Poly u Viewportu)"
        self.report(
            {"INFO"},
            f"Viewport Proxy {mode_lbl}: {res['before_polys']:,} -> {res['after_polys']:,} poligona ({res['swapped']} meševa).",
        )
        return {"FINISHED"}


# ============================================================================
# 5. REGISTRATION
# ============================================================================

CLASSES = (
    AFDIR_OT_IntegrateLibrary,
    AFDIR_OT_SelectCharacterFromList,
    AFDIR_OT_FocusSelectedCharacter,
    AFDIR_OT_SpawnElf,
    AFDIR_OT_DuplicateSelectedElf,
    AFDIR_OT_DeleteSelectedElf,
    AFDIR_OT_RandomizeCrowdOffsets,
    AFDIR_OT_LockConstantStrideSpeed,
    AFDIR_OT_ToggleTemplateLineup,
    AFDIR_OT_ToggleViewportProxyMode,
    AFDIR_OT_AppendAnimationNLA,
    AFDIR_OT_RemoveNLAClip,
    AFDIR_OT_MoveNLAClip,
    AFDIR_OT_ToggleNLAClipFillMode,
    AFDIR_OT_AdjustNLAClipRepeat,
    AFDIR_OT_ClearNLA,
    AFDIR_OT_DrawLocomotionCurve,
    AFDIR_OT_FinishAndFollowCurve,
    AFDIR_OT_DetachFromCurve,
    AFDIR_OT_SnapToGround,
    AFDIR_OT_TurnTowards,
    AFDIR_OT_ResetPoseOffset,
    AFDIR_OT_SyncActionForgeFolder,
    AFDIR_OT_ImportAnimationFile,
    AFDIR_OT_RemoveAnimationFromLib,
    AFDIR_OT_SaveDatabase,
    AFDIR_OT_StepAnimation,
    AFDIR_OT_StepLoopPreviewFrame,
    AFDIR_OT_OpenPreviewCatalog,
    AFDIR_OT_IsolateWorkbenchStation,
    AFDIR_OT_SelectStationProp,
    AFDIR_OT_TogglePoseTweakMode,
    VIEW3D_PT_ActionForgeElfDirector,
)


def register():
    register_previews()
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

    bpy.types.Scene.af_director_show_visual_previews = BoolProperty(
        name="Show Visual Previews",
        description="Prikaži vizualnu galeriju (24 sličice) i 8-FPS animirani loop preview u N-panelu",
        default=True,
    )
    bpy.types.Scene.af_director_live_loop_preview = BoolProperty(
        name="Live 8-FPS Loop Preview",
        description="Automatski vrti 8-FPS loop sličice aktivne animacije u N-panelu",
        default=True,
    )

    bpy.types.Scene.af_director_active_char_index = IntProperty(
        name="Active Character Index",
        default=0,
        update=on_active_char_index_changed,
    )
    bpy.types.Scene.af_director_elf_enum = EnumProperty(
        name="Rigged Elf",
        items=get_elf_enum_items,
        update=on_ui_elf_type_changed,
    )
    bpy.types.Scene.af_director_anim_enum = EnumProperty(
        name="Animation",
        items=get_animation_enum_items,
        update=on_ui_anim_changed,
    )
    bpy.types.Scene.af_director_loop_anim = BoolProperty(
        name="Loop Animation",
        default=True,
        update=on_ui_playback_changed,
    )
    bpy.types.Scene.af_director_anim_speed = FloatProperty(
        name="Playback Speed",
        default=1.0,
        min=0.1,
        max=4.0,
        update=on_ui_playback_changed,
    )
    bpy.types.Scene.af_director_frame_offset = IntProperty(
        name="Frame Offset",
        default=0,
        min=0,
        max=240,
        update=on_ui_playback_changed,
    )
    bpy.types.Scene.af_director_blend_frames = IntProperty(
        name="NLA Crossfade Frames",
        default=12,
        min=0,
        max=60,
    )
    bpy.types.Scene.af_director_walk_speed = FloatProperty(
        name="Constant Walk Speed (m/s)",
        default=1.42,
        min=0.2,
        max=8.0,
        update=on_ui_walk_speed_changed,
    )
    bpy.types.Scene.af_director_flip_curve_dir = BoolProperty(
        name="Flip Forward Direction",
        default=False,
        update=on_ui_playback_changed,
    )
    bpy.types.Scene.af_director_curve_start_pct = FloatProperty(
        name="Curve Start %",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        update=on_ui_playback_changed,
    )
    bpy.types.Scene.af_director_char_scale = FloatProperty(
        name="Character Scale",
        default=1.0,
        min=0.2,
        max=5.0,
        update=on_ui_scale_changed,
    )
    bpy.types.Scene.af_director_show_hat = BoolProperty(
        name="Show Hat",
        default=True,
        update=on_ui_accessories_changed,
    )
    bpy.types.Scene.af_director_show_glasses = BoolProperty(
        name="Show Glasses",
        default=True,
        update=on_ui_accessories_changed,
    )
    bpy.types.Scene.af_director_pose_head_yaw = FloatProperty(
        name="Head Yaw (°)",
        default=0.0,
        min=-75.0,
        max=75.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_head_pitch = FloatProperty(
        name="Head Pitch (°)",
        default=0.0,
        min=-45.0,
        max=45.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_torso_bend = FloatProperty(
        name="Torso Bend (°)",
        default=0.0,
        min=-45.0,
        max=45.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_torso_twist = FloatProperty(
        name="Torso Twist (°)",
        default=0.0,
        min=-60.0,
        max=60.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_arms_raise = FloatProperty(
        name="Arms Raise (°)",
        default=0.0,
        min=-45.0,
        max=90.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_arms_forward = FloatProperty(
        name="Arms Forward Reach (°)",
        default=0.0,
        min=-45.0,
        max=60.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_arms_inward = FloatProperty(
        name="Arms Inward/Outward (°)",
        default=0.0,
        min=-45.0,
        max=45.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_elbows_bend = FloatProperty(
        name="Elbows Bend (°)",
        default=0.0,
        min=-60.0,
        max=60.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_pose_pelvis_z_cm = FloatProperty(
        name="Pelvis Z Offset (cm)",
        default=0.0,
        min=-35.0,
        max=35.0,
        update=on_ui_pose_offset_changed,
    )
    bpy.types.Scene.af_director_import_inplace = BoolProperty(
        name="Lock In-Place for Curve",
        default=True,
    )
    bpy.types.Scene.af_director_allow_subpart_select = BoolProperty(
        name="Allow Subpart Selection",
        default=False,
    )

    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "af_selection_redirect_handler":
            bpy.app.handlers.depsgraph_update_post.remove(h)
    bpy.app.handlers.depsgraph_update_post.append(af_selection_redirect_handler)

    for h in list(bpy.app.handlers.render_pre):
        if getattr(h, "__name__", "") == "af_proxy_render_pre_handler":
            bpy.app.handlers.render_pre.remove(h)
    bpy.app.handlers.render_pre.append(af_proxy_render_pre_handler)

    for h_list in (bpy.app.handlers.render_post, bpy.app.handlers.render_cancel):
        for h in list(h_list):
            if getattr(h, "__name__", "") == "af_proxy_render_post_handler":
                h_list.remove(h)
        h_list.append(af_proxy_render_post_handler)

    try:
        from .cliff_baskets_ui import register_cliff_baskets_ui
        register_cliff_baskets_ui()
    except Exception as exc:
        print(f"[ElfDirector] register_cliff_baskets_ui warning: {exc}")

    try:
        from .minecart_pusher_ui import register_minecart_pusher_ui
        register_minecart_pusher_ui()
    except Exception as exc:
        print(f"[ElfDirector] register_minecart_pusher_ui warning: {exc}")

    try:
        from .ropeway_gondolas_ui import register_ropeway_gondolas_ui
        register_ropeway_gondolas_ui()
    except Exception as exc:
        print(f"[ElfDirector] register_ropeway_gondolas_ui warning: {exc}")


def unregister():
    try:
        from .ropeway_gondolas_ui import unregister_ropeway_gondolas_ui
        unregister_ropeway_gondolas_ui()
    except Exception:
        pass
    try:
        from .minecart_pusher_ui import unregister_minecart_pusher_ui
        unregister_minecart_pusher_ui()
    except Exception:
        pass
    try:
        from .cliff_baskets_ui import unregister_cliff_baskets_ui
        unregister_cliff_baskets_ui()
    except Exception:
        pass
    unregister_previews()
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "af_selection_redirect_handler":
            bpy.app.handlers.depsgraph_update_post.remove(h)
    for h in list(bpy.app.handlers.render_pre):
        if getattr(h, "__name__", "") == "af_proxy_render_pre_handler":
            bpy.app.handlers.render_pre.remove(h)
    for h_list in (bpy.app.handlers.render_post, bpy.app.handlers.render_cancel):
        for h in list(h_list):
            if getattr(h, "__name__", "") == "af_proxy_render_post_handler":
                h_list.remove(h)
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
