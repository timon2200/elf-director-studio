# -*- coding: utf-8 -*-
"""
ActionForge Elf Director Studio v3.0 — Rig Actors, Master Gizmo & Accessories
=============================================================================
Spawns, swaps, duplicates, and deletes rigged Elf actors wrapped inside a Master
Floor Ring Gizmo (`CTRL_*`), manages modular 4-part meshes (`BODY`, `HEAD`, `HAT`,
`GLASSES`), and supports cross-character Hat/Glasses equipping from #10 Stari Urar.
"""

import math
import random
import bpy
from mathutils import Vector

from .constants import (
    ACTORS_COLLECTION_NAME,
    DEFAULT_WALK_ACTION,
    RIGGED_ELF_ROSTER,
    bind_action_slot,
    ensure_collection,
    get_elf_info,
)
from .database import ensure_library_loaded, set_action_cyclic_loop


# ============================================================================
# 1. OPTICAL GLASS, FLOOR GIZMO MATERIAL & 3D RING + ARROW MESH BUILDER
# ============================================================================

def ensure_optical_glass_material():
    """Creates or returns the shared transmissive optical glass material for Elf lenses."""
    mat_name = "Elf_Goggle_Lens_Glass_Mat"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    mat.use_backface_culling = False
    if mat.node_tree:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (0.78, 0.90, 0.98, 1.0)
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = 0.0
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.05
            if "IOR" in bsdf.inputs:
                bsdf.inputs["IOR"].default_value = 1.52
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = 0.92
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = 0.92
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = 0.24
    return mat


def ensure_gizmo_controller_material():
    """Creates or returns the glowing golden-amber material for Master Floor Gizmos (`CTRL_*`)."""
    mat_name = "AF_Gizmo_Controller_Mat"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    if mat.node_tree:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (1.0, 0.72, 0.08, 1.0)
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (1.0, 0.75, 0.12, 1.0)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = 1.8
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.2
    return mat


def build_character_gizmo_mesh_data():
    """
    Builds the shared 3D Floor Ring + Forward Arrow (-Y) mesh (`AF_Char_Gizmo_MeshData`)
    so every character has a crisp, clickable floor controller ring under their feet.
    """
    mesh_name = "AF_Char_Gizmo_MeshData"
    existing = bpy.data.meshes.get(mesh_name)
    if existing and len(existing.polygons) > 0:
        return existing
    if existing:
        bpy.data.meshes.remove(existing)

    import bmesh
    bm = bmesh.new()
    segments = 48
    r_inner = 0.42
    r_outer = 0.50
    z_off = 0.008

    inner_verts = []
    outer_verts = []
    for i in range(segments):
        ang = (2.0 * math.pi * i) / segments
        ca, sa = math.cos(ang), math.sin(ang)
        inner_verts.append(bm.verts.new((r_inner * ca, r_inner * sa, z_off)))
        outer_verts.append(bm.verts.new((r_outer * ca, r_outer * sa, z_off)))

    for i in range(segments):
        ni = (i + 1) % segments
        bm.faces.new((inner_verts[i], outer_verts[i], outer_verts[ni], inner_verts[ni]))

    # Forward pointer arrow along -Y (character facing direction)
    a_v1 = bm.verts.new((-0.14, -r_outer + 0.01, z_off))
    a_v2 = bm.verts.new((0.14, -r_outer + 0.01, z_off))
    a_tip = bm.verts.new((0.0, -r_outer - 0.24, z_off))
    bm.faces.new((a_v1, a_tip, a_v2))

    geom = bm.faces[:] + bm.edges[:] + bm.verts[:]
    ret = bmesh.ops.extrude_face_region(bm, geom=geom)
    extruded_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.010), verts=extruded_verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    mesh = bpy.data.meshes.new(mesh_name)
    bm.to_mesh(mesh)
    bm.free()

    mat = ensure_gizmo_controller_material()
    mesh.materials.append(mat)
    return mesh


