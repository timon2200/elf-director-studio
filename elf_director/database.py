# -*- coding: utf-8 -*-
"""
ActionForge Elf Director Studio v3.0 — Asset Database & Biomechanical Retargeter
================================================================================
Manages automatic lazy-loading of the 7 rigged Elf templates (`00_RIGGED_ELF_TEMPLATES`)
and 24+ `AF_*` animations from `database/elf_assets_library.blend`, zero-slip mocap
retargeting/baking, drop-in animation scanning, and database persistence.
"""

import glob
import os
import bpy
from mathutils import Matrix, Vector

from .constants import (
    ACTORS_COLLECTION_NAME,
    AF_TO_BVH_ALIASES,
    AF_TO_MIXAMO,
    DEFAULT_IDLE_ACTION,
    DEFAULT_WALK_ACTION,
    PATHS_COLLECTION_NAME,
    PRIMARY_CHILD,
    RIGGED_ELF_ROSTER,
    TEMPLATE_COLLECTION_NAME,
    bind_action_slot,
    ensure_collection,
    get_action_fcurves,
    get_dropin_anims_dir,
    get_library_blend_path,
    load_registry,
    save_registry,
)


# ============================================================================
# 1. AUTOMATIC DATABASE LOADER & REGISTRY SYNC
# ============================================================================

def _restore_action_metadata_from_registry(reg_data: dict):
    """Restores custom properties (`af_category`, `af_is_locomotion`, `af_speed_mps`, etc.) on loaded Actions."""
    anim_map = {
        a["name"]: a
        for a in reg_data.get("animations", [])
        if isinstance(a, dict) and "name" in a
    }
    for act in bpy.data.actions:
        if act.name.startswith("PathAnim_"):
            continue
        if act.name.startswith("AF_"):
            act.use_fake_user = True
            meta = anim_map.get(act.name)
            if meta:
                if "af_category" not in act:
                    act["af_category"] = meta.get("category", "CUSTOM")
                if "af_is_locomotion" not in act:
                    act["af_is_locomotion"] = bool(meta.get("is_locomotion", False))
                if "af_speed_mps" not in act:
                    act["af_speed_mps"] = float(meta.get("speed_mps", 0.0))
                if "af_ref_leg_len" not in act:
                    act["af_ref_leg_len"] = float(meta.get("ref_leg_len_m", 0.9961))
                if "af_is_backwards" not in act:
                    act["af_is_backwards"] = bool(meta.get("is_backwards", False))


