import copy
import json

from app.config import WORKFLOWS_DIR
from app.safety import REALISM_NEGATIVE_PROMPT, ANGLE_PHRASES

_DESCRIBE_TEMPLATE = json.loads((WORKFLOWS_DIR / "qwen-sheet-describe.json").read_text())
_REFERENCE_TEMPLATE = json.loads((WORKFLOWS_DIR / "qwen-sheet-edit.json").read_text())

# Without a framing directive the model drops the subject small and off-centre
# (verified: reference-mode front/34 came back tiny in an odd corner because the
# canvas inherited the off-centre selfie). The fixed square canvas below does the
# heavy lifting; this clause just reinforces the centred, frame-filling look that
# the synthetic (describe-mode) sheets already have. Same directive on every
# angle — the angle phrase alone widens the crop for the body shot.
_ANGLE_FRAMING = "subject centered and filling the frame, no empty space around the subject"

# Every model — synthetic or from a reference photo — is shot in the SAME base
# wardrobe: a plain underwear set, never the clothes from the reference selfie.
# So the wardrobe is stated as a hard override ("only ... and nothing else") and
# the common source garments are pushed into the negative to strip them.
_WARDROBE = "wearing only a plain neutral underwear set and nothing else"
_WARDROBE_NEGATIVE = (
    "cardigan, sweater, tank top, camisole, jacket, coat, shirt, blouse, dress, "
    "outerwear, layered clothing, street clothes, fully clothed"
)

# ---------------------------------------------------------------------------
# Shared prompt vocabulary — BOTH describe (synthetic) and reference (photo)
# sheets use the same house style, poses, framing and negatives so a model looks
# the same however it was made. Reference mode adds a few clauses on top (identity
# lock, real-body base, selfie/angle correction); see build_reference_graph.
# ---------------------------------------------------------------------------
_PORTRAIT_BASE = (
    "professional studio model portrait, deliberately posed, "
    "neutral relaxed expression, both arms relaxed at the sides"
)
# House lighting/quality tail. Studio lighting on both pipelines (was split
# studio vs "flat available light"); the negative still bans studio-perfect
# retouching so it stays realistic, not glossy.
_QUALITY_TAIL = (
    "plain seamless background, studio lighting, candid realism, "
    "visible pores, ordinary face"
)
# Per-angle posing. Front is squared to the lens but NOT called "symmetrical"
# (that fights the natural-asymmetry realism negatives). Profile is forced to a
# true side view — the edit model fights it hardest. Body shows head-to-feet.
_ANGLE_POSE = {
    "front": "looking straight into the lens, chin level and eyeline to the lens, "
             "head upright with no tilt, shoulders and hips squared to the camera",
    "34": "body angled to a three-quarter view with the front shoulder toward the "
          "camera, face turned back toward the lens",
    "profile": "a true 90-degree side profile, head turned fully to the side so the "
               "nose points to the edge of the frame, only one eye and one ear "
               "visible, face in a clean silhouette",
    "body": "standing upright and facing the camera, full body from head to feet "
            "with both feet visible and flat on the floor, weight evenly on both "
            "legs, tall relaxed posture",
}
# Per-angle negatives. Profile is the one the model keeps fighting (drifts back to
# a frontal grin), so it needs the front view explicitly banned.
_ANGLE_POSE_NEGATIVE = {
    "profile": "front view, three-quarter view, facing the camera, both eyes visible",
}
# Qwen full-body renders mangle hands/feet and crop extremities; guard against it.
_ANATOMY_NEGATIVE = (
    "deformed hands, extra fingers, missing fingers, fused fingers, malformed feet, "
    "extra limbs, cropped feet, cropped head"
)
# Kill any odd framing/tilt so the output angle comes from the sheet, not the
# source photo's random tilt. Applies to both modes (harmless for synthetic).
_ANGLE_NEGATIVE = (
    "tilted camera, dutch angle, crooked horizon, awkward camera angle, "
    "skewed perspective, looking up at the subject, looking down at the subject"
)


def _base_negative(angle: str) -> str:
    """Negative prompt shared by both pipelines, plus any per-angle addition."""
    neg = (
        f"{REALISM_NEGATIVE_PROMPT}, {_ANGLE_NEGATIVE}, "
        f"{_ANATOMY_NEGATIVE}, {_WARDROBE_NEGATIVE}"
    )
    extra = _ANGLE_POSE_NEGATIVE.get(angle)
    return f"{neg}, {extra}" if extra else neg


def build_describe_graph(identity_string: str, angle: str, seed: int, count: int) -> dict:
    graph = copy.deepcopy(_DESCRIBE_TEMPLATE)
    phrase = ANGLE_PHRASES[angle]
    graph["5"]["inputs"]["text"] = (
        f"{identity_string}, {phrase}, {_ANGLE_POSE[angle]}, "
        f"{_PORTRAIT_BASE}, {_ANGLE_FRAMING}, {_WARDROBE}, {_QUALITY_TAIL}"
    )
    graph["6"]["inputs"]["text"] = _base_negative(angle)
    graph["8"]["inputs"]["seed"] = seed
    graph["7"]["inputs"]["batch_size"] = count
    graph["11"]["inputs"]["filename_prefix"] = f"sheet_{angle}"
    return graph


