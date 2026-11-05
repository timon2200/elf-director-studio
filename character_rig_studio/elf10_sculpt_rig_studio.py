"""
Elf #10 (Stari Urar Tornja Varaždinske Vijećnice — S3_10_urar_vijecnice_M_stari)
================================================================================
4-Part Modular Sculpt, Rig, Weight Paint & Mixamo Studio (`BODY` + `HEAD AND HAIR` + `HAT` + `GLASSES`):
Priprema Blender scenu `elf10_urar_rig_ready.blend` s četiri odvojena Tripo P2 3D modela:
  1. `BODY` (Tijelo s odjećom bez glave i bez brade, 7.5 glava visine, 45° A-poza, razdvojeni prsti)
  2. `HEAD AND HAIR` (Glava, lice, duga bijela brada, uši i sijeda kosa — BEZ kape i BEZ naočala)
  3. `HAT` (Zasebna zeleno-crvena baršunasta vilenjačka kapa sa spuštenim vrhom i mjedenim zvončićem)
  4. `GLASSES` (Zasebne mjedene urarske naočale s pomičnim dvostrukim povećalom / lupom)
te 72-koštanim rigom `ARM_Elf_Hero` i interaktivnim N-panelom (`Elf Rig Studio`) za:
  - KORAK 1 [VI]: Ručno spajanje i poravnavanje 4 modela (`BODY` + `HEAD AND HAIR` + `HAT` + `GLASSES`) + Sculpt Grab
  - KORAK 2 [VI]: Ručno poravnavanje kostiju (`Edit Mode` + `X-Axis Mirror`, uključujući kosti kape, naočala i brade)
  - KORAK 3 [VI]: Oštri zglobni Bind + 1-klik Ručni Weight Paint za Tijelo, Glavu/Bradu, Kapu i Naočale + Zaključavanje težina
  - KORAK 4 [AGENT]: 1-klik prijenos Mixamo FBX animacija sa sekundarnom fizikom kape, zvonca, lupe i brade + GLB Export
"""

import bpy
import bmesh
import math
import os
import json
from mathutils import Vector, Matrix, Quaternion, Euler
from mathutils.kdtree import KDTree


DEFAULT_MAC_PROJECT_DIR = "/Users/timonterzic/Documents/Projekti/Advent Lift 2026"


def get_portable_project_dir():
    """Returns main project dir if on studio Mac, or the folder containing the open .blend file on a collaborator PC/Mac."""
    if os.path.exists(DEFAULT_MAC_PROJECT_DIR):
        return DEFAULT_MAC_PROJECT_DIR
    try:
        if bpy.data.filepath:
            blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
            # Check if blend is inside assets/models/
            cand = os.path.abspath(os.path.join(blend_dir, "..", ".."))
            if os.path.exists(os.path.join(cand, "assets")):
                return cand
            return blend_dir
    except Exception:
        pass
    return os.getcwd()


PROJECT_DIR = get_portable_project_dir()
ROOT = PROJECT_DIR
GLB_DIR = os.path.join(PROJECT_DIR, "assets/models/glb/elf_10_urar_modular")
BODY_GLB = os.path.join(GLB_DIR, "elf10_S3_10_headless_body.glb")
HEAD_GLB = os.path.join(GLB_DIR, "elf10_S3_10_head_hair.glb")
HAT_GLB = os.path.join(GLB_DIR, "elf10_S3_10_hat.glb")
GLASSES_GLB = os.path.join(GLB_DIR, "elf10_S3_10_glasses.glb")
PROP_GLB = os.path.join(GLB_DIR, "elf10_S3_10_prop.glb")
BODY_CLEAN_GLB = os.path.join(GLB_DIR, "elf10_S3_10_headless_body_clean.glb")
HEAD_CLEAN_GLB = os.path.join(GLB_DIR, "elf10_S3_10_head_hair_clean.glb")
HAT_CLEAN_GLB = os.path.join(GLB_DIR, "elf10_S3_10_hat_clean.glb")
GLASSES_CLEAN_GLB = os.path.join(GLB_DIR, "elf10_S3_10_glasses_clean.glb")
PROP_CLEAN_GLB = os.path.join(GLB_DIR, "elf10_S3_10_prop_clean.glb")
MIXAMO_DIR = os.path.join(PROJECT_DIR, "assets/animations/rpm_mocap")
OUTPUT_BLEND = os.path.join(PROJECT_DIR, "assets/models/elf10_urar_rig_ready.blend")

# Default neck pivot world position where HEAD AND HAIR sits cleanly in BODY's collar
DEFAULT_HEAD_PIVOT = (0.0, -0.016, 1.742)
# Multiplier applied AFTER baking GLTF node scale (1.34x fills the shirt collar & hangs beard over waistcoat)
RAW_HEAD_SCALE = 1.34
RAW_HEAD_NECK_PIVOT = (0.0, 0.032, -0.095)

# Default hat brim pivot world position where HAT sits on the crown of HEAD AND HAIR
DEFAULT_HAT_PIVOT = (0.014, -0.004, 1.972)
# Multiplier applied AFTER baking GLTF node scale
RAW_HAT_SCALE = 0.90
RAW_HAT_BRIM_PIVOT = (0.0, 0.010, -0.085)

# Default glasses nose-bridge pivot world position where GLASSES sit on the nose & ears of HEAD AND HAIR
DEFAULT_GLASSES_PIVOT = (0.004, -0.122, 1.908)
# Multiplier applied AFTER baking GLTF node scale
RAW_GLASSES_SCALE = 0.56
RAW_GLASSES_BRIDGE_PIVOT = (0.0, -0.035, -0.025)

# Default handheld/belt PROP pivot world position (near right hand / belt holster for easy alignment)
DEFAULT_PROP_PIVOT = (-0.545, -0.035, 1.010)
RAW_PROP_SCALE = 0.52
RAW_PROP_HANDLE_PIVOT = (0.0, 0.0, 0.0)


def auto_tuck_submerged_neck(head_obj, body_obj):
    """
    Smoothly tapers the submerged rear/side base of `HEAD AND HAIR`'s neck (`z_world < 1.800` and `y > -0.03`)
    so the neck slots inside `BODY`'s shirt/coat collar while leaving the front long white beard untouched!
    """
    if not head_obj or not body_obj:
        return
    mw_h = head_obj.matrix_world
    mw_h_inv = mw_h.inverted()
    for v in head_obj.data.vertices:
        wco = mw_h @ v.co
        # Only taper the neck skin column behind the beard (y > -0.035), never the front beard!
        if 1.700 < wco.z < 1.800 and wco.y > -0.035:
            t = max(0.0, min(1.0, (1.800 - wco.z) / 0.060))
            shrink = 1.0 - 0.22 * (t ** 1.2)
            cx, cy = 0.0, 0.015
            wco.x = cx + (wco.x - cx) * shrink
            wco.y = cy + (wco.y - cy) * shrink
            v.co = mw_h_inv @ wco
    head_obj.data.update()


# ============================================================================
# 1. DEFINICIJA 71 KOSTI ZA ELF #10 (STARI URAR — UKLJUČUJUĆI KAPU I BRADU)
# ============================================================================
def get_elf10_bone_defs():
    """Returns dict of 71 bone definitions: name -> (head, tail, parent, connected, group)."""
    b = {}

    # --- 1. TIJELO I KRALJEŽNICA ---
    b["Hips"]   = ((0.0, 0.010, 0.950), (0.0, 0.010, 1.095), None,     False, "1_Tijelo_i_Noge")
    b["Spine"]  = ((0.0, 0.010, 1.095), (0.0, 0.012, 1.255), "Hips",   True,  "1_Tijelo_i_Noge")
    b["Spine1"] = ((0.0, 0.012, 1.255), (0.0, 0.015, 1.435), "Spine",  True,  "1_Tijelo_i_Noge")
    b["Spine2"] = ((0.0, 0.015, 1.435), (0.0, 0.015, 1.655), "Spine1", True,  "1_Tijelo_i_Noge")

    # --- 4. GLAVA, VRAT, BRADA, OČI I UŠI ---
    b["Neck"]          = ((0.0, 0.015, 1.655), (0.0, 0.005, 1.785), "Spine2", True,  "4_Glava_Lice_Usi")
    b["Head"]          = ((0.0, 0.005, 1.785), (0.0, 0.000, 1.965), "Neck",   True,  "4_Glava_Lice_Usi")
    b["Jaw"]           = ((0.0, -0.035, 1.845), (0.0, -0.095, 1.795), "Head", False, "4_Glava_Lice_Usi")
    b["Beard.01"]      = ((0.0, -0.085, 1.815), (0.0, -0.115, 1.705), "Jaw",  False, "4_Glava_Lice_Usi")
    b["Beard.02"]      = ((0.0, -0.115, 1.705), (0.0, -0.110, 1.585), "Beard.01", True, "4_Glava_Lice_Usi")

    # --- 5. KAPA (LANAC 4 KOSTI), URARSKE NAOČALE S LUPOM I ALAT NA POJASU ---
    # Naočale (Glasses) sjedaju na nos i uši (parent: Head), a dvostruka urarska lupa (ForeheadLoupe) je vezana na Glasses
    b["Glasses"]       = ((0.000, -0.078, 1.885), (0.000, -0.112, 1.885), "Head",    False, "5_Kapa_i_Alat")
    b["ForeheadLoupe"] = ((0.042, -0.088, 1.912), (0.068, -0.125, 1.958), "Glasses", False, "5_Kapa_i_Alat")

    # Kapa se savija u lijevu stranu lika (+X = .L) i završava zvončićem HatBell
    b["Hat.01"]      = ((0.000, 0.005, 1.935), (0.025, 0.010, 2.085), "Head",   False, "5_Kapa_i_Alat")
    b["Hat.02"]      = ((0.025, 0.010, 2.085), (0.095, 0.005, 2.135), "Hat.01", True,  "5_Kapa_i_Alat")
    b["Hat.03"]      = ((0.095, 0.005, 2.135), (0.165, -0.010, 2.005), "Hat.02", True,  "5_Kapa_i_Alat")
    b["HatBell"]     = ((0.165, -0.010, 2.005), (0.180, -0.012, 1.955), "Hat.03", True,  "5_Kapa_i_Alat")

    # Urarski ključevi na desnom boku (-X), šestar/alat na lijevom boku (+X) i kosti za zasebni PROP u ruci
    b["ClockKeys.R"] = ((-0.105, -0.145, 1.185), (-0.115, -0.150, 1.035), "Hips",   False, "5_Kapa_i_Alat")
    b["Calipers.L"]  = (( 0.125, -0.135, 1.195), ( 0.145, -0.140, 1.015), "Hips",   False, "5_Kapa_i_Alat")
    b["Prop.R"]      = ((-0.545, -0.015, 1.010), (-0.545, -0.125, 1.010), "Hand.R", False, "5_Kapa_i_Alat")
    b["Prop.L"]      = (( 0.545, -0.015, 1.010), ( 0.545, -0.125, 1.010), "Hand.L", False, "5_Kapa_i_Alat")

    # --- SIMETRIČNI PAROVI (.L = +X, .R = -X) ---
    for side, s in [(".L", 1.0), (".R", -1.0)]:
        leg_side = "Left" if s > 0 else "Right"

        # Oči, Brkovi i Vilenjačke Uši
        b[f"Eye{side}"]      = ((s * 0.036, -0.072, 1.895), (s * 0.036, -0.108, 1.895), "Head", False, "4_Glava_Lice_Usi")
        b[f"Mustache{side}"] = ((s * 0.024, -0.098, 1.842), (s * 0.065, -0.085, 1.835), "Head", False, "4_Glava_Lice_Usi")
        b[f"Ear.01{side}"]   = ((s * 0.074,  0.004, 1.865), (s * 0.115,  0.024, 1.895), "Head", False, "4_Glava_Lice_Usi")
        b[f"Ear.02{side}"]   = ((s * 0.115,  0.024, 1.895), (s * 0.165,  0.038, 1.928), f"Ear.01{side}", True, "4_Glava_Lice_Usi")

        # Rame, Nadlaktica, Podlaktica, Šaka (45° A-poza)
        b[f"Shoulder{side}"] = ((s * 0.065, 0.015, 1.575), (s * 0.220, 0.020, 1.545), "Spine2",            False, "2_Ruke")
        b[f"UpperArm{side}"] = ((s * 0.220, 0.020, 1.545), (s * 0.380, 0.036, 1.350), f"Shoulder{side}",   True,  "2_Ruke")
        b[f"ForeArm{side}"]  = ((s * 0.380, 0.036, 1.350), (s * 0.515, 0.025, 1.120), f"UpperArm{side}",   True,  "2_Ruke")
        b[f"Hand{side}"]     = ((s * 0.515, 0.025, 1.120), (s * 0.550, 0.035, 1.025), f"ForeArm{side}",    True,  "2_Ruke")

        # 5 Prstiju × 3 Falange po ruci (ukupno 30 kostiju prstiju)
        b[f"Thumb.01{side}"] = ((s * 0.510, -0.025, 1.062), (s * 0.502, -0.055, 1.022), f"Hand{side}",     False, "3_Prsti")
        b[f"Thumb.02{side}"] = ((s * 0.502, -0.055, 1.022), (s * 0.498, -0.072, 0.992), f"Thumb.01{side}", True,  "3_Prsti")
        b[f"Thumb.03{side}"] = ((s * 0.498, -0.072, 0.992), (s * 0.495, -0.088, 0.965), f"Thumb.02{side}", True,  "3_Prsti")

        b[f"Index.01{side}"] = ((s * 0.555, -0.015, 1.010), (s * 0.562, -0.022, 0.962), f"Hand{side}",     False, "3_Prsti")
        b[f"Index.02{side}"] = ((s * 0.562, -0.022, 0.962), (s * 0.558, -0.026, 0.932), f"Index.01{side}", True,  "3_Prsti")
        b[f"Index.03{side}"] = ((s * 0.558, -0.026, 0.932), (s * 0.550, -0.028, 0.908), f"Index.02{side}", True,  "3_Prsti")

        b[f"Middle.01{side}"] = ((s * 0.565, 0.015, 1.005), (s * 0.572, 0.015, 0.952), f"Hand{side}",      False, "3_Prsti")
        b[f"Middle.02{side}"] = ((s * 0.572, 0.015, 0.952), (s * 0.568, 0.015, 0.920), f"Middle.01{side}", True,  "3_Prsti")
        b[f"Middle.03{side}"] = ((s * 0.568, 0.015, 0.920), (s * 0.558, 0.015, 0.895), f"Middle.02{side}", True,  "3_Prsti")

        b[f"Ring.01{side}"] = ((s * 0.562, 0.045, 1.005), (s * 0.568, 0.048, 0.955), f"Hand{side}",    False, "3_Prsti")
        b[f"Ring.02{side}"] = ((s * 0.568, 0.048, 0.955), (s * 0.562, 0.050, 0.925), f"Ring.01{side}", True,  "3_Prsti")
        b[f"Ring.03{side}"] = ((s * 0.562, 0.050, 0.925), (s * 0.554, 0.052, 0.902), f"Ring.02{side}", True,  "3_Prsti")

        b[f"Pinky.01{side}"] = ((s * 0.555, 0.072, 1.010), (s * 0.560, 0.078, 0.965), f"Hand{side}",     False, "3_Prsti")
        b[f"Pinky.02{side}"] = ((s * 0.560, 0.078, 0.965), (s * 0.554, 0.080, 0.938), f"Pinky.01{side}", True,  "3_Prsti")
        b[f"Pinky.03{side}"] = ((s * 0.554, 0.080, 0.938), (s * 0.546, 0.082, 0.916), f"Pinky.02{side}", True,  "3_Prsti")

        # Noge i Čizme
        b[f"{leg_side}UpLeg"]   = ((s * 0.145, 0.015, 0.955), (s * 0.255,  0.025, 0.535), "Hips",               False, "1_Tijelo_i_Noge")
        b[f"{leg_side}Leg"]     = ((s * 0.255, 0.025, 0.535), (s * 0.285,  0.055, 0.085), f"{leg_side}UpLeg",   True,  "1_Tijelo_i_Noge")
        b[f"{leg_side}Foot"]    = ((s * 0.285, 0.055, 0.085), (s * 0.285, -0.055, 0.045), f"{leg_side}Leg",     True,  "1_Tijelo_i_Noge")
        b[f"{leg_side}ToeBase"] = ((s * 0.285, -0.055, 0.045), (s * 0.285, -0.185, 0.075), f"{leg_side}Foot",   True,  "1_Tijelo_i_Noge")

    return b


