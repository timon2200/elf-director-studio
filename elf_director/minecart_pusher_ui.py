# -*- coding: utf-8 -*-
"""
N-Panel UI, Operators & Reactive Property Callbacks for Section 7:
`7. Vilenjak Gura Minecart po Krivulji / Tračnicama` (`elf_director.minecart_pusher_ui`).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

from .constants import STATE
from .minecart_pusher import (
    MINECART_VARIANTS,
    attach_minecart_to_elf,
    build_or_update_3d_rails_for_curve,
    get_elf_minecart_prop,
    register_minecart_pusher_handlers,
    remove_minecart_from_elf,
    set_curve_3d_rails_enabled,
    set_elf_minecart_variant,
    spawn_elf_pushing_minecart_on_rail_curve,
    unregister_minecart_pusher_handlers,
    update_minecart_curve_steering_for_controller,
)
from .nla_sequencer import apply_additive_pose_offset
from .rig_actors import (
    enable_viewport_transform_gizmos,
    find_character_controller,
    get_active_character_controller,
)


def sync_minecart_ui_from_controller(ctrl_obj: bpy.types.Object):
    if not ctrl_obj or STATE.get("mc_ui_sync_guard", False):
        return
    scn = getattr(bpy.context, "scene", None)
    if not scn:
        return

    STATE["mc_ui_sync_guard"] = True
    try:
        variant = ctrl_obj.get("af_mc_variant", "FULL")
        scn.af_mc_variant_enum = variant if variant in ("EMPTY", "FULL") else "FULL"
        scn.af_mc_show_cargo = bool(ctrl_obj.get("af_mc_show_cargo", variant == "FULL"))
        scn.af_mc_distance_m = float(ctrl_obj.get("af_mc_distance_m", 0.88))
        scn.af_mc_grip_pitch_deg = float(ctrl_obj.get("af_mc_grip_pitch_deg", 0.0))

        crv_name = ctrl_obj.get("af_attached_curve", "")
        crv_obj = bpy.data.objects.get(crv_name) if crv_name else None
        if crv_obj:
            scn.af_mc_rails_enabled = bool(crv_obj.get("af_mc_rails_enabled", True))
    except Exception:
        pass
    finally:
        STATE["mc_ui_sync_guard"] = False


def on_mc_variant_changed(self, context):
    if STATE.get("mc_ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    set_elf_minecart_variant(ctrl, self.af_mc_variant_enum)
    sync_minecart_ui_from_controller(ctrl)


def on_mc_show_cargo_changed(self, context):
    if STATE.get("mc_ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    new_var = "FULL" if bool(self.af_mc_show_cargo) else "EMPTY"
    set_elf_minecart_variant(ctrl, new_var)
    sync_minecart_ui_from_controller(ctrl)


def on_mc_distance_changed(self, context):
    if STATE.get("mc_ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    dist = float(self.af_mc_distance_m)
    ctrl["af_mc_distance_m"] = dist
    prop_root = get_elf_minecart_prop(ctrl)
    if prop_root:
        update_minecart_curve_steering_for_controller(ctrl, scene=context.scene)


def on_mc_grip_pitch_changed(self, context):
    if STATE.get("mc_ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    if not ctrl:
        return
    deg = float(self.af_mc_grip_pitch_deg)
    ctrl["af_mc_grip_pitch_deg"] = deg
    apply_additive_pose_offset(
        ctrl,
        torso_bend_deg=deg * 0.45,
        arms_raise_deg=deg * 0.85,
    )


def on_mc_rails_enabled_changed(self, context):
    if STATE.get("mc_ui_sync_guard", False):
        return
    ctrl = get_active_character_controller(context)
    crv_obj = None
    if ctrl and ctrl.get("af_attached_curve"):
        crv_obj = bpy.data.objects.get(ctrl.get("af_attached_curve"))
    elif context.active_object and context.active_object.type == "CURVE":
        crv_obj = context.active_object
    if crv_obj:
        set_curve_3d_rails_enabled(crv_obj, enabled=bool(self.af_mc_rails_enabled))


# ============================================================================
# OPERATORS
# ============================================================================

class AFDIR_OT_SpawnElfMinecartOnRails(bpy.types.Operator):
    bl_idname = "af_director.spawn_minecart_pusher"
    bl_label = "+ Stvori Vilenjaka koji Gura Minecart na Novoj Tračnici"
    bl_description = "Stvara vilenjaka s animacijom AF_34_Walk_Push_Minecart, prilaže 3D Minecart (Prazni ili Puni), gradi 3-točkovnu krivulju s 3D tračnicama i povezuje ih bez klizanja stopala"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        elf_id = getattr(scn, "af_director_elf_enum", "ELF06") or "ELF06"
        variant = getattr(scn, "af_mc_variant_enum", "FULL") or "FULL"
        dist = float(getattr(scn, "af_mc_distance_m", 0.88))

        # Check how many rail curves already exist
        existing_curves = [o for o in bpy.data.objects if o.type == "CURVE" and o.name.startswith("Elf_Minecart_Rail_Path_")]
        idx = len(existing_curves) + 1
        y_off = -3.4 - (idx - 1) * 2.2
        pts = [
            (-6.2, y_off, 0.0),
            (0.0, y_off + 1.8, 0.0),
            (6.2, y_off, 0.0),
        ]
        ctrl, prop_root, curve_obj, track_obj = spawn_elf_pushing_minecart_on_rail_curve(
            context=context,
            elf_id=elf_id,
            variant=variant,
            curve_points=pts,
            curve_name=f"Elf_Minecart_Rail_Path_{idx:02d}",
            start_pct=15.0,
            distance_m=dist,
        )
        bpy.ops.object.select_all(action="DESELECT")
        ctrl.select_set(True)
        context.view_layer.objects.active = ctrl
        enable_viewport_transform_gizmos()
        sync_minecart_ui_from_controller(ctrl)
        self.report(
            {"INFO"},
            f"Stvoren '{ctrl.name}' koji gura Minecart ({variant}) po 3D tračnici '{curve_obj.name}'!",
        )
        return {"FINISHED"}


class AFDIR_OT_AttachOrSetMinecartVariant(bpy.types.Operator):
    bl_idname = "af_director.set_minecart_variant"
    bl_label = "Postavi Prazni ili Puni Minecart na Odabranog Vilenjaka"
    bl_description = "Prilaže Minecart odabranom vilenjaku (ili prebacuje između Praznog i Punog Minecarta s košarom i plavim ledom) te postavlja animaciju guranja AF_34_Walk_Push_Minecart"
    bl_options = {"REGISTER", "UNDO"}

    variant: StringProperty(default="FULL")

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            self.report({"WARNING"}, "Prvo odaberi vilenjaka u sceni.")
            return {"CANCELLED"}

        prop_root = get_elf_minecart_prop(ctrl)
        if not prop_root:
            prop_root = attach_minecart_to_elf(
                context,
                ctrl_obj=ctrl,
                variant=self.variant,
                distance_m=float(getattr(context.scene, "af_mc_distance_m", 0.88)),
                build_rails_on_attached_curve=True,
                switch_to_push_walk_action=True,
            )
        else:
            set_elf_minecart_variant(ctrl, self.variant)
            crv_name = ctrl.get("af_attached_curve", "")
            crv_obj = bpy.data.objects.get(crv_name) if crv_name else None
            if crv_obj and bool(getattr(context.scene, "af_mc_rails_enabled", True)):
                set_curve_3d_rails_enabled(crv_obj, enabled=True)
            update_minecart_curve_steering_for_controller(ctrl, scene=context.scene)

        sync_minecart_ui_from_controller(ctrl)
        lbl = "Puni Minecart (s Košarom + Ledom)" if self.variant == "FULL" else "Prazni Minecart"
        self.report({"INFO"}, f"Postavljen {lbl} na '{ctrl.name}'.")
        return {"FINISHED"}


class AFDIR_OT_RebuildCurve3DRails(bpy.types.Operator):
    bl_idname = "af_director.rebuild_curve_3d_rails"
    bl_label = "Izgradi / Osvježi 3D Tračnice na Krivulji"
    bl_description = "Gradi ili osvježava 3D drvene pragove i željezne tračnice (RAIL_Track_*) točno po nacrtanoj krivulji"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.active_object
        crv_obj = active if (active and active.type == "CURVE") else None
        if active and active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        ctrl = get_active_character_controller(context)
        if not crv_obj and ctrl and ctrl.get("af_attached_curve"):
            crv_obj = bpy.data.objects.get(ctrl.get("af_attached_curve"))

        if not crv_obj:
            self.report({"WARNING"}, "Odaberi vilenjaka na krivulji ili samu krivulju.")
            return {"CANCELLED"}

        track_obj = set_curve_3d_rails_enabled(crv_obj, enabled=True)
        if ctrl:
            update_minecart_curve_steering_for_controller(ctrl, scene=context.scene)
            sync_minecart_ui_from_controller(ctrl)
        self.report({"INFO"}, f"Izgrađene 3D tračnice i pragovi: '{track_obj.name if track_obj else crv_obj.name}'.")
        return {"FINISHED"}


class AFDIR_OT_SelectMinecartProp(bpy.types.Operator):
    bl_idname = "af_director.select_minecart_prop"
    bl_label = "Odaberi Minecart Prop (G/R/S)"
    bl_description = "Odabire 3D Minecart ispred vilenjaka za ručno pomicanje/rotaciju (G/R/S)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        prop_root = get_elf_minecart_prop(ctrl)
        if not prop_root:
            self.report({"WARNING"}, "Odabrani vilenjak nema priložen Minecart.")
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        STATE["selection_redirect_guard"] = True
        try:
            bpy.ops.object.select_all(action="DESELECT")
            prop_root.select_set(True)
            context.view_layer.objects.active = prop_root
            enable_viewport_transform_gizmos()
        finally:
            STATE["selection_redirect_guard"] = False
        self.report({"INFO"}, f"Odabran '{prop_root.name}' (koristi G/R/S ili klizač udaljenosti).")
        return {"FINISHED"}


class AFDIR_OT_RemoveMinecartFromElf(bpy.types.Operator):
    bl_idname = "af_director.remove_minecart"
    bl_label = "Ukloni Minecart s Vilenjaka"
    bl_description = "Uklanja 3D Minecart s odabranog vilenjaka"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ctrl = get_active_character_controller(context)
        if not ctrl:
            return {"CANCELLED"}
        remove_minecart_from_elf(ctrl)
        self.report({"INFO"}, f"Uklonjen Minecart s '{ctrl.name}'.")
        return {"FINISHED"}


# ============================================================================
# N-PANEL (`VIEW3D_PT_ActionForgeMinecartPusher`)
# ============================================================================

class VIEW3D_PT_ActionForgeMinecartPusher(bpy.types.Panel):
    bl_label = "7. Vilenjak Gura Minecart po Krivulji / Tračnicama"
    bl_idname = "VIEW3D_PT_af_minecart_pusher"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Elf Director"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        ctrl = get_active_character_controller(context)

        box_spawn = layout.box()
        row_sp = box_spawn.row(align=True)
        row_sp.scale_y = 1.35
        row_sp.operator(
            "af_director.spawn_minecart_pusher",
            text="+ Stvori Vilenjaka koji Gura Minecart na Novoj Tračnici",
            icon="AUTO",
        )

        if not ctrl:
            box_spawn.label(text="Odaberi vilenjaka ili klikni gumb iznad.", icon="INFO")
            return

        has_mc = bool(ctrl.get("af_mc_attached", False) and get_elf_minecart_prop(ctrl))
        cur_var = ctrl.get("af_mc_variant", "FULL") if has_mc else getattr(scn, "af_mc_variant_enum", "FULL")

        box_var = layout.box()
        box_var.label(
            text=f"1-Klik Odabir Minecarta za: {ctrl.name}" + (f" [{cur_var}]" if has_mc else " [Nije priložen]"),
            icon="MESH_CUBE",
        )
        row_btns = box_var.row(align=True)
        row_btns.scale_y = 1.30
        op_emp = row_btns.operator(
            "af_director.set_minecart_variant",
            text="Prazni Minecart",
            depress=(has_mc and cur_var == "EMPTY"),
            icon="MESH_PLANE",
        )
        op_emp.variant = "EMPTY"

        op_ful = row_btns.operator(
            "af_director.set_minecart_variant",
            text="Puni Minecart (s Punom Košarom + Ledom)",
            depress=(has_mc and cur_var == "FULL"),
            icon="PACKAGE",
        )
        op_ful.variant = "FULL"

        row_tog = box_var.row(align=True)
        row_tog.prop(
            scn,
            "af_mc_show_cargo",
            text="Prikaži Punu Košaru / Led Unutra",
            toggle=True,
            icon="HIDE_OFF" if getattr(scn, "af_mc_show_cargo", True) else "HIDE_ON",
        )
        if has_mc:
            row_tog.operator("af_director.select_minecart_prop", text="G/R/S", icon="GIZMO")
            row_tog.operator("af_director.remove_minecart", text="", icon="X")

        # Fine-tuning & 3D Rails on Curve
        box_tune = layout.box()
        box_tune.label(text="Fino Podešavanje Hvatanja i 3D Tračnica na Krivulji:", icon="CURVE_PATH")
        col_t = box_tune.column(align=True)
        col_t.prop(scn, "af_mc_distance_m", text="Udaljenost Minecarta Ispred Vilenjaka (m)", slider=True)
        col_t.prop(scn, "af_mc_grip_pitch_deg", text="Visina Hvatanja Ruku / Nagib Trupa (°)", slider=True)

        row_rail = box_tune.row(align=True)
        row_rail.scale_y = 1.2
        row_rail.prop(
            scn,
            "af_mc_rails_enabled",
            text="3D Tračnice na Krivulji (On/Off)",
            toggle=True,
            icon="MOD_BUILD",
        )
        row_rail.operator("af_director.rebuild_curve_3d_rails", text="Osvježi Tračnice", icon="FILE_REFRESH")


MC_CLASSES = (
    AFDIR_OT_SpawnElfMinecartOnRails,
    AFDIR_OT_AttachOrSetMinecartVariant,
    AFDIR_OT_RebuildCurve3DRails,
    AFDIR_OT_SelectMinecartProp,
    AFDIR_OT_RemoveMinecartFromElf,
    VIEW3D_PT_ActionForgeMinecartPusher,
)


def register_minecart_pusher_ui():
    for cls in MC_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

    bpy.types.Scene.af_mc_variant_enum = EnumProperty(
        name="Varijanta Minecarta",
        items=[(v[0], v[1], v[2]) for v in MINECART_VARIANTS],
        default="FULL",
        update=on_mc_variant_changed,
    )
    bpy.types.Scene.af_mc_show_cargo = BoolProperty(
        name="Prikaži Punu Košaru / Led Unutra",
        default=True,
        update=on_mc_show_cargo_changed,
    )
    bpy.types.Scene.af_mc_distance_m = FloatProperty(
        name="Udaljenost Minecarta Ispred Vilenjaka (m)",
        default=0.88,
        min=0.55,
        max=1.60,
        update=on_mc_distance_changed,
    )
    bpy.types.Scene.af_mc_grip_pitch_deg = FloatProperty(
        name="Visina Hvatanja Ruku / Nagib Trupa (°)",
        default=0.0,
        min=-25.0,
        max=25.0,
        update=on_mc_grip_pitch_changed,
    )
    bpy.types.Scene.af_mc_rails_enabled = BoolProperty(
        name="3D Tračnice na Krivulji (On/Off)",
        default=True,
        update=on_mc_rails_enabled_changed,
    )

    register_minecart_pusher_handlers()


def unregister_minecart_pusher_ui():
    unregister_minecart_pusher_handlers()
    for cls in reversed(MC_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
