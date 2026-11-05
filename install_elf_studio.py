#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ActionForge Elf Animation Director Studio v3.0 — One-Click Universal Installer
==============================================================================
Cross-platform installer (macOS / Windows / Linux) for Humans and AI Agents.

What this script does automatically:
  1. Reassembles `database/elf_assets_library.blend` from Git chunks (`.part01` + `.part02`)
     or downloads it from GitHub Release `v3.0.0` if missing.
  2. Writes `elf_director/_studio_paths.json` pointing to this repository's `database/`
     and `assets/` directories so the add-on works from ANY `.blend` file on the machine.
  3. Rebuilds `elf_director_addon.zip` (with `_studio_paths.json` included).
  4. Detects all installed Blender 4.x / 5.x versions (macOS, Windows, Linux), installs
     `elf_director` into Blender's `scripts/addons/elf_director`, and enables the add-on
     in Blender User Preferences (`bpy.ops.preferences.addon_enable(module="elf_director")`).
  5. Generates a ready-to-open `elf_director_quickstart.blend` scene with all 7 rigged
     elves, 34 animations, and the `Elf Director` N-Panel active.
  6. Optional (`--download-scenes`): Downloads the full studio demo scenes
     (`elves_animation_director_studio.blend` and `minecart_pusher_demo.blend`) from
     GitHub Releases.

Usage:
  python3 install_elf_studio.py
  python3 install_elf_studio.py --download-scenes
