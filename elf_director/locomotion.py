# -*- coding: utf-8 -*-
"""
ActionForge Elf Director Studio v3.0 — Zero-Slip & Dynamic Multi-Clip Curve Locomotion Engine
=============================================================================================
Provides:
  1. Biomechanical stride speed calculation per animation (`get_character_exact_stride_speed`),
  2. Automatic classification of Fixed Event animations (`Walk_Jump`, `NinjaJump`, stationary gestures)
     vs. Auto-Fill Cyclic Locomotion animations (`Walk_Steady`, `Jog_Cycle`, `Run_Sprint`, etc.),
  3. Dynamic Curve Space Solver (`solve_nla_curve_timing_plan`) that automatically calculates
     repeat counts of `FILL` locomotion loops so fixed events (`Walk_Jump`) land at exact landmarks
     (start `0%`, middle `50%`, end `100%` of the curve) while the character's ground speed along
     the curve dynamically changes per clip and across NLA crossfades with zero foot slip!
"""

import json
import math
import bpy
from mathutils import Vector

from .constants import (
    DEFAULT_WALK_ACTION,
    PATHS_COLLECTION_NAME,
    bind_action_slot,
    ensure_collection,
    get_action_fcurves,
)
from .database import compute_armature_leg_length
from .rig_actors import get_character_armature_from_ctrl


# ============================================================================
# 1. BIOMECHANICAL ANTI-SLIDE STRIDE SPEED & CLIP ROLE CLASSIFICATION
# ============================================================================

FIXED_EVENT_KEYWORDS = (
    "jump",
    "hop",
    "leap",
    "land",
    "idle",
    "talk",
    "dance",
    "victory",
    "expression",
    "work",
    "craft",
    "shiftweight",
    "lookaround",
)


def is_default_fill_locomotion_action(act) -> bool:
    """
    Returns True if `act` is a continuous cyclic locomotion loop (e.g. `AF_01_Walk_Steady`,
    `AF_02_Walk_Brisk`, `AF_03_Jog_Cycle`, `AF_04_Run_Sprint`, `AF_05_Walk_Backwards`,
    `AF_11_Walk_Masculine`, `AF_12_Walk_Strafe_Left`, `AF_13_Walk_Strafe_Right`) that should
    automatically stretch/repeat (`FILL`) to bridge curve segments between fixed event clips
    like `AF_14_Walk_Jump`.
    """
    if not act:
        return False
    spd = float(act.get("af_speed_mps", 0.0))
    if spd <= 0.1:
        return False
    nl = act.name.lower()
    if any(kw in nl for kw in FIXED_EVENT_KEYWORDS):
        return False
    return True


def get_character_exact_stride_speed(ctrl_obj, act=None, speed_mult_override=None) -> float:
    """
    Computes the exact ground speed (m/s) for `ctrl_obj` during `act` so its stance feet
    have 0.000 m/s world slip, accounting for:
    - The action's base stride speed (`af_speed_mps`, or `0.0` for stationary clips),
    - The ratio of this character's leg bone length (scaled by `ctrl_obj.scale.z`)
      to the reference rig (`af_ref_leg_len`),
    - The clip's or character's playback speed multiplier (`speed_mult_override` or `af_anim_speed`).
    """
    if not ctrl_obj:
        return 1.42
    if act is None:
        anim_name = ctrl_obj.get("af_anim_name", DEFAULT_WALK_ACTION)
        act = bpy.data.actions.get(anim_name)

    if not act:
        return 1.42

    base_spd = float(act.get("af_speed_mps", 0.0))
    if base_spd <= 0.05:
        # Check if it's a locomotion clip missing metadata; otherwise stationary = 0.0 m/s
        if bool(act.get("af_is_locomotion", False)):
            base_spd = 1.42
        else:
            return 0.0

    ref_leg = float(act.get("af_ref_leg_len", 0.9961))
    scale_z = float(ctrl_obj.scale.z) if ctrl_obj.scale.z > 1e-4 else float(ctrl_obj.get("af_char_scale", 1.0))
    arm_obj = get_character_armature_from_ctrl(ctrl_obj)
    char_leg = compute_armature_leg_length(arm_obj, scale_override=scale_z) if arm_obj else (ref_leg * scale_z)

    leg_ratio = char_leg / max(0.2, ref_leg)
    if speed_mult_override is not None:
        anim_speed = float(speed_mult_override)
    else:
        anim_speed = float(ctrl_obj.get("af_anim_speed", 1.0))
    return round(base_spd * leg_ratio * max(0.1, anim_speed), 4)


