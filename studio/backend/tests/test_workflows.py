import json
import pytest
from pathlib import Path
from app import workflows
from app.config import WORKFLOWS_DIR


def test_build_describe_graph_sets_prompt_and_seed():
    graph = workflows.build_describe_graph(
        identity_string="a synthetic woman, late 20s, athletic build",
        angle="front", seed=48120, count=8,
    )
    assert "front-facing" in graph["5"]["inputs"]["text"]
    assert "a synthetic woman, late 20s, athletic build" in graph["5"]["inputs"]["text"]
    assert graph["8"]["inputs"]["seed"] == 48120
    assert graph["7"]["inputs"]["batch_size"] == 8


def test_build_describe_graph_includes_realism_negative():
    graph = workflows.build_describe_graph(
        identity_string="a synthetic man, 30s", angle="body", seed=1, count=1,
    )
    assert "glossy render" in graph["6"]["inputs"]["text"].lower()


def test_build_describe_graph_uses_correct_angle_phrase():
    for angle, phrase in [("front", "front-facing"), ("34", "three-quarter turn"),
                           ("profile", "full profile"), ("body", "full-body standing")]:
        graph = workflows.build_describe_graph(
            identity_string="a synthetic person", angle=angle, seed=1, count=1,
        )
        assert phrase in graph["5"]["inputs"]["text"]


def test_qwen_sheet_describe_json_exists_and_has_expected_nodes():
    data = json.loads((WORKFLOWS_DIR / "qwen-sheet-describe.json").read_text())
    for node_id in ["5", "6", "7", "8", "11"]:
        assert node_id in data


def test_build_reference_graph_sets_ref_image_and_seed():
    graph = workflows.build_reference_graph(
        ref_image_path="uploads/ref123.png", angle="front", seed=48120,
        count=8,
    )
    assert graph["2"]["inputs"]["image"] == "uploads/ref123.png"
    assert graph["8"]["inputs"]["seed"] == 48120
    # node 7 is a fixed EmptySD3LatentImage canvas (so framing no longer inherits
    # the reference photo's aspect); its batch field is "batch_size"
    assert graph["7"]["inputs"]["batch_size"] == 8


def test_build_reference_graph_runs_at_full_denoise():
    # Qwen-Image-Edit only re-shoots the angle at full denoise; lower values
    # reconstruct the input photo (see workflows._REFERENCE_DENOISE rationale).
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )
    assert graph["8"]["inputs"]["denoise"] == pytest.approx(1.0)


def test_build_reference_graph_includes_angle_phrase_and_negative():
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="profile", seed=1, count=1,
    )
    # node 5/6 are TextEncodeQwenImageEdit (verified graph); text field is "prompt"
    assert "full profile" in graph["5"]["inputs"]["prompt"]
    assert "glossy render" in graph["6"]["inputs"]["prompt"].lower()


def test_build_reference_graph_locks_identity_on_every_angle():
    # Reference mode reproduces a real person's likeness; instruct the edit model
    # to keep the exact face on all angles, not just the close ones.
    for angle in ["front", "34", "profile", "body"]:
        graph = workflows.build_reference_graph(
            ref_image_path="r.png", angle=angle, seed=1, count=1,
        )
        assert "same face and facial identity" in graph["5"]["inputs"]["prompt"]


def test_build_reference_graph_adds_face_focus_on_body_only():
    # Only the body shot shrinks the face, so only it gets the face-focus clause.
    # Profile is a silhouette (one eye visible) and must NOT get it; front/34 are
    # already close to the reference.
    body = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=1, count=1,
    )
    assert "sharp focus" in body["5"]["inputs"]["prompt"]
    for angle in ["front", "34", "profile"]:
        graph = workflows.build_reference_graph(
            ref_image_path="r.png", angle=angle, seed=1, count=1,
        )
        assert "sharp focus" not in graph["5"]["inputs"]["prompt"]


