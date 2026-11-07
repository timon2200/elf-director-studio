# -*- coding: utf-8 -*-
"""
Minecart Curve Pusher, 3D Narrow-Gauge Rail Generator & Curve-Tangent Steering Engine
(`elf_director.minecart_pusher`)
=====================================================================================
Provides:
  1. 3D Empty & Full Minecart Loader (`SM_Minecart_01_Empty.glb` &
     `SM_Minecart_02_Full_Loaded.glb` = Empty Minecart + `SM_Basket_04_FullCargo_Ice`
     + glowing blue ice crystals from `assets/models/glb/minecart/`).
  2. 1-Click Attachment of Minecart (`MINECART_EMPTY` or `MINECART_FULL`) to any
     Elf (`CTRL_*`), automatically assigning `AF_34_Walk_Push_Minecart` (95-frame
     zero-slip locomotion cycle with both hands gripping the rear push-handle bar).
  3. Live Curve-Tangent Look-Ahead Steering (`af_minecart_pusher_frame_handler`):
     Whenever an Elf with an attached Minecart walks along any drawn curve
     (`1. Nova Putanja (3 Točke / Edit Mode)` & `2. Poveži Vilenjaka s Krivuljom`),
     evaluates the curve tangent ahead of the Elf so the minecart's 4 wheels follow
     the curved rails while the rear push-bar stays inside the Elf's gripping hands.
  4. Procedural 3D Narrow-Gauge Rails & Wooden Sleepers (`RAIL_Track_<CurveName>` +
     `GN_Minecart_Rails_On_Curve` modifier) generated directly from any drawn curve.
"""

import math
import os
import bmesh
import bpy
from bpy.app.handlers import persistent
from mathutils import Euler, Matrix, Vector

from .constants import PACKAGE_DIR, PATHS_COLLECTION_NAME, STATE, ensure_collection, get_assets_glb_dir
from .human_tools import apply_stored_settings_to_character
from .locomotion import (
    attach_controller_to_locomotion_curve,
    create_walk_curve_from_points,
)
from .nla_sequencer import apply_additive_pose_offset, clear_nla_sequence
from .rig_actors import (
    find_character_controller,
    get_active_character_controller,
    get_all_scene_character_controllers,
    spawn_elf_actor,
)

PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)
MINECART_GLB_DIR = get_assets_glb_dir("minecart")
MINECART_COLLECTION_NAME = "06_MINECART_RAILS_STUDIO"
PUSH_WALK_ACTION_NAME = "AF_34_Walk_Push_Minecart"

MINECART_VARIANTS = (
    (
        "EMPTY",
        "1. Prazni Minecart (SM_Minecart_01_Empty)",
        "SM_Minecart_01_Empty.glb",
    ),
    (
        "FULL",
        "2. Puni Minecart (s Punom Košarom + Plavim Ledom)",
        "SM_Minecart_02_Full_Loaded.glb",
    ),
)

# Ergonomic calibration matching `AF_34_Walk_Push_Minecart` hand grip coordinates:
# In `AF_34_Walk_Push_Minecart`, the Elf's gripping hands sit at:
#   X = ±0.27 m, Y = -0.495 m, Z = +1.080 m (in CTRL_* local space).
# In `SM_Minecart_01_Empty.glb` (normalized 0.86 x 1.28 x 0.94 m), the rear push-bar is at:
#   Y_raw = +0.604 m, Z_raw = +0.872 m, and wheel center X_raw = ±0.369 m.
# Scaling the minecart by `CART_SCALE = 1.20` and placing its local mesh shift at
# `Y_SHIFT = -0.340 m, Z_RAIL_TOP = 0.036 m` puts the push-bar at:
#   Y_local_in_prop = +0.604 * 1.20 - 0.340 = +0.385 m
#   Z_local_in_prop = +0.872 * 1.20 + 0.036 = +1.082 m
# So when `Prop_Minecart_<CtrlName>` is at `location = (0.0, -0.88, 0.0)` (`default 0.88 m`),
# the rear push-bar is at `Y = -0.88 + 0.385 = -0.495 m, Z = +1.082 m` — right inside the Elf's hands!
CART_SCALE = 1.14
CART_MESH_Y_SHIFT = -0.365
RAIL_HEAD_TOP_Z = 0.036
RAIL_HALF_GAUGE_M = 0.369 * CART_SCALE  # 0.421 m (full track gauge = 0.842 m)

_MINECART_HANDLER_GUARD = False


# ============================================================================
# 1. MATERIALS & 3D MINECART / CARGO MESH LOADER
# ============================================================================

def _get_or_create_mat(name: str, base_color: tuple, metallic: float = 0.0, roughness: float = 0.55):
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
    mat.diffuse_color = (*base_color[:3], 1.0)
    return mat


def _import_glb_objects(filepath: str) -> list:
    before = set(bpy.data.objects)
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    else:
        bpy.ops.import_scene.gltf(filepath=filepath)
    return [o for o in bpy.data.objects if o not in before]


