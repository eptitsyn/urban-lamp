from itertools import product

import pytest

from entity_marker.infrastructure.matching.bitap import BitapMatcher
from entity_marker.infrastructure.matching.exact import ExactMatcher


def levenshtein(left: str, right: str) -> int:
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        following = [i]
        for j, b in enumerate(right, 1):
            following.append(min(row[j] + 1, following[-1] + 1, row[j - 1] + (a != b)))
        row = following
    return row[-1]


def test_exhaustive_reference() -> None:
    """Compare every span, not only the best match at each ending position."""
    words = ["".join(chars) for size in range(5) for chars in product("ab", repeat=size)]
    matcher = BitapMatcher()
    for text in words:
        for pattern in words[1:]:
            for budget in range(4):
                expected = {}
                for start in range(len(text)):
                    for end in range(start + 1, len(text) + 1):
                        distance = levenshtein(pattern, text[start:end])
                        if distance <= budget:
                            expected[(start, end)] = distance
                found = matcher.find(text, pattern, budget)
                actual = {(m.span.start, m.span.end): m.distance for m in found}
                assert len(actual) == len(found)
                assert actual == expected, (text, pattern, budget)


@pytest.mark.parametrize(
    "text,pattern,distance",
    [
        ("X7LHSR0VN12345678", "X7LHSRDVN12345678", 1),
        ("X7LHSRXDVN12345678", "X7LHSRDVN12345678", 1),
        ("X7LHSRVN12345678", "X7LHSRDVN12345678", 1),
        ("Птцын", "Птицын", 1),
        ("😀abc", "😀axc", 1),
        ("a" * 130 + "c", "a" * 130 + "b", 1),
    ],
)
def test_edit_operations_and_long_patterns(text: str, pattern: str, distance: int) -> None:
    found = BitapMatcher().find(text, pattern, distance)
    assert any(
        m.span.start == 0 and m.span.end == len(text) and m.distance == distance for m in found
    )


@pytest.mark.parametrize("text,pattern", [("абаба", "аба"), ("aaaa", "aa"), ("", "a")])
def test_zero_is_exact(text: str, pattern: str) -> None:
    assert [m.span for m in BitapMatcher().find(text, pattern, 0)] == ExactMatcher().find(
        text, pattern
    )


def test_no_match_and_input_contract() -> None:
    matcher = BitapMatcher()
    assert matcher.find("zzzz", "abcd", 1) == []
    assert matcher.find("", "abc", 1) == []
    with pytest.raises(ValueError):
        matcher.find("abc", "", 1)
    with pytest.raises(ValueError):
        matcher.find("abc", "abc", -1)


def test_budget_larger_than_pattern() -> None:
    found = BitapMatcher().find("abc", "a", 100)
    assert len(found) == 6  # All nonempty substrings, unique and correctly scored.
    assert all(m.distance == levenshtein("a", "abc"[m.span.start : m.span.end]) for m in found)
