# -*- coding: utf-8 -*-
r"""
Underground Aerial Ropeway, Ski-Lift Gondola & Dynamic Catenary Sag Studio
(`elf_director.ropeway_gondolas`)
==========================================================================
Provides a complete, mathematically rigorous, and ultra-optimized aerial
cableway / ski-gondola controller system for `Advent Lift 2026`:

  1. Interactive Pylon Null / Empty Points (`GIZMO_RW_<sys>_Null_01..N`):
     - Each Null point defines the exact 3D coordinate where a pylon tower's
       pulley sheaves (`koloture`) touch and support the continuous haul rope.
     - Users can freely move Null points in the 3D Viewport (`G`), insert new
       Null points (`+ Dodaj Null Točku Stupa`), or remove existing ones
       (`- Ukloni Null Točku Stupa`), and the entire closed-loop ropeway,
       pulley alignment, catenary sag, and gondolas update dynamically in
       real time.

  2. Exact Mathematical Dynamic Catenary Sag & Moving Gondola Load Sink:
     - Closed-loop continuous circulation (`Outgoing Line` from the right-hand
       glacier wall toward the left/distant underground city + `180° Turnaround
       Bullwheel` + `Return Line` + `180° Drive Bullwheel`).
     - Every span $[S_i, S_{i+1}]$ of length $L_i = \|S_{i+1} - S_i\|$ dynamically
       evaluates:
         a) Hyperbolic Catenary Self-Weight Sag:
            $$\Delta Z_{\text{cat}}(u) = -d_{\text{base}} \left(\frac{L_i}{L_{\text{ref}}}\right)^2 \cos\alpha_i \, \frac{\cosh(\kappa) - \cosh(\kappa(2u - 1))}{\cosh(\kappa) - 1}$$
         b) Dynamic Point-Load Green's Function Deflection from Moving Gondolas:
            $$\Delta Z_{\text{load}}(u, t) = -d_{\text{load}} \left(\frac{L_i}{L_{\text{ref}}}\right) \cos\alpha_i \sum_{k \in \text{span } i} w_k \, g_{\text{smooth}}\big(u, u_k(t)\big)$$
            where $g_{\text{smooth}}(u, u_k)$ is the $C^\infty$ flexural Green's
            kernel pinned at the sheaves ($g(0, u_k) = g(1, u_k) = 0$) and
            peaking right under each gondola's grip clamp ($u = u_k(t)$).
     - The cable spline includes an exact vertex at each gondola's instantaneous
       $u_k(t)$, guaranteeing 0.000 mm gap between the sagging cable and every
       gondola's overhead grip clamp across all span lengths and animations!

  3. Pulley / Sheave & Pylon Tower Controls (`Kontroler za Koloture`):
     - Automatic angle-bisector yaw alignment and cable-slope pitch alignment
       of pulley roller batteries at every Null point.
     - Physically synchronized rotation ($\theta(t) = s(t) / R$) of grooved
       brass sheave rollers and terminal $180^\circ$ turnaround bullwheels.
     - Configurable support structure (`PYLON_TOWER`, `CEILING_HANGER`, or
       `PULLEY_ONLY`), loop gauge width, pulley scale, and roller count.

  4. Two Low-Poly Gondola Variations + Individual Gondola Content & Elf Rider:
     - `GONDOLA_CARGO` (`1. Teretna Gondola s Kristalima i Ovjesnom Rukom`):
       Loaded with glowing cyan-blue glacier ice crystals (or modular crates/barrels).
     - `GONDOLA_PASSENGER` (`2. Putnička Gondola za Vilenjaka s Ovjesnom Rukom`):
       Open-sided ski-lift passenger carriage capable of carrying a rigged,
       animated Elf (`ELF06..ELF28`) or modular cargo packages.
     - True hardware mesh instancing (all gondolas of the same variation share
       a single optimized low-poly `bpy.types.Mesh` datablock) for ultra-fast
       Cycles / RTX 4090 OptiX rendering even with 100+ gondolas across the cavern.
"""

import math
import os
import bmesh
import bpy
from bpy.app.handlers import persistent
from mathutils import Euler, Matrix, Vector

from .constants import PACKAGE_DIR, RIGGED_ELF_ROSTER, STATE, ensure_collection, get_assets_glb_dir
from .nla_sequencer import rebuild_nla_sequence_from_specs
from .rig_actors import (
    get_character_armature_from_ctrl,
    set_actor_accessories,
    spawn_elf_actor,
)

PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)
ROPEWAY_MASTER_COLLECTION = "07_ZICARE_I_GONDOLE_SUSTAVI"
ROPEWAY_COLLECTION_NAME = ROPEWAY_MASTER_COLLECTION
ROPEWAY_GLB_DIR = get_assets_glb_dir("ropeway_gondolas")
ROPEWAY_OPT_GLB_DIR = (
    os.path.join(PROJECT_ROOT, "assets", "models", "glb_optimized")
    if os.path.isdir(os.path.join(PROJECT_ROOT, "assets", "models", "glb_optimized"))
    else ROPEWAY_GLB_DIR
)
CLIFF_GLB_DIR = get_assets_glb_dir("cliff_baskets")

GONDOLA_VARIATIONS = (
    (
        "GONDOLA_CARGO",
        "1. Teretna Gondola (Prijevoz Kristala Leda i Tereta)",
        "SM_Gondola_01_Cargo_LowPoly.glb",
        "SM_Ropeway_V2_02_Cargo_Basket_Wide_Raw.fbx",
        (1.60, 1.60, 2.45),
    ),
    (
        "GONDOLA_PASSENGER",
        "2. Putnička Gondola (Kabina za Vilenjaka / Putnička)",
        "SM_Gondola_02_Passenger_LowPoly.glb",
        "SM_Ropeway_V2_03_Passenger_Cabin_Wide_Raw.fbx",
        (1.74, 1.74, 2.91),
    ),
)

GONDOLA_CARGO_CONTENT_TYPES = (
    ("ICE_CRYSTALS", "Plavi Kristali Leda (Iz Ledenog Zida)", "SM_Cargo_A_BlueIce_Heap.glb"),
    ("CRATE_TOOLS", "Sanduk s Rudarskim Alatom i Užetom", "SM_Cargo_B_ToolCrate_Tools.glb"),
    ("BARREL_LANTERN", "Okovana Bačva i Mjedeni Fenjer", "SM_Cargo_C_Barrel_Lantern.glb"),
    ("NONE", "Bez Dodatnog Tereta (Samo Košara / Putnička)", ""),
)

ROPEWAY_DISTRIBUTION_MODES = (
    (
        "MIXED_75_CARGO_25_ELF",
        "Miješano: Uglavnom Teretne s Kristalima + Tu i Tamo Vilenjak (75% / 25%)",
        "3 teretne gondole s plavim kristalima leda pa 1 putnička gondola s vilenjakom",
    ),
    (
        "ALL_CARGO",
        "Sve Teretne Gondole (100% Prijevoz Kristala Leda)",
        "Sve gondole na žičari su teretne i prevoze kristale leda prema gradu",
    ),
    (
        "ALTERNATING",
        "Naizmjenično (50% Teretna / 50% Putnička)",
        "Svaka druga gondola je putnička, a svaka druga teretna",
    ),
    (
        "ALL_PASSENGER",
        "Sve Putničke Gondole",
        "Sve gondole koriste putničku kabinu",
    ),
    (
        "CUSTOM",
        "Ručni Odabir (Pojedinačna Kontrola Svake Gondole)",
        "Zadržava ručne postavke pojedinih gondola",
    ),
)

TOWER_SUPPORT_MODES = (
    (
        "PYLON_TOWER",
        "Potporni Stup Prema Dolje (Dinamička Visina od Null Točke Prema Dolje)",
        "Gradi rešetkasti drveno-željezni stup žičare od Null točke prema dolje za zadanu visinu",
    ),
    (
        "CLIFF_WALL_BRACKET",
        "Zidna Konzola u Stijenu / Ledeni Zid (Bez Vertikalnog Stupa)",
        "Gradi bočnu konzolu usidrenu u stijenu/ledeni zid bez stupa prema tlu",
    ),
    (
        "CEILING_HANGER",
        "Stropni Ovjes Prema Gore (Konzola u Strop Špilje Iznad Kolotura)",
        "Gradi čelično-drveni ovjesni nosač prema stropu špilje iznad kolotura",
    ),
    (
        "PULLEY_ONLY",
        "Samo Glava Stupa i Koloture (Bez Vertikalnog Stupa)",
        "Prikazuje samo poprečnu gredu s koloturama i okretnim kotačem",
    ),
)

_RW_EVAL_GUARD = False
_NULL_POS_CACHE = {}


def show_viewport_move_gizmo_arrows(enabled: bool = True):
    """Enables 3D Viewport Move gizmo arrows so the user can drag Null points directly."""
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
    except Exception:
        pass


# ============================================================================
# 1. SHARED MATERIALS & ULTRA-LOW-POLY INSTANCED MESH BUILDERS
# ============================================================================

def _get_or_create_rw_material(
    name: str,
    base_color: tuple,
    metallic: float = 0.0,
    roughness: float = 0.5,
    emission_color: tuple = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
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


def _ensure_rw_palette() -> dict:
    return {
        "wood": (
            bpy.data.materials.get("MAT_S3_Beechwood_Sleeper_And_Timber")
            or _get_or_create_rw_material("AF_RW_OakTimber_Mat", (0.19, 0.11, 0.06), metallic=0.0, roughness=0.76)
        ),
        "wicker": _get_or_create_rw_material("AF_RW_Wicker_Mat", (0.14, 0.08, 0.04), metallic=0.0, roughness=0.84),
        "brass": (
            bpy.data.materials.get("MAT_S3_Aged_Brass_And_Steam_Pipes")
            or _get_or_create_rw_material("AF_RW_AgedBrass_Mat", (0.72, 0.53, 0.22), metallic=0.88, roughness=0.32)
        ),
        "iron": (
            bpy.data.materials.get("MAT_S3_Wrought_Iron_Oiled")
            or _get_or_create_rw_material("AF_RW_ForgedIron_Mat", (0.13, 0.14, 0.16), metallic=0.86, roughness=0.44)
        ),
        "cable": _get_or_create_rw_material("AF_RW_SteelCable_Mat", (0.16, 0.17, 0.20), metallic=0.90, roughness=0.38),
        "ice": (
            bpy.data.materials.get("MAT_S3_Ice_Stalactite_SSS")
            or _get_or_create_rw_material(
                "AF_RW_BlueIceCrystal_Mat",
                (0.20, 0.72, 0.98),
                metallic=0.05,
                roughness=0.14,
                emission_color=(0.18, 0.68, 1.0),
                emission_strength=2.2,
            )
        ),
        "lantern": _get_or_create_rw_material(
            "AF_RW_Lantern2700K_Mat",
            (1.0, 0.80, 0.38),
            metallic=0.0,
            roughness=0.15,
            emission_color=(1.0, 0.76, 0.30),
            emission_strength=10.0,
        ),
        "gizmo_null": _get_or_create_rw_material(
            "AF_RW_GizmoNull_Mat",
            (1.0, 0.45, 0.05),
            metallic=0.1,
            roughness=0.2,
            emission_color=(1.0, 0.42, 0.04),
            emission_strength=4.0,
        ),
    }


def _build_null_point_gizmo_mesh(
    name: str = "TPL_RW_Null_Gizmo_Mesh",
    radius: float = 2.60,
    force_rebuild: bool = False,
) -> bpy.types.Mesh:
    """Builds a large, high-visibility 3D double-ring + overhead diamond beacon gizmo mesh for Pylon Null points."""
    mesh = bpy.data.meshes.get(name)
    if mesh and len(mesh.vertices) > 0 and not force_rebuild:
        return mesh
    if not mesh:
        mesh = bpy.data.meshes.new(name)

    pal = _ensure_rw_palette()
    mesh.materials.clear()
    mesh.materials.append(pal["gizmo_null"])

    bm = bmesh.new()
    n_seg = 24
    tube = 0.22
    # Outer horizontal control ring around the pylon head (radius 2.60 m -> 5.2 m diameter)
    for r_ring, z_ring in ((radius, 0.0), (radius * 0.62, 1.35)):
        for i in range(n_seg):
            a0 = (2.0 * math.pi * i) / n_seg
            a1 = (2.0 * math.pi * (i + 1)) / n_seg
            p0 = Vector((math.cos(a0) * r_ring, math.sin(a0) * r_ring, z_ring))
            p1 = Vector((math.cos(a1) * r_ring, math.sin(a1) * r_ring, z_ring))
            dv = p1 - p0
            ret = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(tube, tube, dv.length * 1.06), verts=ret["verts"])
            rot = dv.normalized().to_track_quat("Z", "X").to_matrix().to_3x3()
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot, verts=ret["verts"])
            bmesh.ops.translate(bm, vec=0.5 * (p0 + p1), verts=ret["verts"])

    # 3D axis crossbars + vertical beacon mast above the pylon
    for scale_vec, z_off in (
        ((radius * 2.15, tube * 0.9, tube * 0.9), 0.0),
        ((tube * 0.9, radius * 2.15, tube * 0.9), 0.0),
        ((tube * 0.95, tube * 0.95, 2.80), 1.40),
    ):
        ret = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=scale_vec, verts=ret["verts"])
        if z_off != 0.0:
            bmesh.ops.translate(bm, vec=(0.0, 0.0, z_off), verts=ret["verts"])

    # Overhead octahedral diamond handle at Z = +2.85 m so it is easily clickable above the pylon
    ret_d = bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.65, radius2=0.02, depth=0.85)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 3.15), verts=ret_d["verts"])
    ret_d2 = bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.02, radius2=0.65, depth=0.85)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 2.30), verts=ret_d2["verts"])

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.use_fake_user = True
    return mesh


