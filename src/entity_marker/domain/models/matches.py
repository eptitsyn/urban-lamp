from dataclasses import dataclass
from enum import StrEnum

from entity_marker.domain.models.entities import EntityType
from entity_marker.domain.models.text import TextSpan


class MatchMethod(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    BITAP = "bitap"


class NormalizationProfile(StrEnum):
    NAME = "name"
    VIN = "vin"
    PLATE = "plate"
    IDENTIFIER = "identifier"
    DATE = "date"
    TEXT = "text"
    EMAIL = "email"
    TAX_ID = "tax_id"
    REFERENCE = "reference"


@dataclass(frozen=True)
class MatchScore:
    value: float

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 1:
            raise ValueError("Match score must be between zero and one")


@dataclass(frozen=True)
class EntityAlias:
    entity_id: str
    entity_type: EntityType
    field_name: str
    value: str
    weight: float
    profile: NormalizationProfile


@dataclass(frozen=True)
class ApproximateMatch:
    span: TextSpan
    distance: int


@dataclass(frozen=True)
class MatchCandidate:
    alias: EntityAlias
    span: TextSpan
    matched_text: str
    score: MatchScore
    method: MatchMethod
    edit_distance: int = 0


@dataclass(frozen=True)
class MatchEvidence:
    supporting_matches: tuple[MatchCandidate, ...]
    score: MatchScore


@dataclass(frozen=True)
class ObjectOccurrence:
    entity_id: str
    entity_type: EntityType
    field_name: str
    span: TextSpan
    matched_text: str
    source_value: str
    score: MatchScore
    method: MatchMethod
    edit_distance: int
    evidence: MatchEvidence


@dataclass(frozen=True)
class ResolutionDecision:
    candidate: MatchCandidate
    reason: str


@dataclass(frozen=True)
class MarkingResult:
    occurrences: tuple[ObjectOccurrence, ...]
    rejected: tuple[ResolutionDecision, ...]