def clean_actionforge_armature(arm_obj):
    """Removes glTF helper/IK socket cones and hides bone wireframe clutter in the viewport."""
    if not arm_obj or arm_obj.type != "ARMATURE":
        return
    prev_active = bpy.context.view_layer.objects.active
    if prev_active and prev_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    ebones = arm_obj.data.edit_bones
    junk_prefixes = ("ik_hand", "ik_foot", "socket_", "interaction", "center_of_mass")
    for eb in list(ebones):
        nl = eb.name.lower()
        if nl.startswith(junk_prefixes) or "_leaf_" in nl or nl.endswith("_leaf"):
            ebones.remove(eb)
        elif eb.name == "root":
            vec = eb.tail - eb.head
            if vec.length > 0.08:
                eb.tail = eb.head + vec.normalized() * 0.05
            eb.use_deform = False

    bpy.ops.object.mode_set(mode="OBJECT")
    arm_obj.show_in_front = False
    arm_obj.data.display_type = "WIRE"

    for b in arm_obj.data.bones:
        b.hide = True
    if arm_obj.pose:
        for pb in arm_obj.pose.bones:
            pb.hide = True


# ============================================================================
# 2. CONTROLLER LOOKUP & VIEWPORT GIZMO HELPERS
# ============================================================================

def find_character_controller(obj):
    """
    Given ANY object (mesh part like HEAD/BODY/HAT/GLASSES, Armature, prop, or `CTRL_*` gizmo),
    returns its Master Character Controller (`CTRL_*`).
    """
    if not obj:
        return None
    if obj.get("af_is_char_controller"):
        return obj
    st_ctrl_name = obj.get("af_station_ctrl")
    if st_ctrl_name:
        st_ctrl = bpy.data.objects.get(st_ctrl_name)
        if st_ctrl:
            return st_ctrl
    ctrl_name = obj.get("af_controller_name")
    if ctrl_name:
        ctrl = bpy.data.objects.get(ctrl_name)
        if ctrl:
            return ctrl
    curr = obj.parent
    while curr:
        if curr.get("af_is_char_controller"):
            return curr
        if curr.get("af_station_ctrl") and bpy.data.objects.get(curr.get("af_station_ctrl")):
            return bpy.data.objects.get(curr.get("af_station_ctrl"))
        curr = curr.parent
    for mod in getattr(obj, "modifiers", []):
        if mod.type == "ARMATURE" and mod.object:
            arm = mod.object
            if arm.parent and arm.parent.get("af_is_char_controller"):
                return arm.parent
    return None


def get_character_armature_from_ctrl(ctrl_obj):
    """Returns the child `Actor_*` armature belonging to `ctrl_obj`."""
    if not ctrl_obj:
        return None
    if ctrl_obj.type == "ARMATURE":
        return ctrl_obj
    arm_name = ctrl_obj.get("af_armature_name")
    if arm_name and bpy.data.objects.get(arm_name):
        return bpy.data.objects.get(arm_name)
    for ch in ctrl_obj.children:
        if ch.type == "ARMATURE":
            return ch
    return None


def get_all_scene_character_controllers() -> list:
    """Returns all `CTRL_*` character controllers in `01_SCENE_ELF_ACTORS` sorted by name."""
    actors_col = bpy.data.collections.get(ACTORS_COLLECTION_NAME)
    if not actors_col:
        return []
    return sorted(
        [o for o in actors_col.all_objects if o.get("af_is_char_controller")],
        key=lambda x: x.name,
    )


def get_active_character_controller(context=None):
    """Returns the currently selected/active `CTRL_*` controller, or the active list item."""
    if context is None:
        context = bpy.context
    active_obj = getattr(context, "active_object", None)
    ctrl = find_character_controller(active_obj)
    if ctrl:
        return ctrl
    for o in getattr(context, "selected_objects", []):
        ctrl = find_character_controller(o)
        if ctrl:
            return ctrl
    scn = getattr(context, "scene", None)
    all_ctrls = get_all_scene_character_controllers()
    if scn:
        idx = getattr(scn, "af_director_active_char_index", 0)
        if 0 <= idx < len(all_ctrls):
            return all_ctrls[idx]
    return all_ctrls[0] if all_ctrls else None


