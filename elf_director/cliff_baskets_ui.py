# -*- coding: utf-8 -*-
"""
N-Panel UI, Operators & Reactive Property Callbacks for the
Cliff Basket, 4-Gizmo Rope Rig & Damped Pendulum / Pickaxe Recoil Physics Studio.
"""

import math
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from .cliff_baskets import (
    CLIFF_BASKET_PRESETS,
    CLIFF_CARGO_PRESETS,
    apply_basket_physics_to_rig,
    auto_snap_4_gizmos_to_basket_rim,
    bake_cliff_basket_physics_to_keyframes,
    clear_baked_cliff_basket_keyframes,
    ensure_gn_cliff_mining_scaffolding_wall_snap,
    find_cliff_basket_rig,
    get_active_cliff_basket_rig,
    get_all_cliff_basket_rigs,
    mirror_active_pin_gizmo_to_all_4_corners,
    register_cliff_basket_handlers,
    register_cliff_basket_object_properties,
    reload_all_tripo_basket_models_in_scene,
    sample_glacier_wall_surface,
    show_viewport_move_gizmo_arrows,
    snap_single_basket_to_glacier_wall,
    spawn_cliff_basket_station,
    swap_cliff_basket_preset,
    sync_scaffolding_and_rails_to_glacier_wall,
    unregister_cliff_basket_handlers,
    update_rope_assembly_curves_for_rig,
)
from .constants import RIGGED_ELF_ROSTER, STATE


def _on_s3_wall_snap_settings_changed(self, context):
    if STATE.get("cb_ui_sync_guard", False):
        return
    scn = context.scene
    auto_adapt = bool(getattr(scn, "af_s3_auto_adapt_wall", True))
    standoff = float(getattr(scn, "af_s3_wall_standoff_m", 1.85))
    smoothing = int(getattr(scn, "af_s3_wall_smoothing", 4))
    ensure_gn_cliff_mining_scaffolding_wall_snap(
        wall_standoff_m=standoff,
        smoothing_iterations=smoothing,
        auto_adapt=auto_adapt,
    )
    if auto_adapt:
        sync_scaffolding_and_rails_to_glacier_wall(
            context=context,
            wall_standoff_m=standoff,
            smoothing_window=max(1, smoothing),
        )


def sync_cliff_basket_ui_from_rig(rig_root: bpy.types.Object):
    if not rig_root or STATE.get("cb_ui_sync_guard", False):
        return
    scn = getattr(bpy.context, "scene", None)
    if not scn:
        return

    STATE["cb_ui_sync_guard"] = True
    try:
        scn.af_cb_preset_enum = rig_root.get("af_cb_preset_id", "BASKET_01_OCT_EMPTY")
        scn.af_cb_num_ropes = str(int(rig_root.get("af_cb_num_ropes", 4)))
        scn.af_cb_rope_mode = rig_root.get("af_cb_rope_mode", "SPREADER_4_TO_1")
        scn.af_cb_rope_slack_cm = float(rig_root.get("af_cb_rope_slack_m", 0.035)) * 100.0
        scn.af_cb_winch_mode = rig_root.get("af_cb_winch_mode", "LOWER_AND_STOP")
        scn.af_cb_z_start = float(rig_root.get("af_cb_z_start", 1.85))
        scn.af_cb_z_work = float(rig_root.get("af_cb_z_work", 0.00))
        scn.af_cb_lower_start_frame = int(rig_root.get("af_cb_lower_start_frame", 1))
        scn.af_cb_lower_stop_frame = int(rig_root.get("af_cb_lower_stop_frame", 48))
        scn.af_cb_recoil_cm = float(rig_root.get("af_cb_recoil_cm", 15.0))
        scn.af_cb_tilt_kick_deg = float(rig_root.get("af_cb_tilt_kick_deg", 7.8))
        scn.af_cb_damping = float(rig_root.get("af_cb_damping", 1.55))
        scn.af_cb_wall_gap_cm = float(rig_root.get("af_cb_wall_gap_cm", 5.0))
        scn.af_cb_wall_restitution = float(rig_root.get("af_cb_wall_restitution", 0.30))
        scn.af_cb_hit_frame_offset = int(rig_root.get("af_cb_hit_frame_offset", 0))
    except Exception:
        pass
    finally:
        STATE["cb_ui_sync_guard"] = False


def on_cb_preset_changed(self, context):
    if STATE.get("cb_ui_sync_guard", False):
        return
    rig = get_active_cliff_basket_rig(context)
    if rig:
        swap_cliff_basket_preset(rig, self.af_cb_preset_enum, auto_snap_pins=True)
        apply_basket_physics_to_rig(rig, float(context.scene.frame_current), scene=context.scene)


def on_cb_physics_param_changed(self, context):
    if STATE.get("cb_ui_sync_guard", False):
        return
    rig = get_active_cliff_basket_rig(context)
    if not rig:
        return
    rig["af_cb_num_ropes"] = int(self.af_cb_num_ropes)
    rig["af_cb_rope_mode"] = self.af_cb_rope_mode
    rig["af_cb_rope_slack_m"] = float(self.af_cb_rope_slack_cm) * 0.01
    rig["af_cb_winch_mode"] = self.af_cb_winch_mode
    rig["af_cb_z_start"] = float(self.af_cb_z_start)
    rig["af_cb_z_work"] = float(self.af_cb_z_work)
    rig["af_cb_lower_start_frame"] = int(self.af_cb_lower_start_frame)
    rig["af_cb_lower_stop_frame"] = int(self.af_cb_lower_stop_frame)
    rig["af_cb_recoil_cm"] = float(self.af_cb_recoil_cm)
    rig["af_cb_tilt_kick_deg"] = float(self.af_cb_tilt_kick_deg)
    rig["af_cb_damping"] = float(self.af_cb_damping)
    rig["af_cb_wall_gap_cm"] = float(self.af_cb_wall_gap_cm)
    rig["af_cb_wall_restitution"] = float(self.af_cb_wall_restitution)
    rig["af_cb_hit_frame_offset"] = int(self.af_cb_hit_frame_offset)
    apply_basket_physics_to_rig(rig, float(context.scene.frame_current), scene=context.scene)