# Identity is preserved by Qwen-Image-Edit-2511's TextEncodeQwenImageEditPlus
# conditioning (node 5): it VL-encodes the reference AND VAE-encodes it into
# `reference_latents` appended to the conditioning — a far stronger identity lock
# than the original edit model, and purpose-built for multi-angle views from one
# reference. A FaceDetailer pass (nodes 12/13) then crops the face and re-renders
# it at low denoise to sharpen the likeness without changing identity. The KSampler
# still paints onto a fixed empty square canvas (node 7, EmptySD3LatentImage) rather
# than a latent derived from the reference, so output framing does not inherit the
# reference photo's aspect/off-centre subject — it matches the clean 1024x1024
# describe-mode sheets. With an empty canvas the sampler runs at full denoise.
_REFERENCE_DENOISE = 1.0

# Qwen-Image-Edit holds identity through the reference conditioning; 2511's
# reference_latents make it much stickier, but the further the requested angle is
# from the (roughly frontal) reference the more the likeness can still drift.
# Instruct the edit model to keep the exact face, and on the hard angles (body,
# profile) call out a sharp, clearly-visible face so the sampler spends detail
# there instead of reinventing it.
_IDENTITY_CLAUSE = "keep the exact same face and facial identity as the reference person"
# The body is the reference photo's real physique (real skin, real build — not an
# idealized text-built body). The description only *enhances* it — nudges details
# like thicker thighs — rather than overriding it. So this is a base the
# description refines, and the body-drift negatives are intentionally NOT set
# (they would forbid the very enhancements the description brings).
_BODY_CLAUSE = "start from the reference person's real body and skin"
_FACE_FOCUS_CLAUSE = "face clearly visible and in sharp focus"
# Only the body shot needs the face pulled back into focus (it shrinks in a wide
# full-length frame). Profile is a silhouette — a face-focus clause there just
# fights the "one eye visible" side view, so it is excluded.
_FACE_FOCUS_ANGLES = {"body"}

# Reference-only. The source is usually a casual arm-extended selfie at some
# random angle: head tilted, eyes off to the side, a reaching arm foreshortened.
# Qwen-Image-Edit clings to that source pose, so we tell it to re-frame at the
# sheet's angle and push the selfie cues into the negative. Identity now rides on
# 2511's reference_latents plus a FaceDetailer refine pass (see build_reference_graph)
# rather than a bolt-on face-ID adapter — PuLID/InstantID are SDXL/Flux-native and
# do not apply to Qwen's DiT.
_REFRAME_CLAUSE = (
    "shot as a clean upright studio photograph that ignores the reference photo's "
    "original camera angle and tilt — re-frame it at the specified studio angle"
)
# Gaze terms intentionally excluded so profile/34 can still turn away.
_SELFIE_NEGATIVE = (
    "selfie, arm reaching toward the camera, outstretched arm, foreshortened arm, "
    "holding a phone, phone in hand, tilted head, casual snapshot"
)


def build_reference_graph(
    ref_image_path: str, angle: str, seed: int, count: int,
    identity_string: str | None = None, extra: str = "",
) -> dict:
    """Build a Qwen-Image-Edit reference graph (identity-preserving).

    The reference image is injected as in-context conditioning (node 5/6's
    TextEncodeQwenImageEdit ``image`` input); the model keeps the subject's face
    while being re-posed into a professional front-facing studio portrait. The
    body *starts* from the reference photo (real skin/physique, not a text-built
    body) and the optional ``identity_string`` (the model's written description)
    only *enhances* it — nudging details like thicker thighs — without overriding
    the reference's real build. Output is re-framed to the specified studio angle
    regardless of the reference photo's original camera angle/tilt.
    """
    graph = copy.deepcopy(_REFERENCE_TEMPLATE)
    phrase = ANGLE_PHRASES[angle]
    pose = _ANGLE_POSE[angle]
    desc = identity_string.strip() if identity_string and identity_string.strip() else ""
    refine = f"and the figure is enhanced by this description: {desc}, " if desc else ""
    face_clause = f"{_FACE_FOCUS_CLAUSE}, " if angle in _FACE_FOCUS_ANGLES else ""
    graph["2"]["inputs"]["image"] = ref_image_path
    # Ordered high-signal-first (Qwen weights early tokens more): the shot, then
    # who it is, then house style, then framing/wardrobe/quality.
    extra_clause = f"{extra.strip()}, " if extra and extra.strip() else ""
    graph["5"]["inputs"]["prompt"] = (
        f"{phrase}, {pose}, "
        f"{_IDENTITY_CLAUSE}, {_BODY_CLAUSE}, {refine}{face_clause}"
        f"{_PORTRAIT_BASE}, {_REFRAME_CLAUSE}, {_ANGLE_FRAMING}, "
        f"{extra_clause}"
        f"{_WARDROBE}, {_QUALITY_TAIL}"
    )
    # Reference adds the selfie negative on top of the shared base.
    graph["6"]["inputs"]["prompt"] = f"{_base_negative(angle)}, {_SELFIE_NEGATIVE}"
    graph["8"]["inputs"]["seed"] = seed
    graph["8"]["inputs"]["denoise"] = _REFERENCE_DENOISE
    # FaceDetailer (node 13) reuses the same conditioning to refine the face at low
    # denoise; keep its seed in step with the main sampler for reproducible sheets.
    graph["13"]["inputs"]["seed"] = seed
    graph["7"]["inputs"]["batch_size"] = count
    graph["11"]["inputs"]["filename_prefix"] = f"sheet_ref_{angle}"
    return graph