def enable_viewport_transform_gizmos():
    """Keeps 3D Viewport clean by disabling intrusive Object Translate/Rotate/Scale gizmo balls."""
    if bpy.app.background:
        return
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            space.show_gizmo_object_translate = False
                            space.show_gizmo_object_rotate = False
                            space.show_gizmo_object_scale = False
    except Exception:
        pass


# ============================================================================
# 3. MODULAR 4-PART MESH INSPECTION & HAT / GLASSES ACCESSORY TOGGLING
# ============================================================================

def _infer_mesh_part_type(mesh_obj) -> str:
    """Infers whether `mesh_obj` is `BODY`, `HEAD`, `HAT`, or `GLASSES`."""
    pt = str(mesh_obj.get("af_part_type", "")).upper()
    if pt in ("BODY", "HEAD", "HAT", "GLASSES"):
        return pt

    nu = mesh_obj.name.upper()
    for tag in ("GLASSES", "HAT", "HEAD", "BODY"):
        if nu.endswith(f"_{tag}") or f"_{tag}_" in nu:
            return tag

    if "GLASS" in nu or "GOGGLE" in nu or "LENS" in nu:
        return "GLASSES"
    if "HAT" in nu or "CAP" in nu or "HELMET" in nu:
        return "HAT"
    if "HEAD" in nu or "FACE" in nu or "BEARD" in nu:
        return "HEAD"

    for slot in getattr(mesh_obj, "material_slots", []):
        if slot.material:
            ml = slot.material.name.lower()
            if "glass" in ml or "goggle" in ml or "lens" in ml:
                return "GLASSES"
            if "hat" in ml or "cap" in ml:
                return "HAT"
            if "head" in ml or "face" in ml or "beard" in ml or "hair" in ml:
                return "HEAD"
    return "BODY"


def get_actor_part_meshes(ctrl_obj) -> dict:
    """
    Returns a dictionary mapping `"BODY"`, `"HEAD"`, `"HAT"`, `"GLASSES"` to the child
    mesh objects of `ctrl_obj`'s armature. Automatically tags legacy meshes with `af_part_type`.
    """
    arm_obj = get_character_armature_from_ctrl(ctrl_obj)
    if not arm_obj:
        return {}

    parts = {}
    meshes = [ch for ch in arm_obj.children if ch.type == "MESH"]
    for m in sorted(meshes, key=lambda x: x.name):
        pt = _infer_mesh_part_type(m)
        m["af_part_type"] = pt
        if pt not in parts:
            parts[pt] = m
    return parts


def _find_head_bone(arm_obj):
    if not arm_obj or not arm_obj.data:
        return None
    for cand in ("Head", "head"):
        if cand in arm_obj.data.bones:
            return arm_obj.data.bones[cand]
    for b in arm_obj.data.bones:
        if "head" in b.name.lower():
            return b
    return None