# ============================================================================
# OPERATORS
# ============================================================================

class AFDIR_OT_SpawnCliffBasketStation(bpy.types.Operator):
    bl_idname = "af_director.spawn_cliff_basket"
    bl_label = "+ Nova Košara na Zidu (4 Gizma + Fizika)"
    bl_description = "Stvara 3D košaru s vilenjakom i krampom, 4 interaktivna gizma za užad, kolotur, zid i fiziku ljuljanja"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        existing = get_all_cliff_basket_rigs(scn)
        x_off = len(existing) * 3.2
        preset_id = getattr(scn, "af_cb_preset_enum", "BASKET_01_OCT_EMPTY")
        elf_id = getattr(scn, "af_director_elf_enum", "ELF14") or "ELF14"
        rig = spawn_cliff_basket_station(
            context=context,
            preset_id=preset_id,
            elf_id=elf_id,
            location=(x_off, -1.8, 1.35),
            rotation_z_deg=95.0,
            winch_height_m=5.60,
            build_cliff_wall_preview=True,
            setup_demo_nla_sequence=True,
        )
        sync_cliff_basket_ui_from_rig(rig)
        # Select Pin 1 so the user immediately sees the Move gizmo on the basket rim
        p1 = bpy.data.objects.get(rig.get("af_cb_pin_01", ""))
        target = p1 or rig
        for o in list(context.selected_objects):
            o.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target
        show_viewport_move_gizmo_arrows(True)
        self.report({"INFO"}, f"Stvorena stanica košare na zidu: {rig.name} (Odabran {target.name})")
        return {"FINISHED"}


class AFDIR_OT_SelectCliffBasketGizmo(bpy.types.Operator):
    bl_idname = "af_director.select_cliff_gizmo"
    bl_label = "Odaberi Gizmo Košare (G/R/S)"
    bl_description = "Odabire traženi 3D gizmo (Pin 1..4, Sabirna Kuka, Gornji Kolotur, Zid ili Košaru) i uključuje strelice za pomicanje (G)"
    bl_options = {"REGISTER", "UNDO"}

    gizmo_key: StringProperty(default="af_cb_pin_01")

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            self.report({"WARNING"}, "Nema aktivne košare u sceni.")
            return {"CANCELLED"}

        if self.gizmo_key == "RIG_ROOT":
            target = rig
        else:
            target = bpy.data.objects.get(rig.get(self.gizmo_key, ""))

        if not target:
            self.report({"WARNING"}, f"Gizmo ({self.gizmo_key}) nije pronađen.")
            return {"CANCELLED"}

        target.hide_viewport = False
        if context.active_object and context.active_object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        for o in list(context.selected_objects):
            o.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target
        show_viewport_move_gizmo_arrows(True)
        sync_cliff_basket_ui_from_rig(rig)
        self.report({"INFO"}, f"Odabran gizmo: {target.name} — pomakni ga s 'G' ili strelicama u 3D Viewportu.")
        return {"FINISHED"}


class AFDIR_OT_MirrorCliffPinGizmos(bpy.types.Operator):
    bl_idname = "af_director.mirror_cliff_pins"
    bl_label = "Zrcali Odabrani Pin na Sva 4 Kuta"
    bl_description = "Uzima poziciju trenutno odabranog Pin gizma (ili Pin 1) i simetrično postavlja sva 4 gizma na kutove košare"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            return {"CANCELLED"}
        active = context.active_object
        mirror_active_pin_gizmo_to_all_4_corners(rig, source_pin_obj=active)
        self.report({"INFO"}, "Sva 4 gizma za užad simetrično su poravnata prema odabranom kutu.")
        return {"FINISHED"}


class AFDIR_OT_AutoSnapCliffPinGizmos(bpy.types.Operator):
    bl_idname = "af_director.autosnap_cliff_pins"
    bl_label = "Auto-Snap 4 Gizma na Rub 3D Košare"
    bl_description = "Automatski pronalazi najviše točke (mjedene ušice) u 4 kuta 3D modela košare i postavlja GIZMO_Pin_01..04 na njih"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            return {"CANCELLED"}
        coords = auto_snap_4_gizmos_to_basket_rim(rig)
        self.report({"INFO"}, f"Auto-Snap postavio 4 gizma na rub košare: {coords}")
        return {"FINISHED"}


class AFDIR_OT_ToggleCliffCargoProp(bpy.types.Operator):
    bl_idname = "af_director.toggle_cliff_cargo"
    bl_label = "Uključi/Isključi ili Odaberi Paket Opreme u Košari"
    bl_description = "Prikazuje/skriva modularni paket opreme u košari i odabire ga za pomicanje (G/R/S)"
    bl_options = {"REGISTER", "UNDO"}

    cargo_key: StringProperty(default="af_cb_cargo_a_ice")

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            return {"CANCELLED"}
        c_obj = bpy.data.objects.get(rig.get(self.cargo_key, ""))
        if not c_obj:
            return {"CANCELLED"}

        if c_obj.hide_viewport:
            c_obj.hide_viewport = False
            c_obj.hide_render = False
            for o in list(context.selected_objects):
                o.select_set(False)
            c_obj.select_set(True)
            context.view_layer.objects.active = c_obj
            show_viewport_move_gizmo_arrows(True)
            self.report({"INFO"}, f"Prikazan i odabran paket u košari: {c_obj.name} (pomakni s G/R/S)")
        else:
            if context.active_object == c_obj:
                c_obj.hide_viewport = True
                c_obj.hide_render = True
                self.report({"INFO"}, f"Skriven paket: {c_obj.name}")
            else:
                for o in list(context.selected_objects):
                    o.select_set(False)
                c_obj.select_set(True)
                context.view_layer.objects.active = c_obj
                show_viewport_move_gizmo_arrows(True)
                self.report({"INFO"}, f"Odabran paket: {c_obj.name} (klikni još jednom za skrivanje)")
        return {"FINISHED"}


