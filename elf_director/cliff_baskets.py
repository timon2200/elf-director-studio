# -*- coding: utf-8 -*-
"""
Cliff Basket, 4-Gizmo Rope Rig & Damped Pendulum / Pickaxe Recoil Physics Studio
(`elf_director.cliff_baskets`)
=================================================================================
Provides:
  1. 3D Basket & Modular Cargo Loader (Tripo 3D v3 `.glb` models from
     `assets/models/glb/cliff_baskets/` + high-detail procedural fallbacks).
  2. 4 Interactive Rope Attachment Gizmos (`GIZMO_Pin_01..04`), Collector Hook
     Gizmo (`GIZMO_SpreaderHook`), Top Winch Pulley Gizmo (`GIZMO_TopWinch`),
     and Wall Impact Target Gizmo (`GIZMO_WallTarget`) — all directly clickable
     and movable (`G`) in the 3D Viewport with `show_in_front = True`.
  3. Procedural 3D Rope, Forged Shackle & Rotating Winch Pulley Rig
     (`GN_Cliff_Basket_Rope_Rig`) supporting 2, 3, or 4 ropes in Spreader (`4->1`)
     or Parallel (`4->4`) mode, with live catenary/vibration deformation.
  4. Analytical Damped Pendulum + Winch Lowering/Stopping + Pickaxe Strike
     Push-Off Recoil Solver synchronized with the mounted Elf's NLA strips
     (`AF_27_Mine_Pickaxe` -> swing/recoil; `Idle` or post-lowering -> decays
     smoothly to 100% stationary standstill `0.000 m`), plus One-Way Wall Bumper
     Clamp and Blue-Ice Shard Burst VFX (`VFX_IceBurst`).
  5. 1-Click Bake to Keyframes (Graph Editor fine-tuning) and 1-Click Revert to
     Live Procedural Physics.
"""

import math
import os
import bmesh
import bpy
from bpy.app.handlers import persistent
from mathutils import Euler, Matrix, Vector

from .constants import PACKAGE_DIR, STATE, ensure_collection, get_assets_glb_dir
from .nla_sequencer import (
    append_animation_to_nla,
    apply_additive_pose_offset,
    clear_nla_sequence,
    get_nla_sequence_clips,
    rebuild_nla_sequence_from_specs,
)
from .rig_actors import (
    find_character_controller,
    get_character_armature_from_ctrl,
    set_actor_accessories,
    spawn_elf_actor,
)


def show_viewport_move_gizmo_arrows(enabled: bool = True):
    """Enables the 3D Viewport Translate/Rotate gizmo arrows so the user can drag GIZMO_Pin_01..04 directly."""
    if bpy.app.background:
        return
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            space.show_gizmo = True
                            space.show_gizmo_object_translate = bool(enabled)
                            space.show_gizmo_object_rotate = False
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)
CLIFF_BASKETS_COLLECTION_NAME = "05_CLIFF_BASKETS_STUDIO"
CLIFF_GLB_DIR = get_assets_glb_dir("cliff_baskets")

CLIFF_BASKET_PRESETS = (
    (
        "BASKET_01_OCT_EMPTY",
        "1. Oktagonalna Košara (Prazna — 1 Vilenjak)",
        "SM_Basket_01_Octagonal_Empty.glb",
        (2.15, 2.15, 1.24),
    ),
    (
        "BASKET_02_GONDOLA_EMPTY",
        "2. Pravokutna Gondola (Prazna — 1-2 Vilenjaka)",
        "SM_Basket_02_Gondola_Empty.glb",
        (2.60, 1.80, 1.22),
    ),
    (
        "BASKET_03_HALF_MINER",
        "3. Polupuna Radna Košara (Oprema + Mjesto za Vilenjaka)",
        "SM_Basket_03_HalfLoaded_Miner.glb",
        (2.28, 2.10, 1.26),
    ),
    (
        "BASKET_04_FULL_CARGO",
        "4. Puna Teretna Košara (Plavi Led + Bačva + Alat)",
        "SM_Basket_04_FullCargo_Ice.glb",
        (2.38, 1.78, 1.32),
    ),
)

CLIFF_CARGO_PRESETS = (
    (
        "CARGO_A_ICE",
        "Paket A: Plavi Ledeni Kristali",
        "SM_Cargo_A_BlueIce_Heap.glb",
        (0.46, 0.42, 0.34),
        (0.32, 0.14, 0.02),
    ),
    (
        "CARGO_B_TOOLS",
        "Paket B: Sanduk s Krampovima i Užetom",
        "SM_Cargo_B_ToolCrate_Tools.glb",
        (0.50, 0.38, 0.42),
        (0.30, -0.18, 0.02),
    ),
    (
        "CARGO_C_BARREL",
        "Paket C: Bačva s Manometrom i Lampom",
        "SM_Cargo_C_Barrel_Lantern.glb",
        (0.42, 0.40, 0.54),
        (-0.32, 0.22, 0.02),
    ),
)

_PHYSICS_EVAL_GUARD = False


# ============================================================================
# 1. MATERIALS & PROCEDURAL / TRIPO 3D MESH BUILDERS
# ============================================================================

def _get_or_create_material(name: str, base_color: tuple, metallic: float = 0.0, roughness: float = 0.5, emission_color: tuple = None, emission_strength: float = 0.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*base_color[:3], 1.0)
        bsdf.inputs["Metallic"].default_value = float(metallic)
        bsdf.inputs["Roughness"].default_value = float(roughness)
        if emission_color and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emission_color[:3], 1.0)
            bsdf.inputs["Emission Strength"].default_value = float(emission_strength)
    mat.diffuse_color = (*base_color[:3], 1.0)
    return mat


def _build_gizmo_ring_mesh(name: str, radius: float, tube: float, color: tuple, emission: float = 2.4, add_crosshair: bool = True):
    """Creates a bright, easy-to-click 3D Torus + Crosshair mesh for the 4 rope attachment gizmos."""
    mesh = bpy.data.meshes.get(name)
    if mesh:
        bpy.data.meshes.remove(mesh, do_unlink=True)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()

    segs_major = 24
    segs_minor = 10
    ring_verts = []
    for i in range(segs_major):
        a = 2.0 * math.pi * i / segs_major
        ca, sa = math.cos(a), math.sin(a)
        loop = []
        for j in range(segs_minor):
            b = 2.0 * math.pi * j / segs_minor
            cb, sb = math.cos(b), math.sin(b)
            r = radius + tube * cb
            x = r * ca
            y = r * sa
            z = tube * sb
            loop.append(bm.verts.new((x, y, z)))
        ring_verts.append(loop)

    for i in range(segs_major):
        ni = (i + 1) % segs_major
        for j in range(segs_minor):
            nj = (j + 1) % segs_minor
            try:
                bm.faces.new((
                    ring_verts[i][j],
                    ring_verts[ni][j],
                    ring_verts[ni][nj],
                    ring_verts[i][nj],
                ))
            except ValueError:
                pass

    if add_crosshair:
        # Center sphere / octahedron core so clicking the middle of the ring hits solid geometry
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=radius * 0.42)

    bm.to_mesh(mesh)
    bm.free()

    mat = _get_or_create_material(
        f"MAT_{name}",
        base_color=color,
        metallic=0.3,
        roughness=0.2,
        emission_color=color,
        emission_strength=emission,
    )
    mesh.materials.append(mat)
    return mesh


def _build_procedural_basket_fallback_mesh(preset_id: str, target_dims: tuple) -> bpy.types.Mesh:
    """
    Builds an open-top hollow wicker/timber/brass basket mesh with standing floor at Z=0.0,
    top rim at Z = target_dims[2] - 0.08, and 4 corner brass eye-rings if the Tripo GLB is not yet on disk.
    """
    mesh_name = f"PROC_Mesh_{preset_id}"
    old = bpy.data.meshes.get(mesh_name)
    if old:
        bpy.data.meshes.remove(old, do_unlink=True)
    mesh = bpy.data.meshes.new(mesh_name)

    w_mat = _get_or_create_material("AF_CB_WickerWood_Mat", (0.28, 0.17, 0.09), metallic=0.05, roughness=0.62)
    b_mat = _get_or_create_material("AF_CB_AgedBrass_Mat", (0.80, 0.60, 0.22), metallic=0.88, roughness=0.28)
    i_mat = _get_or_create_material("AF_CB_ForgedIron_Mat", (0.20, 0.22, 0.25), metallic=0.82, roughness=0.38)
    c_mat = _get_or_create_material("AF_CB_BlueIce_Mat", (0.25, 0.78, 0.98), metallic=0.10, roughness=0.18, emission_color=(0.18, 0.68, 0.96), emission_strength=1.4)

    mesh.materials.append(w_mat)  # slot 0
    mesh.materials.append(b_mat)  # slot 1
    mesh.materials.append(i_mat)  # slot 2
    mesh.materials.append(c_mat)  # slot 3

    bm = bmesh.new()
    wx, wy, hz = target_dims
    rx, ry = wx * 0.5, wy * 0.5
    wall_t = 0.075
    z_bot = -0.08
    z_floor = 0.00
    z_top = hz - 0.08

    is_oct = "OCT" in preset_id or "HALF" in preset_id
    sides = 8 if is_oct else 4
    angle_offset = (math.pi / 8.0) if is_oct else (math.pi / 4.0)
    scale_corr = 1.08 if is_oct else math.sqrt(2.0)

    outer_bot, outer_top, inner_floor, inner_top = [], [], [], []
    for s in range(sides):
        ang = angle_offset + 2.0 * math.pi * s / sides
        ca, sa = math.cos(ang) * scale_corr, math.sin(ang) * scale_corr
        ox = max(-rx, min(rx, ca * rx / scale_corr if is_oct else (rx if ca > 0 else -rx)))
        oy = max(-ry, min(ry, sa * ry / scale_corr if is_oct else (ry if sa > 0 else -ry)))
        if is_oct:
            ox = math.cos(ang) * rx
            oy = math.sin(ang) * ry
        ix = ox * (1.0 - wall_t / max(rx, 0.2))
        iy = oy * (1.0 - wall_t / max(ry, 0.2))
        outer_bot.append(bm.verts.new((ox, oy, z_bot)))
        outer_top.append(bm.verts.new((ox, oy, z_top)))
        inner_floor.append(bm.verts.new((ix, iy, z_floor)))
        inner_top.append(bm.verts.new((ix, iy, z_top)))

    for s in range(sides):
        ns = (s + 1) % sides
        # Outer wall
        f_out = bm.faces.new((outer_bot[s], outer_bot[ns], outer_top[ns], outer_top[s]))
        f_out.material_index = 0
        # Top brass rim
        f_rim = bm.faces.new((outer_top[s], outer_top[ns], inner_top[ns], inner_top[s]))
        f_rim.material_index = 1
        # Inner wall
        f_in = bm.faces.new((inner_top[s], inner_top[ns], inner_floor[ns], inner_floor[s]))
        f_in.material_index = 0

    # Inner standing floor face & bottom face
    f_fl = bm.faces.new(inner_floor)
    f_fl.material_index = 0
    f_bt = bm.faces.new(list(reversed(outer_bot)))
    f_bt.material_index = 2

    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _hollow_out_interior_standing_well(mesh_obj: bpy.types.Object, preset_id: str, target_dims: tuple):
    """
    Normalizes the imported Tripo 3D basket mesh outer bounding box to `target_dims` (`wx, wy, hz`)
    with outer base at `Z = -0.08 m`, preserves 100% of Tripo's 3D geometry (brass lifting rings,
    wicker walls, iron skids/rollers, and interior compartment), and measures the interior standing
    floor height `af_cb_floor_z` where the Elf's boots stand.
    """
    mesh = mesh_obj.data
    if not mesh or not mesh.vertices:
        return

    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    cur_wx = max(max_x - min_x, 1e-4)
    cur_wy = max(max_y - min_y, 1e-4)
    cur_hz = max(max_z - min_z, 1e-4)

    cx = 0.5 * (min_x + max_x)
    cy = 0.5 * (min_y + max_y)

    twx, twy, thz = target_dims
    sx = twx / cur_wx
    sy = twy / cur_wy
    sz = thz / cur_hz
    z_bot_target = -0.08

    for v in mesh.vertices:
        v.co.x = (v.co.x - cx) * sx
        v.co.y = (v.co.y - cy) * sy
        v.co.z = (v.co.z - min_z) * sz + z_bot_target

    # Carve/depress a clean flat interior standing floor well at Z = 0.04 m in the Elf standing zone
    # so the Elf stands waist-deep inside the basket behind the outer wicker/timber walls & brass rim.
    if preset_id in ("BASKET_01_OCT_EMPTY", "BASKET_02_GONDOLA_EMPTY", "BASKET_03_HALF_MINER"):
        sample_cx = -0.34 if preset_id == "BASKET_03_HALF_MINER" else 0.0
        rx_well = 0.42 if preset_id == "BASKET_03_HALF_MINER" else (twx * 0.34)
        ry_well = twy * 0.32
        for v in mesh.vertices:
            dx = abs(v.co.x - sample_cx) / max(rx_well, 1e-4)
            dy = abs(v.co.y) / max(ry_well, 1e-4)
            radial = max(dx, dy) if "GONDOLA" in preset_id else math.hypot(dx, dy)
            if radial < 1.0 and 0.04 < v.co.z < (thz * 0.82):
                # Smooth blend near the inner wall edge (0.82..1.0)
                t = max(0.0, min(1.0, (radial - 0.82) / 0.18))
                v.co.z = 0.04 * (1.0 - t) + v.co.z * t
        floor_z = 0.04
    else:
        floor_z = 0.20

    mesh["af_cb_floor_z"] = float(floor_z)
    mesh.update()


def _resolve_model_file_path(filename: str) -> str:
    """Finds either `.glb` or `.fbx` (Tripo `--quad` native output) in `CLIFF_GLB_DIR`."""
    stem = os.path.splitext(filename)[0]
    for ext in (".glb", ".fbx", ".gltf"):
        cand = os.path.join(CLIFF_GLB_DIR, stem + ext)
        if os.path.isfile(cand) and os.path.getsize(cand) > 30_000:
            return cand
    return os.path.join(CLIFF_GLB_DIR, filename)


def _import_3d_file_objects(filepath: str) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    else:
        bpy.ops.import_scene.gltf(filepath=filepath)
    return [o for o in bpy.data.objects if o not in before]


def load_or_build_basket_mesh_object(name: str, preset_id: str, collection: bpy.types.Collection) -> bpy.types.Object:
    """
    Loads the Tripo 3D `.glb` or `.fbx` basket model for `preset_id` if available in `assets/models/glb/cliff_baskets/`,
    normalizes its scale & hollow interior floor (`Z=0.0`), and links it to `collection`.
    Falls back to `_build_procedural_basket_fallback_mesh` if the model file is not yet on disk.
    """
    preset_map = {p[0]: p for p in CLIFF_BASKET_PRESETS}
    _, _, glb_filename, target_dims = preset_map.get(preset_id, CLIFF_BASKET_PRESETS[0])
    model_path = _resolve_model_file_path(glb_filename)

    tpl_mesh_name = f"TPL_CB_Mesh_{preset_id}"
    cached_mesh = bpy.data.meshes.get(tpl_mesh_name)

    if not cached_mesh and os.path.isfile(model_path):
        try:
            imported = _import_3d_file_objects(model_path)
            mesh_objs = [o for o in imported if o.type == "MESH" and o.data and len(o.data.vertices) > 0]
            if mesh_objs:
                mesh_objs.sort(key=lambda o: len(o.data.vertices), reverse=True)
                primary = mesh_objs[0]
                mw_rot = primary.matrix_world.to_3x3()
                cached_mesh = primary.data.copy()
                cached_mesh.name = tpl_mesh_name
                for v in cached_mesh.vertices:
                    v.co = mw_rot @ v.co
                temp_obj = bpy.data.objects.new("_tmp_norm", cached_mesh)
                _hollow_out_interior_standing_well(temp_obj, preset_id, target_dims)
                bpy.data.objects.remove(temp_obj, do_unlink=True)
            for o in imported:
                if o.name in bpy.data.objects:
                    bpy.data.objects.remove(o, do_unlink=True)
        except Exception as exc:
            print(f"[CliffBaskets] 3D import warning for {model_path}: {exc}")

    if not cached_mesh:
        cached_mesh = _build_procedural_basket_fallback_mesh(preset_id, target_dims)

    obj = bpy.data.objects.new(name, cached_mesh)
    collection.objects.link(obj)
    obj["af_cb_preset_id"] = preset_id
    obj["af_cb_using_tripo_glb"] = bool(cached_mesh.name == tpl_mesh_name)
    return obj


def load_or_build_cargo_prop_object(name: str, cargo_id: str, collection: bpy.types.Collection) -> bpy.types.Object:
    """Loads a modular cargo prop (`CARGO_A_ICE`, `CARGO_B_TOOLS`, `CARGO_C_BARREL`) from Tripo GLB/FBX or procedural fallback."""
    cargo_map = {c[0]: c for c in CLIFF_CARGO_PRESETS}
    _, _, glb_filename, target_dims, default_loc = cargo_map.get(cargo_id, CLIFF_CARGO_PRESETS[0])
    model_path = _resolve_model_file_path(glb_filename)

    tpl_mesh_name = f"TPL_CB_Cargo_{cargo_id}"
    cached_mesh = bpy.data.meshes.get(tpl_mesh_name)

    if not cached_mesh and os.path.isfile(model_path):
        try:
            imported = _import_3d_file_objects(model_path)
            mesh_objs = [o for o in imported if o.type == "MESH" and o.data and len(o.data.vertices) > 0]
            if mesh_objs:
                mesh_objs.sort(key=lambda o: len(o.data.vertices), reverse=True)
                primary = mesh_objs[0]
                mw_rot = primary.matrix_world.to_3x3()
                cached_mesh = primary.data.copy()
                cached_mesh.name = tpl_mesh_name
                for v in cached_mesh.vertices:
                    v.co = mw_rot @ v.co
                xs = [v.co.x for v in cached_mesh.vertices]
                ys = [v.co.y for v in cached_mesh.vertices]
                zs = [v.co.z for v in cached_mesh.vertices]
                cx, cy, min_z = 0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys)), min(zs)
                sx = target_dims[0] / max(max(xs) - min(xs), 1e-4)
                sy = target_dims[1] / max(max(ys) - min(ys), 1e-4)
                sz = target_dims[2] / max(max(zs) - min(zs), 1e-4)
                s_uni = min(sx, sy, sz)
                for v in cached_mesh.vertices:
                    v.co.x = (v.co.x - cx) * s_uni
                    v.co.y = (v.co.y - cy) * s_uni
                    v.co.z = (v.co.z - min_z) * s_uni
                cached_mesh.update()
            for o in imported:
                if o.name in bpy.data.objects:
                    bpy.data.objects.remove(o, do_unlink=True)
        except Exception as exc:
            print(f"[CliffBaskets] Cargo 3D import warning for {model_path}: {exc}")

    if not cached_mesh:
        cached_mesh = bpy.data.meshes.new(f"PROC_Cargo_{cargo_id}")
        bm = bmesh.new()
        if "ICE" in cargo_id:
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=target_dims[0] * 0.45)
            mat = _get_or_create_material("AF_CB_BlueIce_Mat", (0.25, 0.78, 0.98), roughness=0.18, emission_color=(0.18, 0.68, 0.96), emission_strength=1.4)
        elif "TOOLS" in cargo_id:
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=target_dims, verts=bm.verts)
            mat = _get_or_create_material("AF_CB_WickerWood_Mat", (0.28, 0.17, 0.09), roughness=0.62)
        else:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=target_dims[0] * 0.48, radius2=target_dims[0] * 0.44, depth=target_dims[2])
            mat = _get_or_create_material("AF_CB_AgedBrass_Mat", (0.80, 0.60, 0.22), metallic=0.88, roughness=0.28)
        for v in bm.verts:
            v.co.z += target_dims[2] * 0.5
        bm.to_mesh(cached_mesh)
        bm.free()
        cached_mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, cached_mesh)
    obj.location = default_loc
    obj["af_is_editable_prop"] = True
    obj["af_cb_cargo_id"] = cargo_id
    collection.objects.link(obj)
    return obj


# ============================================================================
# 2. GEOMETRY NODES & PROCEDURAL 3D ROPE + SHACKLE + PULLEY BUILDER
# ============================================================================