def _equip_accessory_from_template(ctrl_obj, arm_obj, part_type: str):
    """
    Copies `TPL_ARM_Elf10_Urar_HAT` or `TPL_ARM_Elf10_Urar_GLASSES` onto `arm_obj`
    and aligns its rest offset relative to the character's `Head` bone.
    """
    ensure_library_loaded(load_templates=True, load_actions=False)
    tpl_elf10 = bpy.data.objects.get("TPL_ARM_Elf10_Urar")
    if not tpl_elf10:
        return None

    tpl_mesh = bpy.data.objects.get(f"TPL_ARM_Elf10_Urar_{part_type}")
    if not tpl_mesh:
        for ch in tpl_elf10.children:
            if ch.type == "MESH" and _infer_mesh_part_type(ch) == part_type:
                tpl_mesh = ch
                break
    if not tpl_mesh:
        return None

    actors_col = ensure_collection(ACTORS_COLLECTION_NAME)
    new_mesh = tpl_mesh.copy()
    new_mesh.data = tpl_mesh.data.copy()
    new_mesh.name = f"{arm_obj.name}_{part_type}"
    new_mesh.parent = arm_obj
    new_mesh.matrix_parent_inverse = tpl_mesh.matrix_parent_inverse.copy()
    new_mesh.location = tpl_mesh.location.copy()
    new_mesh.rotation_euler = tpl_mesh.rotation_euler.copy()
    new_mesh.scale = tpl_mesh.scale.copy()

    dst_head = _find_head_bone(arm_obj)
    src_head = _find_head_bone(tpl_elf10)
    if dst_head and src_head:
        delta_head = dst_head.head_local - src_head.head_local
        new_mesh.location = tpl_mesh.location + Vector((delta_head.x, delta_head.y, delta_head.z))

    # Ensure vertex group matches the target armature's Head bone name
    if dst_head:
        for vg in new_mesh.vertex_groups:
            if vg.name.lower() == "head" and vg.name != dst_head.name:
                vg.name = dst_head.name

    has_arm_mod = False
    for mod in new_mesh.modifiers:
        if mod.type == "ARMATURE":
            mod.object = arm_obj
            has_arm_mod = True
    if not has_arm_mod:
        mod = new_mesh.modifiers.new(name="Armature", type="ARMATURE")
        mod.object = arm_obj

    if part_type == "GLASSES":
        glass_mat = ensure_optical_glass_material()
        for slot in new_mesh.material_slots:
            if slot.material and ("glass_mat" in slot.material.name.lower() or "lens" in slot.material.name.lower()):
                slot.material = glass_mat

    new_mesh["af_part_type"] = part_type
    new_mesh["af_controller_name"] = ctrl_obj.name
    actors_col.objects.link(new_mesh)
    return new_mesh


def set_actor_accessories(ctrl_obj, show_hat=None, show_glasses=None, equip_if_missing: bool = True) -> dict:
    """
    Shows or hides `HAT` and `GLASSES` on `ctrl_obj`. If `equip_if_missing=True` and the character
    does not natively have a Hat or Glasses mesh, automatically equips and aligns the modular
    Hat/Glasses from `TPL_ARM_Elf10_Urar`.
    """
    if not ctrl_obj:
        return {"has_hat": False, "has_glasses": False, "show_hat": False, "show_glasses": False}

    arm_obj = get_character_armature_from_ctrl(ctrl_obj)
    if not arm_obj:
        return {"has_hat": False, "has_glasses": False, "show_hat": False, "show_glasses": False}

    parts = get_actor_part_meshes(ctrl_obj)

    if show_hat is True and "HAT" not in parts and equip_if_missing:
        equipped_hat = _equip_accessory_from_template(ctrl_obj, arm_obj, "HAT")
        if equipped_hat:
            parts["HAT"] = equipped_hat

    if show_glasses is True and "GLASSES" not in parts and equip_if_missing:
        equipped_glasses = _equip_accessory_from_template(ctrl_obj, arm_obj, "GLASSES")
        if equipped_glasses:
            parts["GLASSES"] = equipped_glasses

    if show_hat is None:
        show_hat = bool(ctrl_obj.get("af_show_hat", "HAT" in parts and not parts["HAT"].hide_viewport))
    if show_glasses is None:
        show_glasses = bool(ctrl_obj.get("af_show_glasses", "GLASSES" in parts and not parts["GLASSES"].hide_viewport))

    if "HAT" in parts:
        parts["HAT"].hide_viewport = not bool(show_hat)
        parts["HAT"].hide_render = not bool(show_hat)
    if "GLASSES" in parts:
        parts["GLASSES"].hide_viewport = not bool(show_glasses)
        parts["GLASSES"].hide_render = not bool(show_glasses)

    ctrl_obj["af_show_hat"] = bool(show_hat and "HAT" in parts)
    ctrl_obj["af_show_glasses"] = bool(show_glasses and "GLASSES" in parts)

    return {
        "has_hat": "HAT" in parts,
        "has_glasses": "GLASSES" in parts,
        "show_hat": bool(ctrl_obj["af_show_hat"]),
        "show_glasses": bool(ctrl_obj["af_show_glasses"]),
    }