def _ensure_minecart_template_meshes() -> tuple:
    """
    Loads and caches the normalized Tripo 3D meshes from `SM_Minecart_01_Empty.glb`
    and `SM_Minecart_02_Full_Loaded.glb`:
      - `TPL_MC_Body_Empty_Mesh`: the empty minecart body, wheels & rear push-bar
      - `TPL_MC_Cargo_Full_Mesh`: the combined full cargo basket (`SM_Basket_04_FullCargo_Ice`)
        + overflowing blue-ice crystal clusters inside the trough
    Applies `CART_SCALE`, `CART_MESH_Y_SHIFT`, and `RAIL_HEAD_TOP_Z` into vertex coordinates
    so `Prop_Minecart_<CtrlName>` sits at `location = (0, -0.88, 0)` with wheels on the rails
    and push-bar at `(0, +0.385, 1.082)` in prop space (`(0, -0.495, 1.082)` in Elf space).
    """
    body_mesh = bpy.data.meshes.get("TPL_MC_Body_Empty_Mesh")
    cargo_mesh = bpy.data.meshes.get("TPL_MC_Cargo_Full_Mesh")

    if body_mesh and cargo_mesh:
        return body_mesh, cargo_mesh

    full_path = os.path.join(MINECART_GLB_DIR, "SM_Minecart_02_Full_Loaded.glb")
    empty_path = os.path.join(MINECART_GLB_DIR, "SM_Minecart_01_Empty.glb")

    if os.path.isfile(full_path):
        imported = _import_glb_objects(full_path)
        meshes = [o for o in imported if o.type == "MESH" and o.data and len(o.data.vertices) > 0]
        # In SM_Minecart_02_Full_Loaded.glb, the empty minecart mesh is the one whose min Z reaches ~0.00 (the wheels)
        cart_candidates = []
        cargo_candidates = []
        for o in meshes:
            mw = o.matrix_world
            zs = [(mw @ v.co).z for v in o.data.vertices]
            if min(zs) < 0.12:
                cart_candidates.append(o)
            else:
                cargo_candidates.append(o)

        if not cart_candidates and meshes:
            cart_candidates = [meshes[0]]
            cargo_candidates = meshes[1:]

        if cart_candidates and not body_mesh:
            c_obj = cart_candidates[0]
            mw = c_obj.matrix_world.copy()
            body_mesh = c_obj.data.copy()
            body_mesh.name = "TPL_MC_Body_Empty_Mesh"
            body_mesh.use_fake_user = True
            for v in body_mesh.vertices:
                p = mw @ v.co
                v.co.x = p.x * CART_SCALE
                v.co.y = p.y * CART_SCALE + CART_MESH_Y_SHIFT
                v.co.z = p.z * CART_SCALE + RAIL_HEAD_TOP_Z
            body_mesh.update()

        if cargo_candidates and not cargo_mesh:
            # Merge all cargo sub-meshes (SM_Basket_04_FullCargo_Ice + BlueIce clusters) into one clean multi-material mesh
            bm = bmesh.new()
            cargo_mesh = bpy.data.meshes.new("TPL_MC_Cargo_Full_Mesh")
            cargo_mesh.use_fake_user = True
            mat_list = []

            for co_obj in cargo_candidates:
                mw = co_obj.matrix_world.copy()
                sub_m = co_obj.data.copy()
                mat_offset = len(mat_list)
                for m in sub_m.materials:
                    mat_list.append(m)
                    cargo_mesh.materials.append(m)
                for v in sub_m.vertices:
                    p = mw @ v.co
                    v.co.x = p.x * CART_SCALE
                    v.co.y = p.y * CART_SCALE + CART_MESH_Y_SHIFT
                    v.co.z = p.z * CART_SCALE + RAIL_HEAD_TOP_Z
                for poly in sub_m.polygons:
                    poly.material_index += mat_offset
                bm.from_mesh(sub_m)
                bpy.data.meshes.remove(sub_m, do_unlink=True)

            bm.to_mesh(cargo_mesh)
            bm.free()
            cargo_mesh.update()

        for o in list(imported):
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)

    elif os.path.isfile(empty_path) and not body_mesh:
        imported = _import_glb_objects(empty_path)
        meshes = [o for o in imported if o.type == "MESH" and o.data and len(o.data.vertices) > 0]
        if meshes:
            c_obj = meshes[0]
            mw = c_obj.matrix_world.copy()
            body_mesh = c_obj.data.copy()
            body_mesh.name = "TPL_MC_Body_Empty_Mesh"
            body_mesh.use_fake_user = True
            for v in body_mesh.vertices:
                p = mw @ v.co
                v.co.x = p.x * CART_SCALE
                v.co.y = p.y * CART_SCALE + CART_MESH_Y_SHIFT
                v.co.z = p.z * CART_SCALE + RAIL_HEAD_TOP_Z
            body_mesh.update()
        for o in list(imported):
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)

    return body_mesh, cargo_mesh


# ============================================================================
# 2. PROCEDURAL 3D NARROW-GAUGE RAILS & WOODEN SLEEPERS ON ANY CURVE
# ============================================================================

