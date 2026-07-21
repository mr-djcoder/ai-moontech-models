from app.schema import Release

_ADULT_BANDS_REJECT_KEYWORDS = ["teen", "minor", "child", "kid"]

REALISM_NEGATIVE_PROMPT = (
    "glossy render, plastic skin, airbrushed, studio-perfect lighting, "
    "CGI look, waxy skin, overly smooth, beauty-filter, artificial symmetry, "
    "wig, doll hair, mannequin hair, helmet hair, perfectly styled hair, "
    "smooth flawless skin, poreless, uncanny valley, 3d render, cartoon, "
    "deepfake sheen, over-sharpened, oversaturated"
)

ANGLE_PHRASES = {
    "front": "front-facing",
    "34": "three-quarter turn",
    "profile": "full profile",
    "body": "full-body standing",
}


def is_adult(age_band: str) -> bool:
    band = age_band.strip().lower()
    if not band:
        return False
    if any(kw in band for kw in _ADULT_BANDS_REJECT_KEYWORDS):
        return False
    if band.isdigit() and int(band) < 18:
        return False
    return True


def check_save(
    provenance: str,
    release: Release | None,
    is_real_person_reference: bool,
    is_celebrity_or_public_figure: bool,
    age_band: str,
) -> tuple[bool, str | None]:
    if not is_adult(age_band):
        return False, "age_band does not resolve to an adult; refused."
    if is_celebrity_or_public_figure:
        return False, "celebrities and public figures are refused outright, release or not."
    if is_real_person_reference or provenance == "likeness-consented":
        if release is None or not release.consent:
            return False, "real-person reference requires an attached, consenting release record."
    return True, None