# ============================================================================
# 2. DYNAMIC MULTI-CLIP CURVE TIMING & AUTO-FILL SOLVER
# ============================================================================

def solve_nla_curve_timing_plan(ctrl_obj, clip_specs: list, curve_obj=None, fps: float = None) -> dict:
    """
    Solves the exact per-clip repeat counts, frame intervals, and frame-by-frame curve
    progression `u_hat_per_frame` (0.0 .. 1.0) for a multi-clip NLA sequence:
      - Every clip moves along the curve at its own exact biomechanical speed `v_i` (m/s).
      - During NLA crossfades (`blend_in` frames), curve velocity transitions smoothly
        from `v_{i-1}` to `v_i`.
      - `FIXED` event clips (e.g. `AF_14_Walk_Jump`) play their fixed repeat count (`1.0x`),
        while `FILL` locomotion loops (e.g. `AF_03_Jog_Cycle`, `AF_01_Walk_Steady`, `AF_04_Run_Sprint`)
        automatically calculate their `effective_repeat` to fill the remaining curve length!
      - Guarantees symmetric placement: e.g. `[Walk_Jump, Jog_Cycle, Walk_Jump, Jog_Cycle, Walk_Jump]`
        places the first `Walk_Jump` at `0%`, the middle `Walk_Jump` centered at `50%`, and the
        final `Walk_Jump` finishing at `100%` of the curve!
    """
    if fps is None:
        try:
            scn = bpy.context.scene
            fps = float(scn.render.fps) / max(1e-4, float(scn.render.fps_base))
        except Exception:
            fps = 24.0
    fps = max(1.0, float(fps))

    if curve_obj is None and ctrl_obj:
        cname = ctrl_obj.get("af_attached_curve", "")
        if cname:
            curve_obj = bpy.data.objects.get(cname)

    arc_len = compute_curve_true_1d_length(curve_obj) if (curve_obj and curve_obj.type == "CURVE") else 0.0
    default_spd_mult = float(ctrl_obj.get("af_anim_speed", 1.0)) if ctrl_obj else 1.0

    raw_clips = []
    for idx, spec in enumerate(clip_specs or []):
        if isinstance(spec, str):
            act_name = spec
            user_rep = 1.0
            spd_mult = default_spd_mult
            bld = 0 if idx == 0 else 12
            mode = "AUTO"
        elif isinstance(spec, dict):
            act_name = spec.get("action") or spec.get("action_name") or spec.get("name") or ""
            user_rep = float(spec.get("repeat", 1.0))
            spd_mult = float(spec.get("speed", default_spd_mult))
            bld = int(round(float(spec.get("blend", spec.get("blend_in", 0 if idx == 0 else 12)))))
            mode = str(spec.get("mode", "AUTO")).upper()
        else:
            continue

        act = bpy.data.actions.get(act_name)
        if not act:
            continue

        f0_span = max(1.0, float(act.frame_range[1] - act.frame_range[0]))
        spd_mult = max(0.1, round(spd_mult, 3))
        v_mps = get_character_exact_stride_speed(ctrl_obj, act, speed_mult_override=spd_mult)
        t_single_sec = f0_span / (fps * spd_mult)
        dist_single_m = v_mps * t_single_sec

        if mode == "FILL" and dist_single_m > 0.05:
            is_fill = True
        elif mode == "FIXED" or dist_single_m <= 0.05:
            is_fill = False
        else:
            mode = "AUTO"
            is_fill = is_default_fill_locomotion_action(act)

        raw_clips.append({
            "index": len(raw_clips),
            "action": act.name,
            "act_obj": act,
            "f0_span": f0_span,
            "user_repeat": max(0.1, round(user_rep, 2)),
            "speed": spd_mult,
            "blend": 0 if len(raw_clips) == 0 else max(0, bld),
            "mode": mode,
            "is_fill": is_fill,
            "speed_mps": v_mps,
            "t_single_sec": t_single_sec,
            "dist_single_m": dist_single_m,
        })

    if not raw_clips:
        return {
            "clips": [],
            "cycle_frames": 100,
            "arc_len_m": arc_len,
            "total_distance_m": 0.0,
            "u_hat_per_frame": [0.0, 1.0],
        }

    # Solve effective_repeat for FILL clips when attached to a curve
    fill_indices = [i for i, c in enumerate(raw_clips) if c["is_fill"] and c["dist_single_m"] > 0.05]
    fixed_indices = [i for i, c in enumerate(raw_clips) if i not in fill_indices]

    if arc_len > 0.2 and fill_indices:
        dist_fixed_sum = sum(raw_clips[i]["user_repeat"] * raw_clips[i]["dist_single_m"] for i in fixed_indices)

        # Crossfade time overlap adjustment
        blend_overlap_dist = 0.0
        for i in range(1, len(raw_clips)):
            b_sec = float(raw_clips[i]["blend"]) / fps
            v_avg = 0.5 * (raw_clips[i - 1]["speed_mps"] + raw_clips[i]["speed_mps"])
            blend_overlap_dist += v_avg * b_sec

        fill_needed_m = arc_len - dist_fixed_sum + blend_overlap_dist

        # Minimum readable loop count for FILL clips (at least 1.0 cycle per fill slot)
        min_cycles = 1.0
        fill_min_m = sum(
            max(min_cycles, raw_clips[j]["user_repeat"]) * raw_clips[j]["dist_single_m"]
            for j in fill_indices
        )
        fill_target_m = max(fill_needed_m, fill_min_m)

        total_weight = sum(max(0.1, raw_clips[j]["user_repeat"]) for j in fill_indices)
        for j in fill_indices:
            w_j = max(0.1, raw_clips[j]["user_repeat"])
            alloc_dist_m = fill_target_m * (w_j / max(1e-6, total_weight))
            eff_rep = alloc_dist_m / max(0.05, raw_clips[j]["dist_single_m"])
            raw_clips[j]["effective_repeat"] = max(0.5, eff_rep)

        for i in fixed_indices:
            raw_clips[i]["effective_repeat"] = raw_clips[i]["user_repeat"]
    else:
        for c in raw_clips:
            c["effective_repeat"] = c["user_repeat"]

    # Compute exact strip frame intervals [tau_start, tau_end] within 1 cycle
    tau_cursor = 0
    for i, c in enumerate(raw_clips):
        single_frames = max(1.0, c["f0_span"] / c["speed"])
        df = max(4, int(round(c["effective_repeat"] * single_frames)))
        c["duration_frames"] = df
        c["effective_repeat"] = round(float(df) / single_frames, 4)
        if i == 0:
            c["eff_blend"] = 0
            c["tau_start"] = 0
            c["tau_end"] = df
        else:
            prev_df = raw_clips[i - 1]["duration_frames"]
            max_b = max(0, min(int(prev_df * 0.45), int(df * 0.45)))
            eff_b = min(int(c["blend"]), max_b)
            c["eff_blend"] = eff_b
            c["tau_start"] = max(0, tau_cursor - eff_b)
            c["tau_end"] = c["tau_start"] + df
        tau_cursor = c["tau_end"]

    cycle_frames = max(4, tau_cursor)

    # Evaluate instantaneous blended ground speed v_net(tau) at every frame tau in 0 .. cycle_frames
    v_net = [0.0] * (cycle_frames + 1)
    for tau in range(cycle_frames + 1):
        v_val = raw_clips[0]["speed_mps"]
        for i in range(1, len(raw_clips)):
            c = raw_clips[i]
            ts = c["tau_start"]
            te = c["tau_end"]
            eb = c["eff_blend"]
            if tau >= ts:
                if eb > 0 and tau < ts + eb:
                    alpha = float(tau - ts) / float(eb)
                else:
                    alpha = 1.0
                v_val = (1.0 - alpha) * v_val + alpha * c["speed_mps"]
                if tau > te and i < len(raw_clips) - 1:
                    pass
        v_net[tau] = max(0.0, v_val)

    # Integrate cumulative distance s(tau) in meters
    s_cum = [0.0] * (cycle_frames + 1)
    for tau in range(1, cycle_frames + 1):
        v_mid = 0.5 * (v_net[tau - 1] + v_net[tau])
        s_cum[tau] = s_cum[tau - 1] + (v_mid / fps)

    total_dist_m = s_cum[-1]
    if total_dist_m > 1e-5:
        u_hat = [s / total_dist_m for s in s_cum]
    else:
        u_hat = [float(tau) / float(cycle_frames) for tau in range(cycle_frames + 1)]
    u_hat[0] = 0.0
    u_hat[-1] = 1.0

    # Annotate each clip with its exact curve percentage interval [u_start_pct, u_end_pct]
    plan_clips = []
    for c in raw_clips:
        ts = min(cycle_frames, max(0, c["tau_start"]))
        te = min(cycle_frames, max(0, c["tau_end"]))
        tm = min(cycle_frames, max(0, (ts + te) // 2))
        u_s = round(100.0 * u_hat[ts], 1)
        u_e = round(100.0 * u_hat[te], 1)
        u_m = round(100.0 * u_hat[tm], 1)
        plan_clips.append({
            "index": c["index"],
            "action": c["action"],
            "repeat": c["user_repeat"],
            "effective_repeat": c["effective_repeat"],
            "speed": c["speed"],
            "blend": c["blend"],
            "eff_blend": c["eff_blend"],
            "mode": c["mode"],
            "is_fill": c["is_fill"],
            "speed_mps": round(c["speed_mps"], 2),
            "tau_start": ts,
            "tau_end": te,
            "duration_frames": c["duration_frames"],
            "u_start_pct": u_s,
            "u_end_pct": u_e,
            "u_mid_pct": u_m,
            "dist_m": round(s_cum[te] - s_cum[ts], 2),
        })

    return {
        "clips": plan_clips,
        "cycle_frames": cycle_frames,
        "arc_len_m": round(arc_len, 3),
        "total_distance_m": round(total_dist_m, 3),
        "u_hat_per_frame": u_hat,
    }


# ============================================================================
# 3. SEQUENTIAL EDGE-GRAPH UNIFORM ARC-LENGTH CURVE RESAMPLER
# ============================================================================

def _extract_ordered_world_polyline(mesh, mw, is_cyclic: bool) -> list:
    """
    Walks the evaluated 1D curve mesh edge graph in true sequential order
    (from a degree-1 endpoint for open curves, or around the loop for cyclic curves).
    """
    n_verts = len(mesh.vertices)
    if n_verts == 0:
        return []
    if len(mesh.edges) == 0:
        return [mw @ v.co for v in mesh.vertices]

    adj = {i: [] for i in range(n_verts)}
    for e in mesh.edges:
        v0, v1 = int(e.vertices[0]), int(e.vertices[1])
        adj[v0].append(v1)
        adj[v1].append(v0)

    start_v = 0
    if not is_cyclic:
        if len(adj.get(0, [])) == 1:
            start_v = 0
        else:
            endpoints = [v for v, nbrs in adj.items() if len(nbrs) == 1]
            if endpoints:
                start_v = min(endpoints)

    order = [start_v]
    visited = {start_v}
    curr = start_v
    while True:
        nxt = next((nb for nb in adj.get(curr, []) if nb not in visited), None)
        if nxt is None:
            break
        visited.add(nxt)
        order.append(nxt)
        curr = nxt

    pts_world = [mw @ mesh.vertices[i].co for i in order]
    if is_cyclic and len(pts_world) >= 3:
        if (pts_world[0] - pts_world[-1]).length > 1e-4:
            pts_world.append(pts_world[0].copy())
    return pts_world


def resample_curve_uniform_arclength(curve_obj, step_m: float = 0.08, max_points: int = 4) -> float:
    """
    Preserves clean low-point Bezier curves (2..6 points) untouched so humans can
    effortlessly move 3-5 control points in Edit Mode!
    Only simplifies overly dense curves (> 6 points, e.g. from freehand drawing)
    down to `max_points` (default 4) smooth AUTO Bezier points.
    Returns total 1D arc length in meters.
    """
    if not curve_obj or curve_obj.type != "CURVE":
        return 5.0

    cd = curve_obj.data
    is_cyclic = bool(cd.splines and cd.splines[0].use_cyclic_u)

    if (
        len(cd.splines) == 1
        and cd.splines[0].type == "BEZIER"
        and 2 <= len(cd.splines[0].bezier_points) <= 32
    ):
        cd.splines[0].resolution_u = 64
        cd.resolution_u = 64
        curve_obj["af_uniform_resampled"] = True
        return compute_curve_true_1d_length(curve_obj)

    orig_bevel = cd.bevel_depth
    orig_extrude = cd.extrude
    cd.bevel_depth = 0.0
    cd.extrude = 0.0

    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = curve_obj.evaluated_get(deps)
    mesh = eval_obj.to_mesh()

    mw = curve_obj.matrix_world
    mw_inv = mw.inverted()

    pts_world = _extract_ordered_world_polyline(mesh, mw, is_cyclic) if mesh else []
    eval_obj.to_mesh_clear()

    if len(pts_world) < 2:
        cd.bevel_depth = orig_bevel
        cd.extrude = orig_extrude
        return 5.0

    cum_d = [0.0]
    for i in range(1, len(pts_world)):
        cum_d.append(cum_d[-1] + (pts_world[i] - pts_world[i - 1]).length)
    total_len = cum_d[-1]
    if total_len < 0.2:
        cd.bevel_depth = orig_bevel
        cd.extrude = orig_extrude
        return max(0.2, total_len)

    num_samples = max(3, min(6, int(max_points)))
    denom = float(num_samples) if is_cyclic else float(max(1, num_samples - 1))

    uniform_local_pts = []
    idx = 0
    for k in range(num_samples):
        target_s = (total_len * k) / denom
        while idx < len(cum_d) - 2 and cum_d[idx + 1] < target_s:
            idx += 1
        seg_len = max(1e-6, cum_d[idx + 1] - cum_d[idx])
        t = max(0.0, min(1.0, (target_s - cum_d[idx]) / seg_len))
        p_w = pts_world[idx].lerp(pts_world[idx + 1], t)
        uniform_local_pts.append(mw_inv @ p_w)

    cd.splines.clear()
    sp = cd.splines.new(type="BEZIER")
    sp.use_cyclic_u = is_cyclic
    sp.bezier_points.add(len(uniform_local_pts) - 1)
    for i, co in enumerate(uniform_local_pts):
        bp = sp.bezier_points[i]
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    sp.resolution_u = 64
    cd.resolution_u = 64

    cd.bevel_depth = orig_bevel
    cd.extrude = orig_extrude
    curve_obj["af_uniform_resampled"] = True
    return compute_curve_true_1d_length(curve_obj)


def compute_curve_true_1d_length(curve_obj) -> float:
    """Computes the exact 1D centerline arc length of `curve_obj` in world meters (safe in UI draw context)."""
    if not curve_obj or curve_obj.type != "CURVE":
        return 5.0
    cd = curve_obj.data
    orig_bevel = cd.bevel_depth
    orig_extrude = cd.extrude
    try:
        cd.bevel_depth = 0.0
        cd.extrude = 0.0
    except AttributeError:
        cached = float(curve_obj.get("af_cached_arc_len", 0.0))
        if cached > 0.2:
            return cached
        mw = curve_obj.matrix_world
        approx_len = 0.0
        for sp in cd.splines:
            pts = [mw @ bp.co for bp in sp.bezier_points] if sp.type == "BEZIER" else [mw @ Vector(p.co[:3]) for p in sp.points]
            for i in range(1, len(pts)):
                approx_len += (pts[i] - pts[i - 1]).length
            if sp.use_cyclic_u and len(pts) > 2:
                approx_len += (pts[0] - pts[-1]).length
        return max(0.2, approx_len)

    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = curve_obj.evaluated_get(deps)
    mesh = eval_obj.to_mesh()
    mw = curve_obj.matrix_world
    total_len = 0.0
    if mesh and len(mesh.edges) > 0:
        verts = mesh.vertices
        for e in mesh.edges:
            total_len += ((mw @ verts[e.vertices[0]].co) - (mw @ verts[e.vertices[1]].co)).length
    eval_obj.to_mesh_clear()
    cd.bevel_depth = orig_bevel
    cd.extrude = orig_extrude
    res_len = max(0.2, total_len)
    try:
        curve_obj["af_cached_arc_len"] = float(res_len)
    except Exception:
        pass
    return res_len


def create_walk_curve_from_points(
    name: str = "Walk_Path",
    points=None,
    cyclic: bool = False,
    bevel_depth: float = 0.012,
):
    """
    Programmatically builds a smooth, uniformly-resampled 3D Bezier curve in
    `02_LOCOMOTION_CURVES` from a list of `(x, y, z)` points.
    """
    if not points or len(points) < 2:
        points = [(-3.0, -2.0, 0.0), (0.0, -0.5, 0.0), (3.0, -2.0, 0.0)]

    paths_col = ensure_collection(PATHS_COLLECTION_NAME)
    cdata = bpy.data.curves.new(name=name, type="CURVE")
    cdata.dimensions = "3D"
    cdata.resolution_u = 24
    cdata.bevel_depth = float(bevel_depth)

    sp = cdata.splines.new(type="BEZIER")
    sp.use_cyclic_u = bool(cyclic)
    sp.bezier_points.add(len(points) - 1)
    for i, pt in enumerate(points):
        bp = sp.bezier_points[i]
        bp.co = Vector(pt)
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"

    cobj = bpy.data.objects.new(name, cdata)
    paths_col.objects.link(cobj)

    resample_curve_uniform_arclength(cobj, step_m=0.08)
    cobj["af_uniform_resampled"] = True
    return cobj


# ============================================================================
# 4. MULTI-ACTOR & DYNAMIC MULTI-CLIP FOLLOW PATH ENGINE
# ============================================================================

def _extract_stored_nla_specs(ctrl_obj) -> list:
    """Reads `af_nla_sequence_json` from `ctrl_obj` if a multi-clip NLA sequence is active."""
    if not ctrl_obj:
        return []
    raw_json = ctrl_obj.get("af_nla_sequence_json", "")
    if raw_json:
        try:
            data = json.loads(raw_json)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    return []


def attach_controller_to_locomotion_curve(
    context,
    ctrl_obj,
    curve_obj,
    speed_mps=None,
    loop_path: bool = True,
    flip_forward: bool = False,
    start_pct=None,
    _from_nla_rebuild: bool = False,
) -> tuple:
    """
    Attaches `ctrl_obj` (`CTRL_*`) to `curve_obj` using a per-controller `use_fixed_location`
    `FOLLOW_PATH` constraint and dedicated `PathAnim_<ctrl_obj.name>` action.
    - When a multi-clip NLA sequence is active on `ctrl_obj`, dynamically varies the character's
      ground speed along the curve to match each active animation (`Walk_Jump`, `Jog_Cycle`,
      `Run_Sprint`, etc.) and solves `FILL` repeat counts so fixed events align with the curve!
    - Multiple Elves can share the same curve simultaneously at independent speeds and start offsets!
    """
    if context is None:
        context = bpy.context
    if not ctrl_obj or not curve_obj or curve_obj.type != "CURVE":
        return False, "Odaberi vilenjaka i krivulju."

    if getattr(context, "object", None) and context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass

    if not curve_obj.get("af_uniform_resampled"):
        arc_len = resample_curve_uniform_arclength(curve_obj, step_m=0.08)
        curve_obj["af_uniform_resampled"] = True
    else:
        arc_len = compute_curve_true_1d_length(curve_obj)

    if start_pct is None:
        start_pct = float(ctrl_obj.get("af_curve_start_pct", 0.0))
    start_pct = float(start_pct) % 100.0
    u0 = start_pct / 100.0

    ctrl_obj["af_attached_curve"] = curve_obj.name
    ctrl_obj["af_flip_curve_dir"] = bool(flip_forward)
    ctrl_obj["af_curve_start_pct"] = round(start_pct, 2)

    nla_specs = _extract_stored_nla_specs(ctrl_obj)
    if nla_specs and not _from_nla_rebuild:
        from .nla_sequencer import rebuild_nla_sequence_from_specs
        rebuild_nla_sequence_from_specs(ctrl_obj, nla_specs, sync_curve=False)
        nla_specs = _extract_stored_nla_specs(ctrl_obj)

    anim_name = ctrl_obj.get("af_anim_name", DEFAULT_WALK_ACTION)
    act = bpy.data.actions.get(anim_name)

    if speed_mps is None:
        speed_mps = get_character_exact_stride_speed(ctrl_obj, act)
    if speed_mps <= 0.05:
        speed_mps = 1.42
    speed_mps = max(0.05, float(speed_mps))
    ctrl_obj["af_walk_speed"] = float(speed_mps)

    # Keep the Curve datablock 100% passive so multiple Elves can share it without conflict
    cd = curve_obj.data
    cd.dimensions = "3D"
    cd.use_path = True
    cd.use_path_follow = True
    if cd.animation_data:
        cd.animation_data_clear()
    legacy_curve_pa = bpy.data.actions.get(f"PathAnim_{curve_obj.name}")
    if legacy_curve_pa:
        try:
            bpy.data.actions.remove(legacy_curve_pa, do_unlink=True)
        except Exception:
            pass

    fps = context.scene.render.fps / max(1e-4, context.scene.render.fps_base)

    ctrl_obj.location = (0.0, 0.0, 0.0)
    ctrl_obj.rotation_mode = "XYZ"
    ctrl_obj.rotation_euler = (0.0, 0.0, 0.0)

    for c in list(ctrl_obj.constraints):
        if c.type == "FOLLOW_PATH":
            ctrl_obj.constraints.remove(c)

    is_backwards_anim = bool(act and act.get("af_is_backwards", False))
    effective_flip = bool(flip_forward) ^ is_backwards_anim

    con = ctrl_obj.constraints.new(type="FOLLOW_PATH")
    con.name = "AF_Locomotion_FollowPath"
    con.target = curve_obj
    con.use_curve_follow = True
    con.use_fixed_location = True
    con.forward_axis = "TRACK_NEGATIVE_Y" if not effective_flip else "TRACK_Y"
    con.up_axis = "UP_Z"

    # Build per-controller path action on `ctrl_obj.animation_data`
    if not ctrl_obj.animation_data:
        ctrl_obj.animation_data_create()
    path_act_name = f"PathAnim_{ctrl_obj.name}"
    old_pa = bpy.data.actions.get(path_act_name)
    if old_pa:
        bpy.data.actions.remove(old_pa, do_unlink=True)
    pa = bpy.data.actions.new(name=path_act_name)
    ctrl_obj.animation_data.action = pa
    bind_action_slot(ctrl_obj.animation_data, pa)

    data_path = f'constraints["{con.name}"].offset_factor'
    base_offset = max(0, int(ctrl_obj.get("af_frame_offset", 0)))
    start_f = 1 + base_offset

    if nla_specs:
        plan = solve_nla_curve_timing_plan(ctrl_obj, nla_specs, curve_obj=curve_obj, fps=fps)
        u_hat = plan["u_hat_per_frame"]
        duration_frames = plan["cycle_frames"]
    else:
        duration_frames = max(10, int(round((arc_len / max(0.1, speed_mps)) * fps)))
        u_hat = [float(tau) / float(duration_frames) for tau in range(duration_frames + 1)]

    # Insert first keyframe to create Blender 4.x/5.x channelbag F-Curve cleanly
    u_first = (u0 + u_hat[0]) % 1.0 if u0 > 1e-4 else 0.0
    con.offset_factor = u_first
    ctrl_obj.keyframe_insert(data_path=data_path, frame=float(start_f))
    bind_action_slot(ctrl_obj.animation_data, pa)

    fcurves = get_action_fcurves(pa)
    if fcurves:
        fc = fcurves[0]
        n_pts = len(u_hat)
        if len(fc.keyframe_points) < n_pts:
            fc.keyframe_points.add(n_pts - len(fc.keyframe_points))

        prev_u = None
        for tau, uh in enumerate(u_hat):
            frame_val = float(start_f + tau)
            if u0 <= 1e-4 or not loop_path:
                u_val = min(1.0, u0 + uh)
            else:
                if tau == n_pts - 1:
                    u_val = u0
                else:
                    u_val = (u0 + uh) % 1.0

            kp = fc.keyframe_points[tau]
            kp.co = (frame_val, u_val)
            kp.interpolation = "LINEAR"
            if prev_u is not None and u_val < prev_u - 0.35 and tau > 0:
                fc.keyframe_points[tau - 1].interpolation = "CONSTANT"
            prev_u = u_val

        fc.update()
        for m in list(fc.modifiers):
            fc.modifiers.remove(m)
        if loop_path:
            fc.modifiers.new(type="CYCLES")

    if context.scene:
        if nla_specs and loop_path:
            context.scene.frame_start = 1
            context.scene.frame_end = max(duration_frames, start_f + duration_frames - 1)
        elif context.scene.frame_end < duration_frames:
            context.scene.frame_end = max(context.scene.frame_end, duration_frames)

    if nla_specs:
        spd_summary = " -> ".join(f"{c['action'].replace('AF_', '')}({c['speed_mps']:.1f}m/s)" for c in plan["clips"])
        return (
            True,
            f"'{ctrl_obj.name}' dinamički prati '{curve_obj.name}' ({arc_len:.2f} m, {duration_frames}f krug): {spd_summary}",
        )

    return (
        True,
        f"'{ctrl_obj.name}' prati '{curve_obj.name}' ({arc_len:.2f} m @ {speed_mps:.2f} m/s, "
        f"start {start_pct:.0f}%, {duration_frames}f, bez klizanja stopala).",
    )


def detach_controller_from_curve(context, ctrl_obj) -> bool:
    """
    Detaches `ctrl_obj` from its locomotion curve while preserving its current evaluated
    world position and rotation.
    """
    if not ctrl_obj:
        return False
    if context is None:
        context = bpy.context

    deps = context.evaluated_depsgraph_get()
    mw = ctrl_obj.evaluated_get(deps).matrix_world.copy()

    for c in list(ctrl_obj.constraints):
        if c.type == "FOLLOW_PATH":
            ctrl_obj.constraints.remove(c)

    if ctrl_obj.animation_data:
        ctrl_obj.animation_data_clear()
    pa = bpy.data.actions.get(f"PathAnim_{ctrl_obj.name}")
    if pa:
        try:
            bpy.data.actions.remove(pa, do_unlink=True)
        except Exception:
            pass

    ctrl_obj.matrix_world = mw
    ctrl_obj["af_attached_curve"] = ""
    return True