class AFDIR_OT_BakeCliffBasketPhysics(bpy.types.Operator):
    bl_idname = "af_director.bake_cliff_physics"
    bl_label = "Bake Fiziku Košare u Keyframeove (Graph Editor)"
    bl_description = "Zapisuje proceduralno spuštanje, odguravanje krampom i ljuljanje u standardne Blender F-krivulje za ručni fine-tuning u Graph Editoru"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            return {"CANCELLED"}
        bake_cliff_basket_physics_to_keyframes(rig)
        basket_body = bpy.data.objects.get(rig.get("af_cb_basket_body", ""))
        if basket_body:
            for o in list(context.selected_objects):
                o.select_set(False)
            basket_body.select_set(True)
            context.view_layer.objects.active = basket_body
        self.report({"INFO"}, f"Fizika košare ({rig.name}) zapisana u Keyframeove! Otvori Graph Editor za ručni fine-tuning.")
        return {"FINISHED"}


class AFDIR_OT_RevertCliffBasketProcedural(bpy.types.Operator):
    bl_idname = "af_director.revert_cliff_procedural"
    bl_label = "Vrati na Automatsku Proceduralnu Fiziku"
    bl_description = "Briše zapečene keyframeove košare i vraća živu proceduralnu fiziku povezanu s NLA sekvencom vilenjaka"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            return {"CANCELLED"}
        clear_baked_cliff_basket_keyframes(rig)
        self.report({"INFO"}, f"Košara ({rig.name}) vraćena na živu proceduralnu fiziku.")
        return {"FINISHED"}


class AFDIR_OT_ReloadTripoBasketModels(bpy.types.Operator):
    bl_idname = "af_director.reload_tripo_baskets"
    bl_label = "Učitaj / Osvježi Tripo 3D Modele Košara (.GLB)"
    bl_description = "Učitava sve 3D modele košara i tereta iz assets/models/glb/cliff_baskets/ i ažurira aktivne košare u sceni"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cnt = reload_all_tripo_basket_models_in_scene(context)
        self.report({"INFO"}, f"Osvježeni Tripo 3D modeli košara na {cnt} stanica.")
        return {"FINISHED"}