def test_reference_front_and_34_face_the_camera():
    # The selfie source looks off-camera; front/34 must be re-posed to look into
    # the lens as a deliberate studio portrait.
    for angle in ["front", "34"]:
        graph = workflows.build_reference_graph(
            ref_image_path="r.png", angle=angle, seed=1, count=1,
        )
        p = graph["5"]["inputs"]["prompt"]
        assert "studio model portrait" in p
        assert "camera" in p


def test_reference_negative_rejects_selfie_cues():
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )
    neg = graph["6"]["inputs"]["prompt"].lower()
    assert "selfie" in neg
    assert "reaching toward the camera" in neg


def test_reference_body_starts_from_photo_and_description_enhances():
    # Body starts from the reference physique; the description enhances it (not a
    # text-built body, not a hard override).
    desc = "a synthetic woman, Filipino, mid 40s, chubby build, thick thighs"
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=1, count=1,
        identity_string=desc,
    )
    p = graph["5"]["inputs"]["prompt"]
    assert "start from the reference person's real body" in p
    assert "figure is enhanced by this description" in p
    assert desc in p


def test_reference_output_reframes_regardless_of_source_angle():
    # A weirdly-angled reference must still yield an upright studio shot at the
    # requested angle — the source tilt/angle is overridden, not inherited.
    for angle in ["front", "34", "profile", "body"]:
        graph = workflows.build_reference_graph(
            ref_image_path="r.png", angle=angle, seed=1, count=1,
        )
        assert "ignores the reference photo's original camera angle" in graph["5"]["inputs"]["prompt"]
        assert "dutch angle" in graph["6"]["inputs"]["prompt"].lower()
    # Front squares the whole body to the camera, not just the face.
    front = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )
    assert "shoulders and hips squared to the camera" in front["5"]["inputs"]["prompt"]


def test_reference_negative_does_not_lock_body_proportions():
    # The body-drift negatives would forbid the proportion changes the description
    # asks for, so they must NOT be present.
    neg = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=1, count=1,
    )["6"]["inputs"]["prompt"].lower()
    assert "changed body proportions" not in neg
    assert "altered physique" not in neg


def test_reference_description_is_optional():
    # No description passed -> prompt still builds cleanly (no dangling "None").
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )
    assert "None" not in graph["5"]["inputs"]["prompt"]


def test_profile_forces_true_side_view():
    # The edit model kept returning a frontal grin for "profile"; force a real 90°
    # side view and ban the front view in the negative.
    g = workflows.build_reference_graph(
        ref_image_path="r.png", angle="profile", seed=1, count=1,
    )
    assert "90-degree side profile" in g["5"]["inputs"]["prompt"]
    assert "front view" in g["6"]["inputs"]["prompt"].lower()


def test_body_pose_shows_feet_and_upright_posture():
    g = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=1, count=1,
    )
    p = g["5"]["inputs"]["prompt"]
    assert "both feet visible" in p
    assert "head to feet" in p


def test_front_pose_no_head_tilt_eyeline_to_lens():
    p = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )["5"]["inputs"]["prompt"]
    assert "no tilt" in p
    assert "eyeline to the lens" in p


def test_reference_negative_guards_anatomy():
    neg = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=1, count=1,
    )["6"]["inputs"]["prompt"].lower()
    assert "extra fingers" in neg


def test_front_has_no_profile_only_negative():
    # The profile-only negative must not leak onto other angles.
    front_neg = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )["6"]["inputs"]["prompt"].lower()
    assert "both eyes visible" not in front_neg


def test_all_models_use_base_underwear_and_strip_reference_clothes():
    # Every model, synthetic or reference, is shot in the base underwear set; the
    # reference selfie's clothes (cardigan, tank top, ...) must be negated.
    ref = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )
    desc = workflows.build_describe_graph(
        identity_string="a synthetic person", angle="front", seed=1, count=1,
    )
    assert "only a plain neutral underwear set and nothing else" in ref["5"]["inputs"]["prompt"]
    assert "only a plain neutral underwear set and nothing else" in desc["5"]["inputs"]["text"]
    assert "cardigan" in ref["6"]["inputs"]["prompt"]
    assert "cardigan" in desc["6"]["inputs"]["text"]


