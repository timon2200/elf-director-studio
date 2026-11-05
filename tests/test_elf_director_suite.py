# -*- coding: utf-8 -*-
"""
Automated Headless QA & Verification Test Suite for `elf_director` v3.0
=======================================================================
Run via:
    blender -b --factory-startup -P elf_director_studio/tests/test_elf_director_suite.py
"""

import math
import os
import sys
import traceback

import bpy
from mathutils import Vector

# Ensure `elf_director_studio` is on sys.path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STUDIO_ROOT = os.path.dirname(THIS_DIR)
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import elf_director as ed
from elf_director.nla_sequencer import get_nla_sequence_clips, move_nla_clip
from elf_director.rig_actors import get_actor_part_meshes, get_character_armature_from_ctrl


def _banner(title: str):
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _quat_angle_diff(q1, q2) -> float:
    """Returns the angular difference in radians between two world orientations (quaternions)."""
    q1_n = q1.normalized()
    q2_n = q2.normalized()
    dot = abs(q1_n.dot(q2_n))
    dot = max(-1.0, min(1.0, dot))
    return 2.0 * math.acos(dot)


def _mesh_world_centroid(mesh_obj, deps) -> Vector:
    """Computes the world-space vertex centroid of the deformed/evaluated mesh object."""
    eval_obj = mesh_obj.evaluated_get(deps)
    temp_mesh = eval_obj.to_mesh()
    mw = eval_obj.matrix_world
    if not temp_mesh or len(temp_mesh.vertices) == 0:
        if temp_mesh:
            eval_obj.to_mesh_clear()
        return mw.translation.copy()
    acc = Vector((0.0, 0.0, 0.0))
    n = len(temp_mesh.vertices)
    for v in temp_mesh.vertices:
        acc += mw @ v.co
    eval_obj.to_mesh_clear()
    return acc / float(n)