def create_editable_armature(arm_name="ARM_Elf_Hero"):
    """Creates the 71-bone editable armature with X-Axis Mirror and 5 color-coded Bone Collections."""
    old = bpy.data.objects.get(arm_name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    arm_data = bpy.data.armatures.new(arm_name)
    arm_obj = bpy.data.objects.new(arm_name, arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)

    arm_obj.show_in_front = True
    arm_data.display_type = "OCTAHEDRAL"
    arm_data.show_names = False
    arm_data.show_axes = False
    arm_data.use_mirror_x = True

    collection_themes = {
        "1_Tijelo_i_Noge":    "THEME04",
        "2_Ruke":             "THEME09",
        "3_Prsti":            "THEME03",
        "4_Glava_Lice_Usi":   "THEME01",
        "5_Kapa_i_Alat":      "THEME06",
    }
    bcols = {}
    if hasattr(arm_data, "collections"):
        for cname in collection_themes:
            bcols[cname] = arm_data.collections.new(cname)

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    bdefs = get_elf10_bone_defs()
    ebones = {}
    for bname, (head, tail, parent, connected, group_name) in bdefs.items():
        eb = arm_data.edit_bones.new(bname)
        eb.head = Vector(head)
        eb.tail = Vector(tail)
        eb.use_deform = True
        ebones[bname] = eb

    for bname, (head, tail, parent, connected, group_name) in bdefs.items():
        eb = ebones[bname]
        if parent and parent in ebones:
            eb.parent = ebones[parent]
            eb.use_connect = connected
        bpy.ops.armature.select_all(action="DESELECT")
        eb.select = True
        eb.select_head = True
        eb.select_tail = True
        if "Thumb" in bname:
            bpy.ops.armature.calculate_roll(type="GLOBAL_POS_X")
        elif any(k in bname for k in ["Index", "Middle", "Ring", "Pinky", "UpperArm", "ForeArm", "Hand", "Shoulder"]):
            bpy.ops.armature.calculate_roll(type="GLOBAL_POS_Y")
        else:
            bpy.ops.armature.calculate_roll(type="GLOBAL_NEG_Y")

    bpy.ops.object.mode_set(mode="OBJECT")

    for bname, (_, _, _, _, group_name) in bdefs.items():
        bone = arm_data.bones.get(bname)
        pb = arm_obj.pose.bones.get(bname)
        theme = collection_themes.get(group_name, "DEFAULT")
        if bone and group_name in bcols:
            bcols[group_name].assign(bone)
        if bone and hasattr(bone, "color"):
            bone.color.palette = theme
        if pb and hasattr(pb, "color"):
            pb.color.palette = theme

    arm_obj["ref_head_pivot"] = list(DEFAULT_HEAD_PIVOT)
    arm_obj["ref_head_scale"] = [1.0, 1.0, 1.0]
    arm_obj["ref_hat_pivot"] = list(DEFAULT_HAT_PIVOT)
    arm_obj["ref_hat_scale"] = [1.0, 1.0, 1.0]
    arm_obj["ref_glasses_pivot"] = list(DEFAULT_GLASSES_PIVOT)
    arm_obj["ref_glasses_scale"] = [1.0, 1.0, 1.0]
    arm_obj["ref_prop_pivot"] = list(DEFAULT_PROP_PIVOT)
    arm_obj["ref_prop_scale"] = [1.0, 1.0, 1.0]
    return arm_obj


# ============================================================================
# 2. SINKRONIZACIJA KOSTIJU GLAVE, KAPE, NAOČALA I PROPA S POMAKOM MODELA
# ============================================================================
def sync_head_and_hat_bones_to_meshes(context):
    """
    Reads location/rotation/scale deltas of `HEAD AND HAIR`, `HAT`, `GLASSES`, and `PROP` relative to their
    reference pivots, updates the head/beard bones (`4_Glava_Lice_Usi`), hat bones
    (`Hat.01..HatBell`), glasses bones (`Glasses`, `ForeheadLoupe`), and prop bone (`Prop.R`), and bakes rotation/scale cleanly.
    """
    head_obj = bpy.data.objects.get("HEAD AND HAIR")
    hat_obj = bpy.data.objects.get("HAT")
    glasses_obj = bpy.data.objects.get("GLASSES")
    prop_obj = bpy.data.objects.get("PROP")
    body_obj = bpy.data.objects.get("BODY")
    arm_obj = bpy.data.objects.get("ARM_Elf_Hero")

    if not arm_obj:
        return False, "Armatura 'ARM_Elf_Hero' nije pronađena."

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    if body_obj:
        bpy.ops.object.select_all(action="DESELECT")
        body_obj.select_set(True)
        context.view_layer.objects.active = body_obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 1. Read HEAD AND HAIR transform
    cur_head_pivot = head_obj.location.copy() if head_obj else Vector(DEFAULT_HEAD_PIVOT)
    cur_head_scale = head_obj.scale.copy() if head_obj else Vector((1.0, 1.0, 1.0))
    cur_head_rot = head_obj.rotation_euler.to_matrix() if head_obj else Matrix.Identity(3)
    ref_head_pivot = Vector(arm_obj.get("ref_head_pivot", DEFAULT_HEAD_PIVOT))
    ref_head_scale = Vector(arm_obj.get("ref_head_scale", (1.0, 1.0, 1.0)))

    if head_obj:
        bpy.ops.object.select_all(action="DESELECT")
        head_obj.select_set(True)
        context.view_layer.objects.active = head_obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # 2. Read HAT transform
    cur_hat_pivot = hat_obj.location.copy() if hat_obj else Vector(DEFAULT_HAT_PIVOT)
    cur_hat_scale = hat_obj.scale.copy() if hat_obj else Vector((1.0, 1.0, 1.0))
    cur_hat_rot = hat_obj.rotation_euler.to_matrix() if hat_obj else Matrix.Identity(3)
    ref_hat_pivot = Vector(arm_obj.get("ref_hat_pivot", DEFAULT_HAT_PIVOT))
    ref_hat_scale = Vector(arm_obj.get("ref_hat_scale", (1.0, 1.0, 1.0)))

    if hat_obj:
        bpy.ops.object.select_all(action="DESELECT")
        hat_obj.select_set(True)
        context.view_layer.objects.active = hat_obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # 3. Read GLASSES transform
    cur_glasses_pivot = glasses_obj.location.copy() if glasses_obj else Vector(DEFAULT_GLASSES_PIVOT)
    cur_glasses_scale = glasses_obj.scale.copy() if glasses_obj else Vector((1.0, 1.0, 1.0))
    cur_glasses_rot = glasses_obj.rotation_euler.to_matrix() if glasses_obj else Matrix.Identity(3)
    ref_glasses_pivot = Vector(arm_obj.get("ref_glasses_pivot", DEFAULT_GLASSES_PIVOT))
    ref_glasses_scale = Vector(arm_obj.get("ref_glasses_scale", (1.0, 1.0, 1.0)))

    if glasses_obj:
        bpy.ops.object.select_all(action="DESELECT")
        glasses_obj.select_set(True)
        context.view_layer.objects.active = glasses_obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # 4. Read PROP transform
    cur_prop_pivot = prop_obj.location.copy() if prop_obj else Vector(DEFAULT_PROP_PIVOT)
    cur_prop_scale = prop_obj.scale.copy() if prop_obj else Vector((1.0, 1.0, 1.0))
    cur_prop_rot = prop_obj.rotation_euler.to_matrix() if prop_obj else Matrix.Identity(3)
    ref_prop_pivot = Vector(arm_obj.get("ref_prop_pivot", DEFAULT_PROP_PIVOT))
    ref_prop_scale = Vector(arm_obj.get("ref_prop_scale", (1.0, 1.0, 1.0)))

    if prop_obj:
        bpy.ops.object.select_all(action="DESELECT")
        prop_obj.select_set(True)
        context.view_layer.objects.active = prop_obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    head_bone_names = [
        "Head", "Jaw", "Beard.01", "Beard.02",
        "Eye.L", "Eye.R",
        "Mustache.L", "Mustache.R",
        "Ear.01.L", "Ear.02.L", "Ear.01.R", "Ear.02.R",
    ]
    hat_bone_names = ["Hat.01", "Hat.02", "Hat.03", "HatBell"]
    glasses_bone_names = ["Glasses", "ForeheadLoupe"]
    prop_bone_names = ["Prop.R"]

    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    head_s_ratio = Vector((
        cur_head_scale.x / max(ref_head_scale.x, 1e-4),
        cur_head_scale.y / max(ref_head_scale.y, 1e-4),
        cur_head_scale.z / max(ref_head_scale.z, 1e-4),
    ))
    hat_s_ratio = Vector((
        cur_hat_scale.x / max(ref_hat_scale.x, 1e-4),
        cur_hat_scale.y / max(ref_hat_scale.y, 1e-4),
        cur_hat_scale.z / max(ref_hat_scale.z, 1e-4),
    ))
    glasses_s_ratio = Vector((
        cur_glasses_scale.x / max(ref_glasses_scale.x, 1e-4),
        cur_glasses_scale.y / max(ref_glasses_scale.y, 1e-4),
        cur_glasses_scale.z / max(ref_glasses_scale.z, 1e-4),
    ))

    def transform_head_pt(pt):
        rel = pt - ref_head_pivot
        rel = Vector((rel.x * head_s_ratio.x, rel.y * head_s_ratio.y, rel.z * head_s_ratio.z))
        rel = cur_head_rot @ rel
        return cur_head_pivot + rel

    def transform_hat_pt(pt):
        rel = pt - ref_hat_pivot
        rel = Vector((rel.x * hat_s_ratio.x, rel.y * hat_s_ratio.y, rel.z * hat_s_ratio.z))
        rel = cur_hat_rot @ rel
        return cur_hat_pivot + rel

    def transform_glasses_pt(pt):
        rel = pt - ref_glasses_pivot
        rel = Vector((rel.x * glasses_s_ratio.x, rel.y * glasses_s_ratio.y, rel.z * glasses_s_ratio.z))
        rel = cur_glasses_rot @ rel
        return cur_glasses_pivot + rel

    ebones = arm_obj.data.edit_bones
    if "Neck" in ebones and "Head" in ebones:
        new_head_base = transform_head_pt(ebones["Head"].head.copy())
        ebones["Neck"].tail = new_head_base
    for bname in head_bone_names:
        if bname in ebones:
            eb = ebones[bname]
            if not eb.use_connect:
                eb.head = transform_head_pt(eb.head.copy())
            eb.tail = transform_head_pt(eb.tail.copy())

    for bname in hat_bone_names:
        if bname in ebones:
            eb = ebones[bname]
            if not eb.use_connect:
                eb.head = transform_hat_pt(eb.head.copy())
            eb.tail = transform_hat_pt(eb.tail.copy())

    for bname in glasses_bone_names:
        if bname in ebones:
            eb = ebones[bname]
            if not eb.use_connect:
                eb.head = transform_glasses_pt(eb.head.copy())
            eb.tail = transform_glasses_pt(eb.tail.copy())

    prop_s_ratio = Vector((
        cur_prop_scale.x / max(ref_prop_scale.x, 1e-4),
        cur_prop_scale.y / max(ref_prop_scale.y, 1e-4),
        cur_prop_scale.z / max(ref_prop_scale.z, 1e-4),
    ))
    def transform_prop_pt(pt):
        rel = pt - ref_prop_pivot
        rel = Vector((rel.x * prop_s_ratio.x, rel.y * prop_s_ratio.y, rel.z * prop_s_ratio.z))
        rel = cur_prop_rot @ rel
        return cur_prop_pivot + rel

    for bname in prop_bone_names:
        if bname in ebones:
            eb = ebones[bname]
            if not eb.use_connect:
                eb.head = transform_prop_pt(eb.head.copy())
            eb.tail = transform_prop_pt(eb.tail.copy())

    bpy.ops.object.mode_set(mode="OBJECT")
    arm_obj["ref_head_pivot"] = [cur_head_pivot.x, cur_head_pivot.y, cur_head_pivot.z]
    arm_obj["ref_head_scale"] = [1.0, 1.0, 1.0]
    arm_obj["ref_hat_pivot"] = [cur_hat_pivot.x, cur_hat_pivot.y, cur_hat_pivot.z]
    arm_obj["ref_hat_scale"] = [1.0, 1.0, 1.0]
    arm_obj["ref_glasses_pivot"] = [cur_glasses_pivot.x, cur_glasses_pivot.y, cur_glasses_pivot.z]
    arm_obj["ref_glasses_scale"] = [1.0, 1.0, 1.0]
    arm_obj["ref_prop_pivot"] = [cur_prop_pivot.x, cur_prop_pivot.y, cur_prop_pivot.z]
    arm_obj["ref_prop_scale"] = [1.0, 1.0, 1.0]
    return True, (
        f"Poravnanje potvrđeno! Glava ({cur_head_pivot.z:.3f}m), Kapa ({cur_hat_pivot.z:.3f}m), Naočale i Prop usklađeni s kostima."
    )


# ============================================================================
# 3. OŠTRO VEZIVANJE ZGLOBNIH RAVNINA + 3D WEIGHT & PAZUH GIZMO SUSTAV
# ============================================================================
def smoothstep(edge0, edge1, x):
    t = max(0.0, min(1.0, (x - edge0) / max(1e-8, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def eval_fade_curve(edge0, edge1, x, curve_type="SMOOTH", power=1.0):
    """
    Evaluates a customizable transition fade curve between two bones across [-half_width, +half_width]:
      - 'SMOOTH':    C2 Hermite smoothstep t^2*(3 - 2t)
      - 'QUINTIC':   C4 Perlin quintic t^3*(t*(6t - 15) + 10) (ultra-glatki prijelaz za pazuh i odjeću)
      - 'SOFT_DOME': Cosine bell transition 0.5 - 0.5*cos(pi*t)
      - 'SHARP':     Tightened mechanical hinge transition
      - 'LINEAR':    Linear ramp
      - power:       Bias exponent (<1 shifts weight toward child/arm, >1 shifts weight toward parent/torso)
    """
    t = max(0.0, min(1.0, (x - edge0) / max(1e-8, edge1 - edge0)))
    if abs(power - 1.0) > 1e-3 and 0.0 < t < 1.0:
        t = math.pow(t, max(0.15, min(5.0, power)))
    if curve_type == "QUINTIC":
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
    elif curve_type == "SOFT_DOME":
        return 0.5 - 0.5 * math.cos(math.pi * t)
    elif curve_type == "SHARP":
        u = max(0.0, min(1.0, (t - 0.22) / 0.56))
        return u * u * (3.0 - 2.0 * u)
    elif curve_type == "LINEAR":
        return t
    return t * t * (3.0 - 2.0 * t)


def pt_seg_dist(p, a, b):
    ab = b - a
    ab_len_sq = ab.length_squared
    if ab_len_sq < 1e-12:
        return (p - a).length, 0.0
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab_len_sq))
    proj = a + t * ab
    return (p - proj).length, t


def blend_chain_planes(p, joints, dirs, half_widths, bone_names, curve_type="SMOOTH", power=1.0):
    """
    Cumulative axial joint-plane skinning along an N-bone chain separated by N-1 joint planes:
    - Gives 100% (1.00) rigid weights along bone shafts
    - Transitions smoothly across each joint plane using `curve_type` and `power`
    """
    n = len(bone_names)
    cum_f = 1.0
    F = []
    for i in range(n - 1):
        s_val = (p - joints[i]).dot(dirs[i])
        h = max(0.002, half_widths[i])
        f_i = eval_fade_curve(-h, h, s_val, curve_type=curve_type, power=power)
        cum_f = cum_f * f_i
        F.append(cum_f)
    weights = {}
    for i, bname in enumerate(bone_names):
        f_prev = F[i - 1] if i > 0 else 1.0
        f_curr = F[i] if i < n - 1 else 0.0
        w = f_prev - f_curr
        if w > 1e-4:
            weights[bname] = w
    return weights


def get_armpit_and_joint_gizmo_config(scn, bsegs, side):
    """
    Computes the 3D Armpit Crease Plane & Joint Planes for `side` ('.L' or '.R'),
    reading live overrides from `WGT_GIZMO_Pazuh.L` / `WGT_GIZMO_Lakat.L` if the user
    manipulated the 3D Empty Gizmo in the Viewport, or from Scene sliders!
    """
    s = 1.0 if side == ".L" else -1.0
    ua_h, ua_t = bsegs[f"UpperArm{side}"]
    fa_h, fa_t = bsegs[f"ForeArm{side}"]
    ha_h, ha_t = bsegs[f"Hand{side}"]
    sh_h, sh_t = bsegs.get(f"Shoulder{side}", (Vector((s * 0.065, ua_h.y, ua_h.z + 0.03)), ua_h))

    armpit_inset_m = getattr(scn, "elf01_armpit_inset_cm", 3.5) * 0.01
    armpit_drop_m = getattr(scn, "elf01_armpit_drop_cm", 5.5) * 0.01
    armpit_angle_deg = getattr(scn, "elf01_armpit_angle_deg", 28.0)
    armpit_fade_m = max(0.004, getattr(scn, "elf01_armpit_fade_cm", 3.2) * 0.01)
    shoulder_infl = max(0.0, min(1.5, getattr(scn, "elf01_shoulder_influence", 0.78)))

    # If interactive 3D Empty Gizmo `WGT_GIZMO_Pazuh.L` exists and was moved/rotated/scaled by user, sync from it:
    giz_ap = bpy.data.objects.get("WGT_GIZMO_Pazuh.L")
    if giz_ap and getattr(scn, "elf01_use_3d_gizmo_empties", False):
        ap_loc = giz_ap.location
        p_armpit = Vector((s * abs(ap_loc.x), ap_loc.y, ap_loc.z))
        # Normal from gizmo local X axis (mirrored for .R)
        rot_mat = giz_ap.rotation_euler.to_matrix()
        local_n = (rot_mat @ Vector((1.0, 0.0, 0.35))).normalized()
        n_armpit = Vector((s * abs(local_n.x), local_n.y, local_n.z)).normalized()
        scale_avg = max(0.25, min(3.5, (giz_ap.scale.x + giz_ap.scale.y + giz_ap.scale.z) / 3.0))
        armpit_fade_m = max(0.004, armpit_fade_m * scale_avg)
    else:
        p_armpit = Vector((ua_h.x - s * armpit_inset_m, ua_h.y, ua_h.z - armpit_drop_m))
        ang_rad = math.radians(armpit_angle_deg)
        n_armpit = Vector((s * math.cos(ang_rad), 0.0, math.sin(ang_rad))).normalized()

    return {
        "p_armpit": p_armpit,
        "n_armpit": n_armpit,
        "armpit_fade_m": armpit_fade_m,
        "shoulder_infl": shoulder_infl,
        "sh_h": sh_h,
        "ua_h": ua_h,
        "fa_h": fa_h,
        "ha_h": ha_h,
    }


def bind_hat_mesh_corridor(hat_obj, arm_obj):
    """
    Binds `HAT` to `ARM_Elf_Hero` using Cumulative Axial Joint-Plane Skinning along
    `Head -> Hat.01 -> Hat.02 -> Hat.03 -> HatBell`:
    - Lower headband/brim (`Hat.01` root zone) is anchored 100% to `Head` so the hat never slips off the skull.
    - Upper velvet crown, drooping tail, and brass bell transition cleanly across `Hat.01`, `Hat.02`, `Hat.03`, and `HatBell`.
    """
    arm_obj.data.pose_position = "REST"
    bpy.context.view_layer.update()
    hat_obj.vertex_groups.clear()

    mw_arm = arm_obj.matrix_world
    bsegs = {}
    for bone in arm_obj.data.bones:
        if bone.use_deform:
            bsegs[bone.name] = (mw_arm @ bone.head_local, mw_arm @ bone.tail_local)

    hat_chain_names = ["Head", "Hat.01", "Hat.02", "Hat.03", "HatBell"]
    vgroups = {bname: hat_obj.vertex_groups.new(name=bname) for bname in hat_chain_names if bname in bsegs}

    scn = bpy.context.scene
    hat_hw = max(0.005, getattr(scn, "elf01_hat_joint_cm", 2.0) * 0.01)

    h1_h, h1_t = bsegs.get("Hat.01", (Vector((0, 0, 1.935)), Vector((0.025, 0.01, 2.085))))
    h2_h, h2_t = bsegs.get("Hat.02", (Vector((0.025, 0.01, 2.085)), Vector((0.095, 0.005, 2.135))))
    h3_h, h3_t = bsegs.get("Hat.03", (Vector((0.095, 0.005, 2.135)), Vector((0.165, -0.01, 2.005))))
    hb_h, hb_t = bsegs.get("HatBell", (Vector((0.165, -0.01, 2.005)), Vector((0.180, -0.012, 1.955))))

    u1 = (h1_t - h1_h).normalized()
    u2 = (h2_t - h2_h).normalized()
    u3 = (h3_t - h3_h).normalized()
    u4 = (hb_t - hb_h).normalized()

    # Joint 0: slightly above the lower headband brim so the bottom rim stays 100% locked to Head
    brim_plane_pt = h1_h + u1 * 0.045
    joints = [brim_plane_pt, h2_h, h3_h, hb_h]
    dirs = [
        u1,
        (u1 + u2).normalized(),
        (u2 + u3).normalized(),
        (u3 + u4).normalized(),
    ]
    hws = [hat_hw * 1.1, hat_hw, hat_hw * 0.9, hat_hw * 0.6]

    mw = hat_obj.matrix_world
    for v in hat_obj.data.vertices:
        co = mw @ v.co
        # Separate the drooping right-side tail/bell (+X) from the lower skull headband
        if co.x < 0.075 and co.z < h1_h.z + 0.040:
            scores = {"Head": 1.0}
        else:
            scores = blend_chain_planes(co, joints, dirs, hws, hat_chain_names)

        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:4]
        tot = sum(w for _, w in top)
        if tot > 1e-8:
            for bname, w in top:
                nw = w / tot
                if nw > 0.005 and bname in vgroups:
                    vgroups[bname].add([v.index], nw, "REPLACE")


def bind_glasses_mesh_corridor(glasses_obj, arm_obj):
    """
    Binds `GLASSES` to `ARM_Elf_Hero`:
    - Main round brass spectacle frame, nose pads, and temple ear-stems -> 100% `Glasses`
    - Articulated upper-left double-loupe watchmaker magnifier assembly -> `ForeheadLoupe`
      with a crisp ±0.8 cm hinge transition at the mounting bracket (`ForeheadLoupe` head).
    - Preserves non-bone utility vertex groups such as `Lenses`.
    """
    arm_obj.data.pose_position = "REST"
    bpy.context.view_layer.update()

    mw_arm = arm_obj.matrix_world
    bsegs = {}
    for bone in arm_obj.data.bones:
        if bone.use_deform:
            bsegs[bone.name] = (mw_arm @ bone.head_local, mw_arm @ bone.tail_local)

    glasses_chain = ["Glasses", "ForeheadLoupe"]
    for bname in list(bsegs.keys()) + glasses_chain:
        existing_vg = glasses_obj.vertex_groups.get(bname)
        if existing_vg:
            glasses_obj.vertex_groups.remove(existing_vg)

    vgroups = {bname: glasses_obj.vertex_groups.new(name=bname) for bname in glasses_chain if bname in bsegs}

    fl_h, fl_t = bsegs.get("ForeheadLoupe", (Vector((0.042, -0.088, 1.912)), Vector((0.068, -0.125, 1.958))))
    u_fl = (fl_t - fl_h).normalized()

    mw = glasses_obj.matrix_world
    for v in glasses_obj.data.vertices:
        co = mw @ v.co
        # Only vertices on the upper-left articulated loupe assembly (+X > 0.012 and above the spectacle rim)
        if co.x > 0.012 and co.z > fl_h.z - 0.008 and co.y < fl_h.y + 0.025:
            s_val = (co - fl_h).dot(u_fl)
            w_loupe = smoothstep(-0.008, 0.008, s_val)
            scores = {"Glasses": 1.0 - w_loupe, "ForeheadLoupe": w_loupe}
        else:
            scores = {"Glasses": 1.0}

        for bname, w in scores.items():
            if w > 0.005 and bname in vgroups:
                vgroups[bname].add([v.index], w, "REPLACE")


def bind_prop_mesh_corridor(prop_obj, arm_obj):
    """
    Binds `PROP` 100% rigidly to `Prop.R` (or `Hand.R` fallback) so handheld/belt tools move cleanly without distortion.
    """
    arm_obj.data.pose_position = "REST"
    bpy.context.view_layer.update()
    prop_obj.vertex_groups.clear()
    target_bone = "Prop.R" if "Prop.R" in arm_obj.data.bones else "Hand.R"
    vg = prop_obj.vertex_groups.new(name=target_bone)
    all_indices = [v.index for v in prop_obj.data.vertices]
    if all_indices:
        vg.add(all_indices, 1.0, "REPLACE")


def bind_single_mesh_corridor(mesh_obj, arm_obj, bone_segments, is_head_mesh=False, collar_z_limit=1.785):
    """
    Assigns Crisp Axial Joint-Plane weights to `BODY` or `HEAD AND HAIR` from `ARM_Elf_Hero`:
    - 100% (1.00) rigid weights on bone shafts
    - Tight ±1.8 cm hinge transitions across anatomical joint bisecting planes
    - Neck-Collar Anti-Clipping + Beard chain (`Beard.01 -> Beard.02`) + ForeheadLoupe on `HEAD AND HAIR`
    """
    arm_obj.data.pose_position = "REST"
    bpy.context.view_layer.update()
    mesh_obj.vertex_groups.clear()

    mw_arm = arm_obj.matrix_world
    bsegs = {}
    for bone in arm_obj.data.bones:
        if bone.use_deform:
            bsegs[bone.name] = (mw_arm @ bone.head_local, mw_arm @ bone.tail_local)

    vgroups = {bname: mesh_obj.vertex_groups.new(name=bname) for bname in bsegs}

    arm_chains = {}
    leg_chains = {}
    finger_chains = {}
    finger_names = ("Thumb", "Index", "Middle", "Ring", "Pinky")

    scn = bpy.context.scene
    arm_hw = max(0.003, getattr(scn, "elf01_arm_joint_cm", 1.8) * 0.01)
    leg_hw = max(0.003, getattr(scn, "elf01_leg_joint_cm", 1.8) * 0.01)
    spine_hw = max(0.005, getattr(scn, "elf01_spine_joint_cm", 2.5) * 0.01)
    curve_type = getattr(scn, "elf01_fade_curve_type", "QUINTIC")
    fade_power = getattr(scn, "elf01_fade_power", 1.0)
    elbow_off_m = getattr(scn, "elf01_elbow_offset_cm", 0.0) * 0.01
    elbow_fade_m = max(0.003, getattr(scn, "elf01_elbow_fade_cm", getattr(scn, "elf01_arm_joint_cm", 1.8)) * 0.01)
    wrist_off_m = getattr(scn, "elf01_wrist_offset_cm", 0.0) * 0.01
    wrist_fade_m = max(0.003, getattr(scn, "elf01_wrist_fade_cm", 1.5) * 0.01)
    hip_off_m = getattr(scn, "elf01_hip_offset_cm", 0.0) * 0.01
    hip_fade_m = max(0.004, getattr(scn, "elf01_hip_fade_cm", 2.2) * 0.01)
    knee_off_m = getattr(scn, "elf01_knee_offset_cm", 0.0) * 0.01
    knee_fade_m = max(0.003, getattr(scn, "elf01_knee_fade_cm", getattr(scn, "elf01_leg_joint_cm", 1.8)) * 0.01)
    armpit_cfgs = {}

    for side, s in [(".L", 1.0), (".R", -1.0)]:
        leg_side = "Left" if s > 0 else "Right"

        ua_h, ua_t = bsegs[f"UpperArm{side}"]
        fa_h, fa_t = bsegs[f"ForeArm{side}"]
        ha_h, ha_t = bsegs[f"Hand{side}"]
        u_ua = (ua_t - ua_h).normalized()
        u_fa = (fa_t - fa_h).normalized()
        u_ha = (ha_t - ha_h).normalized()

        ap_cfg = get_armpit_and_joint_gizmo_config(scn, bsegs, side)
        armpit_cfgs[side] = ap_cfg

        n_sh_in = Vector((s * 0.96, 0.0, 0.28)).normalized()
        n_sh_out = ap_cfg["n_armpit"]
        sh_in_pt = Vector((ua_h.x - s * 0.075, ua_h.y, ua_h.z + 0.010))
        ua_plane_pt = Vector((ap_cfg["p_armpit"].x + s * 0.018, ua_h.y, ua_h.z - 0.012))
        n_elb = (u_ua + u_fa).normalized()
        n_wri = (u_fa + u_ha).normalized()
        elb_pt = fa_h + n_elb * elbow_off_m
        wri_pt = ha_h + n_wri * wrist_off_m

        arm_chains[side] = (
            [sh_in_pt, ua_plane_pt, elb_pt, wri_pt],
            [n_sh_in, n_sh_out, n_elb, n_wri],
            [ap_cfg["armpit_fade_m"] * 0.95, ap_cfg["armpit_fade_m"] * 1.15, elbow_fade_m, wrist_fade_m],
            ["Spine2", f"Shoulder{side}", f"UpperArm{side}", f"ForeArm{side}", f"Hand{side}"],
            wri_pt, n_wri
        )

        f_list = []
        for fname in finger_names:
            f1_h, f1_t = bsegs[f"{fname}.01{side}"]
            f2_h, f2_t = bsegs[f"{fname}.02{side}"]
            f3_h, f3_t = bsegs[f"{fname}.03{side}"]
            u1 = (f1_t - f1_h).normalized()
            u2 = (f2_t - f2_h).normalized()
            u3 = (f3_t - f3_h).normalized()
            f_list.append((
                fname,
                [(f1_h, f1_t), (f2_h, f2_t), (f3_h, f3_t)],
                [f1_h, f2_h, f3_h],
                [u1, (u1 + u2).normalized(), (u2 + u3).normalized()],
                [0.005, 0.004, 0.004],
                [f"Hand{side}", f"{fname}.01{side}", f"{fname}.02{side}", f"{fname}.03{side}"],
                f1_h, u1
            ))
        finger_chains[side] = f_list

        ul_h, ul_t = bsegs[f"{leg_side}UpLeg"]
        lg_h, lg_t = bsegs[f"{leg_side}Leg"]
        ft_h, ft_t = bsegs[f"{leg_side}Foot"]
        tb_h, tb_t = bsegs[f"{leg_side}ToeBase"]
        u_ul = (ul_t - ul_h).normalized()
        u_lg = (lg_t - lg_h).normalized()
        u_boot = (tb_t - ft_h).normalized()

        n_hip = Vector((s * 0.10, 0.0, -0.995)).normalized()
        hip_pt = Vector((s * 0.10, 0.0, ul_h.z - 0.015)) + n_hip * hip_off_m
        n_knee = (u_ul + u_lg).normalized()
        knee_pt = lg_h + n_knee * knee_off_m
        ankle_pt = Vector((ft_h.x, 0.05, ft_h.z + 0.008))
        n_ankle = Vector((0.0, -0.45, -0.89)).normalized()
        n_toe = u_boot

        leg_chains[side] = (
            [hip_pt, knee_pt, ankle_pt, tb_h],
            [n_hip, n_knee, n_ankle, n_toe],
            [hip_fade_m, knee_fade_m, leg_hw * 0.85, leg_hw * 0.85],
            ["Hips", f"{leg_side}UpLeg", f"{leg_side}Leg", f"{leg_side}Foot", f"{leg_side}ToeBase"]
        )

    sp_h = bsegs["Spine"][0]
    sp1_h = bsegs["Spine1"][0]
    sp2_h = bsegs["Spine2"][0]
    nk_h = bsegs["Neck"][0]
    z_up = Vector((0.0, 0.0, 1.0))
    spine_joints = [sp_h, sp1_h, sp2_h, nk_h]
    spine_dirs = [z_up, z_up, z_up, z_up]
    spine_hws = [spine_hw, spine_hw, spine_hw, spine_hw * 0.85]
    spine_bnames = ["Hips", "Spine", "Spine1", "Spine2", "Neck"]

    # Beard chain planes for HEAD AND HAIR
    b1_h, b1_t = bsegs.get("Beard.01", (Vector((0, -0.085, 1.815)), Vector((0, -0.115, 1.705))))
    b2_h, b2_t = bsegs.get("Beard.02", (Vector((0, -0.115, 1.705)), Vector((0, -0.110, 1.585))))
    z_down = Vector((0.0, 0.0, -1.0))
    beard_joints = [b1_h, b2_h]
    beard_dirs = [z_down, z_down]
    beard_hws = [0.022, 0.025]
    beard_bnames = ["Head", "Beard.01", "Beard.02"]

    mw = mesh_obj.matrix_world
    for v in mesh_obj.data.vertices:
        co = mw @ v.co
        x, y, z = co.x, co.y, co.z
        abs_x = abs(x)
        side = ".L" if x >= 0.0 else ".R"
        scores = {}

        if is_head_mesh:
            # Front long white beard zone (in front of neck/chest: y < -0.045 and z < 1.825)
            if y < -0.045 and z < 1.825 and abs_x < 0.095:
                scores = blend_chain_planes(co, beard_joints, beard_dirs, beard_hws, beard_bnames)
                # Subtle Spine2 influence on the very bottom beard tip so it glides over the waistcoat
                if z < 1.660:
                    t_chest = smoothstep(1.660, 1.570, z) * 0.35
                    for k in list(scores.keys()):
                        scores[k] *= (1.0 - t_chest)
                    scores["Spine2"] = scores.get("Spine2", 0.0) + t_chest
            else:
                h_eff = z - 0.35 * min(0.0, y + 0.035)
                t_raw = max(0.0, min(1.0, (h_eff - 1.740) / (1.805 - 1.740)))
                u = t_raw * t_raw * (3.0 - 2.0 * t_raw)

                if u < 0.999:
                    scores["Spine2"] = ((1.0 - u) ** 1.4) * 0.55
                    scores["Neck"] = (1.0 - u) * 0.65 + u * (1.0 - u) * 0.80
                    scores["Head"] = (u ** 1.2) * 1.00
                else:
                    scores["Head"] = 1.0

                if u > 0.25:
                    if abs_x > 0.070 and 1.83 < z < 1.98:
                        for eb_name in (f"Ear.01{side}", f"Ear.02{side}"):
                            if eb_name in bsegs:
                                a, b = bsegs[eb_name]
                                d, _ = pt_seg_dist(co, a, b)
                                if d < 0.048:
                                    scores[eb_name] = u * (2.5 / ((d / 0.015) ** 2 + 0.15))
                    if y < -0.075 and 1.825 < z < 1.868 and abs_x > 0.025:
                        mb_name = f"Mustache{side}"
                        if mb_name in bsegs:
                            a, b = bsegs[mb_name]
                            d, _ = pt_seg_dist(co, a, b)
                            if d < 0.026:
                                scores[mb_name] = u * (1.8 / ((d / 0.012) ** 2 + 0.25))
                    if y < -0.070 and 1.910 < z < 1.975 and x > 0.015:
                        if "ForeheadLoupe" in bsegs:
                            a, b = bsegs["ForeheadLoupe"]
                            d, _ = pt_seg_dist(co, a, b)
                            if d < 0.038:
                                scores["ForeheadLoupe"] = u * (2.2 / ((d / 0.015) ** 2 + 0.20))
                    if y < -0.065 and 1.875 < z < 1.920 and 0.015 < abs_x < 0.062:
                        ey_name = f"Eye{side}"
                        if ey_name in bsegs:
                            a, b = bsegs[ey_name]
                            d, _ = pt_seg_dist(co, a, b)
                            if d < 0.024:
                                scores[ey_name] = u * (1.8 / ((d / 0.010) ** 2 + 0.20))

        else:
            ap_cfg = armpit_cfgs[side]
            p_ap = ap_cfg["p_armpit"]
            n_ap = ap_cfg["n_armpit"]
            ap_fade = ap_cfg["armpit_fade_m"]
            sh_infl = ap_cfg["shoulder_infl"]

            # Continuous 3D Armpit Crease & Ribcage Shield Signed Distance (clamped below armpit so hands/thumbs at z~0.95m are 100% arm!)
            z_for_plane = max(z, p_ap.z - 0.08)
            d_plane = (co.x - p_ap.x) * n_ap.x + (co.y - p_ap.y) * n_ap.y + (z_for_plane - p_ap.z) * n_ap.z
            rib_wall_x = abs(p_ap.x) + min(0.085, max(0.0, (p_ap.z - z) * 0.22))
            d_rib = abs_x - rib_wall_x
            if z < p_ap.z:
                s_arm_zone = min(d_plane, d_rib)
            else:
                s_arm_zone = d_plane

            if z > 0.85 and z < 1.665 and s_arm_zone > -ap_fade * 1.35:
                w_arm_zone = eval_fade_curve(-ap_fade, ap_fade, s_arm_zone, curve_type=curve_type, power=fade_power)
            else:
                w_arm_zone = 0.0

            if w_arm_zone > 0.001:
                jts, drs, hws, bns, ha_h, n_wri = arm_chains[side]
                if abs_x > abs(ap_cfg["ua_h"].x) + 0.055:
                    # Past the shoulder joint: evaluate only UpperArm -> ForeArm -> Hand so the upward-tilted
                    # armpit/shoulder plane never intersects the lower forearm, wrist, or thumb at z ~ 1.0m.
                    arm_scores = blend_chain_planes(co, jts[2:], drs[2:], hws[2:], bns[2:], curve_type=curve_type, power=fade_power)
                else:
                    arm_scores = blend_chain_planes(co, jts, drs, hws, bns, curve_type=curve_type, power=fade_power)

                # Modulate Shoulder cushion inside the armpit fold
                sh_key = f"Shoulder{side}"
                if sh_key in arm_scores and abs(sh_infl - 1.0) > 1e-3:
                    old_sh = arm_scores[sh_key]
                    new_sh = old_sh * sh_infl
                    arm_scores[sh_key] = new_sh
                    diff = old_sh - new_sh
                    if diff > 0:
                        arm_scores["Spine2"] = arm_scores.get("Spine2", 0.0) + diff * 0.55
                        arm_scores[f"UpperArm{side}"] = arm_scores.get(f"UpperArm{side}", 0.0) + diff * 0.45

                s_wri = (co - ha_h).dot(n_wri)
                if s_wri > -0.010 and abs_x > 0.380:
                    f_candidates = []
                    for fname, seg3, fjts, fdrs, fhws, fbns, f1_h, u1 in finger_chains[side]:
                        s_kn = (co - f1_h).dot(u1)
                        if s_kn > -0.007:
                            d_min = min(pt_seg_dist(co, sa, sb)[0] for sa, sb in seg3)
                            if d_min < 0.026:
                                f_candidates.append((d_min, fjts, fdrs, fhws, fbns))
                    if f_candidates:
                        f_candidates.sort(key=lambda item: item[0])
                        _, fjts, fdrs, fhws, fbns = f_candidates[0]
                        f_weights = blend_chain_planes(co, fjts, fdrs, fhws, fbns, curve_type=curve_type, power=fade_power)
                        w_fa = arm_scores.get(f"ForeArm{side}", 0.0)
                        arm_scores = {f"ForeArm{side}": w_fa} if w_fa > 1e-4 else {}
                        rem = 1.0 - w_fa
                        for k, val in f_weights.items():
                            arm_scores[k] = arm_scores.get(k, 0.0) + rem * val

                if w_arm_zone >= 0.999:
                    scores = arm_scores
                else:
                    torso_scores = blend_chain_planes(co, spine_joints, spine_dirs, spine_hws, spine_bnames, curve_type=curve_type, power=fade_power)
                    w_t = 1.0 - w_arm_zone
                    scores = {}
                    for k, val in torso_scores.items():
                        scores[k] = scores.get(k, 0.0) + val * w_t
                    for k, val in arm_scores.items():
                        scores[k] = scores.get(k, 0.0) + val * w_arm_zone

            elif z < 1.02:
                co_leg = Vector((co.x, co.y, min(co.z, 0.055) if (y < -0.02 and z < 0.23) else co.z))
                ljts, ldrs, lhws, lbns = leg_chains[side]
                scores = blend_chain_planes(co_leg, ljts, ldrs, lhws, lbns, curve_type=curve_type, power=fade_power)

                if z > 0.78 and abs_x < 0.022:
                    opp_side = ".R" if side == ".L" else ".L"
                    opp_scores = blend_chain_planes(co_leg, *leg_chains[opp_side], curve_type=curve_type, power=fade_power)
                    t_side = smoothstep(0.0, 0.022, abs_x)
                    w_own = 0.5 + 0.5 * t_side
                    w_opp = 1.0 - w_own
                    merged = {}
                    for k, val in scores.items():
                        merged[k] = merged.get(k, 0.0) + val * w_own
                    for k, val in opp_scores.items():
                        merged[k] = merged.get(k, 0.0) + val * w_opp
                    scores = merged

            else:
                scores = blend_chain_planes(co, spine_joints, spine_dirs, spine_hws, spine_bnames, curve_type=curve_type, power=fade_power)

                if "ClockKeys.R" in bsegs and x < -0.05 and y < -0.09 and 1.00 < z < 1.24:
                    a, b = bsegs["ClockKeys.R"]
                    d_acc, _ = pt_seg_dist(co, a, b)
                    if d_acc < 0.055:
                        w_acc = smoothstep(0.055, 0.020, d_acc) * 0.85
                        for k in list(scores.keys()):
                            scores[k] *= (1.0 - w_acc)
                        scores["ClockKeys.R"] = w_acc
                if "Calipers.L" in bsegs and x > 0.06 and y < -0.08 and 0.98 < z < 1.25:
                    a, b = bsegs["Calipers.L"]
                    d_acc, _ = pt_seg_dist(co, a, b)
                    if d_acc < 0.060:
                        w_acc = smoothstep(0.060, 0.020, d_acc) * 0.85
                        for k in list(scores.keys()):
                            scores[k] *= (1.0 - w_acc)
                        scores["Calipers.L"] = w_acc

        if not scores:
            scores["Head" if is_head_mesh else "Spine1"] = 1.0

        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:4]
        tot = sum(w for _, w in top)
        if tot > 1e-8:
            for bname, w in top:
                nw = w / tot
                if nw > 0.005:
                    vgroups[bname].add([v.index], nw, "REPLACE")