def _build_procedural_lowpoly_gondola_mesh(variant_id: str, ultra_low_poly: bool = False) -> bpy.types.Mesh:
    """
    Builds a crisp, ultra-optimized low-poly 3D Gondola mesh (`~240 - 480 faces`)
    with its origin (pivot `(0, 0, 0)`) at the exact top-center Cable Grip Clamp (`Z = 0.00 m`)
    and the basket hanging below (`Z = -2.65 .. 0.00 m`).
    Used both as the Ultra-Low-Poly LOD proxy and as instant fallback if `.glb` is still compiling.
    """
    suffix = "LOD1" if ultra_low_poly else "Proc"
    mesh_name = f"TPL_RW_Mesh_{variant_id}_{suffix}"
    existing = bpy.data.meshes.get(mesh_name)
    if existing and len(existing.vertices) > 0:
        return existing
    mesh = existing or bpy.data.meshes.new(mesh_name)
    mesh.materials.clear()

    pal = _ensure_rw_palette()
    # Material slots: 0=wicker, 1=wood, 2=brass, 3=iron, 4=ice, 5=lantern
    for k in ("wicker", "wood", "brass", "iron", "ice", "lantern"):
        mesh.materials.append(pal[k])

    bm = bmesh.new()

    def _box(x0, x1, y0, y1, z0, z1, mat_idx=1):
        ret = bmesh.ops.create_cube(bm, size=1.0)
        verts = ret["verts"]
        bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=verts)
        bmesh.ops.translate(bm, vec=(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)), verts=verts)
        for v in verts:
            for f in v.link_faces:
                f.material_index = mat_idx

    def _strut(p0, p1, rx=0.045, ry=0.045, mat_idx=3):
        v0, v1 = Vector(p0), Vector(p1)
        dv = v1 - v0
        if dv.length < 1e-4:
            return
        ret = bmesh.ops.create_cube(bm, size=1.0)
        verts = ret["verts"]
        bmesh.ops.scale(bm, vec=(rx * 2.0, ry * 2.0, dv.length), verts=verts)
        rot = dv.normalized().to_track_quat("Z", "X").to_matrix().to_3x3()
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot, verts=verts)
        bmesh.ops.translate(bm, vec=0.5 * (v0 + v1), verts=verts)
        for v in verts:
            for f in v.link_faces:
                f.material_index = mat_idx

    # 1. TOP CABLE GRIP CLAMP & TWIN GUIDE ROLLERS AT ORIGIN Z = 0.00 m
    # Cable runs along local Y axis through (0, y, 0)
    _box(-0.08, 0.08, -0.22, 0.22, -0.10, 0.07, mat_idx=3)  # Forged-iron grip housing
    _box(-0.10, 0.10, -0.09, 0.09, -0.18, -0.04, mat_idx=2)  # Brass spring clamp block
    for y_rol in (-0.16, 0.16):
        ret_r = bmesh.ops.create_cone(bm, cap_ends=True, segments=8 if ultra_low_poly else 12, radius1=0.075, radius2=0.075, depth=0.065)
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((0.0, math.pi * 0.5, 0.0)).to_matrix(), verts=ret_r["verts"])
        bmesh.ops.translate(bm, vec=(0.0, y_rol, 0.01), verts=ret_r["verts"])
        for v in ret_r["verts"]:
            for f in v.link_faces:
                f.material_index = 2

    if variant_id == "GONDOLA_CARGO":
        # 2A. CARGO GONDOLA: Inverted U / C-arch overhead hanger arm spanning X = -0.82 .. +0.82 down to rim Z = -1.35 m
        arch_pts_left = [
            (0.0, 0.0, -0.14),
            (-0.34, 0.0, -0.24),
            (-0.64, 0.0, -0.52),
            (-0.80, 0.0, -0.92),
            (-0.82, 0.0, -1.40),
        ]
        arch_pts_right = [(-x, y, z) for (x, y, z) in arch_pts_left]
        for side_pts in (arch_pts_left, arch_pts_right):
            for i in range(len(side_pts) - 1):
                _strut(side_pts[i], side_pts[i + 1], rx=0.048, ry=0.055, mat_idx=3 if i % 2 == 0 else 2)

        # Octagonal / Chamfered Cargo Basket Body (`Z = -2.52 .. -1.35 m`, radius `0.82 m`)
        n_sides = 8
        z_bot, z_top = -2.48, -1.35
        r_bot, r_top = 0.72, 0.84
        ring_b = []
        ring_t = []
        for i in range(n_sides):
            ang = (2.0 * math.pi * i) / n_sides + (math.pi / n_sides)
            ca, sa = math.cos(ang), math.sin(ang)
            ring_b.append(bm.verts.new((ca * r_bot, sa * r_bot, z_bot)))
            ring_t.append(bm.verts.new((ca * r_top, sa * r_top, z_top)))
            # Corner oak/brass rib
            _strut((ca * (r_bot + 0.02), sa * (r_bot + 0.02), z_bot), (ca * (r_top + 0.02), sa * (r_top + 0.02), z_top), rx=0.04, ry=0.04, mat_idx=1 if i % 2 == 0 else 2)

        for i in range(n_sides):
            ni = (i + 1) % n_sides
            f = bm.faces.new((ring_b[i], ring_b[ni], ring_t[ni], ring_t[i]))
            f.material_index = 0  # Wicker wall
        f_bot = bm.faces.new(list(reversed(ring_b)))
        f_bot.material_index = 1
        f_top = bm.faces.new(ring_t)
        f_top.material_index = 1

        # Top brass rim collar & bottom iron bumper skids
        _box(-0.86, 0.86, -0.86, 0.86, -1.42, -1.33, mat_idx=2)
        _box(-0.76, 0.76, -0.76, 0.76, -2.56, -2.46, mat_idx=3)

        # Glowing Blue Ice Crystals mound on top of the cargo gondola (`Z = -1.36 .. -0.82 m`)
        crystal_specs = [
            (0.0, 0.0, -1.36, 0.34, 0.56, 0.1, 0.05),
            (-0.28, 0.22, -1.36, 0.26, 0.44, -0.25, 0.18),
            (0.30, -0.20, -1.36, 0.25, 0.46, 0.22, -0.20),
            (-0.26, -0.25, -1.36, 0.24, 0.40, 0.18, 0.24),
            (0.25, 0.26, -1.36, 0.24, 0.42, -0.20, -0.18),
            (0.0, 0.36, -1.36, 0.20, 0.35, 0.30, 0.0),
            (0.0, -0.36, -1.36, 0.20, 0.35, -0.30, 0.0),
        ]
        for cx, cy, cz, rad, h_c, tx, ty in crystal_specs:
            ret_c = bmesh.ops.create_cone(bm, cap_ends=True, segments=5 if ultra_low_poly else 6, radius1=rad, radius2=0.02, depth=h_c)
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((tx, ty, 0.3)).to_matrix(), verts=ret_c["verts"])
            bmesh.ops.translate(bm, vec=(cx, cy, cz + h_c * 0.45), verts=ret_c["verts"])
            for v in ret_c["verts"]:
                for f in v.link_faces:
                    f.material_index = 4  # Blue ice SSS

        # Warm 2700K Front Brass Lantern
        _box(-0.10, 0.10, -0.96, -0.78, -1.82, -1.56, mat_idx=5)

    else:
        # 2B. PASSENGER GONDOLA (`GONDOLA_PASSENGER`):
        # Ornate Swan-Neck Overhead Hanger Arm (`Z = -0.12 .. -0.95 m`) curving around the back (-X) so the cabin below is open!
        swan_pts = [
            (0.0, 0.0, -0.14),
            (-0.18, 0.0, -0.35),
            (-0.48, 0.0, -0.56),
            (-0.52, 0.0, -0.78),
            (0.0, 0.0, -0.94),
        ]
        for i in range(len(swan_pts) - 1):
            _strut(swan_pts[i], swan_pts[i + 1], rx=0.055, ry=0.055, mat_idx=2)

        # Arched Canopy Roof Hood (`Z = -1.12 .. -0.92 m`, width `1.56 m`)
        _box(-0.78, 0.78, -0.78, 0.78, -1.08, -0.94, mat_idx=1)
        _box(-0.82, 0.82, -0.82, 0.82, -1.12, -1.05, mat_idx=2)

        # 4 Slender Corner Brass Canopy Columns (`Z = -2.45 .. -1.08 m`) leaving all 4 viewing sides WIDE OPEN for an Elf passenger!
        for sx in (-0.70, 0.70):
            for sy in (-0.70, 0.70):
                _strut((sx, sy, -2.48), (sx, sy, -1.08), rx=0.032, ry=0.032, mat_idx=2)

        # Open-Top Passenger Basket Tub (`Z = -2.52 .. -1.82 m`) with Interior Standing Floor at `Z = -2.42 m`
        # Floor deck
        _box(-0.74, 0.74, -0.74, 0.74, -2.52, -2.40, mat_idx=1)
        # 4 Wicker lower walls (`Z = -2.40 .. -1.88 m`)
        _box(-0.74, 0.74, -0.74, -0.64, -2.40, -1.88, mat_idx=0)
        _box(-0.74, 0.74,  0.64,  0.74, -2.40, -1.88, mat_idx=0)
        _box(-0.74, -0.64, -0.64, 0.64, -2.40, -1.88, mat_idx=0)
        _box( 0.64,  0.74, -0.64, 0.64, -2.40, -1.88, mat_idx=0)
        # Brass filigree top handrail around `Z = -1.72 m`
        _box(-0.76, 0.76, -0.76, -0.68, -1.76, -1.68, mat_idx=2)
        _box(-0.76, 0.76,  0.68,  0.76, -1.76, -1.68, mat_idx=2)
        _box(-0.76, -0.68, -0.68, 0.68, -1.76, -1.68, mat_idx=2)
        _box( 0.68,  0.76, -0.68, 0.68, -1.76, -1.68, mat_idx=2)
        # Hanging front 2700K brass lantern
        _box(0.66, 0.84, -0.84, -0.66, -1.48, -1.22, mat_idx=5)

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.use_fake_user = True
    return mesh


def _load_or_build_gondola_mesh(variant_id: str, low_poly_proxy: bool = False) -> bpy.types.Mesh:
    """
    Loads the optimized low-poly Tripo 3D Gondola `.glb` (shared instanced `bpy.types.Mesh` datablock!),
    normalizing its origin `(0, 0, 0)` to the exact top-center Cable Grip Clamp (`Z = 0.00 m`) so the
    gondola hangs below the rope (`Z = -height .. 0.00 m`).
    If `low_poly_proxy=True` or the `.glb` is not yet on disk, returns the ultra-low-poly procedural mesh.
    """
    if low_poly_proxy:
        return _build_procedural_lowpoly_gondola_mesh(variant_id, ultra_low_poly=True)

    spec = next((v for v in GONDOLA_VARIATIONS if v[0] == variant_id), GONDOLA_VARIATIONS[0])
    _, _, opt_glb_name, raw_glb_name, target_dims = spec
    tpl_mesh_name = f"TPL_RW_TripoMesh_{variant_id}"

    cached = bpy.data.meshes.get(tpl_mesh_name)
    if cached and len(cached.vertices) > 0:
        return cached

    # Search optimized GLB in `assets/models/glb_optimized/` first!
    candidate_paths = [
        os.path.join(ROPEWAY_OPT_GLB_DIR, opt_glb_name),
        os.path.join(ROPEWAY_GLB_DIR, opt_glb_name),
        os.path.join(ROPEWAY_GLB_DIR, raw_glb_name),
        os.path.join(ROPEWAY_GLB_DIR, os.path.splitext(raw_glb_name)[0] + ".fbx"),
    ]
    found_path = next((p for p in candidate_paths if os.path.isfile(p) and os.path.getsize(p) > 25_000), None)
    if not found_path:
        return _build_procedural_lowpoly_gondola_mesh(variant_id, ultra_low_poly=False)

    before = set(bpy.data.objects)
    try:
        if found_path.lower().endswith(".fbx"):
            bpy.ops.import_scene.fbx(filepath=found_path)
        else:
            bpy.ops.import_scene.gltf(filepath=found_path)
    except Exception as exc:
        print(f"[RopewayGondolas] Warning loading {found_path}: {exc}")
        return _build_procedural_lowpoly_gondola_mesh(variant_id, ultra_low_poly=False)

    imported = [o for o in bpy.data.objects if o not in before]
    mesh_objs = [o for o in imported if o.type == "MESH" and o.data and len(o.data.vertices) > 0]
    if not mesh_objs:
        for o in imported:
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
        return _build_procedural_lowpoly_gondola_mesh(variant_id, ultra_low_poly=False)

    mesh_objs.sort(key=lambda o: len(o.data.vertices), reverse=True)
    primary = mesh_objs[0]
    mw = primary.matrix_world.copy()
    mesh = primary.data.copy()
    mesh.name = tpl_mesh_name

    for v in mesh.vertices:
        v.co = mw @ v.co

    for o in imported:
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)

    # Normalize dimensions and set Origin (0, 0, 0) at TOP-CENTER CABLE GRIP CLAMP (`max_z -> 0.04 m`)
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    # Find top clamp X/Y center from the top 10% of vertices so the overhead grip is strictly at X=0, Y=0!
    z_top_band = max_z - 0.10 * max(1e-4, max_z - min_z)
    top_verts = [v.co for v in mesh.vertices if v.co.z >= z_top_band]
    if top_verts:
        cx_top = sum(v.x for v in top_verts) / len(top_verts)
        cy_top = sum(v.y for v in top_verts) / len(top_verts)
    else:
        cx_top = 0.5 * (min_x + max_x)
        cy_top = 0.5 * (min_y + max_y)

    tx, ty, tz = target_dims
    sx = tx / max(1e-4, max_x - min_x)
    sy = ty / max(1e-4, max_y - min_y)
    sz = tz / max(1e-4, max_z - min_z)

    for v in mesh.vertices:
        v.co.x = (v.co.x - cx_top) * sx
        v.co.y = (v.co.y - cy_top) * sy
        # Place cable grip groove at Z = 0.00 m (top rollers slightly above at +0.06 m, basket bottom at -tz)
        v.co.z = (v.co.z - max_z) * sz + 0.06

    mesh.update()
    mesh.use_fake_user = True
    return mesh


def _build_sheave_roller_battery_mesh(
    num_rollers: int = 4,
    roller_radius: float = 0.24,
) -> bpy.types.Mesh:
    """
    Builds a low-poly grooved brass Sheave Roller Battery (`baterija kolotura`)
    centered at `(0, 0, 0)` where the steel cable rides on top of the rollers at `Z = 0.00 m`.
    """
    name = f"TPL_RW_SheaveBattery_{num_rollers}Rollers"
    existing = bpy.data.meshes.get(name)
    if existing and len(existing.vertices) > 0:
        return existing
    mesh = existing or bpy.data.meshes.new(name)
    mesh.materials.clear()
    pal = _ensure_rw_palette()
    mesh.materials.append(pal["brass"])  # 0
    mesh.materials.append(pal["iron"])   # 1

    bm = bmesh.new()
    spacing = roller_radius * 2.35
    total_len = (num_rollers - 1) * spacing

    # Side iron rocker bars supporting the rollers
    for sx in (-0.11, 0.11):
        ret_b = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(0.035, total_len + roller_radius * 1.4, 0.14), verts=ret_b["verts"])
        bmesh.ops.translate(bm, vec=(sx, 0.0, -roller_radius), verts=ret_b["verts"])
        for v in ret_b["verts"]:
            for f in v.link_faces:
                f.material_index = 1

    # Grooved brass rollers whose top tangent sits at Z = 0.00 m (center at Z = -roller_radius)
    for idx in range(num_rollers):
        yc = -0.5 * total_len + idx * spacing
        for dz_flange, rad_mult, thick in (
            (-0.045, 1.0, 0.025),
            ( 0.000, 0.84, 0.065),
            ( 0.045, 1.0, 0.025),
        ):
            ret_w = bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                segments=12,
                radius1=roller_radius * rad_mult,
                radius2=roller_radius * rad_mult,
                depth=thick,
            )
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((0.0, math.pi * 0.5, 0.0)).to_matrix(), verts=ret_w["verts"])
            bmesh.ops.translate(bm, vec=(dz_flange, yc, -roller_radius), verts=ret_w["verts"])
            for v in ret_w["verts"]:
                for f in v.link_faces:
                    f.material_index = 0

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.use_fake_user = True
    return mesh


