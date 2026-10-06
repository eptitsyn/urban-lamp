from dataclasses import replace

import pytest

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


@pytest.mark.parametrize("field", ["first_name", "last_name", "middle_name", "previous_last_name"])
@pytest.mark.parametrize("person_score", [0.7, 1.0])
def test_person_components_and_sender_full_name_coexist(field: str, person_score: float) -> None:
    person = replace(
        occurrence(2, 8, person_score, MatchMethod.EXACT),
        entity_type=EntityType.PERSON,
        field_name=field,
    )
    sender = replace(
        occurrence(0, 20, 0.95, MatchMethod.EXACT),
        entity_type=EntityType.SENDER,
        field_name="full_name",
    )
    kept, rejected = OverlapResolver().resolve([person, sender])
    assert kept == (sender, person)
    assert not rejected


def test_partial_person_sender_overlap_still_conflicts() -> None:
    person = replace(
        occurrence(0, 8, 0.7, MatchMethod.EXACT),
        entity_type=EntityType.PERSON,
        field_name="last_name",
    )
    sender = replace(
        occurrence(2, 20, 0.95, MatchMethod.EXACT),
        entity_type=EntityType.SENDER,
        field_name="full_name",
    )
    assert OverlapResolver().resolve([person, sender]) == ((sender,), (person,))