def bind_character_to_rig(context, force=False):
    """
    Binds `BODY`, `HEAD AND HAIR`, and `HAT` to `ARM_Elf_Hero` using Crisp Axial Joint-Plane Skinning.
    If `scene.elf01_lock_weights` is True and `force=False`, refuses to overwrite manual Weight Paint!
    """
    if not force and getattr(context.scene, "elf01_lock_weights", False):
        return (
            False,
            "Ručne težine su ZAKLJUČANE! Isključi 'Zaključaj Ručne Težine' u Koraku 3 ako želiš pregaziti težine novim Bindom.",
        )

    arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
    if not arm_obj:
        return False, "Armatura 'ARM_Elf_Hero' nije pronađena!"

    head_obj = bpy.data.objects.get("HEAD AND HAIR")
    hat_obj = bpy.data.objects.get("HAT")
    glasses_obj = bpy.data.objects.get("GLASSES")
    prop_obj = bpy.data.objects.get("PROP")
    needs_sync = False
    if head_obj and (
        (head_obj.location - Vector(arm_obj.get("ref_head_pivot", DEFAULT_HEAD_PIVOT))).length > 1e-4
        or (head_obj.scale - Vector((1.0, 1.0, 1.0))).length > 1e-4
        or abs(head_obj.rotation_euler.x) + abs(head_obj.rotation_euler.y) + abs(head_obj.rotation_euler.z) > 1e-4
    ):
        needs_sync = True
    if hat_obj and (
        (hat_obj.location - Vector(arm_obj.get("ref_hat_pivot", DEFAULT_HAT_PIVOT))).length > 1e-4
        or (hat_obj.scale - Vector((1.0, 1.0, 1.0))).length > 1e-4
        or abs(hat_obj.rotation_euler.x) + abs(hat_obj.rotation_euler.y) + abs(hat_obj.rotation_euler.z) > 1e-4
    ):
        needs_sync = True
    if glasses_obj and (
        (glasses_obj.location - Vector(arm_obj.get("ref_glasses_pivot", DEFAULT_GLASSES_PIVOT))).length > 1e-4
        or (glasses_obj.scale - Vector((1.0, 1.0, 1.0))).length > 1e-4
        or abs(glasses_obj.rotation_euler.x) + abs(glasses_obj.rotation_euler.y) + abs(glasses_obj.rotation_euler.z) > 1e-4
    ):
        needs_sync = True
    if prop_obj and (
        (prop_obj.location - Vector(arm_obj.get("ref_prop_pivot", DEFAULT_PROP_PIVOT))).length > 1e-4
        or (prop_obj.scale - Vector((1.0, 1.0, 1.0))).length > 1e-4
        or abs(prop_obj.rotation_euler.x) + abs(prop_obj.rotation_euler.y) + abs(prop_obj.rotation_euler.z) > 1e-4
    ):
        needs_sync = True
    if needs_sync:
        sync_head_and_hat_bones_to_meshes(context)

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bone_segments = {}
    mw_arm = arm_obj.matrix_world
    for bone in arm_obj.data.bones:
        if bone.use_deform:
            bone_segments[bone.name] = (mw_arm @ bone.head_local, mw_arm @ bone.tail_local, 0.05)

    body_obj = bpy.data.objects.get("BODY")
    collar_z_limit = 1.785
    if body_obj:
        mw_b = body_obj.matrix_world
        collar_z_limit = max((mw_b @ v.co).z for v in body_obj.data.vertices) - 0.005

    preserve_vol = getattr(context.scene, "elf01_preserve_volume", True)
    bound_meshes = []
    for m_name in ("BODY", "HEAD AND HAIR", "HAT", "GLASSES", "PROP"):
        m_obj = bpy.data.objects.get(m_name)
        if not m_obj or m_obj.type != "MESH":
            continue
        if m_name == "HAT":
            bind_hat_mesh_corridor(m_obj, arm_obj)
        elif m_name == "GLASSES":
            bind_glasses_mesh_corridor(m_obj, arm_obj)
        elif m_name == "PROP":
            bind_prop_mesh_corridor(m_obj, arm_obj)
        else:
            is_head = (m_name == "HEAD AND HAIR")
            bind_single_mesh_corridor(m_obj, arm_obj, bone_segments, is_head_mesh=is_head, collar_z_limit=collar_z_limit)

        m_obj.parent = arm_obj
        m_obj.matrix_parent_inverse = arm_obj.matrix_world.inverted()

        for mod in list(m_obj.modifiers):
            if mod.type in ("ARMATURE", "CORRECTIVE_SMOOTH"):
                m_obj.modifiers.remove(mod)

        arm_mod = m_obj.modifiers.new(name="Armature", type="ARMATURE")
        arm_mod.object = arm_obj
        arm_mod.use_deform_preserve_volume = preserve_vol
        arm_mod.show_in_editmode = True
        arm_mod.show_on_cage = True

        bound_meshes.append(m_name)

    return True, f"Uspješno vezani modeli ({', '.join(bound_meshes)}) uz glatku pazušnu kapsulu i 3D zglobne ravnine!"


def recalc_armpit_and_joint_zone_only(context, zone="ARMPIT"):
    """
    Localized real-time weight recalculation strictly inside the selected joint/armpit corridor (`ARMPIT`, `ELBOW`, `WRIST`, `HIP`, `KNEE`):
    - Leaves 100% of manual weight painting outside that joint zone untouched!
    - Preserves active Pose Mode / Weight Paint Mode so you see the mesh deform live as you drag sliders or 3D Gizmos!
    """
    body_obj = bpy.data.objects.get("BODY")
    arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
    if not body_obj or not arm_obj:
        return False, "Model 'BODY' ili 'ARM_Elf_Hero' nije pronađen."

    scn = context.scene
    mw_arm = arm_obj.matrix_world
    bsegs = {b.name: (mw_arm @ b.head_local, mw_arm @ b.tail_local) for b in arm_obj.data.bones if b.use_deform}
    vgroups = {vg.name: vg for vg in body_obj.vertex_groups}
    for bname in bsegs:
        if bname not in vgroups:
            vgroups[bname] = body_obj.vertex_groups.new(name=bname)

    curve_type = getattr(scn, "elf01_fade_curve_type", "QUINTIC")
    fade_power = getattr(scn, "elf01_fade_power", 1.0)
    spine_hw = max(0.005, getattr(scn, "elf01_spine_joint_cm", 2.5) * 0.01)
    leg_hw = max(0.003, getattr(scn, "elf01_leg_joint_cm", 1.8) * 0.01)
    elbow_off_m = getattr(scn, "elf01_elbow_offset_cm", 0.0) * 0.01
    elbow_fade_m = max(0.003, getattr(scn, "elf01_elbow_fade_cm", getattr(scn, "elf01_arm_joint_cm", 1.8)) * 0.01)
    wrist_off_m = getattr(scn, "elf01_wrist_offset_cm", 0.0) * 0.01
    wrist_fade_m = max(0.003, getattr(scn, "elf01_wrist_fade_cm", 1.5) * 0.01)
    hip_off_m = getattr(scn, "elf01_hip_offset_cm", 0.0) * 0.01
    hip_fade_m = max(0.004, getattr(scn, "elf01_hip_fade_cm", 2.2) * 0.01)
    knee_off_m = getattr(scn, "elf01_knee_offset_cm", 0.0) * 0.01
    knee_fade_m = max(0.003, getattr(scn, "elf01_knee_fade_cm", getattr(scn, "elf01_leg_joint_cm", 1.8)) * 0.01)

    sp_h = bsegs["Spine"][0]
    sp1_h = bsegs["Spine1"][0]
    sp2_h = bsegs["Spine2"][0]
    nk_h = bsegs["Neck"][0]
    z_up = Vector((0.0, 0.0, 1.0))
    spine_joints = [sp_h, sp1_h, sp2_h, nk_h]
    spine_dirs = [z_up, z_up, z_up, z_up]
    spine_hws = [spine_hw, spine_hw, spine_hw, spine_hw * 0.85]
    spine_bnames = ["Hips", "Spine", "Spine1", "Spine2", "Neck"]

    armpit_cfgs = {}
    arm_chains = {}
    leg_chains = {}
    for side, s in [(".L", 1.0), (".R", -1.0)]:
        leg_side = "Left" if s > 0 else "Right"
        ua_h, ua_t = bsegs[f"UpperArm{side}"]
        fa_h, fa_t = bsegs[f"ForeArm{side}"]
        ha_h, ha_t = bsegs[f"Hand{side}"]
        u_ua = (ua_t - ua_h).normalized()
        u_fa = (fa_t - fa_h).normalized()
        u_ha = (ha_t - ha_h).normalized()

        ap_cfg = get_armpit_and_joint_gizmo_config(scn, bsegs, side)
        armpit_cfgs[side] = ap_cfg

        n_sh_in = Vector((s * 0.96, 0.0, 0.28)).normalized()
        n_sh_out = ap_cfg["n_armpit"]
        sh_in_pt = Vector((ua_h.x - s * 0.075, ua_h.y, ua_h.z + 0.010))
        ua_plane_pt = Vector((ap_cfg["p_armpit"].x + s * 0.018, ua_h.y, ua_h.z - 0.012))
        n_elb = (u_ua + u_fa).normalized()
        n_wri = (u_fa + u_ha).normalized()
        elb_pt = fa_h + n_elb * elbow_off_m
        wri_pt = ha_h + n_wri * wrist_off_m

        arm_chains[side] = (
            [sh_in_pt, ua_plane_pt, elb_pt, wri_pt],
            [n_sh_in, n_sh_out, n_elb, n_wri],
            [ap_cfg["armpit_fade_m"] * 0.95, ap_cfg["armpit_fade_m"] * 1.15, elbow_fade_m, wrist_fade_m],
            ["Spine2", f"Shoulder{side}", f"UpperArm{side}", f"ForeArm{side}", f"Hand{side}"],
        )

        ul_h, ul_t = bsegs[f"{leg_side}UpLeg"]
        lg_h, lg_t = bsegs[f"{leg_side}Leg"]
        ft_h, ft_t = bsegs[f"{leg_side}Foot"]
        tb_h, tb_t = bsegs[f"{leg_side}ToeBase"]
        u_ul = (ul_t - ul_h).normalized()
        u_lg = (lg_t - lg_h).normalized()
        u_boot = (tb_t - ft_h).normalized()
        n_hip = Vector((s * 0.10, 0.0, -0.995)).normalized()
        hip_pt = Vector((s * 0.10, 0.0, ul_h.z - 0.015)) + n_hip * hip_off_m
        n_knee = (u_ul + u_lg).normalized()
        knee_pt = lg_h + n_knee * knee_off_m
        ankle_pt = Vector((ft_h.x, 0.05, ft_h.z + 0.008))
        n_ankle = Vector((0.0, -0.45, -0.89)).normalized()
        leg_chains[side] = (
            [hip_pt, knee_pt, ankle_pt, tb_h],
            [n_hip, n_knee, n_ankle, u_boot],
            [hip_fade_m, knee_fade_m, leg_hw * 0.85, leg_hw * 0.85],
            ["Hips", f"{leg_side}UpLeg", f"{leg_side}Leg", f"{leg_side}Foot", f"{leg_side}ToeBase"],
        )

    mw = body_obj.matrix_world
    updated_count = 0
    for v in body_obj.data.vertices:
        co = mw @ v.co
        x, y, z = co.x, co.y, co.z
        abs_x = abs(x)
        side = ".L" if x >= 0.0 else ".R"
        leg_side = "Left" if x >= 0.0 else "Right"

        if zone == "ARMPIT":
            if not (1.18 < z < 1.66 and 0.05 < abs_x < 0.36):
                continue
            target_bones = ("Spine", "Spine1", "Spine2", "Neck", f"Shoulder{side}", f"UpperArm{side}", f"ForeArm{side}")
        elif zone == "ELBOW":
            fa_h = bsegs[f"ForeArm{side}"][0]
            if (co - Vector((abs(fa_h.x) * (1 if x >= 0 else -1), fa_h.y, fa_h.z))).length > 0.14:
                continue
            target_bones = (f"Shoulder{side}", f"UpperArm{side}", f"ForeArm{side}", f"Hand{side}")
        elif zone == "WRIST":
            ha_h = bsegs[f"Hand{side}"][0]
            if (co - Vector((abs(ha_h.x) * (1 if x >= 0 else -1), ha_h.y, ha_h.z))).length > 0.08:
                continue
            target_bones = (f"UpperArm{side}", f"ForeArm{side}", f"Hand{side}")
        elif zone == "HIP":
            if not (0.72 < z < 1.12):
                continue
            target_bones = ("Hips", "Spine", f"{leg_side}UpLeg", f"{leg_side}Leg")
        elif zone == "KNEE":
            if not (0.34 < z < 0.72):
                continue
            target_bones = ("Hips", f"{leg_side}UpLeg", f"{leg_side}Leg", f"{leg_side}Foot")
        else:
            continue

        for tb in target_bones:
            if tb in vgroups:
                vgroups[tb].remove([v.index])

        scores = {}
        if zone in ("ARMPIT", "ELBOW", "WRIST"):
            ap_cfg = armpit_cfgs[side]
            p_ap = ap_cfg["p_armpit"]
            n_ap = ap_cfg["n_armpit"]
            ap_fade = ap_cfg["armpit_fade_m"]
            sh_infl = ap_cfg["shoulder_infl"]

            d_plane = (co - p_ap).dot(n_ap)
            rib_wall_x = abs(p_ap.x) + max(0.0, (p_ap.z - z) * 0.24)
            d_rib = abs_x - rib_wall_x
            s_arm_zone = min(d_plane, d_rib) if z < p_ap.z else d_plane
            w_arm_zone = eval_fade_curve(-ap_fade, ap_fade, s_arm_zone, curve_type=curve_type, power=fade_power)

            jts, drs, hws, bns = arm_chains[side]
            arm_scores = blend_chain_planes(co, jts, drs, hws, bns, curve_type=curve_type, power=fade_power)
            sh_key = f"Shoulder{side}"
            if sh_key in arm_scores and abs(sh_infl - 1.0) > 1e-3:
                old_sh = arm_scores[sh_key]
                new_sh = old_sh * sh_infl
                arm_scores[sh_key] = new_sh
                diff = old_sh - new_sh
                if diff > 0:
                    arm_scores["Spine2"] = arm_scores.get("Spine2", 0.0) + diff * 0.55
                    arm_scores[f"UpperArm{side}"] = arm_scores.get(f"UpperArm{side}", 0.0) + diff * 0.45

            torso_scores = blend_chain_planes(co, spine_joints, spine_dirs, spine_hws, spine_bnames, curve_type=curve_type, power=fade_power)
            w_t = 1.0 - w_arm_zone
            for k, val in torso_scores.items():
                if k in target_bones:
                    scores[k] = scores.get(k, 0.0) + val * w_t
            for k, val in arm_scores.items():
                if k in target_bones:
                    scores[k] = scores.get(k, 0.0) + val * w_arm_zone
        else:
            co_leg = Vector((co.x, co.y, min(co.z, 0.055) if (y < -0.02 and z < 0.23) else co.z))
            ljts, ldrs, lhws, lbns = leg_chains[side]
            leg_scores = blend_chain_planes(co_leg, ljts, ldrs, lhws, lbns, curve_type=curve_type, power=fade_power)
            for k, val in leg_scores.items():
                if k in target_bones:
                    scores[k] = val

        tot = sum(scores.values())
        if tot > 1e-8:
            for bname, w in scores.items():
                nw = w / tot
                if nw > 0.003 and bname in vgroups:
                    vgroups[bname].add([v.index], nw, "REPLACE")
            updated_count += 1

    body_obj.data.update()
    return True, f"Zona '{zone}' ažurirana uživo ({updated_count} vrhova na .L i .R strani)!"


