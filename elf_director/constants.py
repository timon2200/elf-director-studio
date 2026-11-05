# -*- coding: utf-8 -*-
"""
ActionForge Elf Director Studio v3.0 — Constants, Roster & Shared Helpers
=========================================================================
Dynamic path resolution (zero hardcoded user paths required at runtime),
7-Elf template roster, bone mapping tables, Blender 4.x/5.x F-Curve and
Action Slot helpers, and JSON registry persistence.
"""

import json
import os
import bpy


# ============================================================================
# 1. DYNAMIC RELATIVE PATH RESOLUTION
# ============================================================================

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.dirname(ADDON_DIR)
_FALLBACK_DATABASE_DIR = "/Users/timonterzic/Documents/Projekti/Advent Lift 2026/elf_director_studio/database"


def _load_studio_paths_config() -> dict:
    """Loads optional `_studio_paths.json` written by `install_elf_studio.py` when installed into Blender's addons folder."""
    cfg_path = os.path.join(ADDON_DIR, "_studio_paths.json")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def get_database_dir() -> str:
    """
    Resolves the `database/` directory dynamically so the studio package works
    portably on any machine:
    1. `ELF_DIRECTOR_STUDIO_DIR` environment variable
    2. `_studio_paths.json` inside `elf_director/` (installed Blender Add-on)
    3. `<PACKAGE_DIR>/database` (adjacent to `elf_director/` package)
    4. `<ADDON_DIR>/database` (packaged inside `elf_director/`)
    5. `<blend_dir>/elf_director_studio/database` or `<blend_dir>/database`
    6. Common user clone paths (`~/elf-director-studio/database`, etc.)
    7. Fallback to `/Users/timonterzic/Documents/Projekti/Advent Lift 2026/elf_director_studio/database`
    """
    candidates = []
    env_root = os.environ.get("ELF_DIRECTOR_STUDIO_DIR", "").strip()
    if env_root:
        candidates.append(os.path.join(env_root, "database"))

    cfg = _load_studio_paths_config()
    if cfg.get("database_dir"):
        candidates.append(cfg["database_dir"])
    if cfg.get("studio_root"):
        candidates.append(os.path.join(cfg["studio_root"], "database"))

    candidates.append(os.path.join(PACKAGE_DIR, "database"))
    candidates.append(os.path.join(ADDON_DIR, "database"))

    try:
        blend_path = getattr(bpy.data, "filepath", "") if bpy and hasattr(bpy, "data") else ""
        if blend_path:
            blend_dir = os.path.dirname(os.path.abspath(blend_path))
            candidates.append(os.path.join(blend_dir, "elf_director_studio", "database"))
            candidates.append(os.path.join(blend_dir, "database"))
    except Exception:
        pass

    home = os.path.expanduser("~")
    for sub in ("elf-director-studio", "Documents/elf-director-studio", "Desktop/elf-director-studio"):
        candidates.append(os.path.join(home, sub, "database"))

    candidates.append(_FALLBACK_DATABASE_DIR)

    for cand in candidates:
        if cand and os.path.isdir(cand):
            lib_file = os.path.join(cand, "elf_assets_library.blend")
            part_file = os.path.join(cand, "elf_assets_library.blend.part01")
            reg_file = os.path.join(cand, "registry.json")
            if os.path.exists(lib_file) or os.path.exists(part_file) or os.path.exists(reg_file):
                return cand

    for cand in candidates:
        if cand and os.path.isdir(cand):
            return cand

    return os.path.join(PACKAGE_DIR, "database")


def get_library_blend_path() -> str:
    """
    Returns the resolved path to `database/elf_assets_library.blend`.
    If only split Git chunks (`elf_assets_library.blend.part01`, `.part02`, ...) exist on disk
    (for example right after a fresh `git clone`), automatically reassembles
    `elf_assets_library.blend` seamlessly!
    """
    db_dir = get_database_dir()
    lib_path = os.path.join(db_dir, "elf_assets_library.blend")
    if not os.path.isfile(lib_path):
        part1 = os.path.join(db_dir, "elf_assets_library.blend.part01")
        if os.path.isfile(part1):
            try:
                parts = sorted(
                    f for f in os.listdir(db_dir)
                    if f.startswith("elf_assets_library.blend.part")
                )
                tmp_path = lib_path + ".assembling"
                with open(tmp_path, "wb") as out_f:
                    for pname in parts:
                        with open(os.path.join(db_dir, pname), "rb") as in_f:
                            while True:
                                chunk = in_f.read(8 * 1024 * 1024)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                os.replace(tmp_path, lib_path)
                print(f"[ElfDirector] Automatically assembled {lib_path} from {len(parts)} parts.")
            except Exception as exc:
                print(f"[ElfDirector] Warning assembling library blend: {exc}")
    return lib_path


