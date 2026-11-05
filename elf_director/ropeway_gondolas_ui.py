# -*- coding: utf-8 -*-
"""
Aerial Ropeway / Ski-Lift Gondola System N-Panel UI (`elf_director.ropeway_gondolas_ui`)
========================================================================================
Interactive Blender N-Panel controller (`View3D > Sidebar > Elf Director > 7. Žičare, Gondole i Koloture`)
for managing underground aerial ropeways, interactive pylon Null points, dynamic catenary sag &
moving gondola point-load deflection, pulley sheave batteries (`koloture`), and individual
Cargo/Passenger gondolas with blue ice crystals and Elf passengers.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)

from .constants import RIGGED_ELF_ROSTER
from .ropeway_gondolas import (
    GONDOLA_CARGO_CONTENT_TYPES,
    GONDOLA_VARIATIONS,
    ROPEWAY_DISTRIBUTION_MODES,
    TOWER_SUPPORT_MODES,
    add_null_point_to_ropeway_system,
    apply_ropeway_evaluation_to_system,
    auto_fit_null_tower_height_to_ground,
    delete_ropeway_system,
    find_ropeway_system_from_object,
    get_active_gondola_object,
    get_active_null_point_object,
    get_active_ropeway_system,
    get_all_ropeway_systems,
    get_null_support_mode,
    get_null_tower_height_m,
    get_system_gondola_objects,
    get_system_null_point_objects,
    populate_cavern_multi_ropeway_network,
    rebuild_all_pylons_for_system,
    register_ropeway_gondola_handlers,
    reload_all_tripo_gondola_models_in_scene,
    remove_null_point_from_ropeway_system,
    set_individual_gondola_configuration,
    set_null_tower_height_m,
    show_viewport_move_gizmo_arrows,
    spawn_ropeway_system,
    sync_ropeway_gondola_fleet,
    unregister_ropeway_gondola_handlers,
)

_UI_SYNC_GUARD = False
_SUPPORT_MODE_TO_IDX = {m[0]: i for i, m in enumerate(TOWER_SUPPORT_MODES)}
_IDX_TO_SUPPORT_MODE = {i: m[0] for i, m in enumerate(TOWER_SUPPORT_MODES)}


def _get_null_obj_tower_height(self) -> float:
    sys_root = find_ropeway_system_from_object(self)
    return float(get_null_tower_height_m(sys_root, self))


def _set_null_obj_tower_height(self, value: float):
    h = max(0.5, min(200.0, float(value)))
    set_null_tower_height_m(self, height_m=h)
    sys_root = find_ropeway_system_from_object(self)
    if sys_root:
        sys_root["af_rw_tower_height_m"] = h


def _get_null_obj_support_mode(self) -> int:
    sys_root = find_ropeway_system_from_object(self)
    mode = get_null_support_mode(sys_root, self)
    return _SUPPORT_MODE_TO_IDX.get(mode, 0)


def _set_null_obj_support_mode(self, value: int):
    mode = _IDX_TO_SUPPORT_MODE.get(int(value), "PYLON_TOWER")
    set_null_tower_height_m(self, support_mode=mode)


def _get_elf_enum_items(self, context):
    items = [("NONE", "Bez Vilenjaka (Samo Teret / Prazna)", "Gondola vozi bez vilenjaka")]
    for e in RIGGED_ELF_ROSTER:
        lbl = e.get("title") or e.get("label") or e["id"]
        items.append((e["id"], lbl, lbl))
    return items


def _get_variation_enum_items(self, context):
    return [(v[0], v[1], v[1]) for v in GONDOLA_VARIATIONS]


def _get_cargo_enum_items(self, context):
    return [(c[0], c[1], c[1]) for c in GONDOLA_CARGO_CONTENT_TYPES]


def sync_ropeway_ui_from_active_system(scene, sys_root=None, gondola_obj=None):
    global _UI_SYNC_GUARD
    if not scene:
        return
    if sys_root is None:
        sys_root = get_active_ropeway_system()
    if not sys_root:
        return

    _UI_SYNC_GUARD = True
    try:
        scene.af_rw_ui_gondola_count = int(sys_root.get("af_rw_gondola_count", 12))
        scene.af_rw_ui_distribution_mode = sys_root.get("af_rw_distribution_mode", "MIXED_75_CARGO_25_ELF")
        scene.af_rw_ui_base_sag_m = float(sys_root.get("af_rw_base_sag_m", 1.45))
        scene.af_rw_ui_load_sink_m = float(sys_root.get("af_rw_load_sink_m", 0.95))
        scene.af_rw_ui_speed_mps = float(sys_root.get("af_rw_speed_mps", 2.40))
        scene.af_rw_ui_sway_amp_deg = float(sys_root.get("af_rw_sway_amp_deg", 4.5))
        scene.af_rw_ui_loop_gauge_m = float(sys_root.get("af_rw_loop_gauge_m", 3.40))
        scene.af_rw_ui_pulley_scale = float(sys_root.get("af_rw_pulley_scale", 1.0))
        scene.af_rw_ui_rollers_per_side = int(sys_root.get("af_rw_rollers_per_side", 4))
        scene.af_rw_ui_show_turnaround = bool(sys_root.get("af_rw_show_turnaround_wheels", True))
        scene.af_rw_ui_tower_support_mode = sys_root.get("af_rw_tower_support_mode", "PYLON_TOWER")
        scene.af_rw_ui_tower_height_m = float(sys_root.get("af_rw_tower_height_m", 14.0))
        scene.af_rw_ui_auto_height_from_base_z = bool(sys_root.get("af_rw_auto_height_from_base_z", False))
        scene.af_rw_ui_low_poly_mode = bool(sys_root.get("af_rw_low_poly_mode", False))

        if gondola_obj is None:
            gondola_obj = get_active_gondola_object(sys_root=sys_root)
        if gondola_obj:
            scene.af_rw_slot_variation = gondola_obj.get("af_rw_gondola_variant", "GONDOLA_CARGO")
            scene.af_rw_slot_cargo = gondola_obj.get("af_rw_cargo_type", "ICE_CRYSTALS")
            scene.af_rw_slot_elf_id = gondola_obj.get("af_rw_elf_id", "NONE")
            scene.af_rw_slot_weight_factor = float(gondola_obj.get("af_rw_weight_factor", 1.25))
            scene.af_rw_slot_scale = float(gondola_obj.get("af_rw_scale", 1.0))
    finally:
        _UI_SYNC_GUARD = False


# ============================================================================
# 1. REACTIVE PROPERTY UPDATE CALLBACKS
# ============================================================================

def _on_rw_physics_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    sys_root["af_rw_base_sag_m"] = float(self.af_rw_ui_base_sag_m)
    sys_root["af_rw_load_sink_m"] = float(self.af_rw_ui_load_sink_m)
    sys_root["af_rw_speed_mps"] = float(self.af_rw_ui_speed_mps)
    sys_root["af_rw_sway_amp_deg"] = float(self.af_rw_ui_sway_amp_deg)
    sys_root["af_rw_pulley_scale"] = float(self.af_rw_ui_pulley_scale)
    sys_root["af_rw_show_turnaround_wheels"] = bool(self.af_rw_ui_show_turnaround)
    apply_ropeway_evaluation_to_system(sys_root, scene=context.scene)


def _on_rw_pylon_geometry_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    sys_root["af_rw_loop_gauge_m"] = float(self.af_rw_ui_loop_gauge_m)
    sys_root["af_rw_rollers_per_side"] = int(self.af_rw_ui_rollers_per_side)
    rebuild_all_pylons_for_system(sys_root)


def _on_rw_system_tower_height_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    h = max(0.5, min(200.0, float(self.af_rw_ui_tower_height_m)))
    sys_root["af_rw_tower_height_m"] = h
    for n_obj in get_system_null_point_objects(sys_root):
        n_obj["af_rw_null_tower_height_m"] = h
        n_obj["af_rw_null_base_z"] = float(n_obj.location.z) - h
    rebuild_all_pylons_for_system(sys_root)


def _on_rw_system_support_mode_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    mode = self.af_rw_ui_tower_support_mode
    sys_root["af_rw_tower_support_mode"] = mode
    for n_obj in get_system_null_point_objects(sys_root):
        n_obj["af_rw_null_support_mode"] = mode
    rebuild_all_pylons_for_system(sys_root)


def _on_rw_auto_height_mode_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    enabled = bool(self.af_rw_ui_auto_height_from_base_z)
    sys_root["af_rw_auto_height_from_base_z"] = enabled
    if enabled:
        for n_obj in get_system_null_point_objects(sys_root):
            h = get_null_tower_height_m(sys_root, n_obj)
            n_obj["af_rw_null_base_z"] = float(n_obj.location.z) - h


def _on_rw_fleet_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    sys_root["af_rw_gondola_count"] = int(self.af_rw_ui_gondola_count)
    sys_root["af_rw_distribution_mode"] = self.af_rw_ui_distribution_mode
    sync_ropeway_gondola_fleet(
        sys_root,
        target_count=int(self.af_rw_ui_gondola_count),
        distribution_mode=self.af_rw_ui_distribution_mode,
        spawn_elves_in_passenger=True,
    )
    apply_ropeway_evaluation_to_system(sys_root, scene=context.scene)
    sync_ropeway_ui_from_active_system(context.scene, sys_root=sys_root)


def _on_rw_low_poly_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    if not sys_root:
        return
    sys_root["af_rw_low_poly_mode"] = bool(self.af_rw_ui_low_poly_mode)
    reload_all_tripo_gondola_models_in_scene(context)


def _on_rw_individual_gondola_changed(self, context):
    if _UI_SYNC_GUARD:
        return
    sys_root = get_active_ropeway_system(context)
    g_obj = get_active_gondola_object(context, sys_root=sys_root)
    if not g_obj:
        return
    if sys_root:
        sys_root["af_rw_distribution_mode"] = "CUSTOM"
    set_individual_gondola_configuration(
        g_obj,
        variant_id=self.af_rw_slot_variation,
        cargo_type=self.af_rw_slot_cargo,
        elf_id=self.af_rw_slot_elf_id,
        weight_factor=float(self.af_rw_slot_weight_factor),
        scale=float(self.af_rw_slot_scale),
    )
    if sys_root:
        apply_ropeway_evaluation_to_system(sys_root, scene=context.scene)


# ============================================================================
# 2. OPERATORS
# ============================================================================

class AFDIR_OT_SpawnRopewaySystem(bpy.types.Operator):
    bl_idname = "af_director.spawn_ropeway_system"
    bl_label = "+ Dodaj Novi Sustav Žičare"
    bl_description = (
        "Kreiraj novi kružni sustav podzemne žičare s interaktivnim Null točkama stupova, "
        "koloturama, dinamičkim provjesom žice i gondolama (od Ledenog zida prema gradu)"
    )
    bl_options = {"REGISTER", "UNDO"}

    preset_mode: StringProperty(default="GLACIER_TO_CITY")

    def execute(self, context):
        all_sys = get_all_ropeway_systems(context.scene)
        next_idx = len(all_sys) + 1
        y_shift = ((next_idx - 1) % 5) * 68.0
        z_shift = ((next_idx - 1) % 3) * 5.0

        if self.preset_mode == "CURSOR":
            c = context.scene.cursor.location
            pts = [
                (c.x + 14.0, c.y - 18.0, c.z + 8.0),
                (c.x - 4.0,  c.y + 4.0,  c.z + 11.0),
                (c.x - 28.0, c.y + 28.0, c.z + 14.0),
                (c.x - 56.0, c.y + 55.0, c.z + 17.0),
            ]
        else:
            pts = [
                ( 14.0, 118.0 + y_shift, 13.0 + z_shift),
                ( -8.5, 148.0 + y_shift, 16.0 + z_shift),
                (-38.0, 182.0 + y_shift, 19.5 + z_shift),
                (-78.0, 220.0 + y_shift, 23.0 + z_shift),
            ]

        sys_root = spawn_ropeway_system(
            context=context,
            null_points=pts,
            label=f"Žičara {next_idx:02d} (Ledeni Zid -> Prema Gradu Lijevo)",
            gondola_count=12,
            loop_gauge_m=3.40,
            speed_mps=2.45,
            base_sag_m=1.40,
            load_sink_m=0.95,
            tower_support_mode="PYLON_TOWER",
            tower_height_m=15.0,
            distribution_mode="MIXED_75_CARGO_25_ELF",
            spawn_elves_in_passenger=True,
        )
        sync_ropeway_ui_from_active_system(context.scene, sys_root=sys_root)
        nulls = get_system_null_point_objects(sys_root)
        target_sel = nulls[0] if nulls else sys_root
        try:
            bpy.ops.object.select_all(action="DESELECT")
            target_sel.select_set(True)
            context.view_layer.objects.active = target_sel
            show_viewport_move_gizmo_arrows(True)
        except Exception:
            pass

        self.report({"INFO"}, f"Kreiran sustav žičare '{sys_root.name}' ({len(nulls)} stupa, 12 gondola).")
        return {"FINISHED"}


class AFDIR_OT_SpawnCavernRopewayNetwork(bpy.types.Operator):
    bl_idname = "af_director.spawn_cavern_ropeway_network"
    bl_label = "Popuni Podzemlje Mrežom Žičara (3 Linije: Ledeni Zid -> Grad)"
    bl_description = (
        "Izgradi kompletan sustav od 3 kružne žičare koje prevoze plave kristale leda "
        "od Desnog ledenog zida preko špilje i ponora prema podzemnom gradu"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        created = populate_cavern_multi_ropeway_network(context)
        if created:
            sync_ropeway_ui_from_active_system(context.scene, sys_root=created[0])
        self.report(
            {"INFO"},
            f"Izgrađena mreža od {len(created)} kružnih žičara (42 gondole s kristalima leda i vilenjacima)!",
        )
        return {"FINISHED"}


class AFDIR_OT_SelectRopewayObject(bpy.types.Operator):
    bl_idname = "af_director.select_ropeway_object"
    bl_label = "Odaberi Sustav Žičare, Null Točku ili Gondolu"
    bl_description = "Odaberi ovaj sustav žičare, Null točku stupa ili gondolu u 3D Viewportu i uključi strelice za pomicanje (G)"
    bl_options = {"REGISTER", "UNDO"}

    target_name: StringProperty(default="")
    frame_view: BoolProperty(default=False)

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_name)
        if not obj:
            return {"CANCELLED"}

        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        sys_root = find_ropeway_system_from_object(obj)
        if sys_root:
            context.scene.af_rw_active_system_name = sys_root.name
            if obj.get("af_is_rw_gondola"):
                sys_root["af_rw_active_gondola_name"] = obj.name
            elif obj.get("af_is_rw_null_point"):
                sys_root["af_rw_active_null_name"] = obj.name
            sync_ropeway_ui_from_active_system(
                context.scene,
                sys_root=sys_root,
                gondola_obj=obj if obj.get("af_is_rw_gondola") else None,
            )

        bpy.ops.object.select_all(action="DESELECT")
        obj.hide_viewport = False
        obj.hide_select = False
        obj.select_set(True)
        context.view_layer.objects.active = obj
        show_viewport_move_gizmo_arrows(True)

        if self.frame_view and not bpy.app.background:
            try:
                for win in context.window_manager.windows:
                    for area in win.screen.areas:
                        if area.type == "VIEW_3D":
                            region = next((r for r in area.regions if r.type == "WINDOW"), None)
                            if region:
                                with context.temp_override(window=win, area=area, region=region):
                                    bpy.ops.view3d.view_selected()
                                break
            except Exception:
                pass

        return {"FINISHED"}


class AFDIR_OT_AutoFitRopewayPylonToGround(bpy.types.Operator):
    bl_idname = "af_director.auto_fit_ropeway_pylon_to_ground"
    bl_label = "Spusti Stup do Tla / Kopiraj Visinu"
    bl_description = (
        "Automatski izračunaj i izgradi stup od Null točke prema dolje do tla/skele ispod stupa "
        "(ili primijeni visinu odabranog stupa na sve stupove žičare)"
    )
    bl_options = {"REGISTER", "UNDO"}

    null_name: StringProperty(default="")
    action_mode: StringProperty(default="AUTO_GROUND")

    def execute(self, context):
        sys_root = get_active_ropeway_system(context)
        if not sys_root:
            return {"CANCELLED"}

        nulls = get_system_null_point_objects(sys_root)
        if not nulls:
            return {"CANCELLED"}

        if self.action_mode == "COPY_ACTIVE_TO_ALL":
            src = bpy.data.objects.get(self.null_name) if self.null_name else get_active_null_point_object(context, sys_root=sys_root)
            if not src:
                return {"CANCELLED"}
            h = get_null_tower_height_m(sys_root, src)
            m = get_null_support_mode(sys_root, src)
            sys_root["af_rw_tower_height_m"] = h
            sys_root["af_rw_tower_support_mode"] = m
            for n_obj in nulls:
                set_null_tower_height_m(n_obj, height_m=h, support_mode=m)
            sync_ropeway_ui_from_active_system(context.scene, sys_root=sys_root)
            self.report({"INFO"}, f"Visina {h:.1f} m primijenjena na svih {len(nulls)} stupova žičare.")
            return {"FINISHED"}

        target = bpy.data.objects.get(self.null_name) if self.null_name else None
        targets = [target] if target else nulls
        fitted = []
        for n_obj in targets:
            new_h = auto_fit_null_tower_height_to_ground(n_obj, fallback_floor_z=0.0, scene=context.scene)
            fitted.append(f"{n_obj.name}: {new_h:.1f}m")

        sync_ropeway_ui_from_active_system(context.scene, sys_root=sys_root)
        self.report({"INFO"}, f"Stupovi izgrađeni od Null točke prema dolje ({', '.join(fitted)}).")
        return {"FINISHED"}


class AFDIR_OT_AddRopewayNullPoint(bpy.types.Operator):
    bl_idname = "af_director.add_ropeway_null_point"
    bl_label = "+ Dodaj Novu Null Točku (Stup / Koloturu)"
    bl_description = (
        "Dodaj novu interaktivnu Null točku stupa iza odabrane točke (ili na 3D kursor) "
        "i automatski preračunaj koloture i provjes žice"
    )
    bl_options = {"REGISTER", "UNDO"}

    insert_mode: StringProperty(default="AFTER_ACTIVE")

    def execute(self, context):
        sys_root = get_active_ropeway_system(context)
        if not sys_root:
            self.report({"WARNING"}, "Prvo odaberi ili kreiraj sustav žičare.")
            return {"CANCELLED"}

        active = getattr(context, "active_object", None)
        after_null = active if (active and active.get("af_is_rw_null_point")) else None
        loc = tuple(context.scene.cursor.location) if self.insert_mode == "AT_CURSOR" else None

        new_null = add_null_point_to_ropeway_system(
            sys_root,
            after_null_obj=after_null,
            location=loc,
        )
        if not new_null:
            return {"CANCELLED"}

        try:
            bpy.ops.object.select_all(action="DESELECT")
            new_null.select_set(True)
            context.view_layer.objects.active = new_null
            show_viewport_move_gizmo_arrows(True)
        except Exception:
            pass

        self.report({"INFO"}, f"Dodana nova Null točka stupa '{new_null.name}' — pomakni je s G!")
        return {"FINISHED"}


class AFDIR_OT_RemoveRopewayNullPoint(bpy.types.Operator):
    bl_idname = "af_director.remove_ropeway_null_point"
    bl_label = "- Ukloni Null Točku Stupa"
    bl_description = "Ukloni odabranu (ili zadnju) Null točku stupa sa žičare (sustav zadržava najmanje 2 točke)"
    bl_options = {"REGISTER", "UNDO"}

    null_name: StringProperty(default="")

    def execute(self, context):
        sys_root = get_active_ropeway_system(context)
        if not sys_root:
            return {"CANCELLED"}

        target = bpy.data.objects.get(self.null_name) if self.null_name else None
        if not target:
            active = getattr(context, "active_object", None)
            if active and active.get("af_is_rw_null_point"):
                target = active

        ok = remove_null_point_from_ropeway_system(sys_root, target_null_obj=target)
        if not ok:
            self.report({"WARNING"}, "Žičara mora imati najmanje 2 Null točke stupova (Početak i Kraj).")
            return {"CANCELLED"}

        nulls = get_system_null_point_objects(sys_root)
        if nulls:
            try:
                bpy.ops.object.select_all(action="DESELECT")
                nulls[-1].select_set(True)
                context.view_layer.objects.active = nulls[-1]
            except Exception:
                pass

        self.report({"INFO"}, f"Uklonjena Null točka stupa. Preostalo {len(nulls)} točaka.")
        return {"FINISHED"}


class AFDIR_OT_DeleteRopewaySystem(bpy.types.Operator):
    bl_idname = "af_director.delete_ropeway_system"
    bl_label = "Obriši Sustav Žičare"
    bl_description = "Obriši cijeli odabrani sustav žičare, njegove stupove, koloture, žice i gondole"
    bl_options = {"REGISTER", "UNDO"}

    system_name: StringProperty(default="")

    def execute(self, context):
        sys_root = bpy.data.objects.get(self.system_name) if self.system_name else get_active_ropeway_system(context)
        if not sys_root:
            return {"CANCELLED"}
        name = sys_root.name
        delete_ropeway_system(sys_root)
        rem = get_all_ropeway_systems(context.scene)
        if rem:
            context.scene.af_rw_active_system_name = rem[0].name
            sync_ropeway_ui_from_active_system(context.scene, sys_root=rem[0])
        self.report({"INFO"}, f"Obrisan sustav žičare '{name}'.")
        return {"FINISHED"}


class AFDIR_OT_ReloadRopewayTripoModels(bpy.types.Operator):
    bl_idname = "af_director.reload_ropeway_models"
    bl_label = "Osvježi 3D Modele Gondola i Kolotura (.GLB)"
    bl_description = "Ponovno učitaj optimizirane V2 Tripo 3D low-poly modele gondola s unificiranim C-prihvatom"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cnt = reload_all_tripo_gondola_models_in_scene(context)
        self.report({"INFO"}, f"Osvježeni V2 3D modeli gondola na {cnt} sustava žičara.")
        return {"FINISHED"}


# ============================================================================
# 3. N-PANEL UI (`7. Žičare, Gondole i Koloture`)
# ============================================================================

class VIEW3D_PT_RopewayGondolasStudio(bpy.types.Panel):
    bl_label = "7. Žičare, Gondole i Koloture (Ropeway Studio)"
    bl_idname = "VIEW3D_PT_af_ropeway_gondolas"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Elf Director"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        all_sys = get_all_ropeway_systems(scn)
        active_sys = get_active_ropeway_system(context)

        # --------------------------------------------------------------------
        # 1. MULTI-SYSTEM ROPEWAY MANAGER (`Sustavi Žičara u Sceni`)
        # --------------------------------------------------------------------
        box_sys = layout.box()
        row_hdr = box_sys.row(align=True)
        row_hdr.label(
            text=f"1. Sustavi Žičara u Sceni ({len(all_sys)})",
            icon="MOD_CURVE",
        )
        row_hdr.operator(
            "af_director.reload_ropeway_models",
            text="",
            icon="FILE_REFRESH",
        )

        row_spawn = box_sys.row(align=True)
        row_spawn.scale_y = 1.3
        op_new = row_spawn.operator(
            "af_director.spawn_ropeway_system",
            text="+ Dodaj Novi Sustav Žičare",
            icon="ADD",
        )
        op_new.preset_mode = "GLACIER_TO_CITY"

        op_cur = row_spawn.operator(
            "af_director.spawn_ropeway_system",
            text="+ Na Kursoru",
            icon="PIVOT_CURSOR",
        )
        op_cur.preset_mode = "CURSOR"

        row_net = box_sys.row(align=True)
        row_net.scale_y = 1.2
        row_net.operator(
            "af_director.spawn_cavern_ropeway_network",
            text="Popuni Podzemlje Mrežom Žičara (3 Linije: Zid -> Grad)",
            icon="WORLD_DATA",
        )

        if all_sys:
            col_slist = box_sys.column(align=True)
            for s_obj in all_sys:
                is_sel = (s_obj == active_sys)
                null_cnt = len(get_system_null_point_objects(s_obj))
                g_cnt = int(s_obj.get("af_rw_gondola_count", 12))
                lbl = s_obj.get("af_rw_label", s_obj.name)
                r = col_slist.row(align=True)
                op_s = r.operator(
                    "af_director.select_ropeway_object",
                    text=f"{s_obj.name}: {lbl} [{null_cnt} stupa | {g_cnt} gond.]",
                    depress=is_sel,
                    icon="RADIOBUT_ON" if is_sel else "RADIOBUT_OFF",
                )
                op_s.target_name = s_obj.name
                op_s.frame_view = False

                op_z = r.operator(
                    "af_director.select_ropeway_object",
                    text="",
                    icon="VIEWZOOM",
                )
                op_z.target_name = s_obj.name
                op_z.frame_view = True

                op_del = r.operator(
                    "af_director.delete_ropeway_system",
                    text="",
                    icon="TRASH",
                )
                op_del.system_name = s_obj.name

        if not active_sys:
            layout.label(
                text="Klikni '+ Dodaj Novi Sustav Žičare' za početak.",
                icon="INFO",
            )
            return

        # --------------------------------------------------------------------
        # 2. PYLON NULL POINTS & DYNAMIC DOWNWARD TOWER HEIGHT (`Null Točke i Visina Stupova`)
        # --------------------------------------------------------------------
        nulls = get_system_null_point_objects(active_sys)
        active_null = get_active_null_point_object(context, sys_root=active_sys)
        box_nulls = layout.box()
        box_nulls.label(
            text=f"2. Null Točke i Visina Stupova Prema Dolje ({len(nulls)} stupa):",
            icon="EMPTY_AXIS",
        )

        row_nbtn = box_nulls.row(align=True)
        row_nbtn.scale_y = 1.25
        op_add_n = row_nbtn.operator(
            "af_director.add_ropeway_null_point",
            text="+ Dodaj Null Točku Stupa",
            icon="ADD",
        )
        op_add_n.insert_mode = "AFTER_ACTIVE"

        op_add_c = row_nbtn.operator(
            "af_director.add_ropeway_null_point",
            text="+ Na 3D Kursor",
            icon="PIVOT_CURSOR",
        )
        op_add_c.insert_mode = "AT_CURSOR"

        op_rem_n = row_nbtn.operator(
            "af_director.remove_ropeway_null_point",
            text="- Ukloni",
            icon="REMOVE",
        )
        op_rem_n.null_name = ""

        col_nlist = box_nulls.column(align=True)
        for idx, n_obj in enumerate(nulls):
            is_nsel = (active_null == n_obj)
            loc = n_obj.location
            r_n = col_nlist.row(align=True)
            role_lbl = (
                "START"
                if idx == 0
                else ("KRAJ" if idx == len(nulls) - 1 else f"Stup #{idx + 1}")
            )
            op_n = r_n.operator(
                "af_director.select_ropeway_object",
                text=f"Null {idx + 1:02d} [{role_lbl}] Z={loc.z:.1f}m",
                depress=is_nsel,
                icon="OUTLINER_OB_EMPTY" if is_nsel else "EMPTY_DATA",
            )
            op_n.target_name = n_obj.name
            op_n.frame_view = False

            # Direct per-null dynamic downward tower height slider right in the row!
            r_n.prop(n_obj, "af_rw_tower_height_m", text="Visina", slider=True)

            op_fit = r_n.operator(
                "af_director.auto_fit_ropeway_pylon_to_ground",
                text="",
                icon="IMPORT",
            )
            op_fit.null_name = n_obj.name
            op_fit.action_mode = "AUTO_GROUND"

            op_nz = r_n.operator(
                "af_director.select_ropeway_object",
                text="",
                icon="VIEWZOOM",
            )
            op_nz.target_name = n_obj.name
            op_nz.frame_view = True

            if len(nulls) > 2:
                op_nx = r_n.operator(
                    "af_director.remove_ropeway_null_point",
                    text="",
                    icon="X",
                )
                op_nx.null_name = n_obj.name

        # Selected Null Point Dynamic Pylon Inspector
        if active_null:
            n_idx = int(active_null.get("af_rw_null_index", 1))
            cur_h = get_null_tower_height_m(active_sys, active_null)
            top_z = float(active_null.location.z)
            bot_z = top_z - cur_h
            n_tiers = max(1, int(round(max(0.15, cur_h - 0.85) / 3.8)))

            box_sel_null = box_nulls.box()
            row_sn = box_sel_null.row(align=True)
            row_sn.label(
                text=f"Odabrani Stup: Null {n_idx:02d} (Od Null Točke Prema Dolje)",
                icon="MOD_BUILD",
            )
            op_snz = row_sn.operator("af_director.select_ropeway_object", text="", icon="VIEWZOOM")
            op_snz.target_name = active_null.name
            op_snz.frame_view = True

            col_sn = box_sel_null.column(align=True)
            col_sn.scale_y = 1.15
            col_sn.prop(
                active_null,
                "af_rw_tower_height_m",
                text="Zadana Visina Stupa Prema Dolje (m)",
                slider=True,
            )
            col_sn.prop(active_null, "af_rw_support_mode", text="Vrsta Stupa")

            box_sel_null.label(
                text=f"Vrh (Null): Z = {top_z:+.1f} m  ->  Dno Stupa: Z = {bot_z:+.1f} m  ({n_tiers} katova rešetke)",
                icon="DRIVER_DISTANCE",
            )

            row_act_n = box_sel_null.row(align=True)
            op_fit_one = row_act_n.operator(
                "af_director.auto_fit_ropeway_pylon_to_ground",
                text="Spusti Ovaj Stup do Tla Ispod",
                icon="IMPORT",
            )
            op_fit_one.null_name = active_null.name
            op_fit_one.action_mode = "AUTO_GROUND"

            op_copy_all = row_act_n.operator(
                "af_director.auto_fit_ropeway_pylon_to_ground",
                text="Primijeni Visinu na Sve Stupove",
                icon="DUPLICATE",
            )
            op_copy_all.null_name = active_null.name
            op_copy_all.action_mode = "COPY_ACTIVE_TO_ALL"

        # --------------------------------------------------------------------
        # 3. DYNAMIC CATENARY SAG & PHYSICS (`Dinamički Provjes Žice i Fizika`)
        # --------------------------------------------------------------------
        box_sag = layout.box()
        box_sag.label(
            text="3. Dinamički Provjes Žice (Catenary Sag + Težina Gondola):",
            icon="FORCE_CURVE",
        )
        col_sag = box_sag.column(align=True)
        col_sag.prop(scn, "af_rw_ui_base_sag_m", text="Osnovni Provjes Žice (Catenary Sag m)", slider=True)
        col_sag.prop(
            scn,
            "af_rw_ui_load_sink_m",
            text="Dinamičko Potonuće pod Gondolom (Load Sink m)",
            slider=True,
        )
        col_sag.prop(scn, "af_rw_ui_speed_mps", text="Brzina Kruženja Žičare (m/s)", slider=True)
        col_sag.prop(scn, "af_rw_ui_sway_amp_deg", text="Njihanje Gondole u Vožnji (°)", slider=True)

        total_loop_m = float(active_sys.get("af_rw_stat_loop_length_m", 0.0))
        max_sag_m = float(active_sys.get("af_rw_stat_max_sag_m", 0.0))
        box_sag.label(
            text=f"Duljina Kruga: {total_loop_m:.1f} m  |  Maks. Dinamički Provjes: {max_sag_m:.2f} m",
            icon="DRIVER_DISTANCE",
        )

        # --------------------------------------------------------------------
        # 4. PULLEY / SHEAVE & TOWER CONTROLLER (`Kontroler za Koloture i Stupove`)
        # --------------------------------------------------------------------
        box_pul = layout.box()
        box_pul.label(
            text="4. Kontroler za Koloture i Sve Stupove Žičare:",
            icon="MOD_SCREW",
        )
        col_pul = box_pul.column(align=True)
        col_pul.prop(scn, "af_rw_ui_loop_gauge_m", text="Širina Kruga / Razmak Kolotura (m)", slider=True)
        col_pul.prop(scn, "af_rw_ui_pulley_scale", text="Veličina Kolotura (Pulley Scale)", slider=True)
        col_pul.prop(scn, "af_rw_ui_rollers_per_side", text="Broj Kotačića po Koloturi (2..6)", slider=True)
        col_pul.prop(
            scn,
            "af_rw_ui_show_turnaround",
            text="Veliki Okretni Koloturi na Krajevima (Bullwheels)",
            toggle=True,
        )
        col_pul.prop(scn, "af_rw_ui_tower_support_mode", text="Nosač Svih")
        if getattr(scn, "af_rw_ui_tower_support_mode", "PYLON_TOWER") != "PULLEY_ONLY":
            col_pul.prop(
                scn,
                "af_rw_ui_tower_height_m",
                text="Visina Svih Stupova Prema Dolje (m)",
                slider=True,
            )
            col_pul.prop(
                scn,
                "af_rw_ui_auto_height_from_base_z",
                text="Fiksiraj Dno Stupa pri Pomicanju Null Točke s 'G' (Auto-Visina)",
                toggle=True,
            )
            op_fit_all = col_pul.operator(
                "af_director.auto_fit_ropeway_pylon_to_ground",
                text="Auto-Visina Svih Stupova do Tla / Skela Ispod",
                icon="IMPORT",
            )
            op_fit_all.null_name = ""
            op_fit_all.action_mode = "AUTO_GROUND"

        # --------------------------------------------------------------------
        # 5. GONDOLA FLEET & INDIVIDUAL GONDOLA CONTROLLER (`Gondole: Teretne i Putničke`)
        # --------------------------------------------------------------------
        box_gond = layout.box()
        gondolas = get_system_gondola_objects(active_sys)
        active_g = get_active_gondola_object(context, sys_root=active_sys)

        box_gond.label(
            text=f"5. Kontrola Gondola ({len(gondolas)} na Cijeloj Žičari):",
            icon="OBJECT_DATA",
        )
        col_gf = box_gond.column(align=True)
        col_gf.prop(scn, "af_rw_ui_gondola_count", text="Ukupan Broj Gondola na Žičari", slider=True)
        col_gf.prop(scn, "af_rw_ui_distribution_mode", text="Raspored")

        # 1-Click Grid of all Gondolas on the active ropeway
        if gondolas:
            col_ggrid = box_gond.column(align=True)
            for r_start in range(0, len(gondolas), 4):
                row_g = col_ggrid.row(align=True)
                row_g.scale_y = 1.15
                for g_obj in gondolas[r_start:r_start + 4]:
                    g_idx = int(g_obj.get("af_rw_gondola_index", 1))
                    v_tag = "T" if g_obj.get("af_rw_gondola_variant") == "GONDOLA_CARGO" else "P"
                    e_id = g_obj.get("af_rw_elf_id", "NONE")
                    e_tag = f"+{e_id}" if (e_id and e_id != "NONE") else ""
                    op_g = row_g.operator(
                        "af_director.select_ropeway_object",
                        text=f"#{g_idx:02d} [{v_tag}{e_tag}]",
                        depress=(g_obj == active_g),
                    )
                    op_g.target_name = g_obj.name
                    op_g.frame_view = False

        # Individual Gondola Inspector Box
        if active_g:
            g_idx = int(active_g.get("af_rw_gondola_index", 1))
            is_cargo = (active_g.get("af_rw_gondola_variant") == "GONDOLA_CARGO")
            v_title = "Teretna Gondola (Široka Košara 1:1)" if is_cargo else "Putnička Gondola (Široka Kabina 1:1)"
            box_insp = box_gond.box()
            row_ih = box_insp.row(align=True)
            row_ih.label(
                text=f"Pojedinačna Gondola #{g_idx:02d}: {v_title}",
                icon="SETTINGS",
            )
            op_gz = row_ih.operator("af_director.select_ropeway_object", text="", icon="VIEWZOOM")
            op_gz.target_name = active_g.name
            op_gz.frame_view = True

            col_insp = box_insp.column(align=True)
            col_insp.prop(scn, "af_rw_slot_variation", text="Varijacija")
            col_insp.prop(scn, "af_rw_slot_cargo", text="Teret Unutra")
            col_insp.prop(scn, "af_rw_slot_elf_id", text="Vilenjak Unutra")
            col_insp.prop(
                scn,
                "af_rw_slot_weight_factor",
                text="Težina Gondole (Faktor Potonuća Žice)",
                slider=True,
            )
            col_insp.prop(scn, "af_rw_slot_scale", text="Veličina Gondole (Scale)", slider=True)

        # --------------------------------------------------------------------
        # 6. EXTREME OPTIMIZATION & LOW-POLY CONTROLS
        # --------------------------------------------------------------------
        box_opt = layout.box()
        row_opt = box_opt.row(align=True)
        row_opt.label(text="6. Optimizacija i Low-Poly:", icon="MOD_DECIM")
        row_opt.prop(
            scn,
            "af_rw_ui_low_poly_mode",
            text="Ultra Low-Poly Proxy Mode",
            toggle=True,
        )


class VIEW3D_PT_RopewayGondolasStandaloneTab(bpy.types.Panel):
    bl_label = "Žičare, Gondole i Koloture (Ropeway Studio)"
    bl_idname = "VIEW3D_PT_af_ropeway_gondolas_tab"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Žičare Studio"

    def draw(self, context):
        VIEW3D_PT_RopewayGondolasStudio.draw(self, context)


# ============================================================================
# 4. REGISTRATION
# ============================================================================

UI_CLASSES = (
    AFDIR_OT_SpawnRopewaySystem,
    AFDIR_OT_SpawnCavernRopewayNetwork,
    AFDIR_OT_SelectRopewayObject,
    AFDIR_OT_AutoFitRopewayPylonToGround,
    AFDIR_OT_AddRopewayNullPoint,
    AFDIR_OT_RemoveRopewayNullPoint,
    AFDIR_OT_DeleteRopewaySystem,
    AFDIR_OT_ReloadRopewayTripoModels,
    VIEW3D_PT_RopewayGondolasStudio,
    VIEW3D_PT_RopewayGondolasStandaloneTab,
)


def register_ropeway_gondolas_ui():
    for cls in UI_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

    bpy.types.Object.af_rw_tower_height_m = FloatProperty(
        name="Visina Stupa od Null Točke Prema Dolje (m)",
        description="Dinamički gradi rešetkasti stup žičare od ove Null točke prema dolje za zadanu visinu (u metrima)",
        default=14.5,
        min=0.5,
        max=200.0,
        soft_min=1.5,
        soft_max=100.0,
        step=25,
        precision=2,
        get=_get_null_obj_tower_height,
        set=_set_null_obj_tower_height,
    )
    bpy.types.Object.af_rw_support_mode = EnumProperty(
        name="Vrsta Stupa / Nosača",
        items=TOWER_SUPPORT_MODES,
        default="PYLON_TOWER",
        get=_get_null_obj_support_mode,
        set=_set_null_obj_support_mode,
    )

    bpy.types.Scene.af_rw_active_system_name = StringProperty(
        name="Aktivni Sustav Žičare",
        default="",
    )
    bpy.types.Scene.af_rw_ui_gondola_count = IntProperty(
        name="Ukupan Broj Gondola na Žičari",
        default=12,
        min=1,
        max=60,
        update=_on_rw_fleet_changed,
    )
    bpy.types.Scene.af_rw_ui_distribution_mode = EnumProperty(
        name="Raspored Gondola",
        items=ROPEWAY_DISTRIBUTION_MODES,
        default="MIXED_75_CARGO_25_ELF",
        update=_on_rw_fleet_changed,
    )
    bpy.types.Scene.af_rw_ui_base_sag_m = FloatProperty(
        name="Osnovni Provjes Žice (Catenary Sag m)",
        default=1.45,
        min=0.05,
        max=8.0,
        update=_on_rw_physics_changed,
    )
    bpy.types.Scene.af_rw_ui_load_sink_m = FloatProperty(
        name="Dinamičko Potonuće pod Gondolom (Load Sink m)",
        default=0.95,
        min=0.0,
        max=5.0,
        update=_on_rw_physics_changed,
    )
    bpy.types.Scene.af_rw_ui_speed_mps = FloatProperty(
        name="Brzina Žičare (m/s)",
        default=2.45,
        min=-10.0,
        max=10.0,
        update=_on_rw_physics_changed,
    )
    bpy.types.Scene.af_rw_ui_sway_amp_deg = FloatProperty(
        name="Amplituda Ljuljanja Gondole (°)",
        default=4.5,
        min=0.0,
        max=25.0,
        update=_on_rw_physics_changed,
    )
    bpy.types.Scene.af_rw_ui_loop_gauge_m = FloatProperty(
        name="Širina Kruga / Razmak Kolotura (m)",
        default=3.40,
        min=1.6,
        max=8.0,
        update=_on_rw_pylon_geometry_changed,
    )
    bpy.types.Scene.af_rw_ui_pulley_scale = FloatProperty(
        name="Veličina Kolotura",
        default=1.0,
        min=0.4,
        max=2.5,
        update=_on_rw_physics_changed,
    )
    bpy.types.Scene.af_rw_ui_rollers_per_side = IntProperty(
        name="Broj Kotačića po Koloturi",
        default=4,
        min=2,
        max=6,
        update=_on_rw_pylon_geometry_changed,
    )
    bpy.types.Scene.af_rw_ui_show_turnaround = BoolProperty(
        name="Veliki Okretni Koloturi na Krajevima",
        default=True,
        update=_on_rw_physics_changed,
    )
    bpy.types.Scene.af_rw_ui_tower_support_mode = EnumProperty(
        name="Vrsta Nosača Stupa",
        items=TOWER_SUPPORT_MODES,
        default="PYLON_TOWER",
        update=_on_rw_system_support_mode_changed,
    )
    bpy.types.Scene.af_rw_ui_tower_height_m = FloatProperty(
        name="Visina Svih Stupova Prema Dolje (m)",
        default=14.5,
        min=0.5,
        max=200.0,
        soft_min=1.5,
        soft_max=100.0,
        update=_on_rw_system_tower_height_changed,
    )
    bpy.types.Scene.af_rw_ui_auto_height_from_base_z = BoolProperty(
        name="Fiksiraj Dno Stupa pri Pomicanju Null Točke s 'G' (Auto-Visina)",
        description="Kad pomičeš Null točku gore/dolje s 'G', stup se automatski produljuje ili skraćuje prema dolje do svoje bazne razine",
        default=False,
        update=_on_rw_auto_height_mode_changed,
    )
    bpy.types.Scene.af_rw_ui_low_poly_mode = BoolProperty(
        name="Ultra Low-Poly Proxy Mode",
        default=False,
        update=_on_rw_low_poly_changed,
    )

    # Individual Gondola Inspector Properties
    bpy.types.Scene.af_rw_slot_variation = EnumProperty(
        name="Varijacija Gondole",
        items=_get_variation_enum_items,
        update=_on_rw_individual_gondola_changed,
    )
    bpy.types.Scene.af_rw_slot_cargo = EnumProperty(
        name="Unutarnji Teret",
        items=_get_cargo_enum_items,
        update=_on_rw_individual_gondola_changed,
    )
    bpy.types.Scene.af_rw_slot_elf_id = EnumProperty(
        name="Vilenjak u Gondoli",
        items=_get_elf_enum_items,
        update=_on_rw_individual_gondola_changed,
    )
    bpy.types.Scene.af_rw_slot_weight_factor = FloatProperty(
        name="Težina Gondole (Faktor Potonuća Žice)",
        default=1.25,
        min=0.2,
        max=3.5,
        update=_on_rw_individual_gondola_changed,
    )
    bpy.types.Scene.af_rw_slot_scale = FloatProperty(
        name="Skala Gondole",
        default=1.0,
        min=0.4,
        max=2.5,
        update=_on_rw_individual_gondola_changed,
    )

    register_ropeway_gondola_handlers()


def unregister_ropeway_gondolas_ui():
    unregister_ropeway_gondola_handlers()

    for obj_prop in ("af_rw_tower_height_m", "af_rw_support_mode"):
        if hasattr(bpy.types.Object, obj_prop):
            try:
                delattr(bpy.types.Object, obj_prop)
            except Exception:
                pass

    for prop in (
        "af_rw_active_system_name",
        "af_rw_ui_gondola_count",
        "af_rw_ui_distribution_mode",
        "af_rw_ui_base_sag_m",
        "af_rw_ui_load_sink_m",
        "af_rw_ui_speed_mps",
        "af_rw_ui_sway_amp_deg",
        "af_rw_ui_loop_gauge_m",
        "af_rw_ui_pulley_scale",
        "af_rw_ui_rollers_per_side",
        "af_rw_ui_show_turnaround",
        "af_rw_ui_tower_support_mode",
        "af_rw_ui_tower_height_m",
        "af_rw_ui_auto_height_from_base_z",
        "af_rw_ui_low_poly_mode",
        "af_rw_slot_variation",
        "af_rw_slot_cargo",
        "af_rw_slot_elf_id",
        "af_rw_slot_weight_factor",
        "af_rw_slot_scale",
    ):
        if hasattr(bpy.types.Scene, prop):
            try:
                delattr(bpy.types.Scene, prop)
            except Exception:
                pass

    for cls in reversed(UI_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