def ensure_library_loaded(load_templates: bool = True, load_actions: bool = True) -> dict:
    """
    Ensures all 7 `TPL_ARM_*` rigged elf templates and all `AF_*` animations from
    `database/elf_assets_library.blend` are present in `bpy.data`.
    Appends any missing datablocks seamlessly and keeps `00_RIGGED_ELF_TEMPLATES` hidden.
    """
    reg_data = load_registry()
    lib_path = get_library_blend_path()

    missing_arms = [
        e["arm_name"]
        for e in RIGGED_ELF_ROSTER
        if bpy.data.objects.get(e["arm_name"]) is None
    ] if load_templates else []

    expected_anims = [
        a["name"]
        for a in reg_data.get("animations", [])
        if isinstance(a, dict) and "name" in a
    ]
    if not expected_anims:
        expected_anims = [DEFAULT_WALK_ACTION, DEFAULT_IDLE_ACTION]

    missing_anims = [
        name for name in expected_anims if bpy.data.actions.get(name) is None
    ] if load_actions else []

    loaded_tpl_count = 0
    loaded_act_count = 0

    if (missing_arms or missing_anims) and os.path.exists(lib_path):
        try:
            with bpy.data.libraries.load(lib_path, link=False) as (data_from, data_to):
                if missing_arms:
                    if TEMPLATE_COLLECTION_NAME in data_from.collections and not bpy.data.collections.get(TEMPLATE_COLLECTION_NAME):
                        data_to.collections = [TEMPLATE_COLLECTION_NAME]
                    else:
                        sub_cols = [
                            e["col_name"]
                            for e in RIGGED_ELF_ROSTER
                            if e["arm_name"] in missing_arms and e["col_name"] in data_from.collections
                        ]
                        if sub_cols:
                            data_to.collections = sub_cols
                        else:
                            obj_names = [
                                o_name
                                for o_name in data_from.objects
                                if any(o_name.startswith(arm_n) for arm_n in missing_arms)
                            ]
                            data_to.objects = obj_names

                if load_actions:
                    avail_af = [
                        a_name
                        for a_name in data_from.actions
                        if a_name.startswith("AF_") and bpy.data.actions.get(a_name) is None
                    ]
                    data_to.actions = avail_af
                    loaded_act_count = len(avail_af)
            for lib in list(bpy.data.libraries):
                if len(getattr(lib, "users_id", ())) == 0:
                    try:
                        bpy.data.libraries.remove(lib)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[ElfDirector] Error loading library '{lib_path}': {e}")

    # Link and hide template collection
    tpl_col = bpy.data.collections.get(TEMPLATE_COLLECTION_NAME)
    if tpl_col:
        if bpy.context and bpy.context.scene:
            scn_col = bpy.context.scene.collection
            if tpl_col.name not in scn_col.children:
                try:
                    scn_col.children.link(tpl_col)
                except Exception:
                    pass
        for e in RIGGED_ELF_ROSTER:
            sub = bpy.data.collections.get(e["col_name"])
            if sub and sub.name not in tpl_col.children:
                try:
                    tpl_col.children.link(sub)
                except Exception:
                    pass
        tpl_col.hide_viewport = True
        tpl_col.hide_render = True

    _restore_action_metadata_from_registry(reg_data)

    for act in bpy.data.actions:
        if act.name.startswith("AF_"):
            act.use_fake_user = True
            set_action_cyclic_loop(act, enabled=True)

    present_arms = [
        e["arm_name"] for e in RIGGED_ELF_ROSTER if bpy.data.objects.get(e["arm_name"]) is not None
    ]
    loaded_tpl_count = len(present_arms)
    total_af_actions = sum(1 for a in bpy.data.actions if a.name.startswith("AF_"))

    return {
        "loaded_templates": loaded_tpl_count,
        "loaded_actions": loaded_act_count,
        "total_templates": len(present_arms),
        "total_actions": total_af_actions,
    }


# ============================================================================
# 2. BIOMECHANICAL BONE RESOLUTION & LEG LENGTH (HIDDEN-COLLECTION SAFE)
# ============================================================================

def resolve_source_bone_name(src_arm, d_name: str):
    """
    Maps a canonical ActionForge bone name (`d_name`) to the matching bone in `src_arm`.
    Supports exact match, case-insensitive match, Mixamo names, `mixamorig:` prefixes,
    and CMU / Bandai Namco / SMPL BVH aliases.
    """
    if not src_arm or not getattr(src_arm, "data", None):
        return None
    bones = src_arm.data.bones
    if d_name in bones:
        return d_name

    d_lower = d_name.lower()
    for b in bones:
        if b.name.lower() == d_lower:
            return b.name

    mix_name = AF_TO_MIXAMO.get(d_name) or AF_TO_MIXAMO.get(d_lower)
    if mix_name:
        if mix_name in bones:
            return mix_name
        prefixed = f"mixamorig:{mix_name}"
        if prefixed in bones:
            return prefixed
        mix_lower = mix_name.lower()
        pref_lower = prefixed.lower()
        for b in bones:
            bl = b.name.lower()
            if bl == mix_lower or bl == pref_lower or bl.endswith(f":{mix_lower}"):
                return b.name

    aliases = AF_TO_BVH_ALIASES.get(d_name) or AF_TO_BVH_ALIASES.get(d_lower) or ()
    for cand in aliases:
        if cand in bones:
            return cand
        cl = cand.lower()
        for b in bones:
            if b.name.lower() == cl or b.name.lower().endswith(f":{cl}"):
                return b.name
    return None


