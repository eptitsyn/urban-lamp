from entity_marker.domain.models.text import TextSpan


class ExactMatcher:
    """Find all literal occurrences, including overlapping ones."""

    def find(self, text: str, pattern: str) -> list[TextSpan]:
        if not pattern:
            raise ValueError("Search pattern must not be empty")
        spans: list[TextSpan] = []
        offset = 0
        while (start := text.find(pattern, offset)) != -1:
            spans.append(TextSpan(start, start + len(pattern)))
            offset = start + 1
        return spans
