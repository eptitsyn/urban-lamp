from typing import Protocol

from entity_marker.domain.models.matches import NormalizationProfile
from entity_marker.domain.models.text import NormalizedText


class TextNormalizer(Protocol):
    def normalize(self, text: str, profile: NormalizationProfile) -> NormalizedText: ...
