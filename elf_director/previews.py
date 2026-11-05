# -*- coding: utf-8 -*-
"""
ActionForge Elf Director Studio v3.0 — Visual Previews & 8-FPS Loop Player
==========================================================================
Manages `bpy.utils.previews` collections for:
  1. 7 Rigged Elf Portrait Thumbnails (`database/previews/elves/<ELF_ID>.png`)
  2. 24 Static Key-Pose Animation Thumbnails (`database/previews/thumbs/<AF_Anim>.png`)
     for the `template_icon_view` visual popup gallery
  3. 8-Frame Low-FPS Flipbook Loop Icons (`database/previews/flipbook/<AF_Anim>__f0..7.png`)
     driven by an 8-FPS `bpy.app.timers` loop right inside the Blender N-Panel!
"""

import os
import time
import bpy
import bpy.utils.previews

from .constants import get_database_dir

_PREVIEW_COLLECTIONS = {}
_LOOP_STATE = {
    "frame_idx": 0,
    "last_tick": 0.0,
    "num_frames": 8,
    "fps": 8.0,
}


def get_previews_root_dir() -> str:
    return os.path.join(get_database_dir(), "previews")


def _ensure_preview_collection():
    pcoll = _PREVIEW_COLLECTIONS.get("main")
    if pcoll is None:
        pcoll = bpy.utils.previews.new()
        _PREVIEW_COLLECTIONS["main"] = pcoll
    return pcoll


def get_elf_preview_icon_id(elf_id: str) -> int:
    """Returns the `icon_id` for a rigged Elf portrait (`ELF06` .. `ELF28`), or 0 if unavailable."""
    if bpy.app.background:
        return 0
    pcoll = _ensure_preview_collection()
    key = f"ELF_{elf_id}"
    if key in pcoll:
        return pcoll[key].icon_id
    img_path = os.path.join(get_previews_root_dir(), "elves", f"{elf_id}.png")
    if os.path.isfile(img_path):
        try:
            thumb = pcoll.load(key, img_path, "IMAGE")
            return thumb.icon_id
        except Exception:
            return 0
    return 0


def get_anim_thumb_icon_id(act_name: str) -> int:
    """Returns the static key-pose `icon_id` for `act_name` (used in `template_icon_view` popup grid)."""
    if bpy.app.background or not act_name:
        return 0
    pcoll = _ensure_preview_collection()
    key = f"THUMB_{act_name}"
    if key in pcoll:
        return pcoll[key].icon_id
    img_path = os.path.join(get_previews_root_dir(), "thumbs", f"{act_name}.png")
    if os.path.isfile(img_path):
        try:
            thumb = pcoll.load(key, img_path, "IMAGE")
            return thumb.icon_id
        except Exception:
            return 0
    return 0


def get_anim_loop_icon_id(act_name: str, frame_override: int = None) -> int:
    """
    Returns the current 8-FPS flipbook loop frame `icon_id` for `act_name`
    (`flipbook/<act_name>__f0..7.png`), falling back to the static thumbnail if not found.
    """
    if bpy.app.background or not act_name:
        return 0
    pcoll = _ensure_preview_collection()
    num_f = int(_LOOP_STATE.get("num_frames", 8))
    if frame_override is not None:
        f_idx = int(frame_override) % num_f
    else:
        f_idx = int(_LOOP_STATE.get("frame_idx", 0)) % num_f

    key = f"LOOP_{act_name}__f{f_idx}"
    if key in pcoll:
        return pcoll[key].icon_id

    img_path = os.path.join(get_previews_root_dir(), "flipbook", f"{act_name}__f{f_idx}.png")
    if os.path.isfile(img_path):
        try:
            thumb = pcoll.load(key, img_path, "IMAGE")
            return thumb.icon_id
        except Exception:
            pass
    return get_anim_thumb_icon_id(act_name)


def get_current_loop_frame_index() -> int:
    return int(_LOOP_STATE.get("frame_idx", 0)) % int(_LOOP_STATE.get("num_frames", 8))