def _ensure_rail_geonodes_templates(half_gauge_m: float = RAIL_HALF_GAUGE_M) -> tuple:
    """
    Creates or updates the hidden template objects used by `GN_Minecart_Rails_On_Curve`:
      - `TPL_MC_Sleeper_Unit`: Weathered dark-oak cross-tie sleeper + 2 forged-iron tie-plates
      - `TPL_MC_Rail_IronWeb_Profile`: 2D profile curve for left & right rail base flange + web
      - `TPL_MC_Rail_BrassHead_Profile`: 2D profile curve for left & right polished running head
    """
    mat_wood = _get_or_create_mat("AF_MC_SleeperOak_Mat", (0.20, 0.13, 0.08), metallic=0.05, roughness=0.72)
    mat_iron = _get_or_create_mat("AF_MC_RailForgedIron_Mat", (0.24, 0.25, 0.28), metallic=0.86, roughness=0.36)
    mat_brass = _get_or_create_mat("AF_MC_RailTopBrassSteel_Mat", (0.62, 0.56, 0.44), metallic=0.92, roughness=0.24)

    tpl_col = ensure_collection("00_AF_ELF_TEMPLATES")

    def _hide_tpl(obj):
        if obj.name not in tpl_col.objects:
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            tpl_col.objects.link(obj)
        obj.hide_viewport = True
        obj.hide_render = True
        obj.hide_select = True

    sl_mesh_name = "Mesh_TPL_MC_Sleeper_Unit"
    sl_obj_name = "TPL_MC_Sleeper_Unit"
    sl_mesh = bpy.data.meshes.get(sl_mesh_name) or bpy.data.meshes.new(sl_mesh_name)
    sl_mesh.materials.clear()
    sl_mesh.materials.append(mat_wood)  # 0: oak sleeper
    sl_mesh.materials.append(mat_iron)  # 1: iron tie-plates

    bm = bmesh.new()
    sleeper_half_w = half_gauge_m + 0.16
    sleeper_half_l = 0.065
    z_sl_bot = -0.004
    z_sl_top = 0.013

    ret = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sleeper_half_w * 2.0, sleeper_half_l * 2.0, z_sl_top - z_sl_bot), verts=ret["verts"])
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.5 * (z_sl_bot + z_sl_top)), verts=ret["verts"])
    for v in ret["verts"]:
        for f in v.link_faces:
            f.material_index = 0

    for side_sgn in (-1.0, +1.0):
        cx = side_sgn * half_gauge_m
        ret_p = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(0.090, 0.110, 0.006), verts=ret_p["verts"])
        bmesh.ops.translate(bm, vec=(cx, 0.0, z_sl_top + 0.0025), verts=ret_p["verts"])
        for v in ret_p["verts"]:
            for f in v.link_faces:
                f.material_index = 1

    bm.normal_update()
    bm.to_mesh(sl_mesh)
    bm.free()
    sl_mesh.update()

    sl_obj = bpy.data.objects.get(sl_obj_name) or bpy.data.objects.new(sl_obj_name, sl_mesh)
    sl_obj.data = sl_mesh
    _hide_tpl(sl_obj)

    def _ensure_profile_curve_obj(obj_name: str, section_pts_rx_rz: list):
        crv_name = f"Curve_{obj_name}"
        cd = bpy.data.curves.get(crv_name) or bpy.data.curves.new(crv_name, "CURVE")
        cd.dimensions = "2D"
        cd.splines.clear()
        for side_sgn in (-1.0, +1.0):
            sp = cd.splines.new("POLY")
            sp.use_cyclic_u = True
            sp.points.add(len(section_pts_rx_rz) - 1)
            for idx, (rx, rz) in enumerate(section_pts_rx_rz):
                sp.points[idx].co = (rz, side_sgn * half_gauge_m + rx, 0.0, 1.0)
        obj = bpy.data.objects.get(obj_name) or bpy.data.objects.new(obj_name, cd)
        obj.data = cd
        _hide_tpl(obj)
        return obj

    iron_web_obj = _ensure_profile_curve_obj(
        "TPL_MC_Rail_IronWeb_Profile",
        [
            (-0.024, 0.012),
            (+0.024, 0.012),
            (+0.016, 0.024),
            (+0.017, 0.0325),
            (-0.017, 0.0325),
            (-0.016, 0.024),
        ],
    )
    brass_head_obj = _ensure_profile_curve_obj(
        "TPL_MC_Rail_BrassHead_Profile",
        [
            (-0.0185, 0.0320),
            (+0.0185, 0.0320),
            (+0.0185, RAIL_HEAD_TOP_Z),
            (-0.0185, RAIL_HEAD_TOP_Z),
        ],
    )
    return sl_obj, iron_web_obj, brass_head_obj, mat_wood, mat_iron, mat_brass