def relax_armpit_seam_weights(context, iterations=3, factor=0.45):
    """
    Topological Laplacian weight relaxation strictly inside the left and right armpit crease zones
    (`1.22 < z < 1.65`, `0.07 < |x| < 0.34`) across `Spine1`, `Spine2`, `Shoulder.L/.R`, and `UpperArm.L/.R`.
    Eliminates spiky/pinched triangles in the armpit while leaving the rest of the mesh 100% untouched!
    """
    body_obj = bpy.data.objects.get("BODY")
    if not body_obj or body_obj.type != "MESH":
        return False, "Mesh 'BODY' nije pronađen."

    me = body_obj.data
    mw = body_obj.matrix_world
    vgs = body_obj.vertex_groups
    vg_map = {g.name: g.index for g in vgs}
    armpit_bones = ["Spine1", "Spine2", "Shoulder.L", "UpperArm.L", "Shoulder.R", "UpperArm.R"]
    target_gis = set(vg_map[b] for b in armpit_bones if b in vg_map)
    if not target_gis:
        return False, "Kosti pazuha nisu pronađene u vertex grupama."

    armpit_v_indices = set()
    for v in me.vertices:
        co = mw @ v.co
        if 1.22 < co.z < 1.65 and 0.07 < abs(co.x) < 0.34:
            armpit_v_indices.add(v.index)

    adj = {vi: [] for vi in armpit_v_indices}
    for e in me.edges:
        v0, v1 = e.vertices[0], e.vertices[1]
        if v0 in adj and v1 in armpit_v_indices:
            adj[v0].append(v1)
        if v1 in adj and v0 in armpit_v_indices:
            adj[v1].append(v0)

    weights = [{g.group: g.weight for g in v.groups if g.group in target_gis} for v in me.vertices]

    for _ in range(iterations):
        new_w = {}
        for vi, nbs in adj.items():
            if not nbs:
                continue
            cur = weights[vi]
            blended = {}
            all_keys = set(cur.keys())
            for nb in nbs:
                all_keys.update(weights[nb].keys())
            inv_n = 1.0 / len(nbs)
            for k in all_keys:
                avg_nb = sum(weights[nb].get(k, 0.0) for nb in nbs) * inv_n
                blended[k] = (1.0 - factor) * cur.get(k, 0.0) + factor * avg_nb
            tot = sum(blended.values())
            if tot > 1e-8:
                new_w[vi] = {k: val / tot for k, val in blended.items() if val / tot > 0.002}
        for vi, bw in new_w.items():
            weights[vi] = bw

    for vi in armpit_v_indices:
        other_sum = sum(g.weight for g in me.vertices[vi].groups if g.group not in target_gis)
        avail = max(0.0, 1.0 - other_sum)
        for gi in target_gis:
            vgs[gi].remove([vi])
        bw = weights[vi]
        tot = sum(bw.values())
        if tot > 1e-8 and avail > 1e-4:
            for gi, val in bw.items():
                nw = (val / tot) * avail
                if nw > 0.002:
                    vgs[gi].add([vi], nw, "REPLACE")

    me.update()
    return True, f"Pazuh zaglađen (Laplacian Relax ×{iterations} na {len(armpit_v_indices)} vrhova)!"


# ============================================================================
# 4. HIJERARHIJSKI MIXAMO RETARGETER (SA SEKUNDARNOM FIZIKOM KAPE I BRADE)
# ============================================================================
MIXAMO_MAP = [
    ("Hips",          "mixamorig:Hips"),
    ("Spine",         "mixamorig:Spine"),
    ("Spine1",        "mixamorig:Spine1"),
    ("Spine2",        "mixamorig:Spine2"),
    ("Neck",          "mixamorig:Neck"),
    ("Head",          "mixamorig:Head"),
    ("Shoulder.L",    "mixamorig:LeftShoulder"),
    ("UpperArm.L",    "mixamorig:LeftArm"),
    ("ForeArm.L",     "mixamorig:LeftForeArm"),
    ("Hand.L",        "mixamorig:LeftHand"),
    ("Shoulder.R",    "mixamorig:RightShoulder"),
    ("UpperArm.R",    "mixamorig:RightArm"),
    ("ForeArm.R",     "mixamorig:RightForeArm"),
    ("Hand.R",        "mixamorig:RightHand"),
    ("LeftUpLeg",     "mixamorig:LeftUpLeg"),
    ("LeftLeg",       "mixamorig:LeftLeg"),
    ("LeftFoot",      "mixamorig:LeftFoot"),
    ("LeftToeBase",   "mixamorig:LeftToeBase"),
    ("RightUpLeg",    "mixamorig:RightUpLeg"),
    ("RightLeg",      "mixamorig:RightLeg"),
    ("RightFoot",     "mixamorig:RightFoot"),
    ("RightToeBase",  "mixamorig:RightToeBase"),
    ("Thumb.01.L",    "mixamorig:LeftHandThumb1"),
    ("Thumb.02.L",    "mixamorig:LeftHandThumb2"),
    ("Thumb.03.L",    "mixamorig:LeftHandThumb3"),
    ("Index.01.L",    "mixamorig:LeftHandIndex1"),
    ("Index.02.L",    "mixamorig:LeftHandIndex2"),
    ("Index.03.L",    "mixamorig:LeftHandIndex3"),
    ("Middle.01.L",   "mixamorig:LeftHandMiddle1"),
    ("Middle.02.L",   "mixamorig:LeftHandMiddle2"),
    ("Middle.03.L",   "mixamorig:LeftHandMiddle3"),
    ("Ring.01.L",     "mixamorig:LeftHandRing1"),
    ("Ring.02.L",     "mixamorig:LeftHandRing2"),
    ("Ring.03.L",     "mixamorig:LeftHandRing3"),
    ("Pinky.01.L",    "mixamorig:LeftHandPinky1"),
    ("Pinky.02.L",    "mixamorig:LeftHandPinky2"),
    ("Pinky.03.L",    "mixamorig:LeftHandPinky3"),
    ("Thumb.01.R",    "mixamorig:RightHandThumb1"),
    ("Thumb.02.R",    "mixamorig:RightHandThumb2"),
    ("Thumb.03.R",    "mixamorig:RightHandThumb3"),
    ("Index.01.R",    "mixamorig:RightHandIndex1"),
    ("Index.02.R",    "mixamorig:RightHandIndex2"),
    ("Index.03.R",    "mixamorig:RightHandIndex3"),
    ("Middle.01.R",   "mixamorig:RightHandMiddle1"),
    ("Middle.02.R",   "mixamorig:RightHandMiddle2"),
    ("Middle.03.R",   "mixamorig:RightHandMiddle3"),
    ("Ring.01.R",     "mixamorig:RightHandRing1"),
    ("Ring.02.R",     "mixamorig:RightHandRing2"),
    ("Ring.03.R",     "mixamorig:RightHandRing3"),
    ("Pinky.01.R",    "mixamorig:RightHandPinky1"),
    ("Pinky.02.R",    "mixamorig:RightHandPinky2"),
    ("Pinky.03.R",    "mixamorig:RightHandPinky3"),
]


def retarget_mixamo_fbx(arm_obj, fbx_path, action_name=None):
    """Imports a Mixamo FBX and bakes a twist-free hierarchical Action onto `arm_obj` with Hat & Beard physics."""
    if not os.path.exists(fbx_path):
        return False, f"FBX nije pronađen: {fbx_path}"

    scene = bpy.context.scene
    before_objs = set(scene.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_path, automatic_bone_orientation=True)
    new_objs = [o for o in scene.objects if o not in before_objs]
    src_arm = next((o for o in new_objs if o.type == "ARMATURE"), None)
    if not src_arm:
        for o in new_objs:
            bpy.data.objects.remove(o, do_unlink=True)
        return False, "U FBX datoteci nije pronađena Mixamo armatura."

    f_start, f_end = 1, 60
    if src_arm.animation_data and src_arm.animation_data.action:
        fr = src_arm.animation_data.action.frame_range
        f_start = max(1, int(round(fr[0])))
        f_end = max(f_start + 1, int(round(fr[1])))

    if not action_name:
        base = os.path.splitext(os.path.basename(fbx_path))[0]
        action_name = f"Elf10_{base}"

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    act = bpy.data.actions.new(name=action_name)
    arm_obj.animation_data.action = act

    tgt_rest_mat = {}
    tgt_rel_rest = {}
    tgt_rest_vec = {}
    for bname, _ in MIXAMO_MAP:
        b = arm_obj.data.bones.get(bname)
        if not b:
            continue
        tgt_rest_mat[bname] = b.matrix_local.copy()
        if b.parent:
            tgt_rel_rest[bname] = b.parent.matrix_local.inverted() @ b.matrix_local
        else:
            tgt_rel_rest[bname] = b.matrix_local.copy()
        tgt_rest_vec[bname] = (b.tail_local - b.head_local).normalized()

    src_rest_dir = {}
    src_bone_lookup = {}
    for bname, sname in MIXAMO_MAP:
        short_name = sname.split(":")[-1]
        sb = src_arm.data.bones.get(sname) or src_arm.data.bones.get(short_name)
        if not sb:
            continue
        src_bone_lookup[bname] = sb.name
        v = (src_arm.matrix_world.to_3x3() @ (sb.tail_local - sb.head_local)).normalized()
        src_rest_dir[bname] = v

    scene.frame_set(f_start)
    bpy.context.view_layer.update()
    hips_src_name = src_bone_lookup.get("Hips", "Hips")
    src_hips_pb = src_arm.pose.bones.get(hips_src_name)
    src_hips_z0 = (src_arm.matrix_world @ src_hips_pb.head).z if src_hips_pb else 1.0
    src_hips_p0 = (src_arm.matrix_world @ src_hips_pb.head).copy() if src_hips_pb else Vector((0, 0, 1))
    tgt_hips_z0 = arm_obj.data.bones["Hips"].head_local.z
    scale_ratio = tgt_hips_z0 / max(src_hips_z0, 0.1)

    for pb in arm_obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)

    f_limit = min(f_end, f_start + 120)
    for f in range(f_start, f_limit + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        posed_mat = {}

        for bname, sname in MIXAMO_MAP:
            pb = arm_obj.pose.bones.get(bname)
            actual_sname = src_bone_lookup.get(bname)
            spb = src_arm.pose.bones.get(actual_sname) if actual_sname else None
            if not pb or not spb:
                continue

            v_src_cur = (src_arm.matrix_world.to_3x3() @ (spb.tail - spb.head)).normalized()
            v_src_0 = src_rest_dir.get(bname, v_src_cur)
            q_delta_world = v_src_0.rotation_difference(v_src_cur)
            v_target = (q_delta_world @ tgt_rest_vec[bname]).normalized()

            parent_bone = pb.bone.parent
            if parent_bone and parent_bone.name in posed_mat:
                m_zero = posed_mat[parent_bone.name] @ tgt_rel_rest[bname]
            else:
                m_zero = tgt_rest_mat[bname].copy()

            v_zero = (m_zero.to_3x3() @ Vector((0, 1, 0))).normalized()
            q_swing_world = v_zero.rotation_difference(v_target)

            r_zero_inv = m_zero.to_3x3().inverted().to_quaternion()
            q_local = r_zero_inv @ q_swing_world @ m_zero.to_3x3().to_quaternion()
            pb.rotation_quaternion = q_local

            if bname == "Hips":
                cur_p = src_arm.matrix_world @ spb.head
                dp = (cur_p - src_hips_p0) * scale_ratio
                pb.location = m_zero.to_3x3().inverted() @ dp
                pb.keyframe_insert(data_path="location", frame=f)

            pb.keyframe_insert(data_path="rotation_quaternion", frame=f)
            posed_mat[bname] = m_zero @ q_local.to_matrix().to_4x4()

        # Subtle secondary motion on Ears, Beard, and Hat + Bell
        phase = f * 0.22
        for side, s in [(".L", 1.0), (".R", -1.0)]:
            for eb_n, amp in [(f"Ear.01{side}", 0.025), (f"Ear.02{side}", 0.045)]:
                epb = arm_obj.pose.bones.get(eb_n)
                if epb:
                    epb.rotation_quaternion = Quaternion((1.0, math.sin(phase) * amp, 0.0, s * math.cos(phase) * amp * 0.5)).normalized()
                    epb.keyframe_insert(data_path="rotation_quaternion", frame=f)

        for hb_n, amp, lag in [("Hat.01", 0.020, 0.0), ("Hat.02", 0.038, 0.5), ("Hat.03", 0.055, 1.0), ("HatBell", 0.085, 1.5)]:
            hpb = arm_obj.pose.bones.get(hb_n)
            if hpb:
                hpb.rotation_quaternion = Quaternion((
                    1.0,
                    math.sin(phase - lag) * amp,
                    0.0,
                    math.cos(phase - lag) * amp * 0.7,
                )).normalized()
                hpb.keyframe_insert(data_path="rotation_quaternion", frame=f)

        for bb_n, amp, lag in [("Beard.01", 0.022, 0.3), ("Beard.02", 0.040, 0.8)]:
            bpb = arm_obj.pose.bones.get(bb_n)
            if bpb:
                bpb.rotation_quaternion = Quaternion((
                    1.0,
                    math.sin(phase - lag) * amp,
                    0.0,
                    math.cos(phase - lag) * amp * 0.4,
                )).normalized()
                bpb.keyframe_insert(data_path="rotation_quaternion", frame=f)

    for o in new_objs:
        bpy.data.objects.remove(o, do_unlink=True)

    scene.frame_start = f_start
    scene.frame_end = f_limit
    scene.frame_set(f_start)
    return True, f"Animacija '{action_name}' ({f_start}–{f_limit} sličica) prebačena na Elf #10 (Urar + Kapa + Brada)!"


def retarget_mocap_npz(arm_obj, npz_path, action_name=None):
    """
    Retargets 133-keypoint 3D video motion capture (`.npz` from `tools/mocap_room_pipeline.py`)
    directly onto `ARM_Elf_Hero` in hierarchical parent-to-child order with torso/head 3D yaw
    twist, 30-bone finger curl, and velocity-driven Hat + Bell + Beard secondary physics.
    """
    import numpy as np

    if not os.path.exists(npz_path):
        return False, f"Mocap NPZ nije pronađen: {npz_path}"

    data = np.load(npz_path, allow_pickle=True)
    kpts_3d = data["keypoints_3d"]  # (T, 133, 3) in Blender metric Z-up
    scores = data["scores"] if "scores" in data else np.ones(kpts_3d.shape[:2], dtype=np.float32)
    T = int(kpts_3d.shape[0])
    fps = float(data["fps"]) if "fps" in data else 25.0

    if not action_name:
        base = os.path.splitext(os.path.basename(npz_path))[0]
        action_name = f"Elf10_{base}"

    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    if action_name in bpy.data.actions:
        bpy.data.actions.remove(bpy.data.actions[action_name])
    act = bpy.data.actions.new(name=action_name)
    act.use_fake_user = True
    arm_obj.animation_data.action = act
    arm_obj.data.pose_position = "POSE"

    # Cache target rest transforms for all bones in ARM_Elf_Hero
    tgt_rest_mat = {}
    tgt_rel_rest = {}
    tgt_rest_vec = {}
    for b in arm_obj.data.bones:
        bname = b.name
        tgt_rest_mat[bname] = b.matrix_local.copy()
        if b.parent:
            tgt_rel_rest[bname] = b.parent.matrix_local.inverted() @ b.matrix_local
        else:
            tgt_rel_rest[bname] = b.matrix_local.copy()
        tgt_rest_vec[bname] = (b.tail_local - b.head_local).normalized()

    for pb in arm_obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)

    # Per-frame perspective scale normalization: normalize by torso+leg apparent size so walking
    # closer to the camera doesn't make the character float upward!
    hip_centers = 0.5 * (kpts_3d[:, 11] + kpts_3d[:, 12])
    sh_centers = 0.5 * (kpts_3d[:, 5] + kpts_3d[:, 6])
    torso_lengths = np.linalg.norm(sh_centers - hip_centers, axis=-1)
    ref_torso_len = float(np.median(torso_lengths[:min(25, T)]))

    foot_min_z = np.minimum(kpts_3d[:, 15, 2], kpts_3d[:, 16, 2])
    hip_above_floor = (hip_centers[:, 2] - foot_min_z) * (ref_torso_len / np.maximum(0.15, torso_lengths))
    ref_hip_h0 = float(np.median(hip_above_floor[:min(25, T)]))
    ref_hip_xy0 = np.median(hip_centers[:min(25, T), :2], axis=0)

    tgt_hips_z0 = arm_obj.data.bones["Hips"].head_local.z if "Hips" in arm_obj.data.bones else 0.72
    scale_ratio = tgt_hips_z0 / max(0.35, ref_hip_h0)

    # Reference Frame-0 foot vectors so curled elf boots stay level on standing frames
    v_foot_l0 = (Vector(kpts_3d[0, 17]) - Vector(kpts_3d[0, 19])).normalized()
    v_foot_r0 = (Vector(kpts_3d[0, 20]) - Vector(kpts_3d[0, 22])).normalized()

    # Subtle outward coat-clearance rotation for arms when lowered to the sides
    q_clear_l = Quaternion((0.0, 1.0, 0.0), math.radians(-9.0))
    q_clear_r = Quaternion((0.0, 1.0, 0.0), math.radians(9.0))

    v_up = Vector((0.0, 0.0, 1.0))

    def apply_bone_world_dir(bname, v_target, posed_mat, twist_yaw_rad=0.0, frame_num=1, root_dp=None):
        pb = arm_obj.pose.bones.get(bname)
        if not pb:
            return
        parent_bone = pb.bone.parent
        if parent_bone and parent_bone.name in posed_mat:
            m_zero = posed_mat[parent_bone.name] @ tgt_rel_rest[bname]
        else:
            m_zero = tgt_rest_mat[bname].copy()

        v_zero = (m_zero.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
        q_swing_world = v_zero.rotation_difference(v_target.normalized())
        if abs(twist_yaw_rad) > 1e-4:
            q_twist_world = Quaternion(v_target.normalized(), twist_yaw_rad)
            q_world = q_twist_world @ q_swing_world
        else:
            q_world = q_swing_world

        r_zero_inv = m_zero.to_3x3().inverted().to_quaternion()
        q_local = r_zero_inv @ q_world @ m_zero.to_3x3().to_quaternion()
        pb.rotation_quaternion = q_local
        pb.keyframe_insert(data_path="rotation_quaternion", frame=frame_num)

        if root_dp is not None:
            pb.location = m_zero.to_3x3().inverted() @ root_dp
            pb.keyframe_insert(data_path="location", frame=frame_num)

        posed_mat[bname] = m_zero @ q_local.to_matrix().to_4x4()

    prev_nose = Vector(kpts_3d[0, 0])
    hat_vel_x, hat_vel_z = 0.0, 0.0

    for t in range(T):
        f = t + 1
        pts = kpts_3d[t]
        sc = scores[t]
        posed_mat = {}

        nose_p = Vector(pts[0])
        l_ear = Vector(pts[3])
        r_ear = Vector(pts[4])
        l_sh = Vector(pts[5])
        r_sh = Vector(pts[6])
        l_el = Vector(pts[7])
        r_el = Vector(pts[8])
        l_wr = Vector(pts[9])
        r_wr = Vector(pts[10])
        l_hip = Vector(pts[11])
        r_hip = Vector(pts[12])
        l_kn = Vector(pts[13])
        r_kn = Vector(pts[14])
        l_ank = Vector(pts[15])
        r_ank = Vector(pts[16])
        l_btoe = Vector(pts[17])
        l_heel = Vector(pts[19])
        r_btoe = Vector(pts[20])
        r_heel = Vector(pts[22])

        hip_c = 0.5 * (l_hip + r_hip)
        sh_c = 0.5 * (l_sh + r_sh)
        v_spine = (sh_c - hip_c).normalized()

        # 3D Yaw angles around Z from lateral hip, shoulder, and ear vectors
        lat_hip = (l_hip - r_hip).normalized()
        lat_sh = (l_sh - r_sh).normalized()
        lat_ear = (l_ear - r_ear).normalized()
        yaw_hip = math.atan2(lat_hip.y, lat_hip.x)
        yaw_sh = math.atan2(lat_sh.y, lat_sh.x)
        yaw_head = math.atan2(lat_ear.y, lat_ear.x)

        dp = Vector((
            (hip_c.x - float(ref_hip_xy0[0])) * scale_ratio * 0.45,
            (hip_c.y - float(ref_hip_xy0[1])) * scale_ratio * 0.25,
            (float(hip_above_floor[t]) - ref_hip_h0) * scale_ratio * 0.55,
        ))

        # 1. Hips & Spine chain
        apply_bone_world_dir("Hips", v_up.slerp(v_spine, 0.35), posed_mat, twist_yaw_rad=yaw_hip * 0.65, frame_num=f, root_dp=dp)
        apply_bone_world_dir("Spine", v_up.slerp(v_spine, 0.55), posed_mat, twist_yaw_rad=(yaw_sh - yaw_hip) * 0.30, frame_num=f)
        apply_bone_world_dir("Spine1", v_up.slerp(v_spine, 0.80), posed_mat, twist_yaw_rad=(yaw_sh - yaw_hip) * 0.35, frame_num=f)
        apply_bone_world_dir("Spine2", v_spine, posed_mat, twist_yaw_rad=(yaw_sh - yaw_hip) * 0.35, frame_num=f)

        # 2. Neck & Head
        v_head_raw = (nose_p - sh_c + Vector((0.0, 0.085, 0.02))).normalized()
        v_neck = v_spine.slerp(v_head_raw, 0.45)
        v_head = v_up.slerp(v_head_raw, 0.65)
        apply_bone_world_dir("Neck", v_neck, posed_mat, twist_yaw_rad=(yaw_head - yaw_sh) * 0.40, frame_num=f)
        apply_bone_world_dir("Head", v_head, posed_mat, twist_yaw_rad=(yaw_head - yaw_sh) * 0.60, frame_num=f)

        # 3. Shoulders & Arms (with subtle coat-clearance outward offset when arms are down)
        v_sh_l = tgt_rest_vec.get("Shoulder.L", Vector((1, 0, 0))).slerp((l_sh - sh_c).normalized(), 0.35)
        v_sh_r = tgt_rest_vec.get("Shoulder.R", Vector((-1, 0, 0))).slerp((r_sh - sh_c).normalized(), 0.35)
        v_ua_l = (q_clear_l @ (l_el - l_sh).normalized()).normalized()
        v_fa_l = (q_clear_l @ (l_wr - l_el).normalized()).normalized()
        v_ua_r = (q_clear_r @ (r_el - r_sh).normalized()).normalized()
        v_fa_r = (q_clear_r @ (r_wr - r_el).normalized()).normalized()

        apply_bone_world_dir("Shoulder.L", v_sh_l, posed_mat, frame_num=f)
        apply_bone_world_dir("UpperArm.L", v_ua_l, posed_mat, frame_num=f)
        apply_bone_world_dir("ForeArm.L", v_fa_l, posed_mat, frame_num=f)
        v_hand_l = (q_clear_l @ (Vector(pts[99]) - l_wr).normalized()).normalized() if sc[99] > 0.3 else v_fa_l
        apply_bone_world_dir("Hand.L", v_fa_l.slerp(v_hand_l, 0.50), posed_mat, frame_num=f)

        apply_bone_world_dir("Shoulder.R", v_sh_r, posed_mat, frame_num=f)
        apply_bone_world_dir("UpperArm.R", v_ua_r, posed_mat, frame_num=f)
        apply_bone_world_dir("ForeArm.R", v_fa_r, posed_mat, frame_num=f)
        v_hand_r = (q_clear_r @ (Vector(pts[120]) - r_wr).normalized()).normalized() if sc[120] > 0.3 else v_fa_r
        apply_bone_world_dir("Hand.R", v_fa_r.slerp(v_hand_r, 0.50), posed_mat, frame_num=f)

        # 4. Legs & Feet (using Frame-0 delta on feet so curled elf boots remain flat on floor)
        apply_bone_world_dir("LeftUpLeg", (l_kn - l_hip).normalized(), posed_mat, frame_num=f)
        apply_bone_world_dir("LeftLeg", (l_ank - l_kn).normalized(), posed_mat, frame_num=f)
        q_foot_dl = Quaternion((1, 0, 0, 0)).slerp(v_foot_l0.rotation_difference((l_btoe - l_heel).normalized()), 0.35)
        v_foot_l = (q_foot_dl @ tgt_rest_vec.get("LeftFoot", Vector((0, -0.82, -0.57)))).normalized()
        apply_bone_world_dir("LeftFoot", v_foot_l, posed_mat, frame_num=f)

        apply_bone_world_dir("RightUpLeg", (r_kn - r_hip).normalized(), posed_mat, frame_num=f)
        apply_bone_world_dir("RightLeg", (r_ank - r_kn).normalized(), posed_mat, frame_num=f)
        q_foot_dr = Quaternion((1, 0, 0, 0)).slerp(v_foot_r0.rotation_difference((r_btoe - r_heel).normalized()), 0.35)
        v_foot_r = (q_foot_dr @ tgt_rest_vec.get("RightFoot", Vector((0, -0.82, -0.57)))).normalized()
        apply_bone_world_dir("RightFoot", v_foot_r, posed_mat, frame_num=f)

        # 5. Velocity-driven secondary physics on Hat, Bell, Beard & Ears
        head_vel = (nose_p - prev_nose) * fps
        prev_nose = nose_p.copy()
        hat_vel_x = 0.78 * hat_vel_x + 0.22 * float(np.clip(-head_vel.y * 0.12, -0.18, 0.18))
        hat_vel_z = 0.78 * hat_vel_z + 0.22 * float(np.clip(-head_vel.x * 0.14, -0.22, 0.22))
        phase = f * 0.20

        for side, s in [(".L", 1.0), (".R", -1.0)]:
            for eb_n, amp in [(f"Ear.01{side}", 0.025), (f"Ear.02{side}", 0.045)]:
                epb = arm_obj.pose.bones.get(eb_n)
                if epb:
                    epb.rotation_quaternion = Quaternion((
                        1.0,
                        hat_vel_x * 0.35 + math.sin(phase) * amp,
                        0.0,
                        hat_vel_z * 0.35 + s * math.cos(phase) * amp * 0.5,
                    )).normalized()
                    epb.keyframe_insert(data_path="rotation_quaternion", frame=f)

        for hb_n, mult, amp, lag in [
            ("Hat.01", 0.45, 0.018, 0.0),
            ("Hat.02", 0.85, 0.032, 0.5),
            ("Hat.03", 1.25, 0.048, 1.0),
            ("HatBell", 1.75, 0.075, 1.5),
        ]:
            hpb = arm_obj.pose.bones.get(hb_n)
            if hpb:
                hpb.rotation_quaternion = Quaternion((
                    1.0,
                    hat_vel_x * mult + math.sin(phase - lag) * amp,
                    0.0,
                    hat_vel_z * mult + math.cos(phase - lag) * amp * 0.7,
                )).normalized()
                hpb.keyframe_insert(data_path="rotation_quaternion", frame=f)

        for bb_n, mult, amp, lag in [("Beard.01", 0.55, 0.020, 0.3), ("Beard.02", 0.95, 0.036, 0.8)]:
            bpb = arm_obj.pose.bones.get(bb_n)
            if bpb:
                bpb.rotation_quaternion = Quaternion((
                    1.0,
                    hat_vel_x * mult + math.sin(phase - lag) * amp,
                    0.0,
                    hat_vel_z * mult * 0.6 + math.cos(phase - lag) * amp * 0.4,
                )).normalized()
                bpb.keyframe_insert(data_path="rotation_quaternion", frame=f)

    scene = bpy.context.scene
    scene.render.fps = int(round(fps))
    scene.frame_start = 1
    scene.frame_end = T
    scene.frame_set(1)
    return True, f"Video-to-Motion '{action_name}' ({T} sličica @ {fps:.0f} fps) prebačen na Elf #10 (Urar + Kapa + Brada + Naočale)!"


# ============================================================================
# 5. BLENDER OPERATORI I N-PANEL (`Elf Rig Studio`)
# ============================================================================
class ELF01_OT_SelectModelTransform(bpy.types.Operator):
    bl_idname = "elf01.select_model_transform"
    bl_label = "Odaberi Model za Poravnanje (G/R/S)"
    bl_description = "Odabire HEAD AND HAIR, HAT ili BODY s aktivnim Move/Rotate/Scale gizmom"
    bl_options = {"REGISTER", "UNDO"}

    target_name: bpy.props.StringProperty(default="HEAD AND HAIR")

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_name)
        if not obj:
            self.report({"WARNING"}, f"Objekt '{self.target_name}' nije pronađen.")
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.transform")
        except Exception:
            pass
        self.report({"INFO"}, f"Odabran '{self.target_name}'. Koristi G (pomak), R (rotacija) ili S (skaliranje).")
        return {"FINISHED"}