def test_build_graphs_center_and_fill_the_frame():
    # Subject was landing small and off in a corner; every angle must pin the
    # subject centred and filling the frame, in both describe and reference modes.
    for angle in ["front", "34", "profile", "body"]:
        ref = workflows.build_reference_graph(
            ref_image_path="r.png", angle=angle, seed=1, count=1,
        )
        desc = workflows.build_describe_graph(
            identity_string="a synthetic person", angle=angle, seed=1, count=1,
        )
        assert "filling the frame" in ref["5"]["inputs"]["prompt"]
        assert "filling the frame" in desc["5"]["inputs"]["text"]


def test_reference_graph_uses_fixed_square_canvas():
    # The whole point of matching the describe-mode (jess/steven) view: output
    # framing must come from a fixed square canvas, NOT the reference photo's
    # aspect. node 7 is EmptySD3LatentImage at 1024x1024 on every angle.
    for angle in ["front", "34", "profile", "body"]:
        graph = workflows.build_reference_graph(
            ref_image_path="r.png", angle=angle, seed=1, count=1,
        )
        assert graph["7"]["class_type"] == "EmptySD3LatentImage"
        assert graph["7"]["inputs"]["width"] == 1024
        assert graph["7"]["inputs"]["height"] == 1024


def test_reference_graph_still_encodes_reference_for_identity():
    # Canvas is empty, but identity must still flow from the reference image via
    # the positive TextEncodeQwenImageEditPlus image1 input (node 5), which
    # VAE-encodes it into reference_latents.
    graph = workflows.build_reference_graph(
        ref_image_path="ref.png", angle="body", seed=1, count=1,
    )
    assert graph["2"]["inputs"]["image"] == "ref.png"
    assert graph["5"]["inputs"]["image1"] == ["2", 0]


def test_reference_negative_prompt_rejects_identity_drift():
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=1, count=1,
    )
    assert "different person" in graph["6"]["inputs"]["prompt"].lower()


def test_qwen_sheet_edit_json_exists_and_has_expected_nodes():
    data = json.loads((WORKFLOWS_DIR / "qwen-sheet-edit.json").read_text())
    for node_id in ["2", "5", "6", "7", "8", "11", "12", "13"]:
        assert node_id in data


def test_qwen_sheet_edit_uses_2511_and_plus_encoder():
    # The reference sheet must run on Qwen-Image-Edit-2511 with the Plus encoder
    # (reference_latents identity lock) — the original edit model drifted the face.
    data = json.loads((WORKFLOWS_DIR / "qwen-sheet-edit.json").read_text())
    assert "2511" in data["1"]["inputs"]["unet_name"]
    assert data["5"]["class_type"] == "TextEncodeQwenImageEditPlus"


def test_qwen_sheet_edit_has_facedetailer_refine_pass():
    # A FaceDetailer pass (bbox detector -> low-denoise face re-render) sharpens
    # the likeness; SaveImage must consume its output, not the raw VAEDecode.
    data = json.loads((WORKFLOWS_DIR / "qwen-sheet-edit.json").read_text())
    assert data["13"]["class_type"] == "FaceDetailer"
    assert data["13"]["inputs"]["denoise"] < 0.5
    assert data["11"]["inputs"]["images"] == ["13", 0]


def test_reference_graph_syncs_facedetailer_seed():
    graph = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=777, count=1,
    )
    assert graph["13"]["inputs"]["seed"] == 777
    assert graph["8"]["inputs"]["seed"] == 777


def test_reference_graph_injects_extra_modifier():
    base = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )["5"]["inputs"]["prompt"]
    withx = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
        extra="warm side lighting, close head-and-shoulders framing",
    )["5"]["inputs"]["prompt"]
    assert "warm side lighting, close head-and-shoulders framing" in withx
    assert withx != base


def test_reference_graph_empty_extra_is_unchanged():
    base = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=7, count=2,
    )["5"]["inputs"]["prompt"]
    same = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=7, count=2, extra="",
    )["5"]["inputs"]["prompt"]
    assert base == same