def _build_turnaround_bullwheel_mesh(radius: float = 1.70) -> bpy.types.Mesh:
    """
    Builds a low-poly spoked brass Turnaround Bullwheel (`Okretni Kolotur Postaje`)
    of radius `R = loop_gauge_m / 2` centered at `(0, 0, 0)` in the XY plane so the
    outgoing cable at `X = +R` wraps 180° around the rim onto the return cable at `X = -R`!
    """
    r_key = int(round(radius * 100))
    name = f"TPL_RW_TurnaroundBullwheel_R{r_key}"
    existing = bpy.data.meshes.get(name)
    if existing and len(existing.vertices) > 0:
        return existing
    mesh = existing or bpy.data.meshes.new(name)
    mesh.materials.clear()
    pal = _ensure_rw_palette()
    mesh.materials.append(pal["brass"])  # 0
    mesh.materials.append(pal["iron"])   # 1

    bm = bmesh.new()
    n_seg = 28
    # Grooved outer rim at radius `R`
    for z_off, r_out, r_in, h_ring, m_idx in (
        ( 0.07, radius * 1.04, radius * 0.90, 0.04, 0),
        ( 0.00, radius * 0.99, radius * 0.88, 0.10, 1),
        (-0.07, radius * 1.04, radius * 0.90, 0.04, 0),
    ):
        for i in range(n_seg):
            a0 = (2.0 * math.pi * i) / n_seg
            a1 = (2.0 * math.pi * (i + 1)) / n_seg
            p0 = Vector((math.cos(a0) * r_out, math.sin(a0) * r_out, z_off))
            p1 = Vector((math.cos(a1) * r_out, math.sin(a1) * r_out, z_off))
            dv = p1 - p0
            ret = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(r_out - r_in, h_ring, dv.length * 1.05), verts=ret["verts"])
            mid = 0.5 * (p0 + p1)
            radial_ang = math.atan2(mid.y, mid.x)
            rot = Euler((math.pi * 0.5, 0.0, radial_ang + math.pi * 0.5)).to_matrix()
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot, verts=ret["verts"])
            bmesh.ops.translate(bm, vec=mid, verts=ret["verts"])
            for v in ret["verts"]:
                for f in v.link_faces:
                    f.material_index = m_idx

    # 8 Radial Brass Spokes + Central Iron Hub
    for k in range(8):
        ang = (2.0 * math.pi * k) / 8.0
        ret_s = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(radius * 0.92, 0.11, 0.09), verts=ret_s["verts"])
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((0.0, 0.0, ang)).to_matrix(), verts=ret_s["verts"])
        bmesh.ops.translate(bm, vec=(math.cos(ang) * radius * 0.46, math.sin(ang) * radius * 0.46, 0.0), verts=ret_s["verts"])
        for v in ret_s["verts"]:
            for f in v.link_faces:
                f.material_index = 0

    ret_h = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.34, radius2=0.34, depth=0.45)
    for v in ret_h["verts"]:
        for f in v.link_faces:
            f.material_index = 1

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.use_fake_user = True
    return mesh


def _build_pylon_crossarm_and_support_mesh(
    loop_gauge_m: float = 3.40,
    support_mode: str = "PYLON_TOWER",
    tower_height_m: float = 14.0,
    target_mesh: bpy.types.Mesh = None,
) -> bpy.types.Mesh:
    """
    Builds or updates in-place an ultra-optimized low-poly Pylon Cross-Arm & Dynamic
    Downward Support Tower mesh centered at the Null point `(0, 0, 0)` where:
      - Outgoing sheave battery sits at `X = +loop_gauge_m / 2, Z = 0.0`
      - Return sheave battery sits at `X = -loop_gauge_m / 2, Z = 0.0`
      - For `PYLON_TOWER`: dynamically constructs a tapered 4-leg timber & iron
        lattice tower from the Null point cross-arm (`Z = -0.85 m`) straight downwards
        to `Z = -tower_height_m`, dynamically adding/removing structural truss bays
        every ~3.8 m as `tower_height_m` changes.
    """
    if target_mesh is not None:
        mesh = target_mesh
    else:
        g_key = int(round(loop_gauge_m * 100))
        h_key = int(round(tower_height_m * 100))
        name = f"TPL_RW_PylonCrossArm_{support_mode}_G{g_key}_H{h_key}"
        mesh = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)

    mesh.materials.clear()
    pal = _ensure_rw_palette()
    mesh.materials.append(pal["wood"])     # 0
    mesh.materials.append(pal["iron"])     # 1
    mesh.materials.append(pal["brass"])    # 2
    mesh.materials.append(pal["lantern"])  # 3

    bm = bmesh.new()
    half_g = 0.5 * loop_gauge_m

    def _box(x0, x1, y0, y1, z0, z1, mat_idx=0):
        ret = bmesh.ops.create_cube(bm, size=1.0)
        verts = ret["verts"]
        bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=verts)
        bmesh.ops.translate(bm, vec=(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)), verts=verts)
        for v in verts:
            for f in v.link_faces:
                f.material_index = mat_idx

    def _strut(p0, p1, r=0.12, mat_idx=0):
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
        ret = bmesh.ops.create_cube(bm, size=1.0)
        verts = ret["verts"]
        for v in verts:
            lx, ly, lz = v.co.x * (r * 2.0), v.co.y * (r * 2.0), v.co.z * length
            v.co = mid + x_axis * lx + y_axis * ly + z_axis * lz
            for f in v.link_faces:
                f.material_index = mat_idx

    # 1. Horizontal T-Bar Oak Cross-Arm (`X = -(half_g + 0.45) .. +(half_g + 0.45)`, `Z = -0.88 .. -0.52 m`)
    arm_w = half_g + 0.45
    _box(-arm_w, arm_w, -0.22, 0.22, -0.88, -0.52, mat_idx=0)
    # Iron mounting brackets under left & right sheave batteries (`X = ±half_g`)
    for sx in (-half_g, half_g):
        _box(sx - 0.22, sx + 0.22, -0.28, 0.28, -0.54, -0.36, mat_idx=1)
    # Central iron collar & top signal lantern at `(0, 0, +0.45 m)`
    _box(-0.34, 0.34, -0.34, 0.34, -0.95, 0.25, mat_idx=1)
    _box(-0.14, 0.14, -0.14, 0.14,  0.25, 0.58, mat_idx=3)

    # Diagonal knee braces under the cross-arm
    knee_z = -min(max(1.10, float(tower_height_m)), 2.10)
    _strut((-0.25, 0.0, knee_z), (-half_g * 0.82, 0.0, -0.75), r=0.10, mat_idx=1)
    _strut(( 0.25, 0.0, knee_z), ( half_g * 0.82, 0.0, -0.75), r=0.10, mat_idx=1)

    # 2. Support Structure Mode
    if support_mode == "PYLON_TOWER":
        h = max(0.95, float(tower_height_m))
        if h > 1.02:
            z_top_leg = -0.85
            leg_span = max(0.15, h - 0.85)
            # Tapered 4-leg timber & iron trestle tower from Z = -0.85 straight down to Z = -h
            top_w = 0.34
            bot_w = min(4.20, 0.36 + leg_span * 0.055)
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    _strut((sx * top_w, sy * top_w, z_top_leg), (sx * bot_w, sy * bot_w, -h), r=0.14, mat_idx=0)
                    # Iron base footing pad at exact Z = -h
                    foot_h = min(0.32, leg_span * 0.25)
                    _box(
                        sx * bot_w - 0.26, sx * bot_w + 0.26,
                        sy * bot_w - 0.26, sy * bot_w + 0.26,
                        -h, -h + foot_h,
                        mat_idx=1,
                    )

            # Dynamic horizontal perimeter rings & 4-sided X-bracing tiers every ~3.8 m
            n_tiers = max(1, int(round(leg_span / 3.8)))
            for t_idx in range(1, n_tiers + 1):
                u0 = (t_idx - 1) / n_tiers
                u1 = t_idx / n_tiers
                z0 = z_top_leg - u0 * leg_span
                z1 = z_top_leg - u1 * leg_span
                w0 = top_w + u0 * (bot_w - top_w)
                w1 = top_w + u1 * (bot_w - top_w)

                # 4 perimeter horizontal iron collar beams at z1
                for sy in (-1.0, 1.0):
                    _strut((-w1, sy * w1, z1), (w1, sy * w1, z1), r=0.075, mat_idx=1)
                for sx in (-1.0, 1.0):
                    _strut((sx * w1, -w1, z1), (sx * w1, w1, z1), r=0.075, mat_idx=1)

                # 4-sided diagonal X-braces (front +Y, back -Y, left -X, right +X)
                for sy in (-1.0, 1.0):
                    _strut((-w0, sy * w0, z0), ( w1, sy * w1, z1), r=0.06, mat_idx=1)
                    _strut(( w0, sy * w0, z0), (-w1, sy * w1, z1), r=0.06, mat_idx=1)
                for sx in (-1.0, 1.0):
                    _strut((sx * w0, -w0, z0), (sx * w1,  w1, z1), r=0.06, mat_idx=1)
                    _strut((sx * w0,  w0, z0), (sx * w1, -w1, z1), r=0.06, mat_idx=1)
    elif support_mode == "CEILING_HANGER":
        h = max(1.5, float(tower_height_m))
        # Overhead A-frame suspension struts rising up into the cavern ceiling (`Z = 0.0 .. +h`)
        _strut((-0.30, -0.25, -0.55), (-1.15, -0.85, h), r=0.13, mat_idx=1)
        _strut(( 0.30,  0.25, -0.55), ( 1.15,  0.85, h), r=0.13, mat_idx=1)
        _strut((-0.30,  0.25, -0.55), (-1.15,  0.85, h), r=0.13, mat_idx=1)
        _strut(( 0.30, -0.25, -0.55), ( 1.15, -0.85, h), r=0.13, mat_idx=1)
    elif support_mode == "CLIFF_WALL_BRACKET":
        # Cantilevered cliffside terminal bracket extending along local -Y directly into the +X glacier cliff wall!
        for sx in (-0.88, 0.88):
            _strut((sx, 0.18, -0.70), (sx, -6.80, -0.70), r=0.15, mat_idx=0)
            _strut((sx, 0.05, -0.78), (sx, -6.80, -3.55), r=0.14, mat_idx=0)
            _box(sx - 0.22, sx + 0.22, -0.24, 0.24, -0.96, -0.46, mat_idx=1)
        _box(-1.05, 1.05, -1.65, -1.42, -0.88, -0.54, mat_idx=1)
        _strut((-0.88, -0.20, -0.70), (0.88, -2.40, -1.65), r=0.08, mat_idx=1)
        _strut(( 0.88, -0.20, -0.70), (-0.88, -2.40, -1.65), r=0.08, mat_idx=1)

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    if target_mesh is None:
        mesh.use_fake_user = True
    return mesh


def _load_or_build_cargo_insert_mesh(cargo_type: str) -> bpy.types.Mesh:
    """Loads or builds a low-poly instanced cargo insert mesh (`ICE_CRYSTALS`, `CRATE_TOOLS`, `BARREL_LANTERN`)."""
    if cargo_type == "NONE":
        return None
    tpl_name = f"TPL_RW_CargoInsert_{cargo_type}"
    cached = bpy.data.meshes.get(tpl_name)
    if cached and len(cached.vertices) > 0:
        return cached

    # Procedural low-poly crystal/crate/barrel insert (only ~48 faces!) for ultra-fast rendering
    mesh = cached or bpy.data.meshes.new(tpl_name)
    mesh.materials.clear()
    pal = _ensure_rw_palette()
    mesh.materials.append(pal["ice"])      # 0
    mesh.materials.append(pal["wood"])     # 1
    mesh.materials.append(pal["brass"])    # 2
    mesh.materials.append(pal["lantern"])  # 3

    bm = bmesh.new()
    if cargo_type == "ICE_CRYSTALS":
        specs = [
            (0.0, 0.0, 0.0, 0.30, 0.62, 0.08, -0.05),
            (-0.24, 0.18, 0.0, 0.22, 0.48, -0.22, 0.16),
            (0.24, -0.18, 0.0, 0.22, 0.50, 0.20, -0.18),
            (-0.20, -0.22, 0.0, 0.20, 0.42, 0.15, 0.22),
            (0.22, 0.22, 0.0, 0.20, 0.44, -0.18, -0.16),
        ]
        for cx, cy, cz, rad, hc, rx, ry in specs:
            ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=rad, radius2=0.02, depth=hc)
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((rx, ry, 0.2)).to_matrix(), verts=ret["verts"])
            bmesh.ops.translate(bm, vec=(cx, cy, cz + hc * 0.45), verts=ret["verts"])
            for v in ret["verts"]:
                for f in v.link_faces:
                    f.material_index = 0
    elif cargo_type == "CRATE_TOOLS":
        ret = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(0.68, 0.52, 0.46), verts=ret["verts"])
        bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.23), verts=ret["verts"])
        for v in ret["verts"]:
            for f in v.link_faces:
                f.material_index = 1
    else:
        ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.28, radius2=0.28, depth=0.62)
        bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.31), verts=ret["verts"])
        for v in ret["verts"]:
            for f in v.link_faces:
                f.material_index = 1

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.use_fake_user = True
    return mesh


# ============================================================================
# 2. MATHEMATICAL CATENARY & MOVING GONDOLA LOAD DEFLECTION ENGINE
# ============================================================================

def compute_catenary_normalized_profile(u: float, kappa: float = 1.35) -> float:
    r"""
    Normalized hyperbolic catenary sag profile $\Phi_{\text{cat}}(u) \in [0, 1]$:
      - $\Phi_{\text{cat}}(0) = 0$
      - $\Phi_{\text{cat}}(1) = 0$
      - $\Phi_{\text{cat}}(0.5) = 1.0$
    """
    u_c = max(0.0, min(1.0, float(u)))
    denom = math.cosh(kappa) - 1.0
    if denom < 1e-6:
        return 4.0 * u_c * (1.0 - u_c)
    return (math.cosh(kappa) - math.cosh(kappa * (2.0 * u_c - 1.0))) / denom