def compute_armature_leg_length(arm_obj, scale_override=None) -> float:
    """
    Computes the biomechanical leg length (`thigh_l + calf_l + 0.5 * foot_l`) directly from
    `arm_obj.data.bones` local rest vectors multiplied by character scale.
    CRITICAL FIX: Does NOT rely on `arm_obj.matrix_world` alone because template armatures inside
    hidden collections (`00_RIGGED_ELF_TEMPLATES`) may have un-evaluated world matrices.
    """
    if not arm_obj or arm_obj.type != "ARMATURE" or not arm_obj.data:
        return 1.0

    if scale_override is not None:
        scale = float(scale_override)
    elif arm_obj.parent is not None:
        scale = float(arm_obj.parent.scale.z)
    else:
        scale = float(arm_obj.scale.z)
    if scale <= 1e-4:
        scale = 1.0

    total_local = 0.0
    for d_name, weight in (("thigh_l", 1.0), ("calf_l", 1.0), ("foot_l", 0.5)):
        b_name = resolve_source_bone_name(arm_obj, d_name)
        if b_name and b_name in arm_obj.data.bones:
            b = arm_obj.data.bones[b_name]
            total_local += (b.tail_local - b.head_local).length * weight

    total_l = total_local * scale
    if total_l < 0.2:
        s_hips = resolve_source_bone_name(arm_obj, "pelvis")
        if s_hips and s_hips in arm_obj.data.bones:
            total_l = max(0.3, float(arm_obj.data.bones[s_hips].head_local.z) * scale)
        else:
            total_l = 1.0
    return total_l


def set_action_cyclic_loop(action, enabled: bool = True):
    """Adds or removes the `CYCLES` F-Curve modifier on all F-Curves of `action` (Blender 4.x & 5.x)."""
    if not action:
        return
    for fc in get_action_fcurves(action):
        cyc = next((m for m in fc.modifiers if m.type == "CYCLES"), None)
        if enabled and not cyc:
            try:
                fc.modifiers.new(type="CYCLES")
            except Exception:
                pass
        elif not enabled and cyc:
            try:
                fc.modifiers.remove(cyc)
            except Exception:
                pass


# ============================================================================
# 3. ZERO-SLIP BIOMECHANICAL RETARGETER & DROP-IN ANIMATION IMPORTER
# ============================================================================