class ELF01_OT_OffsetHeadForTest(bpy.types.Operator):
    bl_idname = "elf01.offset_head_test"
    bl_label = "Postavi Poziciju Glave ili Kape"
    bl_description = "Odvoji glavu/kapu +15 cm za ručno spajanje ili ih vrati na default poziciju"
    bl_options = {"REGISTER", "UNDO"}

    target_name: bpy.props.StringProperty(default="HEAD AND HAIR")
    mode: bpy.props.StringProperty(default="SNAP")

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_name)
        if not obj:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if self.target_name == "HAT":
            base_piv = Vector(DEFAULT_HAT_PIVOT)
            offset_vec = Vector((0.0, 0.0, 0.15))
        elif self.target_name == "GLASSES":
            base_piv = Vector(DEFAULT_GLASSES_PIVOT)
            offset_vec = Vector((0.0, -0.15, 0.0))
        elif self.target_name == "PROP":
            base_piv = Vector(DEFAULT_PROP_PIVOT)
            offset_vec = Vector((-0.15, -0.10, 0.0))
        else:
            base_piv = Vector(DEFAULT_HEAD_PIVOT)
            offset_vec = Vector((0.0, 0.0, 0.15))
        if self.mode == "LIFT":
            obj.location = base_piv + offset_vec
            self.report({"INFO"}, f"'{self.target_name}' odmaknut +15 cm — namjesti ga ručno (G) na mjesto!")
        else:
            obj.location = base_piv
            obj.rotation_euler = (0.0, 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)
            sync_head_and_hat_bones_to_meshes(context)
            self.report({"INFO"}, f"'{self.target_name}' vraćen na predviđeno mjesto i usklađen s kostima.")
        return {"FINISHED"}


class ELF01_OT_SculptGrabMode(bpy.types.Operator):
    bl_idname = "elf01.sculpt_grab_mode"
    bl_label = "Sculpt Mode: Grab Četka"
    bl_description = "Ulazi u Sculpt Mode s Grab četkom za fino namještanje spoja vrata, ovratnika, kape ili naočala"
    bl_options = {"REGISTER", "UNDO"}

    target_name: bpy.props.StringProperty(default="HEAD AND HAIR")

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_name)
        if not obj:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="SCULPT")
        # Keep X-mirror off for asymmetric HAT tail and asymmetric GLASSES loupe, on for BODY and HEAD
        obj.use_mesh_mirror_x = (self.target_name not in ("HAT", "GLASSES"))
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin_brush.Grab")
            context.scene.tool_settings.unified_paint_settings.size = 85
        except Exception:
            pass
        self.report({"INFO"}, f"Sculpt Grab četka aktivna na '{self.target_name}' (F = veličina četke).")
        return {"FINISHED"}


class ELF01_OT_ConfirmModelAlignment(bpy.types.Operator):
    bl_idname = "elf01.confirm_model_alignment"
    bl_label = "Potvrdi Poravnanje Modela (Sync Kosti Glave i Kape)"
    bl_description = "Primjenjuje transformacije na HEAD AND HAIR, HAT i BODY te automatski pomiče kosti glave, brade i kape"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ok, msg = sync_head_and_hat_bones_to_meshes(context)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_EditBonesSymmetry(bpy.types.Operator):
    bl_idname = "elf01.edit_bones_symmetry"
    bl_label = "Uredi Kosti (Edit Mode + Simetrija)"
    bl_description = "Prebacuje ARM_Elf_Hero u Edit Mode s uključenim X-Axis Mirrorom"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        arm_obj.select_set(True)
        context.view_layer.objects.active = arm_obj
        arm_obj.show_in_front = True
        arm_obj.data.use_mirror_x = True
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.move")
        except Exception:
            pass
        self.report({"INFO"}, "Edit Mode aktivan (X-Axis Mirror UKLJUČEN). Pomicanje .L kosti automatski zrcali .R kost!")
        return {"FINISHED"}


class ELF01_OT_FocusRegion(bpy.types.Operator):
    bl_idname = "elf01.focus_region"
    bl_label = "Fokusiraj Kameru na Regiju"
    bl_description = "Zumira 3D Viewport na odabranu regiju kostiju (Šake, Glava/Brada, Kapa, Cijelo tijelo)"
    bl_options = {"REGISTER", "UNDO"}

    region: bpy.props.StringProperty(default="ALL")

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        arm_obj.select_set(True)
        context.view_layer.objects.active = arm_obj
        arm_obj.data.use_mirror_x = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.armature.select_all(action="DESELECT")

        for eb in arm_obj.data.edit_bones:
            match = False
            if self.region == "HAND_L" and (eb.name.endswith(".L") and any(k in eb.name for k in ["Hand", "Thumb", "Index", "Middle", "Ring", "Pinky"])):
                match = True
            elif self.region == "HAND_R" and (eb.name.endswith(".R") and any(k in eb.name for k in ["Hand", "Thumb", "Index", "Middle", "Ring", "Pinky"])):
                match = True
            elif self.region == "HEAD" and any(k in eb.name for k in ["Neck", "Head", "Jaw", "Beard", "ForeheadLoupe", "Eye", "Ear", "Mustache"]):
                match = True
            elif self.region == "HAT" and any(k in eb.name for k in ["Hat", "Head"]):
                match = True
            elif self.region == "ALL":
                match = True
            if match:
                eb.select = True
                eb.select_head = True
                eb.select_tail = True

        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for reg in area.regions:
                    if reg.type == "WINDOW":
                        with context.temp_override(area=area, region=reg):
                            bpy.ops.view3d.view_selected()
                        break
        return {"FINISHED"}


class ELF01_OT_FilterBoneCollections(bpy.types.Operator):
    bl_idname = "elf01.filter_bone_collections"
    bl_label = "Filtriraj Kolekcije Kostiju"
    bl_description = "Prikazuje sve kosti ili samo odabranu grupu (Prsti / Glava / Kapa)"
    bl_options = {"REGISTER", "UNDO"}

    group: bpy.props.StringProperty(default="ALL")

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj or not hasattr(arm_obj.data, "collections"):
            return {"CANCELLED"}
        for col in arm_obj.data.collections:
            if self.group == "ALL":
                col.is_visible = True
            else:
                col.is_visible = (col.name == self.group)
        return {"FINISHED"}


class ELF01_OT_ToggleBoneDisplay(bpy.types.Operator):
    bl_idname = "elf01.toggle_bone_display"
    bl_label = "Stick / Octahedral Prikaz"
    bl_description = "Prebacuje prikaz kostiju između tankih linija (STICK) i klasičnih kostiju (OCTAHEDRAL)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        arm_obj.data.display_type = "STICK" if arm_obj.data.display_type != "STICK" else "OCTAHEDRAL"
        return {"FINISHED"}


class ELF01_OT_ToggleXRay(bpy.types.Operator):
    bl_idname = "elf01.toggle_xray"
    bl_label = "X-Ray Prozirnost Modela"
    bl_description = "Uključuje/isključuje poluprozirni X-Ray prikaz modela kako bi se kosti lakše vidjele unutar prstiju, glave i kape"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.show_xray = not space.shading.show_xray
                        space.shading.xray_alpha = 0.55
        return {"FINISHED"}


class ELF01_OT_BindRig(bpy.types.Operator):
    bl_idname = "elf01.bind_rig"
    bl_label = "Zaveži Rig za Modele (Bind Weights)"
    bl_description = "Veže BODY, HEAD AND HAIR i HAT prema trenutnim pozicijama kostiju i klizačima širine zglobova"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ok, msg = bind_character_to_rig(context)
        self.report({"INFO" if ok else "ERROR"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_JointRadiusPreset(bpy.types.Operator):
    bl_idname = "elf01.joint_radius_preset"
    bl_label = "Preset Oštrine Zglobova"
    bl_description = "Postavlja širinu prijelaza zglobova (u cm) za ruke, noge, kralježnicu i kapu te preračunava težine"
    bl_options = {"REGISTER", "UNDO"}

    arm_cm: bpy.props.FloatProperty(default=1.8)
    leg_cm: bpy.props.FloatProperty(default=1.8)
    spine_cm: bpy.props.FloatProperty(default=2.5)
    hat_cm: bpy.props.FloatProperty(default=2.0)

    def execute(self, context):
        context.scene.elf01_arm_joint_cm = self.arm_cm
        context.scene.elf01_leg_joint_cm = self.leg_cm
        context.scene.elf01_spine_joint_cm = self.spine_cm
        context.scene.elf01_hat_joint_cm = self.hat_cm
        ok, msg = bind_character_to_rig(context)
        self.report({"INFO" if ok else "WARNING"}, f"Zglobovi postavljeni (Ruke={self.arm_cm:.1f}cm, Kapa={self.hat_cm:.1f}cm). {msg}")
        return {"FINISHED" if ok else "CANCELLED"}


def enter_weight_paint_on_bone(context, target_mesh_name="BODY", bone_name=None):
    """
    Puts `ARM_Elf_Hero` in POSE mode + `target_mesh_name` (`BODY`, `HEAD AND HAIR`, or `HAT`)
    in WEIGHT_PAINT mode simultaneously with Auto-Normalize and Cage Deform enabled!
    """
    arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
    mesh_obj = bpy.data.objects.get(target_mesh_name)
    if not mesh_obj:
        return False, f"Mesh '{target_mesh_name}' nije pronađen."

    for mod in mesh_obj.modifiers:
        if mod.type == "ARMATURE":
            mod.show_in_editmode = True
            mod.show_on_cage = True

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    if arm_obj:
        arm_obj.select_set(True)
        context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="POSE")
        if bone_name and bone_name in arm_obj.pose.bones:
            for pb in arm_obj.pose.bones:
                if hasattr(pb, "select"):
                    pb.select = (pb.name == bone_name)
                elif hasattr(pb.bone, "select"):
                    pb.bone.select = (pb.name == bone_name)
            arm_obj.data.bones.active = arm_obj.data.bones[bone_name]
        bpy.ops.object.mode_set(mode="OBJECT")
        arm_obj.select_set(True)

    mesh_obj.select_set(True)
    context.view_layer.objects.active = mesh_obj
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")

    ts = context.scene.tool_settings
    ts.use_auto_normalize = True
    if hasattr(ts, "use_multipaint"):
        ts.use_multipaint = False
    # Disable X-mirror on HAT and GLASSES because the hat tail and double-loupe are asymmetric (+X)
    is_symmetric_mesh = (target_mesh_name not in ("HAT", "GLASSES"))
    mesh_obj.use_mesh_mirror_x = is_symmetric_mesh
    if hasattr(mesh_obj.data, "use_mirror_vertex_groups"):
        mesh_obj.data.use_mirror_vertex_groups = is_symmetric_mesh

    if bone_name and bone_name in mesh_obj.vertex_groups:
        mesh_obj.vertex_groups.active_index = mesh_obj.vertex_groups[bone_name].index

    for area in context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.overlay.show_wpaint_contours = False
                    space.overlay.show_weight = True
                    space.overlay.show_bones = True

    active_vg = mesh_obj.vertex_groups.active.name if mesh_obj.vertex_groups.active else "None"
    return True, f"Weight Paint aktivan na '{target_mesh_name}' -> Kost: '{active_vg}'."


class ELF01_OT_SelectWeightBone(bpy.types.Operator):
    bl_idname = "elf01.select_weight_bone"
    bl_label = "Uredi Težine Odabrane Kosti"
    bl_description = "Ulazi u Weight Paint Mode na odgovarajućem modelu (BODY, HEAD AND HAIR ili HAT) i prikazuje težine odabrane kosti"
    bl_options = {"REGISTER", "UNDO"}

    target_mesh: bpy.props.StringProperty(default="BODY")
    bone_name: bpy.props.StringProperty(default="UpperArm.L")

    def execute(self, context):
        ok, msg = enter_weight_paint_on_bone(context, self.target_mesh, self.bone_name)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_SetWeightBrush(bpy.types.Operator):
    bl_idname = "elf01.set_weight_brush"
    bl_label = "Postavi Četku za Težine"
    bl_description = "Jednim klikom postavlja četku za dodavanje (100%), zglob (50%), brisanje (0%) ili omekšavanje ruba (Blur)"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.StringProperty(default="ADD_100")

    def execute(self, context):
        if not context.object or context.object.mode != "WEIGHT_PAINT":
            enter_weight_paint_on_bone(context, "BODY", None)

        ts = context.scene.tool_settings
        wp = ts.weight_paint
        ups = getattr(wp, "unified_paint_settings", None) or getattr(ts, "unified_paint_settings", None)

        if self.mode == "BLUR":
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin_brush.Blur")
            except Exception:
                pass
            if wp.brush:
                wp.brush.strength = 0.55
            self.report({"INFO"}, "Četka: OMEKŠAJ RUB (Blur) — prijeđi preko zgloba za glatki prijelaz.")
        else:
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin_brush.Draw")
            except Exception:
                pass
            target_w = 1.0
            strength = 1.0
            if self.mode == "ADD_100":
                target_w, strength = 1.0, 1.0
            elif self.mode == "HALF_50":
                target_w, strength = 0.5, 0.65
            elif self.mode == "SUB_0":
                target_w, strength = 0.0, 1.0

            if ups:
                if hasattr(ups, "use_unified_weight"):
                    ups.use_unified_weight = True
                if hasattr(ups, "weight"):
                    ups.weight = target_w
                if hasattr(ups, "use_unified_strength"):
                    ups.use_unified_strength = True
                if hasattr(ups, "strength"):
                    ups.strength = strength
            if wp.brush:
                wp.brush.weight = target_w
                wp.brush.strength = strength
                if hasattr(wp.brush, "blend"):
                    wp.brush.blend = "MIX"
            self.report({"INFO"}, f"Četka: Težina = {int(target_w*100)}%, Jačina = {int(strength*100)}% (Auto-Normalize aktivan).")
        return {"FINISHED"}


class ELF01_OT_SharpenOrSmoothWeights(bpy.types.Operator):
    bl_idname = "elf01.sharpen_smooth_weights"
    bl_label = "Izoštri ili Omekšaj Zglobove"
    bl_description = "Jednim klikom sužava (izoštrava) ili širi (omekšava) sve prijelaze zglobova na aktivnom modelu"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.StringProperty(default="SHARPEN")
    only_active: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        mesh_obj = context.object if (context.object and context.object.type == "MESH") else bpy.data.objects.get("BODY")
        if not mesh_obj or mesh_obj.type != "MESH":
            return {"CANCELLED"}

        prev_mode = mesh_obj.mode
        if prev_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if self.action == "SHARPEN":
            vgs = mesh_obj.vertex_groups
            active_idx = vgs.active_index
            for v in mesh_obj.data.vertices:
                if not v.groups:
                    continue
                gw = []
                for g in v.groups:
                    w = g.weight
                    if not self.only_active or g.group == active_idx:
                        w = smoothstep(0.14, 0.86, w)
                    gw.append((g.group, w))
                tot = sum(w for _, w in gw)
                if tot > 1e-8:
                    for gi, w in gw:
                        nw = w / tot
                        vgs[gi].add([v.index], nw if nw > 0.002 else 0.0, "REPLACE")
            msg = f"Zglobovi na '{mesh_obj.name}' izoštreni (-30% manji radijus savijanja)!"
        else:
            bpy.ops.object.select_all(action="DESELECT")
            mesh_obj.select_set(True)
            context.view_layer.objects.active = mesh_obj
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
            grp_mode = "ACTIVE" if self.only_active else "ALL"
            bpy.ops.object.vertex_group_smooth(group_select_mode=grp_mode, factor=0.35, repeat=1)
            bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
            bpy.ops.object.mode_set(mode="OBJECT")
            msg = f"Zglobovi na '{mesh_obj.name}' omekšani (+30% širi prijelaz)!"

        if prev_mode == "WEIGHT_PAINT":
            enter_weight_paint_on_bone(context, mesh_obj.name, None)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ELF01_OT_MirrorWeightsLR(bpy.types.Operator):
    bl_idname = "elf01.mirror_weights_lr"
    bl_label = "Zrcali Ručne Težine (.L -> .R)"
    bl_description = "Kopira sve ručno obojane težine s lijeve strane (.L / Left*) na desnu stranu (.R / Right*) pomoću 3D KD-stabla"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mesh_obj = context.object if (context.object and context.object.type == "MESH") else bpy.data.objects.get("BODY")
        if not mesh_obj or mesh_obj.type != "MESH":
            return {"CANCELLED"}

        prev_mode = mesh_obj.mode
        if prev_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        me = mesh_obj.data
        kd = KDTree(len(me.vertices))
        for i, v in enumerate(me.vertices):
            kd.insert(v.co, i)
        kd.balance()

        vgs = mesh_obj.vertex_groups
        vg_by_name = {g.name: g for g in vgs}

        mirror_map = {}
        for g in vgs:
            n = g.name
            if n.endswith(".R"):
                l_name = n[:-2] + ".L"
                if l_name in vg_by_name:
                    mirror_map[g.index] = vg_by_name[l_name].index
            elif n.startswith("Right"):
                l_name = "Left" + n[5:]
                if l_name in vg_by_name:
                    mirror_map[g.index] = vg_by_name[l_name].index
            elif n.endswith(".L"):
                r_name = n[:-2] + ".R"
                if r_name in vg_by_name:
                    mirror_map[g.index] = vg_by_name[r_name].index
            elif n.startswith("Left"):
                r_name = "Right" + n[4:]
                if r_name in vg_by_name:
                    mirror_map[g.index] = vg_by_name[r_name].index
            else:
                mirror_map[g.index] = g.index

        src_weights = [{g.group: g.weight for g in v.groups} for v in me.vertices]

        mirrored_count = 0
        for v in me.vertices:
            if v.co.x < -0.001:
                mirror_co = Vector((-v.co.x, v.co.y, v.co.z))
                _, src_idx, dist = kd.find(mirror_co)
                if dist < 0.015:
                    sw = src_weights[src_idx]
                    for g in vgs:
                        vgs[g.index].remove([v.index])
                    for src_gi, w in sw.items():
                        dst_gi = mirror_map.get(src_gi, src_gi)
                        if w > 0.001:
                            vgs[dst_gi].add([v.index], w, "REPLACE")
                    mirrored_count += 1

        if prev_mode == "WEIGHT_PAINT":
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        self.report({"INFO"}, f"Zrcaljeno {mirrored_count} vrhova s Lijeve (.L) na Desnu (.R) stranu!")
        return {"FINISHED"}


class ELF01_OT_BendJointsTestPose(bpy.types.Operator):
    bl_idname = "elf01.bend_joints_test_pose"
    bl_label = "Savij Laktove, Koljena, Bradu i Kapu (Test Poza)"
    bl_description = "Savija laktove, koljeno, bradu i kapu kako bi u stvarnom vremenu vidio i bojao težine na savijenim zglobovima"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        arm_obj.animation_data_clear()
        arm_obj.data.pose_position = "POSE"
        for pb in arm_obj.pose.bones:
            pb.rotation_mode = "XYZ"
            pb.location = (0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.scale = (1, 1, 1)

        if "UpperArm.L" in arm_obj.pose.bones:
            arm_obj.pose.bones["UpperArm.L"].rotation_euler = Euler((math.radians(15), 0, math.radians(-20)), "XYZ")
        if "ForeArm.L" in arm_obj.pose.bones:
            arm_obj.pose.bones["ForeArm.L"].rotation_euler = Euler((math.radians(55), math.radians(15), math.radians(-65)), "XYZ")
        if "UpperArm.R" in arm_obj.pose.bones:
            arm_obj.pose.bones["UpperArm.R"].rotation_euler = Euler((math.radians(25), 0, math.radians(30)), "XYZ")
        if "ForeArm.R" in arm_obj.pose.bones:
            arm_obj.pose.bones["ForeArm.R"].rotation_euler = Euler((math.radians(65), math.radians(-15), math.radians(65)), "XYZ")
        if "LeftUpLeg" in arm_obj.pose.bones:
            arm_obj.pose.bones["LeftUpLeg"].rotation_euler = Euler((math.radians(48), 0, math.radians(-8)), "XYZ")
        if "LeftLeg" in arm_obj.pose.bones:
            arm_obj.pose.bones["LeftLeg"].rotation_euler = Euler((math.radians(-72), 0, 0), "XYZ")
        if "LeftFoot" in arm_obj.pose.bones:
            arm_obj.pose.bones["LeftFoot"].rotation_euler = Euler((math.radians(22), 0, 0), "XYZ")
        if "Head" in arm_obj.pose.bones:
            arm_obj.pose.bones["Head"].rotation_euler = Euler((math.radians(8), math.radians(-10), math.radians(12)), "XYZ")
        if "Beard.01" in arm_obj.pose.bones:
            arm_obj.pose.bones["Beard.01"].rotation_euler = Euler((math.radians(-12), 0, math.radians(-8)), "XYZ")
        if "Beard.02" in arm_obj.pose.bones:
            arm_obj.pose.bones["Beard.02"].rotation_euler = Euler((math.radians(-15), 0, math.radians(-10)), "XYZ")
        if "Hat.01" in arm_obj.pose.bones:
            arm_obj.pose.bones["Hat.01"].rotation_euler = Euler((math.radians(10), 0, math.radians(-12)), "XYZ")
        if "Hat.02" in arm_obj.pose.bones:
            arm_obj.pose.bones["Hat.02"].rotation_euler = Euler((math.radians(14), 0, math.radians(-18)), "XYZ")
        if "Hat.03" in arm_obj.pose.bones:
            arm_obj.pose.bones["Hat.03"].rotation_euler = Euler((math.radians(18), 0, math.radians(-22)), "XYZ")

        self.report({"INFO"}, "Testna poza aktivna (Ruke, Noge, Glava, Brada i Kapa)!")
        return {"FINISHED"}


class ELF01_OT_TestPoseMode(bpy.types.Operator):
    bl_idname = "elf01.test_pose_mode"
    bl_label = "Testiraj Pozu (Pose Mode)"
    bl_description = "Ulazi u Pose Mode s alatom za rotaciju kostiju"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        arm_obj.select_set(True)
        context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="POSE")
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.rotate")
        except Exception:
            pass
        return {"FINISHED"}


class ELF01_OT_ResetPose(bpy.types.Operator):
    bl_idname = "elf01.reset_pose"
    bl_label = "Resetiraj Pozu (Rest Pose)"
    bl_description = "Vraća sve kosti u početnu A-pozu"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        arm_obj.animation_data_clear()
        for pb in arm_obj.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.scale = (1, 1, 1)
        return {"FINISHED"}


class ELF01_OT_ConfirmRigAndInitialBind(bpy.types.Operator):
    bl_idname = "elf01.confirm_rig_and_initial_bind"
    bl_label = "Potvrdi Rig -> Izračunaj Početni Bind za Weight Paint"
    bl_description = "Izlazi iz Edit Modea, sprema pozicije kostiju, otključava i računa početne oštre težine (Tijelo + Glava + Kapa) te otvara Weight Paint"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        context.scene.elf01_lock_weights = False
        arm_obj["user_rig_aligned"] = True
        # Spremi točne koordinate kostiju unutar .blend datoteke (za suradnike na drugim računalima)
        bone_snapshot = {}
        for b in arm_obj.data.bones:
            bone_snapshot[b.name] = {
                "head": [round(float(v), 6) for v in b.head_local],
                "tail": [round(float(v), 6) for v in b.tail_local],
            }
        arm_obj["custom_bone_table_json"] = json.dumps(bone_snapshot)
        ok, msg = bind_character_to_rig(context, force=True)
        if ok:
            enter_weight_paint_on_bone(context, "BODY", "UpperArm.L")
        self.report({"INFO" if ok else "WARNING"}, f"Rig potvrđen! {msg} Sada možeš ručno urediti težine u Koraku 3.")
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_LockManualWeightsHandoff(bpy.types.Operator):
    bl_idname = "elf01.lock_manual_weights_handoff"
    bl_label = "Potvrdi i Zaključaj Ručne Težine (Predaj Agentu)"
    bl_description = "Normalizira sve ručno obojane težine (Tijelo, Glava, Kapa), vraća Rest pozu, zaključava težine od brisanja i sprema .blend za Agenta"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if arm_obj:
            arm_obj.animation_data_clear()
            for pb in arm_obj.pose.bones:
                pb.location = (0, 0, 0)
                pb.rotation_quaternion = (1, 0, 0, 0)
                pb.rotation_euler = (0, 0, 0)
                pb.scale = (1, 1, 1)
            arm_obj["user_weights_locked"] = True

        context.scene.elf01_lock_weights = True
        try:
            if bpy.data.filepath:
                bpy.ops.wm.save_mainfile()
        except Exception:
            pass

        self.report(
            {"INFO"},
            "Ručne težine (Tijelo + Glava + Kapa) ZAKLJUČANE i spremljene u .blend! Javi Agentu u chatu da preuzme Korak 4.",
        )
        return {"FINISHED"}


class ELF01_OT_ExportFinalGLB(bpy.types.Operator):
    bl_idname = "elf01.export_final_glb"
    bl_label = "Izvezi Finalni Rigged GLB (Čuva Ručne Težine)"
    bl_description = "Izvozi BODY + HEAD AND HAIR + HAT + ARM_Elf_Hero s tvojim ručno obojanim težinama u GLB"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        export_dir = GLB_DIR
        if not os.path.exists(DEFAULT_MAC_PROJECT_DIR) and bpy.data.filepath:
            export_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
        os.makedirs(export_dir, exist_ok=True)
        out_glb = os.path.join(export_dir, "elf10_S3_10_combined_rigged.glb")
        bpy.ops.object.select_all(action="DESELECT")
        for nm in ("ARM_Elf_Hero", "BODY", "HEAD AND HAIR", "HAT", "GLASSES", "PROP"):
            o = bpy.data.objects.get(nm)
            if o:
                o.select_set(True)
        bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=True)
        self.report({"INFO"}, f"Izvezen GLB s ručnim težinama (Tijelo + Glava + Kapa + Dodaci): {out_glb}")
        return {"FINISHED"}