def get_assets_glb_dir(subfolder: str = "") -> str:
    """
    Resolves `assets/models/glb/<subfolder>` portably across standalone Git clones,
    installed Blender Add-ons (`_studio_paths.json`), and the master project workspace.
    """
    cfg = _load_studio_paths_config()
    roots = []
    env_root = os.environ.get("ELF_DIRECTOR_STUDIO_DIR", "").strip()
    if env_root:
        roots.append(os.path.join(env_root, "assets"))
    if cfg.get("assets_dir"):
        roots.append(cfg["assets_dir"])
    if cfg.get("studio_root"):
        roots.append(os.path.join(cfg["studio_root"], "assets"))

    roots.append(os.path.join(PACKAGE_DIR, "assets"))
    roots.append(os.path.join(os.path.dirname(PACKAGE_DIR), "assets"))
    roots.append(os.path.join(ADDON_DIR, "assets"))

    try:
        blend_path = getattr(bpy.data, "filepath", "") if bpy and hasattr(bpy, "data") else ""
        if blend_path:
            bdir = os.path.dirname(os.path.abspath(blend_path))
            roots.append(os.path.join(bdir, "assets"))
            roots.append(os.path.join(os.path.dirname(bdir), "assets"))
    except Exception:
        pass

    home = os.path.expanduser("~")
    for sub in ("elf-director-studio", "Documents/elf-director-studio", "Desktop/elf-director-studio"):
        roots.append(os.path.join(home, sub, "assets"))

    roots.append("/Users/timonterzic/Documents/Projekti/Advent Lift 2026/assets")

    rel = os.path.join("models", "glb", subfolder) if subfolder else os.path.join("models", "glb")
    for r in roots:
        cand = os.path.join(r, rel)
        if os.path.isdir(cand):
            return cand
    return os.path.join(PACKAGE_DIR, "assets", rel)


def get_registry_json_path() -> str:
    """Returns the resolved path to `database/registry.json`."""
    return os.path.join(get_database_dir(), "registry.json")


def get_dropin_anims_dir() -> str:
    """Returns the resolved path to `database/animations_dropin/` (creating it if needed)."""
    dropin_dir = os.path.join(get_database_dir(), "animations_dropin")
    try:
        os.makedirs(dropin_dir, exist_ok=True)
    except Exception:
        pass
    return dropin_dir


DATABASE_DIR = get_database_dir()
LIBRARY_BLEND_PATH = get_library_blend_path()
REGISTRY_JSON_PATH = get_registry_json_path()
DROPIN_ANIMS_DIR = get_dropin_anims_dir()


# ============================================================================
# 2. SCENE COLLECTION CONSTANTS & GUARD STATE
# ============================================================================

TEMPLATE_COLLECTION_NAME = "00_RIGGED_ELF_TEMPLATES"
ACTORS_COLLECTION_NAME = "01_SCENE_ELF_ACTORS"
PATHS_COLLECTION_NAME = "02_LOCOMOTION_CURVES"

DEFAULT_IDLE_ACTION = "AF_06_Idle_Breathing"
DEFAULT_WALK_ACTION = "AF_01_Walk_Steady"

# Shared mutable state dictionary preventing recursive UI/selection callbacks
STATE = {
    "selection_redirect_guard": False,
    "ui_sync_guard": False,
}


# ============================================================================
# 3. 7-ELF MASTER TEMPLATE ROSTER
# ============================================================================

