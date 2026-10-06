"""Levenshtein Shift-And (positive-bit Bitap).

Each bit i means a prefix of length i is reachable with <= e edits.
A streaming pass locates ends. A reversed, anchored pass recovers ALL starts,
not just the shortest/best match at each end. Empty substrings are excluded.
Python big integers support patterns longer than a machine word.

For n text characters, m pattern characters, budget k and H matching ends:
O(n*k + H*(m+k)*k) big-integer operations plus result sorting. Integer
operations themselves scale with pattern length. Large budgets can produce
quadratically many results; production domain policies cap them to 1 or 2.
"""

from entity_marker.domain.models.matches import ApproximateMatch
from entity_marker.domain.models.text import TextSpan
from entity_marker.infrastructure.matching.exact import ExactMatcher


def _masks(pattern: str) -> dict[str, int]:
    masks: dict[str, int] = {}
    for i, char in enumerate(pattern):
        masks[char] = masks.get(char, 0) | (1 << i)
    return masks


def _initial(length: int, budget: int) -> list[int]:
    return [(1 << (min(e, length) + 1)) - 1 for e in range(budget + 1)]


def _step(old: list[int], mask: int, limit: int, restart: bool) -> list[int]:
    new = [(((old[0] & mask) << 1) | int(restart)) & limit]
    for e in range(1, len(old)):
        new.append(
            (
                ((old[e] & mask) << 1)  # equal character
                | (old[e - 1] << 1)  # substitution
                | old[e - 1]  # insertion into the pattern
                | (new[e - 1] << 1)  # deletion from the pattern
                | int(restart)
            )
            & limit
        )
    return new


class BitapMatcher:
    def find(self, text: str, pattern: str, max_distance: int) -> list[ApproximateMatch]:
        if max_distance < 0:
            raise ValueError("Maximum distance must be nonnegative")
        if not pattern:
            raise ValueError("Search pattern must not be empty")
        if max_distance == 0:
            return [ApproximateMatch(span, 0) for span in ExactMatcher().find(text, pattern)]
        if not text:
            return []
        m = len(pattern)
        k = min(max_distance, max(m, len(text)))
        masks, reverse_masks = _masks(pattern), _masks(pattern[::-1])
        limit, accept = (1 << (m + 1)) - 1, 1 << m
        state = _initial(m, k)
        matches: list[ApproximateMatch] = []
        for end, char in enumerate(text, start=1):
            state = _step(state, masks.get(char, 0), limit, restart=True)
            if not state[k] & accept:
                continue
            backwards = _initial(m, k)
            for start in range(end - 1, max(-1, end - m - k - 1), -1):
                backwards = _step(
                    backwards, reverse_masks.get(text[start], 0), limit, restart=False
                )
                if backwards[k] & accept:
                    distance = next(e for e, bits in enumerate(backwards) if bits & accept)
                    matches.append(ApproximateMatch(TextSpan(start, end), distance))
        return sorted(matches, key=lambda match: (match.span.start, match.span.end))