def compute_smooth_greens_point_load_deflection(u: float, u_load: float, eps0: float = 0.085) -> float:
    r"""
    Exact $C^\infty$ flexural Green's function $g_{\text{smooth}}(u, u_k)$ for a tensioned cable span
    pinned at the pulley sheaves ($u = 0$ and $u = 1$) under a concentrated moving gondola load at $u_k \in (0, 1)$:
      $$g_{\text{smooth}}(u, u_k) = 2\left( u + u_k - 2 u u_k - \sqrt{(u - u_k)^2 + \big(4 \epsilon_0 u(1-u) u_k(1-u_k)\big)^2} \right)$$
    Properties:
      - $g_{\text{smooth}}(0, u_k) = 0$ and $g_{\text{smooth}}(1, u_k) = 0$ (100% pinned to pulley sheaves at Null points!)
      - $g_{\text{smooth}}(u, 0) = 0$ and $g_{\text{smooth}}(u, 1) = 0$ (zero extra sink when gondola passes over a pulley tower!)
      - $g_{\text{smooth}}(0.5, 0.5) \approx 1.0$ (maximum sink when gondola is at mid-span!)
    """
    u_c = max(0.0, min(1.0, float(u)))
    uk_c = max(0.0, min(1.0, float(u_load)))
    if u_c <= 1e-6 or u_c >= 1.0 - 1e-6 or uk_c <= 1e-6 or uk_c >= 1.0 - 1e-6:
        return 0.0
    du = u_c - uk_c
    flex_reg = 4.0 * eps0 * u_c * (1.0 - u_c) * uk_c * (1.0 - uk_c)
    val = 2.0 * (u_c + uk_c - 2.0 * u_c * uk_c - math.sqrt(du * du + flex_reg * flex_reg))
    return max(0.0, val)


def evaluate_span_3d_point_and_slope(
    s0: Vector,
    s1: Vector,
    u: float,
    gondola_loads_on_span: list,
    base_sag_m: float = 1.35,
    load_sink_m: float = 0.95,
    ref_span_m: float = 45.0,
) -> tuple[Vector, Vector, float]:
    r"""
    Evaluates the exact 3D cable coordinate $\mathbf{C}(u, t)$, unit 3D tangent $\hat{\mathbf{T}}(u, t)$,
    and total vertical sag depression $\Delta Z(u, t) \le 0$ at fractional position $u \in [0, 1]$
    along a span from sheave $\mathbf{s}_0$ to sheave $\mathbf{s}_1$.

    `gondola_loads_on_span`: list of `(u_k, weight_factor_k)` for all gondolas currently on this span.
    """
    u_c = max(0.0, min(1.0, float(u)))
    chord = s1 - s0
    L = max(0.01, chord.length)
    L_h = math.hypot(chord.x, chord.y)
    cos_alpha = L_h / L

    # Quadratic span scaling for self-weight catenary sag, linear span scaling for concentrated point load
    span_ratio = L / max(5.0, ref_span_m)
    cat_amp = min(L * 0.28, float(base_sag_m) * (span_ratio ** 1.85) * max(0.25, cos_alpha))
    load_amp = min(L * 0.22, float(load_sink_m) * (span_ratio ** 1.05) * max(0.25, cos_alpha))

    def _dz_at(uu: float) -> float:
        sag_cat = cat_amp * compute_catenary_normalized_profile(uu)
        sag_loads = 0.0
        for uk, wk in gondola_loads_on_span:
            sag_loads += float(wk) * compute_smooth_greens_point_load_deflection(uu, uk)
        return -(sag_cat + load_amp * sag_loads)

    dz = _dz_at(u_c)
    pt = s0.lerp(s1, u_c)
    pt.z += dz

    # Numerical derivative along u for exact cable tangent slope (pitch & grip alignment)
    du_step = 0.008
    u_a = max(0.0, u_c - du_step)
    u_b = min(1.0, u_c + du_step)
    pt_a = s0.lerp(s1, u_a)
    pt_a.z += _dz_at(u_a)
    pt_b = s0.lerp(s1, u_b)
    pt_b.z += _dz_at(u_b)
    tang = (pt_b - pt_a)
    if tang.length > 1e-6:
        tang.normalize()
    else:
        tang = chord.normalized()

    return pt, tang, dz


def compute_pylon_frames_from_null_points(null_objs: list, loop_gauge_m: float) -> list:
    r"""
    Given an ordered list of $N \ge 2$ Pylon Null point objects `[P_0, P_1, ..., P_{N-1}]`,
    computes at each Null point $i$:
      - `pos`: 3D Vector $\mathbf{P}_i$
      - `fwd_xy`: horizontal unit tangent bisecting incoming and outgoing spans
      - `right_xy`: horizontal unit cross-arm vector perpendicular to `fwd_xy`
      - `yaw_rad`: Z-rotation angle so local `+Y` points along `fwd_xy` and local `+X` points along `right_xy`
      - `pitch_out_rad`, `pitch_ret_rad`: vertical cable slope angles at the sheaves
      - `sheave_out`: 3D contact point $\mathbf{A}_i = \mathbf{P}_i + \frac{W}{2}\hat{\mathbf{r}}_i$ (Outgoing line)
      - `sheave_ret`: 3D contact point $\mathbf{B}_i = \mathbf{P}_i - \frac{W}{2}\hat{\mathbf{r}}_i$ (Return line)
    """
    pts = [o.location.copy() for o in null_objs]
    n = len(pts)
    half_g = 0.5 * max(0.5, float(loop_gauge_m))
    frames = []

    for i in range(n):
        if i == 0:
            d_out = pts[1] - pts[0]
            d_in = d_out
        elif i == n - 1:
            d_in = pts[n - 1] - pts[n - 2]
            d_out = d_in
        else:
            d_in = pts[i] - pts[i - 1]
            d_out = pts[i + 1] - pts[i]

        t_in_xy = Vector((d_in.x, d_in.y, 0.0))
        t_out_xy = Vector((d_out.x, d_out.y, 0.0))
        if t_in_xy.length > 1e-5:
            t_in_xy.normalize()
        else:
            t_in_xy = Vector((0.0, 1.0, 0.0))
        if t_out_xy.length > 1e-5:
            t_out_xy.normalize()
        else:
            t_out_xy = t_in_xy.copy()

        bis = t_in_xy + t_out_xy
        if bis.length > 1e-5:
            fwd_xy = bis.normalized()
        else:
            fwd_xy = t_out_xy.copy()

        # Right vector (+X local when +Y local = fwd_xy)
        right_xy = Vector((fwd_xy.y, -fwd_xy.x, 0.0)).normalized()
        yaw_rad = math.atan2(-fwd_xy.x, fwd_xy.y)

        # Average vertical slope pitch across this pylon
        slope_vec = 0.5 * (d_in.normalized() + d_out.normalized())
        horiz_len = max(1e-4, math.hypot(slope_vec.x, slope_vec.y))
        pitch_rad = math.atan2(slope_vec.z, horiz_len)

        p_i = pts[i]
        sheave_out = p_i + right_xy * half_g
        sheave_ret = p_i - right_xy * half_g

        frames.append({
            "index": i,
            "null_obj": null_objs[i],
            "pos": p_i,
            "fwd_xy": fwd_xy,
            "right_xy": right_xy,
            "yaw_rad": yaw_rad,
            "pitch_rad": pitch_rad,
            "half_gauge": half_g,
            "sheave_out": sheave_out,
            "sheave_ret": sheave_ret,
        })

    return frames


def evaluate_ropeway_system_at_frame(sys_root: bpy.types.Object, frame: float, scene: bpy.types.Scene = None) -> dict:
    r"""
    Pure mathematical solver for the entire closed-loop Ropeway System at `frame`.
    Returns:
      - `pylon_frames`: computed transforms and sheave contact points for all $N$ Null points
      - `cable_loop_points`: ordered 3D points forming the closed cyclic haul cable (including exact vertices at every gondola clamp!)
      - `gondola_states`: list of dicts (`location`, `rotation_euler`, `span_type`, `span_index`, `u`, `sag_dz_m`) for all $K$ gondolas
      - `travel_dist_m`: cumulative cable travel distance $s(t) = v \cdot t$ (used to spin all pulley sheaves and bullwheels)
      - `total_loop_length_m`: total 3D closed circuit length
      - `max_sag_m`: deepest dynamic cable sag across all spans at this frame
    """
    scn = scene or bpy.context.scene
    fps = float(scn.render.fps) / max(1.0, float(scn.render.fps_base))
    t_sec = (float(frame) - 1.0) / max(1.0, fps)

    null_objs = get_system_null_point_objects(sys_root)
    if len(null_objs) < 2:
        return {}

    loop_gauge_m = float(sys_root.get("af_rw_loop_gauge_m", 3.40))
    speed_mps = float(sys_root.get("af_rw_speed_mps", 2.40))
    base_sag_m = float(sys_root.get("af_rw_base_sag_m", 1.35))
    load_sink_m = float(sys_root.get("af_rw_load_sink_m", 0.95))
    sway_amp_deg = float(sys_root.get("af_rw_sway_amp_deg", 4.5))
    ref_span_m = float(sys_root.get("af_rw_ref_span_m", 45.0))

    pylons = compute_pylon_frames_from_null_points(null_objs, loop_gauge_m)
    n_pylons = len(pylons)
    n_spans = n_pylons - 1
    half_g = 0.5 * max(0.5, loop_gauge_m)

    # 1. Build the closed-loop circuit segment table:
    #    - Outgoing spans: e = 0 .. n_spans - 1 (from A_e to A_{e+1})
    #    - Far turnaround arc at pylon N-1 (semicircle from A_{N-1} around +fwd_{N-1} to B_{N-1})
    #    - Return spans: e = 0 .. n_spans - 1 (from B_{N-1-e} to B_{N-2-e})
    #    - Near turnaround arc at pylon 0 (semicircle from B_0 around -fwd_0 to A_0)
    segments = []
    cum_len = 0.0

    for e in range(n_spans):
        s0 = pylons[e]["sheave_out"]
        s1 = pylons[e + 1]["sheave_out"]
        seg_len = max(0.1, (s1 - s0).length)
        segments.append({
            "kind": "SPAN_OUT",
            "span_idx": e,
            "s0": s0,
            "s1": s1,
            "length": seg_len,
            "s_start": cum_len,
            "s_end": cum_len + seg_len,
            "gondolas": [],
        })
        cum_len += seg_len

    far_arc_len = math.pi * half_g
    segments.append({
        "kind": "TURN_FAR",
        "pylon_idx": n_pylons - 1,
        "length": far_arc_len,
        "s_start": cum_len,
        "s_end": cum_len + far_arc_len,
        "gondolas": [],
    })
    cum_len += far_arc_len

    for e in range(n_spans):
        p_from = n_pylons - 1 - e
        p_to = n_pylons - 2 - e
        s0 = pylons[p_from]["sheave_ret"]
        s1 = pylons[p_to]["sheave_ret"]
        seg_len = max(0.1, (s1 - s0).length)
        segments.append({
            "kind": "SPAN_RET",
            "span_idx": e,
            "pylon_from": p_from,
            "pylon_to": p_to,
            "s0": s0,
            "s1": s1,
            "length": seg_len,
            "s_start": cum_len,
            "s_end": cum_len + seg_len,
            "gondolas": [],
        })
        cum_len += seg_len

    near_arc_len = math.pi * half_g
    segments.append({
        "kind": "TURN_NEAR",
        "pylon_idx": 0,
        "length": near_arc_len,
        "s_start": cum_len,
        "s_end": cum_len + near_arc_len,
        "gondolas": [],
    })
    cum_len += near_arc_len
    total_loop_len = max(1.0, cum_len)

    # 2. Locate each gondola along the closed loop at time t_sec and register its point load on its active span
    gondola_objs = get_system_gondola_objects(sys_root)
    n_gondolas = len(gondola_objs)
    travel_dist = speed_mps * t_sec

    gondola_placements = []
    for k, g_obj in enumerate(gondola_objs):
        phase_offset = float(g_obj.get("af_rw_phase_offset", 0.0))
        s_pos = (((k + phase_offset) / max(1, n_gondolas)) * total_loop_len + travel_dist) % total_loop_len
        w_factor = float(g_obj.get("af_rw_weight_factor", 1.25))

        # Find segment containing s_pos
        active_seg = segments[-1]
        for seg in segments:
            if seg["s_start"] <= s_pos <= seg["s_end"] + 1e-5:
                active_seg = seg
                break
        u_local = (s_pos - active_seg["s_start"]) / max(1e-4, active_seg["length"])
        u_local = max(0.0, min(1.0, u_local))

        active_seg["gondolas"].append((k, u_local, w_factor))
        gondola_placements.append({
            "index": k,
            "obj": g_obj,
            "s_pos": s_pos,
            "seg": active_seg,
            "u": u_local,
            "weight": w_factor,
        })

    # 3. Evaluate the 3D Closed-Loop Cable Curve Points (including exact sample vertices at every gondola u_k!)
    cable_loop_pts = []
    max_sag_abs = 0.0
    base_samples_per_span = 18

    def _eval_turnaround_arc(pylon_frame: dict, is_far_end: bool, u_arc: float) -> tuple[Vector, Vector]:
        """
        Evaluates position and tangent on the 180° turnaround bullwheel of radius `half_g`.
        - Far end (`pylon N-1`): goes from `sheave_out` (+right_xy) around `+fwd_xy` to `sheave_ret` (-right_xy).
        - Near end (`pylon 0`): goes from `sheave_ret` (-right_xy) around `-fwd_xy` to `sheave_out` (+right_xy).
        """
        center = pylon_frame["pos"]
        r_vec = pylon_frame["right_xy"]
        f_vec = pylon_frame["fwd_xy"]
        R = pylon_frame["half_gauge"]
        ang = math.pi * max(0.0, min(1.0, u_arc))
        if is_far_end:
            pos = center + (r_vec * math.cos(ang) + f_vec * math.sin(ang)) * R
            tang = (-r_vec * math.sin(ang) + f_vec * math.cos(ang)).normalized()
        else:
            pos = center + (-r_vec * math.cos(ang) - f_vec * math.sin(ang)) * R
            tang = (r_vec * math.sin(ang) - f_vec * math.cos(ang)).normalized()
        return pos, tang

    for seg in segments:
        kind = seg["kind"]
        if kind in ("SPAN_OUT", "SPAN_RET"):
            s0, s1 = seg["s0"], seg["s1"]
            loads = [(u_k, w_k) for (_, u_k, w_k) in seg["gondolas"]]
            # Merge uniform u grid with exact gondola u_k coordinates so the cable vertex hits every grip clamp!
            u_grid = [j / base_samples_per_span for j in range(base_samples_per_span)]
            for _, u_k, _ in seg["gondolas"]:
                if 0.002 < u_k < 0.998:
                    u_grid.append(u_k)
            u_sorted = sorted(set(round(u_val, 5) for u_val in u_grid))
            for u_val in u_sorted:
                pt, _, dz = evaluate_span_3d_point_and_slope(
                    s0, s1, u_val, loads,
                    base_sag_m=base_sag_m,
                    load_sink_m=load_sink_m,
                    ref_span_m=ref_span_m,
                )
                cable_loop_pts.append(pt)
                if abs(dz) > max_sag_abs:
                    max_sag_abs = abs(dz)
        elif kind == "TURN_FAR":
            pf = pylons[seg["pylon_idx"]]
            for j in range(10):
                pt, _ = _eval_turnaround_arc(pf, is_far_end=True, u_arc=j / 10.0)
                cable_loop_pts.append(pt)
        elif kind == "TURN_NEAR":
            pf = pylons[seg["pylon_idx"]]
            for j in range(10):
                pt, _ = _eval_turnaround_arc(pf, is_far_end=False, u_arc=j / 10.0)
                cable_loop_pts.append(pt)

    # 4. Evaluate Exact 3D Grip Clamp Position & Damped Pendulum Orientation for Every Gondola
    gondola_states = []
    sway_rad = math.radians(sway_amp_deg)

    for gp in gondola_placements:
        k = gp["index"]
        seg = gp["seg"]
        u_k = gp["u"]
        kind = seg["kind"]

        if kind in ("SPAN_OUT", "SPAN_RET"):
            s0, s1 = seg["s0"], seg["s1"]
            loads = [(uk_other, wk_other) for (_, uk_other, wk_other) in seg["gondolas"]]
            pt, tang, dz = evaluate_span_3d_point_and_slope(
                s0, s1, u_k, loads,
                base_sag_m=base_sag_m,
                load_sink_m=load_sink_m,
                ref_span_m=ref_span_m,
            )
            yaw = math.atan2(-tang.x, tang.y)
            # Damped tower-crossing pendulum oscillation + gentle wind/cable harmonic sway
            dist_from_sheave = min(u_k, 1.0 - u_k) * seg["length"]
            sheave_impulse = math.exp(-0.18 * dist_from_sheave) * math.sin(t_sec * 3.4 + k * 1.7)
            ambient_sway = 0.35 * math.sin(t_sec * 1.85 + k * 2.1)
            roll = sway_rad * (0.75 * sheave_impulse + ambient_sway)
            # Subtle damped pitch following cable sag slope + pendulum harmonic
            cable_slope_pitch = math.atan2(tang.z, max(1e-4, math.hypot(tang.x, tang.y)))
            pitch = 0.22 * cable_slope_pitch + sway_rad * 0.55 * math.cos(t_sec * 2.9 + k * 1.3) * math.exp(-0.12 * dist_from_sheave)
        else:
            is_far = (kind == "TURN_FAR")
            pf = pylons[seg["pylon_idx"]]
            pt, tang = _eval_turnaround_arc(pf, is_far_end=is_far, u_arc=u_k)
            dz = 0.0
            yaw = math.atan2(-tang.x, tang.y)
            # Centrifugal outward roll while swinging around the 180° turnaround bullwheel
            centrifugal_roll = math.atan2(speed_mps * abs(speed_mps), 9.81 * max(0.6, half_g)) * 0.65
            envelope = math.sin(math.pi * u_k)
            roll = centrifugal_roll * envelope + 0.25 * sway_rad * math.sin(t_sec * 2.5 + k)
            pitch = 0.20 * sway_rad * math.cos(t_sec * 2.5 + k)

        gondola_states.append({
            "index": k,
            "location": pt,
            "rotation_euler": Euler((pitch, roll, yaw), "XYZ"),
            "segment_kind": kind,
            "u": u_k,
            "sag_dz_m": round(dz, 4),
        })

    return {
        "pylon_frames": pylons,
        "cable_loop_points": cable_loop_pts,
        "gondola_states": gondola_states,
        "travel_dist_m": travel_dist,
        "total_loop_length_m": round(total_loop_len, 3),
        "max_sag_m": round(max_sag_abs, 4),
    }