# ============================================================================
# 4. SPAWN, SWAP, DUPLICATE & DELETE ELF ACTORS
# ============================================================================

def _assign_initial_action_safe(arm_obj, action, speed_mult=1.0, frame_offset=0, loop_enabled=True):
    """Calls `nla_sequencer.assign_action_with_slot` lazily, with fallback if unavailable."""
    try:
        from .nla_sequencer import assign_action_with_slot
        assign_action_with_slot(
            arm_obj,
            action,
            speed_mult=speed_mult,
            frame_offset=frame_offset,
            loop_enabled=loop_enabled,
        )
        return
    except Exception:
        pass

    if not arm_obj or not action:
        return
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    adt = arm_obj.animation_data
    set_action_cyclic_loop(action, enabled=loop_enabled)
    adt.action = action
    bind_action_slot(adt, action)


def spawn_elf_actor(
    context,
    elf_id: str = "ELF10",
    location=None,
    initial_action_name: str = DEFAULT_WALK_ACTION,
    frame_offset: int = 0,
    sync_ui_callback=None,
):
    """
    Spawns a rigged Elf character from `00_RIGGED_ELF_TEMPLATES` wrapped inside a Master
    Floor Ring Gizmo Controller (`CTRL_<ELF>_<NN>`) in `01_SCENE_ELF_ACTORS`.
    """
    if context is None:
        context = bpy.context

    ensure_library_loaded(load_templates=True, load_actions=True)
    elf_info = get_elf_info(elf_id)
    tpl_arm = bpy.data.objects.get(elf_info["arm_name"])
    if not tpl_arm:
        return None

    actors_col = ensure_collection(ACTORS_COLLECTION_NAME)
    idx_num = 1
    while bpy.data.objects.get(f"CTRL_{elf_info['id']}_{idx_num:02d}") is not None:
        idx_num += 1

    ctrl_name = f"CTRL_{elf_info['id']}_{idx_num:02d}"
    actor_prefix = f"Actor_{elf_info['id']}_{idx_num:02d}"

    gizmo_mesh = build_character_gizmo_mesh_data()
    ctrl_obj = bpy.data.objects.new(ctrl_name, gizmo_mesh)
    ctrl_obj.hide_render = True
    ctrl_obj.show_name = True
    actors_col.objects.link(ctrl_obj)

    if location is None:
        location = context.scene.cursor.location.copy() if (context and context.scene) else Vector((0.0, 0.0, 0.0))
    ctrl_obj.location = Vector(location)
    ctrl_obj.rotation_mode = "XYZ"
    ctrl_obj.rotation_euler = (0.0, 0.0, 0.0)
    ctrl_obj.scale = (1.0, 1.0, 1.0)

    new_arm = tpl_arm.copy()
    new_arm.data = tpl_arm.data.copy()
    new_arm.name = actor_prefix
    new_arm.parent = ctrl_obj
    new_arm.location = (0.0, 0.0, 0.0)
    new_arm.rotation_mode = "XYZ"
    new_arm.rotation_euler = (0.0, 0.0, 0.0)
    new_arm.scale = (1.0, 1.0, 1.0)
    new_arm["af_elf_id"] = elf_info["id"]
    new_arm["af_is_template"] = False
    new_arm["af_controller_name"] = ctrl_obj.name
    new_arm.hide_viewport = False
    new_arm.show_in_front = False
    actors_col.objects.link(new_arm)

    glass_mat = ensure_optical_glass_material()
    tpl_meshes = sorted(
        [o for o in bpy.data.objects if o.parent == tpl_arm and o.type == "MESH"],
        key=lambda x: x.name,
    )
    parts_created = {}
    for idx, m in enumerate(tpl_meshes, start=1):
        pt = _infer_mesh_part_type(m)
        nm = m.copy()
        nm.data = m.data.copy()
        suffix = pt if pt not in parts_created else f"{pt}_{idx:02d}"
        nm.name = f"{new_arm.name}_{suffix}"
        nm.parent = new_arm
        nm.matrix_parent_inverse = m.matrix_parent_inverse.copy()
        nm.location = m.location.copy()
        nm.rotation_euler = m.rotation_euler.copy()
        nm.scale = m.scale.copy()
        nm.hide_viewport = False
        nm.hide_render = False
        nm["af_part_type"] = pt
        nm["af_controller_name"] = ctrl_obj.name
        for mod in nm.modifiers:
            if mod.type == "ARMATURE":
                mod.object = new_arm
        for slot in nm.material_slots:
            if slot.material and ("glass_mat" in slot.material.name.lower() or "lens" in slot.material.name.lower()):
                slot.material = glass_mat
        actors_col.objects.link(nm)
        parts_created[pt] = nm

    act_name = initial_action_name or getattr(context.scene, "af_director_anim_enum", DEFAULT_WALK_ACTION)
    act = bpy.data.actions.get(act_name) or bpy.data.actions.get(DEFAULT_WALK_ACTION)

    from .locomotion import get_character_exact_stride_speed

    ctrl_obj["af_is_char_controller"] = True
    ctrl_obj["af_elf_id"] = elf_info["id"]
    ctrl_obj["af_elf_title"] = elf_info["title"]
    ctrl_obj["af_armature_name"] = new_arm.name
    ctrl_obj["af_anim_name"] = act.name if act else DEFAULT_WALK_ACTION
    ctrl_obj["af_anim_speed"] = 1.0
    ctrl_obj["af_frame_offset"] = int(frame_offset)
    ctrl_obj["af_loop_anim"] = True
    ctrl_obj["af_flip_curve_dir"] = False
    ctrl_obj["af_attached_curve"] = ""
    ctrl_obj["af_curve_start_pct"] = 0.0
    ctrl_obj["af_char_scale"] = 1.0
    ctrl_obj["af_show_hat"] = bool("HAT" in parts_created)
    ctrl_obj["af_show_glasses"] = bool("GLASSES" in parts_created)
    ctrl_obj["af_pose_head_yaw"] = 0.0
    ctrl_obj["af_pose_head_pitch"] = 0.0
    ctrl_obj["af_pose_torso_bend"] = 0.0
    ctrl_obj["af_pose_torso_twist"] = 0.0
    ctrl_obj["af_pose_arms_raise"] = 0.0
    ctrl_obj["af_walk_speed"] = get_character_exact_stride_speed(ctrl_obj, act)

    if act:
        _assign_initial_action_safe(new_arm, act, speed_mult=1.0, frame_offset=frame_offset, loop_enabled=True)

    try:
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        ctrl_obj.select_set(True)
        context.view_layer.objects.active = ctrl_obj
    except Exception:
        pass

    enable_viewport_transform_gizmos()
    if callable(sync_ui_callback):
        sync_ui_callback(ctrl_obj)
    return ctrl_obj