def bake_animation_to_actionforge_rig(
    src_arm,
    dst_arm,
    action_name: str,
    in_place_locomotion: bool = False,
    default_speed_mps: float = 1.42,
    category: str = "ACTIONFORGE",
):
    """
    Retargets and bakes `src_arm`'s animation onto `dst_arm` (canonical ActionForge rig)
    with ZERO foot sliding:
    - Temporarily unhides `00_RIGGED_ELF_TEMPLATES` and `dst_arm` so Blender's depsgraph
      evaluates `dst_arm` accurately during baking, then restores visibility.
    - Extracts exact total root displacement `total_disp_xy` over `(f_end - f_start)` frames
      and computes `locked_speed_mps`.
    - Subtracts ONLY the constant linear trend from `pelvis`, preserving intra-step hip surge.
    """
    tpl_col = bpy.data.collections.get(TEMPLATE_COLLECTION_NAME)
    orig_col_hide = tpl_col.hide_viewport if tpl_col else False
    orig_dst_hide = dst_arm.hide_viewport if dst_arm else False
    orig_frame = bpy.context.scene.frame_current if (bpy.context and bpy.context.scene) else 1

    sub_cols_state = []
    if tpl_col:
        tpl_col.hide_viewport = False
        for ch_col in tpl_col.children:
            sub_cols_state.append((ch_col, ch_col.hide_viewport))
            ch_col.hide_viewport = False
    if dst_arm:
        dst_arm.hide_viewport = False

    try:
        src_act = src_arm.animation_data.action if src_arm.animation_data else None
        if src_act:
            f_start = int(round(src_act.frame_range[0]))
            f_end = int(round(src_act.frame_range[1]))
        else:
            f_start, f_end = 1, 60
        if f_end <= f_start:
            f_end = f_start + 30

        fps = bpy.context.scene.render.fps / max(1e-4, bpy.context.scene.render.fps_base)
        mw_s = src_arm.matrix_world.to_3x3().normalized()
        mw_d = dst_arm.matrix_world.to_3x3().normalized()

        offset_mats = {}
        for d_name, db in dst_arm.data.bones.items():
            s_name = resolve_source_bone_name(src_arm, d_name)
            if not s_name:
                continue
            sb = src_arm.data.bones[s_name]
            s_rest = (mw_s @ sb.matrix_local.to_3x3()).normalized()
            d_rest = (mw_d @ db.matrix_local.to_3x3()).normalized()

            c_d = PRIMARY_CHILD.get(d_name)
            if c_d and c_d not in dst_arm.data.bones and c_d.lower() in dst_arm.data.bones:
                c_d = c_d.lower()
            c_s = resolve_source_bone_name(src_arm, c_d) if c_d else None
            if c_d and c_s and c_s in src_arm.data.bones and c_d in dst_arm.data.bones:
                v_s = src_arm.data.bones[c_s].head_local - sb.head_local
                v_d = dst_arm.data.bones[c_d].head_local - db.head_local
                if v_s.length > 1e-5 and v_d.length > 1e-5:
                    u_src = (mw_s @ v_s).normalized()
                    u_dst = (mw_d @ v_d).normalized()
                    r_align = u_dst.rotation_difference(u_src).to_matrix()
                else:
                    r_align = Matrix.Identity(3)
            else:
                r_align = Matrix.Identity(3)
            offset_mats[d_name] = (s_name, s_rest, d_rest, r_align)

        s_hips_name = resolve_source_bone_name(src_arm, "pelvis")
        src_leg_len = compute_armature_leg_length(src_arm)
        dst_leg_len = compute_armature_leg_length(dst_arm)
        if s_hips_name and "pelvis" in dst_arm.data.bones:
            w_s_hips_rest = src_arm.matrix_world @ src_arm.data.bones[s_hips_name].head_local
            leg_scale = max(0.2, min(5.0, dst_leg_len / max(0.2, src_leg_len)))
            d_pelvis_rest_3x3 = dst_arm.data.bones["pelvis"].matrix_local.to_3x3().normalized()
        else:
            w_s_hips_rest = Vector((0.0, 0.0, 1.0))
            leg_scale = 1.0
            d_pelvis_rest_3x3 = Matrix.Identity(3)

        bpy.context.scene.frame_set(f_start)
        esrc_0 = src_arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        w_s_hips_start = (
            (src_arm.matrix_world @ esrc_0.pose.bones[s_hips_name].head)
            if s_hips_name
            else w_s_hips_rest.copy()
        )

        bpy.context.scene.frame_set(f_end)
        esrc_1 = src_arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        w_s_hips_end = (
            (src_arm.matrix_world @ esrc_1.pose.bones[s_hips_name].head)
            if s_hips_name
            else w_s_hips_rest.copy()
        )

        n_intervals = max(1, f_end - f_start)
        total_disp_xy = Vector((
            w_s_hips_end.x - w_s_hips_start.x,
            w_s_hips_end.y - w_s_hips_start.y,
            0.0,
        )) * leg_scale
        duration_sec = n_intervals / fps

        if in_place_locomotion and total_disp_xy.length > 0.20:
            locked_speed_mps = total_disp_xy.length / duration_sec
            is_backwards = (w_s_hips_end.y - w_s_hips_start.y) > 0.15
        else:
            locked_speed_mps = float(default_speed_mps) if in_place_locomotion else 0.0
            is_backwards = "backward" in action_name.lower()

        old_act = bpy.data.actions.get(action_name)
        if old_act:
            bpy.data.actions.remove(old_act)

        new_act = bpy.data.actions.new(name=action_name)
        new_act.use_fake_user = True
        new_act["af_category"] = category
        new_act["af_is_locomotion"] = bool(in_place_locomotion)
        new_act["af_speed_mps"] = round(float(locked_speed_mps), 4)
        new_act["af_ref_leg_len"] = round(float(dst_leg_len), 4)
        new_act["af_is_backwards"] = bool(is_backwards)

        if not dst_arm.animation_data:
            dst_arm.animation_data_create()
        dst_arm.animation_data.action = new_act
        bind_action_slot(dst_arm.animation_data, new_act)

        for dpb in dst_arm.pose.bones:
            dpb.rotation_mode = "QUATERNION"
            dpb.location = (0.0, 0.0, 0.0)
            dpb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            dpb.scale = (1.0, 1.0, 1.0)

        for f in range(f_start, f_end + 1):
            bpy.context.scene.frame_set(f)
            esrc = src_arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
            u_frac = float(f - f_start) / float(n_intervals)

            d_target_map = {}
            for b in dst_arm.data.bones:
                d_name = b.name
                if d_name not in offset_mats:
                    continue
                s_name, s_rest, d_rest, r_align = offset_mats[d_name]
                s_posed = (mw_s @ esrc.pose.bones[s_name].matrix.to_3x3()).normalized()
                d_target = (s_posed @ s_rest.inverted()) @ r_align @ d_rest
                d_target_map[d_name] = d_target

                if b.parent and b.parent.name in d_target_map:
                    p_posed = d_target_map[b.parent.name]
                    p_rest = (mw_d @ b.parent.matrix_local.to_3x3()).normalized()
                    rest_rel = p_rest.inverted() @ d_rest
                    local_rot = (p_posed @ rest_rel).inverted() @ d_target
                else:
                    local_rot = d_rest.inverted() @ d_target

                dpb = dst_arm.pose.bones[d_name]
                dpb.rotation_quaternion = local_rot.to_quaternion()
                dpb.keyframe_insert(data_path="rotation_quaternion", frame=f - f_start + 1)

            if s_hips_name and "pelvis" in dst_arm.pose.bones:
                w_s_hips_cur = src_arm.matrix_world @ esrc.pose.bones[s_hips_name].head
                delta_w = Vector((
                    (w_s_hips_cur.x - w_s_hips_start.x) * leg_scale,
                    (w_s_hips_cur.y - w_s_hips_start.y) * leg_scale,
                    (w_s_hips_cur.z - w_s_hips_rest.z) * leg_scale,
                ))
                if in_place_locomotion:
                    delta_w.x -= total_disp_xy.x * u_frac
                    delta_w.y -= total_disp_xy.y * u_frac

                dpb_pelvis = dst_arm.pose.bones["pelvis"]
                dpb_pelvis.location = d_pelvis_rest_3x3.inverted() @ (mw_d.inverted() @ delta_w)
                dpb_pelvis.keyframe_insert(data_path="location", frame=f - f_start + 1)

        bind_action_slot(dst_arm.animation_data, new_act)
        set_action_cyclic_loop(new_act, enabled=True)
        return new_act
    finally:
        if dst_arm:
            idle_act = bpy.data.actions.get(DEFAULT_IDLE_ACTION)
            if idle_act and dst_arm.animation_data:
                dst_arm.animation_data.action = idle_act
                bind_action_slot(dst_arm.animation_data, idle_act)
            dst_arm.hide_viewport = orig_dst_hide
        if tpl_col:
            for ch_col, st in sub_cols_state:
                ch_col.hide_viewport = st
            tpl_col.hide_viewport = orig_col_hide
        try:
            bpy.context.scene.frame_set(orig_frame)
        except Exception:
            pass


