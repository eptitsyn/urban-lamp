from entity_marker.domain.models.entities import EntityType
from entity_marker.domain.models.matches import (
    MatchEvidence,
    MatchMethod,
    MatchScore,
    ObjectOccurrence,
)
from entity_marker.domain.models.text import TextSpan
from entity_marker.domain.services.overlap_resolver import OverlapResolver


def occurrence(
    start: int, end: int, score: float, method: MatchMethod, identity: str = "c"
) -> ObjectOccurrence:
    return ObjectOccurrence(
        identity,
        EntityType.CAR,
        "vin",
        TextSpan(start, end),
        "x" * (end - start),
        "value",
        MatchScore(score),
        method,
        int(method == MatchMethod.BITAP),
        MatchEvidence((), MatchScore(score)),
    )


def test_exact_beats_higher_scoring_fuzzy() -> None:
    exact = occurrence(0, 4, 0.7, MatchMethod.EXACT)
    fuzzy = occurrence(0, 5, 0.9, MatchMethod.BITAP)
    kept, rejected = OverlapResolver().resolve([fuzzy, exact])
    assert kept == (exact,)
    assert rejected == (fuzzy,)


def test_partial_overlaps_and_adjacent_regions() -> None:
    left = occurrence(0, 4, 0.9, MatchMethod.EXACT)
    right = occurrence(3, 8, 0.8, MatchMethod.EXACT)
    adjacent = occurrence(4, 8, 0.7, MatchMethod.EXACT)
    kept, _ = OverlapResolver().resolve([right, adjacent, left])
    assert kept == (left, adjacent)


def test_contained_tie_prefers_longer_span() -> None:
    short = occurrence(2, 4, 0.9, MatchMethod.EXACT)
    long = occurrence(0, 8, 0.9, MatchMethod.EXACT)
    assert OverlapResolver().resolve([short, long])[0] == (long,)