class ELF01_OT_ApplyMixamoPreset(bpy.types.Operator):
    bl_idname = "elf01.apply_mixamo_preset"
    bl_label = "Primijeni Mixamo Animaciju"
    bl_description = "Uvozi odabranu Mixamo FBX animaciju i prebacuje ju na Elf #10 (čuva ručne težine Tijela, Glave i Kape!)"
    bl_options = {"REGISTER", "UNDO"}

    fbx_filename: bpy.props.StringProperty(default="Happy Idle.fbx")

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        fbx_path = os.path.join(MIXAMO_DIR, self.fbx_filename)
        ok, msg = retarget_mixamo_fbx(arm_obj, fbx_path)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_ApplyMocapNPZ(bpy.types.Operator):
    bl_idname = "elf01.apply_mocap_npz"
    bl_label = "Primijeni Video-to-Motion (133-Keypoint 3D NPZ)"
    bl_description = "Prebacuje 3D Video-to-Motion snimku (.npz iz RTMW3D + OpenCap LSTM) izravno na Elf #10 bez diranja ručnih težina"
    bl_options = {"REGISTER", "UNDO"}

    npz_filename: bpy.props.StringProperty(default="dji_0057_mocap.npz")

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        npz_path = os.path.join(ROOT, "assets", "animations", self.npz_filename)
        ok, msg = retarget_mocap_npz(arm_obj, npz_path)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


_GIZMO_EMPTY_LAST_MAT = {}
_GIZMO_RECALC_BUSY = False


def on_depsgraph_gizmo_empty_moved(scene, depsgraph=None):
    """
    Live handler when the user moves (G), rotates (R), or scales (S) a `WGT_GIZMO_*`
    3D Empty ring/sphere in the 3D Viewport: automatically recalculates that joint/armpit zone!
    """
    global _GIZMO_RECALC_BUSY
    if _GIZMO_RECALC_BUSY:
        return
    if getattr(scene, "elf01_lock_weights", False):
        return
    if not getattr(scene, "elf01_live_gizmo_update", True):
        return
    if not getattr(scene, "elf01_use_3d_gizmo_empties", False):
        return
    try:
        active_obj = bpy.context.view_layer.objects.active if (bpy.context and bpy.context.view_layer) else None
    except Exception:
        return
    if not active_obj or not active_obj.name.startswith("WGT_GIZMO_"):
        return
    mat_key = tuple(round(float(v), 4) for row in active_obj.matrix_world for v in row)
    if _GIZMO_EMPTY_LAST_MAT.get(active_obj.name) == mat_key:
        return
    _GIZMO_EMPTY_LAST_MAT[active_obj.name] = mat_key
    zone_map = {
        "WGT_GIZMO_Pazuh.L": "ARMPIT",
        "WGT_GIZMO_Lakat.L": "ELBOW",
        "WGT_GIZMO_Zapesce.L": "WRIST",
        "WGT_GIZMO_Kuk.L": "HIP",
        "WGT_GIZMO_Koljeno.L": "KNEE",
    }
    zone = zone_map.get(active_obj.name, "ARMPIT")
    try:
        _GIZMO_RECALC_BUSY = True
        recalc_armpit_and_joint_zone_only(bpy.context, zone=zone)
    finally:
        _GIZMO_RECALC_BUSY = False


def on_live_weight_param_change(self, context):
    """
    Live callback when the user drags any 3D Gizmo arrow or N-panel slider for Armpit / Joint Fade:
    Immediately recalculates ONLY the affected joint zone (`ARMPIT`, `ELBOW`, `WRIST`, `HIP`, `KNEE`)
    so the user sees the mesh deform in real time while the character is posed!
    """
    scn = context.scene
    if getattr(scn, "elf01_lock_weights", False):
        return
    if not getattr(scn, "elf01_live_gizmo_update", True):
        return
    active_zone = getattr(scn, "elf01_active_gizmo_zone", "ARMPIT")
    recalc_armpit_and_joint_zone_only(context, zone=active_zone)


def ensure_3d_weight_gizmo_empties(context, visible=True):
    """
    Creates or updates selectable 3D Wireframe Empty Gizmo rings/spheres (`WGT_GIZMO_Pazuh.L`,
    `WGT_GIZMO_Lakat.L`, `WGT_GIZMO_Zapesce.L`, `WGT_GIZMO_Kuk.L`, `WGT_GIZMO_Koljeno.L`)
    so the user can also press G (move cut plane), R (tilt cut angle), or S (scale fade width)
    directly in the 3D Viewport!
    """
    arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
    if not arm_obj:
        return []

    col_name = "WGT_Gizmos_Elf"
    col = bpy.data.collections.get(col_name)
    if not col:
        col = bpy.data.collections.new(col_name)
        context.scene.collection.children.link(col)

    mw_arm = arm_obj.matrix_world
    bsegs = {b.name: (mw_arm @ b.head_local, mw_arm @ b.tail_local) for b in arm_obj.data.bones if b.use_deform}
    scn = context.scene
    ap_cfg = get_armpit_and_joint_gizmo_config(scn, bsegs, ".L")

    gizmo_specs = [
        ("WGT_GIZMO_Pazuh.L", "CIRCLE", ap_cfg["p_armpit"], 0.085, (0.0, math.radians(62), 0.0)),
        ("WGT_GIZMO_Lakat.L", "SPHERE", bsegs["ForeArm.L"][0], 0.055, (0.0, 0.0, 0.0)),
        ("WGT_GIZMO_Zapesce.L", "SPHERE", bsegs["Hand.L"][0], 0.042, (0.0, 0.0, 0.0)),
        ("WGT_GIZMO_Kuk.L", "CIRCLE", Vector((0.10, 0.0, bsegs["LeftUpLeg"][0].z - 0.015)), 0.085, (0.0, math.radians(8), 0.0)),
        ("WGT_GIZMO_Koljeno.L", "SPHERE", bsegs["LeftLeg"][0], 0.060, (0.0, 0.0, 0.0)),
    ]

    created = []
    for gname, dtype, loc, radius, rot in gizmo_specs:
        obj = bpy.data.objects.get(gname)
        if not obj:
            obj = bpy.data.objects.new(gname, None)
            obj.empty_display_type = dtype
            obj.empty_display_size = radius
            obj.show_in_front = True
            obj.show_name = True
            obj.location = loc
            obj.rotation_euler = rot
            col.objects.link(obj)
        obj.hide_viewport = not visible
        obj.hide_render = True
        created.append(obj)
    return created


