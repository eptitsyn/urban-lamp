import pytest

from entity_marker.domain.models.matches import NormalizationProfile as Profile
from entity_marker.domain.models.text import TextSpan
from entity_marker.infrastructure.normalization.text import MappedNormalizer


@pytest.mark.parametrize(
    "original,profile,normalized",
    [
        ("А123ВС77", Profile.PLATE, "A123BC77"),
        ("А 123 ВС 77", Profile.PLATE, "A123BC77"),
        ("А-123-ВС-77", Profile.PLATE, "A123BC77"),
        ("45 01 № 123456", Profile.IDENTIFIER, "4501123456"),
        ("20.01 1 1973", Profile.DATE, "20.0111973"),
        ("СЕМЁН", Profile.NAME, "семен"),
        ("СЕМЕ\u0308Н", Profile.NAME, "семен"),
        ("Straße", Profile.NAME, "strasse"),
        ("ﬃ", Profile.NAME, "ffi"),
        ("\u1100\u1161", Profile.NAME, "가"),
    ],
)
def test_round_trip(original: str, profile: Profile, normalized: str) -> None:
    mapped = MappedNormalizer().normalize(original, profile)
    assert mapped.normalized == normalized
    span = mapped.to_original_span(TextSpan(0, len(normalized)))
    assert original[span.start : span.end] == original


def test_expanded_character_boundary() -> None:
    mapped = MappedNormalizer().normalize("ß", Profile.NAME)
    assert not mapped.has_complete_boundaries(TextSpan(0, 1))
    assert mapped.has_complete_boundaries(TextSpan(0, 2))


def test_local_span_with_emoji_and_crlf() -> None:
    original = "😀\r\nавто А 123 ВС 77!"
    mapped = MappedNormalizer().normalize(original, Profile.PLATE)
    start = mapped.normalized.index("A123BC77")
    span = mapped.to_original_span(TextSpan(start, start + 8))
    assert original[span.start : span.end] == "А 123 ВС 77"
    assert span.start == original.index("А 123")


def test_profiles_are_distinct() -> None:
    normalizer = MappedNormalizer()
    assert normalizer.normalize("А", Profile.NAME).normalized == "а"
    assert normalizer.normalize("А", Profile.PLATE).normalized == "A"
    assert normalizer.normalize("12\n34", Profile.IDENTIFIER).normalized == "12\n34"