def run_all_tests():
    _banner("ACTIONFORGE ELF DIRECTOR STUDIO v3.0 — HEADLESS QA TEST SUITE")
    print(f"Blender Version: {bpy.app.version_string}")
    print(f"Studio Root:     {STUDIO_ROOT}")

    # Clean factory scene objects so we test in a pristine environment
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.fps = 30
    scn.render.fps_base = 1.0
    scn.frame_start = 1
    scn.frame_end = 180

    # =========================================================================
    # TEST 1: Library Integration
    # =========================================================================
    _banner("TEST 1: Library Integration (`ed.integrate_into_scene()`)")
    res_int = ed.integrate_into_scene(spawn_demo=False)
    print("Integration Result:", res_int)
    assert res_int.get("ok") is True, "integrate_into_scene() did not return ok=True"
    assert res_int.get("total_templates") == 7, f"Expected 7 templates, got {res_int.get('total_templates')}"
    assert res_int.get("total_actions") >= 24, f"Expected >= 24 AF_* actions, got {res_int.get('total_actions')}"

    elves_info = ed.list_available_elves()
    assert len(elves_info) == 7, f"Expected 7 elves in roster, got {len(elves_info)}"
    for e in elves_info:
        assert e["loaded"] is True, f"Template armature not loaded for {e['id']} ({e['template_armature']})"
        assert bpy.data.objects.get(e["template_armature"]) is not None

    anims_info = ed.list_available_animations()
    assert len(anims_info) >= 24, f"Expected >= 24 animations from list_available_animations(), got {len(anims_info)}"

    # Verify zero external library dependencies (everything appended locally & textures packed)
    linked_libs = list(bpy.data.libraries)
    assert len(linked_libs) == 0, f"Expected 0 external linked libraries, found: {[l.filepath for l in linked_libs]}"
    unpacked_external_imgs = [
        img.name
        for img in bpy.data.images
        if img.name not in ("Render Result", "Viewer Node")
        and img.source == "FILE"
        and img.packed_file is None
    ]
    assert len(unpacked_external_imgs) == 0, f"Found unpacked external images: {unpacked_external_imgs}"
    print(f"[PASS] Test 1: Loaded {len(elves_info)} templates and {len(anims_info)} animations with 0 external dependencies.")

    # =========================================================================
    # TEST 2: Spawning & 4-Part Meshes
    # =========================================================================
    _banner("TEST 2: Spawning & 4-Part Meshes (`ELF10` & `ELF14`)")
    elf10 = ed.spawn("ELF10", location=(-1.5, 0.0, 0.0), animation="AF_01_Walk_Steady")
    elf14 = ed.spawn("ELF14", location=(1.5, 0.0, 0.0), animation="AF_01_Walk_Steady")

    assert elf10 is not None and elf10.name.startswith("CTRL_ELF10_"), f"Invalid ELF10 controller: {elf10}"
    assert elf14 is not None and elf14.name.startswith("CTRL_ELF14_"), f"Invalid ELF14 controller: {elf14}"
    assert elf10.get("af_is_char_controller") is True
    assert elf14.get("af_is_char_controller") is True

    arm10 = get_character_armature_from_ctrl(elf10)
    arm14 = get_character_armature_from_ctrl(elf14)
    assert arm10 is not None and arm10.type == "ARMATURE", "ELF10 missing child armature"
    assert arm14 is not None and arm14.type == "ARMATURE", "ELF14 missing child armature"

    parts10 = get_actor_part_meshes(elf10)
    parts14 = get_actor_part_meshes(elf14)
    print("ELF10 parts:", {k: v.name for k, v in parts10.items()})
    print("ELF14 parts:", {k: v.name for k, v in parts14.items()})

    for req_part in ("BODY", "HEAD", "HAT", "GLASSES"):
        assert req_part in parts10, f"ELF10 missing part {req_part}"
        assert parts10[req_part].get("af_part_type") == req_part, f"ELF10 {req_part} has wrong af_part_type"

    for req_part in ("BODY", "HEAD"):
        assert req_part in parts14, f"ELF14 missing part {req_part}"
        assert parts14[req_part].get("af_part_type") == req_part, f"ELF14 {req_part} has wrong af_part_type"
    assert "HAT" not in parts14 and "GLASSES" not in parts14, "ELF14 should only have BODY and HEAD by default"
    print("[PASS] Test 2: Spawned ELF10 (4 parts) and ELF14 (2 parts) with valid controllers, armatures, and af_part_type tags.")

    # =========================================================================
    # TEST 3: Accessories Toggle & 1-Click Equip
    # =========================================================================
    _banner("TEST 3: Accessories Toggle & 1-Click Equip")
    acc_off = ed.set_accessories(elf10, hat=False, glasses=False)
    assert acc_off["show_hat"] is False and acc_off["show_glasses"] is False
    assert parts10["HAT"].hide_viewport is True and parts10["HAT"].hide_render is True
    assert parts10["GLASSES"].hide_viewport is True and parts10["GLASSES"].hide_render is True

    acc_on = ed.set_accessories(elf10, hat=True, glasses=True)
    assert acc_on["show_hat"] is True and acc_on["show_glasses"] is True
    assert parts10["HAT"].hide_viewport is False and parts10["HAT"].hide_render is False
    assert parts10["GLASSES"].hide_viewport is False and parts10["GLASSES"].hide_render is False

    # Equip Hat & Glasses onto ELF14 (who only has BODY & HEAD by default)
    acc_equip = ed.set_accessories(elf14, hat=True, glasses=True)
    parts14_after = get_actor_part_meshes(elf14)
    print("ELF14 parts after equip:", {k: v.name for k, v in parts14_after.items()})
    assert acc_equip["has_hat"] is True and acc_equip["has_glasses"] is True
    assert acc_equip["show_hat"] is True and acc_equip["show_glasses"] is True
    assert "HAT" in parts14_after and "GLASSES" in parts14_after

    hat14 = parts14_after["HAT"]
    glasses14 = parts14_after["GLASSES"]
    assert hat14.name == f"{arm14.name}_HAT", f"Expected {arm14.name}_HAT, got {hat14.name}"
    assert glasses14.name == f"{arm14.name}_GLASSES", f"Expected {arm14.name}_GLASSES, got {glasses14.name}"
    assert hat14.hide_viewport is False and hat14.hide_render is False
    assert glasses14.hide_viewport is False and glasses14.hide_render is False

    # Verify <arm>_HAT and <arm>_GLASSES are bound to Head and move when Head pose bone moves!
    scn.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    hat_c_before = _mesh_world_centroid(hat14, deps)
    glasses_c_before = _mesh_world_centroid(glasses14, deps)

    # Apply a strong Head pitch/yaw offset to ELF14 and verify deformed HAT and GLASSES centroids move
    ed.set_pose_offset(elf14, head_yaw=40.0, head_pitch=-25.0, torso_bend=20.0)
    scn.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    hat_c_after = _mesh_world_centroid(hat14, deps)
    glasses_c_after = _mesh_world_centroid(glasses14, deps)

    hat_shift = (hat_c_after - hat_c_before).length
    glasses_shift = (glasses_c_after - glasses_c_before).length
    print(f"ELF14 equipped HAT centroid shift: {hat_shift:.4f} m, GLASSES shift: {glasses_shift:.4f} m")
    assert hat_shift > 0.02, f"ELF14 equipped HAT did not move with Head bone (shift={hat_shift:.5f}m)"
    assert glasses_shift > 0.02, f"ELF14 equipped GLASSES did not move with Head bone (shift={glasses_shift:.5f}m)"

    # Reset ELF14 pose offset
    ed.set_pose_offset(elf14, head_yaw=0.0, head_pitch=0.0, torso_bend=0.0)
    print("[PASS] Test 3: Accessories toggle on ELF10 and 1-click equip + Head deformation on ELF14 verified.")

    # =========================================================================
    # TEST 4: Multi-Character Shared Curve Locomotion & `start_pct` Wrap-Around
    # =========================================================================
    _banner("TEST 4: Multi-Character Shared Curve Locomotion & `start_pct` Wrap-Around")
    shared_curve = ed.create_walk_curve(
        "Test_Shared_Curve",
        points=[(-3.0, -2.0, 0.0), (0.0, 0.0, 0.0), (3.0, -2.0, 0.0)],
        cyclic=False,
    )
    assert shared_curve is not None and shared_curve.type == "CURVE"

    ok10, msg10 = ed.follow_curve(elf10, shared_curve, start_pct=0.0, loop=True)
    ok14, msg14 = ed.follow_curve(elf14, shared_curve, start_pct=50.0, loop=True)
    print("Follow curve ELF10:", ok10, msg10)
    print("Follow curve ELF14:", ok14, msg14)
    assert ok10 is True and ok14 is True

    sample_frames = [1, 20, 40, 60, 80, 100, 120]
    pos10 = {}
    pos14 = {}

    for f in sample_frames:
        scn.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        p10 = elf10.evaluated_get(deps).matrix_world.translation.copy()
        p14 = elf14.evaluated_get(deps).matrix_world.translation.copy()
        pos10[f] = p10
        pos14[f] = p14
        sep = (p10 - p14).length
        print(
            f"  Frame {f:3d} | ELF10=( {p10.x:6.3f}, {p10.y:6.3f}, {p10.z:5.3f} ) | "
            f"ELF14=( {p14.x:6.3f}, {p14.y:6.3f}, {p14.z:5.3f} ) | sep={sep:.3f}m"
        )
        assert sep > 0.30, f"ELF10 and ELF14 collided/overlapped at frame {f} (sep={sep:.4f}m)"
        # Ensure neither character flew off the curve bounds
        assert -4.0 <= p10.x <= 4.0 and -3.0 <= p10.y <= 1.0, f"ELF10 out of curve bounds at frame {f}: {p10}"
        assert -4.0 <= p14.x <= 4.0 and -3.0 <= p14.y <= 1.0, f"ELF14 out of curve bounds at frame {f}: {p14}"

    # Compute cumulative path distance traveled across sample_frames
    dist10 = sum((pos10[sample_frames[i]] - pos10[sample_frames[i - 1]]).length for i in range(1, len(sample_frames)))
    # For ELF14, exclude the single wrap-around jump interval when summing forward travel, or sum all intervals
    step_dists_14 = [
        (pos14[sample_frames[i]] - pos14[sample_frames[i - 1]]).length
        for i in range(1, len(sample_frames))
    ]
    # Every single 20-frame interval must show active movement (> 0.4m), proving ELF14 is NEVER stuck at 50% or 100%!
    for i in range(1, len(sample_frames)):
        f_prev, f_cur = sample_frames[i - 1], sample_frames[i]
        d10 = (pos10[f_cur] - pos10[f_prev]).length
        d14 = (pos14[f_cur] - pos14[f_prev]).length
        assert d10 > 0.40, f"ELF10 stuck between frames {f_prev}..{f_cur} (d={d10:.4f}m)"
        assert d14 > 0.40, f"ELF14 stuck between frames {f_prev}..{f_cur} (d={d14:.4f}m)"

    total_dist14 = sum(step_dists_14)
    print(f"Total distance sampled — ELF10: {dist10:.3f} m, ELF14: {total_dist14:.3f} m")
    assert dist10 > 3.0, f"ELF10 traveled < 3.0m ({dist10:.3f}m)"
    assert total_dist14 > 3.0, f"ELF14 traveled < 3.0m ({total_dist14:.3f}m)"

    # Verify ELF14 wrapped past 1.0 (x > 0 before wrap at f=60, and back to x < 0 on the first half of curve at f=80,100,120)
    assert pos14[1].x > -0.5 and pos14[60].x > 1.5, f"ELF14 did not advance toward curve end (f1={pos14[1].x:.2f}, f60={pos14[60].x:.2f})"
    assert pos14[100].x < 0.0, f"ELF14 did not wrap around to the start half of the curve at frame 100 (x={pos14[100].x:.3f})"
    assert pos14[120].x > pos14[100].x + 0.4, (
        f"ELF14 did not continue advancing after wrap-around (f100.x={pos14[100].x:.3f}, f120.x={pos14[120].x:.3f})"
    )
    print("[PASS] Test 4: Multi-character shared curve & 50% wrap-around verified.")

    # =========================================================================
    # TEST 5: Character Scale & Proportional Stride Speed
    # =========================================================================
    _banner("TEST 5: Character Scale & Proportional Stride Speed")
    spd_before = float(elf10["af_walk_speed"])
    applied_scale = ed.set_scale(elf10, 1.3)
    spd_after = float(elf10["af_walk_speed"])
    ratio = spd_after / spd_before
    print(f"Scale: {applied_scale:.2f} | Walk speed before: {spd_before:.4f} m/s -> after: {spd_after:.4f} m/s (ratio={ratio:.4f})")
    assert abs(elf10.scale.z - 1.3) < 1e-4, f"Expected ctrl.scale.z == 1.3, got {elf10.scale.z}"
    assert abs(ratio - 1.3) < 0.01, f"Expected walk speed to scale by 1.3x, got {ratio:.4f}x"
    print("[PASS] Test 5: Character scale and 1.3x proportional stride speed verified.")

    # =========================================================================
    # TEST 6: NLA Animation Chaining, Reordering, Clip Removal & Clear
    # =========================================================================
    _banner("TEST 6: NLA Animation Chaining, Reordering, Clip Removal & Clear")
    ok_chain, msg_chain = ed.chain_animations(
        elf14,
        [
            "AF_01_Walk_Steady",
            {"action": "AF_08_Talking_Gestures", "repeat": 1.0, "blend": 10},
            "AF_09_Victory_Dance",
        ],
    )
    print("Chain result:", ok_chain, msg_chain)
    assert ok_chain is True, f"chain_animations failed: {msg_chain}"

    clips = get_nla_sequence_clips(elf14)
    print("Chained clips:", [c["action_name"] for c in clips])
    assert len(clips) == 3, f"Expected 3 NLA clips, got {len(clips)}"
    assert [c["action_name"] for c in clips] == [
        "AF_01_Walk_Steady",
        "AF_08_Talking_Gestures",
        "AF_09_Victory_Dance",
    ]
    assert int(round(clips[1]["blend_in"])) == 10, f"Expected clip 1 blend_in == 10, got {clips[1]['blend_in']}"

    # Reorder clip 1 UP -> becomes index 0
    ok_move, msg_move = move_nla_clip(elf14, 1, "UP")
    print("Move clip 1 UP:", ok_move, msg_move)
    assert ok_move is True
    clips_moved = get_nla_sequence_clips(elf14)
    assert [c["action_name"] for c in clips_moved] == [
        "AF_08_Talking_Gestures",
        "AF_01_Walk_Steady",
        "AF_09_Victory_Dance",
    ]

    # Remove clip at index 1 ("AF_01_Walk_Steady")
    ok_rem, msg_rem = ed.remove_nla_clip(elf14, 1)
    print("Remove clip 1:", ok_rem, msg_rem)
    assert ok_rem is True
    clips_rem = get_nla_sequence_clips(elf14)
    assert len(clips_rem) == 2
    assert [c["action_name"] for c in clips_rem] == [
        "AF_08_Talking_Gestures",
        "AF_09_Victory_Dance",
    ]

    # Clear NLA
    ok_clr = ed.clear_nla(elf14)
    assert ok_clr is True
    assert len(get_nla_sequence_clips(elf14)) == 0
    print("[PASS] Test 6: NLA chaining, reordering, clip removal, and clear verified.")

    # =========================================================================
    # TEST 7: Non-Destructive Additive Pose Offset
    # =========================================================================
    _banner("TEST 7: Non-Destructive Additive Pose Offset")
    scn.frame_set(15)
    deps = bpy.context.evaluated_depsgraph_get()
    eval_arm10 = arm10.evaluated_get(deps)
    head_rot_before = (eval_arm10.matrix_world @ eval_arm10.pose.bones["Head"].matrix).to_quaternion()

    ok_pose = ed.set_pose_offset(elf10, head_yaw=30.0, head_pitch=-15.0, torso_bend=10.0)
    assert ok_pose is True

    scn.frame_set(15)
    deps = bpy.context.evaluated_depsgraph_get()
    eval_arm10 = arm10.evaluated_get(deps)
    head_rot_after = (eval_arm10.matrix_world @ eval_arm10.pose.bones["Head"].matrix).to_quaternion()

    rot_diff_rad = _quat_angle_diff(head_rot_before, head_rot_after)
    print(f"ELF10 Head world rotation change at frame 15: {rot_diff_rad:.4f} rad ({math.degrees(rot_diff_rad):.2f} deg)")
    assert rot_diff_rad > 0.20, f"Expected Head rotation change > 0.20 rad, got {rot_diff_rad:.4f} rad"

    # Verify pelvis / thigh_l still animate between frame 1 and frame 15!
    scn.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    eval_arm10_f1 = arm10.evaluated_get(deps)
    thigh_rot_f1 = eval_arm10_f1.pose.bones["thigh_l"].matrix.to_quaternion()
    pelvis_head_f1 = eval_arm10_f1.pose.bones["pelvis"].head.copy()

    scn.frame_set(15)
    deps = bpy.context.evaluated_depsgraph_get()
    eval_arm10_f15 = arm10.evaluated_get(deps)
    thigh_rot_f15 = eval_arm10_f15.pose.bones["thigh_l"].matrix.to_quaternion()
    pelvis_head_f15 = eval_arm10_f15.pose.bones["pelvis"].head.copy()

    thigh_anim_delta = _quat_angle_diff(thigh_rot_f1, thigh_rot_f15)
    pelvis_anim_delta = (pelvis_head_f15 - pelvis_head_f1).length
    print(f"Underlying animation delta (frame 1 -> 15): thigh_l={thigh_anim_delta:.4f} rad, pelvis={pelvis_anim_delta:.4f} m")
    assert thigh_anim_delta > 0.05 or pelvis_anim_delta > 0.005, "Base walk animation stopped playing after pose offset!"
    print("[PASS] Test 7: Additive pose offset (> 0.2 rad) + underlying walk animation verified.")

    # =========================================================================
    # TEST 8: Snap to Ground & Look At
    # =========================================================================
    _banner("TEST 8: Snap to Ground & Look At")
    # Detach ELF14 from curve first so we can move & orient it freely on the test floor
    ed.detach_curve(elf14)

    bpy.ops.mesh.primitive_plane_add(size=10.0, location=(2.0, 2.0, 1.25))
    test_floor = bpy.context.active_object
    test_floor.name = "QA_Test_Floor"

    elf14.location = Vector((2.0, 2.0, 5.0))
    ok_snap, msg_snap = ed.snap_to_ground(elf14)
    print("Snap to ground:", ok_snap, msg_snap)
    assert ok_snap is True
    assert abs(elf14.location.z - 1.25) < 0.02, f"Expected elf14.location.z ~ 1.25, got {elf14.location.z}"

    ok_look, msg_look = ed.look_at(elf14, (5.0, 2.0, 1.25))
    print("Look at (5.0, 2.0, 1.25):", ok_look, msg_look)
    assert ok_look is True

    deps = bpy.context.evaluated_depsgraph_get()
    mw14 = elf14.evaluated_get(deps).matrix_world
    forward_vec = (mw14.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
    expected_dir = Vector((1.0, 0.0, 0.0))
    dot_fwd = forward_vec.dot(expected_dir)
    print(f"ELF14 -Y forward vector: ({forward_vec.x:.4f}, {forward_vec.y:.4f}, {forward_vec.z:.4f}), dot={dot_fwd:.4f}")
    assert dot_fwd > 0.99, f"ELF14 -Y forward vector does not point towards (5.0, 2.0): dot={dot_fwd:.4f}"

    # Remove temporary floor plane and re-attach ELF14 to Test_Shared_Curve at start_pct=50% for Test 9 scene verification
    bpy.data.objects.remove(test_floor, do_unlink=True)
    ed.follow_curve(elf14, shared_curve, start_pct=50.0, loop=True)
    print("[PASS] Test 8: Snap to ground (Z=1.25) and Look-At (-Y forward alignment) verified.")

    # =========================================================================
    # TEST 9: Scene Verification API
    # =========================================================================
    _banner("TEST 9: Scene Verification API (`ed.verify_scene()`)")
    ver_res = ed.verify_scene()
    print("verify_scene() output:", ver_res)
    assert ver_res["ok"] is True, f"verify_scene() reported issues: {ver_res['issues']}"
    assert len(ver_res["issues"]) == 0, f"Expected 0 issues, got: {ver_res['issues']}"
    assert ver_res["actors_checked"] == 2, f"Expected 2 actors checked, got {ver_res['actors_checked']}"

    manifest = ed.get_scene_manifest()
    assert manifest["actors_count"] == 2
    assert manifest["curves_count"] == 1
    print("[PASS] Test 9: verify_scene() passed with 0 issues across all scene actors.")

    _banner("ALL 9 QA TESTS PASSED 100%!")


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as exc:
        print("\n[FAIL] QA Test Suite failed with exception:")
        traceback.print_exc()
        sys.exit(1)