def import_and_bake_animation_file(
    filepath: str,
    dst_template_arm=None,
    action_name: str = None,
    in_place=None,
    speed_mps: float = 1.42,
    category: str = "CUSTOM",
    save_to_db: bool = False,
):
    """
    Imports an external `.glb`, `.gltf`, or `.fbx` animation file, retargets/bakes it
    onto `dst_template_arm`, cleans up temporary objects, and optionally saves to database.
    """
    if not filepath or not os.path.exists(filepath):
        return None

    if dst_template_arm is None:
        ensure_library_loaded(load_templates=True, load_actions=False)
        dst_template_arm = (
            bpy.data.objects.get("TPL_ARM_Elf10_Urar")
            or next(
                (bpy.data.objects.get(e["arm_name"]) for e in RIGGED_ELF_ROSTER if bpy.data.objects.get(e["arm_name"])),
                None,
            )
        )
    if not dst_template_arm:
        return None

    ext = os.path.splitext(filepath)[1].lower()
    before_objs = set(bpy.data.objects)
    before_acts = set(bpy.data.actions)

    try:
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=filepath)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=filepath)
        else:
            return None
    except Exception as e:
        print(f"[ElfDirector] Failed to import animation file '{filepath}': {e}")
        return None

    new_objs = [o for o in bpy.data.objects if o not in before_objs]
    new_acts = [a for a in bpy.data.actions if a not in before_acts]
    src_arm = next((o for o in new_objs if o.type == "ARMATURE"), None)

    if not src_arm:
        for o in new_objs:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        return None

    if not action_name:
        base = os.path.splitext(os.path.basename(filepath))[0]
        base_clean = base.split("[")[0].strip().replace(" ", "_").replace("-", "_")
        action_name = base_clean if base_clean.startswith("AF_") else f"AF_{base_clean}"

    if in_place is None:
        nl = action_name.lower()
        in_place = any(k in nl for k in ("walk", "jog", "run", "strafe", "locomotion", "march", "sprint"))

    if category == "CUSTOM" and in_place:
        category = "LOCOMOTION"

    baked_act = bake_animation_to_actionforge_rig(
        src_arm=src_arm,
        dst_arm=dst_template_arm,
        action_name=action_name,
        in_place_locomotion=bool(in_place),
        default_speed_mps=float(speed_mps),
        category=category,
    )

    for o in new_objs:
        try:
            bpy.data.objects.remove(o, do_unlink=True)
        except Exception:
            pass
    for a in new_acts:
        if a != baked_act:
            try:
                bpy.data.actions.remove(a)
            except Exception:
                pass

    if baked_act and save_to_db:
        save_database_to_disk()

    return baked_act