RIGGED_ELF_ROSTER = [
    {
        "id": "ELF06",
        "code": "#06",
        "title": "#06 Strojovođa (Lokomotiva)",
        "arm_name": "TPL_ARM_Elf06_Strojovodja",
        "col_name": "TPL_Elf06_Strojovodja",
        "lineup_x": -4.5,
        "has_hat": False,
        "has_glasses": True,
    },
    {
        "id": "ELF10",
        "code": "#10",
        "title": "#10 Stari Urar (Horologist)",
        "arm_name": "TPL_ARM_Elf10_Urar",
        "col_name": "TPL_Elf10_Urar",
        "lineup_x": -3.0,
        "has_hat": True,
        "has_glasses": True,
    },
    {
        "id": "ELF14",
        "code": "#14",
        "title": "#14 Majstor Stolar (Woodworker)",
        "arm_name": "TPL_ARM_Elf14_Stolar",
        "col_name": "TPL_Elf14_Stolar",
        "lineup_x": -1.5,
        "has_hat": False,
        "has_glasses": False,
    },
    {
        "id": "ELF16",
        "code": "#16",
        "title": "#16 Bojadišarica (Toy Painter)",
        "arm_name": "TPL_ARM_Elf16_Bojadisarica",
        "col_name": "TPL_Elf16_Bojadisarica",
        "lineup_x": 0.0,
        "has_hat": False,
        "has_glasses": False,
    },
    {
        "id": "ELF21",
        "code": "#21",
        "title": "#21 Pekar Medenjaka (Baker)",
        "arm_name": "TPL_ARM_Elf21_Pekar",
        "col_name": "TPL_Elf21_Pekar",
        "lineup_x": 1.5,
        "has_hat": False,
        "has_glasses": False,
    },
    {
        "id": "ELF23",
        "code": "#23",
        "title": "#23 Stari Birokrat (Pošta)",
        "arm_name": "TPL_ARM_Elf23_Birokrat",
        "col_name": "TPL_Elf23_Birokrat",
        "lineup_x": 3.0,
        "has_hat": True,
        "has_glasses": True,
    },
    {
        "id": "ELF28",
        "code": "#28",
        "title": "#28 Osobni Pomoćnik Djeda",
        "arm_name": "TPL_ARM_Elf28_Pomocnik",
        "col_name": "TPL_Elf28_Pomocnik",
        "lineup_x": 4.5,
        "has_hat": False,
        "has_glasses": False,
    },
]


def get_elf_info(elf_id: str) -> dict:
    """Returns the roster dictionary for `elf_id` (defaults to ELF10 if not found)."""
    for item in RIGGED_ELF_ROSTER:
        if item["id"] == elf_id:
            return item
    return next((e for e in RIGGED_ELF_ROSTER if e["id"] == "ELF10"), RIGGED_ELF_ROSTER[0])


# ============================================================================
# 4. SKELETAL RETARGETING MAPS (ACTIONFORGE <-> MIXAMO / RPM)
# ============================================================================

AF_TO_MIXAMO = {
    "pelvis": "Hips",
    "spine_01": "Spine",
    "spine_02": "Spine1",
    "spine_03": "Spine2",
    "neck_01": "Neck",
    "Head": "Head",
    "head": "Head",
    "clavicle_l": "LeftShoulder",
    "upperarm_l": "LeftArm",
    "lowerarm_l": "LeftForeArm",
    "hand_l": "LeftHand",
    "clavicle_r": "RightShoulder",
    "upperarm_r": "RightArm",
    "lowerarm_r": "RightForeArm",
    "hand_r": "RightHand",
    "thigh_l": "LeftUpLeg",
    "calf_l": "LeftLeg",
    "foot_l": "LeftFoot",
    "ball_l": "LeftToeBase",
    "thigh_r": "RightUpLeg",
    "calf_r": "RightLeg",
    "foot_r": "RightFoot",
    "ball_r": "RightToeBase",
    "thumb_01_l": "LeftHandThumb1",
    "thumb_02_l": "LeftHandThumb2",
    "thumb_03_l": "LeftHandThumb3",
    "index_01_l": "LeftHandIndex1",
    "index_02_l": "LeftHandIndex2",
    "index_03_l": "LeftHandIndex3",
    "middle_01_l": "LeftHandMiddle1",
    "middle_02_l": "LeftHandMiddle2",
    "middle_03_l": "LeftHandMiddle3",
    "ring_01_l": "LeftHandRing1",
    "ring_02_l": "LeftHandRing2",
    "ring_03_l": "LeftHandRing3",
    "pinky_01_l": "LeftHandPinky1",
    "pinky_02_l": "LeftHandPinky2",
    "pinky_03_l": "LeftHandPinky3",
    "thumb_01_r": "RightHandThumb1",
    "thumb_02_r": "RightHandThumb2",
    "thumb_03_r": "RightHandThumb3",
    "index_01_r": "RightHandIndex1",
    "index_02_r": "RightHandIndex2",
    "index_03_r": "RightHandIndex3",
    "middle_01_r": "RightHandMiddle1",
    "middle_02_r": "RightHandMiddle2",
    "middle_03_r": "RightHandMiddle3",
    "ring_01_r": "RightHandRing1",
    "ring_02_r": "RightHandRing2",
    "ring_03_r": "RightHandRing3",
    "pinky_01_r": "RightHandPinky1",
    "pinky_02_r": "RightHandPinky2",
    "pinky_03_r": "RightHandPinky3",
}