# ============================================================================
# 3. SCENE APPLICATION, OBJECT DISCOVERY & LIVE HANDLERS
# ============================================================================

def get_all_ropeway_systems(scene: bpy.types.Scene = None) -> list:
    objs = (scene.objects if scene else bpy.data.objects)
    systems = [o for o in objs if o.get("af_is_ropeway_system")]
    systems.sort(key=lambda o: o.get("af_rw_tag", o.name))
    return systems


def find_ropeway_system_from_object(obj: bpy.types.Object) -> bpy.types.Object:
    if not obj:
        return None
    if obj.get("af_is_ropeway_system"):
        return obj
    sys_name = obj.get("af_rw_sys_root", "")
    if sys_name and sys_name in bpy.data.objects:
        return bpy.data.objects[sys_name]
    cur = obj.parent
    while cur:
        if cur.get("af_is_ropeway_system"):
            return cur
        s_n = cur.get("af_rw_sys_root", "")
        if s_n and s_n in bpy.data.objects:
            return bpy.data.objects[s_n]
        cur = cur.parent
    return None


def get_active_ropeway_system(context=None) -> bpy.types.Object:
    ctx = context or bpy.context
    active = getattr(ctx, "active_object", None)
    sys_root = find_ropeway_system_from_object(active)
    if sys_root:
        return sys_root
    scn = getattr(ctx, "scene", None) or bpy.context.scene
    chosen_name = getattr(scn, "af_rw_active_system_name", "")
    if chosen_name and chosen_name in bpy.data.objects:
        cand = bpy.data.objects[chosen_name]
        if cand.get("af_is_ropeway_system"):
            return cand
    all_sys = get_all_ropeway_systems(scn)
    return all_sys[0] if all_sys else None


def get_system_null_point_objects(sys_root: bpy.types.Object) -> list:
    if not sys_root:
        return []
    tag = sys_root.get("af_rw_tag", "01")
    nulls = [
        o for o in bpy.data.objects
        if o.get("af_is_rw_null_point") and o.get("af_rw_tag") == tag
    ]
    nulls.sort(key=lambda o: int(o.get("af_rw_null_index", 0)))
    return nulls


def get_system_gondola_objects(sys_root: bpy.types.Object) -> list:
    if not sys_root:
        return []
    tag = sys_root.get("af_rw_tag", "01")
    gondolas = [
        o for o in bpy.data.objects
        if o.get("af_is_rw_gondola") and o.get("af_rw_tag") == tag
    ]
    gondolas.sort(key=lambda o: int(o.get("af_rw_gondola_index", 0)))
    return gondolas


def get_active_gondola_object(context=None, sys_root: bpy.types.Object = None) -> bpy.types.Object:
    ctx = context or bpy.context
    active = getattr(ctx, "active_object", None)
    if active:
        if active.get("af_is_rw_gondola"):
            return active
        cur = active.parent
        while cur:
            if cur.get("af_is_rw_gondola"):
                return cur
            cur = cur.parent
    sys_r = sys_root or get_active_ropeway_system(ctx)
    if not sys_r:
        return None
    gondolas = get_system_gondola_objects(sys_r)
    if not gondolas:
        return None
    scn = getattr(ctx, "scene", None) or bpy.context.scene
    idx = int(getattr(scn, "af_rw_selected_gondola_index", 1)) - 1
    idx = max(0, min(len(gondolas) - 1, idx))
    return gondolas[idx]


def apply_ropeway_evaluation_to_system(sys_root: bpy.types.Object, frame: float = None, scene: bpy.types.Scene = None) -> dict:
    """
    Evaluates the mathematical catenary + moving gondola load sag solver at `frame`
    and updates:
      1. The 3D Closed-Loop Haul Cable Curve (`ROPE_Loop_<tag>`)
      2. All Pylon Cross-Arms, Rotating Sheave Roller Batteries, and Turnaround Bullwheels (`PYLON_Head_<tag>_*`)
      3. All Gondola Carriages (`GONDOLA_Car_<tag>_*`) and their mounted Elves/Cargo
    """
    if not sys_root:
        return {}
    scn = scene or bpy.context.scene
    f_eval = float(scn.frame_current if frame is None else frame)

    state = evaluate_ropeway_system_at_frame(sys_root, f_eval, scene=scn)
    if not state:
        return {}

    tag = sys_root.get("af_rw_tag", "01")
    travel_dist = state["travel_dist_m"]
    show_bull = bool(sys_root.get("af_rw_show_turnaround_wheels", True))
    pulley_scale = float(sys_root.get("af_rw_pulley_scale", 1.0))

    # 1. Update Closed-Loop Haul Cable Spline (`ROPE_Loop_<tag>`)
    rope_obj = bpy.data.objects.get(sys_root.get("af_rw_rope_obj", f"ROPE_Loop_{tag}"))
    pts = state["cable_loop_points"]
    if rope_obj and rope_obj.type == "CURVE" and pts:
        cu = rope_obj.data
        if not cu.splines or len(cu.splines[0].points) != len(pts):
            cu.splines.clear()
            sp = cu.splines.new("POLY")
            sp.points.add(len(pts) - 1)
            sp.use_cyclic_u = True
        else:
            sp = cu.splines[0]
            sp.use_cyclic_u = True
        for i, p in enumerate(pts):
            sp.points[i].co = (p.x, p.y, p.z, 1.0)

        # 2. Update Pylon Cross-Arms, Sheave Roller Batteries & Turnaround Bullwheels
    pylons = state["pylon_frames"]
    n_pylons = len(pylons)
    for pf in pylons:
        n_obj = pf["null_obj"]
        head_obj = bpy.data.objects.get(n_obj.get("af_rw_pylon_head_obj", ""))
        if head_obj:
            head_obj.location = pf["pos"]
            head_obj.rotation_mode = "XYZ"
            head_obj.rotation_euler = (0.0, 0.0, pf["yaw_rad"])
            # Keep head_obj at 1:1 scale so downward tower height is exact in world meters!
            head_obj.scale = (1.0, 1.0, 1.0)

        # Pitch & align the left/right sheave roller batteries along the cable slope
        half_g = pf["half_gauge"]
        for side_key, x_sign in (("af_rw_rollers_out_obj", +1.0), ("af_rw_rollers_ret_obj", -1.0)):
            r_obj = bpy.data.objects.get(n_obj.get(side_key, ""))
            if r_obj:
                r_obj.location = (x_sign * half_g, 0.0, 0.0)
                r_obj.rotation_mode = "XYZ"
                r_obj.rotation_euler = (pf["pitch_rad"], 0.0, 0.0)
                r_obj.scale = (pulley_scale, pulley_scale, pulley_scale)

        # Turnaround bullwheel on end stations (i == 0 and i == n_pylons - 1)
        bull_obj = bpy.data.objects.get(n_obj.get("af_rw_bullwheel_obj", ""))
        if bull_obj:
            is_terminal = (pf["index"] == 0 or pf["index"] == n_pylons - 1)
            bull_obj.hide_viewport = not (show_bull and is_terminal)
            bull_obj.hide_render = not (show_bull and is_terminal)
            if show_bull and is_terminal:
                bull_angle = travel_dist / max(0.3, pf["half_gauge"])
                bull_obj.location = (0.0, 0.0, -0.04)
                bull_obj.rotation_mode = "XYZ"
                bull_obj.rotation_euler = (0.0, 0.0, bull_angle)
                bull_obj.scale = (1.0, 1.0, pulley_scale)

    # 3. Update All Gondola Carriages (`GONDOLA_Car_<tag>_*`)
    gondola_objs = get_system_gondola_objects(sys_root)
    for g_state in state["gondola_states"]:
        k = g_state["index"]
        if k >= len(gondola_objs):
            continue
        g_obj = gondola_objs[k]
        g_obj.location = g_state["location"]
        g_obj.rotation_mode = "XYZ"
        g_obj.rotation_euler = g_state["rotation_euler"]
        g_sc = float(g_obj.get("af_rw_scale", 1.0))
        g_obj.scale = (g_sc, g_sc, g_sc)
        g_obj["af_rw_current_sag_dz_m"] = g_state["sag_dz_m"]

    sys_root["af_rw_total_loop_length_m"] = state["total_loop_length_m"]
    sys_root["af_rw_max_sag_m"] = state["max_sag_m"]
    sys_root["af_rw_stat_loop_length_m"] = state["total_loop_length_m"]
    sys_root["af_rw_stat_max_sag_m"] = state["max_sag_m"]
    return state


# ============================================================================
# 4. SYSTEM, NULL POINT & GONDOLA BUILDERS / MUTATORS
# ============================================================================

def get_active_null_point_object(context=None, sys_root: bpy.types.Object = None) -> bpy.types.Object:
    """Returns the currently active Pylon Null point object (`GIZMO_RW_*_Null_*`), or the first Null point of `sys_root`."""
    ctx = context or bpy.context
    active = getattr(ctx, "active_object", None)
    if active and active.get("af_is_rw_null_point"):
        if sys_root is None or active.get("af_rw_tag") == sys_root.get("af_rw_tag"):
            return active
    sys_r = sys_root or get_active_ropeway_system(ctx)
    if not sys_r:
        return None
    nulls = get_system_null_point_objects(sys_r)
    if not nulls:
        return None
    saved_name = sys_r.get("af_rw_active_null_name", "")
    if saved_name:
        cand = bpy.data.objects.get(saved_name)
        if cand in nulls:
            return cand
    return nulls[0]


def get_null_tower_height_m(sys_root: bpy.types.Object, null_obj: bpy.types.Object) -> float:
    """Returns the dynamic downward pylon height (in meters) from `null_obj` down to the tower base."""
    if null_obj is not None:
        if "af_rw_null_tower_height_m" in null_obj:
            return max(0.5, float(null_obj["af_rw_null_tower_height_m"]))
        if "af_rw_tower_height_m" in null_obj:
            return max(0.5, float(null_obj["af_rw_tower_height_m"]))
    if sys_root is not None and "af_rw_tower_height_m" in sys_root:
        return max(0.5, float(sys_root["af_rw_tower_height_m"]))
    return 14.5


def get_null_support_mode(sys_root: bpy.types.Object, null_obj: bpy.types.Object) -> str:
    """Returns the support mode (`PYLON_TOWER`, `CLIFF_WALL_BRACKET`, `CEILING_HANGER`, `PULLEY_ONLY`) for `null_obj`."""
    valid = {m[0] for m in TOWER_SUPPORT_MODES}
    if null_obj is not None:
        m_null = null_obj.get("af_rw_null_support_mode", "")
        if m_null in valid:
            return m_null
    if sys_root is not None:
        m_sys = sys_root.get("af_rw_tower_support_mode", "PYLON_TOWER")
        if m_sys in valid:
            return m_sys
    return "PYLON_TOWER"