"""

import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_SLUG = "timon2200/elf-director-studio"
RELEASE_TAG = "v3.0.0"
RELEASE_BASE_URL = f"https://github.com/{REPO_SLUG}/releases/download/{RELEASE_TAG}"

STUDIO_ROOT = Path(__file__).resolve().parent
ADDON_SRC_DIR = STUDIO_ROOT / "elf_director"
DATABASE_DIR = STUDIO_ROOT / "database"
ASSETS_DIR = STUDIO_ROOT / "assets"
LIBRARY_BLEND = DATABASE_DIR / "elf_assets_library.blend"
ADDON_ZIP_PATH = STUDIO_ROOT / "elf_director_addon.zip"
QUICKSTART_BLEND = STUDIO_ROOT / "elf_director_quickstart.blend"


def log(msg: str):
    print(f"[ElfStudio Installer] {msg}", flush=True)


def ensure_library_blend() -> Path:
    """Reassembles `database/elf_assets_library.blend` from `.part01`+`.part02` or downloads from Release."""
    if LIBRARY_BLEND.is_file() and LIBRARY_BLEND.stat().st_size > 50_000_000:
        log(f"Found library database: {LIBRARY_BLEND.name} ({LIBRARY_BLEND.stat().st_size / (1024*1024):.1f} MB)")
        return LIBRARY_BLEND

    parts = sorted(DATABASE_DIR.glob("elf_assets_library.blend.part*"))
    if parts:
        log(f"Assembling {LIBRARY_BLEND.name} from {len(parts)} repository chunks...")
        tmp_path = DATABASE_DIR / "elf_assets_library.blend.assembling"
        with open(tmp_path, "wb") as out_f:
            for p in parts:
                with open(p, "rb") as in_f:
                    shutil.copyfileobj(in_f, out_f, length=8 * 1024 * 1024)
        tmp_path.replace(LIBRARY_BLEND)
        log(f"Assembled {LIBRARY_BLEND.name} ({LIBRARY_BLEND.stat().st_size / (1024*1024):.1f} MB)")
        return LIBRARY_BLEND

    url = f"{RELEASE_BASE_URL}/elf_assets_library.blend"
    log(f"Downloading {LIBRARY_BLEND.name} from {url} ...")
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, LIBRARY_BLEND)
    log(f"Downloaded {LIBRARY_BLEND.name} ({LIBRARY_BLEND.stat().st_size / (1024*1024):.1f} MB)")
    return LIBRARY_BLEND


def write_studio_paths_config() -> Path:
    """Writes `_studio_paths.json` inside `elf_director/` so the installed add-on finds `database/` & `assets/`."""
    cfg_path = ADDON_SRC_DIR / "_studio_paths.json"
    payload = {
        "studio_root": str(STUDIO_ROOT),
        "database_dir": str(DATABASE_DIR),
        "assets_dir": str(ASSETS_DIR),
    }
    cfg_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Configured portable studio paths -> {cfg_path}")
    return cfg_path


def build_addon_zip() -> Path:
    """Builds `elf_director_addon.zip` ready for Blender Preferences -> Install from Disk."""
    with zipfile.ZipFile(ADDON_ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(ADDON_SRC_DIR.rglob("*")):
            if "__pycache__" in file_path.parts or file_path.suffix in (".pyc", ".pyo"):
                continue
            if file_path.is_file():
                arcname = Path("elf_director") / file_path.relative_to(ADDON_SRC_DIR)
                zf.write(file_path, arcname.as_posix())
    log(f"Built Blender Add-on archive: {ADDON_ZIP_PATH.name} ({ADDON_ZIP_PATH.stat().st_size / 1024:.1f} KB)")
    return ADDON_ZIP_PATH


def find_blender_executable() -> str:
    """Locates the Blender 4.x / 5.x executable on macOS, Windows, or Linux."""
    env_bin = os.environ.get("BLENDER_BIN", "").strip()
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    sys_name = platform.system()
    candidates = []
    if sys_name == "Darwin":
        candidates.extend([
            "/Applications/Blender.app/Contents/MacOS/Blender",
            os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender"),
        ])
        for app in sorted(glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender"), reverse=True):
            candidates.append(app)
    elif sys_name == "Windows":
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        for exe in sorted(glob.glob(os.path.join(prog_files, "Blender Foundation", "Blender*", "blender.exe")), reverse=True):
            candidates.append(exe)
    else:
        candidates.extend([
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/snap/bin/blender",
        ])

    which_blender = shutil.which("blender") or shutil.which("Blender")
    if which_blender:
        candidates.insert(0, which_blender)

    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""


def get_blender_version_tuple(blender_bin: str) -> str:
    """Queries `Blender --version` and returns `<major>.<minor>` (e.g. `5.3`, `4.3`)."""
    if not blender_bin:
        return ""
    try:
        out = subprocess.check_output([blender_bin, "--version"], text=True, stderr=subprocess.DEVNULL, timeout=10)
        m = re.search(r"Blender\s+(\d+\.\d+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def find_blender_addon_dirs(blender_bin: str = "") -> list:
    """Finds all Blender 4.x / 5.x user `scripts/addons` directories on macOS, Windows, or Linux."""
    sys_name = platform.system()
    base_dirs = []
    if sys_name == "Darwin":
        base_dirs.append(Path.home() / "Library" / "Application Support" / "Blender")
    elif sys_name == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            base_dirs.append(Path(appdata) / "Blender Foundation" / "Blender")
    else:
        base_dirs.append(Path.home() / ".config" / "blender")

    addon_dirs = []
    detected_ver = get_blender_version_tuple(blender_bin)

    for base in base_dirs:
        if detected_ver:
            ver_addons = base / detected_ver / "scripts" / "addons"
            ver_addons.mkdir(parents=True, exist_ok=True)
            addon_dirs.append(ver_addons)
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_dir() and re.match(r"^[45]\.\d+$", child.name):
                    ad = child / "scripts" / "addons"
                    ad.mkdir(parents=True, exist_ok=True)
                    if ad not in addon_dirs:
                        addon_dirs.append(ad)
    return addon_dirs


def install_into_blender_addons(addon_dirs: list) -> list:
    """Copies `elf_director/` (including `_studio_paths.json`) into each detected Blender `scripts/addons/` directory."""
    installed = []
    for ad in addon_dirs:
        dst = ad / "elf_director"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(
            ADDON_SRC_DIR,
            dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        installed.append(dst)
        log(f"Installed add-on into Blender: {dst}")
    return installed


def enable_addon_and_build_quickstart(blender_bin: str, build_quickstart: bool = True):
    """Enables `elf_director` in Blender user preferences and builds `elf_director_quickstart.blend`."""
    if not blender_bin:
        log("Blender executable not found on PATH; add-on files copied. Open Blender and enable 'ActionForge Elf Animation Director Studio'.")
        return

    bootstrap_code = (STUDIO_ROOT / "bootstrap_director.py").read_text(encoding="utf-8")
    py_expr = f"""