# Ordered fallback aliases for CMU Mocap BVH, Bandai Namco BVH, and SMPL/OpenPose rigs
AF_TO_BVH_ALIASES = {
    "pelvis": ("Hips", "pelvis", "root", "joint_Root"),
    "spine_01": ("LowerBack", "Spine", "spine_01"),
    "spine_02": ("Spine", "Spine1", "Chest", "spine_02"),
    "spine_03": ("Spine2", "Spine1", "Chest", "spine_03"),
    "neck_01": ("Neck", "Neck1", "neck_01"),
    "Head": ("Head", "head"),
    "head": ("Head", "head"),
    "clavicle_l": ("LeftShoulder", "Shoulder_L", "L_Collar", "clavicle_l"),
    "upperarm_l": ("LeftArm", "UpperArm_L", "L_Shoulder", "upperarm_l"),
    "lowerarm_l": ("LeftForeArm", "LowerArm_L", "L_Elbow", "lowerarm_l"),
    "hand_l": ("LeftHand", "Hand_L", "L_Wrist", "hand_l"),
    "clavicle_r": ("RightShoulder", "Shoulder_R", "R_Collar", "clavicle_r"),
    "upperarm_r": ("RightArm", "UpperArm_R", "R_Shoulder", "upperarm_r"),
    "lowerarm_r": ("RightForeArm", "LowerArm_R", "R_Elbow", "lowerarm_r"),
    "hand_r": ("RightHand", "Hand_R", "R_Wrist", "hand_r"),
    "thigh_l": ("LeftUpLeg", "UpperLeg_L", "L_Hip", "thigh_l"),
    "calf_l": ("LeftLeg", "LowerLeg_L", "L_Knee", "calf_l"),
    "foot_l": ("LeftFoot", "Foot_L", "L_Ankle", "foot_l"),
    "ball_l": ("LeftToeBase", "Toes_L", "L_Foot", "ball_l"),
    "thigh_r": ("RightUpLeg", "UpperLeg_R", "R_Hip", "thigh_r"),
    "calf_r": ("RightLeg", "LowerLeg_R", "R_Knee", "calf_r"),
    "foot_r": ("RightFoot", "Foot_R", "R_Ankle", "foot_r"),
    "ball_r": ("RightToeBase", "Toes_R", "R_Foot", "ball_r"),
    "middle_01_l": ("LeftHandMiddle1", "LeftHandIndex1", "LeftFingerBase", "middle_01_l"),
    "middle_01_r": ("RightHandMiddle1", "RightHandIndex1", "RightFingerBase", "middle_01_r"),
}