def _rebuild_pylon_hardware_for_null(sys_root: bpy.types.Object, null_obj: bpy.types.Object, sys_col: bpy.types.Collection = None):
    """
    Creates or dynamically updates in-place the Pylon Cross-Arm & Downward Support Tower (`PYLON_Head_*`),
    Sheave Roller Batteries (`WHEEL_Rollers_*`), and Bullwheel (`WHEEL_Bull_*`) under `null_obj`.
    """
    if not sys_root or not null_obj:
        return
    if sys_col is None:
        sys_col = bpy.data.collections.get(sys_root.get("af_rw_collection", "")) or bpy.context.scene.collection

    tag = sys_root.get("af_rw_tag", "01")
    n_idx = int(null_obj.get("af_rw_null_index", 1))
    loop_gauge_m = float(sys_root.get("af_rw_loop_gauge_m", 3.40))
    support_mode = get_null_support_mode(sys_root, null_obj)
    tower_height_m = get_null_tower_height_m(sys_root, null_obj)
    num_rollers = int(sys_root.get("af_rw_rollers_per_side", 4))

    null_obj["af_rw_null_tower_height_m"] = float(tower_height_m)
    null_obj["af_rw_null_support_mode"] = support_mode
    null_obj["af_rw_null_base_z"] = float(null_obj.location.z) - float(tower_height_m)

    head_name = f"PYLON_Head_{tag}_{n_idx:02d}"
    head_obj = bpy.data.objects.get(null_obj.get("af_rw_pylon_head_obj", "")) or bpy.data.objects.get(head_name)

    # Dedicated per-null mesh datablock so in-place height changes never collide with other pylons
    dedicated_mesh_name = f"Mesh_PYLON_Head_{tag}_{n_idx:02d}"
    target_mesh = bpy.data.meshes.get(dedicated_mesh_name)
    if not target_mesh:
        target_mesh = bpy.data.meshes.new(dedicated_mesh_name)

    _build_pylon_crossarm_and_support_mesh(
        loop_gauge_m=loop_gauge_m,
        support_mode=support_mode,
        tower_height_m=tower_height_m,
        target_mesh=target_mesh,
    )

    if not head_obj:
        head_obj = bpy.data.objects.new(head_name, target_mesh)
        head_obj.location = null_obj.location.copy()
        sys_col.objects.link(head_obj)
    else:
        head_obj.name = head_name
        if head_obj.data != target_mesh:
            head_obj.data = target_mesh
        if head_obj.name not in sys_col.objects:
            try:
                sys_col.objects.link(head_obj)
            except Exception:
                pass

    head_obj["af_rw_sys_root"] = sys_root.name
    head_obj["af_rw_tag"] = tag
    head_obj["af_rw_tower_height_m"] = float(tower_height_m)
    null_obj["af_rw_pylon_head_obj"] = head_obj.name

    # Shared instanced sheave roller batteries (Outgoing right + Return left)
    roller_mesh = _build_sheave_roller_battery_mesh(num_rollers=num_rollers, roller_radius=0.24)
    half_g = 0.5 * loop_gauge_m
    for side_tag, side_key, x_off in (
        ("Out", "af_rw_rollers_out_obj", +half_g),
        ("Ret", "af_rw_rollers_ret_obj", -half_g),
    ):
        r_name = f"WHEEL_Rollers_{side_tag}_{tag}_{n_idx:02d}"
        r_obj = bpy.data.objects.get(null_obj.get(side_key, "")) or bpy.data.objects.get(r_name)
        if not r_obj:
            r_obj = bpy.data.objects.new(r_name, roller_mesh)
            r_obj.parent = head_obj
            r_obj.location = (x_off, 0.0, 0.0)
            sys_col.objects.link(r_obj)
        else:
            r_obj.name = r_name
            r_obj.parent = head_obj
            r_obj.data = roller_mesh
        r_obj["af_rw_sys_root"] = sys_root.name
        r_obj["af_rw_tag"] = tag
        null_obj[side_key] = r_obj.name

    # Shared instanced Turnaround Bullwheel
    bull_mesh = _build_turnaround_bullwheel_mesh(radius=half_g)
    bull_name = f"WHEEL_Bull_{tag}_{n_idx:02d}"
    bull_obj = bpy.data.objects.get(null_obj.get("af_rw_bullwheel_obj", "")) or bpy.data.objects.get(bull_name)
    if not bull_obj:
        bull_obj = bpy.data.objects.new(bull_name, bull_mesh)
        bull_obj.parent = head_obj
        bull_obj.location = (0.0, 0.0, -0.04)
        sys_col.objects.link(bull_obj)
    else:
        bull_obj.name = bull_name
        bull_obj.parent = head_obj
        bull_obj.data = bull_mesh
    bull_obj["af_rw_sys_root"] = sys_root.name
    bull_obj["af_rw_tag"] = tag
    null_obj["af_rw_bullwheel_obj"] = bull_obj.name


def set_null_tower_height_m(
    null_obj: bpy.types.Object,
    height_m: float = None,
    support_mode: str = None,
):
    """
    Dynamically sets the downward tower height `height_m` (from `null_obj` straight down)
    and/or `support_mode` for a single Pylon Null point and updates its 3D tower mesh in-place.
    """
    if not null_obj:
        return
    sys_root = find_ropeway_system_from_object(null_obj)
    if not sys_root:
        return
    if height_m is not None:
        h = max(0.5, min(200.0, float(height_m)))
        null_obj["af_rw_null_tower_height_m"] = h
        null_obj["af_rw_null_base_z"] = float(null_obj.location.z) - h
    if support_mode is not None:
        null_obj["af_rw_null_support_mode"] = support_mode
    sys_col = bpy.data.collections.get(sys_root.get("af_rw_collection", "")) or bpy.context.scene.collection
    _rebuild_pylon_hardware_for_null(sys_root, null_obj, sys_col)


def auto_fit_null_tower_height_to_ground(
    null_obj: bpy.types.Object,
    fallback_floor_z: float = 0.0,
    scene: bpy.types.Scene = None,
) -> float:
    """
    Raycasts straight downwards from `null_obj.location` to detect any cavern floor, rock,
    or scaffolding surface below (or uses `null_obj.location.z - fallback_floor_z` if over
    an open void), sets the Null point's tower height to reach that level, and rebuilds
    the tower downwards in-place.
    """
    if not null_obj:
        return 14.5
    scn = scene or bpy.context.scene
    sys_root = find_ropeway_system_from_object(null_obj)
    hit_z = None
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        cur_o = Vector((null_obj.location.x, null_obj.location.y, null_obj.location.z - 1.2))
        direction = Vector((0.0, 0.0, -1.0))
        for _ in range(10):
            ok, loc, _norm, _idx, obj, _mw = scn.ray_cast(depsgraph, cur_o, direction, distance=220.0)
            if not ok or not obj:
                break
            if (
                obj.get("af_rw_sys_root")
                or obj.get("af_is_rw_null_point")
                or obj.get("af_is_rw_gondola")
                or any(p in obj.name for p in ("RW_", "PYLON_", "WHEEL_", "ROPE_", "GONDOLA_", "GIZMO_RW_"))
            ):
                cur_o = loc + Vector((0.0, 0.0, -0.25))
                continue
            hit_z = float(loc.z)
            break
    except Exception:
        hit_z = None

    target_base_z = hit_z if hit_z is not None else float(fallback_floor_z)
    new_h = max(1.5, min(200.0, float(null_obj.location.z) - target_base_z))
    set_null_tower_height_m(null_obj, height_m=new_h, support_mode="PYLON_TOWER")
    if sys_root:
        sys_root["af_rw_tower_height_m"] = new_h
    return new_h


def _fit_elf_rider_inside_gondola(ctrl_elf: bpy.types.Object, gondola_obj: bpy.types.Object, cur_var: str):
    """
    Positions and scales `ctrl_elf` inside `gondola_obj` by measuring the actual 3D vertex bounds
    of the Elf character (including boots and hat) in `ctrl_elf` space so that:
      - In `GONDOLA_PASSENGER`: boots stand directly on the lower wooden floor (`Z = -2.68 m`)
        and the top of the head/hat reaches `Z = -1.66 m` (cleanly visible inside the open
        carriage window beneath the `Z = -1.52 m` arched roof eaves).
      - In `GONDOLA_CARGO`: boots stand at `Z = -1.62 m` and top reaches `Z = -0.68 m`.
    """
    if not ctrl_elf or not gondola_obj:
        return
    ctrl_elf.parent = gondola_obj
    ctrl_elf.matrix_parent_inverse = Matrix.Identity(4)
    ctrl_elf.location = (0.0, 0.0, 0.0)
    ctrl_elf.rotation_mode = "XYZ"
    ctrl_elf.rotation_euler = (0.0, 0.0, 0.0)
    ctrl_elf.scale = (1.0, 1.0, 1.0)
    try:
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
    except Exception:
        depsgraph = None

    inv_ctrl = ctrl_elf.matrix_world.inverted_safe()
    z_vals = []
    for ch in ctrl_elf.children_recursive:
        if ch.type == "MESH" and not ch.hide_render and ch.data and len(ch.data.vertices) > 0:
            ch_eval = ch.evaluated_get(depsgraph) if depsgraph else ch
            mat_rel = inv_ctrl @ ch_eval.matrix_world
            bb = getattr(ch_eval, "bound_box", None)
            if bb:
                for corner in bb:
                    z_vals.append((mat_rel @ Vector(corner)).z)
            else:
                for v in ch.data.vertices:
                    z_vals.append((mat_rel @ v.co).z)

    if z_vals:
        raw_min_z = min(z_vals)
        raw_max_z = max(z_vals)
        raw_h = max(0.25, raw_max_z - raw_min_z)
    else:
        raw_min_z = 0.0
        raw_h = 2.35

    if cur_var == "GONDOLA_PASSENGER":
        target_feet_z = -2.68
        target_height = 1.02  # Boots at -2.68 m, hat tip at -1.66 m (well below -1.52 m roof arch!)
    else:
        target_feet_z = -1.62
        target_height = 0.94

    s = target_height / raw_h
    ctrl_elf.scale = (s, s, s)
    ctrl_elf.location = (0.0, 0.0, target_feet_z - raw_min_z * s)


def set_individual_gondola_configuration(
    gondola_obj: bpy.types.Object,
    variant_id: str = None,
    cargo_type: str = None,
    elf_id: str = None,
    weight_factor: float = None,
    scale: float = None,
):
    """
    Configures an individual Gondola carriage:
      - `variant_id`: `'GONDOLA_CARGO'` (Teretna) or `'GONDOLA_PASSENGER'` (Putnička)
      - `cargo_type`: `'ICE_CRYSTALS'` | `'CRATE_TOOLS'` | `'BARREL_LANTERN'` | `'NONE'`
      - `elf_id`: `'NONE'` | `'ELF06'` | `'ELF10'` | `'ELF14'` | `'ELF16'` | `'ELF21'` | `'ELF23'` | `'ELF28'`
      - `weight_factor`: dynamic cable load depression multiplier ($w_k$)
      - `scale`: uniform 3D scale of the gondola
    """
    if not gondola_obj:
        return
    sys_root = find_ropeway_system_from_object(gondola_obj)
    low_poly_proxy = bool(sys_root.get("af_rw_low_poly_mode", False)) if sys_root else False
    sys_col = gondola_obj.users_collection[0] if gondola_obj.users_collection else bpy.context.scene.collection

    if variant_id is not None:
        gondola_obj["af_rw_gondola_variant"] = variant_id
    cur_var = gondola_obj.get("af_rw_gondola_variant", "GONDOLA_CARGO")

    # Swap to shared instanced mesh datablock (`TPL_RW_TripoMesh_*` or `TPL_RW_Mesh_*_LOD1`)
    gondola_obj.data = _load_or_build_gondola_mesh(cur_var, low_poly_proxy=low_poly_proxy)

    if cargo_type is not None:
        gondola_obj["af_rw_cargo_type"] = cargo_type
    cur_cargo = gondola_obj.get("af_rw_cargo_type", "ICE_CRYSTALS" if cur_var == "GONDOLA_CARGO" else "NONE")

    # Manage optional cargo insert child object
    old_cargo_name = gondola_obj.get("af_rw_cargo_child_obj", "")
    if old_cargo_name and old_cargo_name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[old_cargo_name], do_unlink=True)
    gondola_obj["af_rw_cargo_child_obj"] = ""

    # Notice: `GONDOLA_CARGO` already has glowing blue ice crystals sculpted into its top rim;
    # if the user puts `ICE_CRYSTALS`, `CRATE_TOOLS`, or `BARREL_LANTERN` into a `GONDOLA_PASSENGER`
    # (or extra crate/barrel on `GONDOLA_CARGO`), we attach the lightweight instanced cargo insert!
    need_insert = (
        (cur_var == "GONDOLA_PASSENGER" and cur_cargo != "NONE")
        or (cur_var == "GONDOLA_CARGO" and cur_cargo in ("CRATE_TOOLS", "BARREL_LANTERN"))
    )
    if need_insert:
        c_mesh = _load_or_build_cargo_insert_mesh(cur_cargo)
        if c_mesh:
            c_obj = bpy.data.objects.new(f"CARGO_In_{gondola_obj.name}", c_mesh)
            c_obj.parent = gondola_obj
            c_obj.location = (0.0, 0.0, -2.38 if cur_var == "GONDOLA_PASSENGER" else -1.42)
            c_obj["af_rw_sys_root"] = sys_root.name if sys_root else ""
            sys_col.objects.link(c_obj)
            gondola_obj["af_rw_cargo_child_obj"] = c_obj.name

    # Manage optional Rigged Elf rider inside the gondola
    if elf_id is not None:
        old_elf_name = gondola_obj.get("af_rw_elf_ctrl_obj", "")
        old_elf_id = gondola_obj.get("af_rw_elf_id", "NONE")
        old_ctrl_exists = bool(old_elf_name and old_elf_name in bpy.data.objects)
        if old_elf_id != elf_id or (elf_id != "NONE" and not old_ctrl_exists):
            if old_ctrl_exists:
                old_ctrl = bpy.data.objects[old_elf_name]
                for ch in list(old_ctrl.children_recursive):
                    if ch.name in bpy.data.objects:
                        bpy.data.objects.remove(ch, do_unlink=True)
                bpy.data.objects.remove(old_ctrl, do_unlink=True)
            gondola_obj["af_rw_elf_ctrl_obj"] = ""
            gondola_obj["af_rw_elf_id"] = elf_id

            if elf_id and elf_id != "NONE":
                try:
                    ctrl_elf = spawn_elf_actor(
                        bpy.context,
                        elf_id=elf_id,
                        location=(0.0, 0.0, 0.0),
                    )
                    if ctrl_elf:
                        for c in list(ctrl_elf.users_collection):
                            c.objects.unlink(ctrl_elf)
                        sys_col.objects.link(ctrl_elf)
                        for ch in ctrl_elf.children_recursive:
                            for c in list(ch.users_collection):
                                c.objects.unlink(ch)
                            sys_col.objects.link(ch)

                        _fit_elf_rider_inside_gondola(ctrl_elf, gondola_obj, cur_var)
                        ctrl_elf["af_rw_sys_root"] = sys_root.name if sys_root else ""

                        rider_specs = [
                            {"action": "AF_28_Wave_Hello", "repeat": 2.0, "speed": 1.0, "blend": 8, "mode": "FIXED"},
                            {"action": "AF_06_Idle_Breathing", "repeat": 6.0, "speed": 1.0, "blend": 10, "mode": "FIXED"},
                        ]
                        rebuild_nla_sequence_from_specs(ctrl_elf, rider_specs, sync_curve=False)
                        _fit_elf_rider_inside_gondola(ctrl_elf, gondola_obj, cur_var)
                        gondola_obj["af_rw_elf_ctrl_obj"] = ctrl_elf.name
                except Exception as exc:
                    print(f"[RopewayGondolas] Elf rider spawn warning: {exc}")

    # Always ensure any existing Elf rider sits on the interior floor at the proper cabin scale
    cur_elf_ctrl_name = gondola_obj.get("af_rw_elf_ctrl_obj", "")
    if cur_elf_ctrl_name and cur_elf_ctrl_name in bpy.data.objects:
        cur_elf_ctrl = bpy.data.objects[cur_elf_ctrl_name]
        _fit_elf_rider_inside_gondola(cur_elf_ctrl, gondola_obj, cur_var)

    # Weight & Scale
    if weight_factor is not None:
        gondola_obj["af_rw_weight_factor"] = float(weight_factor)
    elif "af_rw_weight_factor" not in gondola_obj:
        has_elf = bool(gondola_obj.get("af_rw_elf_id", "NONE") != "NONE")
        if cur_var == "GONDOLA_CARGO":
            gondola_obj["af_rw_weight_factor"] = 1.35 if cur_cargo != "NONE" else 0.75
        else:
            gondola_obj["af_rw_weight_factor"] = 1.15 if has_elf else 0.70

    if scale is not None:
        gondola_obj["af_rw_scale"] = float(scale)
    elif "af_rw_scale" not in gondola_obj:
        gondola_obj["af_rw_scale"] = 1.0