def swap_character_model_on_controller(
    context,
    ctrl_obj,
    new_elf_id: str,
    apply_settings_callback=None,
) -> bool:
    """
    Swaps the rigged Elf model inside an existing `CTRL_*` controller while preserving
    its world transform, character scale, active animation, NLA tracks, pose overrides,
    and curve locomotion constraint.
    """
    if not ctrl_obj or not ctrl_obj.get("af_is_char_controller"):
        return False
    if ctrl_obj.get("af_elf_id") == new_elf_id:
        return True

    ensure_library_loaded(load_templates=True, load_actions=True)
    elf_info = get_elf_info(new_elf_id)
    tpl_arm = bpy.data.objects.get(elf_info["arm_name"])
    if not tpl_arm:
        return False

    old_arm = get_character_armature_from_ctrl(ctrl_obj)
    saved_nla_specs = []
    if old_arm and old_arm.animation_data:
        for tr in old_arm.animation_data.nla_tracks:
            if not tr.name.startswith("AF_AutoPlayback"):
                strips_info = []
                for s in tr.strips:
                    strips_info.append({
                        "name": s.name,
                        "start": int(round(s.frame_start)),
                        "action": s.action,
                        "scale": float(s.scale),
                        "repeat": float(s.repeat),
                        "blend_in": float(s.blend_in),
                        "blend_out": float(s.blend_out),
                        "blend_type": str(s.blend_type),
                        "extrapolation": str(s.extrapolation),
                    })
                saved_nla_specs.append({"name": tr.name, "strips": strips_info})

    if old_arm:
        for ch in list(old_arm.children):
            bpy.data.objects.remove(ch, do_unlink=True)
        bpy.data.objects.remove(old_arm, do_unlink=True)

    actors_col = ensure_collection(ACTORS_COLLECTION_NAME)
    actor_prefix = ctrl_obj.name.replace("CTRL_", "Actor_")

    new_arm = tpl_arm.copy()
    new_arm.data = tpl_arm.data.copy()
    new_arm.name = f"{actor_prefix}_{new_elf_id}"
    new_arm.parent = ctrl_obj
    new_arm.location = (0.0, 0.0, 0.0)
    new_arm.rotation_mode = "XYZ"
    new_arm.rotation_euler = (0.0, 0.0, 0.0)
    new_arm.scale = (1.0, 1.0, 1.0)
    new_arm["af_elf_id"] = new_elf_id
    new_arm["af_is_template"] = False
    new_arm["af_controller_name"] = ctrl_obj.name
    new_arm.hide_viewport = False
    new_arm.show_in_front = False
    actors_col.objects.link(new_arm)

    glass_mat = ensure_optical_glass_material()
    tpl_meshes = sorted(
        [o for o in bpy.data.objects if o.parent == tpl_arm and o.type == "MESH"],
        key=lambda x: x.name,
    )
    parts_created = {}
    for idx, m in enumerate(tpl_meshes, start=1):
        pt = _infer_mesh_part_type(m)
        nm = m.copy()
        nm.data = m.data.copy()
        suffix = pt if pt not in parts_created else f"{pt}_{idx:02d}"
        nm.name = f"{new_arm.name}_{suffix}"
        nm.parent = new_arm
        nm.matrix_parent_inverse = m.matrix_parent_inverse.copy()
        nm.location = m.location.copy()
        nm.rotation_euler = m.rotation_euler.copy()
        nm.scale = m.scale.copy()
        nm.hide_viewport = False
        nm.hide_render = False
        nm["af_part_type"] = pt
        nm["af_controller_name"] = ctrl_obj.name
        for mod in nm.modifiers:
            if mod.type == "ARMATURE":
                mod.object = new_arm
        for slot in nm.material_slots:
            if slot.material and ("glass_mat" in slot.material.name.lower() or "lens" in slot.material.name.lower()):
                slot.material = glass_mat
        actors_col.objects.link(nm)
        parts_created[pt] = nm

    ctrl_obj["af_elf_id"] = new_elf_id
    ctrl_obj["af_elf_title"] = elf_info["title"]
    ctrl_obj["af_armature_name"] = new_arm.name
    ctrl_obj["af_show_hat"] = bool("HAT" in parts_created)
    ctrl_obj["af_show_glasses"] = bool("GLASSES" in parts_created)

    if saved_nla_specs:
        if not new_arm.animation_data:
            new_arm.animation_data_create()
        new_arm.animation_data.action = None
        for tr_spec in saved_nla_specs:
            tr = new_arm.animation_data.nla_tracks.new()
            tr.name = tr_spec["name"]
            for s_spec in tr_spec["strips"]:
                if not s_spec["action"]:
                    continue
                st = tr.strips.new(s_spec["name"], s_spec["start"], s_spec["action"])
                st.scale = s_spec["scale"]
                st.repeat = s_spec["repeat"]
                st.blend_in = s_spec["blend_in"]
                st.blend_out = s_spec["blend_out"]
                st.blend_type = s_spec["blend_type"]
                st.extrapolation = s_spec["extrapolation"]
                bind_action_slot(st, s_spec["action"])

    if callable(apply_settings_callback):
        apply_settings_callback(context, ctrl_obj)
    else:
        act = bpy.data.actions.get(ctrl_obj.get("af_anim_name", DEFAULT_WALK_ACTION))
        if act:
            _assign_initial_action_safe(
                new_arm,
                act,
                speed_mult=float(ctrl_obj.get("af_anim_speed", 1.0)),
                frame_offset=int(ctrl_obj.get("af_frame_offset", 0)),
                loop_enabled=bool(ctrl_obj.get("af_loop_anim", True)),
            )
    return True