def _ensure_rail_geonodes_group(half_gauge_m: float = RAIL_HALF_GAUGE_M) -> bpy.types.NodeTree:
    """
    Creates or updates the live `GN_Minecart_Rails_On_Curve` Geometry Nodes group so that
    `RAIL_Track_<CurveName>` updates in real-time in BOTH Edit Mode (while dragging curve
    vertices/handles) and Object Mode via `Object Info (RELATIVE)`.
    """
    sl_obj, iron_web_obj, brass_head_obj, _, mat_iron, mat_brass = _ensure_rail_geonodes_templates(half_gauge_m)

    gn_name = "GN_Minecart_Rails_On_Curve"
    ng = bpy.data.node_groups.get(gn_name)
    if not ng:
        ng = bpy.data.node_groups.new(gn_name, "GeometryNodeTree")

    if len(ng.nodes) >= 18 and ng.nodes.get("RailCurveObjInfo"):
        return ng

    ng.interface.clear()
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="*1: Krivulja Pruge (Curve)", in_out="INPUT", socket_type="NodeSocketObject")
    s_spc = ng.interface.new_socket(name="*1: Razmak Pragova (m)", in_out="INPUT", socket_type="NodeSocketFloat")
    s_spc.default_value = 0.44
    s_spc.min_value = 0.20
    s_spc.max_value = 2.00
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    ng.nodes.clear()
    ng.links.clear()

    n_in = ng.nodes.new("NodeGroupInput")
    n_in.location = (-1200, 0)
    n_out = ng.nodes.new("NodeGroupOutput")
    n_out.location = (900, 0)

    n_crv_info = ng.nodes.new("GeometryNodeObjectInfo")
    n_crv_info.name = "RailCurveObjInfo"
    n_crv_info.transform_space = "RELATIVE"
    n_crv_info.location = (-960, 140)
    ng.links.new(n_in.outputs["*1: Krivulja Pruge (Curve)"], n_crv_info.inputs["Object"])

    n_dom = ng.nodes.new("GeometryNodeAttributeDomainSize")
    n_dom.component = "CURVE"
    n_dom.location = (-740, 280)
    ng.links.new(n_crv_info.outputs["Geometry"], n_dom.inputs["Geometry"])

    n_gt0 = ng.nodes.new("FunctionNodeCompare")
    n_gt0.data_type = "INT"
    n_gt0.operation = "GREATER_THAN"
    n_gt0.location = (-540, 280)
    ng.links.new(n_dom.outputs["Point Count"], n_gt0.inputs[0])

    n_sw_crv = ng.nodes.new("GeometryNodeSwitch")
    n_sw_crv.input_type = "GEOMETRY"
    n_sw_crv.location = (-340, 140)
    ng.links.new(n_gt0.outputs["Result"], n_sw_crv.inputs["Switch"])
    ng.links.new(n_in.outputs["Geometry"], n_sw_crv.inputs["False"])
    ng.links.new(n_crv_info.outputs["Geometry"], n_sw_crv.inputs["True"])

    n_res_rail = ng.nodes.new("GeometryNodeResampleCurve")
    if "Mode" in n_res_rail.inputs:
        n_res_rail.inputs["Mode"].default_value = "Length"
    n_res_rail.inputs["Length"].default_value = 0.22
    n_res_rail.location = (-120, 220)
    ng.links.new(n_sw_crv.outputs["Output"], n_res_rail.inputs["Curve"])

    n_norm = ng.nodes.new("GeometryNodeSetCurveNormal")
    n_norm.inputs["Mode"].default_value = "Free"
    n_norm.inputs["Normal"].default_value = (0.0, 0.0, 1.0)
    n_norm.location = (80, 220)
    ng.links.new(n_res_rail.outputs["Curve"], n_norm.inputs["Curve"])

    n_prof_iron = ng.nodes.new("GeometryNodeObjectInfo")
    n_prof_iron.transform_space = "ORIGINAL"
    n_prof_iron.inputs["Object"].default_value = iron_web_obj
    n_prof_iron.location = (80, 420)

    n_c2m_iron = ng.nodes.new("GeometryNodeCurveToMesh")
    n_c2m_iron.inputs["Fill Caps"].default_value = True
    n_c2m_iron.location = (300, 320)
    ng.links.new(n_norm.outputs["Curve"], n_c2m_iron.inputs["Curve"])
    ng.links.new(n_prof_iron.outputs["Geometry"], n_c2m_iron.inputs["Profile Curve"])

    n_mat_iron = ng.nodes.new("GeometryNodeSetMaterial")
    n_mat_iron.inputs["Material"].default_value = mat_iron
    n_mat_iron.location = (500, 320)
    ng.links.new(n_c2m_iron.outputs["Mesh"], n_mat_iron.inputs["Geometry"])

    n_prof_brass = ng.nodes.new("GeometryNodeObjectInfo")
    n_prof_brass.transform_space = "ORIGINAL"
    n_prof_brass.inputs["Object"].default_value = brass_head_obj
    n_prof_brass.location = (80, 40)

    n_c2m_brass = ng.nodes.new("GeometryNodeCurveToMesh")
    n_c2m_brass.inputs["Fill Caps"].default_value = True
    n_c2m_brass.location = (300, 100)
    ng.links.new(n_norm.outputs["Curve"], n_c2m_brass.inputs["Curve"])
    ng.links.new(n_prof_brass.outputs["Geometry"], n_c2m_brass.inputs["Profile Curve"])

    n_mat_brass = ng.nodes.new("GeometryNodeSetMaterial")
    n_mat_brass.inputs["Material"].default_value = mat_brass
    n_mat_brass.location = (500, 100)
    ng.links.new(n_c2m_brass.outputs["Mesh"], n_mat_brass.inputs["Geometry"])

    n_res_sl = ng.nodes.new("GeometryNodeResampleCurve")
    if "Mode" in n_res_sl.inputs:
        n_res_sl.inputs["Mode"].default_value = "Length"
    n_res_sl.location = (-120, -180)
    ng.links.new(n_sw_crv.outputs["Output"], n_res_sl.inputs["Curve"])
    ng.links.new(n_in.outputs["*1: Razmak Pragova (m)"], n_res_sl.inputs["Length"])

    n_tan = ng.nodes.new("GeometryNodeInputTangent")
    n_tan.location = (-120, -360)

    n_al1 = ng.nodes.new("FunctionNodeAlignRotationToVector")
    n_al1.axis = "Y"
    n_al1.pivot_axis = "AUTO"
    n_al1.location = (80, -340)
    ng.links.new(n_tan.outputs["Tangent"], n_al1.inputs["Vector"])

    n_al2 = ng.nodes.new("FunctionNodeAlignRotationToVector")
    n_al2.axis = "Z"
    n_al2.pivot_axis = "Y"
    n_al2.inputs["Vector"].default_value = (0.0, 0.0, 1.0)
    n_al2.location = (260, -340)
    ng.links.new(n_al1.outputs["Rotation"], n_al2.inputs["Rotation"])

    n_sl_info = ng.nodes.new("GeometryNodeObjectInfo")
    n_sl_info.transform_space = "ORIGINAL"
    n_sl_info.inputs["Object"].default_value = sl_obj
    n_sl_info.location = (260, -160)

    n_inst = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_inst.location = (460, -220)
    ng.links.new(n_res_sl.outputs["Curve"], n_inst.inputs["Points"])
    ng.links.new(n_sl_info.outputs["Geometry"], n_inst.inputs["Instance"])
    ng.links.new(n_al2.outputs["Rotation"], n_inst.inputs["Rotation"])

    n_real = ng.nodes.new("GeometryNodeRealizeInstances")
    n_real.location = (620, -220)
    ng.links.new(n_inst.outputs["Instances"], n_real.inputs["Geometry"])

    n_join = ng.nodes.new("GeometryNodeJoinGeometry")
    n_join.location = (740, 60)
    ng.links.new(n_mat_iron.outputs["Geometry"], n_join.inputs["Geometry"])
    ng.links.new(n_mat_brass.outputs["Geometry"], n_join.inputs["Geometry"])
    ng.links.new(n_real.outputs["Geometry"], n_join.inputs["Geometry"])
    ng.links.new(n_join.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


def sample_curve_world_points_and_tangents(curve_obj: bpy.types.Object, num_samples: int = 160) -> tuple:
    """
    Evaluates `curve_obj` directly via `mathutils.geometry.interpolate_bezier` (safe inside
    `frame_change_post` and headless renders without mutating datablocks or triggering depsgraph)
    into an ordered list of uniform arc-length world points (`u = 0.0 -> 1.0`),
    unit forward tangents, cumulative distances, and total length.
    """
    if not curve_obj or curve_obj.type != "CURVE":
        return [], [], [], 0.0

    cd = curve_obj.data
    if not cd or not cd.splines:
        return [], [], [], 0.0

    sp = cd.splines[0]
    is_cyclic = bool(sp.use_cyclic_u)
    mw = curve_obj.matrix_world

    from mathutils.geometry import interpolate_bezier

    pts_raw = []
    if sp.type == "BEZIER" and len(sp.bezier_points) >= 2:
        bps = sp.bezier_points
        n_bp = len(bps)
        seg_count = n_bp if is_cyclic else (n_bp - 1)
        res = max(6, min(24, int(cd.resolution_u or 12)))
        for i in range(seg_count):
            b0 = bps[i]
            b1 = bps[(i + 1) % n_bp]
            seg_pts = interpolate_bezier(b0.co, b0.handle_right, b1.handle_left, b1.co, res)
            if i > 0 and len(seg_pts) > 1:
                seg_pts = seg_pts[1:]
            for p_local in seg_pts:
                pts_raw.append(mw @ p_local)
    elif len(sp.points) >= 2:
        for pt in sp.points:
            pts_raw.append(mw @ Vector((pt.co.x, pt.co.y, pt.co.z)))
        if is_cyclic and (pts_raw[0] - pts_raw[-1]).length > 1e-4:
            pts_raw.append(pts_raw[0].copy())

    if len(pts_raw) < 2:
        return [], [], [], 0.0

    cum = [0.0]
    for i in range(1, len(pts_raw)):
        cum.append(cum[-1] + (pts_raw[i] - pts_raw[i - 1]).length)
    total_len = cum[-1]
    if total_len < 0.1:
        return [], [], [], total_len

    pts = []
    s_vals = []
    idx = 0
    for k in range(num_samples + 1):
        s_t = (total_len * k) / float(num_samples)
        while idx < len(cum) - 2 and cum[idx + 1] < s_t:
            idx += 1
        seg = max(1e-6, cum[idx + 1] - cum[idx])
        t = max(0.0, min(1.0, (s_t - cum[idx]) / seg))
        pts.append(pts_raw[idx].lerp(pts_raw[idx + 1], t))
        s_vals.append(s_t)

    tangents = []
    for k in range(len(pts)):
        if k == 0:
            v = pts[1] - pts[0]
        elif k == len(pts) - 1:
            v = pts[-1] - pts[-2]
        else:
            v = pts[k + 1] - pts[k - 1]
        tangents.append(v.normalized() if v.length > 1e-6 else Vector((0.0, -1.0, 0.0)))

    return pts, tangents, s_vals, total_len


def _set_modifier_socket(mod, ident: str, val):
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


def build_or_update_3d_rails_for_curve(
    curve_obj: bpy.types.Object,
    half_gauge_m: float = RAIL_HALF_GAUGE_M,
    sleeper_spacing_m: float = 0.44,
) -> bpy.types.Object:
    """
    Builds or updates a live 3D narrow-gauge railway track object (`RAIL_Track_<CurveName>`)
    driven directly by `curve_obj` via `GN_Minecart_Rails_On_Curve` (`Object Info (RELATIVE)`),
    so editing `curve_obj` in Edit Mode (moving/rotating control points) or Object Mode
    updates `RAIL_Track_<CurveName>` in real time!
    """
    if not curve_obj or curve_obj.type != "CURVE":
        return None

    # Keep the curve a pure 1D spline (`bevel_depth = 0.0`) so Object Info outputs Curve geometry
    # to Geometry Nodes and Edit Mode displays clean Bezier control points & handles!
    curve_obj.data.bevel_depth = 0.0
    curve_obj.data.extrude = 0.0

    # Ensure Proportional Editing is disabled so editing individual curve vertices in Edit Mode
    # never rotates or moves the entire curve!
    try:
        if bpy.context and bpy.context.scene and bpy.context.scene.tool_settings:
            ts = bpy.context.scene.tool_settings
            ts.use_proportional_edit = False
            ts.use_proportional_edit_objects = False
            ts.use_proportional_connected = False
            if ts.proportional_size > 5.0:
                ts.proportional_size = 1.5
    except Exception:
        pass

    rail_col = ensure_collection(MINECART_COLLECTION_NAME)
    track_name = f"RAIL_Track_{curve_obj.name}"
    mesh_name = f"Mesh_{track_name}"

    track_obj = bpy.data.objects.get(track_name)
    if track_obj and track_obj.type == "MESH":
        t_mesh = track_obj.data
    else:
        t_mesh = bpy.data.meshes.get(mesh_name) or bpy.data.meshes.new(mesh_name)
        track_obj = bpy.data.objects.new(track_name, t_mesh)
        rail_col.objects.link(track_obj)

    if track_obj.name not in rail_col.objects:
        try:
            rail_col.objects.link(track_obj)
        except Exception:
            pass

    track_obj.location = (0.0, 0.0, 0.0)
    track_obj.rotation_euler = (0.0, 0.0, 0.0)
    track_obj.scale = (1.0, 1.0, 1.0)

    _, _, _, mat_wood, mat_iron, mat_brass = _ensure_rail_geonodes_templates(half_gauge_m)
    t_mesh.materials.clear()
    t_mesh.materials.append(mat_wood)   # 0: oak sleepers
    t_mesh.materials.append(mat_iron)   # 1: rail web/base & tie plates
    t_mesh.materials.append(mat_brass)  # 2: polished rail running head

    # Clear base mesh vertices so ONLY the live Geometry Nodes output is rendered
    if len(t_mesh.vertices) > 0:
        bm = bmesh.new()
        bm.to_mesh(t_mesh)
        bm.free()
        t_mesh.update()

    ng = _ensure_rail_geonodes_group(half_gauge_m)
    mod = track_obj.modifiers.get("GN_Minecart_Rails")
    if not mod:
        mod = track_obj.modifiers.new(name="GN_Minecart_Rails", type="NODES")
    mod.node_group = ng
    mod.show_viewport = True
    mod.show_render = True
    mod.show_in_editmode = True

    for item in ng.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT":
            if "Krivulja" in item.name:
                _set_modifier_socket(mod, item.identifier, curve_obj)
            elif "Razmak" in item.name:
                _set_modifier_socket(mod, item.identifier, float(sleeper_spacing_m))

    track_obj.update_tag()
    curve_obj["af_mc_rail_track_obj"] = track_obj.name
    track_obj["af_mc_source_curve"] = curve_obj.name
    return track_obj


def set_curve_3d_rails_enabled(curve_obj: bpy.types.Object, enabled: bool = True):
    if not curve_obj or curve_obj.type != "CURVE":
        return None
    curve_obj["af_mc_rails_enabled"] = bool(enabled)
    track_name = curve_obj.get("af_mc_rail_track_obj", f"RAIL_Track_{curve_obj.name}")
    track_obj = bpy.data.objects.get(track_name)
    if enabled:
        track_obj = build_or_update_3d_rails_for_curve(curve_obj)
        if track_obj:
            track_obj.hide_viewport = False
            track_obj.hide_render = False
        return track_obj
    else:
        if track_obj:
            track_obj.hide_viewport = True
            track_obj.hide_render = True
        return None


# ============================================================================
# 3. ATTACH / SWAP / REMOVE MINECART ON ANY ELF (`CTRL_*`)
# ============================================================================

def get_elf_minecart_prop(ctrl_obj: bpy.types.Object) -> bpy.types.Object:
    """Returns the `Prop_Minecart_<CtrlName>` root object attached to `ctrl_obj`, if any."""
    ctrl_obj = find_character_controller(ctrl_obj)
    if not ctrl_obj:
        return None
    prop_name = ctrl_obj.get("af_mc_prop_root", f"Prop_Minecart_{ctrl_obj.name}")
    prop_obj = bpy.data.objects.get(prop_name)
    if prop_obj and prop_obj.parent == ctrl_obj:
        return prop_obj
    for ch in ctrl_obj.children:
        if ch.get("af_is_minecart_prop") or ch.name.startswith("Prop_Minecart_"):
            return ch
    return None


def attach_minecart_to_elf(
    context,
    ctrl_obj: bpy.types.Object,
    variant: str = "EMPTY",
    distance_m: float = None,
    build_rails_on_attached_curve: bool = True,
    switch_to_push_walk_action: bool = True,
) -> bpy.types.Object:
    """
    Attaches a 3D Minecart (`EMPTY` or `FULL`) to `ctrl_obj` (`CTRL_*`):
      - Parents `Prop_Minecart_<CtrlName>` to `ctrl_obj` at `location = (0.0, -distance_m, 0.0)`
        (`default 0.88 m`), where `-Y` is the character's forward direction.
      - Contains `MC_Body_<CtrlName>` (`SM_Minecart_01_Empty.glb`) and
        `MC_Cargo_<CtrlName>` (`SM_Basket_04_FullCargo_Ice` + blue ice from `SM_Minecart_02_Full_Loaded.glb`),
        toggling cargo visibility based on `variant` (`"EMPTY"` vs `"FULL"`).
      - Automatically sets the Elf's locomotion animation to `AF_34_Walk_Push_Minecart`
        so the Elf leans forward and grips the rear push-handle bar with both hands!
      - If the Elf is attached to a locomotion curve, builds 3D narrow-gauge rails on that curve
        and steers the minecart along the curve ahead of the Elf!
    """
    if context is None:
        context = bpy.context
    ctrl_obj = find_character_controller(ctrl_obj) or get_active_character_controller(context)
    if not ctrl_obj:
        return None

    variant = "FULL" if str(variant).upper().startswith("FULL") else "EMPTY"
    if distance_m is None:
        distance_m = float(ctrl_obj.get("af_mc_distance_m", 0.88))
    distance_m = max(0.55, min(1.60, float(distance_m)))

    body_mesh, cargo_mesh = _ensure_minecart_template_meshes()
    if not body_mesh:
        raise RuntimeError("Nije moguće učitati 3D model SM_Minecart_01_Empty.glb iz assets/models/glb/minecart/")

    # Put minecart objects in the same collection as `ctrl_obj`
    target_col = ctrl_obj.users_collection[0] if ctrl_obj.users_collection else ensure_collection(MINECART_COLLECTION_NAME)

    prop_root = get_elf_minecart_prop(ctrl_obj)
    if not prop_root:
        prop_name = f"Prop_Minecart_{ctrl_obj.name}"
        prop_root = bpy.data.objects.get(prop_name)
        if prop_root:
            bpy.data.objects.remove(prop_root, do_unlink=True)
        prop_root = bpy.data.objects.new(prop_name, None)
        prop_root.empty_display_type = "ARROWS"
        prop_root.empty_display_size = 0.25
        target_col.objects.link(prop_root)
        prop_root.parent = ctrl_obj

    prop_root["af_is_minecart_prop"] = True
    prop_root["af_is_editable_prop"] = True
    prop_root["af_mc_owner_ctrl"] = ctrl_obj.name
    prop_root.location = (0.0, -distance_m, 0.0)
    prop_root.rotation_mode = "XYZ"
    prop_root.rotation_euler = (0.0, 0.0, 0.0)

    # Ensure Body Mesh child
    body_name = f"MC_Body_{ctrl_obj.name}"
    body_obj = bpy.data.objects.get(body_name)
    if not body_obj:
        body_obj = bpy.data.objects.new(body_name, body_mesh)
        target_col.objects.link(body_obj)
    else:
        body_obj.data = body_mesh
    body_obj.parent = prop_root
    body_obj.location = (0.0, 0.0, 0.0)
    body_obj.rotation_euler = (0.0, 0.0, 0.0)
    body_obj["af_is_editable_prop"] = True

    # Ensure Cargo Mesh child (`SM_Basket_04_FullCargo_Ice` + blue ice)
    cargo_name = f"MC_Cargo_{ctrl_obj.name}"
    cargo_obj = bpy.data.objects.get(cargo_name)
    if cargo_mesh:
        if not cargo_obj:
            cargo_obj = bpy.data.objects.new(cargo_name, cargo_mesh)
            target_col.objects.link(cargo_obj)
        else:
            cargo_obj.data = cargo_mesh
        cargo_obj.parent = prop_root
        cargo_obj.location = (0.0, 0.0, 0.0)
        cargo_obj.rotation_euler = (0.0, 0.0, 0.0)
        cargo_obj["af_is_editable_prop"] = True
        show_cargo = (variant == "FULL")
        cargo_obj.hide_viewport = not show_cargo
        cargo_obj.hide_render = not show_cargo

    ctrl_obj["af_mc_attached"] = True
    ctrl_obj["af_mc_variant"] = variant
    ctrl_obj["af_mc_show_cargo"] = (variant == "FULL")
    ctrl_obj["af_mc_distance_m"] = float(distance_m)
    ctrl_obj["af_mc_prop_root"] = prop_root.name
    ctrl_obj["af_mc_body_obj"] = body_obj.name
    ctrl_obj["af_mc_cargo_obj"] = cargo_obj.name if cargo_obj else ""

    # Assign `AF_34_Walk_Push_Minecart` if available
    if switch_to_push_walk_action:
        push_act = bpy.data.actions.get(PUSH_WALK_ACTION_NAME)
        if not push_act:
            from .database import ensure_library_loaded
            ensure_library_loaded(load_templates=False, load_actions=True)
            push_act = bpy.data.actions.get(PUSH_WALK_ACTION_NAME)
        if push_act:
            clear_nla_sequence(ctrl_obj)
            ctrl_obj["af_anim_name"] = PUSH_WALK_ACTION_NAME
            apply_stored_settings_to_character(context, ctrl_obj)

    # Re-sync curve locomotion and build 3D rails if attached to a curve
    crv_name = ctrl_obj.get("af_attached_curve", "")
    crv_obj = bpy.data.objects.get(crv_name) if crv_name else None
    if crv_obj and crv_obj.type == "CURVE":
        attach_controller_to_locomotion_curve(
            context,
            ctrl_obj=ctrl_obj,
            curve_obj=crv_obj,
            speed_mps=None,
            loop_path=bool(ctrl_obj.get("af_loop_anim", True)),
            flip_forward=bool(ctrl_obj.get("af_flip_curve_dir", False)),
            start_pct=float(ctrl_obj.get("af_curve_start_pct", 0.0)),
        )
        if build_rails_on_attached_curve:
            set_curve_3d_rails_enabled(crv_obj, enabled=True)
        update_minecart_curve_steering_for_controller(ctrl_obj, scene=context.scene)

    return prop_root


def set_elf_minecart_variant(ctrl_obj: bpy.types.Object, variant: str = "FULL") -> bool:
    """Switches an Elf's attached minecart between `EMPTY` and `FULL` (or attaches it if not yet attached)."""
    ctrl_obj = find_character_controller(ctrl_obj)
    if not ctrl_obj:
        return False
    prop_root = get_elf_minecart_prop(ctrl_obj)
    if not prop_root:
        attach_minecart_to_elf(bpy.context, ctrl_obj, variant=variant)
        return True

    variant = "FULL" if str(variant).upper().startswith("FULL") else "EMPTY"
    show_cargo = (variant == "FULL")
    ctrl_obj["af_mc_variant"] = variant
    ctrl_obj["af_mc_show_cargo"] = show_cargo

    cargo_obj = bpy.data.objects.get(ctrl_obj.get("af_mc_cargo_obj", f"MC_Cargo_{ctrl_obj.name}"))
    if cargo_obj:
        cargo_obj.hide_viewport = not show_cargo
        cargo_obj.hide_render = not show_cargo
    return True


def remove_minecart_from_elf(ctrl_obj: bpy.types.Object) -> bool:
    """Removes the attached Minecart prop from `ctrl_obj`."""
    ctrl_obj = find_character_controller(ctrl_obj)
    if not ctrl_obj:
        return False
    prop_root = get_elf_minecart_prop(ctrl_obj)
    if prop_root:
        for ch in list(prop_root.children):
            bpy.data.objects.remove(ch, do_unlink=True)
        bpy.data.objects.remove(prop_root, do_unlink=True)
    ctrl_obj["af_mc_attached"] = False
    ctrl_obj["af_mc_prop_root"] = ""
    return True


# ============================================================================
# 4. CURVE-TANGENT LOOK-AHEAD STEERING HANDLER (`af_minecart_pusher_frame_handler`)
# ============================================================================

def update_minecart_curve_steering_for_controller(ctrl_obj: bpy.types.Object, scene=None):
    """
    Evaluates the locomotion curve ahead of `ctrl_obj` (`~distance_m` ahead along the curve)
    and smoothly steers `Prop_Minecart_<CtrlName>`'s local X offset, Z yaw, and X pitch
    so the minecart's 4 flanged wheels track the curved 3D rails ahead while its rear
    push-handle bar stays inside the Elf's hands!
    """
    if not ctrl_obj or not ctrl_obj.get("af_mc_attached", False):
        return
    prop_root = get_elf_minecart_prop(ctrl_obj)
    if not prop_root:
        return

    dist_m = float(ctrl_obj.get("af_mc_distance_m", 0.88))
    crv_name = ctrl_obj.get("af_attached_curve", "")
    crv_obj = bpy.data.objects.get(crv_name) if crv_name else None

    if not crv_obj or crv_obj.type != "CURVE":
        prop_root.location = (0.0, -dist_m, 0.0)
        prop_root.rotation_euler = (0.0, 0.0, 0.0)
        return

    con = next((c for c in ctrl_obj.constraints if c.type == "FOLLOW_PATH" and c.target == crv_obj), None)
    if not con:
        prop_root.location = (0.0, -dist_m, 0.0)
        prop_root.rotation_euler = (0.0, 0.0, 0.0)
        return

    pts, tangents, s_vals, total_len = sample_curve_world_points_and_tangents(crv_obj, num_samples=160)
    if len(pts) < 2 or total_len < 0.2:
        prop_root.location = (0.0, -dist_m, 0.0)
        prop_root.rotation_euler = (0.0, 0.0, 0.0)
        return

    flip = bool(ctrl_obj.get("af_flip_curve_dir", False))
    dir_sgn = -1.0 if flip else 1.0
    u_elf = float(con.offset_factor) % 1.0
    s_elf = u_elf * total_len

    # Look ahead along the curve to the rear push-bar (0.556 m ahead) and front axle (1.42 m ahead)
    is_cyclic = bool(crv_obj.data.splines and crv_obj.data.splines[0].use_cyclic_u)
    s_bar = s_elf + dir_sgn * max(0.35, dist_m - 0.324)
    s_front = s_elf + dir_sgn * (dist_m + 0.45)

    def _interp_curve_pt(s_query: float) -> Vector:
        if is_cyclic:
            s_q = s_query % total_len
        else:
            s_q = max(0.0, min(total_len, s_query))
        f_idx = (s_q / total_len) * (len(pts) - 1)
        i0 = max(0, min(len(pts) - 2, int(f_idx)))
        t = f_idx - i0
        return pts[i0].lerp(pts[i0 + 1], t)

    p_elf = _interp_curve_pt(s_elf)
    p_bar = _interp_curve_pt(s_bar)
    p_front = _interp_curve_pt(s_front)

    # Tangent at Elf position
    t_elf = (_interp_curve_pt(s_elf + dir_sgn * 0.08) - _interp_curve_pt(s_elf - dir_sgn * 0.08))
    if t_elf.length < 1e-5:
        t_elf = Vector((0.0, -1.0, 0.0))
    else:
        t_elf.normalize()

    # Chord vector of the minecart from rear push-bar to front axle
    chord_cart = (p_front - p_bar)
    if chord_cart.length < 1e-5:
        chord_cart = t_elf.copy()
    else:
        chord_cart.normalize()

    # Compute relative yaw angle (in XY plane) between Elf forward tangent `t_elf` and minecart chord `chord_cart`
    ang_elf = math.atan2(t_elf.y, t_elf.x)
    ang_cart = math.atan2(chord_cart.y, chord_cart.x)
    delta_yaw = (ang_cart - ang_elf + math.pi) % (2.0 * math.pi) - math.pi
    delta_yaw = max(math.radians(-32.0), min(math.radians(32.0), delta_yaw))

    # Relative pitch angle
    pitch_elf = math.asin(max(-0.99, min(0.99, t_elf.z)))
    pitch_cart = math.asin(max(-0.99, min(0.99, chord_cart.z)))
    delta_pitch = max(math.radians(-20.0), min(math.radians(20.0), pitch_cart - pitch_elf))

    # Pivot the minecart around the rear push-bar `(0, +0.324, 0)` in prop space so the push-bar
    # stays locked inside the Elf's hands `(0, -(dist_m - 0.324), 1.03)` while the front of the
    # minecart swings by `delta_yaw` onto the curved rails ahead!
    bar_offset_y = 0.324
    pivot_y_in_ctrl = -(dist_m - bar_offset_y)
    loc_x = bar_offset_y * math.sin(delta_yaw)
    loc_y = pivot_y_in_ctrl - bar_offset_y * math.cos(delta_yaw)

    prop_root.location = (loc_x, loc_y, 0.0)
    prop_root.rotation_euler = (-delta_pitch, 0.0, delta_yaw)


def update_all_scene_minecarts(scene=None):
    """Updates curve look-ahead steering for all Elves with attached minecarts in `scene`."""
    if scene is None:
        scene = bpy.context.scene
    if not scene:
        return
    for o in scene.objects:
        if o.get("af_is_char_controller") and o.get("af_mc_attached", False):
            update_minecart_curve_steering_for_controller(o, scene=scene)


@persistent
def af_minecart_pusher_frame_handler(scene, depsgraph=None):
    global _MINECART_HANDLER_GUARD
    if _MINECART_HANDLER_GUARD:
        return
    _MINECART_HANDLER_GUARD = True
    try:
        for o in scene.objects:
            if o.get("af_is_char_controller") and o.get("af_mc_attached", False):
                update_minecart_curve_steering_for_controller(o, scene=scene)
    except Exception:
        pass
    finally:
        _MINECART_HANDLER_GUARD = False


def register_minecart_pusher_handlers():
    for h_list in (bpy.app.handlers.frame_change_post, bpy.app.handlers.depsgraph_update_post):
        for h in list(h_list):
            if getattr(h, "__name__", "") == "af_minecart_pusher_frame_handler":
                h_list.remove(h)
    bpy.app.handlers.frame_change_post.append(af_minecart_pusher_frame_handler)


def unregister_minecart_pusher_handlers():
    for h_list in (bpy.app.handlers.frame_change_post, bpy.app.handlers.depsgraph_update_post):
        for h in list(h_list):
            if getattr(h, "__name__", "") == "af_minecart_pusher_frame_handler":
                h_list.remove(h)


# ============================================================================
# 5. ONE-CLICK DEMO SPAWNER (`spawn_elf_pushing_minecart_on_rail_curve`)
# ============================================================================

def spawn_elf_pushing_minecart_on_rail_curve(
    context=None,
    elf_id: str = "ELF06",
    variant: str = "FULL",
    curve_obj: bpy.types.Object = None,
    curve_points: list = None,
    curve_name: str = "Elf_Minecart_Rail_Path_01",
    start_pct: float = 15.0,
    distance_m: float = 0.88,
) -> tuple:
    """
    One-click helper that:
      1. Creates or reuses a 3-point Bezier railway curve (`curve_obj`) and generates
         3D Narrow-Gauge Rails & Wooden Sleepers (`RAIL_Track_<CurveName>`),
      2. Spawns an Elf (`elf_id`) with `AF_34_Walk_Push_Minecart`,
      3. Attaches the 3D Minecart (`EMPTY` or `FULL`),
      4. Attaches the Elf + Minecart to the rail curve at `start_pct` with zero foot slip!
    """
    if context is None:
        context = bpy.context

    from .database import ensure_library_loaded
    ensure_library_loaded(load_templates=True, load_actions=True)

    if curve_obj is None:
        curve_obj = bpy.data.objects.get(curve_name)
    if curve_obj is None:
        if not curve_points:
            curve_points = [
                (-6.2, -3.4, 0.0),
                (0.0, -1.6, 0.0),
                (6.2, -3.4, 0.0),
            ]
        curve_obj = create_walk_curve_from_points(
            name=curve_name,
            points=curve_points,
            cyclic=False,
            bevel_depth=0.008,
        )

    track_obj = set_curve_3d_rails_enabled(curve_obj, enabled=True)

    ctrl = spawn_elf_actor(
        context,
        elf_id=elf_id,
        initial_action_name=PUSH_WALK_ACTION_NAME,
    )
    ctrl["af_curve_start_pct"] = float(start_pct)
    ctrl["af_loop_anim"] = True

    prop_root = attach_minecart_to_elf(
        context,
        ctrl_obj=ctrl,
        variant=variant,
        distance_m=distance_m,
        build_rails_on_attached_curve=False,
        switch_to_push_walk_action=True,
    )

    attach_controller_to_locomotion_curve(
        context,
        ctrl_obj=ctrl,
        curve_obj=curve_obj,
        speed_mps=None,
        loop_path=True,
        flip_forward=False,
        start_pct=float(start_pct),
    )
    update_minecart_curve_steering_for_controller(ctrl, scene=context.scene)
    return ctrl, prop_root, curve_obj, track_obj