def sync_ropeway_gondola_fleet(
    sys_root: bpy.types.Object,
    target_count: int = None,
    distribution_mode: str = None,
    spawn_elves_in_passenger: bool = True,
):
    """
    Synchronizes the total number of Gondolas (`af_rw_gondola_count`) on `sys_root`,
    spawning or removing instanced gondola carriages and applying the chosen distribution
    pattern (`MIXED_75_CARGO_25_ELF`, `ALL_CARGO`, `ALTERNATING`, `ALL_PASSENGER`, or `CUSTOM`).
    """
    if not sys_root:
        return []
    tag = sys_root.get("af_rw_tag", "01")
    if target_count is not None:
        sys_root["af_rw_gondola_count"] = max(1, int(target_count))
    count = max(1, int(sys_root.get("af_rw_gondola_count", 12)))

    if distribution_mode is not None:
        sys_root["af_rw_distribution_mode"] = distribution_mode
    dist_mode = sys_root.get("af_rw_distribution_mode", "MIXED_75_CARGO_25_ELF")

    sys_col = bpy.data.collections.get(sys_root.get("af_rw_collection", "")) or bpy.context.scene.collection
    existing = get_system_gondola_objects(sys_root)

    # Remove excess gondolas if count decreased
    while len(existing) > count:
        rem = existing.pop()
        for ch in list(rem.children_recursive):
            if ch.name in bpy.data.objects:
                bpy.data.objects.remove(ch, do_unlink=True)
        if rem.name in bpy.data.objects:
            bpy.data.objects.remove(rem, do_unlink=True)

    # Spawn new gondolas if count increased
    low_poly_proxy = bool(sys_root.get("af_rw_low_poly_mode", False))
    base_mesh = _load_or_build_gondola_mesh("GONDOLA_CARGO", low_poly_proxy=low_poly_proxy)
    while len(existing) < count:
        new_idx = len(existing) + 1
        g_obj = bpy.data.objects.new(f"GONDOLA_Car_{tag}_{new_idx:02d}", base_mesh)
        g_obj["af_is_rw_gondola"] = True
        g_obj["af_rw_tag"] = tag
        g_obj["af_rw_sys_root"] = sys_root.name
        g_obj["af_rw_gondola_index"] = new_idx
        g_obj["af_rw_phase_offset"] = 0.0
        g_obj["af_rw_scale"] = 1.0
        sys_col.objects.link(g_obj)
        existing.append(g_obj)

    # Apply distribution pattern (unless CUSTOM)
    elf_pool = ("ELF14", "ELF10", "ELF21", "ELF06", "ELF23", "ELF16", "ELF28")
    if dist_mode != "CUSTOM":
        for idx, g_obj in enumerate(existing):
            if dist_mode == "ALL_CARGO":
                var_id = "GONDOLA_CARGO"
                c_type = "ICE_CRYSTALS"
                e_id = "NONE"
                w_fac = 1.35
            elif dist_mode == "ALL_PASSENGER":
                var_id = "GONDOLA_PASSENGER"
                c_type = "NONE"
                e_id = elf_pool[idx % len(elf_pool)] if (spawn_elves_in_passenger and idx % 2 == 0) else "NONE"
                w_fac = 1.15 if e_id != "NONE" else 0.70
            elif dist_mode == "ALTERNATING":
                is_pass = (idx % 2 == 1)
                var_id = "GONDOLA_PASSENGER" if is_pass else "GONDOLA_CARGO"
                c_type = "NONE" if is_pass else "ICE_CRYSTALS"
                e_id = elf_pool[(idx // 2) % len(elf_pool)] if (is_pass and spawn_elves_in_passenger and (idx // 2) % 2 == 0) else "NONE"
                w_fac = (1.15 if e_id != "NONE" else 0.72) if is_pass else 1.35
            else:
                # Default: MIXED_75_CARGO_25_ELF ("uglavnom prevoze stvari, tu i tam bude nekakvi vilenjak")
                is_pass = (idx % 4 == 3)
                var_id = "GONDOLA_PASSENGER" if is_pass else "GONDOLA_CARGO"
                if is_pass:
                    c_type = "NONE"
                    # Put a rigged Elf rider in every passenger gondola (up to 3 per line for ultra-fast playback)
                    pass_num = idx // 4
                    e_id = elf_pool[pass_num % len(elf_pool)] if (spawn_elves_in_passenger and pass_num < 3) else "NONE"
                    w_fac = 1.18 if e_id != "NONE" else 0.75
                else:
                    c_type = "ICE_CRYSTALS" if idx % 3 != 2 else "CRATE_TOOLS"
                    e_id = "NONE"
                    w_fac = 1.38 if c_type == "ICE_CRYSTALS" else 1.20

            set_individual_gondola_configuration(
                g_obj,
                variant_id=var_id,
                cargo_type=c_type,
                elf_id=e_id,
                weight_factor=w_fac,
            )

    return existing


def spawn_ropeway_system(
    context=None,
    null_points: list = None,
    label: str = "",
    gondola_count: int = 12,
    loop_gauge_m: float = 3.40,
    speed_mps: float = 2.40,
    base_sag_m: float = 1.45,
    load_sink_m: float = 0.95,
    tower_support_mode: str = "PYLON_TOWER",
    tower_height_m: float = 14.0,
    distribution_mode: str = "MIXED_75_CARGO_25_ELF",
    spawn_elves_in_passenger: bool = True,
) -> bpy.types.Object:
    """
    Spawns a complete, closed-loop Aerial Ropeway / Ski-Gondola System (`RW_SYS_<tag>`)
    with interactive Pylon Null points (`GIZMO_RW_<tag>_Null_01..N`), rotating pulley sheaves,
    turnaround bullwheels, dynamic catenary + point-load sagging cable (`ROPE_Loop_<tag>`),
    and `gondola_count` instanced Cargo & Passenger Gondolas.
    """
    ctx = context or bpy.context
    scn = ctx.scene

    master_col = ensure_collection(ROPEWAY_MASTER_COLLECTION, scn.collection)
    existing_sys = get_all_ropeway_systems(scn)
    used_tags = {s.get("af_rw_tag", "") for s in existing_sys}
    idx_num = 1
    while f"{idx_num:02d}" in used_tags:
        idx_num += 1
    tag = f"{idx_num:02d}"

    sys_col_name = f"RW_{tag}_Sustav_Zicare"
    sys_col = ensure_collection(sys_col_name, master_col)

    if not null_points or len(null_points) < 2:
        # Default trajectory: from Right-Hand Glacier Wall (X=+14 m) across the chasm to the Left / Distant City (X=-75 m, +Y)
        y_base = 115.0 + (idx_num - 1) * 75.0
        z_base = 14.5 + (idx_num - 1) * 6.0
        null_points = [
            ( 13.5, y_base,        z_base),
            (-12.0, y_base + 32.0, z_base + 3.5),
            (-42.0, y_base + 68.0, z_base + 7.0),
            (-78.0, y_base + 110.0, z_base + 11.0),
        ]

    # 1. Create System Root Empty (`RW_SYS_<tag>`)
    sys_root = bpy.data.objects.new(f"RW_SYS_{tag}", None)
    sys_root.empty_display_type = "SPHERE"
    sys_root.empty_display_size = 0.8
    sys_root.location = Vector(null_points[0])
    sys_root["af_is_ropeway_system"] = True
    sys_root["af_rw_tag"] = tag
    sys_root["af_rw_label"] = label or f"Žičara {tag} (Ledeni Zid -> Prema Gradu Lijevo)"
    sys_root["af_rw_collection"] = sys_col.name
    sys_root["af_rw_gondola_count"] = int(gondola_count)
    sys_root["af_rw_loop_gauge_m"] = float(loop_gauge_m)
    sys_root["af_rw_speed_mps"] = float(speed_mps)
    sys_root["af_rw_base_sag_m"] = float(base_sag_m)
    sys_root["af_rw_load_sink_m"] = float(load_sink_m)
    sys_root["af_rw_sway_amp_deg"] = 4.5
    sys_root["af_rw_ref_span_m"] = 45.0
    sys_root["af_rw_pulley_scale"] = 1.0
    sys_root["af_rw_rollers_per_side"] = 4
    sys_root["af_rw_show_turnaround_wheels"] = True
    sys_root["af_rw_tower_support_mode"] = tower_support_mode
    sys_root["af_rw_tower_height_m"] = float(tower_height_m)
    sys_root["af_rw_distribution_mode"] = distribution_mode
    sys_root["af_rw_low_poly_mode"] = False
    sys_col.objects.link(sys_root)

    # 2. Create Closed-Loop Haul Cable Curve (`ROPE_Loop_<tag>`)
    pal = _ensure_rw_palette()
    cu = bpy.data.curves.new(f"Curve_ROPE_Loop_{tag}", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.032
    cu.bevel_resolution = 2
    cu.materials.append(pal["cable"])
    rope_obj = bpy.data.objects.new(f"ROPE_Loop_{tag}", cu)
    rope_obj["af_rw_sys_root"] = sys_root.name
    rope_obj["af_rw_tag"] = tag
    sys_col.objects.link(rope_obj)
    sys_root["af_rw_rope_obj"] = rope_obj.name

    # 3. Create Interactive Pylon Null Points (`GIZMO_RW_<tag>_Null_01..N`)
    gizmo_mesh = _build_null_point_gizmo_mesh()
    for i, pt in enumerate(null_points):
        n_idx = i + 1
        null_obj = bpy.data.objects.new(f"GIZMO_RW_{tag}_Null_{n_idx:02d}", gizmo_mesh)
        null_obj.location = Vector(pt)
        null_obj.show_in_front = True
        null_obj["af_is_rw_null_point"] = True
        null_obj["af_rw_tag"] = tag
        null_obj["af_rw_sys_root"] = sys_root.name
        null_obj["af_rw_null_index"] = n_idx
        null_obj["af_rw_null_tower_height_m"] = float(tower_height_m)
        null_obj["af_rw_null_support_mode"] = tower_support_mode
        null_obj["af_rw_null_base_z"] = float(null_obj.location.z) - float(tower_height_m)
        sys_col.objects.link(null_obj)
        _rebuild_pylon_hardware_for_null(sys_root, null_obj, sys_col)

    # 4. Spawn Gondola Fleet along the closed loop
    sync_ropeway_gondola_fleet(
        sys_root,
        target_count=gondola_count,
        distribution_mode=distribution_mode,
        spawn_elves_in_passenger=spawn_elves_in_passenger,
    )

    # 5. Evaluate initial mathematical catenary + point-load sag state
    apply_ropeway_evaluation_to_system(sys_root, frame=float(scn.frame_current), scene=scn)
    scn.af_rw_active_system_name = sys_root.name
    register_ropeway_gondola_handlers()
    return sys_root


def add_null_point_to_ropeway_system(
    sys_root: bpy.types.Object,
    after_null_obj: bpy.types.Object = None,
    location: tuple = None,
) -> bpy.types.Object:
    """
    Inserts a new Pylon Null point (`GIZMO_RW_<tag>_Null_*`) into `sys_root`,
    re-indexes the Null point chain, builds its Pylon Cross-Arm & Sheave Pulley
    Assembly, and immediately updates the dynamic catenary cable sag and gondolas.
    """
    if not sys_root:
        return None
    tag = sys_root.get("af_rw_tag", "01")
    sys_col = bpy.data.collections.get(sys_root.get("af_rw_collection", "")) or bpy.context.scene.collection
    nulls = get_system_null_point_objects(sys_root)
    if not nulls:
        return None

    inherit_h = float(sys_root.get("af_rw_tower_height_m", 14.5))
    inherit_mode = sys_root.get("af_rw_tower_support_mode", "PYLON_TOWER")

    if location is not None:
        new_pos = Vector(location)
        insert_pos = len(nulls)
        if after_null_obj and after_null_obj in nulls:
            inherit_h = get_null_tower_height_m(sys_root, after_null_obj)
            inherit_mode = get_null_support_mode(sys_root, after_null_obj)
    elif after_null_obj and after_null_obj in nulls:
        inherit_h = get_null_tower_height_m(sys_root, after_null_obj)
        inherit_mode = get_null_support_mode(sys_root, after_null_obj)
        idx = nulls.index(after_null_obj)
        if idx < len(nulls) - 1:
            # Insert midway between `nulls[idx]` and `nulls[idx + 1]`
            new_pos = 0.5 * (nulls[idx].location + nulls[idx + 1].location)
            inherit_h = 0.5 * (
                get_null_tower_height_m(sys_root, nulls[idx])
                + get_null_tower_height_m(sys_root, nulls[idx + 1])
            )
            insert_pos = idx + 1
        else:
            # Extend beyond the last Null point along the outgoing trajectory toward the city (-X, +Y)
            if len(nulls) >= 2:
                step = nulls[-1].location - nulls[-2].location
                if step.length < 5.0:
                    step = Vector((-28.0, 32.0, 2.5))
            else:
                step = Vector((-28.0, 32.0, 2.5))
            new_pos = nulls[-1].location + step * 0.85
            insert_pos = len(nulls)
    else:
        step = (nulls[-1].location - nulls[-2].location) if len(nulls) >= 2 else Vector((-28.0, 32.0, 2.5))
        new_pos = nulls[-1].location + step * 0.85
        inherit_h = get_null_tower_height_m(sys_root, nulls[-1])
        inherit_mode = get_null_support_mode(sys_root, nulls[-1])
        insert_pos = len(nulls)

    gizmo_mesh = _build_null_point_gizmo_mesh()
    new_null = bpy.data.objects.new(f"GIZMO_RW_{tag}_Null_NEW", gizmo_mesh)
    new_null.location = new_pos
    new_null.show_in_front = True
    new_null["af_is_rw_null_point"] = True
    new_null["af_rw_tag"] = tag
    new_null["af_rw_sys_root"] = sys_root.name
    new_null["af_rw_null_tower_height_m"] = float(inherit_h)
    new_null["af_rw_null_support_mode"] = inherit_mode
    new_null["af_rw_null_base_z"] = float(new_pos.z) - float(inherit_h)
    sys_col.objects.link(new_null)

    nulls.insert(insert_pos, new_null)
    for i, n_obj in enumerate(nulls):
        n_idx = i + 1
        n_obj["af_rw_null_index"] = n_idx
        n_obj.name = f"GIZMO_RW_{tag}_Null_{n_idx:02d}"

    rebuild_all_pylons_for_system(sys_root)
    return new_null


def remove_null_point_from_ropeway_system(
    sys_root: bpy.types.Object,
    target_null_obj: bpy.types.Object = None,
) -> bool:
    """
    Removes `target_null_obj` (or the last Null point) from `sys_root`
    (keeping at least 2 Null points so the closed loop remains valid),
    cleans up its pylon/pulley objects, re-indexes remaining Null points,
    and updates the dynamic catenary cable sag and gondolas.
    """
    if not sys_root:
        return False
    nulls = get_system_null_point_objects(sys_root)
    if len(nulls) <= 2:
        return False

    rem_null = target_null_obj if (target_null_obj in nulls) else nulls[-1]
    for key in ("af_rw_pylon_head_obj", "af_rw_rollers_out_obj", "af_rw_rollers_ret_obj", "af_rw_bullwheel_obj"):
        h_name = rem_null.get(key, "")
        if h_name and h_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[h_name], do_unlink=True)

    nulls.remove(rem_null)
    bpy.data.objects.remove(rem_null, do_unlink=True)

    tag = sys_root.get("af_rw_tag", "01")
    for i, n_obj in enumerate(nulls):
        n_idx = i + 1
        n_obj["af_rw_null_index"] = n_idx
        n_obj.name = f"GIZMO_RW_{tag}_Null_{n_idx:02d}"

    rebuild_all_pylons_for_system(sys_root)
    return True


def rebuild_all_pylons_for_system(sys_root: bpy.types.Object):
    """Rebuilds the Pylon Cross-Arms, Sheave Roller Batteries, and Support Towers for all Null points of `sys_root`."""
    if not sys_root:
        return
    sys_col = bpy.data.collections.get(sys_root.get("af_rw_collection", "")) or bpy.context.scene.collection
    for n_obj in get_system_null_point_objects(sys_root):
        _rebuild_pylon_hardware_for_null(sys_root, n_obj, sys_col)
    apply_ropeway_evaluation_to_system(sys_root)


def delete_ropeway_system(sys_root: bpy.types.Object):
    """Deletes an entire Ropeway System and its sub-collection cleanly."""
    if not sys_root:
        return
    col_name = sys_root.get("af_rw_collection", "")
    col = bpy.data.collections.get(col_name)
    if col:
        for o in list(col.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(col)
    elif sys_root.name in bpy.data.objects:
        bpy.data.objects.remove(sys_root, do_unlink=True)


def reload_all_tripo_gondola_models_in_scene(context=None) -> int:
    """Safely reloads cached template gondola meshes without deleting any gondola objects using them."""
    old_meshes = []
    for m in list(bpy.data.meshes):
        if m.name.startswith("TPL_RW_TripoMesh_"):
            m.name = f"_OLD_{m.name}"
            old_meshes.append(m)

    scn = (context.scene if context else bpy.context.scene)
    systems = get_all_ropeway_systems(scn)
    for sys_root in systems:
        low_poly_proxy = bool(sys_root.get("af_rw_low_poly_mode", False))
        for g_obj in get_system_gondola_objects(sys_root):
            var_id = g_obj.get("af_rw_gondola_variant", "GONDOLA_CARGO")
            g_obj.data = _load_or_build_gondola_mesh(var_id, low_poly_proxy=low_poly_proxy)
            cur_elf_ctrl_name = g_obj.get("af_rw_elf_ctrl_obj", "")
            if cur_elf_ctrl_name and cur_elf_ctrl_name in bpy.data.objects:
                cur_elf_ctrl = bpy.data.objects[cur_elf_ctrl_name]
                _fit_elf_rider_inside_gondola(cur_elf_ctrl, g_obj, var_id)
        apply_ropeway_evaluation_to_system(sys_root, scene=scn)

    for m in old_meshes:
        if m.name in bpy.data.meshes and m.users == 0:
            bpy.data.meshes.remove(m, do_unlink=True)
    return len(systems)


def populate_cavern_multi_ropeway_network(context=None) -> list:
    """
    1-Click Production Network Generator:
    Spawns 3 multi-span Aerial Ropeway Systems across the S3 Underground Cavern,
    transporting glowing blue ice crystals from the Right-Hand Glacier Wall (`X = +12..+18 m`)
    over the Viaduct and deep chasm toward the Left / Distant Underground City (`X = -85..-145 m, +Y`):
      1. `Žičara 01 (Skela R2 -> Kroz Klanac -> Prema Gradu Lijevo)`: 4 Pylon Null stations, 12 Gondolas
      2. `Žičara 02 (Skela R3 -> Iznad Vijadukta -> Prema Gradu Lijevo)`: 4 Pylon Null stations, 14 Gondolas
      3. `Žičara 03 (Skela R4 Dizalo -> Visoka Dijagonala -> Prema Gradu u Daljinu)`: 5 Pylon Null stations, 16 Gondolas
    """
    ctx = context or bpy.context
    scn = ctx.scene

    # Clean up any existing ropeway systems before building the fresh multi-line network
    for old_sys in list(get_all_ropeway_systems(scn)):
        delete_ropeway_system(old_sys)

    network_specs = [
        {
            "label": "Žičara 01 (Skela R2 Ledeni Zid -> Prema Gradu Lijevo)",
            "null_points": [
                ( 13.5, 118.0, 12.5),
                ( -8.0, 145.0, 14.5),
                (-38.0, 178.0, 17.5),
                (-76.0, 215.0, 21.0),
            ],
            "gondola_count": 12,
            "loop_gauge_m": 3.40,
            "speed_mps": 2.45,
            "base_sag_m": 1.35,
            "load_sink_m": 0.92,
            "tower_support_mode": "PYLON_TOWER",
            "tower_height_m": 14.5,
            "distribution_mode": "MIXED_75_CARGO_25_ELF",
        },
        {
            "label": "Žičara 02 (Skela R3 Duga Galerija -> Prema Gradu Lijevo)",
            "null_points": [
                ( 14.2, 188.0, 16.5),
                (-10.5, 222.0, 19.0),
                (-46.0, 262.0, 22.5),
                (-92.0, 310.0, 26.5),
            ],
            "gondola_count": 14,
            "loop_gauge_m": 3.50,
            "speed_mps": 2.65,
            "base_sag_m": 1.50,
            "load_sink_m": 1.05,
            "tower_support_mode": "PYLON_TOWER",
            "tower_height_m": 18.0,
            "distribution_mode": "MIXED_75_CARGO_25_ELF",
        },
        {
            "label": "Žičara 03 (Skela R4 Visoka Linija -> Daleko Lijevo Prema Gradu)",
            "null_points": [
                (  14.8, 262.0, 24.5),
                (  -8.0, 298.0, 27.0),
                ( -42.0, 340.0, 30.0),
                ( -84.0, 385.0, 33.5),
                (-130.0, 435.0, 37.0),
            ],
            "gondola_count": 16,
            "loop_gauge_m": 3.60,
            "speed_mps": 2.85,
            "base_sag_m": 1.65,
            "load_sink_m": 1.10,
            "tower_support_mode": "PYLON_TOWER",
            "tower_height_m": 22.0,
            "distribution_mode": "MIXED_75_CARGO_25_ELF",
        },
    ]

    spawned = []
    for spec in network_specs:
        sys_root = spawn_ropeway_system(
            context=ctx,
            null_points=spec["null_points"],
            label=spec["label"],
            gondola_count=spec["gondola_count"],
            loop_gauge_m=spec["loop_gauge_m"],
            speed_mps=spec["speed_mps"],
            base_sag_m=spec["base_sag_m"],
            load_sink_m=spec["load_sink_m"],
            tower_support_mode=spec["tower_support_mode"],
            tower_height_m=spec["tower_height_m"],
            distribution_mode=spec["distribution_mode"],
            spawn_elves_in_passenger=True,
        )
        spawned.append(sys_root)

    if spawned:
        scn.af_rw_active_system_name = spawned[0].name
    return spawned


# ============================================================================
# 5. PERSISTENT FRAME-CHANGE & VIEWPORT GIZMO DRAG HANDLERS
# ============================================================================

@persistent
def af_ropeway_frame_change_handler(scene, depsgraph=None):
    global _RW_EVAL_GUARD
    if _RW_EVAL_GUARD:
        return
    _RW_EVAL_GUARD = True
    try:
        f_cur = float(scene.frame_current)
        for sys_root in get_all_ropeway_systems(scene):
            apply_ropeway_evaluation_to_system(sys_root, frame=f_cur, scene=scene)
    except Exception:
        pass
    finally:
        _RW_EVAL_GUARD = False


@persistent
def af_ropeway_depsgraph_update_handler(scene, depsgraph=None):
    """
    Detects when the user manually moves any `GIZMO_RW_*_Null_*` Empty point in the 3D Viewport
    with `G` (or changes its downward tower height / support mode) and immediately recalculates
    the dynamic downward pylon tower mesh, cross-arm orientation, dynamic catenary sag,
    and gondola positions in real time!
    """
    global _RW_EVAL_GUARD, _NULL_POS_CACHE
    if _RW_EVAL_GUARD:
        return

    dirty_systems = set()
    dirty_nulls = []

    for sys_root in get_all_ropeway_systems(scene):
        auto_base_z = bool(sys_root.get("af_rw_auto_height_from_base_z", False))
        for n_obj in get_system_null_point_objects(sys_root):
            key = n_obj.name
            cur_loc = (round(n_obj.location.x, 4), round(n_obj.location.y, 4), round(n_obj.location.z, 4))
            cur_h = round(get_null_tower_height_m(sys_root, n_obj), 3)
            cur_mode = get_null_support_mode(sys_root, n_obj)
            prev = _NULL_POS_CACHE.get(key)

            if prev is None:
                _NULL_POS_CACHE[key] = (cur_loc, cur_h, cur_mode)
                continue

            prev_loc, prev_h, prev_mode = prev
            if cur_loc != prev_loc or cur_h != prev_h or cur_mode != prev_mode:
                need_mesh_rebuild = (cur_h != prev_h or cur_mode != prev_mode)
                # If Auto-Height from Base Z is enabled and the Null point moved vertically in Z,
                # automatically adjust the tower height from the Null point down to its anchored base Z!
                if auto_base_z and abs(cur_loc[2] - prev_loc[2]) > 1e-3 and cur_h == prev_h:
                    base_z = float(n_obj.get("af_rw_null_base_z", prev_loc[2] - prev_h))
                    new_h = max(0.95, min(200.0, float(n_obj.location.z) - base_z))
                    n_obj["af_rw_null_tower_height_m"] = new_h
                    cur_h = round(new_h, 3)
                    need_mesh_rebuild = True
                elif cur_h != prev_h:
                    n_obj["af_rw_null_base_z"] = float(n_obj.location.z) - float(cur_h)

                _NULL_POS_CACHE[key] = (cur_loc, cur_h, cur_mode)
                dirty_systems.add(sys_root)
                if need_mesh_rebuild:
                    dirty_nulls.append((sys_root, n_obj))

    if not dirty_systems:
        return

    _RW_EVAL_GUARD = True
    try:
        for sys_root, n_obj in dirty_nulls:
            _rebuild_pylon_hardware_for_null(sys_root, n_obj)
        f_cur = float(scene.frame_current)
        for sys_root in dirty_systems:
            apply_ropeway_evaluation_to_system(sys_root, frame=f_cur, scene=scene)
    except Exception:
        pass
    finally:
        _RW_EVAL_GUARD = False


def register_ropeway_gondola_handlers():
    for h in list(bpy.app.handlers.frame_change_post):
        if getattr(h, "__name__", "") == "af_ropeway_frame_change_handler":
            bpy.app.handlers.frame_change_post.remove(h)
    bpy.app.handlers.frame_change_post.append(af_ropeway_frame_change_handler)

    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "af_ropeway_depsgraph_update_handler":
            bpy.app.handlers.depsgraph_update_post.remove(h)
    bpy.app.handlers.depsgraph_update_post.append(af_ropeway_depsgraph_update_handler)


def unregister_ropeway_gondola_handlers():
    for h in list(bpy.app.handlers.frame_change_post):
        if getattr(h, "__name__", "") == "af_ropeway_frame_change_handler":
            bpy.app.handlers.frame_change_post.remove(h)
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "af_ropeway_depsgraph_update_handler":
            bpy.app.handlers.depsgraph_update_post.remove(h)