class ELF01_GGT_WeightZoneGizmoGroup(bpy.types.GizmoGroup):
    """
    Interactive 3D Viewport Gizmo Group that draws draggable 3D Arrows & Rings directly on the
    Armpit (`Pazuh.L`), Elbow (`Lakat.L`), Wrist (`Zapešće.L`), Hip (`Kuk.L`), and Knee (`Koljeno.L`)!
    Dragging the arrows in the 3D Viewport adjusts the Joint Plane Position and Fade Width in real time!
    """
    bl_idname = "ELF01_GGT_weight_zone_gizmos"
    bl_label = "Elf 3D Weight & Pazuh Gizmos"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context):
        scn = context.scene
        if not getattr(scn, "elf01_show_weight_gizmos", True):
            return False
        return bpy.data.objects.get("ARM_Elf_Hero") is not None and bpy.data.objects.get("BODY") is not None

    def setup(self, context):
        # 1. Armpit Inset Arrow (Magenta — moves armpit cut plane inward/outward)
        gz_ap_pos = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz_ap_pos.draw_style = "NORMAL"
        gz_ap_pos.color = (1.0, 0.22, 0.65)
        gz_ap_pos.alpha = 0.92
        gz_ap_pos.color_highlight = (1.0, 0.55, 0.85)
        gz_ap_pos.alpha_highlight = 1.0
        gz_ap_pos.scale_basis = 0.14
        gz_ap_pos.target_set_prop("offset", context.scene, "elf01_armpit_inset_cm")
        self.gz_ap_pos = gz_ap_pos

        # 2. Armpit Height Arrow (Gold — moves armpit crease up/down)
        gz_ap_drop = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz_ap_drop.draw_style = "NORMAL"
        gz_ap_drop.color = (1.0, 0.82, 0.15)
        gz_ap_drop.alpha = 0.92
        gz_ap_drop.color_highlight = (1.0, 0.95, 0.45)
        gz_ap_drop.alpha_highlight = 1.0
        gz_ap_drop.scale_basis = 0.13
        gz_ap_drop.target_set_prop("offset", context.scene, "elf01_armpit_drop_cm")
        self.gz_ap_drop = gz_ap_drop

        # 3. Armpit Fade Width Arrow (Cyan Box/Stem — widens/narrows armpit fade zone)
        gz_ap_fade = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz_ap_fade.draw_style = "BOX"
        gz_ap_fade.color = (0.15, 0.90, 0.95)
        gz_ap_fade.alpha = 0.92
        gz_ap_fade.color_highlight = (0.55, 1.0, 1.0)
        gz_ap_fade.alpha_highlight = 1.0
        gz_ap_fade.scale_basis = 0.13
        gz_ap_fade.target_set_prop("offset", context.scene, "elf01_armpit_fade_cm")
        self.gz_ap_fade = gz_ap_fade

        # 4. Armpit Crease Plane Ring (Visual 3D Ring showing the exact angled cut plane)
        gz_ap_ring = self.gizmos.new("GIZMO_GT_dial_3d")
        gz_ap_ring.color = (1.0, 0.35, 0.20)
        gz_ap_ring.alpha = 0.75
        gz_ap_ring.scale_basis = 0.09
        gz_ap_ring.use_draw_value = False
        self.gz_ap_ring = gz_ap_ring

        # 5. Elbow Fade Arrow (Green Box — widens/narrows elbow fade)
        gz_elb_fade = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz_elb_fade.draw_style = "BOX"
        gz_elb_fade.color = (0.20, 0.95, 0.40)
        gz_elb_fade.alpha = 0.90
        gz_elb_fade.color_highlight = (0.55, 1.0, 0.65)
        gz_elb_fade.alpha_highlight = 1.0
        gz_elb_fade.scale_basis = 0.12
        gz_elb_fade.target_set_prop("offset", context.scene, "elf01_elbow_fade_cm")
        self.gz_elb_fade = gz_elb_fade

        # 6. Elbow Cut Offset Arrow (Yellow — shifts elbow cut plane along arm)
        gz_elb_off = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz_elb_off.draw_style = "NORMAL"
        gz_elb_off.color = (0.95, 0.85, 0.20)
        gz_elb_off.alpha = 0.90
        gz_elb_off.scale_basis = 0.12
        gz_elb_off.target_set_prop("offset", context.scene, "elf01_elbow_offset_cm")
        self.gz_elb_off = gz_elb_off

    def refresh(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return
        mw_arm = arm_obj.matrix_world
        bsegs = {b.name: (mw_arm @ b.head_local, mw_arm @ b.tail_local) for b in arm_obj.data.bones if b.use_deform}
        if "UpperArm.L" not in bsegs or "ForeArm.L" not in bsegs:
            return

        scn = context.scene
        ap_cfg = get_armpit_and_joint_gizmo_config(scn, bsegs, ".L")
        p_ap = ap_cfg["p_armpit"]
        n_ap = ap_cfg["n_armpit"]
        fa_h, fa_t = bsegs["ForeArm.L"]
        u_fa = (fa_t - fa_h).normalized()

        # Position Armpit Gizmos at p_ap
        rot_in = Vector((-1.0, 0.0, 0.0)).to_track_quat("Z", "Y").to_matrix().to_4x4()
        rot_in.translation = p_ap
        self.gz_ap_pos.matrix_basis = rot_in

        rot_down = Vector((0.0, 0.0, -1.0)).to_track_quat("Z", "Y").to_matrix().to_4x4()
        rot_down.translation = p_ap + Vector((0.0, -0.02, 0.0))
        self.gz_ap_drop.matrix_basis = rot_down

        rot_fade = Vector((0.0, -1.0, 0.0)).to_track_quat("Z", "Y").to_matrix().to_4x4()
        rot_fade.translation = p_ap + Vector((0.0, -0.04, 0.0))
        self.gz_ap_fade.matrix_basis = rot_fade

        rot_ring = n_ap.to_track_quat("Z", "Y").to_matrix().to_4x4()
        rot_ring.translation = p_ap
        self.gz_ap_ring.matrix_basis = rot_ring

        # Position Elbow Gizmos at fa_h
        rot_elb = u_fa.to_track_quat("Z", "Y").to_matrix().to_4x4()
        rot_elb.translation = fa_h
        self.gz_elb_off.matrix_basis = rot_elb

        rot_elb_f = Vector((0.0, -1.0, 0.0)).to_track_quat("Z", "Y").to_matrix().to_4x4()
        rot_elb_f.translation = fa_h
        self.gz_elb_fade.matrix_basis = rot_elb_f


class ELF01_OT_ToggleWeightGizmos(bpy.types.Operator):
    bl_idname = "elf01.toggle_weight_gizmos"
    bl_label = "Prikaži / Sakrij 3D Weight Gizmo Kontrole"
    bl_description = "Uključuje/isključuje interaktivne 3D strelice i prstenove u Viewportu za fino uštimavanje pazuha i zglobova"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        scn.elf01_show_weight_gizmos = not getattr(scn, "elf01_show_weight_gizmos", True)
        ensure_3d_weight_gizmo_empties(context, visible=scn.elf01_show_weight_gizmos and scn.elf01_use_3d_gizmo_empties)
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
        state_str = "UKLJUČENI" if scn.elf01_show_weight_gizmos else "SAKRIVENI"
        self.report({"INFO"}, f"3D Weight Gizmo kontroleri u Viewportu: {state_str}")
        return {"FINISHED"}


class ELF01_OT_SelectWeightGizmoEmpty(bpy.types.Operator):
    bl_idname = "elf01.select_weight_gizmo_empty"
    bl_label = "Odaberi 3D Gizmo Zgloba u Viewportu (G / R / S)"
    bl_description = "Stvara i odabire 3D kružni Gizmo u Viewportu (G = pomakni rez zgloba, R = nagni kut pazuha, S = proširi/suzi fade)"
    bl_options = {"REGISTER", "UNDO"}

    gizmo_name: bpy.props.StringProperty(default="WGT_GIZMO_Pazuh.L")
    zone: bpy.props.StringProperty(default="ARMPIT")

    def execute(self, context):
        scn = context.scene
        scn.elf01_show_weight_gizmos = True
        scn.elf01_use_3d_gizmo_empties = True
        scn.elf01_active_gizmo_zone = self.zone
        ensure_3d_weight_gizmo_empties(context, visible=True)

        giz_obj = bpy.data.objects.get(self.gizmo_name)
        if not giz_obj:
            return {"CANCELLED"}

        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        giz_obj.select_set(True)
        context.view_layer.objects.active = giz_obj
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.move")
        except Exception:
            pass
        self.report(
            {"INFO"},
            f"Odabran '{self.gizmo_name}'! Koristi G (pomak), R (kut ravnine), S (širina fadea), pa klikni 'Primijeni 3D Gizmo na Zonu'.",
        )
        return {"FINISHED"}


class ELF01_OT_FixArmpitWeightsOnly(bpy.types.Operator):
    bl_idname = "elf01.fix_armpit_weights_only"
    bl_label = "Preračunaj Samo Odabranu Zonu (Pazuh / Zglob)"
    bl_description = "Preračunava čisti matematički fade samo u odabranoj zoni (npr. Pazuh .L + .R) prema 3D Gizmu i klizačima, čuvajući sve ostale ručne težine"
    bl_options = {"REGISTER", "UNDO"}

    zone: bpy.props.StringProperty(default="ARMPIT")

    def execute(self, context):
        context.scene.elf01_active_gizmo_zone = self.zone
        ok, msg = recalc_armpit_and_joint_zone_only(context, zone=self.zone)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_RelaxArmpitSeam(bpy.types.Operator):
    bl_idname = "elf01.relax_armpit_seam"
    bl_label = "Laplacian Relax Pazuha (Ugladi Zgužvane Vrhove)"
    bl_description = "Izvodi topološko zaglađivanje težina (Laplacian Relax) isključivo u naboru lijevog i desnog pazuha bez diranja ostatka tijela"
    bl_options = {"REGISTER", "UNDO"}

    iterations: bpy.props.IntProperty(default=3, min=1, max=15)

    def execute(self, context):
        ok, msg = relax_armpit_seam_weights(context, iterations=self.iterations, factor=0.45)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class ELF01_OT_TestArmpitPose(bpy.types.Operator):
    bl_idname = "elf01.test_armpit_pose"
    bl_label = "Test Poza za Pazuh (Spusti / Podigni Ruke)"
    bl_description = "Spušta ruke uz tijelo (-42°) ili ih podiže (+55°) kako bi odmah vidio i uštimao deformaciju pazuha pomoću 3D Gizma i klizača"
    bl_options = {"REGISTER", "UNDO"}

    pose_type: bpy.props.StringProperty(default="ARMS_DOWN")

    def execute(self, context):
        arm_obj = bpy.data.objects.get("ARM_Elf_Hero")
        if not arm_obj:
            return {"CANCELLED"}
        arm_obj.animation_data_clear()
        arm_obj.data.pose_position = "POSE"
        for pb in arm_obj.pose.bones:
            pb.rotation_mode = "XYZ"
            pb.location = (0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.scale = (1, 1, 1)

        if self.pose_type == "ARMS_DOWN":
            # Spusti ruke iz 45° A-poze uz tijelo — najvažniji test pazuha!
            if "Shoulder.L" in arm_obj.pose.bones:
                arm_obj.pose.bones["Shoulder.L"].rotation_euler = Euler((0, 0, math.radians(-8)), "XYZ")
            if "UpperArm.L" in arm_obj.pose.bones:
                arm_obj.pose.bones["UpperArm.L"].rotation_euler = Euler((math.radians(4), 0, math.radians(-38)), "XYZ")
            if "ForeArm.L" in arm_obj.pose.bones:
                arm_obj.pose.bones["ForeArm.L"].rotation_euler = Euler((math.radians(18), 0, math.radians(-10)), "XYZ")
            if "Shoulder.R" in arm_obj.pose.bones:
                arm_obj.pose.bones["Shoulder.R"].rotation_euler = Euler((0, 0, math.radians(8)), "XYZ")
            if "UpperArm.R" in arm_obj.pose.bones:
                arm_obj.pose.bones["UpperArm.R"].rotation_euler = Euler((math.radians(4), 0, math.radians(38)), "XYZ")
            if "ForeArm.R" in arm_obj.pose.bones:
                arm_obj.pose.bones["ForeArm.R"].rotation_euler = Euler((math.radians(18), 0, math.radians(10)), "XYZ")
            msg = "Test poza: RUKE SPUŠTENE UZ TIJELO (-42°) — povlači klizače pazuha ili 3D Gizmo za uštimavanje uživo!"
        elif self.pose_type == "ARMS_UP":
            if "Shoulder.L" in arm_obj.pose.bones:
                arm_obj.pose.bones["Shoulder.L"].rotation_euler = Euler((0, 0, math.radians(12)), "XYZ")
            if "UpperArm.L" in arm_obj.pose.bones:
                arm_obj.pose.bones["UpperArm.L"].rotation_euler = Euler((math.radians(10), 0, math.radians(48)), "XYZ")
            if "ForeArm.L" in arm_obj.pose.bones:
                arm_obj.pose.bones["ForeArm.L"].rotation_euler = Euler((math.radians(35), 0, math.radians(-25)), "XYZ")
            if "Shoulder.R" in arm_obj.pose.bones:
                arm_obj.pose.bones["Shoulder.R"].rotation_euler = Euler((0, 0, math.radians(-12)), "XYZ")
            if "UpperArm.R" in arm_obj.pose.bones:
                arm_obj.pose.bones["UpperArm.R"].rotation_euler = Euler((math.radians(10), 0, math.radians(-48)), "XYZ")
            if "ForeArm.R" in arm_obj.pose.bones:
                arm_obj.pose.bones["ForeArm.R"].rotation_euler = Euler((math.radians(35), 0, math.radians(25)), "XYZ")
            msg = "Test poza: RUKE PODIGNUTE GORE (+55°) — provjera istezanja donjeg dijela pazuha!"
        else:
            msg = "Vraćena Rest A-Poza."

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ELF01_OT_TogglePreserveVolume(bpy.types.Operator):
    bl_idname = "elf01.toggle_preserve_volume"
    bl_label = "Preserve Volume (Dual-Quaternion protiv stiskanja pazuha)"
    bl_description = "Uključuje/isključuje Dual-Quaternion Preserve Volume na Armature modifikatoru kako se pazuh i laktovi ne bi stiskali pri savijanju"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        scn.elf01_preserve_volume = not getattr(scn, "elf01_preserve_volume", True)
        for nm in ("BODY", "HEAD AND HAIR", "HAT"):
            o = bpy.data.objects.get(nm)
            if o:
                for mod in o.modifiers:
                    if mod.type == "ARMATURE":
                        mod.use_deform_preserve_volume = scn.elf01_preserve_volume
        state = "UKLJUČEN (pun volumen pazuha)" if scn.elf01_preserve_volume else "ISKLJUČEN (Linear Skinning)"
        self.report({"INFO"}, f"Preserve Volume: {state}")
        return {"FINISHED"}


class ELF01_PT_StudioPanel(bpy.types.Panel):
    bl_label = "Elf #10 Rig Studio (Urar + Kapa)"
    bl_idname = "ELF01_PT_studio_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Elf Rig Studio"

    def draw(self, context):
        layout = self.layout
        is_locked = getattr(context.scene, "elf01_lock_weights", False)

        # --- KORAK 1: SPOJI I PORAVNAJ MODELE (GLAVA + KAPA + NAOČALE + PROP + TIJELO) ---
        box1 = layout.box()
        box1.label(text="KORAK 1 [VI]: Spoji Modele (Glava + Kapa + Dodaci + Tijelo)", icon="MESH_DATA")
        col1 = box1.column(align=True)
        op1 = col1.operator("elf01.select_model_transform", text="Odaberi HEAD AND HAIR (G / R / S)", icon="OBJECT_DATAMODE")
        op1.target_name = "HEAD AND HAIR"
        if bpy.data.objects.get("HAT"):
            op_hat = col1.operator("elf01.select_model_transform", text="Odaberi HAT / KAPU (G / R / S)", icon="MOD_CLOTH")
            op_hat.target_name = "HAT"
        if bpy.data.objects.get("GLASSES"):
            op_gls = col1.operator("elf01.select_model_transform", text="Odaberi GLASSES / NAOČALE (G / R / S)", icon="VIEWZOOM")
            op_gls.target_name = "GLASSES"
        if bpy.data.objects.get("PROP"):
            op_prp = col1.operator("elf01.select_model_transform", text="Odaberi PROP / REKVIZIT (G / R / S)", icon="TOOL_SETTINGS")
            op_prp.target_name = "PROP"
        op2 = col1.operator("elf01.select_model_transform", text="Odaberi BODY (G / R / S)", icon="OUTLINER_OB_MESH")
        op2.target_name = "BODY"

        row_t1 = col1.row(align=True)
        op_hl = row_t1.operator("elf01.offset_head_test", text="Glava +15cm", icon="TRIA_UP")
        op_hl.target_name = "HEAD AND HAIR"
        op_hl.mode = "LIFT"
        op_hs = row_t1.operator("elf01.offset_head_test", text="Glava u Ovratnik", icon="SNAP_ON")
        op_hs.target_name = "HEAD AND HAIR"
        op_hs.mode = "SNAP"

        if bpy.data.objects.get("HAT"):
            row_t2 = col1.row(align=True)
            op_kl = row_t2.operator("elf01.offset_head_test", text="Kapa +15cm", icon="TRIA_UP")
            op_kl.target_name = "HAT"
            op_kl.mode = "LIFT"
            op_ks = row_t2.operator("elf01.offset_head_test", text="Kapa na Glavu", icon="SNAP_ON")
            op_ks.target_name = "HAT"
            op_ks.mode = "SNAP"

        if bpy.data.objects.get("GLASSES"):
            row_t3 = col1.row(align=True)
            op_gl = row_t3.operator("elf01.offset_head_test", text="Naočale +15cm", icon="TRIA_UP")
            op_gl.target_name = "GLASSES"
            op_gl.mode = "LIFT"
            op_gs = row_t3.operator("elf01.offset_head_test", text="Naočale na Nos", icon="SNAP_ON")
            op_gs.target_name = "GLASSES"
            op_gs.mode = "SNAP"

        if bpy.data.objects.get("PROP"):
            row_t4 = col1.row(align=True)
            op_pl = row_t4.operator("elf01.offset_head_test", text="Prop +15cm", icon="TRIA_UP")
            op_pl.target_name = "PROP"
            op_pl.mode = "LIFT"
            op_ps = row_t4.operator("elf01.offset_head_test", text="Prop u Ruku/Pojas", icon="SNAP_ON")
            op_ps.target_name = "PROP"
            op_ps.mode = "SNAP"

        row_sc = col1.row(align=True)
        sc1 = row_sc.operator("elf01.sculpt_grab_mode", text="Grab: Glava", icon="SCULPTMODE_HLT")
        sc1.target_name = "HEAD AND HAIR"
        if bpy.data.objects.get("HAT"):
            sc_h = row_sc.operator("elf01.sculpt_grab_mode", text="Grab: Kapa", icon="SCULPTMODE_HLT")
            sc_h.target_name = "HAT"
        if bpy.data.objects.get("GLASSES"):
            sc_g = row_sc.operator("elf01.sculpt_grab_mode", text="Grab: Naočale", icon="SCULPTMODE_HLT")
            sc_g.target_name = "GLASSES"
        if bpy.data.objects.get("PROP"):
            sc_p = row_sc.operator("elf01.sculpt_grab_mode", text="Grab: Prop", icon="SCULPTMODE_HLT")
            sc_p.target_name = "PROP"
        sc2 = row_sc.operator("elf01.sculpt_grab_mode", text="Grab: Tijelo", icon="SCULPTMODE_HLT")
        sc2.target_name = "BODY"

        col1.separator()
        col1.operator("elf01.confirm_model_alignment", text="Potvrdi Poravnanje Modela (Sync Kosti)", icon="CHECKMARK")

        # --- KORAK 2: RUČNO PORAVNAJ RIG I KOSTI (UKLJUČUJUĆI KAPU I BRADU) ---
        box2 = layout.box()
        box2.label(text="KORAK 2 [VI]: Poravnaj Rig i Kosti (Tijelo + Kapa)", icon="ARMATURE_DATA")
        col2 = box2.column(align=True)
        col2.scale_y = 1.25
        col2.operator("elf01.edit_bones_symmetry", text="Uredi Kosti (Edit Mode + X-Mirror)", icon="BONE_DATA")

        sub2 = box2.column(align=True)
        sub2.label(text="Brzi Zoom Kamere na Regiju:")
        r_z1 = sub2.row(align=True)
        z_hl = r_z1.operator("elf01.focus_region", text="Lijeva Šaka", icon="VIEWZOOM")
        z_hl.region = "HAND_L"
        z_hr = r_z1.operator("elf01.focus_region", text="Desna Šaka", icon="VIEWZOOM")
        z_hr.region = "HAND_R"
        r_z2 = sub2.row(align=True)
        z_hd = r_z2.operator("elf01.focus_region", text="Glava i Brada", icon="VIEWZOOM")
        z_hd.region = "HEAD"
        z_ht = r_z2.operator("elf01.focus_region", text="Kapa i Zvonce", icon="VIEWZOOM")
        z_ht.region = "HAT"
        sub2.operator("elf01.focus_region", text="Cijelo Tijelo", icon="FULLSCREEN_ENTER").region = "ALL"

        sub2.separator()
        r_f = sub2.row(align=True)
        f_all = r_f.operator("elf01.filter_bone_collections", text="Sve Kosti")
        f_all.group = "ALL"
        f_fng = r_f.operator("elf01.filter_bone_collections", text="Prsti")
        f_fng.group = "3_Prsti"
        f_hd = r_f.operator("elf01.filter_bone_collections", text="Glava")
        f_hd.group = "4_Glava_Lice_Usi"
        f_kp = r_f.operator("elf01.filter_bone_collections", text="Kapa/Alat")
        f_kp.group = "5_Kapa_i_Alat"

        r_d = sub2.row(align=True)
        r_d.operator("elf01.toggle_bone_display", text="Stick / Octahedral", icon="BONE_DATA")
        r_d.operator("elf01.toggle_xray", text="X-Ray Model", icon="XRAY")

        sub2.separator()
        r_c2 = sub2.column(align=True)
        r_c2.scale_y = 1.25
        r_c2.operator(
            "elf01.confirm_rig_and_initial_bind",
            text="Potvrdi Rig -> Početni Bind za Weight Paint",
            icon="CHECKMARK",
        )

        # --- KORAK 3: TEŽINE KOSTIJU (TIJELO + GLAVA/BRADA + KAPA) ---
        box3 = layout.box()
        box3.label(text="KORAK 3 [VI]: Težine i Ručni Weight Paint", icon="WPAINT_HLT")

        col_sl = box3.column(align=True)
        col_sl.enabled = not is_locked
        col_sl.label(text="A) Početna Širina Zglobova (prije bojanja):")
        col_sl.prop(context.scene, "elf01_arm_joint_cm", text="Zglobovi Ruku (cm)", slider=True)
        col_sl.prop(context.scene, "elf01_leg_joint_cm", text="Zglobovi Nogu (cm)", slider=True)
        col_sl.prop(context.scene, "elf01_spine_joint_cm", text="Kralježnica (cm)", slider=True)
        col_sl.prop(context.scene, "elf01_hat_joint_cm", text="Zglobovi Kape (cm)", slider=True)

        r_pr = col_sl.row(align=True)
        p1 = r_pr.operator("elf01.joint_radius_preset", text="Oštri (1.0cm)")
        p1.arm_cm, p1.leg_cm, p1.spine_cm, p1.hat_cm = 1.0, 1.0, 1.8, 1.2
        p2 = r_pr.operator("elf01.joint_radius_preset", text="Prirodni (1.8cm)")
        p2.arm_cm, p2.leg_cm, p2.spine_cm, p2.hat_cm = 1.8, 1.8, 2.5, 2.0
        p3 = r_pr.operator("elf01.joint_radius_preset", text="Mekani (3.5cm)")
        p3.arm_cm, p3.leg_cm, p3.spine_cm, p3.hat_cm = 3.5, 3.5, 4.0, 3.2

        col_bind = box3.column(align=True)
        col_bind.enabled = not is_locked
        col_bind.scale_y = 1.25
        col_bind.operator("elf01.bind_rig", text="Primijeni Klizače i Zaveži Rig (Bind)", icon="CHECKMARK")

        # 3A-2: 3D WEIGHT & FADE GIZMO STUDIO (FINO UŠTIMAVANJE PAZUHA I ZGLOBOVA)
        box_gz = box3.box()
        box_gz.label(text="A2) 3D Weight Gizmo & Pazuh Tuner (Uživo u Viewportu):", icon="GIZMO")
        col_gz = box_gz.column(align=True)
        col_gz.enabled = not is_locked

        r_gt = col_gz.row(align=True)
        r_gt.scale_y = 1.2
        gz_on = getattr(context.scene, "elf01_show_weight_gizmos", True)
        r_gt.operator(
            "elf01.toggle_weight_gizmos",
            text="3D Gizmo: AKTIVAN" if gz_on else "Uključi 3D Gizmo u Viewportu",
            icon="HIDE_OFF" if gz_on else "HIDE_ON",
            depress=gz_on,
        )
        pv_on = getattr(context.scene, "elf01_preserve_volume", True)
        r_gt.operator(
            "elf01.toggle_preserve_volume",
            text="Preserve Vol: DA" if pv_on else "Preserve Vol: NE",
            icon="MOD_MESHDEFORM",
            depress=pv_on,
        )

        # Test poze za provjeru pazuha uživo
        col_gz.label(text="1. Testiraj Pozu Pazuha dok pomičeš 3D Gizmo / Klizače:")
        r_ap_pose = col_gz.row(align=True)
        op_pd = r_ap_pose.operator("elf01.test_armpit_pose", text="Ruke Dolje (-42° Pazuh)", icon="TRIA_DOWN")
        op_pd.pose_type = "ARMS_DOWN"
        op_pu = r_ap_pose.operator("elf01.test_armpit_pose", text="Ruke Gore (+55°)", icon="TRIA_UP")
        op_pu.pose_type = "ARMS_UP"
        r_ap_pose.operator("elf01.reset_pose", text="A-Poza", icon="LOOP_BACK")

        col_gz.separator()
        col_gz.prop(context.scene, "elf01_live_gizmo_update", text="Auto-Update Težina Uživo pri pomicanju klizača/Gizma", toggle=True)

        # Kontrole za Pazuh (Armpit Crease & Fade)
        col_gz.label(text="2. Fino Uštimavanje Pazuha (Spine2 <-> Shoulder <-> UpperArm):")
        col_gz.prop(context.scene, "elf01_armpit_inset_cm", text="Ulaz Pazuha prema Prsima (cm)", slider=True)
        col_gz.prop(context.scene, "elf01_armpit_drop_cm", text="Dubina Pazuha ispod Ramena (cm)", slider=True)
        col_gz.prop(context.scene, "elf01_armpit_angle_deg", text="Kut Pazušne Ravnine (°)", slider=True)
        col_gz.prop(context.scene, "elf01_armpit_fade_cm", text="Širina Fadea Pazuha (cm)", slider=True)
        col_gz.prop(context.scene, "elf01_shoulder_influence", text="Jastuk Ramena u Pazuhu (Shoulder)", slider=True)

        r_ap_fix = col_gz.row(align=True)
        r_ap_fix.scale_y = 1.25
        op_fa = r_ap_fix.operator("elf01.fix_armpit_weights_only", text="Preračunaj Samo Pazuh (.L+.R)", icon="FILE_REFRESH")
        op_fa.zone = "ARMPIT"
        r_ap_fix.operator("elf01.relax_armpit_seam", text="Laplacian Relax Pazuha", icon="SMOOTHCURVE")

        col_gz.separator()
        col_gz.label(text="3. Krivulja Prijelaza (Fade Curve) i Ostali Zglobovi:")
        col_gz.prop(context.scene, "elf01_fade_curve_type", text="Oblik Fadea")
        col_gz.prop(context.scene, "elf01_fade_power", text="Bias (Trup <-> Ud)", slider=True)

        r_el = col_gz.row(align=True)
        r_el.prop(context.scene, "elf01_elbow_offset_cm", text="Lakat Pomak (cm)", slider=True)
        r_el.prop(context.scene, "elf01_elbow_fade_cm", text="Lakat Fade (cm)", slider=True)

        r_wr = col_gz.row(align=True)
        r_wr.prop(context.scene, "elf01_wrist_offset_cm", text="Zapešće Pomak (cm)", slider=True)
        r_wr.prop(context.scene, "elf01_wrist_fade_cm", text="Zapešće Fade (cm)", slider=True)

        r_hp = col_gz.row(align=True)
        r_hp.prop(context.scene, "elf01_hip_offset_cm", text="Kuk Pomak (cm)", slider=True)
        r_hp.prop(context.scene, "elf01_hip_fade_cm", text="Kuk Fade (cm)", slider=True)

        r_kn = col_gz.row(align=True)
        r_kn.prop(context.scene, "elf01_knee_offset_cm", text="Koljeno Pomak (cm)", slider=True)
        r_kn.prop(context.scene, "elf01_knee_fade_cm", text="Koljeno Fade (cm)", slider=True)

        col_gz.label(text="4. Odaberi 3D Kružni Gizmo u Viewportu (G=Pomak / R=Kut / S=Fade):")
        r_ge1 = col_gz.row(align=True)
        for lbl, gname, zn in [
            ("3D Pazuh", "WGT_GIZMO_Pazuh.L", "ARMPIT"),
            ("3D Lakat", "WGT_GIZMO_Lakat.L", "ELBOW"),
            ("3D Zapešće", "WGT_GIZMO_Zapesce.L", "WRIST"),
        ]:
            op_g = r_ge1.operator("elf01.select_weight_gizmo_empty", text=lbl, icon="EMPTY_AXIS")
            op_g.gizmo_name = gname
            op_g.zone = zn
        r_ge2 = col_gz.row(align=True)
        for lbl, gname, zn in [
            ("3D Kuk", "WGT_GIZMO_Kuk.L", "HIP"),
            ("3D Koljeno", "WGT_GIZMO_Koljeno.L", "KNEE"),
        ]:
            op_g = r_ge2.operator("elf01.select_weight_gizmo_empty", text=lbl, icon="EMPTY_AXIS")
            op_g.gizmo_name = gname
            op_g.zone = zn

        # 3B: 1-Klik Ručni Weight Paint Studio (Tijelo, Glava/Brada i Kapa)
        box_wp = box3.box()
        box_wp.label(text="B) Ručno Bojanje Težina (1-Klik Weight Paint):", icon="BRUSH_DATA")

        sub_b = box_wp.column(align=True)
        sub_b.label(text="1. Odaberi Kost (Tijelo / Glava i Brada / Kapa):")
        r_b1 = sub_b.row(align=True)
        for lbl, bname in [("Rame.L", "Shoulder.L"), ("Nadlaktica.L", "UpperArm.L"), ("Podlaktica.L", "ForeArm.L"), ("Šaka.L", "Hand.L")]:
            b_op = r_b1.operator("elf01.select_weight_bone", text=lbl)
            b_op.target_mesh = "BODY"
            b_op.bone_name = bname

        r_b2 = sub_b.row(align=True)
        for lbl, bname in [("Kukovi", "Hips"), ("Bedro.L", "LeftUpLeg"), ("Potkoljenica.L", "LeftLeg"), ("Stopalo.L", "LeftFoot")]:
            b_op = r_b2.operator("elf01.select_weight_bone", text=lbl)
            b_op.target_mesh = "BODY"
            b_op.bone_name = bname

        r_b3 = sub_b.row(align=True)
        for lbl, tm, bname in [
            ("Prsa", "BODY", "Spine2"),
            ("Glava", "HEAD AND HAIR", "Head"),
            ("Brada 1", "HEAD AND HAIR", "Beard.01"),
            ("Brada 2", "HEAD AND HAIR", "Beard.02"),
        ]:
            b_op = r_b3.operator("elf01.select_weight_bone", text=lbl)
            b_op.target_mesh = tm
            b_op.bone_name = bname

        sub_b.label(text="Kosti Kape i Naočala (HAT / GLASSES modeli):")
        r_b4 = sub_b.row(align=True)
        for lbl, bname in [
            ("Obruč (Head)", "Head"),
            ("Kapa 1", "Hat.01"),
            ("Kapa 2", "Hat.02"),
            ("Kapa 3", "Hat.03"),
            ("Zvonce", "HatBell"),
        ]:
            b_op = r_b4.operator("elf01.select_weight_bone", text=lbl)
            b_op.target_mesh = "HAT"
            b_op.bone_name = bname

        r_b5 = sub_b.row(align=True)
        if bpy.data.objects.get("GLASSES"):
            for lbl, bname in [
                ("Okvir Naočala (Glasses)", "Glasses"),
                ("Dvostruka Lupa (ForeheadLoupe)", "ForeheadLoupe"),
            ]:
                b_op = r_b5.operator("elf01.select_weight_bone", text=lbl)
                b_op.target_mesh = "GLASSES"
                b_op.bone_name = bname
        if bpy.data.objects.get("PROP"):
            b_prp = r_b5.operator("elf01.select_weight_bone", text="Rekvizit / Prop (Prop.R)")
            b_prp.target_mesh = "PROP"
            b_prp.bone_name = "Prop.R"

        if context.object and context.object.type == "MESH" and context.object.vertex_groups:
            sub_b.separator()
            sub_b.prop_search(context.object.vertex_groups, "active", context.object, "vertex_groups", text="Sve Kosti")

        # 1-Klik Četke
        sub_br = box_wp.column(align=True)
        sub_br.label(text="2. Odaberi Četku i Bojaj po Modelu:")
        r_br1 = sub_br.row(align=True)
        r_br1.scale_y = 1.2
        b_add = r_br1.operator("elf01.set_weight_brush", text="Dodaj 100% (Kruto)", icon="ADD")
        b_add.mode = "ADD_100"
        b_hlf = r_br1.operator("elf01.set_weight_brush", text="Zglob 50%", icon="CLIPUV_DEHLT")
        b_hlf.mode = "HALF_50"
        b_sub = r_br1.operator("elf01.set_weight_brush", text="Briši 0%", icon="REMOVE")
        b_sub.mode = "SUB_0"
        b_blr = r_br1.operator("elf01.set_weight_brush", text="Omekšaj (Blur)", icon="SMOOTHCURVE")
        b_blr.mode = "BLUR"

        ts = context.scene.tool_settings
        wp = ts.weight_paint
        ups = getattr(wp, "unified_paint_settings", None) or getattr(ts, "unified_paint_settings", None)
        if ups:
            r_ups = sub_br.row(align=True)
            if hasattr(ups, "weight"):
                r_ups.prop(ups, "weight", text="Težina Četke", slider=True)
            if hasattr(ups, "size"):
                r_ups.prop(ups, "size", text="Veličina (px)", slider=True)

        sub_op = box_wp.column(align=True)
        sub_op.label(text="3. Brze Operacije nad Zglobovima (1-Klik):")
        r_sh = sub_op.row(align=True)
        op_sh = r_sh.operator("elf01.sharpen_smooth_weights", text="Izoštri Zglobove (-30% Rub)", icon="IPO_EXPO")
        op_sh.action = "SHARPEN"
        op_sh.only_active = False
        op_sm = r_sh.operator("elf01.sharpen_smooth_weights", text="Omekšaj Zglobove (+30% Rub)", icon="SMOOTHCURVE")
        op_sm.action = "SMOOTH"
        op_sm.only_active = False

        sub_op.operator("elf01.mirror_weights_lr", text="Zrcali Ručne Težine s Lijeve na Desnu (.L -> .R)", icon="MOD_MIRROR")

        # 3C: Testiranje Poze dok uređuješ težine
        r_p = box3.row(align=True)
        r_p.operator("elf01.bend_joints_test_pose", text="Savij Zglobove/Kapu (Test)", icon="POSE_HLT")
        r_p.operator("elf01.test_pose_mode", text="Rotiraj Kosti (Pose)", icon="ORIENTATION_GIMBAL")
        r_p.operator("elf01.reset_pose", text="Rest Poza", icon="LOOP_BACK")

        # 3D: Zaključavanje ručnih težina i predaja Agentu
        box_lk = box3.box()
        box_lk.label(text="C) Završetak Weight Painta (Predaja Agentu):", icon="LOCKED" if is_locked else "UNLOCKED")
        col_lk = box_lk.column(align=True)
        col_lk.prop(context.scene, "elf01_lock_weights", text="Zaključaj Ručne Težine (Zaštiti od Binda)", toggle=True)
        r_lk_btn = col_lk.column(align=True)
        r_lk_btn.scale_y = 1.3
        r_lk_btn.operator(
            "elf01.lock_manual_weights_handoff",
            text="Potvrdi i Zaključaj Težine (Spremno za Agenta)",
            icon="CHECKMARK",
        )

        # --- KORAK 4: MIXAMO ANIMACIJE I FINALNI EXPORT (AGENT / 1-KLIK) ---
        box4 = layout.box()
        box4.label(text="KORAK 4 [AGENT / 1-KLIK]: Animacije i Export", icon="ACTION")
        if is_locked:
            box4.label(text="Status: Ručne težine su ZAKLJUČANE i sigurne!", icon="LOCKED")
        else:
            box4.label(text="Savjet: Zaključaj težine u Koraku 3C prije animacija.", icon="INFO")

        col4 = box4.column(align=True)
        dji_npz = os.path.join(ROOT, "assets", "animations", "dji_0057_mocap.npz")
        if os.path.exists(dji_npz):
            r_mc = col4.column(align=True)
            r_mc.scale_y = 1.3
            op_mc = r_mc.operator("elf01.apply_mocap_npz", text="Video-to-Motion: DJI_0057 (417 sličica)", icon="CAMERA_DATA")
            op_mc.npz_filename = "dji_0057_mocap.npz"
            col4.separator()

        presets = [
            ("F_Standing_Idle_001.fbx", "Standing Idle (Mirno Disanje)"),
            ("F_Standing_Idle_Variations_001.fbx", "Idle Look Around (Razgledavanje)"),
            ("M_Standing_Expressions_001.fbx", "Standing Expressions 1 (Gestikulacija)"),
            ("M_Standing_Expressions_002.fbx", "Standing Expressions 2 (Pozdrav)"),
            ("F_Talking_Variations_001.fbx", "Talking 1 (Razgovor)"),
            ("F_Talking_Variations_002.fbx", "Talking 2 (Objašnjavanje)"),
            ("M_Walk_001.fbx", "Male Walk (Muški Hod Urara)"),
            ("F_Dances_001.fbx", "Festive Dance (Božićni Ples)"),
        ]
        for fname, label in presets:
            if os.path.exists(os.path.join(MIXAMO_DIR, fname)):
                op_m = col4.operator("elf01.apply_mixamo_preset", text=label, icon="PLAY")
                op_m.fbx_filename = fname

        col4.separator()
        r_exp = col4.column(align=True)
        r_exp.scale_y = 1.25
        r_exp.operator("elf01.export_final_glb", text="Izvezi Finalni Rigged GLB (Čuva Ručne Težine)", icon="EXPORT")


CLASSES = (
    ELF01_OT_SelectModelTransform,
    ELF01_OT_OffsetHeadForTest,
    ELF01_OT_SculptGrabMode,
    ELF01_OT_ConfirmModelAlignment,
    ELF01_OT_EditBonesSymmetry,
    ELF01_OT_FocusRegion,
    ELF01_OT_FilterBoneCollections,
    ELF01_OT_ToggleBoneDisplay,
    ELF01_OT_ToggleXRay,
    ELF01_OT_ConfirmRigAndInitialBind,
    ELF01_OT_BindRig,
    ELF01_OT_JointRadiusPreset,
    ELF01_OT_SelectWeightBone,
    ELF01_OT_SetWeightBrush,
    ELF01_OT_SharpenOrSmoothWeights,
    ELF01_OT_MirrorWeightsLR,
    ELF01_OT_BendJointsTestPose,
    ELF01_OT_TestPoseMode,
    ELF01_OT_ResetPose,
    ELF01_GGT_WeightZoneGizmoGroup,
    ELF01_OT_ToggleWeightGizmos,
    ELF01_OT_SelectWeightGizmoEmpty,
    ELF01_OT_FixArmpitWeightsOnly,
    ELF01_OT_RelaxArmpitSeam,
    ELF01_OT_TestArmpitPose,
    ELF01_OT_TogglePreserveVolume,
    ELF01_OT_LockManualWeightsHandoff,
    ELF01_OT_ExportFinalGLB,
    ELF01_OT_ApplyMixamoPreset,
    ELF01_OT_ApplyMocapNPZ,
    ELF01_PT_StudioPanel,
)


def register():
    bpy.types.Scene.elf01_arm_joint_cm = bpy.props.FloatProperty(
        name="Zglobovi Ruku (cm)",
        description="Poluširina prijelaza zglobova ruku (rame, lakat, zapešće) u centimetrima",
        default=1.8, min=0.3, max=6.0, step=10, precision=1
    )
    bpy.types.Scene.elf01_leg_joint_cm = bpy.props.FloatProperty(
        name="Zglobovi Nogu (cm)",
        description="Poluširina prijelaza zglobova nogu (kuk, koljeno, gležanj, prsti) u centimetrima",
        default=1.8, min=0.3, max=6.0, step=10, precision=1
    )
    bpy.types.Scene.elf01_spine_joint_cm = bpy.props.FloatProperty(
        name="Kralježnica (cm)",
        description="Poluširina prijelaza zglobova kralježnice u centimetrima",
        default=2.5, min=0.5, max=8.0, step=10, precision=1
    )
    bpy.types.Scene.elf01_hat_joint_cm = bpy.props.FloatProperty(
        name="Zglobovi Kape (cm)",
        description="Poluširina prijelaza između segmenata kape (Head -> Hat.01 -> Hat.02 -> Hat.03 -> HatBell) u centimetrima",
        default=2.0, min=0.4, max=6.0, step=10, precision=1
    )
    bpy.types.Scene.elf01_show_weight_gizmos = bpy.props.BoolProperty(
        name="Prikaži 3D Weight Gizmo Kontrole",
        description="Prikazuje interaktivne 3D strelice i prstenove u Viewportu za uštimavanje pazuha i zglobova",
        default=True,
    )
    bpy.types.Scene.elf01_use_3d_gizmo_empties = bpy.props.BoolProperty(
        name="Koristi 3D Empty Gizmo objekte",
        default=False,
    )
    bpy.types.Scene.elf01_live_gizmo_update = bpy.props.BoolProperty(
        name="Auto-Update Težina Uživo",
        description="Automatski preračunava težine odabranog zgloba/pazuha dok pomičeš klizače ili 3D Gizmo u Viewportu",
        default=True,
    )
    bpy.types.Scene.elf01_active_gizmo_zone = bpy.props.StringProperty(
        name="Aktivna Gizmo Zona",
        default="ARMPIT",
    )
    bpy.types.Scene.elf01_preserve_volume = bpy.props.BoolProperty(
        name="Preserve Volume (Dual-Quaternion)",
        description="Čuva volumen pazuha i laktova pri savijanju ruku uz tijelo",
        default=True,
    )
    bpy.types.Scene.elf01_armpit_inset_cm = bpy.props.FloatProperty(
        name="Ulaz Pazuha prema Prsima (cm)",
        description="Koliko centimetara unutar ramena prolazi pazušna ravnina odvajanja trupa (Spine2) od nadlaktice (UpperArm)",
        default=3.5, min=-2.0, max=12.0, step=10, precision=1,
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_armpit_drop_cm = bpy.props.FloatProperty(
        name="Dubina Pazuha ispod Ramena (cm)",
        description="Koliko centimetara ispod glave nadlaktice (UpperArm) leži točka pazušnog pregiba",
        default=5.5, min=0.5, max=14.0, step=10, precision=1,
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_armpit_angle_deg = bpy.props.FloatProperty(
        name="Kut Pazušne Ravnine (°)",
        description="Nagib ravnine pazuha (od okomice prema ključnoj kosti/pelerini)",
        default=28.0, min=-25.0, max=65.0, step=50, precision=1,
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_armpit_fade_cm = bpy.props.FloatProperty(
        name="Širina Fadea Pazuha (cm)",
        description="Poluširina glatkog prijelaza (fadea) između trupa (Spine2), ramena (Shoulder) i rukava (UpperArm) u pazuhu",
        default=3.2, min=0.4, max=9.0, step=10, precision=1,
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_shoulder_influence = bpy.props.FloatProperty(
        name="Jastuk Ramena u Pazuhu (Shoulder)",
        description="Koliko jako kost ramena (Shoulder) sudjeluje kao prijelazni jastuk između prsnog koša i nadlaktice",
        default=0.78, min=0.0, max=1.5, step=5, precision=2,
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_fade_curve_type = bpy.props.EnumProperty(
        name="Oblik Krivulje Prijelaza (Fade)",
        items=[
            ("QUINTIC", "Quintic C4 (Najglađi za Pazuh/Odjeću)", "Perlinov C4 prijelaz bez loma zakrivljenosti"),
            ("SMOOTH", "Smoothstep C2 (Standardni S-Prijelaz)", "Klasični Hermite C2 prijelaz"),
            ("SOFT_DOME", "Soft Dome (Kosinusni Široki)", "Meki kupolasti prijelaz za kapute i pelerine"),
            ("SHARP", "Sharp Hinge (Oštri Pregib)", "Uski mehanički pregib"),
            ("LINEAR", "Linear (Linearni)", "Ravnomjerni linearni prijelaz"),
        ],
        default="QUINTIC",
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_fade_power = bpy.props.FloatProperty(
        name="Bias (Trup <-> Ud)",
        description="Eksponent prijelaza (<1.0 širi utjecaj ruke/noge, >1.0 drži pazuh/kuk čvršće uz trup)",
        default=1.0, min=0.35, max=2.8, step=5, precision=2,
        update=on_live_weight_param_change,
    )
    bpy.types.Scene.elf01_elbow_offset_cm = bpy.props.FloatProperty(
        name="Lakat Pomak (cm)",
        default=0.0, min=-6.0, max=6.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "ELBOW") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_elbow_fade_cm = bpy.props.FloatProperty(
        name="Lakat Fade (cm)",
        default=1.8, min=0.3, max=6.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "ELBOW") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_wrist_offset_cm = bpy.props.FloatProperty(
        name="Zapešće Pomak (cm)",
        default=0.0, min=-4.0, max=4.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "WRIST") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_wrist_fade_cm = bpy.props.FloatProperty(
        name="Zapešće Fade (cm)",
        default=1.5, min=0.3, max=5.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "WRIST") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_hip_offset_cm = bpy.props.FloatProperty(
        name="Kuk Pomak (cm)",
        default=0.0, min=-6.0, max=6.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "HIP") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_hip_fade_cm = bpy.props.FloatProperty(
        name="Kuk Fade (cm)",
        default=2.2, min=0.4, max=7.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "HIP") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_knee_offset_cm = bpy.props.FloatProperty(
        name="Koljeno Pomak (cm)",
        default=0.0, min=-6.0, max=6.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "KNEE") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_knee_fade_cm = bpy.props.FloatProperty(
        name="Koljeno Fade (cm)",
        default=1.8, min=0.3, max=6.0, step=10, precision=1,
        update=lambda s, c: recalc_armpit_and_joint_zone_only(c, "KNEE") if getattr(c.scene, "elf01_live_gizmo_update", True) else None,
    )
    bpy.types.Scene.elf01_lock_weights = bpy.props.BoolProperty(
        name="Zaključaj Ručne Težine",
        description="Kad je uključeno, sprječava da automatski Bind ili Agent pregaze tvoje ručno obojane težine (Weight Paint)",
        default=False,
    )
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "on_depsgraph_gizmo_empty_moved":
            bpy.app.handlers.depsgraph_update_post.remove(h)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_gizmo_empty_moved)


def unregister():
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "on_depsgraph_gizmo_empty_moved":
            bpy.app.handlers.depsgraph_update_post.remove(h)
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


# ============================================================================
# 6. IZGRADNJA POČETNE SCENE (`elf10_urar_rig_ready.blend`)
# ============================================================================
def build_rig_ready_scene():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)
    os.makedirs(GLB_DIR, exist_ok=True)

    # 1. Import Headless BODY
    bpy.ops.import_scene.gltf(filepath=BODY_GLB)
    body_meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for bm in body_meshes:
        bm.select_set(True)
    bpy.context.view_layer.objects.active = body_meshes[0]
    if len(body_meshes) > 1:
        bpy.ops.object.join()
    body_obj = bpy.context.view_layer.objects.active
    body_obj.name = "BODY"
    body_obj.data.name = "BODY_Mesh"

    bpy.ops.object.select_all(action="DESELECT")
    body_obj.select_set(True)
    bpy.context.view_layer.objects.active = body_obj
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    for o in list(bpy.context.scene.objects):
        if o != body_obj:
            bpy.data.objects.remove(o, do_unlink=True)

    body_obj.rotation_mode = "XYZ"
    body_obj.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    zs_b = [v.co.z for v in body_obj.data.vertices]
    raw_b_h = max(zs_b) - min(zs_b)
    if raw_b_h > 0.01 and (raw_b_h < 1.35 or raw_b_h > 2.05):
        sf_b = 1.785 / raw_b_h
        body_obj.scale = (sf_b, sf_b, sf_b)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    min_z = min(v.co.z for v in body_obj.data.vertices)
    xs_b = [v.co.x for v in body_obj.data.vertices]
    ys_b = [v.co.y for v in body_obj.data.vertices]
    cx_b = 0.5 * (min(xs_b) + max(xs_b))
    cy_b = 0.5 * (min(ys_b) + max(ys_b))
    for v in body_obj.data.vertices:
        v.co.x -= cx_b
        v.co.y -= cy_b
        v.co.z -= min_z
    body_obj.data.update()

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth()

    bpy.ops.object.select_all(action="DESELECT")
    body_obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=BODY_CLEAN_GLB, export_format="GLB", use_selection=True)

    # 2. Import HEAD AND HAIR
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=HEAD_GLB)
    new_objs = [o for o in bpy.context.scene.objects if o not in before]
    head_meshes = [o for o in new_objs if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for hm in head_meshes:
        hm.select_set(True)
    bpy.context.view_layer.objects.active = head_meshes[0]
    if len(head_meshes) > 1:
        bpy.ops.object.join()
    head_obj = bpy.context.view_layer.objects.active
    head_obj.name = "HEAD AND HAIR"
    head_obj.data.name = "HEAD_AND_HAIR_Mesh"

    bpy.ops.object.select_all(action="DESELECT")
    head_obj.select_set(True)
    bpy.context.view_layer.objects.active = head_obj
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    for o in list(bpy.context.scene.objects):
        if o not in (body_obj, head_obj):
            bpy.data.objects.remove(o, do_unlink=True)

    head_obj.rotation_mode = "XYZ"
    head_obj.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    zs_h = [v.co.z for v in head_obj.data.vertices]
    raw_h_span = max(zs_h) - min(zs_h)
    if raw_h_span > 0.45:
        norm_h = 0.300 / raw_h_span
        head_obj.scale = (norm_h, norm_h, norm_h)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    head_obj.scale = (RAW_HEAD_SCALE, RAW_HEAD_SCALE, RAW_HEAD_SCALE)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    neck_pivot_raw = Vector(RAW_HEAD_NECK_PIVOT)
    for v in head_obj.data.vertices:
        v.co -= neck_pivot_raw
    head_obj.data.update()

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth()

    head_obj.location = Vector(DEFAULT_HEAD_PIVOT)
    bpy.context.view_layer.update()
    auto_tuck_submerged_neck(head_obj, body_obj)

    bpy.ops.object.select_all(action="DESELECT")
    head_obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=HEAD_CLEAN_GLB, export_format="GLB", use_selection=True)

    # 3. Import HAT (if available)
    hat_obj = None
    if os.path.exists(HAT_GLB):
        before_h = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=HAT_GLB)
        new_h_objs = [o for o in bpy.context.scene.objects if o not in before_h]
        hat_meshes = [o for o in new_h_objs if o.type == "MESH"]
        bpy.ops.object.select_all(action="DESELECT")
        for htm in hat_meshes:
            htm.select_set(True)
        bpy.context.view_layer.objects.active = hat_meshes[0]
        if len(hat_meshes) > 1:
            bpy.ops.object.join()
        hat_obj = bpy.context.view_layer.objects.active
        hat_obj.name = "HAT"
        hat_obj.data.name = "HAT_Mesh"

        bpy.ops.object.select_all(action="DESELECT")
        hat_obj.select_set(True)
        bpy.context.view_layer.objects.active = hat_obj
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        for o in list(bpy.context.scene.objects):
            if o not in (body_obj, head_obj, hat_obj):
                bpy.data.objects.remove(o, do_unlink=True)

        hat_obj.rotation_mode = "XYZ"
        hat_obj.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        zs_ht = [v.co.z for v in hat_obj.data.vertices]
        raw_ht_span = max(zs_ht) - min(zs_ht)
        if raw_ht_span > 0.45:
            norm_ht = 0.300 / raw_ht_span
            hat_obj.scale = (norm_ht, norm_ht, norm_ht)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        hat_obj.scale = (RAW_HAT_SCALE, RAW_HAT_SCALE, RAW_HAT_SCALE)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        brim_pivot_raw = Vector(RAW_HAT_BRIM_PIVOT)
        for v in hat_obj.data.vertices:
            v.co -= brim_pivot_raw
        hat_obj.data.update()

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.shade_smooth()

        hat_obj.location = Vector(DEFAULT_HAT_PIVOT)
        bpy.context.view_layer.update()

        bpy.ops.object.select_all(action="DESELECT")
        hat_obj.select_set(True)
        bpy.ops.export_scene.gltf(filepath=HAT_CLEAN_GLB, export_format="GLB", use_selection=True)

    # 4. Import GLASSES (if available)
    glasses_obj = None
    if os.path.exists(GLASSES_GLB):
        before_g = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=GLASSES_GLB)
        new_g_objs = [o for o in bpy.context.scene.objects if o not in before_g]
        g_meshes = [o for o in new_g_objs if o.type == "MESH"]
        bpy.ops.object.select_all(action="DESELECT")
        for gm in g_meshes:
            gm.select_set(True)
        bpy.context.view_layer.objects.active = g_meshes[0]
        if len(g_meshes) > 1:
            bpy.ops.object.join()
        glasses_obj = bpy.context.view_layer.objects.active
        glasses_obj.name = "GLASSES"
        glasses_obj.data.name = "GLASSES_Mesh"

        bpy.ops.object.select_all(action="DESELECT")
        glasses_obj.select_set(True)
        bpy.context.view_layer.objects.active = glasses_obj
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        for o in list(bpy.context.scene.objects):
            if o not in (body_obj, head_obj, hat_obj, glasses_obj):
                bpy.data.objects.remove(o, do_unlink=True)

        glasses_obj.rotation_mode = "XYZ"
        glasses_obj.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        xs_gl = [v.co.x for v in glasses_obj.data.vertices]
        ys_gl = [v.co.y for v in glasses_obj.data.vertices]
        raw_gl_span = max(max(xs_gl) - min(xs_gl), max(ys_gl) - min(ys_gl))
        if raw_gl_span > 0.40:
            norm_gl = 0.266 / raw_gl_span
            glasses_obj.scale = (norm_gl, norm_gl, norm_gl)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        glasses_obj.scale = (RAW_GLASSES_SCALE, RAW_GLASSES_SCALE, RAW_GLASSES_SCALE)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        bridge_pivot_raw = Vector(RAW_GLASSES_BRIDGE_PIVOT)
        for v in glasses_obj.data.vertices:
            v.co -= bridge_pivot_raw
        glasses_obj.data.update()

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.shade_smooth()

        glasses_obj.location = Vector(DEFAULT_GLASSES_PIVOT)
        bpy.context.view_layer.update()

        bpy.ops.object.select_all(action="DESELECT")
        glasses_obj.select_set(True)
        bpy.ops.export_scene.gltf(filepath=GLASSES_CLEAN_GLB, export_format="GLB", use_selection=True)

    # 5. Import PROP (if available)
    prop_obj = None
    if os.path.exists(PROP_GLB):
        before_p = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=PROP_GLB)
        new_p_objs = [o for o in bpy.context.scene.objects if o not in before_p]
        p_meshes = [o for o in new_p_objs if o.type == "MESH"]
        if p_meshes:
            bpy.ops.object.select_all(action="DESELECT")
            for pm in p_meshes:
                pm.select_set(True)
            bpy.context.view_layer.objects.active = p_meshes[0]
            if len(p_meshes) > 1:
                bpy.ops.object.join()
            prop_obj = bpy.context.view_layer.objects.active
            prop_obj.name = "PROP"
            prop_obj.data.name = "PROP_Mesh"

            bpy.ops.object.select_all(action="DESELECT")
            prop_obj.select_set(True)
            bpy.context.view_layer.objects.active = prop_obj
            bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
            for o in list(bpy.context.scene.objects):
                if o not in (body_obj, head_obj, hat_obj, glasses_obj, prop_obj):
                    bpy.data.objects.remove(o, do_unlink=True)

            prop_obj.rotation_mode = "XYZ"
            prop_obj.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            xs_p0 = [v.co.x for v in prop_obj.data.vertices]
            ys_p0 = [v.co.y for v in prop_obj.data.vertices]
            zs_p0 = [v.co.z for v in prop_obj.data.vertices]
            raw_p_span = max(max(xs_p0) - min(xs_p0), max(ys_p0) - min(ys_p0), max(zs_p0) - min(zs_p0))
            if raw_p_span > 0.45:
                norm_p = 0.420 / raw_p_span
                prop_obj.scale = (norm_p, norm_p, norm_p)
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            prop_obj.scale = (RAW_PROP_SCALE, RAW_PROP_SCALE, RAW_PROP_SCALE)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            xs_p = [v.co.x for v in prop_obj.data.vertices]
            ys_p = [v.co.y for v in prop_obj.data.vertices]
            zs_p = [v.co.z for v in prop_obj.data.vertices]
            center_p = Vector((
                0.5 * (min(xs_p) + max(xs_p)),
                0.5 * (min(ys_p) + max(ys_p)),
                0.5 * (min(zs_p) + max(zs_p)),
            )) + Vector(RAW_PROP_HANDLE_PIVOT)
            for v in prop_obj.data.vertices:
                v.co -= center_p
            prop_obj.data.update()

            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.remove_doubles(threshold=0.0001)
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.shade_smooth()

            prop_obj.location = Vector(DEFAULT_PROP_PIVOT)
            bpy.context.view_layer.update()

            bpy.ops.object.select_all(action="DESELECT")
            prop_obj.select_set(True)
            bpy.ops.export_scene.gltf(filepath=PROP_CLEAN_GLB, export_format="GLB", use_selection=True)

    # 5. Create 72-bone editable armature ARM_Elf_Hero
    arm_obj = create_editable_armature("ARM_Elf_Hero")

    # 5. Initial Auto-Bind
    bind_character_to_rig(bpy.context)

    # 6. Add clean 3-point studio lighting
    key_data = bpy.data.lights.new(name="KeyLight", type="SUN")
    key_data.energy = 3.2
    key_obj = bpy.data.objects.new(name="KeyLight", object_data=key_data)
    bpy.context.scene.collection.objects.link(key_obj)
    key_obj.rotation_euler = (math.radians(55), math.radians(-15), math.radians(25))

    fill_data = bpy.data.lights.new(name="FillLight", type="SUN")
    fill_data.energy = 1.4
    fill_obj = bpy.data.objects.new(name="FillLight", object_data=fill_data)
    bpy.context.scene.collection.objects.link(fill_obj)
    fill_obj.rotation_euler = (math.radians(65), math.radians(20), math.radians(-145))

    world = bpy.data.worlds.new("StudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.22, 0.23, 0.25, 1.0)
        bg.inputs[1].default_value = 1.0

    script_path = os.path.abspath(__file__)
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            code_str = f.read()
        txt = bpy.data.texts.get("elf10_sculpt_rig_studio.py") or bpy.data.texts.new("elf10_sculpt_rig_studio.py")
        txt.clear()
        txt.write(code_str)
        txt.use_module = True

    register()

    bpy.ops.object.select_all(action="DESELECT")
    if hat_obj:
        hat_obj.select_set(True)
    head_obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = head_obj

    os.makedirs(os.path.dirname(OUTPUT_BLEND), exist_ok=True)
    try:
        bpy.ops.file.pack_all()
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_BLEND)
    print(f"SAVED RIG-READY BLEND: {OUTPUT_BLEND}")


if __name__ == "__main__":
    register()
    if "--build-scene" in os.sys.argv:
        build_rig_ready_scene()