class AF_OT_SnapAllToGlacierWall(bpy.types.Operator):
    bl_idname = "af_cb.snap_all_to_glacier_wall"
    bl_label = "Priljubi Sve Skele, Pruge i Košare uz Ledeni Zid Sada"
    bl_description = (
        "Dinamički priljubljuje GN_Cliff_Mining_Scaffolding, sve krivulje skela (R1..R6), "
        "3D tračnice, vilenjake i viseće košare uz stvarnu površinu GEO_Spilja_Desni_Ledeni_Zid"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        standoff = float(getattr(scn, "af_s3_wall_standoff_m", 1.85))
        smoothing = int(getattr(scn, "af_s3_wall_smoothing", 4))
        auto_adapt = bool(getattr(scn, "af_s3_auto_adapt_wall", True))
        ensure_gn_cliff_mining_scaffolding_wall_snap(
            wall_standoff_m=standoff,
            smoothing_iterations=smoothing,
            auto_adapt=auto_adapt,
        )
        res = sync_scaffolding_and_rails_to_glacier_wall(
            context=context,
            wall_standoff_m=standoff,
            smoothing_window=max(1, smoothing),
        )
        self.report(
            {"INFO"},
            f"Priljubljeno uz ledeni zid (R2 X={res.get('r2_gallery_x', 0):.2f}m, "
            f"R3 X={res.get('r3_gallery_mean_x', 0):.2f}m, "
            f"{len(res.get('baskets_snapped', []))} košara).",
        )
        return {"FINISHED"}


class AF_OT_AddNullRopeStation(bpy.types.Operator):
    bl_idname = "af_cb.add_null_rope_station"
    bl_label = "+ Dodaj Gornju Null Točku Špage & Spusti Vilenjaka"
    bl_description = (
        "Stvara novu stanicu s gornjom Null točkom špage (GIZMO_TopWinch), "
        "automatski lijepi košaru i udarni zid uz GEO_Spilja_Desni_Ledeni_Zid i spušta vilenjaka s krampom"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        preset_id = getattr(scn, "af_cb_preset_enum", "BASKET_01_OCT_EMPTY")
        elf_id = (
            getattr(scn, "af_cb_spawn_elf_enum", None)
            or getattr(scn, "af_director_elf_enum", "ELF14")
            or "ELF14"
        )

        # Determine target (Y, Top_Z) from active object, 3D cursor, or next gallery bay
        cursor_loc = scn.cursor.location
        active_obj = context.active_object
        existing = get_all_cliff_basket_rigs(scn)
        if active_obj and not find_cliff_basket_rig(active_obj) and active_obj.name.startswith("CRV_S3_Skela"):
            y_pos = float(active_obj.location.y) if abs(active_obj.location.y) > 1.0 else 132.0 + len(existing) * 14.0
            top_z = max(5.2, float(active_obj.location.z) + 7.5)
        elif abs(cursor_loc.y) > 10.0:
            y_pos = float(cursor_loc.y)
            top_z = max(4.5, float(cursor_loc.z) if abs(cursor_loc.z) > 1.5 else 9.2)
        else:
            y_pos = 128.0 + len(existing) * 18.0
            top_z = 9.20

        max_drop = 12.0
        drop_alpha = 0.38
        drop_depth = drop_alpha * max_drop
        work_z = top_z - drop_depth

        wall_obj = bpy.data.objects.get("GEO_Spilja_Desni_Ledeni_Zid")
        wall_eval = wall_obj.evaluated_get(context.evaluated_depsgraph_get()) if wall_obj else None
        hit_x, norm_w = sample_glacier_wall_surface(wall_eval, y_pos, work_z)
        raw_yaw_deg = math.degrees(math.atan2(-norm_w.x, norm_w.y))
        rot_z_deg = max(72.0, min(108.0, raw_yaw_deg))
        wall_gap = 0.15
        basket_x = hit_x - (1.08 + wall_gap)

        rig = spawn_cliff_basket_station(
            context=context,
            preset_id=preset_id,
            elf_id=elf_id,
            location=(basket_x, y_pos, work_z),
            rotation_z_deg=rot_z_deg,
            winch_height_m=max(2.5, top_z - work_z),
            build_cliff_wall_preview=False,
            setup_demo_nla_sequence=True,
        )

        # Initialize animatable Top Anchor & Drop Alpha properties
        STATE["cb_prop_sync_guard"] = True
        try:
            rig.af_cb_top_anchor_z = float(top_z)
            rig.af_cb_max_drop_depth_m = float(max_drop)
            rig.af_cb_drop_alpha = float(drop_alpha)
            rig.af_cb_drop_depth_m = float(drop_depth)
            rig.af_cb_wall_gap_offset_m = float(wall_gap)
        finally:
            STATE["cb_prop_sync_guard"] = False

        snap_single_basket_to_glacier_wall(rig, wall_eval=wall_eval, wall_gap_m=wall_gap)
        sync_cliff_basket_ui_from_rig(rig)

        # Select GIZMO_TopWinch so user can immediately position the Top Null Anchor with G
        winch_giz = bpy.data.objects.get(rig.get("af_cb_winch_gizmo", ""))
        target = winch_giz or rig
        for o in list(context.selected_objects):
            o.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target
        show_viewport_move_gizmo_arrows(True)
        self.report(
            {"INFO"},
            f"Stvorena stanica {rig.name} s Gornjom Null Točkom ({target.name}) uz ledeni zid na X={hit_x:.2f}m, Y={y_pos:.1f}m!",
        )
        return {"FINISHED"}


class AF_OT_SnapActiveBasketToWall(bpy.types.Operator):
    bl_idname = "af_cb.snap_active_basket_to_wall"
    bl_label = "Priljubi Aktivnu Košaru i Gornju Null Točku uz Ledeni Zid"
    bl_description = "Postavlja aktivnu košaru, gornju Null točku špage i GIZMO_WallTarget točno uz površinu GEO_Spilja_Desni_Ledeni_Zid"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            self.report({"WARNING"}, "Nema aktivne košare u sceni.")
            return {"CANCELLED"}
        gap = float(getattr(rig, "af_cb_wall_gap_offset_m", rig.get("af_cb_wall_gap_offset_m", 0.15)))
        info = snap_single_basket_to_glacier_wall(rig, wall_gap_m=gap)
        if info:
            apply_basket_physics_to_rig(rig, float(context.scene.frame_current), scene=context.scene)
            self.report({"INFO"}, f"Košara {rig.name} i Gornja Null Točka priljubljene uz ledeni zid (X={rig.location.x:.2f}m).")
            return {"FINISHED"}
        self.report({"WARNING"}, "Površina ledenog zida nije pronađena.")
        return {"CANCELLED"}


class AF_OT_KeyframeDropAlpha(bpy.types.Operator):
    bl_idname = "af_cb.keyframe_drop_alpha"
    bl_label = "Keyframe Položaj Spuštanja Špage"
    bl_description = "Postavlja Drop Alpha (0.0 = Gornji položaj pod koloturom, 1.0 = Spušteni položaj) i zapisuje Keyframe na trenutnom frameu"
    bl_options = {"REGISTER", "UNDO"}

    target_alpha: FloatProperty(default=0.0, min=0.0, max=1.0)

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            self.report({"WARNING"}, "Nema aktivne košare.")
            return {"CANCELLED"}
        f_cur = int(context.scene.frame_current)
        rig.af_cb_drop_alpha = float(self.target_alpha)
        rig.keyframe_insert(data_path="af_cb_drop_alpha", frame=f_cur)
        rig.keyframe_insert(data_path="af_cb_drop_depth_m", frame=f_cur)
        apply_basket_physics_to_rig(rig, float(f_cur), scene=context.scene)
        self.report(
            {"INFO"},
            f"Zapisan Keyframe na frameu {f_cur}: Drop Alpha = {self.target_alpha:.2f} (Dubina = {rig.af_cb_drop_depth_m:.2f} m)",
        )
        return {"FINISHED"}


class AF_OT_SetupAutoDropRamp(bpy.types.Operator):
    bl_idname = "af_cb.setup_auto_drop_ramp"
    bl_label = "Postavi Automatsko Spuštanje (Start Frame -> Stop Frame)"
    bl_description = "Zapisuje keyframeove automatskog spuštanja špage od Start Frame (Alpha=0.0) do Stop Frame (trenutni/ciljani Alpha)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = get_active_cliff_basket_rig(context)
        if not rig:
            self.report({"WARNING"}, "Nema aktivne košare.")
            return {"CANCELLED"}
        scn = context.scene
        f0 = int(getattr(scn, "af_cb_lower_start_frame", rig.get("af_cb_lower_start_frame", 1)))
        f1 = int(getattr(scn, "af_cb_lower_stop_frame", rig.get("af_cb_lower_stop_frame", 48)))
        if f1 <= f0:
            f1 = f0 + 48

        target_alpha = float(getattr(rig, "af_cb_drop_alpha", 0.65))
        if target_alpha < 0.15:
            target_alpha = 0.65

        rig["af_cb_winch_mode"] = "LOWER_AND_STOP"
        rig["af_cb_lower_start_frame"] = f0
        rig["af_cb_lower_stop_frame"] = f1

        # Insert keyframes at f0 (top = 0.05) and f1 (lowered = target_alpha)
        rig.af_cb_drop_alpha = 0.05
        rig.keyframe_insert(data_path="af_cb_drop_alpha", frame=f0)
        rig.keyframe_insert(data_path="af_cb_drop_depth_m", frame=f0)

        rig.af_cb_drop_alpha = target_alpha
        rig.keyframe_insert(data_path="af_cb_drop_alpha", frame=f1)
        rig.keyframe_insert(data_path="af_cb_drop_depth_m", frame=f1)

        apply_basket_physics_to_rig(rig, float(scn.frame_current), scene=scn)
        self.report(
            {"INFO"},
            f"Automatsko spuštanje postavljeno na {rig.name}: Frame {f0} (Alpha=0.05) -> Frame {f1} (Alpha={target_alpha:.2f})",
        )
        return {"FINISHED"}


# ============================================================================
# N-PANEL (`VIEW3D_PT_ActionForgeCliffBaskets`)
# ============================================================================

class VIEW3D_PT_ActionForgeCliffBaskets(bpy.types.Panel):
    bl_label = "6. Košare na Zidu, 4 Gizma i Fizika Užeta"
    bl_idname = "VIEW3D_PT_af_cliff_baskets"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Elf Director"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        rigs = get_all_cliff_basket_rigs(scn)
        active_rig = get_active_cliff_basket_rig(context)

        box_top = layout.box()
        row_sp = box_top.row(align=True)
        row_sp.scale_y = 1.35
        row_sp.operator("af_director.spawn_cliff_basket", icon="ADD")
        row_sp.operator("af_director.reload_tripo_baskets", text="", icon="FILE_REFRESH")

        if not active_rig:
            box_top.label(text="Klikni '+ Nova Košara na Zidu' za postavljanje.", icon="INFO")
            return

        # List all Cliff Basket rigs in scene
        if len(rigs) > 1:
            col_rigs = box_top.column(align=True)
            for r in rigs:
                is_act = (r == active_rig)
                row_r = col_rigs.row(align=True)
                op_sel = row_r.operator(
                    "af_director.select_cliff_gizmo",
                    text=f"{r.name} ({r.get('af_cb_preset_id', '')})",
                    depress=is_act,
                    icon="RADIOBUT_ON" if is_act else "RADIOBUT_OFF",
                )
                op_sel.gizmo_key = "RIG_ROOT"

        box_top.prop(scn, "af_cb_preset_enum", text="3D Košara")

        # Modular Cargo Packages inside the basket
        box_cargo = layout.box()
        box_cargo.label(text="Modularni Teret u Košari (Klik = Prikaži & Pomakni G):", icon="PACKAGE")
        row_cg = box_cargo.row(align=True)
        row_cg.scale_y = 1.15
        for c_id, c_lbl_short in (
            ("af_cb_cargo_a_ice", "A: Plavi Led"),
            ("af_cb_cargo_b_tools", "B: Alat/Kramp"),
            ("af_cb_cargo_c_barrel", "C: Bačva/Lampa"),
        ):
            c_obj = bpy.data.objects.get(active_rig.get(c_id, ""))
            is_vis = bool(c_obj and not c_obj.hide_viewport)
            op_c = row_cg.operator(
                "af_director.toggle_cliff_cargo",
                text=c_lbl_short,
                depress=is_vis,
                icon="HIDE_OFF" if is_vis else "HIDE_ON",
            )
            op_c.cargo_key = c_id

        # 4 Interactive Rope Attachment Gizmos (`GIZMO_Pin_01..04`)
        box_giz = layout.box()
        box_giz.label(text="4 Gizma za Užad na Košari (Klikni -> Pomakni s G):", icon="GIZMO")

        active_obj = context.active_object
        col_pins = box_giz.column(align=True)
        row_p12 = col_pins.row(align=True)
        row_p12.scale_y = 1.25
        for g_key, g_txt in (
            ("af_cb_pin_01", "Pin 1: Prednji-D"),
            ("af_cb_pin_02", "Pin 2: Prednji-L"),
        ):
            g_obj = bpy.data.objects.get(active_rig.get(g_key, ""))
            op_g = row_p12.operator(
                "af_director.select_cliff_gizmo",
                text=g_txt,
                depress=(active_obj == g_obj and g_obj is not None),
                icon="PIVOT_INDIVIDUAL",
            )
            op_g.gizmo_key = g_key

        row_p34 = col_pins.row(align=True)
        row_p34.scale_y = 1.25
        for g_key, g_txt in (
            ("af_cb_pin_03", "Pin 3: Stražnji-L"),
            ("af_cb_pin_04", "Pin 4: Stražnji-D"),
        ):
            g_obj = bpy.data.objects.get(active_rig.get(g_key, ""))
            op_g = row_p34.operator(
                "af_director.select_cliff_gizmo",
                text=g_txt,
                depress=(active_obj == g_obj and g_obj is not None),
                icon="PIVOT_INDIVIDUAL",
            )
            op_g.gizmo_key = g_key

        row_sym = box_giz.row(align=True)
        row_sym.scale_y = 1.2
        row_sym.operator("af_director.mirror_cliff_pins", text="Zrcali Pin Simetrično (1->4)", icon="MOD_MIRROR")
        row_sym.operator("af_director.autosnap_cliff_pins", text="Auto-Snap na Rub", icon="SNAP_ON")

        row_top_g = box_giz.row(align=True)
        row_top_g.scale_y = 1.15
        for g_key, g_txt, g_ic in (
            ("af_cb_spreader_gizmo", "Sabirna Kuka", "HOOK"),
            ("af_cb_winch_gizmo", "Gornji Kolotur", "MOD_SCREW"),
            ("af_cb_wall_gizmo", "Udarni Zid", "FORCE_FORCE"),
        ):
            g_obj = bpy.data.objects.get(active_rig.get(g_key, ""))
            op_g = row_top_g.operator(
                "af_director.select_cliff_gizmo",
                text=g_txt,
                depress=(active_obj == g_obj and g_obj is not None),
                icon=g_ic,
            )
            op_g.gizmo_key = g_key

        row_rmode = box_giz.row(align=True)
        row_rmode.prop(scn, "af_cb_num_ropes", text="Broj Užadi")
        row_rmode.prop(scn, "af_cb_rope_mode", text="")
        box_giz.prop(scn, "af_cb_rope_slack_cm", text="Provjes Užadi (Slack cm)", slider=True)

        # Physics: Winch Lowering/Stopping & Pickaxe Wall-Strike Recoil
        box_phys = layout.box()
        is_proc = bool(active_rig.get("af_cb_use_procedural_physics", True))
        box_phys.label(
            text="Fizika: Spuštanje, Stajanje i Odguravanje Krampom:",
            icon="PHYSICS",
        )
        box_phys.prop(scn, "af_cb_winch_mode", text="Vitlo")
        if getattr(scn, "af_cb_winch_mode", "LOWER_AND_STOP") != "STATIONARY":
            row_z = box_phys.row(align=True)
            row_z.prop(scn, "af_cb_z_start", text="Z Početni (m)")
            row_z.prop(scn, "af_cb_z_work", text="Z Radni (m)")
            row_f = box_phys.row(align=True)
            row_f.prop(scn, "af_cb_lower_start_frame", text="Start Frame")
            row_f.prop(scn, "af_cb_lower_stop_frame", text="Stop Frame")
        else:
            box_phys.prop(scn, "af_cb_z_work", text="Radna Visina Košare Z (m)")

        col_rec = box_phys.column(align=True)
        col_rec.prop(scn, "af_cb_recoil_cm", text="Odguravanje od Zida pri Udarcu (cm)", slider=True)
        col_rec.prop(scn, "af_cb_tilt_kick_deg", text="Nagib Košare pri Udarcu (Tilt °)", slider=True)
        col_rec.prop(scn, "af_cb_damping", text="Prigušenje (Kad Stane -> Stoji Mirno)", slider=True)
        col_rec.prop(scn, "af_cb_wall_gap_cm", text="Odbojnik od Zida (Min Razmak cm)", slider=True)
        col_rec.prop(scn, "af_cb_wall_restitution", text="Elastičnost Odbojnika Zida", slider=True)
        col_rec.prop(scn, "af_cb_hit_frame_offset", text="Fino Podešavanje Trenutka Udara (±f)", slider=True)

        # Graph Editor Bake / Procedural Toggle
        box_bake = layout.box()
        box_bake.label(
            text="Stanje Fizike: " + ("Živa Proceduralna (Auto NLA)" if is_proc else "Zapečeni Keyframeovi (Graph Editor)"),
            icon="FCURVE",
        )
        row_bk = box_bake.row(align=True)
        row_bk.scale_y = 1.25
        row_bk.operator("af_director.bake_cliff_physics", text="Bake u Keyframeove (Fine-Tune)", icon="KEY_HLT")
        row_bk.operator("af_director.revert_cliff_procedural", text="Auto Fizika", icon="LOOP_BACK")


def _draw_scaffolding_and_rope_controller_ui(layout, context):
    scn = context.scene
    rigs = get_all_cliff_basket_rigs(scn)
    active_rig = get_active_cliff_basket_rig(context)

    # ========================================================================
    # SEKCIJA A — Dinamičko Priljubljivanje Skela uz Ledeni Zid
    # ========================================================================
    box_a = layout.box()
    box_a.label(
        text="A. Dinamičko Priljubljivanje Skela uz Ledeni Zid",
        icon="MOD_SHRINKWRAP",
    )
    wall_obj = bpy.data.objects.get("GEO_Spilja_Desni_Ledeni_Zid")
    if wall_obj:
        box_a.label(text="Zid: GEO_Spilja_Desni_Ledeni_Zid (Live Raycast +X)", icon="CHECKMARK")
    else:
        box_a.label(text="Zid: GEO_Spilja_Desni_Ledeni_Zid nije u sceni", icon="INFO")

    col_a = box_a.column(align=True)
    col_a.prop(scn, "af_s3_auto_adapt_wall", text="Auto-Adapt Skele uz Ledeni Zid (Live)", toggle=True)
    col_a.prop(scn, "af_s3_wall_standoff_m", text="Udaljenost Podnice od Zida (Standoff m)", slider=True)
    col_a.prop(scn, "af_s3_wall_smoothing", text="Zaglađivanje Konture (Smoothing)", slider=True)

    row_snap_all = box_a.row(align=True)
    row_snap_all.scale_y = 1.35
    row_snap_all.operator(
        "af_cb.snap_all_to_glacier_wall",
        text="Priljubi Sve Skele, Pruge i Košare uz Ledeni Zid Sada",
        icon="SNAP_ON",
    )

    # ========================================================================
    # SEKCIJA B — Gornje Null Točke Špage (Top Winch Null) & Košare s Vilenjacima
    # ========================================================================
    box_b = layout.box()
    box_b.label(
        text="B. Gornje Null Točke Špage (Top Winch Null) & Košare",
        icon="HOOK",
    )
    col_b_sel = box_b.column(align=True)
    col_b_sel.prop(scn, "af_cb_preset_enum", text="Košara")
    col_b_sel.prop(scn, "af_cb_spawn_elf_enum", text="Vilenjak")

    row_add_null = box_b.row(align=True)
    row_add_null.scale_y = 1.35
    row_add_null.operator(
        "af_cb.add_null_rope_station",
        text="+ Dodaj Gornju Null Točku Špage & Spusti Vilenjaka",
        icon="ADD",
    )

    row_snap_act = box_b.row(align=True)
    row_snap_act.scale_y = 1.25
    row_snap_act.operator(
        "af_cb.snap_active_basket_to_wall",
        text="Priljubi Aktivnu Košaru i Gornju Null Točku uz Ledeni Zid",
        icon="CON_SHRINKWRAP",
    )

    if rigs:
        col_rigs = box_b.column(align=True)
        col_rigs.label(text=f"Aktivne Stanice Košara u Sceni ({len(rigs)}):", icon="OUTLINER_OB_EMPTY")
        for r in rigs:
            is_act = (r == active_rig)
            row_r = col_rigs.row(align=True)
            op_sel = row_r.operator(
                "af_director.select_cliff_gizmo",
                text=f"{r.name} (Z={r.location.z:.1f}m | Drop={getattr(r, 'af_cb_drop_depth_m', 0.0):.1f}m)",
                depress=is_act,
                icon="RADIOBUT_ON" if is_act else "RADIOBUT_OFF",
            )
            op_sel.gizmo_key = "RIG_ROOT"
            op_winch = row_r.operator(
                "af_director.select_cliff_gizmo",
                text="Top Null",
                icon="MOD_SCREW",
            )
            op_winch.gizmo_key = "af_cb_winch_gizmo"

    if not active_rig:
        return

    # ========================================================================
    # SEKCIJA C — Animabilna Kontrola Spuštanja Špage (Keyframeable Drop Controls)
    # ========================================================================
    box_c = layout.box()
    box_c.use_property_split = True
    box_c.use_property_decorate = True
    box_c.label(
        text=f"C. Animabilno Spuštanje Špage ({active_rig.name} — Tipka I za Keyframe)",
        icon="KEYINGSET",
    )

    col_anim = box_c.column(align=True)
    col_anim.prop(active_rig, "af_cb_top_anchor_z", text="Visina Gornje Null Točke (Top Anchor Z)")
    col_anim.prop(active_rig, "af_cb_max_drop_depth_m", text="Maks. Dubina Spuštanja Špage (Max Drop m)")
    col_anim.prop(active_rig, "af_cb_drop_alpha", text="Klizač Spuštanja Košare (Drop Alpha 0.0 -> 1.0)", slider=True)
    col_anim.prop(active_rig, "af_cb_drop_depth_m", text="Trenutna Duljina Ispuštene Špage (Drop Depth m)", slider=True)
    col_anim.prop(active_rig, "af_cb_wall_gap_offset_m", text="Razmak Košare od Ledenog Zida (Wall Gap m)", slider=True)

    # Brzi gumbi za keyframeiranje
    box_kf = box_c.box()
    box_kf.use_property_split = False
    box_kf.label(text="Brzo Keyframeiranje Spuštanja (Dope Sheet / Graph Editor):", icon="KEY_HLT")
    row_kf1 = box_kf.row(align=True)
    row_kf1.scale_y = 1.25
    op_k0 = row_kf1.operator(
        "af_cb.keyframe_drop_alpha",
        text="Keyframe Gornji Položaj (Alpha = 0.0)",
        icon="TRIA_UP",
    )
    op_k0.target_alpha = 0.0
    op_k1 = row_kf1.operator(
        "af_cb.keyframe_drop_alpha",
        text="Keyframe Spušteni Položaj (Alpha = 1.0)",
        icon="TRIA_DOWN",
    )
    op_k1.target_alpha = 1.0

    row_auto_f = box_kf.row(align=True)
    row_auto_f.prop(scn, "af_cb_lower_start_frame", text="Start Frame")
    row_auto_f.prop(scn, "af_cb_lower_stop_frame", text="Stop Frame")

    row_kf2 = box_kf.row(align=True)
    row_kf2.scale_y = 1.25
    row_kf2.operator(
        "af_cb.setup_auto_drop_ramp",
        text="Postavi Automatsko Spuštanje (Start Frame -> Stop Frame)",
        icon="IPO_EASE_IN_OUT",
    )

    # Kontrole fizike užeta
    box_p = box_c.box()
    box_p.use_property_split = False
    box_p.label(text="Fizika Užeta, Provjes i Odguravanje Krampom:", icon="PHYSICS")
    row_rp = box_p.row(align=True)
    row_rp.prop(scn, "af_cb_num_ropes", text="Broj Užadi")
    row_rp.prop(scn, "af_cb_rope_slack_cm", text="Slack (cm)", slider=True)

    col_p = box_p.column(align=True)
    col_p.prop(scn, "af_cb_recoil_cm", text="Odguravanje pri Udarcu Krampom (Recoil cm)", slider=True)
    col_p.prop(scn, "af_cb_tilt_kick_deg", text="Nagib Košare (Tilt °)", slider=True)
    col_p.prop(scn, "af_cb_damping", text="Prigušenje (Damping)", slider=True)

    row_bk = box_p.row(align=True)
    row_bk.scale_y = 1.25
    row_bk.operator("af_director.bake_cliff_physics", text="Bake Fiziku u Keyframeove", icon="KEY_HLT")
    row_bk.operator("af_director.revert_cliff_procedural", text="Auto Fizika", icon="LOOP_BACK")


class AF_PT_Scaffolding_And_Rope_Controller(bpy.types.Panel):
    bl_label = "Skele & Špage Studio (Ledeni Zid & Null Košare)"
    bl_idname = "AF_PT_Scaffolding_And_Rope_Controller"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Elf Director"
    bl_order = 0

    def draw(self, context):
        _draw_scaffolding_and_rope_controller_ui(self.layout, context)


class AF_PT_Scaffolding_And_Rope_Controller_CavernTab(bpy.types.Panel):
    bl_label = "2. Skele & Špage Studio (Ledeni Zid & Null Košare)"
    bl_idname = "AF_PT_Scaffolding_And_Rope_Controller_CavernTab"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SV Cavern Studio"
    bl_order = 1

    def draw(self, context):
        _draw_scaffolding_and_rope_controller_ui(self.layout, context)


CB_CLASSES = (
    AFDIR_OT_SpawnCliffBasketStation,
    AFDIR_OT_SelectCliffBasketGizmo,
    AFDIR_OT_MirrorCliffPinGizmos,
    AFDIR_OT_AutoSnapCliffPinGizmos,
    AFDIR_OT_ToggleCliffCargoProp,
    AFDIR_OT_BakeCliffBasketPhysics,
    AFDIR_OT_RevertCliffBasketProcedural,
    AFDIR_OT_ReloadTripoBasketModels,
    AF_OT_SnapAllToGlacierWall,
    AF_OT_AddNullRopeStation,
    AF_OT_SnapActiveBasketToWall,
    AF_OT_KeyframeDropAlpha,
    AF_OT_SetupAutoDropRamp,
    AF_PT_Scaffolding_And_Rope_Controller,
    AF_PT_Scaffolding_And_Rope_Controller_CavernTab,
    VIEW3D_PT_ActionForgeCliffBaskets,
)


def register_cliff_baskets_ui():
    register_cliff_basket_object_properties()

    for cls in CB_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

    bpy.types.Scene.af_s3_auto_adapt_wall = BoolProperty(
        name="Auto-Adapt Skele uz Ledeni Zid (Live)",
        description="Dinamički priljubljuje GN_Cliff_Mining_Scaffolding, krivulje skela, pruge i košare uz GEO_Spilja_Desni_Ledeni_Zid",
        default=True,
        update=_on_s3_wall_snap_settings_changed,
    )
    bpy.types.Scene.af_s3_wall_standoff_m = FloatProperty(
        name="Udaljenost Podnice od Zida (Standoff m)",
        description="Udaljenost središta podnice skele od površine ledenog zida (default 1.85 m)",
        default=1.85,
        min=0.50,
        max=8.00,
        unit="LENGTH",
        update=_on_s3_wall_snap_settings_changed,
    )
    bpy.types.Scene.af_s3_wall_smoothing = IntProperty(
        name="Zaglađivanje Konture (Smoothing)",
        description="Broj iteracija zaglađivanja konture ledenog zida kako bi skela i pruga tekle glatko",
        default=4,
        min=0,
        max=16,
        update=_on_s3_wall_snap_settings_changed,
    )
    bpy.types.Scene.af_cb_spawn_elf_enum = EnumProperty(
        name="Vilenjak u Košari",
        items=[(e["id"], e["title"], e["title"]) for e in RIGGED_ELF_ROSTER],
        default="ELF14",
    )

    bpy.types.Scene.af_cb_preset_enum = EnumProperty(
        name="Model 3D Košare",
        items=[(p[0], p[1], p[1]) for p in CLIFF_BASKET_PRESETS],
        default="BASKET_01_OCT_EMPTY",
        update=on_cb_preset_changed,
    )
    bpy.types.Scene.af_cb_num_ropes = EnumProperty(
        name="Broj Užadi na Košari",
        items=[
            ("2", "2 Užeta (Dijagonalno / Bočno)", "Spaja Pin 1 i Pin 3"),
            ("3", "3 Užeta (Trokut)", "Spaja Pin 1, Pin 2 i Pin 3"),
            ("4", "4 Užeta (Sva 4 Kuta)", "Spaja sva 4 gizma GIZMO_Pin_01..04"),
        ],
        default="4",
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_rope_mode = EnumProperty(
        name="Način Vješanja Užadi",
        items=[
            ("SPREADER_4_TO_1", "Sabirna Kuka (4 -> 1 -> Kolotur)", "4 užeta s košare idu u sabirnu kuku iznad glave vilenjaka pa na kolotur"),
            ("PARALLEL", "Paralelna Užad (4 -> Greda)", "Svaki pin ide ravno gore u gredu vitla"),
        ],
        default="SPREADER_4_TO_1",
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_rope_slack_cm = FloatProperty(
        name="Provjes Užadi (cm)",
        default=3.5,
        min=0.0,
        max=25.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_winch_mode = EnumProperty(
        name="Način Rada Vitla",
        items=[
            ("LOWER_AND_STOP", "Spusti Košaru i Stani na Mjestu", "Košara se spušta od Start Frame do Stop Frame, zanjiha se pri kočenju i stane"),
            ("STATIONARY", "Stacionarno na Radnoj Visini", "Košara cijelo vrijeme visi na radnoj visini Z"),
            ("RAISE_AND_STOP", "Podigni Košaru i Stani", "Košara se podiže i staje"),
        ],
        default="LOWER_AND_STOP",
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_z_start = FloatProperty(
        name="Početna Visina Spuštanja Z (m)",
        default=1.85,
        min=-10.0,
        max=15.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_z_work = FloatProperty(
        name="Radna Visina Košare Z (m)",
        default=0.00,
        min=-10.0,
        max=15.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_lower_start_frame = IntProperty(
        name="Frame Početka Spuštanja",
        default=1,
        min=1,
        max=2000,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_lower_stop_frame = IntProperty(
        name="Frame Zaustavljanja Spuštanja",
        default=48,
        min=2,
        max=2000,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_recoil_cm = FloatProperty(
        name="Odguravanje od Zida pri Udarcu Krampom (cm)",
        default=15.0,
        min=0.0,
        max=65.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_tilt_kick_deg = FloatProperty(
        name="Nagib Košare pri Udarcu (Tilt °)",
        default=7.8,
        min=0.0,
        max=28.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_damping = FloatProperty(
        name="Prigušenje Ljuljanja (Damping)",
        default=1.55,
        min=0.25,
        max=5.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_wall_gap_cm = FloatProperty(
        name="Minimalni Razmak Odbojnika od Zida (cm)",
        default=5.0,
        min=0.0,
        max=40.0,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_wall_restitution = FloatProperty(
        name="Elastičnost Odbojnika od Zida",
        default=0.30,
        min=0.0,
        max=0.90,
        update=on_cb_physics_param_changed,
    )
    bpy.types.Scene.af_cb_hit_frame_offset = IntProperty(
        name="Fino Podešavanje Trenutka Udara Krampa (±f)",
        default=0,
        min=-30,
        max=30,
        update=on_cb_physics_param_changed,
    )

    register_cliff_basket_handlers()


def unregister_cliff_baskets_ui():
    unregister_cliff_basket_handlers()
    for cls in reversed(CB_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
