from typing import Protocol

from entity_marker.domain.models.matches import ApproximateMatch
from entity_marker.domain.models.text import TextSpan


class ExactTextMatcher(Protocol):
    def find(self, text: str, pattern: str) -> list[TextSpan]: ...


class ApproximateTextMatcher(Protocol):
    def find(self, text: str, pattern: str, max_distance: int) -> list[ApproximateMatch]: ...