PRIMARY_CHILD = {
    "pelvis": "spine_01",
    "spine_01": "spine_02",
    "spine_02": "spine_03",
    "spine_03": "neck_01",
    "neck_01": "Head",
    "clavicle_l": "upperarm_l",
    "upperarm_l": "lowerarm_l",
    "lowerarm_l": "hand_l",
    "hand_l": "middle_01_l",
    "clavicle_r": "upperarm_r",
    "upperarm_r": "lowerarm_r",
    "lowerarm_r": "hand_r",
    "hand_r": "middle_01_r",
    "thigh_l": "calf_l",
    "calf_l": "foot_l",
    "foot_l": "ball_l",
    "thigh_r": "calf_r",
    "calf_r": "foot_r",
    "foot_r": "ball_r",
    "thumb_01_l": "thumb_02_l",
    "thumb_02_l": "thumb_03_l",
    "index_01_l": "index_02_l",
    "index_02_l": "index_03_l",
    "middle_01_l": "middle_02_l",
    "middle_02_l": "middle_03_l",
    "ring_01_l": "ring_02_l",
    "ring_02_l": "ring_03_l",
    "pinky_01_l": "pinky_02_l",
    "pinky_02_l": "pinky_03_l",
    "thumb_01_r": "thumb_02_r",
    "thumb_02_r": "thumb_03_r",
    "index_01_r": "index_02_r",
    "index_02_r": "index_03_r",
    "middle_01_r": "middle_02_r",
    "middle_02_r": "middle_03_r",
    "ring_01_r": "ring_02_r",
    "ring_02_r": "ring_03_r",
    "pinky_01_r": "pinky_02_r",
    "pinky_02_r": "pinky_03_r",
}


# ============================================================================
# 5. SHARED BLENDER & REGISTRY HELPERS
# ============================================================================

def ensure_collection(name: str, parent_col=None):
    """Ensures a Blender collection exists and is linked to `parent_col` or the active scene."""
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
    target_parent = parent_col if parent_col is not None else bpy.context.scene.collection
    if col.name not in target_parent.children:
        try:
            target_parent.children.link(col)
        except Exception:
            pass
    return col


def load_registry() -> dict:
    """Loads `database/registry.json` if present, or returns a default schema dict."""
    reg_path = get_registry_json_path()
    if os.path.exists(reg_path):
        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"[ElfDirector] Warning: Failed to read registry.json ({e})")

    return {
        "package": "ActionForge Elf Animation Director Studio",
        "version": "3.0.0",
        "schema_version": 3,
        "library_blend": "database/elf_assets_library.blend",
        "template_collection": TEMPLATE_COLLECTION_NAME,
        "actors_collection": ACTORS_COLLECTION_NAME,
        "paths_collection": PATHS_COLLECTION_NAME,
        "elves_count": len(RIGGED_ELF_ROSTER),
        "animations_count": 0,
        "elves": [],
        "animations": [],
    }


def save_registry(data: dict) -> bool:
    """Saves `data` to `database/registry.json` with clean UTF-8 formatting."""
    reg_path = get_registry_json_path()
    try:
        os.makedirs(os.path.dirname(reg_path), exist_ok=True)
        with open(reg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ElfDirector] Error saving registry.json: {e}")
        return False


def get_action_fcurves(action) -> list:
    """
    Returns all F-Curves in `action` across both Blender 4.x (`action.fcurves`)
    and Blender 5.x Layered Actions (`action.layers -> strips -> channelbags -> fcurves`).
    """
    if not action:
        return []
    fcurves = []
    seen = set()
    if hasattr(action, "fcurves"):
        try:
            for fc in action.fcurves:
                if id(fc) not in seen:
                    seen.add(id(fc))
                    fcurves.append(fc)
        except Exception:
            pass
    if hasattr(action, "layers"):
        try:
            for layer in action.layers:
                for strip in getattr(layer, "strips", []):
                    for cb in getattr(strip, "channelbags", []):
                        for fc in getattr(cb, "fcurves", []):
                            if id(fc) not in seen:
                                seen.add(id(fc))
                                fcurves.append(fc)
        except Exception:
            pass
    return fcurves


def bind_action_slot(target, action) -> bool:
    """
    Safely binds Blender 5.x `action.slots[0]` onto `target` (an `AnimData` or `NlaStrip`)
    when available.
    """
    if not target or not action:
        return False
    if hasattr(target, "action_slot") and hasattr(action, "slots"):
        try:
            if len(action.slots) > 0:
                target.action_slot = action.slots[0]
                return True
        except Exception:
            pass
    return False