def step_loop_frame(delta: int = 1):
    num_f = int(_LOOP_STATE.get("num_frames", 8))
    _LOOP_STATE["frame_idx"] = (int(_LOOP_STATE.get("frame_idx", 0)) + int(delta)) % num_f


def get_anim_video_path(act_name: str) -> str:
    return os.path.join(get_previews_root_dir(), "videos", f"{act_name}.mp4")


def get_grid_video_path() -> str:
    return os.path.join(get_previews_root_dir(), "all_24_animations_grid_loop.mp4")


def get_html_catalog_path() -> str:
    return os.path.join(get_previews_root_dir(), "index.html")


def preload_all_previews():
    """Preloads all 7 Elf portraits, 24 static thumbnails, and active flipbook frames."""
    if bpy.app.background:
        return
    root = get_previews_root_dir()
    if not os.path.isdir(root):
        return
    elves_dir = os.path.join(root, "elves")
    if os.path.isdir(elves_dir):
        for fn in sorted(os.listdir(elves_dir)):
            if fn.endswith(".png"):
                get_elf_preview_icon_id(os.path.splitext(fn)[0])

    thumbs_dir = os.path.join(root, "thumbs")
    if os.path.isdir(thumbs_dir):
        for fn in sorted(os.listdir(thumbs_dir)):
            if fn.endswith(".png"):
                get_anim_thumb_icon_id(os.path.splitext(fn)[0])


def _is_popup_menu_open(wm) -> bool:
    """Returns True if the user currently has a dropdown or `template_icon_view` popup open."""
    try:
        for win in wm.windows:
            if not win.screen:
                continue
            for reg in getattr(win.screen, "regions", []):
                if reg.type in ("TEMPORARY", "POPUP", "MENU") and reg.width > 2 and reg.height > 2:
                    return True
    except Exception:
        pass
    return False


def _af_preview_loop_timer():
    """
    Lightweight 8-FPS timer callback (`0.125s`) that advances the in-panel animation preview
    frame and tags the `VIEW_3D` `UI` region for redraw when `af_director_live_loop_preview` is True.
    """
    if bpy.app.background:
        return None
    try:
        wm = getattr(bpy.context, "window_manager", None)
        scn = getattr(bpy.context, "scene", None)
        if not wm or not scn:
            return 0.25

        if not getattr(scn, "af_director_live_loop_preview", True):
            return 0.25

        # Do not redraw while a popup menu / dropdown is open so the popup never flickers
        if _is_popup_menu_open(wm):
            return 0.15

        num_f = int(_LOOP_STATE.get("num_frames", 8))
        _LOOP_STATE["frame_idx"] = (int(_LOOP_STATE.get("frame_idx", 0)) + 1) % num_f
        _LOOP_STATE["last_tick"] = time.time()

        # Preload current frame of active animation and tag N-Panel UI region for redraw
        active_anim = getattr(scn, "af_director_anim_enum", "")
        if active_anim and active_anim != "NONE":
            get_anim_loop_icon_id(active_anim)

        for win in wm.windows:
            if not win.screen:
                continue
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for region in area.regions:
                        if region.type == "UI" and region.width > 10:
                            region.tag_redraw()
    except Exception:
        pass
    return 0.125  # 8 FPS


def register_previews():
    if bpy.app.background:
        return
    _ensure_preview_collection()
    preload_all_previews()
    try:
        if not bpy.app.timers.is_registered(_af_preview_loop_timer):
            bpy.app.timers.register(_af_preview_loop_timer, first_interval=0.25, persistent=True)
    except Exception:
        pass


def unregister_previews():
    try:
        if bpy.app.timers.is_registered(_af_preview_loop_timer):
            bpy.app.timers.unregister(_af_preview_loop_timer)
    except Exception:
        pass
    for pcoll in _PREVIEW_COLLECTIONS.values():
        try:
            bpy.utils.previews.remove(pcoll)
        except Exception:
            pass
    _PREVIEW_COLLECTIONS.clear()


def reload_previews():
    unregister_previews()
    register_previews()