import bpy, sys
sys.path.insert(0, {repr(str(STUDIO_ROOT))})
try:
    bpy.ops.preferences.addon_enable(module="elf_director")
    bpy.ops.wm.save_userpref()
    print("[ElfStudio Blender] Enabled 'elf_director' in Blender User Preferences.")
except Exception as e:
    print("[ElfStudio Blender] Note enabling addon:", e)

import elf_director as ed
ed.integrate_into_scene(spawn_demo=True)
elves = ed.list_available_elves()
anims = ed.list_available_animations()
print(f"[ElfStudio Blender] Verified {{len(elves)}} rigged elves and {{len(anims)}} animations.")

if {repr(bool(build_quickstart))}:
    txt = bpy.data.texts.get("bootstrap_director.py") or bpy.data.texts.new("bootstrap_director.py")
    txt.clear()
    txt.write({repr(bootstrap_code)})
    txt.use_module = True
    bpy.ops.wm.save_as_mainfile(filepath={repr(str(QUICKSTART_BLEND))}, compress=True)
    print(f"[ElfStudio Blender] Saved ready-to-open scene -> {repr(str(QUICKSTART_BLEND))}")
"""
    log(f"Running headless Blender verification & setup via: {blender_bin}")
    subprocess.run([blender_bin, "-b", "--python-expr", py_expr], check=False)


def download_release_scenes():
    """Downloads the full 500MB studio demo `.blend` files from GitHub Release `v3.0.0`."""
    for fname in ("elves_animation_director_studio.blend", "minecart_pusher_demo.blend"):
        dst = STUDIO_ROOT / fname
        if dst.is_file() and dst.stat().st_size > 100_000_000:
            log(f"Demo scene already present: {fname} ({dst.stat().st_size / (1024*1024):.1f} MB)")
            continue
        url = f"{RELEASE_BASE_URL}/{fname}"
        log(f"Downloading full studio scene {fname} from {url} ...")
        try:
            urllib.request.urlretrieve(url, dst)
            log(f"Downloaded {fname} ({dst.stat().st_size / (1024*1024):.1f} MB)")
        except Exception as exc:
            log(f"Could not download {fname} ({exc}). You can use {QUICKSTART_BLEND.name} right away.")


def main():
    parser = argparse.ArgumentParser(description="Install ActionForge Elf Animation Director Studio v3.0 into Blender.")
    parser.add_argument("--download-scenes", action="store_true", help="Download full demo .blend scenes from GitHub Releases")
    parser.add_argument("--no-quickstart", action="store_true", help="Skip generating elf_director_quickstart.blend")
    args = parser.parse_args()

    log("=== ActionForge Elf Animation Director Studio v3.0 Setup ===")
    ensure_library_blend()
    write_studio_paths_config()
    build_addon_zip()

    blender_bin = find_blender_executable()
    if blender_bin:
        log(f"Detected Blender executable: {blender_bin} (v{get_blender_version_tuple(blender_bin)})")
    addon_dirs = find_blender_addon_dirs(blender_bin)
    install_into_blender_addons(addon_dirs)
    enable_addon_and_build_quickstart(blender_bin, build_quickstart=not args.no_quickstart)

    if args.download_scenes:
        download_release_scenes()

    log("=== Setup Complete! ===")
    log("Open Blender -> press 'N' in the 3D Viewport -> click the 'Elf Director' tab.")
    if QUICKSTART_BLEND.is_file():
        log(f"Or double-click: {QUICKSTART_BLEND}")


if __name__ == "__main__":
    main()