def ensure_cliff_rope_geonodes_group() -> bpy.types.NodeTree:
    """
    Creates or returns the `GN_Cliff_Basket_Rope_Rig` Geometry Nodes group that
    converts the poly-spline rope curves into 3D braided hemp/steel cables with
    UVs and material assignment.
    """
    gn_name = "GN_Cliff_Basket_Rope_Rig"
    ng = bpy.data.node_groups.get(gn_name)
    if ng:
        return ng

    ng = bpy.data.node_groups.new(gn_name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    s_rad = ng.interface.new_socket(name="*1: Debljina Užeta (m)", in_out="INPUT", socket_type="NodeSocketFloat")
    s_rad.default_value = 0.018
    s_rad.min_value = 0.005
    s_rad.max_value = 0.060
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes = ng.nodes
    links = ng.links
    nodes.clear()

    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-450, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (450, 0)

    n_prof = nodes.new("GeometryNodeCurvePrimitiveCircle")
    n_prof.location = (-200, -180)
    n_prof.inputs["Resolution"].default_value = 10

    n_c2m = nodes.new("GeometryNodeCurveToMesh")
    n_c2m.location = (60, 0)
    if "Fill Caps" in n_c2m.inputs:
        n_c2m.inputs["Fill Caps"].default_value = True

    n_mat = nodes.new("GeometryNodeSetMaterial")
    n_mat.location = (260, 0)
    rope_mat = _get_or_create_material("AF_CB_HempSteelRope_Mat", (0.46, 0.36, 0.22), metallic=0.15, roughness=0.72)
    n_mat.inputs["Material"].default_value = rope_mat

    links.new(n_in.outputs["Geometry"], n_c2m.inputs["Curve"])
    links.new(n_in.outputs["*1: Debljina Užeta (m)"], n_prof.inputs["Radius"])
    links.new(n_prof.outputs["Curve"], n_c2m.inputs["Profile Curve"])
    links.new(n_c2m.outputs["Mesh"], n_mat.inputs["Geometry"])
    links.new(n_mat.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


def update_rope_assembly_curves_for_rig(rig_root: bpy.types.Object, vib_amp_m: float = 0.0, vib_phase: float = 0.0):
    """
    Recomputes the 3D Curve splines of `ROPE_Assembly_<ID>` in real time from the current
    positions of `GIZMO_Pin_01..04`, `GIZMO_SpreaderHook`, and `GIZMO_TopWinch`!
    Also positions the 3D forged iron shackle rings at each active pin.
    """
    if not rig_root:
        return
    rope_obj = bpy.data.objects.get(rig_root.get("af_cb_rope_obj", ""))
    basket_body = bpy.data.objects.get(rig_root.get("af_cb_basket_body", ""))
    spreader = bpy.data.objects.get(rig_root.get("af_cb_spreader_gizmo", ""))
    winch = bpy.data.objects.get(rig_root.get("af_cb_winch_gizmo", ""))
    if not rope_obj or rope_obj.type != "CURVE" or not basket_body or not spreader or not winch:
        return

    num_pins = int(rig_root.get("af_cb_num_ropes", 4))
    rope_mode = rig_root.get("af_cb_rope_mode", "SPREADER_4_TO_1")
    slack_m = float(rig_root.get("af_cb_rope_slack_m", 0.035))

    pin_names = [
        rig_root.get("af_cb_pin_01", ""),
        rig_root.get("af_cb_pin_02", ""),
        rig_root.get("af_cb_pin_03", ""),
        rig_root.get("af_cb_pin_04", ""),
    ]
    pins = [bpy.data.objects.get(pn) for pn in pin_names]

    # Pick active pins based on `num_pins` (2, 3, or 4)
    if num_pins == 2:
        active_indices = [0, 2]
    elif num_pins == 3:
        active_indices = [0, 1, 2]
    else:
        active_indices = [0, 1, 2, 3]

    # Toggle visibility of inactive pin gizmos so the user clearly sees which 2, 3, or 4 pins are active
    for idx, p_obj in enumerate(pins):
        if p_obj:
            p_obj.hide_viewport = (idx not in active_indices)

    # Convert gizmo positions into `rig_root` local space (since `rope_obj` is parented to `rig_root` at identity)
    b_pos = Vector(basket_body.location)
    b_rot = Euler(basket_body.rotation_euler, "XYZ").to_matrix()

    def basket_child_to_root(child_obj) -> Vector:
        return b_pos + (b_rot @ Vector(child_obj.location))

    p_spreader = basket_child_to_root(spreader)
    p_winch = Vector(winch.location)

    curve_data = rope_obj.data
    curve_data.splines.clear()
    segs_per_rope = 9

    def add_catenary_spline(p_start: Vector, p_end: Vector, sag: float, vib_sign: float):
        sp = curve_data.splines.new("POLY")
        sp.points.add(segs_per_rope - 1)
        chord = p_end - p_start
        chord_len = max(chord.length, 1e-4)
        # Perpendicular horizontal normal for transverse string vibration
        perp = Vector((chord.y, -chord.x, 0.0))
        if perp.length > 1e-4:
            perp.normalize()
        else:
            perp = Vector((1.0, 0.0, 0.0))

        for k in range(segs_per_rope):
            u = k / float(segs_per_rope - 1)
            pt = p_start.lerp(p_end, u)
            arch = 4.0 * u * (1.0 - u)
            pt.z -= sag * arch
            if abs(vib_amp_m) > 1e-5:
                wave = math.sin(math.pi * u) * math.sin(vib_phase + u * math.pi * 2.0)
                pt += perp * (vib_amp_m * vib_sign * wave)
                pt.y += 0.5 * vib_amp_m * math.sin(math.pi * u) * math.cos(vib_phase)
            sp.points[k].co = (pt.x, pt.y, pt.z, 1.0)

    if rope_mode == "PARALLEL":
        spreader.hide_viewport = True
        for idx in active_indices:
            p_obj = pins[idx]
            if not p_obj:
                continue
            p_pin = basket_child_to_root(p_obj)
            # Parallel top anchor offset matching pin XY around winch
            p_top = Vector((p_winch.x + p_obj.location.x * 0.85, p_winch.y + p_obj.location.y * 0.85, p_winch.z))
            add_catenary_spline(p_pin, p_top, slack_m * 0.6, 1.0 if idx % 2 == 0 else -1.0)
    else:
        spreader.hide_viewport = False
        for idx in active_indices:
            p_obj = pins[idx]
            if not p_obj:
                continue
            p_pin = basket_child_to_root(p_obj)
            add_catenary_spline(p_pin, p_spreader, slack_m, 1.0 if idx % 2 == 0 else -1.0)
        # Main vertical hoist cable from Spreader Hook up to Top Winch Pulley
        add_catenary_spline(p_spreader, p_winch, slack_m * 0.25, 1.0)


# ============================================================================
# 3. ANALYTICAL DAMPED PENDULUM + WINCH STOP + PICKAXE RECOIL PHYSICS SOLVER
# ============================================================================

def _collect_pickaxe_strike_frames_for_elf(ctrl_obj: bpy.types.Object, scene: bpy.types.Scene, hit_offset_frames: int = 0) -> list[float]:
    """
    Inspects the mounted Elf's NLA strips (or active single Action) directly on `arm_obj.animation_data`
    (100% context-free for frame_change_post safety) and returns a sorted list of exact timeline frames
    `f_hit` where the Elf strikes the cliff wall with the pickaxe!
    """
    if not ctrl_obj:
        return []

    local_strike_frames_in_cycle = (34.0, 92.0)
    cycle_len = 120.0
    hit_frames = []

    arm_obj = get_character_armature_from_ctrl(ctrl_obj)
    adt = arm_obj.animation_data if arm_obj else None

    found_nla_strips = False
    if adt and adt.nla_tracks:
        for tr in adt.nla_tracks:
            if tr.mute or tr.name.startswith("AF_Additive"):
                continue
            for s in tr.strips:
                found_nla_strips = True
                act_name = s.action.name if s.action else s.name
                if not any(k in act_name.upper() for k in ("MINE", "PICKAXE", "27", "CHOP", "HAMMER")):
                    continue
                f_s = float(s.frame_start)
                f_e = float(s.frame_end)
                scale = max(0.1, float(s.scale))
                eff_cycle = cycle_len * scale
                n_cycles = max(1, int(math.ceil((f_e - f_s) / max(eff_cycle, 1.0))) + 1)
                for c_idx in range(n_cycles):
                    for loc_hit in local_strike_frames_in_cycle:
                        f_world = f_s + c_idx * eff_cycle + loc_hit * scale + float(hit_offset_frames)
                        if f_s + 4.0 <= f_world <= f_e - 2.0:
                            hit_frames.append(round(f_world, 2))

    if not found_nla_strips:
        act_name = ctrl_obj.get("af_anim_name", "")
        if any(k in act_name.upper() for k in ("MINE", "PICKAXE", "27", "CHOP", "HAMMER")):
            spd = max(0.1, float(ctrl_obj.get("af_anim_speed", 1.0)))
            f_off = float(ctrl_obj.get("af_frame_offset", 0))
            eff_cycle = cycle_len / spd
            f_min = float(scene.frame_start) if scene else 1.0
            f_max = float(scene.frame_end) if scene else 360.0
            mine_end = float(ctrl_obj.get("af_cb_mine_stop_frame", 0))
            if mine_end > f_min:
                f_max = min(f_max, mine_end)
            n_cycles = max(1, int(math.ceil((f_max - f_min + eff_cycle) / max(eff_cycle, 1.0))) + 1)
            for c_idx in range(-1, n_cycles):
                for loc_hit in local_strike_frames_in_cycle:
                    f_world = f_min + f_off + c_idx * eff_cycle + (loc_hit / spd) + float(hit_offset_frames)
                    if f_min <= f_world <= f_max:
                        hit_frames.append(round(f_world, 2))

    return sorted(set(hit_frames))


_CB_PROP_SYNC_GUARD = False
_LAST_WALL_SIG = None


def _eval_animatable_float_prop(obj: bpy.types.Object, prop_name: str, frame: float, fallback: float) -> tuple[float, bool]:
    """
    Evaluates an animatable property `prop_name` on `obj` at `frame` if an F-curve exists
    (supporting Blender 4.x and Blender 5.x slotted/layered actions), otherwise reads the live
    RNA property or custom-property fallback. Returns `(value, has_fcurve)`.
    """
    if not obj:
        return float(fallback), False
    adt = getattr(obj, "animation_data", None)
    act = getattr(adt, "action", None) if adt else None
    if act:
        fcurves = getattr(act, "fcurves", None)
        if fcurves:
            for dp in (prop_name, f'["{prop_name}"]'):
                fc = fcurves.find(dp)
                if fc:
                    return float(fc.evaluate(frame)), True
        # Blender 5.x layered action channelbags fallback
        layers = getattr(act, "layers", None)
        if layers:
            for layer in layers:
                for strip in getattr(layer, "strips", ()):
                    for cbag in getattr(strip, "channelbags", ()):
                        fcs = getattr(cbag, "fcurves", None)
                        if fcs:
                            for dp in (prop_name, f'["{prop_name}"]'):
                                fc = fcs.find(dp)
                                if fc:
                                    return float(fc.evaluate(frame)), True
    if hasattr(obj, prop_name):
        try:
            return float(getattr(obj, prop_name)), False
        except Exception:
            pass
    if prop_name in obj:
        try:
            return float(obj[prop_name]), False
        except Exception:
            pass
    return float(fallback), False


def evaluate_basket_physics_at_frame(rig_root: bpy.types.Object, frame: float, scene: bpy.types.Scene = None) -> dict:
    r"""
    Evaluates the exact analytical position, rotation, rope vibration, pulley angle, and ice burst state
    for `rig_root` at `frame`:
      1. Top Winch Null (`af_cb_top_anchor_z`) + Animatable Lowering Slider (`af_cb_drop_alpha` / `af_cb_drop_depth_m`
         out of `af_cb_max_drop_depth_m`) + Quintic S-curve Winch Lowering/Stopping & Damped Braking Bounce.
      2. True Rope-Length-Dependent Pendulum Frequency $\omega_0(f) = \sqrt{g / L(f)}$ where
         $L(f) = \max(1.20\,\text{m},\; \text{drop\_depth}(f))$.
      3. Pickaxe Wall-Strike Push-Off Recoil (`+Y` away from `-Y` wall in rig_root local space) +
         Pitch/Roll Tilt Kick + Lateral Sway -> Exponential Decay ($e^{-\gamma \Delta t}$) to `0.000 m`.
      4. One-Way Wall Bumper Clamp so front iron skids/rollers bounce off the cliff wall (`Y >= -wall_gap`).
    """
    scn = scene or bpy.context.scene
    fps = float(scn.render.fps) / max(1.0, float(scn.render.fps_base))

    # Parameters stored on `rig_root`
    winch_mode = rig_root.get("af_cb_winch_mode", "LOWER_AND_STOP")
    z_start = float(rig_root.get("af_cb_z_start", 2.20))
    z_work_base = float(rig_root.get("af_cb_z_work", 0.00))
    f_lower_start = float(rig_root.get("af_cb_lower_start_frame", 1))
    f_lower_stop = float(rig_root.get("af_cb_lower_stop_frame", 55))

    recoil_cm = float(rig_root.get("af_cb_recoil_cm", 14.5))
    tilt_kick_deg = float(rig_root.get("af_cb_tilt_kick_deg", 7.5))
    damping_gamma = float(rig_root.get("af_cb_damping", 1.55))
    wall_gap_offset_m, _ = _eval_animatable_float_prop(
        rig_root,
        "af_cb_wall_gap_offset_m",
        frame,
        float(rig_root.get("af_cb_wall_gap_cm", 15.0)) * 0.01,
    )
    wall_gap_cm = max(float(rig_root.get("af_cb_wall_gap_cm", 5.0)), wall_gap_offset_m * 100.0 * 0.35)
    wall_restitution = float(rig_root.get("af_cb_wall_restitution", 0.30))
    hit_offset_f = int(rig_root.get("af_cb_hit_frame_offset", 0))

    winch_obj = bpy.data.objects.get(rig_root.get("af_cb_winch_gizmo", ""))
    default_winch_local_z = float(winch_obj.location.z) if winch_obj else 6.50
    top_anchor_world_z, has_top_fc = _eval_animatable_float_prop(
        rig_root,
        "af_cb_top_anchor_z",
        frame,
        float(rig_root.location.z) + default_winch_local_z,
    )
    winch_z = max(1.35, top_anchor_world_z - float(rig_root.location.z))
    if winch_obj and (has_top_fc or abs(winch_obj.location.z - winch_z) > 1e-4):
        winch_obj.location.z = winch_z

    # Evaluate animatable Drop Alpha (0.0 .. 1.0) & Drop Depth (m)
    max_drop_m, _ = _eval_animatable_float_prop(
        rig_root,
        "af_cb_max_drop_depth_m",
        frame,
        max(12.0, winch_z * 1.5),
    )
    max_drop_m = max(1.20, max_drop_m)
    default_alpha = min(1.0, max(0.0, winch_z / max_drop_m))
    alpha_f, has_alpha_fc = _eval_animatable_float_prop(rig_root, "af_cb_drop_alpha", frame, default_alpha)
    depth_f, has_depth_fc = _eval_animatable_float_prop(rig_root, "af_cb_drop_depth_m", frame, alpha_f * max_drop_m)

    # Minimum physical rope clearance from Top Winch Pulley to basket floor so SpreaderHook (+2.45m) stays below pulley
    min_drop_m = min(2.55, winch_z - 0.15)
    if not has_alpha_fc and not has_depth_fc and not bool(rig_root.get("af_cb_manual_drop_override", False)):
        target_drop_m = winch_z - z_work_base
    elif has_depth_fc and not has_alpha_fc:
        target_drop_m = max(1.20, depth_f)
    else:
        alpha_clamped = max(0.0, min(1.0, alpha_f))
        target_drop_m = min_drop_m + alpha_clamped * max(0.0, max_drop_m - min_drop_m)
        if not has_alpha_fc and abs(alpha_clamped - default_alpha) < 1e-3:
            target_drop_m = winch_z - z_work_base

    # Working local Z of the basket floor corresponding to `target_drop_m` below `winch_z`
    z_work = winch_z - target_drop_m

    # --- A. Winch Vertical Trajectory Z(f) & Braking Inertia ---
    brake_sway_y = 0.0
    brake_bounce_z = 0.0
    brake_pitch_rad = 0.0

    if has_alpha_fc or has_depth_fc:
        # Keyframed Drop Alpha / Drop Depth curve drives vertical trajectory directly + velocity/acceleration inertia
        cur_z = z_work
        a_prev, _ = _eval_animatable_float_prop(rig_root, "af_cb_drop_alpha", frame - 1.0, alpha_f)
        a_next, _ = _eval_animatable_float_prop(rig_root, "af_cb_drop_alpha", frame + 1.0, alpha_f)
        d_prev = min_drop_m + max(0.0, min(1.0, a_prev)) * max(0.0, max_drop_m - min_drop_m)
        d_next = min_drop_m + max(0.0, min(1.0, a_next)) * max(0.0, max_drop_m - min_drop_m)
        vel_l = (d_next - d_prev) * 0.5 * fps
        acc_l = (d_next - 2.0 * target_drop_m + d_prev) * (fps * fps)
        t_sec = frame / fps
        if abs(vel_l) > 0.01:
            sway_env = min(1.0, abs(vel_l) / 1.5)
            brake_sway_y += 0.026 * sway_env * math.sin(2.4 * t_sec)
            brake_pitch_rad += math.radians(1.7) * sway_env * math.cos(2.4 * t_sec)
        if abs(acc_l) > 0.05:
            brake_bounce_z += max(-0.045, min(0.045, -0.008 * acc_l))
    elif winch_mode == "STATIONARY":
        cur_z = z_work
    else:
        z_top_start = min(winch_z - min_drop_m, z_work + max(0.5, z_start))
        z_a = z_top_start if winch_mode == "LOWER_AND_STOP" else z_work
        z_b = z_work if winch_mode == "LOWER_AND_STOP" else z_top_start
        dur_f = max(1.0, f_lower_stop - f_lower_start)
        if frame <= f_lower_start:
            cur_z = z_a
        elif frame < f_lower_stop:
            u = (frame - f_lower_start) / dur_f
            # Quintic smoothstep C2 curve
            s = u * u * u * (10.0 + u * (-15.0 + 6.0 * u))
            cur_z = z_a + (z_b - z_a) * s
            # Gentle travel sway during descent
            travel_env = math.sin(math.pi * u)
            t_desc = (frame - f_lower_start) / fps
            brake_sway_y += 0.025 * travel_env * math.sin(2.4 * t_desc)
            brake_pitch_rad += math.radians(1.6) * travel_env * math.cos(2.4 * t_desc)
        else:
            cur_z = z_b
            dt_stop = (frame - f_lower_stop) / fps
            decay_stop = math.exp(-damping_gamma * 1.35 * dt_stop)
            if decay_stop > 1e-4:
                # Damped vertical rope stretch bounce + pendulum settle at stop
                drop_sign = -1.0 if z_b < z_a else 1.0
                brake_bounce_z = drop_sign * 0.032 * decay_stop * math.sin(11.5 * dt_stop)
                brake_sway_y += 0.042 * decay_stop * math.sin(3.4 * dt_stop)
                brake_pitch_rad += math.radians(2.8) * decay_stop * math.sin(4.2 * dt_stop + 0.3)

    # Effective rope pendulum length L(f) = max(1.20 m, drop_depth(f)) from Top Winch down to Basket
    rope_len = max(1.20, winch_z - cur_z)
    omega_0 = math.sqrt(9.81 / rope_len)

    # --- B. Pickaxe Strike Push-Off Recoil & Damped Pendulum Sum ---
    ctrl_obj = bpy.data.objects.get(rig_root.get("af_cb_elf_ctrl", ""))
    hit_frames = _collect_pickaxe_strike_frames_for_elf(ctrl_obj, scn, hit_offset_frames=hit_offset_f)

    # Keep only hits after winch has reached the working zone (if lowering first)
    if winch_mode == "LOWER_AND_STOP" and not (has_alpha_fc or has_depth_fc):
        hit_frames = [hf for hf in hit_frames if hf >= f_lower_stop - 4.0]

    recoil_m = recoil_cm * 0.01
    tilt_rad = math.radians(tilt_kick_deg)

    dy_push = brake_sway_y
    dx_lat = 0.0
    dz_total = cur_z + brake_bounce_z
    pitch_x = brake_pitch_rad
    roll_y = 0.0
    yaw_z = 0.0
    vib_amp = 0.0
    vib_phase = 0.0
    active_burst_dt = -1.0

    for k_idx, f_hit in enumerate(hit_frames):
        dt = (frame - f_hit) / fps
        alt_sign = 1.0 if (k_idx % 2 == 0) else -1.0

        # 1. Pre-strike Wind-Up anticipation (-0.38s .. 0.0s before impact)
        if -0.38 <= dt < 0.0:
            u_pre = (dt + 0.38) / 0.38
            pre_bell = math.sin(math.pi * u_pre)
            # Slight lean toward the wall (-Y) as the Elf winds up
            dy_push -= 0.16 * recoil_m * pre_bell
            pitch_x -= 0.22 * tilt_rad * pre_bell

        # 2. Post-strike Push-Off Recoil (+Y away from -Y cliff wall) & Damped Pendulum Swing
        elif 0.0 <= dt < 8.0:
            env_pend = math.exp(-damping_gamma * dt)
            env_rot = math.exp(-damping_gamma * 1.32 * dt)
            if env_pend > 1e-4:
                # Primary push-off away from wall (+Y) followed by damped pendulum return
                dy_push += recoil_m * env_pend * math.sin(omega_0 * dt + 0.18)
                # Subtle lateral X sway along wall
                dx_lat += 0.24 * recoil_m * alt_sign * env_pend * math.sin(0.88 * omega_0 * dt)
                # Vertical upward kick at moment of downward pickaxe strike
                dz_total += 0.18 * recoil_m * env_rot * math.sin(2.6 * omega_0 * dt)
                # Rotational pitch kick (tilts rim back +X rotation when pushed off)
                pitch_x += tilt_rad * env_rot * math.sin(1.42 * omega_0 * dt + 0.24)
                roll_y += 0.38 * tilt_rad * alt_sign * env_rot * math.sin(1.25 * omega_0 * dt)
                yaw_z += 0.28 * tilt_rad * alt_sign * env_rot * math.sin(0.95 * omega_0 * dt)

            # Transverse rope tension vibration over first 0.75s after strike
            env_vib = math.exp(-5.2 * dt)
            if env_vib > 1e-3:
                vib_amp = max(vib_amp, 0.022 * (recoil_cm / 14.5) * env_vib)
                vib_phase = 28.0 * dt

            if 0.0 <= dt <= 0.65:
                if active_burst_dt < 0.0 or dt < active_burst_dt:
                    active_burst_dt = dt

    # --- C. One-Way Cliff Wall Bumper Clamp (prevents clipping into -Y cliff face) ---
    min_y_wall = -(wall_gap_cm * 0.01)
    if dy_push < min_y_wall:
        penetration = min_y_wall - dy_push
        dy_push = min_y_wall + wall_restitution * penetration
        # Slight bumper pitch deflection on wall contact
        pitch_x += min(math.radians(3.5), penetration * 0.85)

    # Deadband snap to pure 0.0000 when damped below 0.15 mm so when stopped it stands 100% motionless
    if abs(dy_push) < 1.5e-4:
        dy_push = 0.0
    if abs(dx_lat) < 1.5e-4:
        dx_lat = 0.0
    if abs(pitch_x) < 1.5e-4:
        pitch_x = 0.0
    if abs(roll_y) < 1.5e-4:
        roll_y = 0.0
    if abs(yaw_z) < 1.5e-4:
        yaw_z = 0.0

    # Pulley wheel rotation angle: theta(f) = -L(f) / R_pulley
    pulley_radius = 0.18
    pulley_angle_rad = -rope_len / pulley_radius

    return {
        "location": Vector((dx_lat, dy_push, dz_total)),
        "rotation_euler": Euler((pitch_x, roll_y, yaw_z), "XYZ"),
        "vib_amp": vib_amp,
        "vib_phase": vib_phase,
        "pulley_angle_rad": pulley_angle_rad,
        "burst_dt": active_burst_dt,
        "rope_len": rope_len,
        "omega_0": omega_0,
    }


def apply_basket_physics_to_rig(rig_root: bpy.types.Object, frame: float, scene: bpy.types.Scene = None):
    """Applies the evaluated analytical physics state to `BASKET_Body`, `ROPE_Assembly`, `WinchPulley`, and `VFX_IceBurst`."""
    if not rig_root or not bool(rig_root.get("af_cb_use_procedural_physics", True)):
        # Still update the Geometry Nodes ropes from current (baked/manual) basket transform!
        update_rope_assembly_curves_for_rig(rig_root, 0.0, 0.0)
        return

    basket_body = bpy.data.objects.get(rig_root.get("af_cb_basket_body", ""))
    if not basket_body:
        return

    state = evaluate_basket_physics_at_frame(rig_root, frame, scene=scene)
    basket_body.location = state["location"]
    basket_body.rotation_mode = "XYZ"
    basket_body.rotation_euler = state["rotation_euler"]

    # Rotate Top Winch Pulley wheel
    pulley_wheel = bpy.data.objects.get(rig_root.get("af_cb_pulley_wheel", ""))
    if pulley_wheel:
        pulley_wheel.rotation_mode = "XYZ"
        pulley_wheel.rotation_euler = (state["pulley_angle_rad"], 0.0, 0.0)

    # Keep Wall Impact Target (`GIZMO_WallTarget`) at the Elf's pickaxe strike height (`cur_z + 1.05 m`)
    burst_obj = bpy.data.objects.get(rig_root.get("af_cb_ice_burst", ""))
    wall_target = bpy.data.objects.get(rig_root.get("af_cb_wall_gizmo", ""))
    if wall_target:
        wall_target.location.z = state["location"].z + 1.05

    # Update Blue-Ice Shard Burst VFX at `GIZMO_WallTarget`
    if burst_obj and wall_target:
        b_dt = state["burst_dt"]
        if 0.0 <= b_dt <= 0.60:
            burst_obj.hide_viewport = False
            burst_obj.hide_render = False
            u_b = b_dt / 0.60
            sc = 0.25 + 1.45 * math.sin(math.pi * min(1.0, u_b * 1.3))
            burst_obj.location = (
                wall_target.location.x,
                wall_target.location.y + 0.14 * u_b,
                wall_target.location.z - 0.55 * (u_b * u_b),
            )
            burst_obj.scale = (sc, sc, sc)
            burst_obj.rotation_euler = (u_b * 3.5, u_b * 2.2, u_b * 4.1)
        else:
            burst_obj.hide_viewport = True
            burst_obj.hide_render = True

    # Update procedural 3D rope curves & transverse vibration
    update_rope_assembly_curves_for_rig(
        rig_root,
        vib_amp_m=state["vib_amp"],
        vib_phase=state["vib_phase"],
    )


@persistent
def af_cliff_baskets_frame_handler(scene, depsgraph=None):
    """Real-time frame_change_post handler evaluating all Cliff Basket rigs in the scene."""
    global _PHYSICS_EVAL_GUARD
    if _PHYSICS_EVAL_GUARD:
        return
    _PHYSICS_EVAL_GUARD = True
    try:
        frame = float(scene.frame_current)
        for rig_root in get_all_cliff_basket_rigs(scene):
            apply_basket_physics_to_rig(rig_root, frame, scene=scene)
    except Exception:
        pass
    finally:
        _PHYSICS_EVAL_GUARD = False


@persistent
def af_cliff_baskets_depsgraph_handler(scene, depsgraph=None):
    """
    Live interactive gizmo drag & glacier wall adaptation handler:
      1. Whenever the user moves any of the 4 Rope Attachment Gizmos (`GIZMO_Pin_01..04`),
         `GIZMO_SpreaderHook`, or `GIZMO_TopWinch` in the 3D Viewport, immediately updates
         the 3D Geometry Nodes ropes and syncs `af_cb_top_anchor_z`.
      2. When `scene.af_s3_auto_adapt_wall` is active and `GEO_Spilja_Desni_Ledeni_Zid`
         is moved or its modifier settings change, re-snaps scaffolding, rails, and baskets!
    """
    global _PHYSICS_EVAL_GUARD, _CB_PROP_SYNC_GUARD, _LAST_WALL_SIG
    if _PHYSICS_EVAL_GUARD or _CB_PROP_SYNC_GUARD or bpy.app.background:
        return
    context = bpy.context
    active = getattr(context, "active_object", None)
    if not active:
        return

    # Check if user moved/edited `GEO_Spilja_Desni_Ledeni_Zid` while Auto-Adapt is ON
    if active.name == "GEO_Spilja_Desni_Ledeni_Zid" and getattr(scene, "af_s3_auto_adapt_wall", True):
        mw = active.matrix_world
        sig = tuple(round(mw[r][c], 3) for r in range(3) for c in range(4))
        if _LAST_WALL_SIG is not None and sig != _LAST_WALL_SIG:
            _LAST_WALL_SIG = sig
            _PHYSICS_EVAL_GUARD = True
            try:
                standoff = float(getattr(scene, "af_s3_wall_standoff_m", 1.85))
                smooth = int(getattr(scene, "af_s3_wall_smoothing", 4))
                sync_scaffolding_and_rails_to_glacier_wall(context, wall_standoff_m=standoff, smoothing_window=smooth)
            except Exception:
                pass
            finally:
                _PHYSICS_EVAL_GUARD = False
            return
        _LAST_WALL_SIG = sig

    rig_root = find_cliff_basket_rig(active)
    if not rig_root:
        return
    _PHYSICS_EVAL_GUARD = True
    _CB_PROP_SYNC_GUARD = True
    try:
        winch_obj = bpy.data.objects.get(rig_root.get("af_cb_winch_gizmo", ""))
        if active == winch_obj and winch_obj is not None:
            new_top_z = float(rig_root.location.z) + float(winch_obj.location.z)
            if hasattr(rig_root, "af_cb_top_anchor_z"):
                rig_root.af_cb_top_anchor_z = round(new_top_z, 4)
        apply_basket_physics_to_rig(rig_root, float(scene.frame_current), scene=scene)
    except Exception:
        pass
    finally:
        _CB_PROP_SYNC_GUARD = False
        _PHYSICS_EVAL_GUARD = False


# ============================================================================
# 4. RIG SPAWNER, GIZMO HELPERS, SYMMETRIC MIRROR, AUTO-SNAP & BAKE TO F-CURVES
# ============================================================================

def get_all_cliff_basket_rigs(scene: bpy.types.Scene = None) -> list[bpy.types.Object]:
    scn = scene or getattr(bpy.context, "scene", None)
    if not scn:
        return []
    rigs = [o for o in scn.objects if o.get("af_is_cliff_basket_rig")]
    rigs.sort(key=lambda o: o.name)
    return rigs


def find_cliff_basket_rig(obj: bpy.types.Object) -> bpy.types.Object:
    """Walks up the parent chain or `af_cb_rig_root` tag to find the owning `CB_ROOT_*` rig."""
    curr = obj
    while curr:
        if curr.get("af_is_cliff_basket_rig"):
            return curr
        root_name = curr.get("af_cb_rig_root", "")
        if root_name and root_name in bpy.data.objects:
            return bpy.data.objects[root_name]
        curr = curr.parent
    return None


def get_active_cliff_basket_rig(context=None) -> bpy.types.Object:
    ctx = context or bpy.context
    active = getattr(ctx, "active_object", None)
    rig = find_cliff_basket_rig(active) if active else None
    if rig:
        return rig
    rigs = get_all_cliff_basket_rigs(getattr(ctx, "scene", None))
    return rigs[0] if rigs else None


def _default_pin_positions_for_preset(preset_id: str) -> list[tuple[float, float, float]]:
    """Returns default 4 corner brass eye-ring coordinates `[(x, y, z), ...]` on the top rim of `preset_id`."""
    preset_map = {p[0]: p for p in CLIFF_BASKET_PRESETS}
    _, _, _, (wx, wy, hz) = preset_map.get(preset_id, CLIFF_BASKET_PRESETS[0])
    z_rim = hz - 0.06
    if "OCT" in preset_id or "HALF" in preset_id:
        # 4 diagonal octagon corners at 45°, 135°, 225°, 315°
        px = wx * 0.5 * 0.74
        py = wy * 0.5 * 0.74
    else:
        px = wx * 0.5 * 0.90
        py = wy * 0.5 * 0.88
    return [
        (-px, -py, z_rim),  # Pin 1: Prednji-Desni (Front-Right, toward -Y cliff wall)
        ( px, -py, z_rim),  # Pin 2: Prednji-Lijevi (Front-Left, toward -Y cliff wall)
        ( px,  py, z_rim),  # Pin 3: Stražnji-Lijevi (Back-Left)
        (-px,  py, z_rim),  # Pin 4: Stražnji-Desni (Back-Right)
    ]


def auto_snap_4_gizmos_to_basket_rim(rig_root: bpy.types.Object) -> list[tuple[float, float, float]]:
    """
    Samples the top-rim vertices (`Z > 0.78 * max_z`) of the active 3D basket mesh in each of the
    4 quadrants (`(-X,-Y)`, `(+X,-Y)`, `(+X,+Y)`, `(-X,+Y)`) and snaps `GIZMO_Pin_01..04` onto
    the highest corner lifting-ring vertices of the Tripo 3D basket!
    """
    if not rig_root:
        return []
    mesh_obj = bpy.data.objects.get(rig_root.get("af_cb_basket_mesh", ""))
    preset_id = rig_root.get("af_cb_preset_id", "BASKET_01_OCT_EMPTY")
    defaults = _default_pin_positions_for_preset(preset_id)

    if not mesh_obj or not mesh_obj.data or not mesh_obj.data.vertices:
        coords = defaults
    else:
        verts = mesh_obj.data.vertices
        max_z = max(v.co.z for v in verts)
        top_verts = [v.co for v in verts if v.co.z >= max_z - 0.085]
        if len(top_verts) < 16:
            top_verts = [v.co for v in verts if v.co.z >= max_z - 0.14]
        min_tx = min(v.x for v in top_verts)
        max_tx = max(v.x for v in top_verts)
        min_ty = min(v.y for v in top_verts)
        max_ty = max(v.y for v in top_verts)
        cx_top = 0.5 * (min_tx + max_tx)
        cy_top = 0.5 * (min_ty + max_ty)
        hx_top = max(0.15, 0.5 * (max_tx - min_tx))
        hy_top = max(0.15, 0.5 * (max_ty - min_ty))

        z_thresh = max_z - 0.14
        min_corner_x = max(0.14, hx_top * 0.35)
        min_corner_y = max(0.14, hy_top * 0.35)
        quad_signs = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        coords = []
        for q_idx, (sx, sy) in enumerate(quad_signs):
            best_v = None
            best_score = -1e9
            for v in verts:
                if v.co.z < z_thresh:
                    continue
                dx = v.co.x - cx_top
                dy = v.co.y - cy_top
                if dx * sx < min_corner_x or dy * sy < min_corner_y:
                    continue
                # Score favors highest Z (the brass lifting eye-rings stick up at the 4 corners!) and corner symmetry
                diag_balance = min(abs(dx) / hx_top, abs(dy) / hy_top)
                score = v.co.z * 3.5 + 0.55 * diag_balance + 0.25 * math.hypot(dx, dy)
                if score > best_score:
                    best_score = score
                    best_v = v.co.copy()
            if best_v is not None:
                coords.append((round(best_v.x, 4), round(best_v.y, 4), round(best_v.z, 4)))
            else:
                coords.append(defaults[q_idx])

        # Align SpreaderHook XY above the centroid of the 4 snapped corner pins
        spreader_obj = bpy.data.objects.get(rig_root.get("af_cb_spreader_gizmo", ""))
        if spreader_obj and coords:
            avg_x = sum(c[0] for c in coords) / len(coords)
            avg_y = sum(c[1] for c in coords) / len(coords)
            spreader_obj.location.x = round(avg_x, 4)
            spreader_obj.location.y = round(avg_y, 4)

    pin_keys = ("af_cb_pin_01", "af_cb_pin_02", "af_cb_pin_03", "af_cb_pin_04")
    for idx, pk in enumerate(pin_keys):
        p_obj = bpy.data.objects.get(rig_root.get(pk, ""))
        if p_obj and idx < len(coords):
            p_obj.location = coords[idx]

    update_rope_assembly_curves_for_rig(rig_root, 0.0, 0.0)
    return coords


def mirror_active_pin_gizmo_to_all_4_corners(rig_root: bpy.types.Object, source_pin_obj: bpy.types.Object = None):
    """
    Takes the XY/Z position of `source_pin_obj` (or `GIZMO_Pin_01`) and mirrors it symmetrically
    across `±X` and `±Y` to all 4 rope attachment gizmos (`GIZMO_Pin_01..04`)!
    """
    if not rig_root:
        return
    p1 = bpy.data.objects.get(rig_root.get("af_cb_pin_01", ""))
    p2 = bpy.data.objects.get(rig_root.get("af_cb_pin_02", ""))
    p3 = bpy.data.objects.get(rig_root.get("af_cb_pin_03", ""))
    p4 = bpy.data.objects.get(rig_root.get("af_cb_pin_04", ""))
    src = source_pin_obj if (source_pin_obj and source_pin_obj in (p1, p2, p3, p4)) else p1
    if not src:
        return

    ax = max(0.15, abs(src.location.x))
    ay = max(0.15, abs(src.location.y))
    az = src.location.z

    if p1:
        p1.location = (-ax, -ay, az)
    if p2:
        p2.location = ( ax, -ay, az)
    if p3:
        p3.location = ( ax,  ay, az)
    if p4:
        p4.location = (-ax,  ay, az)

    update_rope_assembly_curves_for_rig(rig_root, 0.0, 0.0)


def swap_cliff_basket_preset(rig_root: bpy.types.Object, new_preset_id: str, auto_snap_pins: bool = True):
    """Swaps the 3D basket model on `rig_root` and optionally auto-snaps the 4 rope attachment gizmos to its rim."""
    if not rig_root:
        return
    basket_body = bpy.data.objects.get(rig_root.get("af_cb_basket_body", ""))
    old_mesh_obj = bpy.data.objects.get(rig_root.get("af_cb_basket_mesh", ""))
    if not basket_body:
        return

    st_col = next(iter(rig_root.users_collection), bpy.context.scene.collection)
    mesh_name = old_mesh_obj.name if old_mesh_obj else f"SM_Basket_Mesh_{rig_root.name}"
    if old_mesh_obj:
        bpy.data.objects.remove(old_mesh_obj, do_unlink=True)

    new_mesh_obj = load_or_build_basket_mesh_object(mesh_name, new_preset_id, st_col)
    new_mesh_obj.parent = basket_body
    new_mesh_obj.location = (0.0, 0.0, 0.0)
    new_mesh_obj["af_is_editable_prop"] = True
    new_mesh_obj["af_cb_rig_root"] = rig_root.name

    rig_root["af_cb_preset_id"] = new_preset_id
    rig_root["af_cb_basket_mesh"] = new_mesh_obj.name

    # Reposition mounted Elf inside the basket: centered for empty baskets, shifted slightly left (-X = -0.34 m) for HALF_MINER
    ctrl_obj = bpy.data.objects.get(rig_root.get("af_cb_elf_ctrl", ""))
    if ctrl_obj:
        floor_z = float(new_mesh_obj.data.get("af_cb_floor_z", 0.04)) if new_mesh_obj.data else 0.04
        ctrl_obj.location.z = floor_z
        ctrl_obj.location.y = -0.22
        if new_preset_id == "BASKET_03_HALF_MINER":
            ctrl_obj.location.x = -0.34
        else:
            ctrl_obj.location.x = 0.0
        # Hide Elf if FULL_CARGO basket is chosen
        hide_elf = (new_preset_id == "BASKET_04_FULL_CARGO")
        arm = get_character_armature_from_ctrl(ctrl_obj)
        if arm:
            arm.hide_viewport = hide_elf
            arm.hide_render = hide_elf
            for ch in arm.children:
                if not ch.name.startswith("TPL_"):
                    ch.hide_viewport = hide_elf
                    ch.hide_render = hide_elf

    if auto_snap_pins:
        auto_snap_4_gizmos_to_basket_rim(rig_root)


def bake_cliff_basket_physics_to_keyframes(rig_root: bpy.types.Object, frame_start: int = None, frame_end: int = None):
    """
    Bakes the analytical Damped Pendulum + Winch + Pickaxe Recoil physics into standard Blender
    F-curves (`location` & `rotation_euler`) on `BASKET_Body_<ID>` and `WinchPulley_<ID>`,
    then turns off procedural override so the user can fine-tune keyframes in the Graph Editor!
    """
    if not rig_root:
        return
    scn = bpy.context.scene
    f_s = int(frame_start if frame_start is not None else scn.frame_start)
    f_e = int(frame_end if frame_end is not None else scn.frame_end)

    basket_body = bpy.data.objects.get(rig_root.get("af_cb_basket_body", ""))
    pulley_wheel = bpy.data.objects.get(rig_root.get("af_cb_pulley_wheel", ""))
    if not basket_body:
        return

    if basket_body.animation_data:
        basket_body.animation_data_clear()
    if pulley_wheel and pulley_wheel.animation_data:
        pulley_wheel.animation_data_clear()

    rig_root["af_cb_use_procedural_physics"] = True
    for f in range(f_s, f_e + 1):
        state = evaluate_basket_physics_at_frame(rig_root, float(f), scene=scn)
        basket_body.location = state["location"]
        basket_body.rotation_mode = "XYZ"
        basket_body.rotation_euler = state["rotation_euler"]
        basket_body.keyframe_insert(data_path="location", frame=f)
        basket_body.keyframe_insert(data_path="rotation_euler", frame=f)

        if pulley_wheel:
            pulley_wheel.rotation_mode = "XYZ"
            pulley_wheel.rotation_euler = (state["pulley_angle_rad"], 0.0, 0.0)
            pulley_wheel.keyframe_insert(data_path="rotation_euler", frame=f)

    # Pause procedural override so Graph Editor edits take effect immediately
    rig_root["af_cb_use_procedural_physics"] = False


def clear_baked_cliff_basket_keyframes(rig_root: bpy.types.Object):
    """Clears baked F-curves on `BASKET_Body_<ID>` and restores live procedural physics."""
    if not rig_root:
        return
    basket_body = bpy.data.objects.get(rig_root.get("af_cb_basket_body", ""))
    pulley_wheel = bpy.data.objects.get(rig_root.get("af_cb_pulley_wheel", ""))
    if basket_body and basket_body.animation_data:
        basket_body.animation_data_clear()
    if pulley_wheel and pulley_wheel.animation_data:
        pulley_wheel.animation_data_clear()
    rig_root["af_cb_use_procedural_physics"] = True
    apply_basket_physics_to_rig(rig_root, float(bpy.context.scene.frame_current), scene=bpy.context.scene)


def spawn_cliff_basket_station(
    context=None,
    preset_id: str = "BASKET_01_OCT_EMPTY",
    elf_id: str = "ELF14",
    location: tuple = (0.0, 0.0, 1.35),
    rotation_z_deg: float = 0.0,
    winch_height_m: float = 5.80,
    build_cliff_wall_preview: bool = True,
    setup_demo_nla_sequence: bool = True,
) -> bpy.types.Object:
    """
    Spawns a complete Cliff Basket Station (`CB_ROOT_##`) with:
      - 3D Basket Mesh (`SM_Basket_Mesh_##`, normalized & hollowed at `Z=0.0`)
      - 4 Interactive Rope Attachment Gizmos (`GIZMO_Pin_01..04_##`) on the basket rim
      - Collector Hook Gizmo (`GIZMO_SpreaderHook_##`) at `Z = +2.05 m`
      - Top Winch Derrick & Rotating Spoked Brass Pulley Gizmo (`GIZMO_TopWinch_##`)
      - Wall Target Crosshair Gizmo (`GIZMO_WallTarget_##`) & Blue-Ice Burst VFX (`VFX_IceBurst_##`)
      - Procedural 3D Rope Geometry Nodes Assembly (`ROPE_Assembly_##`)
      - Mounted Rigged Elf Actor (`CTRL_Elf_*`) with `Prop_27_Hand_Pickaxe` and NLA sequence:
        `AF_06_Idle_Breathing` (during winch descent) -> `AF_27_Mine_Pickaxe` (wall mining & push-off recoil) -> `AF_06_Idle_Breathing` (settles to 100% standstill!).
    """
    ctx = context or bpy.context
    scn = ctx.scene

    master_col = ensure_collection(CLIFF_BASKETS_COLLECTION_NAME)
    existing = get_all_cliff_basket_rigs(scn)
    idx_num = len(existing) + 1
    while bpy.data.objects.get(f"CB_ROOT_{idx_num:02d}"):
        idx_num += 1
    tag = f"{idx_num:02d}"

    st_col_name = f"CB_{tag}_Cliff_Basket_Unit"
    st_col = bpy.data.collections.get(st_col_name) or bpy.data.collections.new(st_col_name)
    if st_col.name not in master_col.children:
        master_col.children.link(st_col)

    # 1. Station Root Empty (`CB_ROOT_##`)
    rig_root = bpy.data.objects.new(f"CB_ROOT_{tag}", None)
    rig_root.empty_display_type = "ARROWS"
    rig_root.empty_display_size = 0.55
    rig_root.location = location
    rig_root.rotation_mode = "XYZ"
    rig_root.rotation_euler = (0.0, 0.0, math.radians(rotation_z_deg))
    rig_root["af_is_cliff_basket_rig"] = True
    rig_root["af_is_editable_prop"] = True
    rig_root["af_cb_tag"] = tag
    rig_root["af_cb_preset_id"] = preset_id
    rig_root["af_cb_num_ropes"] = 4
    rig_root["af_cb_rope_mode"] = "SPREADER_4_TO_1"
    rig_root["af_cb_rope_slack_m"] = 0.035
    rig_root["af_cb_use_procedural_physics"] = True
    rig_root["af_cb_winch_mode"] = "LOWER_AND_STOP"
    rig_root["af_cb_z_start"] = 1.85
    rig_root["af_cb_z_work"] = 0.00
    rig_root["af_cb_lower_start_frame"] = 1
    rig_root["af_cb_lower_stop_frame"] = 48
    rig_root["af_cb_recoil_cm"] = 15.0
    rig_root["af_cb_tilt_kick_deg"] = 7.8
    rig_root["af_cb_damping"] = 1.55
    rig_root["af_cb_wall_gap_cm"] = 5.0
    rig_root["af_cb_wall_restitution"] = 0.30
    rig_root["af_cb_hit_frame_offset"] = 0
    st_col.objects.link(rig_root)

    # 2. Dynamic Basket Body Empty (`BASKET_Body_##`)
    basket_body = bpy.data.objects.new(f"BASKET_Body_{tag}", None)
    basket_body.empty_display_type = "CIRCLE"
    basket_body.empty_display_size = 0.85
    basket_body.parent = rig_root
    basket_body["af_is_editable_prop"] = True
    basket_body["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(basket_body)
    rig_root["af_cb_basket_body"] = basket_body.name

    # 3. 3D Basket Mesh (`SM_Basket_Mesh_##`)
    basket_mesh_obj = load_or_build_basket_mesh_object(f"SM_Basket_Mesh_{tag}", preset_id, st_col)
    basket_mesh_obj.parent = basket_body
    basket_mesh_obj.location = (0.0, 0.0, 0.0)
    basket_mesh_obj["af_is_editable_prop"] = True
    basket_mesh_obj["af_cb_rig_root"] = rig_root.name
    rig_root["af_cb_basket_mesh"] = basket_mesh_obj.name

    # 4. The 4 Interactive Rope Attachment Gizmos (`GIZMO_Pin_01..04_##`)
    pin_colors = (
        (1.00, 0.78, 0.12),  # Pin 1 (Front-Right): Warm Gold
        (0.15, 0.92, 0.75),  # Pin 2 (Front-Left): Bright Teal-Cyan
        (0.35, 0.72, 1.00),  # Pin 3 (Back-Left): Sky Blue
        (1.00, 0.48, 0.18),  # Pin 4 (Back-Right): Amber-Orange
    )
    pin_labels = ("Prednji-Desni", "Prednji-Lijevi", "Stražnji-Lijevi", "Stražnji-Desni")
    default_pins = _default_pin_positions_for_preset(preset_id)

    for p_idx in range(4):
        p_num = p_idx + 1
        g_mesh = _build_gizmo_ring_mesh(
            f"Mesh_GIZMO_Pin_{p_num:02d}_{tag}",
            radius=0.072,
            tube=0.018,
            color=pin_colors[p_idx],
            emission=2.8,
        )
        g_obj = bpy.data.objects.new(f"GIZMO_Pin_{p_num:02d}_{tag}", g_mesh)
        g_obj.parent = basket_body
        g_obj.location = default_pins[p_idx]
        g_obj.show_in_front = True
        g_obj.hide_render = True
        g_obj["af_is_editable_prop"] = True
        g_obj["af_is_basket_gizmo"] = True
        g_obj["af_cb_gizmo_role"] = f"PIN_{p_num:02d}"
        g_obj["af_cb_gizmo_label"] = pin_labels[p_idx]
        g_obj["af_cb_pin_index"] = p_num
        g_obj["af_cb_rig_root"] = rig_root.name
        st_col.objects.link(g_obj)
        rig_root[f"af_cb_pin_{p_num:02d}"] = g_obj.name

    # Auto-snap the 4 gizmos onto the actual Tripo 3D basket rim vertices!
    auto_snap_4_gizmos_to_basket_rim(rig_root)

    # 5. Collector Spreader Hook Gizmo (`GIZMO_SpreaderHook_##`) above the Elf's hat (`Z = +2.08 m`)
    sp_mesh = _build_gizmo_ring_mesh(
        f"Mesh_GIZMO_Spreader_{tag}",
        radius=0.095,
        tube=0.024,
        color=(0.95, 0.72, 0.20),
        emission=2.0,
    )
    spreader_obj = bpy.data.objects.new(f"GIZMO_SpreaderHook_{tag}", sp_mesh)
    spreader_obj.parent = basket_body
    spreader_obj.location = (0.0, 0.0, 2.45)
    spreader_obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    spreader_obj.show_in_front = True
    spreader_obj.hide_render = True
    spreader_obj["af_is_editable_prop"] = True
    spreader_obj["af_is_basket_gizmo"] = True
    spreader_obj["af_cb_gizmo_role"] = "SPREADER_HOOK"
    spreader_obj["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(spreader_obj)
    rig_root["af_cb_spreader_gizmo"] = spreader_obj.name

    # 6. Top Winch Derrick & Rotating Spoked Brass Pulley Wheel (`GIZMO_TopWinch_##`)
    winch_mesh = _build_gizmo_ring_mesh(
        f"Mesh_GIZMO_TopWinch_{tag}",
        radius=0.14,
        tube=0.026,
        color=(0.25, 0.88, 1.00),
        emission=2.2,
    )
    winch_obj = bpy.data.objects.new(f"GIZMO_TopWinch_{tag}", winch_mesh)
    winch_obj.parent = rig_root
    winch_obj.location = (0.0, -0.05, winch_height_m)
    winch_obj.show_in_front = True
    winch_obj.hide_render = True
    winch_obj["af_is_editable_prop"] = True
    winch_obj["af_is_basket_gizmo"] = True
    winch_obj["af_cb_gizmo_role"] = "TOP_WINCH"
    winch_obj["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(winch_obj)
    rig_root["af_cb_winch_gizmo"] = winch_obj.name

    # Physical 3D Spoked Brass Pulley Wheel + Timber Beam parented to `GIZMO_TopWinch_##`
    pulley_mesh = bpy.data.meshes.new(f"Mesh_WinchPulley_{tag}")
    bm_p = bmesh.new()
    bmesh.ops.create_cone(bm_p, cap_ends=True, cap_tris=False, segments=20, radius1=0.20, radius2=0.20, depth=0.07)
    bmesh.ops.rotate(bm_p, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90.0), 3, "Y"), verts=bm_p.verts)
    bm_p.to_mesh(pulley_mesh)
    bm_p.free()
    pulley_mesh.materials.append(_get_or_create_material("AF_CB_AgedBrass_Mat", (0.80, 0.60, 0.22), metallic=0.88, roughness=0.28))
    pulley_obj = bpy.data.objects.new(f"Prop_WinchPulley_{tag}", pulley_mesh)
    pulley_obj.parent = winch_obj
    pulley_obj["af_is_editable_prop"] = True
    pulley_obj["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(pulley_obj)
    rig_root["af_cb_pulley_wheel"] = pulley_obj.name

    # 7. Wall Impact Target Gizmo (`GIZMO_WallTarget_##`) & Blue-Ice Shard Burst VFX (`VFX_IceBurst_##`)
    wt_mesh = _build_gizmo_ring_mesh(
        f"Mesh_GIZMO_WallTarget_{tag}",
        radius=0.11,
        tube=0.020,
        color=(0.15, 0.95, 1.00),
        emission=3.2,
    )
    wall_gizmo = bpy.data.objects.new(f"GIZMO_WallTarget_{tag}", wt_mesh)
    wall_gizmo.parent = rig_root
    wall_gizmo.location = (0.0, -1.24, 1.05)
    wall_gizmo.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    wall_gizmo.show_in_front = True
    wall_gizmo.hide_render = True
    wall_gizmo["af_is_editable_prop"] = True
    wall_gizmo["af_is_basket_gizmo"] = True
    wall_gizmo["af_cb_gizmo_role"] = "WALL_TARGET"
    wall_gizmo["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(wall_gizmo)
    rig_root["af_cb_wall_gizmo"] = wall_gizmo.name

    # Blue-Ice Shard Burst mesh at impact point
    burst_mesh = bpy.data.meshes.new(f"Mesh_VFX_IceBurst_{tag}")
    bm_b = bmesh.new()
    shard_offsets = [
        (0.0, 0.0, 0.0, 0.08),
        (0.14, 0.08, 0.12, 0.065),
        (-0.15, 0.10, 0.10, 0.06),
        (0.10, 0.14, -0.10, 0.055),
        (-0.12, 0.06, -0.12, 0.05),
        (0.0, 0.18, 0.06, 0.055),
    ]
    for ox, oy, oz, rad in shard_offsets:
        ret = bmesh.ops.create_icosphere(bm_b, subdivisions=1, radius=rad)
        bmesh.ops.translate(bm_b, vec=(ox, oy, oz), verts=ret["verts"])
    bm_b.to_mesh(burst_mesh)
    bm_b.free()
    burst_mesh.materials.append(
        _get_or_create_material(
            "AF_CB_BlueIce_Mat",
            (0.25, 0.78, 0.98),
            roughness=0.15,
            emission_color=(0.20, 0.80, 1.00),
            emission_strength=3.5,
        )
    )
    burst_obj = bpy.data.objects.new(f"VFX_IceBurst_{tag}", burst_mesh)
    burst_obj.parent = rig_root
    burst_obj.location = wall_gizmo.location
    burst_obj.hide_viewport = True
    burst_obj.hide_render = True
    burst_obj["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(burst_obj)
    rig_root["af_cb_ice_burst"] = burst_obj.name

    # 8. Optional Cliff Wall & Ice Vein Preview Segment (`Prop_CliffWall_Preview_##`)
    if build_cliff_wall_preview:
        wall_mesh = bpy.data.meshes.new(f"Mesh_CliffWall_{tag}")
        bm_w = bmesh.new()
        bmesh.ops.create_cube(bm_w, size=1.0)
        bmesh.ops.scale(bm_w, vec=(0.95, 0.42, winch_height_m + 2.2), verts=bm_w.verts)
        bm_w.to_mesh(wall_mesh)
        bm_w.free()
        rock_mat = _get_or_create_material("AF_CB_CliffRock_Mat", (0.16, 0.18, 0.22), metallic=0.05, roughness=0.78)
        wall_mesh.materials.append(rock_mat)
        wall_obj = bpy.data.objects.new(f"Prop_CliffWall_{tag}", wall_mesh)
        wall_obj.parent = rig_root
        wall_obj.location = (0.0, -1.08, (winch_height_m - 0.5) * 0.5)
        wall_obj["af_is_editable_prop"] = True
        wall_obj["af_cb_rig_root"] = rig_root.name
        st_col.objects.link(wall_obj)
        rig_root["af_cb_wall_preview"] = wall_obj.name

        # Glowing Blue-Ice Crystal Cluster embedded in the cliff wall right at `GIZMO_WallTarget`
        vein_obj = load_or_build_cargo_prop_object(f"Prop_WallIceVein_{tag}", "CARGO_A_ICE", st_col)
        vein_obj.parent = rig_root
        vein_obj.location = (0.0, -0.84, 0.78)
        vein_obj.rotation_euler = (math.radians(82.0), 0.0, 0.0)
        vein_obj.scale = (1.35, 1.35, 1.35)
        vein_obj["af_cb_rig_root"] = rig_root.name
        rig_root["af_cb_wall_vein"] = vein_obj.name

    # 9. Modular Cargo Props inside the basket (`Prop_Cargo_A..C_##`)
    for c_id, _, _, _, def_loc in CLIFF_CARGO_PRESETS:
        c_obj = load_or_build_cargo_prop_object(f"Prop_{c_id}_{tag}", c_id, st_col)
        c_obj.parent = basket_body
        c_obj.location = def_loc
        c_obj["af_cb_rig_root"] = rig_root.name
        # Default visibility: hide standalone modular cargo in empty baskets so user can toggle them on with 1 click
        is_vis = (preset_id == "BASKET_02_GONDOLA_EMPTY" and c_id == "CARGO_A_ICE")
        c_obj.hide_viewport = not is_vis
        c_obj.hide_render = not is_vis
        rig_root[f"af_cb_{c_id.lower()}"] = c_obj.name

    # 10. Procedural 3D Rope Geometry Nodes Curve Object (`ROPE_Assembly_##`)
    rope_curve = bpy.data.curves.new(f"Curve_ROPE_Assembly_{tag}", "CURVE")
    rope_curve.dimensions = "3D"
    rope_obj = bpy.data.objects.new(f"ROPE_Assembly_{tag}", rope_curve)
    rope_obj.parent = rig_root
    rope_obj["af_cb_rig_root"] = rig_root.name
    st_col.objects.link(rope_obj)
    rig_root["af_cb_rope_obj"] = rope_obj.name

    gn_group = ensure_cliff_rope_geonodes_group()
    mod = rope_obj.modifiers.new(name="CliffRopeGeoNodes", type="NODES")
    mod.node_group = gn_group

    # 11. Spawn & Mount the Rigged Elf Actor (`CTRL_Elf_*`) inside `BASKET_Body_##`
    elf_x = -0.34 if preset_id == "BASKET_03_HALF_MINER" else 0.0
    floor_z = float(basket_mesh_obj.data.get("af_cb_floor_z", 0.04)) if basket_mesh_obj.data else 0.04
    ctrl_elf = spawn_elf_actor(
        ctx,
        elf_id=elf_id,
        location=(elf_x, -0.22, floor_z),
        initial_action_name="AF_27_Mine_Pickaxe",
        frame_offset=0,
    )
    if ctrl_elf:
        set_actor_accessories(ctrl_elf, show_hat=True, show_glasses=True)
        ctrl_elf.parent = basket_body
        ctrl_elf.location = (elf_x, -0.22, floor_z)
        ctrl_elf.rotation_euler = (0.0, 0.0, 0.0)
        ctrl_elf["af_cb_rig_root"] = rig_root.name
        rig_root["af_cb_elf_ctrl"] = ctrl_elf.name

        # Keep `ctrl_elf` linked in `ACTORS_COLLECTION_NAME` AND link to `st_col`
        arm_obj = get_character_armature_from_ctrl(ctrl_elf)
        elf_objs = [ctrl_elf]
        if arm_obj:
            elf_objs.append(arm_obj)
            elf_objs.extend(list(arm_obj.children))
        for eo in elf_objs:
            if eo.name not in st_col.objects:
                st_col.objects.link(eo)

        # Attach Detailed 3D Miner's Pickaxe (`Prop_27_Hand_Pickaxe_##`) to `hand_r`
        if arm_obj and "hand_r" in arm_obj.data.bones:
            wood_mat = _get_or_create_material("AF_CB_WickerWood_Mat", (0.28, 0.17, 0.09), roughness=0.58)
            iron_mat = _get_or_create_material("AF_CB_ForgedIron_Mat", (0.18, 0.20, 0.23), metallic=0.86, roughness=0.36)
            steel_mat = _get_or_create_material("AF_CB_SteelTip_Mat", (0.64, 0.68, 0.74), metallic=0.95, roughness=0.20)
            brass_mat = _get_or_create_material("AF_CB_AgedBrass_Mat", (0.80, 0.60, 0.22), metallic=0.88, roughness=0.28)

            # 1. Contoured Ash-Wood Handle + Brass Ferrules (`Prop_27_Hand_Pickaxe_##`)
            shaft_mesh = bpy.data.meshes.new(f"Mesh_Pickaxe_Shaft_{tag}")
            shaft_mesh.materials.append(wood_mat)   # 0: Ash wood
            shaft_mesh.materials.append(brass_mat)  # 1: Brass ferrule collars
            bm_s = bmesh.new()
            # Profile rings: (z, rx, ry, mat_idx)
            handle_prof = [
                (-0.24, 0.016, 0.020, 0),
                (-0.21, 0.025, 0.030, 0),  # Bottom pommel swell
                (-0.15, 0.019, 0.023, 0),
                ( 0.00, 0.018, 0.022, 0),  # Right-hand grip center
                ( 0.18, 0.019, 0.023, 0),  # Left-hand grip zone
                ( 0.44, 0.021, 0.026, 0),
                ( 0.52, 0.024, 0.030, 1),  # Lower brass collar ring
                ( 0.56, 0.025, 0.032, 1),
                ( 0.57, 0.023, 0.030, 0),
                ( 0.68, 0.026, 0.034, 0),  # Upper eye socket seat
                ( 0.71, 0.028, 0.036, 1),  # Top brass cap ferrule
                ( 0.73, 0.020, 0.026, 1),
            ]
            n_seg = 14
            rings_s = []
            for z_p, rx, ry, _ in handle_prof:
                ring = []
                for k in range(n_seg):
                    ang = 2.0 * math.pi * k / n_seg
                    ring.append(bm_s.verts.new((rx * math.cos(ang), ry * math.sin(ang), z_p)))
                rings_s.append(ring)
            for r_i in range(len(rings_s) - 1):
                r0, r1 = rings_s[r_i], rings_s[r_i + 1]
                m_idx = handle_prof[r_i][3]
                for k in range(n_seg):
                    nk = (k + 1) % n_seg
                    f = bm_s.faces.new((r0[k], r0[nk], r1[nk], r1[k]))
                    f.material_index = m_idx
            bm_s.faces.new(list(reversed(rings_s[0]))).material_index = 0
            bm_s.faces.new(rings_s[-1]).material_index = 1
            bm_s.normal_update()
            bm_s.to_mesh(shaft_mesh)
            bm_s.free()
            pick_shaft = bpy.data.objects.new(f"Prop_27_Hand_Pickaxe_{tag}", shaft_mesh)
            st_col.objects.link(pick_shaft)

            # 2. Curved Forged-Iron & Hardened-Steel Double Pick Head (`Prop_27_Pickaxe_Head_##`)
            head_mesh = bpy.data.meshes.new(f"Mesh_Pickaxe_Head_{tag}")
            head_mesh.materials.append(iron_mat)   # 0: Forged dark iron body
            head_mesh.materials.append(steel_mat)  # 1: Polished steel striking tips
            head_mesh.materials.append(brass_mat)  # 2: Brass socket trim
            bm_h = bmesh.new()
            # Build curved double-ended pickaxe blade along Y axis (centered at Z=0, mounted at shaft Z=0.63)
            # Sections from rear chisel tip (-Y) through central eye socket (Y=0) to front curved ice-pick point (+Y):
            # (y, z_center, half_wx, half_hz, mat_idx)
            blade_sections = [
                (-0.320, -0.070, 0.036, 0.004, 1),  # Rear beveled chisel cutting edge
                (-0.250, -0.045, 0.032, 0.014, 1),
                (-0.160, -0.018, 0.026, 0.022, 0),
                (-0.065, -0.002, 0.032, 0.036, 0),
                (-0.045,  0.000, 0.040, 0.048, 2),  # Central forged socket eye
                ( 0.000,  0.002, 0.044, 0.052, 0),
                ( 0.045,  0.000, 0.040, 0.048, 2),
                ( 0.070, -0.003, 0.030, 0.035, 0),
                ( 0.175, -0.022, 0.022, 0.025, 0),
                ( 0.285, -0.058, 0.014, 0.016, 1),  # Front hardened steel ice spike
                ( 0.375, -0.098, 0.005, 0.006, 1),
                ( 0.405, -0.114, 0.0015, 0.0015, 1), # Sharp ice-piercing tip
            ]
            # Diamond/octagonal beveled cross-section (8 verts per section)
            oct_dirs = [
                ( 1.0,  0.0),
                ( 0.75, 0.75),
                ( 0.0,  1.0),
                (-0.75, 0.75),
                (-1.0,  0.0),
                (-0.75,-0.75),
                ( 0.0, -1.0),
                ( 0.75,-0.75),
            ]
            h_rings = []
            for y_c, z_c, wx, hz, _ in blade_sections:
                ring = []
                for dx, dz in oct_dirs:
                    ring.append(bm_h.verts.new((dx * wx, y_c, z_c + dz * hz)))
                h_rings.append(ring)
            for s_i in range(len(h_rings) - 1):
                r0, r1 = h_rings[s_i], h_rings[s_i + 1]
                m_idx = blade_sections[s_i][4]
                for k in range(8):
                    nk = (k + 1) % 8
                    f = bm_h.faces.new((r0[k], r1[k], r1[nk], r0[nk]))
                    f.material_index = m_idx
            bm_h.faces.new(list(reversed(h_rings[0]))).material_index = 1
            bm_h.faces.new(h_rings[-1]).material_index = 1
            bm_h.normal_update()
            bm_h.to_mesh(head_mesh)
            bm_h.free()

            pick_head = bpy.data.objects.new(f"Prop_27_Pickaxe_Head_{tag}", head_mesh)
            pick_head.parent = pick_shaft
            pick_head.location = (0.0, 0.0, 0.63)
            pick_head["af_is_editable_prop"] = True
            pick_head["af_cb_rig_root"] = rig_root.name
            st_col.objects.link(pick_head)

            pick_shaft.parent = arm_obj
            pick_shaft.parent_type = "BONE"
            pick_shaft.parent_bone = "hand_r"
            # In hand_r tail space: mid-palm is at Y = -0.05; boneZ points along the gripped handle toward the wall,
            # and rotating -28° around local Z aligns the curved +Y pick spike directly into the forward swing plane!
            pick_shaft.location = (0.0, -0.05, 0.02)
            pick_shaft.rotation_mode = "XYZ"
            pick_shaft.rotation_euler = (0.0, 0.0, math.radians(-28.0))
            pick_shaft["af_is_editable_prop"] = True
            pick_shaft["af_station_ctrl"] = ctrl_elf.name
            pick_shaft["af_cb_rig_root"] = rig_root.name
            ctrl_elf["af_station_hand_tool"] = pick_shaft.name
            rig_root["af_cb_pickaxe_tool"] = pick_shaft.name

        # Build demo NLA sequence showing:
        #   1. Wave/Stand while lowering (frames 1..52) -> settles at stop
        #   2. Mine Pickaxe (1.5x cycles = frames 45..225) -> strikes wall at frames ~79, 137, 199, pushes off, swings
        #   3. Idle Breathing after mining (frames 215..390) -> decays to 100% stationary standstill (0.00000 m)!
        if setup_demo_nla_sequence:
            ctrl_elf["af_loop_anim"] = False
            demo_specs = []
            first_idle = "AF_28_Wave_Hello" if bpy.data.actions.get("AF_28_Wave_Hello") else "AF_06_Idle_Breathing"
            if bpy.data.actions.get(first_idle):
                demo_specs.append({
                    "action": first_idle,
                    "repeat": 0.40 if first_idle == "AF_28_Wave_Hello" else 0.10,
                    "speed": 1.0,
                    "blend": 0,
                    "mode": "FIXED",
                })
            if bpy.data.actions.get("AF_27_Mine_Pickaxe"):
                demo_specs.append({
                    "action": "AF_27_Mine_Pickaxe",
                    "repeat": 1.50,
                    "speed": 1.0,
                    "blend": 8,
                    "mode": "FIXED",
                })
            if bpy.data.actions.get("AF_06_Idle_Breathing"):
                demo_specs.append({
                    "action": "AF_06_Idle_Breathing",
                    "repeat": 0.25,
                    "speed": 1.0,
                    "blend": 12,
                    "mode": "FIXED",
                })
            if demo_specs:
                rebuild_nla_sequence_from_specs(ctrl_elf, demo_specs, sync_curve=False)
            scn.frame_end = 360

    # Initialize animatable Top Anchor Null Z, Max Drop Depth, Drop Alpha & Drop Depth on `rig_root`
    register_cliff_basket_object_properties()
    global _CB_PROP_SYNC_GUARD
    _CB_PROP_SYNC_GUARD = True
    try:
        top_world_z = float(location[2]) + float(winch_height_m)
        max_drop = max(12.0, round(float(winch_height_m) * 1.5, 2))
        min_drop = min(2.55, float(winch_height_m) - 0.15)
        span = max(0.5, max_drop - min_drop)
        init_alpha = max(0.0, min(1.0, (float(winch_height_m) - min_drop) / span))
        rig_root.af_cb_top_anchor_z = round(top_world_z, 3)
        rig_root.af_cb_max_drop_depth_m = round(max_drop, 3)
        rig_root.af_cb_drop_alpha = round(init_alpha, 4)
        rig_root.af_cb_drop_depth_m = round(float(winch_height_m), 3)
        rig_root.af_cb_wall_gap_offset_m = 0.15
    except Exception:
        pass
    finally:
        _CB_PROP_SYNC_GUARD = False

    apply_basket_physics_to_rig(rig_root, float(scn.frame_current), scene=scn)
    show_viewport_move_gizmo_arrows(True)
    return rig_root


def reload_all_tripo_basket_models_in_scene(context=None) -> int:
    """
    Clears any cached procedural basket/cargo meshes and reloads all newly generated
    Tripo 3D `.glb` models from `assets/models/glb/cliff_baskets/` onto all active rigs!
    """
    ctx = context or bpy.context
    for m in list(bpy.data.meshes):
        if m.name.startswith(("TPL_CB_Mesh_", "TPL_CB_Cargo_", "PROC_Mesh_", "PROC_Cargo_")):
            if m.users == 0:
                bpy.data.meshes.remove(m)
            else:
                m.name = f"_OLD_{m.name}"

    rigs = get_all_cliff_basket_rigs(getattr(ctx, "scene", None))
    count = 0
    for rig in rigs:
        preset_id = rig.get("af_cb_preset_id", "BASKET_01_OCT_EMPTY")
        swap_cliff_basket_preset(rig, preset_id, auto_snap_pins=True)
        count += 1
    return count


# ============================================================================
# 5. ANIMATABLE OBJECT PROPERTIES ON `CB_ROOT_##` (TOP NULL & DROP ALPHA)
# ============================================================================

def _on_cb_obj_top_anchor_updated(self, context):
    global _CB_PROP_SYNC_GUARD
    if _CB_PROP_SYNC_GUARD or not self.get("af_is_cliff_basket_rig"):
        return
    _CB_PROP_SYNC_GUARD = True
    try:
        winch_obj = bpy.data.objects.get(self.get("af_cb_winch_gizmo", ""))
        new_local_z = max(1.35, float(self.af_cb_top_anchor_z) - float(self.location.z))
        if winch_obj:
            winch_obj.location.z = new_local_z
        scn = context.scene if context and getattr(context, "scene", None) else bpy.context.scene
        apply_basket_physics_to_rig(self, float(scn.frame_current), scene=scn)
    finally:
        _CB_PROP_SYNC_GUARD = False


def _on_cb_obj_drop_alpha_updated(self, context):
    global _CB_PROP_SYNC_GUARD
    if _CB_PROP_SYNC_GUARD or not self.get("af_is_cliff_basket_rig"):
        return
    _CB_PROP_SYNC_GUARD = True
    try:
        winch_obj = bpy.data.objects.get(self.get("af_cb_winch_gizmo", ""))
        winch_z = float(winch_obj.location.z) if winch_obj else 6.50
        min_drop = min(2.55, winch_z - 0.15)
        max_drop = max(min_drop + 0.5, float(self.af_cb_max_drop_depth_m))
        alpha = max(0.0, min(1.0, float(self.af_cb_drop_alpha)))
        self.af_cb_drop_depth_m = round(min_drop + alpha * (max_drop - min_drop), 3)
        scn = context.scene if context and getattr(context, "scene", None) else bpy.context.scene
        apply_basket_physics_to_rig(self, float(scn.frame_current), scene=scn)
    finally:
        _CB_PROP_SYNC_GUARD = False


def _on_cb_obj_drop_depth_updated(self, context):
    global _CB_PROP_SYNC_GUARD
    if _CB_PROP_SYNC_GUARD or not self.get("af_is_cliff_basket_rig"):
        return
    _CB_PROP_SYNC_GUARD = True
    try:
        winch_obj = bpy.data.objects.get(self.get("af_cb_winch_gizmo", ""))
        winch_z = float(winch_obj.location.z) if winch_obj else 6.50
        min_drop = min(2.55, winch_z - 0.15)
        max_drop = max(min_drop + 0.5, float(self.af_cb_max_drop_depth_m))
        depth = max(min_drop, min(max_drop, float(self.af_cb_drop_depth_m)))
        self.af_cb_drop_alpha = round((depth - min_drop) / max(0.1, max_drop - min_drop), 4)
        scn = context.scene if context and getattr(context, "scene", None) else bpy.context.scene
        apply_basket_physics_to_rig(self, float(scn.frame_current), scene=scn)
    finally:
        _CB_PROP_SYNC_GUARD = False


def _on_cb_obj_wall_gap_updated(self, context):
    global _CB_PROP_SYNC_GUARD
    if _CB_PROP_SYNC_GUARD or not self.get("af_is_cliff_basket_rig"):
        return
    _CB_PROP_SYNC_GUARD = True
    try:
        self["af_cb_wall_gap_cm"] = max(2.0, float(self.af_cb_wall_gap_offset_m) * 100.0)
        scn = context.scene if context and getattr(context, "scene", None) else bpy.context.scene
        apply_basket_physics_to_rig(self, float(scn.frame_current), scene=scn)
    finally:
        _CB_PROP_SYNC_GUARD = False


def register_cliff_basket_object_properties():
    """Registers animatable FloatProperties on `bpy.types.Object` so `I` / keyframing works in Viewport & Dope Sheet."""
    from bpy.props import FloatProperty

    if not hasattr(bpy.types.Object, "af_cb_top_anchor_z"):
        bpy.types.Object.af_cb_top_anchor_z = FloatProperty(
            name="Visina Gornje Null Točke (Top Winch Z)",
            description="Apsolutna Z visina gornjeg sidrišta špage (GIZMO_TopWinch) u prostoru (m)",
            default=11.50,
            min=-25.0,
            max=95.0,
            unit="LENGTH",
            options={"ANIMATABLE"},
            update=_on_cb_obj_top_anchor_updated,
        )
    if not hasattr(bpy.types.Object, "af_cb_max_drop_depth_m"):
        bpy.types.Object.af_cb_max_drop_depth_m = FloatProperty(
            name="Maksimalna Dubina Spuštanja (Max Drop m)",
            description="Maksimalna dubina do koje se košara može spustiti ispod gornje Null točke (m)",
            default=12.0,
            min=0.5,
            max=60.0,
            unit="LENGTH",
            options={"ANIMATABLE"},
            update=_on_cb_obj_drop_alpha_updated,
        )
    if not hasattr(bpy.types.Object, "af_cb_drop_alpha"):
        bpy.types.Object.af_cb_drop_alpha = FloatProperty(
            name="Spuštanje Alpha (0.0 = Gore .. 1.0 = Dolje)",
            description="Glavni animabilni klizač spuštanja košare (0.00 = skroz gore pod koloturom, 1.00 = spušteno do pune dubine Max Drop)",
            default=0.65,
            min=0.0,
            max=1.0,
            subtype="FACTOR",
            options={"ANIMATABLE"},
            update=_on_cb_obj_drop_alpha_updated,
        )
    if not hasattr(bpy.types.Object, "af_cb_drop_depth_m"):
        bpy.types.Object.af_cb_drop_depth_m = FloatProperty(
            name="Trenutna Dubina Spuštanja (Drop Depth m)",
            description="Izravna dubina spuštanja košare ispod gornje Null točke u metrima",
            default=7.80,
            min=0.5,
            max=60.0,
            unit="LENGTH",
            options={"ANIMATABLE"},
            update=_on_cb_obj_drop_depth_updated,
        )
    if not hasattr(bpy.types.Object, "af_cb_wall_gap_offset_m"):
        bpy.types.Object.af_cb_wall_gap_offset_m = FloatProperty(
            name="Razmak Košare od Zida (Wall Gap m)",
            description="Razmak prednjeg odbojnika košare od površine ledenog zida GEO_Spilja_Desni_Ledeni_Zid",
            default=0.15,
            min=0.0,
            max=3.0,
            unit="LENGTH",
            options={"ANIMATABLE"},
            update=_on_cb_obj_wall_gap_updated,
        )


# ============================================================================
# 6. SUSTAV 1: DYNAMIC GLACIER WALL AUTO-SNAP FOR `GN_Cliff_Mining_Scaffolding`,
#    CURVES `CRV_S3_Skela_R1..R6`, `GEO_R1..R6`, 3D RAILS & HANGING BASKETS
# ============================================================================

def ensure_gn_cliff_mining_scaffolding_wall_snap(
    wall_standoff_m: float = 1.85,
    smoothing_iterations: int = 4,
    auto_adapt: bool = True,
) -> bpy.types.NodeTree:
    """
    Upgrades `GN_Cliff_Mining_Scaffolding` with:
      - `*1: Snap to Glacier Wall (Auto-Adapt)` (`NodeSocketBool`, default `True`)
      - `*1: Glacier Wall Object` (`NodeSocketObject`, default `GEO_Spilja_Desni_Ledeni_Zid`)
      - `*1: Wall Standoff Offset (m)` (`NodeSocketFloat`, default `1.85`, min `0.50`, max `8.00`)
      - `*1: Wall Contour Smoothing` (`NodeSocketInt`, default `4`, min `0`, max `16`)
    And inserts a Raycast (`(0.0, Position.Y, Position.Z) -> (+1, 0, 0)`) + `Blur Attribute` +
    `Set Position` stage at the entry of `GN_Cliff_Mining_Scaffolding` before all `Resample Curve`
    and `Instance on Points` nodes.
    """
    ng = bpy.data.node_groups.get("GN_Cliff_Mining_Scaffolding")
    if not ng:
        return None

    wall_obj = bpy.data.objects.get("GEO_Spilja_Desni_Ledeni_Zid")

    def _find_or_add_socket(name: str, socket_type: str):
        for item in ng.interface.items_tree:
            if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
                return item
        return ng.interface.new_socket(name=name, in_out="INPUT", socket_type=socket_type)

    s_snap = _find_or_add_socket("*1: Snap to Glacier Wall (Auto-Adapt)", "NodeSocketBool")
    s_snap.default_value = bool(auto_adapt)

    s_wall = _find_or_add_socket("*1: Glacier Wall Object", "NodeSocketObject")
    if wall_obj:
        s_wall.default_value = wall_obj

    s_off = _find_or_add_socket("*1: Wall Standoff Offset (m)", "NodeSocketFloat")
    s_off.default_value = float(wall_standoff_m)
    s_off.min_value = 0.50
    s_off.max_value = 8.00

    s_sm = _find_or_add_socket("*1: Wall Contour Smoothing", "NodeSocketInt")
    s_sm.default_value = int(smoothing_iterations)
    s_sm.min_value = 0
    s_sm.max_value = 16

    nodes = ng.nodes
    links = ng.links
    n_in = nodes.get("Group Input")
    if not n_in:
        return ng

    def _get_or_new(name: str, bl_idname: str, loc: tuple):
        nd = nodes.get(name)
        if nd and nd.bl_idname != bl_idname:
            nodes.remove(nd)
            nd = None
        if not nd:
            nd = nodes.new(bl_idname)
            nd.name = name
        nd.location = loc
        return nd

    n_pre_res = _get_or_new("SV_WallAdapt_Resample", "GeometryNodeResampleCurve", (-1180, 260))
    if "Mode" in n_pre_res.inputs:
        n_pre_res.inputs["Mode"].default_value = "Length"
    elif hasattr(n_pre_res, "mode"):
        n_pre_res.mode = "LENGTH"
    if "Length" in n_pre_res.inputs:
        n_pre_res.inputs["Length"].default_value = 2.10

    n_obj = _get_or_new("SV_WallAdapt_ObjInfo", "GeometryNodeObjectInfo", (-1180, 60))
    n_obj.transform_space = "RELATIVE"

    n_pos = _get_or_new("SV_WallAdapt_Pos", "GeometryNodeInputPosition", (-1180, -140))
    n_sep = _get_or_new("SV_WallAdapt_SepXYZ", "ShaderNodeSeparateXYZ", (-980, -140))

    n_src = _get_or_new("SV_WallAdapt_CombSrc", "ShaderNodeCombineXYZ", (-780, -120))
    n_src.inputs["X"].default_value = 0.0

    n_ray = _get_or_new("SV_WallAdapt_Raycast", "GeometryNodeRaycast", (-580, 40))
    n_ray.inputs["Ray Direction"].default_value = (1.0, 0.0, 0.0)
    n_ray.inputs["Ray Length"].default_value = 120.0

    n_sep_hit = _get_or_new("SV_WallAdapt_SepHit", "ShaderNodeSeparateXYZ", (-380, 80))

    n_sub = _get_or_new("SV_WallAdapt_SubStandoff", "ShaderNodeMath", (-180, 80))
    n_sub.operation = "SUBTRACT"

    # Prevent deep tunnel/adit mouth recesses (e.g. R2 portal at Y=106..112) from pulling a synced gallery inward:
    # When the spline point is already snapped near the wall (`Position.X > 18.0`), clamp `Hit_X - Standoff`
    # so it cannot jump deep into an open tunnel mouth (`<= Position.X + 0.02`).
    n_gt18 = _get_or_new("SV_WallAdapt_IsSynced", "ShaderNodeMath", (-180, -120))
    n_gt18.operation = "GREATER_THAN"
    n_gt18.inputs[1].default_value = 18.0

    n_min_recess = _get_or_new("SV_WallAdapt_ClampRecess", "ShaderNodeMath", (-40, -20))
    n_min_recess.operation = "MINIMUM"

    n_sw_recess = _get_or_new("SV_WallAdapt_RecessSwitch", "GeometryNodeSwitch", (-40, 120))
    n_sw_recess.input_type = "FLOAT"

    n_sw_hit = _get_or_new("SV_WallAdapt_HitSwitch", "GeometryNodeSwitch", (100, 40))
    n_sw_hit.input_type = "FLOAT"

    n_blur = _get_or_new("SV_WallAdapt_BlurX", "GeometryNodeBlurAttribute", (260, 40))
    n_blur.data_type = "FLOAT"

    n_comb_fin = _get_or_new("SV_WallAdapt_CombFinal", "ShaderNodeCombineXYZ", (440, -40))
    n_set_pos = _get_or_new("SV_WallAdapt_SetPos", "GeometryNodeSetPosition", (620, 160))

    n_sw_en = _get_or_new("SV_WallAdapt_EnableSwitch", "GeometryNodeSwitch", (820, 220))
    n_sw_en.input_type = "GEOMETRY"

    # Connect internal WallAdapt pipeline (directly on input curve points so spline points and GN points match 1:1)
    links.new(n_in.outputs["*1: Glacier Wall Object"], n_obj.inputs["Object"])
    links.new(n_pos.outputs["Position"], n_sep.inputs["Vector"])
    links.new(n_sep.outputs["Y"], n_src.inputs["Y"])
    links.new(n_sep.outputs["Z"], n_src.inputs["Z"])

    links.new(n_obj.outputs["Geometry"], n_ray.inputs["Target Geometry"])
    links.new(n_src.outputs["Vector"], n_ray.inputs["Source Position"])
    links.new(n_ray.outputs["Hit Position"], n_sep_hit.inputs["Vector"])

    links.new(n_sep_hit.outputs["X"], n_sub.inputs[0])
    links.new(n_in.outputs["*1: Wall Standoff Offset (m)"], n_sub.inputs[1])

    links.new(n_sep.outputs["X"], n_gt18.inputs[0])

    links.new(n_ray.outputs["Is Hit"], n_sw_hit.inputs["Switch"])
    links.new(n_sep.outputs["X"], n_sw_hit.inputs["False"])
    links.new(n_sub.outputs["Value"], n_sw_hit.inputs["True"])

    links.new(n_sw_hit.outputs["Output"], n_blur.inputs["Value"])
    links.new(n_in.outputs["*1: Wall Contour Smoothing"], n_blur.inputs["Iterations"])

    links.new(n_blur.outputs["Value"], n_min_recess.inputs[0])
    links.new(n_sep.outputs["X"], n_min_recess.inputs[1])

    links.new(n_gt18.outputs["Value"], n_sw_recess.inputs["Switch"])
    links.new(n_blur.outputs["Value"], n_sw_recess.inputs["False"])
    links.new(n_min_recess.outputs["Value"], n_sw_recess.inputs["True"])

    links.new(n_sw_recess.outputs["Output"], n_comb_fin.inputs["X"])
    links.new(n_sep.outputs["Y"], n_comb_fin.inputs["Y"])
    links.new(n_sep.outputs["Z"], n_comb_fin.inputs["Z"])

    links.new(n_in.outputs["Geometry"], n_set_pos.inputs["Geometry"])
    links.new(n_comb_fin.outputs["Vector"], n_set_pos.inputs["Position"])

    links.new(n_in.outputs["*1: Snap to Glacier Wall (Auto-Adapt)"], n_sw_en.inputs["Switch"])
    links.new(n_in.outputs["Geometry"], n_sw_en.inputs["False"])
    links.new(n_set_pos.outputs["Geometry"], n_sw_en.inputs["True"])

    # Feed `SV_WallAdapt_EnableSwitch.Output` into all downstream Resample Curve nodes
    for r_name in (
        "Resample Curve",
        "Resample Curve.001",
        "Resample Curve.002",
        "Resample Curve.003",
        "Resample Curve.004",
        "Resample Curve.005",
    ):
        r_node = nodes.get(r_name)
        if r_node and "Curve" in r_node.inputs:
            links.new(n_sw_en.outputs["Output"], r_node.inputs["Curve"])

    # Update modifier socket values on all scaffolding curves in the scene (Blender 5.3+ & 4.x compatible)
    def _set_mod_sock(mod, ident: str, val):
        try:
            if hasattr(mod, "properties") and hasattr(mod.properties, "inputs"):
                inp = getattr(mod.properties.inputs, ident, None)
                if inp is not None and hasattr(inp, "value"):
                    inp.value = val
                    return
        except Exception:
            pass
        try:
            mod[ident] = val
        except Exception:
            pass

    for obj in bpy.data.objects:
        if obj.type != "CURVE":
            continue
        for mod in obj.modifiers:
            if mod.type == "NODES" and mod.node_group == ng:
                _set_mod_sock(mod, s_snap.identifier, bool(auto_adapt))
                if wall_obj:
                    _set_mod_sock(mod, s_wall.identifier, wall_obj)
                _set_mod_sock(mod, s_off.identifier, float(wall_standoff_m))
                _set_mod_sock(mod, s_sm.identifier, int(smoothing_iterations))
                obj.update_tag()

    return ng


def sample_glacier_wall_surface(
    wall_eval: bpy.types.Object,
    y: float,
    z: float,
    z_probe_offsets: tuple = (0.0, 1.2, -1.2),
    frontmost: bool = True,
) -> tuple[float, Vector]:
    """
    Raycasts from `(0.0, y + dy, z + dz)` in direction `(+1, 0, 0)` onto the evaluated
    `GEO_Spilja_Desni_Ledeni_Zid` mesh and returns `(hit_x, world_normal)`.
    When `frontmost=True`, returns the outermost (`min X`) protruding serac contact across the
    probe window so scaffolding decks, rails, and under-bridge struts NEVER clip into protruding ice!
    """
    if not wall_eval:
        return 15.6, Vector((-1.0, 0.0, 0.0))

    mw = wall_eval.matrix_world
    mwi = mw.inverted()
    mw_rot = mw.to_3x3()
    ray_dir_l = (mwi.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()

    hits = []
    for dz in z_probe_offsets:
        for dy in (-2.0, -1.0, 0.0, 1.0, 2.0):
            p0_l = mwi @ Vector((0.0, float(y) + dy, float(z) + float(dz)))
            ok, loc_l, norm_l, _ = wall_eval.ray_cast(p0_l, ray_dir_l, distance=120.0)
            if ok:
                w_loc = mw @ loc_l
                if 8.0 <= w_loc.x <= 44.0:
                    w_norm = (mw_rot @ norm_l).normalized()
                    hits.append((float(w_loc.x), w_norm))

    if not hits:
        return 15.6, Vector((-1.0, 0.0, 0.0))

    hits.sort(key=lambda item: item[0])
    pick_idx = 0 if frontmost else (len(hits) // 2)
    best_x = hits[pick_idx][0]
    avg_n = Vector((0.0, 0.0, 0.0))
    for _, n_vec in hits:
        avg_n += n_vec
    best_n = avg_n.normalized() if avg_n.length > 1e-4 else hits[pick_idx][1]
    return best_x, best_n


def _smooth_1d_array(vals: list[float], iterations: int = 4) -> list[float]:
    if len(vals) <= 2 or iterations <= 0:
        return list(vals)
    arr = list(vals)
    for _ in range(iterations):
        nxt = list(arr)
        for i in range(1, len(arr) - 1):
            nxt[i] = (arr[i - 1] + arr[i] + arr[i + 1]) / 3.0
        nxt[0] = 0.5 * (arr[0] + arr[1])
        nxt[-1] = 0.5 * (arr[-1] + arr[-2])
        arr = nxt
    return arr


def snap_single_basket_to_glacier_wall(
    rig_root: bpy.types.Object,
    wall_eval: bpy.types.Object = None,
    wall_gap_m: float = None,
) -> dict:
    """
    Snaps an individual Cliff Basket station (`CB_ROOT_##`) and its Top Winch Null (`GIZMO_TopWinch_##`)
    flush against `GEO_Spilja_Desni_Ledeni_Zid` at the basket's `(Y, Z)` working coordinates,
    orienting the basket so `GIZMO_WallTarget_##` and the Elf's pickaxe strike directly into the ice face.
    """
    if not rig_root:
        return {}
    if wall_eval is None:
        wall_obj = bpy.data.objects.get("GEO_Spilja_Desni_Ledeni_Zid")
        if wall_obj:
            dg = bpy.context.evaluated_depsgraph_get()
            wall_eval = wall_obj.evaluated_get(dg)

    y_pos = float(rig_root.location.y)
    z_pos = float(rig_root.location.z)
    # Sample across the vertical span of the basket `[z_pos + 0.05, z_pos + 0.55, z_pos + 1.05]`
    # and take the frontmost ice contact (`min(hit_x)`) so the basket never clips into a sloped ice ledge!
    span_hits = [
        sample_glacier_wall_surface(wall_eval, y_pos, z_pos + dz_b, z_probe_offsets=(0.0,))
        for dz_b in (0.05, 0.55, 1.05)
    ]
    hit_x, norm_w = min(span_hits, key=lambda item: item[0])

    if wall_gap_m is None:
        wall_gap_m = float(getattr(rig_root, "af_cb_wall_gap_offset_m", 0.15))

    # In `CB_ROOT_##` local space, `GIZMO_WallTarget` (the pickaxe impact point) is at `Y_local = -1.24 m`,
    # and the front rim of the 2.15m basket is at `Y_local ≈ -1.05 m`.
    # With `rotation_z ≈ 90°`, local `-Y` points along world `+X` toward the glacier wall!
    # Placing `rig_root.location.x = hit_x - (1.08 + wall_gap_m)` puts the front basket rim `wall_gap_m`
    # in front of the ice face and puts the pickaxe head (`Y_local = -1.24 m`) right on the ice surface!
    standoff_basket_x = 1.08 + max(0.02, float(wall_gap_m))
    rig_root.location.x = round(hit_x - standoff_basket_x, 3)

    # Compute Z yaw from wall normal so local `-Y` points opposite to `(norm_w.x, norm_w.y)`
    # Clamp yaw within `90° ± 18°` so the basket stays cleanly aligned with the cliff gallery
    raw_yaw_deg = math.degrees(math.atan2(-norm_w.x, norm_w.y))
    clamped_yaw_deg = max(72.0, min(108.0, raw_yaw_deg))
    rig_root.rotation_mode = "XYZ"
    rig_root.rotation_euler = (0.0, 0.0, math.radians(clamped_yaw_deg))

    apply_basket_physics_to_rig(rig_root, float(bpy.context.scene.frame_current), scene=bpy.context.scene)
    return {
        "rig_root": rig_root.name,
        "wall_x": round(hit_x, 3),
        "basket_x": round(rig_root.location.x, 3),
        "yaw_deg": round(clamped_yaw_deg, 2),
    }


def _ensure_r2_tunnel_boolean_cutter_on_wall(wall_obj: bpy.types.Object, r2_portal_x: float):
    """
    Ensures a clean Geometry Nodes face-deletion modifier (`GN_R2_Tunnel_Opening`) opens the mouth of
    the Skela 2 (`R2`) side tunnel (`98.20 <= Y <= 105.80, -0.25 <= Z <= 7.25, X > 15.0`) on the
    single-sided surface mesh `GEO_Spilja_Desni_Ledeni_Zid` without stamping a Boolean front cap wall!
    """
    if not wall_obj:
        return

    # Remove any old Boolean modifier / cutter box (which stamps a solid front cap face on non-manifold walls)
    old_b_mod = wall_obj.modifiers.get("BOOL_R2_Tunnel_Pocket")
    if old_b_mod:
        wall_obj.modifiers.remove(old_b_mod)
    old_cutter = bpy.data.objects.get("CUTTER_S3_R2_Tunnel_Pocket")
    if old_cutter:
        bpy.data.objects.remove(old_cutter, do_unlink=True)

    ng_name = "GN_R2_Tunnel_Opening"
    ng = bpy.data.node_groups.get(ng_name)
    if not ng:
        ng = bpy.data.node_groups.new(ng_name, "GeometryNodeTree")
        ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    ng.nodes.clear()
    ng.links.clear()

    n_in = ng.nodes.new("NodeGroupInput")
    n_in.location = (-800, 0)
    n_out = ng.nodes.new("NodeGroupOutput")
    n_out.location = (600, 0)

    n_pos = ng.nodes.new("GeometryNodeInputPosition")
    n_pos.location = (-800, -220)
    n_sep = ng.nodes.new("ShaderNodeSeparateXYZ")
    n_sep.location = (-600, -220)
    ng.links.new(n_pos.outputs["Position"], n_sep.inputs["Vector"])

    def _cmp_between(val_sock, low_val: float, high_val: float, loc_y: float):
        c_ge = ng.nodes.new("FunctionNodeCompare")
        c_ge.data_type = "FLOAT"
        c_ge.operation = "GREATER_EQUAL"
        c_ge.location = (-360, loc_y)
        c_ge.inputs[1].default_value = float(low_val)
        ng.links.new(val_sock, c_ge.inputs[0])

        c_le = ng.nodes.new("FunctionNodeCompare")
        c_le.data_type = "FLOAT"
        c_le.operation = "LESS_EQUAL"
        c_le.location = (-360, loc_y - 140)
        c_le.inputs[1].default_value = float(high_val)
        ng.links.new(val_sock, c_le.inputs[0])

        b_and = ng.nodes.new("FunctionNodeBooleanMath")
        b_and.operation = "AND"
        b_and.location = (-140, loc_y - 60)
        ng.links.new(c_ge.outputs["Result"], b_and.inputs[0])
        ng.links.new(c_le.outputs["Result"], b_and.inputs[1])
        return b_and.outputs["Boolean"]

    y_in = _cmp_between(n_sep.outputs["Y"], 98.05, 105.95, -40)
    z_in = _cmp_between(n_sep.outputs["Z"], -0.15, 7.45, -340)

    c_x = ng.nodes.new("FunctionNodeCompare")
    c_x.data_type = "FLOAT"
    c_x.operation = "GREATER_THAN"
    c_x.location = (-360, -640)
    c_x.inputs[1].default_value = 10.0
    ng.links.new(n_sep.outputs["X"], c_x.inputs[0])

    and_yz = ng.nodes.new("FunctionNodeBooleanMath")
    and_yz.operation = "AND"
    and_yz.location = (80, -180)
    ng.links.new(y_in, and_yz.inputs[0])
    ng.links.new(z_in, and_yz.inputs[1])

    and_xyz = ng.nodes.new("FunctionNodeBooleanMath")
    and_xyz.operation = "AND"
    and_xyz.location = (240, -260)
    ng.links.new(and_yz.outputs["Boolean"], and_xyz.inputs[0])
    ng.links.new(c_x.outputs["Result"], and_xyz.inputs[1])

    n_del = ng.nodes.new("GeometryNodeDeleteGeometry")
    n_del.domain = "FACE"
    n_del.mode = "ALL"
    n_del.location = (420, 0)
    ng.links.new(n_in.outputs["Geometry"], n_del.inputs["Geometry"])
    ng.links.new(and_xyz.outputs["Boolean"], n_del.inputs["Selection"])
    ng.links.new(n_del.outputs["Geometry"], n_out.inputs["Geometry"])

    mod_name = "GN_R2_Tunnel_Opening"
    g_mod = wall_obj.modifiers.get(mod_name)
    if not g_mod:
        g_mod = wall_obj.modifiers.new(name=mod_name, type="NODES")
    g_mod.node_group = ng
    g_mod.show_viewport = True
    g_mod.show_render = True


def sync_scaffolding_and_rails_to_glacier_wall(
    context=None,
    wall_standoff_m: float = 1.85,
    smoothing_window: int = 4,
) -> dict:
    """
    Master synchronization function (SUSTAV 1):
      1. Upgrades `GN_Cliff_Mining_Scaffolding` with the live Raycast + Blur Attribute wall adaptation nodes.
      2. Evaluates `GEO_Spilja_Desni_Ledeni_Zid` via `evaluated_depsgraph_get()` (temporarily muting
         `GN_R2_Tunnel_Opening` during raycast so outer cliff contour is sampled cleanly).
      3. Snaps all 15 scaffolding curves `CRV_S3_Skela_R1..R6` to `X_curve(Y, Z) = X_wall_smooth(Y, Z) - wall_standoff_m`.
      4. Shifts static scaffolding structures (`GEO_R2_Portal_Bocnog_Rudarskog_Okna`,
         `GEO_R2_Spojeni_Drveni_Pod_Tunel_I_Zavoj`, `GEO_R3_Potporne_Grede_Duge_Galerije`,
         `GEO_R4_Vertikalno_Dizalo_Za_Led`, `GEO_R5_Spojni_Mostici_I_Rampe`,
         `GEO_R6_Kaskadni_Lijevci_Za_Led_Cupar`) by their exact local `ΔX` so every portal, ramp,
         support beam, elevator, and chute sits flush on the snapped scaffolding against the glacier wall.
      5. Updates the 3D narrow-gauge railway curves (`CRV_S3_MC_Track_R2_Bocno_Okno`,
         `CRV_S3_MC_Track_R3_Duga_Galerija`) and rebuilds their 3D rails (`RAIL_Track_*`) and minecarts.
      6. Snaps all scaffold workers (`CTRL_Elf_*`), cargo props (`S3_CargoProp_*`), and hanging cliff
         baskets (`CB_ROOT_01..04`) flush to the new scaffolding and glacier wall positions.
    """
    ctx = context or bpy.context
    scn = ctx.scene
    wall_obj = bpy.data.objects.get("GEO_Spilja_Desni_Ledeni_Zid")
    if not wall_obj:
        return {"error": "GEO_Spilja_Desni_Ledeni_Zid not found"}

    # Disable single-ray GN override so GN_Cliff_Mining_Scaffolding uses the exact multi-height-probed
    # front-envelope `curve_xs` computed below (keeping wooden decks 100% locked to 3D steel rails and 0% clipping!)
    ensure_gn_cliff_mining_scaffolding_wall_snap(
        wall_standoff_m=wall_standoff_m,
        smoothing_iterations=smoothing_window,
        auto_adapt=False,
    )

    # Temporarily disable R2 tunnel opening modifier while sampling the outer cliff wall contour
    for tmp_mod_name in ("BOOL_R2_Tunnel_Pocket", "GN_R2_Tunnel_Opening"):
        tm = wall_obj.modifiers.get(tmp_mod_name)
        if tm:
            tm.show_viewport = False
    wall_obj.update_tag()

    dg = ctx.evaluated_depsgraph_get()
    wall_eval = wall_obj.evaluated_get(dg)

    # Canonical baseline endpoints `(y_start, z_start, y_end, z_end, x_orig)` for all 15 R1..R6 scaffolding curves
    CANONICAL_SKELE_SPECS = {
        "CRV_S3_Skela_R1_Donja_Etaža": (52.0, -9.8, 74.8, -9.8, 12.8),
        "CRV_S3_Skela_R1_Glavna_Galerija": (18.0, -0.6, 68.4, -0.6, 11.8),
        "CRV_S3_Skela_R1_Gornja_Polica": (18.0, 12.6, 38.0, 12.6, 11.8),
        "CRV_S3_Skela_R2_Iz_Bocnog_Okna": (106.0, 0.0, 154.0, 0.0, 12.0),
        "CRV_S3_Skela_R2_Desna_Stepenica": (134.0, 8.2, 162.0, 8.2, 12.4),
        "CRV_S3_Skela_R3_Duga_Galerija": (174.0, 0.4, 234.854, 1.244, 13.0),
        "CRV_S3_Skela_R3_Gornji_Usjek": (180.0, 16.929, 208.0, 16.929, 12.2),
        "CRV_S3_Skela_R4_Donji_Lijevak": (302.0, -10.2, 328.6, -10.2, 12.5),
        "CRV_S3_Skela_R4_Galerija_Dizala": (260.0, 0.2, 323.0, 0.2, 11.8),
        "CRV_S3_Skela_R5_Donja_Etaža": (380.0, -8.6, 412.0, -8.6, 12.2),
        "CRV_S3_Skela_R5_Gornja_Etaža": (344.0, 11.2, 384.0, 11.2, 12.2),
        "CRV_S3_Skela_R5_Srednja_Etaža": (344.0, 0.2, 411.2, 0.2, 11.8),
        "CRV_S3_Skela_R6_Kaskada_01_Vrh": (426.0, 13.0, 454.0, 13.0, 12.5),
        "CRV_S3_Skela_R6_Kaskada_02_Sredina": (450.0, 5.6, 478.0, 5.6, 12.5),
        "CRV_S3_Skela_R6_Kaskada_03_Ulaz_U_Tvornicu": (470.0, -1.2, 502.0, -0.5, 11.5),
    }

    curve_profiles = {}
    for crv_name, (y0, z0, y1, z1, x_orig) in CANONICAL_SKELE_SPECS.items():
        crv_obj = bpy.data.objects.get(crv_name)
        if not crv_obj or crv_obj.type != "CURVE":
            continue
        crv_obj.location = (0.0, 0.0, 0.0)
        crv_obj.rotation_euler = (0.0, 0.0, 0.0)
        crv_obj.scale = (1.0, 1.0, 1.0)

        length_y = abs(y1 - y0)
        n_segs = max(4, int(round(length_y / 4.20)))
        ys = [y0 + (y1 - y0) * (i / float(n_segs)) for i in range(n_segs + 1)]
        zs = [z0 + (z1 - z0) * (i / float(n_segs)) for i in range(n_segs + 1)]

        raw_wall_xs = []
        for y_pt, z_pt in zip(ys, zs):
            y_sample = max(107.0, y_pt) if crv_name == "CRV_S3_Skela_R2_Iz_Bocnog_Okna" else y_pt
            wx, _ = sample_glacier_wall_surface(wall_eval, y_sample, z_pt, z_probe_offsets=(-3.8, -2.0, -0.5, 0.0, 1.5, 3.2))
            raw_wall_xs.append(wx)

        smooth_wall_xs = _smooth_1d_array(raw_wall_xs, iterations=max(2, int(smoothing_window)))
        curve_xs = [round(wx - float(wall_standoff_m), 3) for wx in smooth_wall_xs]

        crv_obj.data.splines.clear()
        sp = crv_obj.data.splines.new("POLY")
        sp.points.add(len(ys) - 1)
        for i, (cx, cy, cz) in enumerate(zip(curve_xs, ys, zs)):
            sp.points[i].co = (cx, round(cy, 3), round(cz, 3), 1.0)
        crv_obj.data.update_tag()
        crv_obj.update_tag()

        curve_profiles[crv_name] = {
            "ys": ys,
            "zs": zs,
            "xs": curve_xs,
            "mean_x": round(sum(curve_xs) / len(curve_xs), 3),
            "start_x": curve_xs[0],
            "end_x": curve_xs[-1],
            "x_orig": x_orig,
        }

    def _interp_curve_x(crv_name: str, y_q: float) -> tuple[float, float]:
        prof = curve_profiles.get(crv_name)
        if not prof:
            wx, _ = sample_glacier_wall_surface(wall_eval, y_q, 0.0)
            return wx - float(wall_standoff_m), 0.0
        ys, zs, xs = prof["ys"], prof["zs"], prof["xs"]
        if y_q <= ys[0]:
            return xs[0], zs[0]
        if y_q >= ys[-1]:
            return xs[-1], zs[-1]
        for i in range(len(ys) - 1):
            if ys[i] <= y_q <= ys[i + 1]:
                t = (y_q - ys[i]) / max(1e-5, ys[i + 1] - ys[i])
                return xs[i] + t * (xs[i + 1] - xs[i]), zs[i] + t * (zs[i + 1] - zs[i])
        return prof["mean_x"], zs[0]

    # 4. Shift static `GEO_R2..R6` meshes idempotently using stored `_sv_orig_co` vertex layer
    def _shift_static_geo_mesh(obj_name: str, delta_x_fn):
        obj = bpy.data.objects.get(obj_name)
        if not obj or obj.type != "MESH" or not obj.data:
            return
        mesh = obj.data
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)

        attr = mesh.attributes.get("_sv_orig_co")
        if not attr:
            attr = mesh.attributes.new(name="_sv_orig_co", type="FLOAT_VECTOR", domain="POINT")
            for i, v in enumerate(mesh.vertices):
                attr.data[i].vector = v.co.copy()

        # Group connected mesh islands so each rigid timber beam/portal frame shifts without shearing
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        visited = set()
        islands = []
        for v in bm.verts:
            if v.index in visited:
                continue
            stack = [v]
            comp = []
            visited.add(v.index)
            while stack:
                curr = stack.pop()
                comp.append(curr.index)
                for e in curr.link_edges:
                    nb = e.other_vert(curr)
                    if nb.index not in visited:
                        visited.add(nb.index)
                        stack.append(nb)
            islands.append(comp)
        bm.free()

        extend_cliff_anchors = obj_name in (
            "GEO_R4_Vertikalno_Dizalo_Za_Led",
            "GEO_R3_Potporne_Grede_Duge_Galerije",
            "GEO_R5_Spojni_Mostici_I_Rampe",
        )
        for comp_indices in islands:
            orig_pts = [Vector(attr.data[idx].vector) for idx in comp_indices]
            min_x = min(p.x for p in orig_pts)
            max_x = max(p.x for p in orig_pts)
            min_z = min(p.z for p in orig_pts)
            max_z = max(p.z for p in orig_pts)
            cy = 0.5 * (min(p.y for p in orig_pts) + max(p.y for p in orig_pts))
            cz = 0.5 * (min_z + max_z)
            dx = float(delta_x_fn(cy, cz))
            is_cross_beam = extend_cliff_anchors and (max_x - min_x > 1.8)
            is_r2_portal_arch = (
                obj_name == "GEO_R2_Portal_Bocnog_Rudarskog_Okna"
                and (96.0 <= cy <= 108.0)
                and (min_x < 13.0)
                and (13.8 <= max_x <= 14.6)
            )
            is_r4_outer_leg = (
                obj_name == "GEO_R4_Vertikalno_Dizalo_Za_Led"
                and (max_z - min_z > 30.0)
                and (max_x < 12.5)
            )
            for idx, p_orig in zip(comp_indices, orig_pts):
                nx = p_orig.x + dx
                nz = p_orig.z
                if is_cross_beam and p_orig.x > 14.85:
                    nx += 4.80
                if is_r2_portal_arch and p_orig.x > 13.75:
                    nx += 2.40
                if is_r4_outer_leg and nz < -12.05:
                    nz = -12.05
                mesh.vertices[idx].co = (nx, p_orig.y, nz)
        mesh.update()

    r2_start_x, _ = _interp_curve_x("CRV_S3_Skela_R2_Iz_Bocnog_Okna", 106.0)
    r2_step_x, _ = _interp_curve_x("CRV_S3_Skela_R2_Desna_Stepenica", 135.0)
    r4_gal_x, _ = _interp_curve_x("CRV_S3_Skela_R4_Galerija_Dizala", 292.0)
    r5_mid_x, _ = _interp_curve_x("CRV_S3_Skela_R5_Srednja_Etaža", 380.0)
    r6_top_x, _ = _interp_curve_x("CRV_S3_Skela_R6_Kaskada_01_Vrh", 442.0)
    r6_mid_x, _ = _interp_curve_x("CRV_S3_Skela_R6_Kaskada_02_Sredina", 464.0)
    r6_low_x, _ = _interp_curve_x("CRV_S3_Skela_R6_Kaskada_03_Ulaz_U_Tvornicu", 486.0)

    # 4B. Rebuild `SM_Mine_Timber_Scaffold_Bent`, `SM_Mine_Plank_Deck_Segment`, and `SM_Mine_Cantilever_Pulley_Hoist`
    #     so ZERO vertical posts or cross-joist cut ends dangle/float in front of the natural glacier cliff!
    def _rebuild_cantilever_scaffold_bent_mesh():
        bent_obj = bpy.data.objects.get("SM_Mine_Timber_Scaffold_Bent")
        if bent_obj and bent_obj.data:
            mesh_b = bent_obj.data
            bm_b = bmesh.new()

            def _b_box(x0, x1, y0, y1, z0, z1, mat_idx=0):
                ret = bmesh.ops.create_cube(bm_b, size=1.0)
                verts = ret["verts"]
                bmesh.ops.scale(bm_b, vec=(x1 - x0, y1 - y0, z1 - z0), verts=verts)
                bmesh.ops.translate(bm_b, vec=(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)), verts=verts)
                for v in verts:
                    for f in v.link_faces:
                        f.material_index = mat_idx

            def _b_strut(p0, p1, rx=0.15, ry=0.15, mat_idx=0):
                v0, v1 = Vector(p0), Vector(p1)
                dv = v1 - v0
                length = dv.length
                if length < 1e-4:
                    return
                z_axis = dv / length
                ref = Vector((0.0, 1.0, 0.0)) if abs(z_axis.y) < 0.9 else Vector((1.0, 0.0, 0.0))
                x_axis = ref.cross(z_axis).normalized()
                y_axis = z_axis.cross(x_axis).normalized()
                mid = 0.5 * (v0 + v1)
                ret = bmesh.ops.create_cube(bm_b, size=1.0)
                verts = ret["verts"]
                for v in verts:
                    lx, ly, lz = v.co.x * (rx * 2.0), v.co.y * (ry * 2.0), v.co.z * length
                    v.co = mid + x_axis * lx + y_axis * ly + z_axis * lz
                    for f in v.link_faces:
                        f.material_index = mat_idx

            # 1. Outer Vertical Post (`X = -1.65 m, Z = -0.36 .. +3.82 m`) & Cliff-Wall Vertical Bearing Post (`X = +1.65 m, Z = -2.75 .. +3.82 m`)
            _b_box(-1.65 - 0.16, -1.65 + 0.16, -0.16, 0.16, -0.36, 3.82, mat_idx=0)
            _b_box(-1.65 - 0.22, -1.65 + 0.22, -0.22, 0.22, -0.44, -0.02, mat_idx=1)
            # Cliff-side wall post runs down to the lower forged-iron rock-anchor gusset (`Z = -2.75 m`)
            _b_box( 1.65 - 0.16,  1.65 + 0.16, -0.16, 0.16, -2.75, 3.82, mat_idx=0)
            _b_box( 1.65 - 0.22,  1.65 + 0.22, -0.22, 0.22, -0.42,  0.14, mat_idx=1)

            # 2. Main Horizontal Deck Ledger Beam (`Z = -0.36 .. -0.04 m`), Overhead Roof Shoring Crossbeam (`Z = +3.39 .. +3.71 m`),
            #    and Lower Horizontal Cliff Rock-Anchor Beam (`Z = -2.78 .. -2.42 m`) extending to `X = +8.50 m` deep inside the glacier cliff!
            _b_box(-1.82, 8.50, -0.17, 0.17, -0.36, -0.04, mat_idx=0)
            _b_box(-1.82, 8.50, -0.15, 0.15,  3.39,  3.71, mat_idx=0)
            _b_box( 1.45, 8.50, -0.16, 0.16, -2.78, -2.42, mat_idx=0)
            # Forged-iron bolted rock-anchor collar at the lower cliff wall joint (`X = +1.42 .. +2.15 m, Z = -2.85 .. -2.35 m`)
            _b_box( 1.42, 2.15, -0.22, 0.22, -2.85, -2.35, mat_idx=1)
            _b_box( 1.39, 2.18, -0.05, 0.05, -2.65, -2.55, mat_idx=2)

            # 3. Triangular Gallows-Bracket Diagonal Knee-Brace Strut from outer deck collar (`X = -1.60, Z = -0.24`)
            #    framing directly into the lower forged-iron cliff-wall gusset collar (`X = +1.65, Z = -2.60`)!
            _b_strut((-1.60, 0.0, -0.24), (1.68, 0.0, -2.60), rx=0.16, ry=0.16, mat_idx=0)
            # Secondary mid-deck diagonal brace into mid cliff-wall collar (`X = +1.65, Z = -1.45`) + horizontal rock anchor
            _b_strut((-0.10, 0.0, -0.22), (1.68, 0.0, -1.45), rx=0.13, ry=0.13, mat_idx=0)
            _b_box( 1.45, 8.50, -0.14, 0.14, -1.62, -1.30, mat_idx=0)
            _b_box( 1.42, 2.05, -0.20, 0.20, -1.68, -1.24, mat_idx=1)

            # 4. Upper Mortise-and-Tenon Knee Braces (`Z = +2.35 .. +3.50 m`)
            _b_strut((-1.62, 0.0, 2.35), (-0.55, 0.0, 3.50), rx=0.12, ry=0.12, mat_idx=0)
            _b_strut(( 1.62, 0.0, 2.35), ( 0.55, 0.0, 3.50), rx=0.12, ry=0.12, mat_idx=0)
            _b_strut(( 1.65, 0.0, 2.35), ( 6.80, 0.0, 5.20), rx=0.12, ry=0.12, mat_idx=0)

            # 5. Forged-Iron Bolted Joint Collars at the structural post intersections (`X = ±1.65 m`)
            for sx in (-1.65, 1.65):
                for sz in (2.35, 3.55):
                    _b_box(sx - 0.22, sx + 0.22, -0.22, 0.22, sz - 0.23, sz + 0.23, mat_idx=1)
                    _b_box(sx - 0.25, sx + 0.25, -0.04, 0.04, sz - 0.04, sz + 0.04, mat_idx=2)

            # 6. Forged-iron pipe saddles & brass steam valves on inner post (`X = +1.35..+1.65 m, Z = +1.45 / +2.05 m`)
            for sz in (1.45, 2.05):
                _b_box(1.30, 1.72, -0.18, 0.18, sz - 0.14, sz + 0.14, mat_idx=1)
                ret_c = bmesh.ops.create_cone(bm_b, cap_ends=True, segments=12, radius1=0.18, radius2=0.18, depth=0.28)
                bmesh.ops.rotate(bm_b, cent=(0, 0, 0), matrix=Euler((math.radians(90.0), 0.0, 0.0)).to_matrix(), verts=ret_c["verts"])
                bmesh.ops.translate(bm_b, vec=(1.35, 0.0, sz), verts=ret_c["verts"])
                for v in ret_c["verts"]:
                    for f in v.link_faces:
                        f.material_index = 2

            bm_b.normal_update()
            bm_b.to_mesh(mesh_b)
            bm_b.free()
            mesh_b.update()

        # Also rebuild `SM_Mine_Plank_Deck_Segment` so all 4 under-deck cross-joists (`Y = 0.15, 1.45, 2.75, 4.05`)
        # and the cliff-side wooden deck planks extend continuously into the natural glacier cliff (`X = +5.2 .. +6.8 m`)!
        seg_obj = bpy.data.objects.get("SM_Mine_Plank_Deck_Segment")
        if seg_obj and seg_obj.data:
            mesh_s = seg_obj.data
            bm_s = bmesh.new()

            def _s_box(x0, x1, y0, y1, z0, z1, mat_idx=0):
                ret = bmesh.ops.create_cube(bm_s, size=1.0)
                verts = ret["verts"]
                bmesh.ops.scale(bm_s, vec=(x1 - x0, y1 - y0, z1 - z0), verts=verts)
                bmesh.ops.translate(bm_s, vec=(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)), verts=verts)
                for v in verts:
                    for f in v.link_faces:
                        f.material_index = mat_idx

            # 15 longitudinal timber deck planks spanning from outer guardrail (`X = -1.53 m`) all the way into the glacier cliff (`X = +5.05 m`)
            plank_xs = [-1.32, -0.88, -0.44, 0.00, 0.44, 0.88, 1.32, 1.76, 2.20, 2.64, 3.08, 3.52, 3.96, 4.40, 4.84]
            for idx_p, cx_p in enumerate(plank_xs):
                zt = 0.000 if (idx_p % 2 == 0) else -0.003
                _s_box(cx_p - 0.21, cx_p + 0.21, -0.06, 4.26, -0.070, zt, mat_idx=0)

            # Outer guardrail curb (`X = -1.58 .. -1.45 m`)
            _s_box(-1.58, -1.45, -0.06, 4.26, -0.070, 0.090, mat_idx=0)

            # Longitudinal under-deck stringers (`X = -1.30, +1.30, +2.85 m`)
            for sx_str in (-1.30, 1.30, 2.85):
                _s_box(sx_str - 0.12, sx_str + 0.12, -0.06, 4.26, -0.220, -0.070, mat_idx=0)

            # 4 Under-deck cross-joists (`Y = 0.15, 1.45, 2.75, 4.05 m`) extending all the way into the natural glacier cliff (`X = +6.80 m`)!
            for y_cj in (0.15, 1.45, 2.75, 4.05):
                _s_box(-1.60, 6.80, y_cj - 0.11, y_cj + 0.11, -0.210, -0.070, mat_idx=0)

            bm_s.normal_update()
            bm_s.to_mesh(mesh_s)
            bm_s.free()
            mesh_s.update()

        # Also extend the top cantilever beam of `SM_Mine_Cantilever_Pulley_Hoist` into the natural glacier cliff (`X = +7.20 m`)
        hoist_obj = bpy.data.objects.get("SM_Mine_Cantilever_Pulley_Hoist")
        if hoist_obj and hoist_obj.data:
            for v in hoist_obj.data.vertices:
                if v.co.z > 3.60 and v.co.x > 1.90:
                    v.co.x = 7.20
            hoist_obj.data.update()

    _rebuild_cantilever_scaffold_bent_mesh()

    # 4C. Rebuild `GEO_R2_Spojeni_Drveni_Pod_Tunel_I_Zavoj` (in canonical X=12.0 coords) so it has ZERO dangling vertical outer stumps
    #     and its corner platform planks & diagonal cantilever struts extend deep (`X = 17.8..19.8 m`) into the natural glacier wall!
    def _rebuild_r2_corner_deck_for_natural_cliff():
        deck_obj = bpy.data.objects.get("GEO_R2_Spojeni_Drveni_Pod_Tunel_I_Zavoj")
        if not deck_obj or not deck_obj.data:
            return
        mesh_d = deck_obj.data
        for attr_n in ("_s3_orig_co", "_sv_orig_co"):
            if attr_n in mesh_d.attributes:
                mesh_d.attributes.remove(mesh_d.attributes[attr_n])
        bm_d = bmesh.new()

        def _d_box(x0, x1, y0, y1, z0, z1, mat_idx=0):
            ret = bmesh.ops.create_cube(bm_d, size=1.0)
            verts = ret["verts"]
            bmesh.ops.scale(bm_d, vec=(x1 - x0, y1 - y0, z1 - z0), verts=verts)
            bmesh.ops.translate(bm_d, vec=(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)), verts=verts)
            for v in verts:
                for f in v.link_faces:
                    f.material_index = mat_idx

        def _d_strut(p0, p1, radius=0.15, mat_idx=0):
            v0, v1 = Vector(p0), Vector(p1)
            dv = v1 - v0
            length = dv.length
            if length < 1e-4:
                return
            z_axis = dv / length
            ref = Vector((0.0, 1.0, 0.0)) if abs(z_axis.y) < 0.9 else Vector((1.0, 0.0, 0.0))
            x_axis = ref.cross(z_axis).normalized()
            y_axis = z_axis.cross(x_axis).normalized()
            mid = 0.5 * (v0 + v1)
            ret = bmesh.ops.create_cube(bm_d, size=1.0)
            verts = ret["verts"]
            for v in verts:
                lx, ly, lz = v.co.x * (radius * 2.0), v.co.y * (radius * 2.0), v.co.z * length
                v.co = mid + x_axis * lx + y_axis * ly + z_axis * lz
                for f in v.link_faces:
                    f.material_index = mat_idx

        # A. Corner Landing Platform outside the tunnel exit (`X = 10.42 .. 17.60, Y = 97.10 .. 106.12, Z_top = 0.000`)
        plank_offsets = [-1.32, -0.88, -0.44, 0.00, 0.44, 0.88, 1.32, 1.76, 2.20, 2.64, 3.08, 3.52, 3.96, 4.40, 4.84, 5.28]
        for idx, dx_p in enumerate(plank_offsets):
            cx = 12.0 + dx_p
            z_t = 0.000 if idx % 2 == 0 else -0.003
            _d_box(cx - 0.212, cx + 0.212, 97.10, 106.12, -0.068, z_t, mat_idx=0)

        # Outer curb beam (`X = 10.42..10.55`) & southern curb (`Y = 97.10..97.26`) extending into the cliff (`X = 17.60`)
        _d_box(10.42, 10.55, 97.10, 106.12, -0.068, 0.085, mat_idx=0)
        _d_box(10.42, 17.60, 97.10, 97.26, -0.068, 0.085, mat_idx=0)

        # Under-deck longitudinal stringers & cross-beams extending deep into the cliff (`X = 19.50`)
        _d_box(10.58, 10.82, 97.10, 106.12, -0.220, -0.068, mat_idx=0)
        _d_box(13.18, 13.42, 97.10, 106.12, -0.220, -0.068, mat_idx=0)
        for yc in (97.35, 99.55, 101.80, 104.00, 105.95):
            _d_box(10.35, 19.50, yc - 0.15, yc + 0.15, -0.360, -0.068, mat_idx=0)

        # Under-deck triangular cliff-wall gallows brackets (`Y = 97.35, 101.80, 105.85`)
        # ZERO vertical stumps hanging in empty air! Diagonal knee-brace frames into a forged-iron cliff-wall gusset + horizontal rock anchor!
        for yc in (97.35, 101.80, 105.85):
            _d_box(10.22, 10.62, yc - 0.20, yc + 0.20, -0.460, -0.060, mat_idx=1)
            # Cliff-wall vertical bearing post (`X = 13.65, Z = -2.80 .. -0.06 m`)
            _d_box(13.49, 13.81, yc - 0.16, yc + 0.16, -2.800, -0.060, mat_idx=0)
            # Lower forged-iron cliff gusset collar + horizontal rock-anchor beam (`X = 13.42 .. 19.50 m, Z = -2.82 .. -2.44 m`)
            _d_box(13.42, 14.15, yc - 0.22, yc + 0.22, -2.880, -2.380, mat_idx=1)
            _d_box(13.45, 19.50, yc - 0.16, yc + 0.16, -2.800, -2.440, mat_idx=0)
            _d_strut((10.42, yc, -0.26), (13.68, yc, -2.62), radius=0.16, mat_idx=0)
            _d_strut((11.90, yc, -0.24), (13.68, yc, -1.48), radius=0.13, mat_idx=0)
            _d_box(13.45, 19.50, yc - 0.14, yc + 0.14, -1.640, -1.320, mat_idx=0)
            _d_box(13.42, 14.05, yc - 0.20, yc + 0.20, -1.700, -1.260, mat_idx=1)

        # Outer wooden safety handrail along the cliff drop-off edge (`X = 10.48, Y = 97.20 .. 106.05`)
        for yc in (97.25, 99.45, 101.80, 104.10, 105.95):
            _d_box(10.40, 10.56, yc - 0.08, yc + 0.08, 0.00, 1.12, mat_idx=0)
            _d_box(10.36, 10.60, yc - 0.11, yc + 0.11, 0.00, 0.14, mat_idx=1)
        _d_box(10.41, 10.55, 97.18, 106.05, 0.98, 1.10, mat_idx=0)
        _d_box(10.42, 10.54, 97.18, 106.05, 0.50, 0.60, mat_idx=0)
        # Southern end guardrail at Y = 97.25 (`X = 10.45 .. 17.50`) anchored directly into the southern ice cliff!
        _d_box(10.45, 17.50, 97.17, 97.31, 0.98, 1.10, mat_idx=0)
        _d_box(10.45, 17.50, 97.18, 97.30, 0.50, 0.60, mat_idx=0)

        # B. Interior Tunnel Wooden Plank Deck (`X = 13.56 .. 28.20, Y = 98.70 .. 105.30, Z_top = 0.000`)
        tunnel_y_centers = [99.10, 99.65, 100.20, 100.75, 101.30, 101.85, 102.40, 102.95, 103.50, 104.05, 104.60, 105.10]
        for idx, cy in enumerate(tunnel_y_centers):
            z_t = 0.000 if idx % 2 == 0 else -0.003
            _d_box(13.56, 28.20, cy - 0.26, cy + 0.26, -0.068, z_t, mat_idx=0)
        for xc in (14.6, 16.9, 19.3, 21.6, 24.0, 26.3, 28.0):
            _d_box(xc - 0.16, xc + 0.16, 98.55, 105.45, -0.180, -0.068, mat_idx=0)

        bm_d.normal_update()
        bm_d.to_mesh(mesh_d)
        bm_d.free()
        mesh_d.update()

    _rebuild_r2_corner_deck_for_natural_cliff()

    # Shift `GEO_R2_Portal_Bocnog_Rudarskog_Okna` (portal at Y=96..107 uses `r2_start_x - 12.0`; ramp at Y=123..137 uses `r2_step_x - 12.1`)
    _shift_static_geo_mesh(
        "GEO_R2_Portal_Bocnog_Rudarskog_Okna",
        lambda cy, cz: (r2_start_x - 12.0) if cy < 115.0 else (_interp_curve_x("CRV_S3_Skela_R2_Iz_Bocnog_Okna", cy)[0] - 12.0),
    )

    # Shift `GEO_R2_Spojeni_Drveni_Pod_Tunel_I_Zavoj` by `r2_start_x - 12.0`
    _shift_static_geo_mesh(
        "GEO_R2_Spojeni_Drveni_Pod_Tunel_I_Zavoj",
        lambda cy, cz: (r2_start_x - 12.0),
    )

    # Shift `GEO_R3_Potporne_Grede_Duge_Galerije` (R1 upper shelf struts at Y=22..38 use `CRV_S3_Skela_R1_Gornja_Polica`)
    _shift_static_geo_mesh(
        "GEO_R3_Potporne_Grede_Duge_Galerije",
        lambda cy, cz: (
            (_interp_curve_x("CRV_S3_Skela_R1_Gornja_Polica", cy)[0] - 11.8)
            if (cy < 100.0 and cz > 4.0)
            else (
                (_interp_curve_x("CRV_S3_Skela_R1_Glavna_Galerija", cy)[0] - 11.8)
                if cy < 100.0
                else (_interp_curve_x("CRV_S3_Skela_R3_Duga_Galerija", cy)[0] - 13.0)
            )
        ),
    )

    # Shift `GEO_R4_Vertikalno_Dizalo_Za_Led`, `GEO_R5_Spojni_Mostici_I_Rampe`, `GEO_R6_Kaskadni_Lijevci_Za_Led_Cupar`
    _shift_static_geo_mesh("GEO_R4_Vertikalno_Dizalo_Za_Led", lambda cy, cz: (r4_gal_x - 11.8))
    _shift_static_geo_mesh("GEO_R5_Spojni_Mostici_I_Rampe", lambda cy, cz: (r5_mid_x - 11.8))
    _shift_static_geo_mesh(
        "GEO_R6_Kaskadni_Lijevci_Za_Led_Cupar",
        lambda cy, cz: (r6_top_x - 12.5) if cy < 452.0 else ((r6_mid_x - 12.5) if cy < 476.0 else (r6_low_x - 12.0)),
    )

    # Remove any old floating rock/ice chunks in `GEO_Spilja_Odroni_Kamena_I_Leda` that overlap the scaffolding zone
    odroni_obj = bpy.data.objects.get("GEO_Spilja_Odroni_Kamena_I_Leda")
    if odroni_obj and odroni_obj.type == "MESH" and odroni_obj.data:
        bm_o = bmesh.new()
        bm_o.from_mesh(odroni_obj.data)
        bm_o.verts.ensure_lookup_table()
        verts_del = [v for v in bm_o.verts if v.co.x > 9.5 and v.co.z > -4.5 and 15.0 <= v.co.y <= 505.0]
        if verts_del:
            bmesh.ops.delete(bm_o, geom=verts_del, context="VERTS")
            bm_o.to_mesh(odroni_obj.data)
            odroni_obj.data.update()
        bm_o.free()

    # 5. Update 3D Narrow-Gauge Railway Curves (`CRV_S3_MC_Track_R2_Bocno_Okno`, `CRV_S3_MC_Track_R3_Duga_Galerija`)
    from .minecart_pusher import build_or_update_3d_rails_for_curve, update_all_scene_minecarts
    from .locomotion import attach_controller_to_locomotion_curve, resample_curve_uniform_arclength
    from .human_tools import turn_controller_towards

    def _build_monotone_bezier_track(crv_obj: bpy.types.Object, pts: list[tuple[float, float, float]]):
        crv_obj.data.splines.clear()
        sp = crv_obj.data.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        vecs = [Vector(p) for p in pts]
        n = len(vecs)
        for i, v in enumerate(vecs):
            bp = sp.bezier_points[i]
            bp.co = v
            bp.handle_left_type = "ALIGNED"
            bp.handle_right_type = "ALIGNED"
            if i == 0:
                tang = (vecs[1] - vecs[0])
                hlen = tang.length * 0.33
                t_dir = tang.normalized() if tang.length > 1e-6 else Vector((0, 1, 0))
                bp.handle_left = v - t_dir * hlen
                bp.handle_right = v + t_dir * hlen
            elif i == n - 1:
                tang = (vecs[-1] - vecs[-2])
                hlen = tang.length * 0.33
                t_dir = tang.normalized() if tang.length > 1e-6 else Vector((0, 1, 0))
                bp.handle_left = v - t_dir * hlen
                bp.handle_right = v + t_dir * hlen
            else:
                d_prev = vecs[i] - vecs[i - 1]
                d_next = vecs[i + 1] - vecs[i]
                t_dir = (d_prev.normalized() + d_next.normalized())
                if t_dir.length > 1e-6:
                    t_dir.normalize()
                else:
                    t_dir = Vector((0, 1, 0))
                if d_next.y > 1.8 and abs(d_next.x) < 0.35:
                    t_dir.x = (d_next.x / max(1e-4, d_next.length))
                    t_dir.normalize()
                bp.handle_left = v - t_dir * (d_prev.length * 0.32)
                bp.handle_right = v + t_dir * (d_next.length * 0.32)

    crv_mc_r2 = bpy.data.objects.get("CRV_S3_MC_Track_R2_Bocno_Okno")
    if crv_mc_r2 and crv_mc_r2.type == "CURVE":
        r2_pts = [
            (r2_start_x + 14.20, 102.00, 0.004),
            (r2_start_x + 2.45, 102.00, 0.004),
            (r2_start_x + 0.18, 103.35, 0.004),
            (_interp_curve_x("CRV_S3_Skela_R2_Iz_Bocnog_Okna", 107.20)[0], 107.20, 0.004),
            (_interp_curve_x("CRV_S3_Skela_R2_Iz_Bocnog_Okna", 129.50)[0], 129.50, 0.004),
            (_interp_curve_x("CRV_S3_Skela_R2_Iz_Bocnog_Okna", 152.80)[0], 152.80, 0.004),
        ]
        _build_monotone_bezier_track(crv_mc_r2, r2_pts)
        resample_curve_uniform_arclength(crv_mc_r2)
        build_or_update_3d_rails_for_curve(crv_mc_r2)

    crv_mc_r3 = bpy.data.objects.get("CRV_S3_MC_Track_R3_Duga_Galerija")
    if crv_mc_r3 and crv_mc_r3.type == "CURVE":
        r3_ys = [175.0, 189.7, 204.4, 219.1, 233.8]
        r3_pts = []
        for y_pt in r3_ys:
            cx, cz = _interp_curve_x("CRV_S3_Skela_R3_Duga_Galerija", y_pt)
            r3_pts.append((cx, y_pt, cz + 0.004))
        _build_monotone_bezier_track(crv_mc_r3, r3_pts)
        resample_curve_uniform_arclength(crv_mc_r3)
        build_or_update_3d_rails_for_curve(crv_mc_r3)

    # Re-bind any attached minecart pushers to the updated railway curves
    for obj in bpy.data.objects:
        if obj.get("af_is_char_controller") and obj.get("af_attached_curve"):
            c_obj = bpy.data.objects.get(str(obj.get("af_attached_curve", "")))
            if c_obj and c_obj.type == "CURVE":
                attach_controller_to_locomotion_curve(ctx, obj, c_obj)

    # 6. Snap scaffold workers (`CTRL_Elf_*`, unparented only!) and deck cargo props (`S3_CargoProp_*`) to the snapped deck,
    #    and ensure any ropeway gondola passenger elves (`obj.parent is not None`) remain seated inside their gondola!
    CANONICAL_DECK_OFFSETS = {
        "CTRL_ELF28_01": 1.05,
        "CTRL_ELF14_02": -1.00,
        "CTRL_ELF21_02": -0.85,
        "S3_CargoProp_01_CrateStack": 1.15,
        "S3_CargoProp_02_SackPile": 1.15,
        "S3_CargoProp_03_BarrelCluster": 1.10,
        "S3_CargoProp_04_R3_CrateStack": -0.80,
        "S3_CargoProp_05_R3_PickaxeAndShovelRack": 1.15,
    }
    for obj in bpy.data.objects:
        if obj.get("af_is_char_controller") and not obj.get("af_attached_curve") and not obj.get("af_cb_rig_root"):
            if obj.parent is not None:
                # Ropeway gondola passenger elf — keep seated inside gondola cabin!
                if obj.parent.name.startswith("RW_"):
                    obj.location = (0.0, 0.12, -2.79)
                continue
            y_w = float(obj.location.y)
            crv_key = "CRV_S3_Skela_R2_Iz_Bocnog_Okna" if y_w < 164.0 else "CRV_S3_Skela_R3_Duga_Galerija"
            cx, cz = _interp_curve_x(crv_key, y_w)
            orig_dx = float(CANONICAL_DECK_OFFSETS.get(obj.name, obj.get("_s3_deck_dx", 0.95)))
            obj["_s3_deck_dx"] = orig_dx
            obj.location.x = round(cx + orig_dx, 3)
            obj.location.z = round(cz + 0.005, 3)
        elif obj.name.startswith("S3_CargoProp_"):
            y_p = float(obj.location.y)
            crv_key = "CRV_S3_Skela_R2_Iz_Bocnog_Okna" if y_p < 164.0 else "CRV_S3_Skela_R3_Duga_Galerija"
            cx, cz = _interp_curve_x(crv_key, y_p)
            orig_dx = float(CANONICAL_DECK_OFFSETS.get(obj.name, obj.get("_s3_deck_dx", 1.10)))
            obj["_s3_deck_dx"] = orig_dx
            obj.location.x = round(cx + orig_dx, 3)
            obj.location.z = round(cz + 0.005, 3)

    # 6B. Snap R1..R6 gallery warm 2400K lights to follow the adapted scaffolding curves (never trapped behind the natural glacier wall!)
    GALLERY_LIGHT_SPECS = [
        ("LGT_R1_Gallery_Warm_2400K", "CRV_S3_Skela_R1_Glavna_Galerija", 42.0, 0.25),
        ("LGT_R2_AditPortal_2400K", "CRV_S3_Skela_R2_Iz_Bocnog_Okna", 106.0, 0.35),
        ("LGT_R2_AditTunnel_Warm_2200K", "CRV_S3_Skela_R2_Iz_Bocnog_Okna", 102.0, 4.20),
        ("LGT_R2_TunnelDeep_2200K", "CRV_S3_Skela_R2_Iz_Bocnog_Okna", 102.0, 9.50),
        ("LGT_R3_Overhang_Warm_2400K", "CRV_S3_Skela_R3_Duga_Galerija", 208.0, 0.25),
        ("LGT_R3_Crusher_Warm_2400K", "CRV_S3_Skela_R3_Duga_Galerija", 208.0, 0.25),
        ("LGT_R4_WinchGallery_2400K", "CRV_S3_Skela_R4_Galerija_Dizala", 292.0, 0.25),
        ("LGT_R4_Elevator_2400K", "CRV_S3_Skela_R4_Galerija_Dizala", 292.0, 0.25),
        ("LGT_R5_Catwalk_2400K", "CRV_S3_Skela_R5_Srednja_Etaža", 378.0, 0.25),
        ("LGT_R5_MidCatwalk_2400K", "CRV_S3_Skela_R5_Srednja_Etaža", 380.0, 0.25),
        ("LGT_R6_HopperCascade_2400K", "CRV_S3_Skela_R6_Kaskada_02_Sredina", 464.0, 0.25),
    ]
    for l_name, l_crv, l_y, l_dx in GALLERY_LIGHT_SPECS:
        l_obj = bpy.data.objects.get(l_name)
        if l_obj:
            lx, _ = _interp_curve_x(l_crv, float(l_obj.location.y))
            l_obj.location.x = round(lx + l_dx, 3)

    # Ensure warm 2400K grazing gallery light `LGT_R2_Gallery_Warm_2400K` rakes across the R2 cliff face & CB_ROOT_01
    lgt_r2_gal = bpy.data.objects.get("LGT_R2_Gallery_Warm_2400K")
    if not lgt_r2_gal:
        ldata = bpy.data.lights.new("LGT_R2_Gallery_Warm_2400K", type="POINT")
        lgt_r2_gal = bpy.data.objects.new("LGT_R2_Gallery_Warm_2400K", ldata)
        scn.collection.objects.link(lgt_r2_gal)
    lgt_r2_gal.data.energy = 3600.0
    lgt_r2_gal.data.color = (1.0, 0.58, 0.24)
    lgt_r2_gal.data.shadow_soft_size = 1.25
    r2_lgt_x, _ = _interp_curve_x("CRV_S3_Skela_R2_Iz_Bocnog_Okna", 112.5)
    lgt_r2_gal.location = (round(r2_lgt_x - 2.35, 3), 112.5, 7.6)

    # 6C. Snap Ropeway cliffside terminal stations (`GIZMO_RW_01..03_Null_01`) to the natural glacier wall with CLIFF_WALL_BRACKET
    #     so no 14m vertical ropeway ground tower ever crashes down through the R2 or R3 wooden scaffolding galleries!
    try:
        from .ropeway_gondolas import (
            get_all_ropeway_systems,
            get_system_null_point_objects,
            _rebuild_pylon_hardware_for_null,
            apply_ropeway_evaluation_to_system,
        )
        for sys_root in get_all_ropeway_systems(scn):
            sys_col = sys_root.users_collection[0] if sys_root.users_collection else scn.collection
            nulls = get_system_null_point_objects(sys_root)
            if nulls:
                n0 = nulls[0]
                if float(n0.location.x) > 6.0:
                    w_hit_x, _ = sample_glacier_wall_surface(wall_eval, float(n0.location.y), float(n0.location.z))
                    n0.location.x = round(w_hit_x - 1.55, 3)
                    n0["af_rw_null_support_mode"] = "CLIFF_WALL_BRACKET"
                    sys_root.location.x = n0.location.x
                    _rebuild_pylon_hardware_for_null(sys_root, n0, sys_col)
            apply_ropeway_evaluation_to_system(sys_root, float(scn.frame_current), scene=scn)
    except Exception as e:
        print("[WARN] Ropeway cliff terminal snap:", e)

    # 7. Snap all hanging Cliff Baskets (`CB_ROOT_01..04`) flush to the glacier wall
    baskets_snapped = []
    for rig_root in get_all_cliff_basket_rigs(scn):
        b_info = snap_single_basket_to_glacier_wall(rig_root, wall_eval=wall_eval)
        baskets_snapped.append(b_info)

    # 7B. Update verification cameras idempotently by the adapted gallery ΔX so they always frame R2/R3 cleanly
    r3_mean_x = float(curve_profiles.get("CRV_S3_Skela_R3_Duga_Galerija", {}).get("mean_x", 13.5))
    dx_r2 = r2_start_x - 12.00
    dx_r3 = r3_mean_x - 13.00
    cb01 = bpy.data.objects.get("CB_ROOT_01")
    dx_cb01 = (float(cb01.location.x) - 13.35) if cb01 else dx_r2

    cam_baseline_specs = {
        "CAM_Verify_R2_01_Tunel_I_Zavoj": (4.50, 92.80, 3.80, dx_r2),
        "CAM_Verify_R2_01_Portal_Exit": (2.60, 84.50, 4.20, dx_r2),
        "CAM_Verify_R2_02_Minecart_I_Podnica": (5.80, 121.50, 2.55, dx_r2),
        "CAM_Verify_R2_02_Minecart_Gallery": (9.15, 108.50, 2.25, dx_r2),
        "CAM_Verify_R2_03_Kosara_I_Kramp": (9.20, 111.80, 7.05, dx_cb01),
        "CAM_Verify_R2_03_Cliff_Basket_Closeup": (7.70, 109.20, 5.10, dx_cb01),
        "CAM_Verify_R3_04_Duga_Galerija": (5.20, 236.50, 4.10, dx_r3),
        "CAM_Verify_R3_04_Long_Gallery_And_Baskets": (4.50, 165.00, 5.20, dx_r3),
        "CAM_Verify_01_R2_R3_Kosare_i_Galerije": (3.80, 241.50, 3.50, dx_r3),
        "CAM_Verify_03_R2_Bocno_Okno_CloseUp": (5.40, 125.00, 2.20, dx_r2),
    }
    for cam_name, (orig_x, orig_y, orig_z, cam_dx) in cam_baseline_specs.items():
        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj:
            cam_obj.location = (round(orig_x + cam_dx, 3), orig_y, orig_z)

    cam_r3 = bpy.data.objects.get("CAM_Verify_R3_04_Duga_Galerija") or bpy.data.objects.get("CAM_Verify_R3_04_Long_Gallery_And_Baskets")
    for obj in bpy.data.objects:
        if obj.get("s3_worker_label") == "Skela_R3_Pozdrav_Hero_Kamera" and cam_r3:
            turn_controller_towards(ctx, obj, tuple(cam_r3.location))

    # 8. Enable the R2 tunnel opening Geometry Nodes modifier on `GEO_Spilja_Desni_Ledeni_Zid`
    _ensure_r2_tunnel_boolean_cutter_on_wall(wall_obj, r2_portal_x=r2_start_x + 1.20)
    wall_obj.update_tag()

    update_all_scene_minecarts(scene=scn)
    ctx.view_layer.update()

    return {
        "wall_standoff_m": float(wall_standoff_m),
        "smoothing_window": int(smoothing_window),
        "r2_gallery_x": round(r2_start_x, 3),
        "r3_gallery_mean_x": curve_profiles.get("CRV_S3_Skela_R3_Duga_Galerija", {}).get("mean_x", 0.0),
        "baskets_snapped": baskets_snapped,
    }


# Alias matching prompt description
snap_all_scaffolding_and_actors_to_glacier_wall = sync_scaffolding_and_rails_to_glacier_wall


def register_cliff_basket_handlers():
    register_cliff_basket_object_properties()
    for h in list(bpy.app.handlers.frame_change_post):
        if getattr(h, "__name__", "") == "af_cliff_baskets_frame_handler":
            bpy.app.handlers.frame_change_post.remove(h)
    bpy.app.handlers.frame_change_post.append(af_cliff_baskets_frame_handler)

    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "af_cliff_baskets_depsgraph_handler":
            bpy.app.handlers.depsgraph_update_post.remove(h)
    bpy.app.handlers.depsgraph_update_post.append(af_cliff_baskets_depsgraph_handler)


def unregister_cliff_basket_handlers():
    for h in list(bpy.app.handlers.frame_change_post):
        if getattr(h, "__name__", "") == "af_cliff_baskets_frame_handler":
            bpy.app.handlers.frame_change_post.remove(h)
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "af_cliff_baskets_depsgraph_handler":
            bpy.app.handlers.depsgraph_update_post.remove(h)
