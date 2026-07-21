from app.schema import Release
from app import safety


def test_is_adult_accepts_adult_bands():
    for band in ["early 20s", "late 20s", "30s", "40s", "50s"]:
        assert safety.is_adult(band) is True


def test_is_adult_rejects_minor_bands():
    for band in ["teen", "16", "child", "minor", ""]:
        assert safety.is_adult(band) is False


def test_check_save_rejects_minor():
    ok, reason = safety.check_save(
        provenance="synthetic", release=None,
        is_real_person_reference=False, is_celebrity_or_public_figure=False,
        age_band="teen",
    )
    assert ok is False
    assert "adult" in reason.lower()


def test_check_save_allows_synthetic_no_release():
    ok, reason = safety.check_save(
        provenance="synthetic", release=None,
        is_real_person_reference=False, is_celebrity_or_public_figure=False,
        age_band="30s",
    )
    assert ok is True
    assert reason is None


def test_check_save_rejects_real_person_without_release():
    ok, reason = safety.check_save(
        provenance="likeness-consented", release=None,
        is_real_person_reference=True, is_celebrity_or_public_figure=False,
        age_band="30s",
    )
    assert ok is False
    assert "release" in reason.lower()


def test_check_save_allows_real_person_with_release():
    release = Release(subject="Jane Doe", date="2026-07-21", consent=True,
                       statement="AI-likeness use granted", file="release/signed.pdf")
    ok, reason = safety.check_save(
        provenance="likeness-consented", release=release,
        is_real_person_reference=True, is_celebrity_or_public_figure=False,
        age_band="30s",
    )
    assert ok is True


def test_check_save_rejects_celebrity_even_with_release():
    release = Release(subject="Famous Person", date="2026-07-21", consent=True,
                       statement="stmt", file="release/signed.pdf")
    ok, reason = safety.check_save(
        provenance="likeness-consented", release=release,
        is_real_person_reference=True, is_celebrity_or_public_figure=True,
        age_band="30s",
    )
    assert ok is False
    assert "celebrit" in reason.lower() or "public figure" in reason.lower()


def test_realism_negative_prompt_mentions_glossy():
    assert "glossy" in safety.REALISM_NEGATIVE_PROMPT.lower()


def test_angle_phrases_has_four_angles():
    assert set(safety.ANGLE_PHRASES.keys()) == {"front", "34", "profile", "body"}
