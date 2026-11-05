# -*- coding: utf-8 -*-
"""
Bootstrap Loader for ActionForge Elf Animation Director Studio v3.0.
Can be embedded inside any `.blend` file (`use_module = True`) or executed directly.
"""

import importlib
import os
import sys
import bpy


def bootstrap_elf_director():
    candidates = []
    env_dir = os.environ.get("ELF_DIRECTOR_STUDIO_DIR", "").strip()
    if env_dir:
        candidates.append(env_dir)
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    if bpy.data.filepath:
        blend_dir = os.path.dirname(os.path.abspath(bpy.data.filepath))
        candidates.append(blend_dir)
        candidates.append(os.path.join(blend_dir, "elf_director_studio"))
    home = os.path.expanduser("~")
    for sub in ("elf-director-studio", "Documents/elf-director-studio", "Desktop/elf-director-studio"):
        candidates.append(os.path.join(home, sub))
    candidates.append("/Users/timonterzic/Documents/Projekti/Advent Lift 2026/elf_director_studio")

    for path in candidates:
        if path and os.path.isdir(os.path.join(path, "elf_director")):
            if path not in sys.path:
                sys.path.insert(0, path)
            break

    import elf_director
    if "elf_director.operators_ui" in sys.modules:
        try:
            elf_director.unregister()
        except Exception:
            pass
    for submod in (
        "constants",
        "previews",
        "database",
        "rig_actors",
        "locomotion",
        "nla_sequencer",
        "human_tools",
        "cliff_baskets",
        "cliff_baskets_ui",
        "minecart_pusher",
        "minecart_pusher_ui",
        "ropeway_gondolas",
        "ropeway_gondolas_ui",
        "operators_ui",
        "agent_sdk",
    ):
        full_name = f"elf_director.{submod}"
        if full_name in sys.modules:
            importlib.reload(sys.modules[full_name])
    importlib.reload(elf_director)
    elf_director.register()
    return elf_director


ed = bootstrap_elf_director()