def scan_dropin_animations(save_to_db: bool = False) -> list:
    """
    Scans `database/animations_dropin/` for `.glb`, `.gltf`, and `.fbx` files and
    automatically imports and bakes any animations not yet in `bpy.data.actions`.
    """
    dropin_dir = get_dropin_anims_dir()
    if not os.path.isdir(dropin_dir):
        return []

    ensure_library_loaded(load_templates=True, load_actions=True)
    tpl_arm = (
        bpy.data.objects.get("TPL_ARM_Elf10_Urar")
        or next(
            (bpy.data.objects.get(e["arm_name"]) for e in RIGGED_ELF_ROSTER if bpy.data.objects.get(e["arm_name"])),
            None,
        )
    )
    if not tpl_arm:
        return []

    imported_names = []
    patterns = ("*.glb", "*.gltf", "*.fbx")
    files = []
    for pat in patterns:
        files.extend(glob.glob(os.path.join(dropin_dir, pat)))

    for fpath in sorted(set(files)):
        base = os.path.splitext(os.path.basename(fpath))[0]
        base_clean = base.split("[")[0].strip().replace(" ", "_").replace("-", "_")
        act_name = base_clean if base_clean.startswith("AF_") else f"AF_{base_clean}"
        if bpy.data.actions.get(act_name):
            continue
        act = import_and_bake_animation_file(
            filepath=fpath,
            dst_template_arm=tpl_arm,
            action_name=act_name,
            save_to_db=False,
        )
        if act:
            imported_names.append(act.name)

    if imported_names and save_to_db:
        save_database_to_disk()

    return imported_names


# ============================================================================
# 4. ANIMATION REMOVAL & PERSISTENT DATABASE WRITER
# ============================================================================

def remove_animation_from_library(action_name: str, save_to_db: bool = False) -> tuple:
    """
    Removes `action_name` from `bpy.data.actions` (protecting `AF_06_Idle_Breathing`),
    safely falls back any scene actors using it to `AF_06_Idle_Breathing`, and optionally
    updates `database/elf_assets_library.blend` + `registry.json`.
    """
    if not action_name or action_name == "NONE":
        return False, "Nije odabrana nijedna animacija."
    if action_name == DEFAULT_IDLE_ACTION:
        return False, f"Osnovna animacija '{DEFAULT_IDLE_ACTION}' je zaštićena i ne može se obrisati."

    act = bpy.data.actions.get(action_name)
    if not act:
        return False, f"Animacija '{action_name}' nije pronađena u sceni."

    fallback_act = bpy.data.actions.get(DEFAULT_IDLE_ACTION)
    actors_col = bpy.data.collections.get(ACTORS_COLLECTION_NAME)
    if actors_col:
        for obj in actors_col.all_objects:
            if obj.get("af_is_char_controller"):
                if obj.get("af_anim_name") == action_name:
                    obj["af_anim_name"] = DEFAULT_IDLE_ACTION
                arm_name = obj.get("af_armature_name")
                arm_obj = bpy.data.objects.get(arm_name) if arm_name else None
                if arm_obj and arm_obj.animation_data:
                    adt = arm_obj.animation_data
                    if adt.action == act:
                        adt.action = fallback_act
                        if fallback_act:
                            bind_action_slot(adt, fallback_act)
                    for tr in list(adt.nla_tracks):
                        for s in list(tr.strips):
                            if s.action == act:
                                tr.strips.remove(s)

    for obj in bpy.data.objects:
        if obj.type == "ARMATURE" and obj.animation_data and obj.animation_data.action == act:
            obj.animation_data.action = fallback_act
            if fallback_act:
                bind_action_slot(obj.animation_data, fallback_act)

    try:
        bpy.data.actions.remove(act, do_unlink=True)
    except Exception as e:
        return False, f"Greška pri brisanju animacije '{action_name}': {e}"

    if save_to_db:
        ok, msg = save_database_to_disk()
        if not ok:
            return True, f"Obrisana '{action_name}' iz memorije (upozorenje pri spremanju baze: {msg})."
        return True, f"Obrisana animacija '{action_name}' i ažurirana baza podataka."

    return True, f"Obrisana animacija '{action_name}' iz trenutne scene."