def duplicate_elf_actor(context, ctrl_obj, offset_vec=(1.2, 0.0, 0.0), frame_offset=None):
    """Spawns a duplicate of `ctrl_obj` offset in world space with desynchronized frame offset."""
    if not ctrl_obj:
        return None
    elf_id = ctrl_obj.get("af_elf_id", "ELF10")
    anim_name = ctrl_obj.get("af_anim_name", DEFAULT_WALK_ACTION)
    pos = ctrl_obj.matrix_world.translation + Vector(offset_vec)
    if frame_offset is None:
        frame_offset = random.randint(5, 45)

    new_ctrl = spawn_elf_actor(
        context,
        elf_id=elf_id,
        location=pos,
        initial_action_name=anim_name,
        frame_offset=frame_offset,
    )
    if not new_ctrl:
        return None

    scale_val = float(ctrl_obj.get("af_char_scale", ctrl_obj.scale.z))
    new_ctrl.scale = (scale_val, scale_val, scale_val)
    new_ctrl["af_char_scale"] = scale_val
    new_ctrl["af_anim_speed"] = float(ctrl_obj.get("af_anim_speed", 1.0))
    new_ctrl["af_loop_anim"] = bool(ctrl_obj.get("af_loop_anim", True))

    set_actor_accessories(
        new_ctrl,
        show_hat=bool(ctrl_obj.get("af_show_hat", False)),
        show_glasses=bool(ctrl_obj.get("af_show_glasses", False)),
        equip_if_missing=True,
    )
    return new_ctrl


def delete_elf_actor(context, ctrl_obj) -> bool:
    """Removes `ctrl_obj`, its child armature and meshes, and its per-controller path action."""
    if not ctrl_obj:
        return False
    ctrl_name = ctrl_obj.name
    arm = get_character_armature_from_ctrl(ctrl_obj)
    if arm:
        for ch in list(arm.children):
            bpy.data.objects.remove(ch, do_unlink=True)
        bpy.data.objects.remove(arm, do_unlink=True)

    pa = bpy.data.actions.get(f"PathAnim_{ctrl_name}")
    if pa:
        try:
            bpy.data.actions.remove(pa, do_unlink=True)
        except Exception:
            pass

    bpy.data.objects.remove(ctrl_obj, do_unlink=True)

    rem = get_all_scene_character_controllers()
    if rem and context and hasattr(context, "view_layer"):
        try:
            rem[0].select_set(True)
            context.view_layer.objects.active = rem[0]
        except Exception:
            pass
    return True