def save_database_to_disk() -> tuple:
    """
    Writes `00_RIGGED_ELF_TEMPLATES` and all `AF_*` actions to `database/elf_assets_library.blend`
    and updates `database/registry.json`.
    """
    ensure_library_loaded(load_templates=True, load_actions=True)
    lib_path = get_library_blend_path()
    os.makedirs(os.path.dirname(lib_path), exist_ok=True)

    fps = 30.0
    if bpy.context and bpy.context.scene:
        fps = bpy.context.scene.render.fps / max(1e-4, bpy.context.scene.render.fps_base)

    datablocks = set()
    tpl_col = bpy.data.collections.get(TEMPLATE_COLLECTION_NAME)
    if tpl_col:
        datablocks.add(tpl_col)
        for ch_col in tpl_col.children_recursive:
            datablocks.add(ch_col)
        for obj in tpl_col.all_objects:
            datablocks.add(obj)

    af_actions = sorted(
        [a for a in bpy.data.actions if a.name.startswith("AF_") and not a.name.startswith("PathAnim_")],
        key=lambda x: x.name,
    )
    for act in af_actions:
        act.use_fake_user = True
        datablocks.add(act)

    try:
        bpy.data.libraries.write(lib_path, datablocks, fake_user=True)
    except Exception as e:
        return False, f"Neuspješno pisanje u '{os.path.basename(lib_path)}': {e}"

    elves_meta = []
    for e in RIGGED_ELF_ROSTER:
        arm = bpy.data.objects.get(e["arm_name"])
        parts = []
        if arm:
            for ch in arm.children:
                if ch.type == "MESH":
                    pt = ch.get("af_part_type", "")
                    if not pt:
                        for cand in ("BODY", "HEAD", "HAT", "GLASSES"):
                            if ch.name.upper().endswith(f"_{cand}"):
                                pt = cand
                                break
                    if pt and pt not in parts:
                        parts.append(pt)
        if not parts:
            parts = ["BODY", "HEAD"]
            if e.get("has_hat"):
                parts.append("HAT")
            if e.get("has_glasses"):
                parts.append("GLASSES")
        parts.sort()
        elves_meta.append({
            "id": e["id"],
            "title": e["title"],
            "template_armature": e["arm_name"],
            "collection": e["col_name"],
            "parts": parts,
            "has_hat": bool(e.get("has_hat", False)),
            "has_glasses": bool(e.get("has_glasses", False)),
        })

    anims_meta = []
    for act in af_actions:
        f_count = max(1, int(round(act.frame_range[1] - act.frame_range[0])) + 1)
        dur_s = round((f_count - 1) / max(1.0, fps), 2)
        anims_meta.append({
            "name": act.name,
            "category": str(act.get("af_category", "CUSTOM")),
            "is_locomotion": bool(act.get("af_is_locomotion", False)),
            "speed_mps": round(float(act.get("af_speed_mps", 0.0)), 4),
            "ref_leg_len_m": round(float(act.get("af_ref_leg_len", 0.9961)), 4),
            "is_backwards": bool(act.get("af_is_backwards", False)),
            "frames": f_count,
            "duration_sec": dur_s,
        })

    reg_payload = {
        "package": "ActionForge Elf Animation Director Studio",
        "version": "3.0.0",
        "schema_version": 3,
        "library_blend": "database/elf_assets_library.blend",
        "template_collection": TEMPLATE_COLLECTION_NAME,
        "actors_collection": ACTORS_COLLECTION_NAME,
        "paths_collection": PATHS_COLLECTION_NAME,
        "elves_count": len(elves_meta),
        "animations_count": len(anims_meta),
        "elves": elves_meta,
        "animations": anims_meta,
    }
    save_registry(reg_payload)
    return True, f"Spremljeno {len(elves_meta)} vilenjaka i {len(anims_meta)} animacija u '{os.path.basename(lib_path)}'."
