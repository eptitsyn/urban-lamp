from dataclasses import dataclass
from types import MappingProxyType

from entity_marker.domain.models.entities import EntityType
from entity_marker.domain.models.matches import EntityAlias


@dataclass(frozen=True)
class MatchingConfig:
    fuzzy_enabled: bool = True
    max_errors: int = 1
    min_fuzzy_pattern_length: int = 4
    acceptance_threshold: float = 0.60
    ambiguity_margin: float = 0.08
    evidence_bonus: float = 0.25
    evidence_window: int = 80
    max_separator_gap: int = 4
    field_weights: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if self.max_errors < 0:
            raise ValueError("Maximum errors must be nonnegative")
        if self.min_fuzzy_pattern_length < 1:
            raise ValueError("Minimum fuzzy length must be positive")
        if self.evidence_window < 0 or self.max_separator_gap < 0:
            raise ValueError("Window and gap limits must be nonnegative")
        if len(dict(self.field_weights)) != len(self.field_weights):
            raise ValueError("Duplicate field weight override")
        for field, weight in self.field_weights:
            if field not in FIELD_WEIGHTS or not 0 <= weight <= 1:
                raise ValueError("Invalid field weight override")
        for value in (self.acceptance_threshold, self.ambiguity_margin, self.evidence_bonus):
            if not 0 <= value <= 1:
                raise ValueError("Scoring parameters must be between zero and one")


# Discriminative weights are heuristic, not probabilities.
FIELD_WEIGHTS = MappingProxyType(
    {
        "vin": 1.0,
        "license_plate": 0.95,
        "body_number": 0.95,
        "chassis_number": 0.95,
        "full_name": 0.95,
        "last_name": 0.65,
        # Components can support one another while isolated given names stay weak.
        "first_name": 0.50,
        "middle_name": 0.50,
        "birth_date": 0.70,
        "issue_date": 0.60,
        "series_number": 0.98,
        "number": 0.90,
        "series": 0.40,
        "previous_last_name": 0.65,
        "previous_full_name": 0.95,
        "document_type": 0.40,
        "inn": 1.0,
        "name": 0.90,
        "position": 0.45,
        "organization_name": 0.90,
        "return_address": 0.85,
        "email": 0.95,
        "incoming_letter_number": 0.90,
        "case_number": 0.90,
        "incoming_letter_date": 0.65,
        "preliminary_response_due_date": 0.65,
        "reply_email": 0.95,
        "reply_address": 0.85,
    }
)


class PersonMatchingPolicy:
    def allowed_distance(self, field_name: str, value: str) -> int:
        if field_name == "birth_date":
            return int(len(value) >= 8)
        if len(value) < 4:
            return 0
        return (
            2
            if field_name in ("full_name", "last_name", "previous_full_name", "previous_last_name")
            and len(value) >= 10
            else 1
        )


class CarMatchingPolicy:
    def allowed_distance(self, field_name: str, value: str) -> int:
        return int(len(value) >= 4)


class DocumentMatchingPolicy:
    def allowed_distance(self, field_name: str, value: str) -> int:
        return int(field_name in ("number", "series_number") and len(value) >= 6)


def allowed_distance(alias: EntityAlias, normalized: str, config: MatchingConfig) -> int:
    # Initials are weak identity signals: never repair a wrong initial by fuzzy matching.
    if alias.field_name in ("full_name", "previous_full_name") and "." in alias.value:
        return 0
    if not config.fuzzy_enabled or len(normalized) < config.min_fuzzy_pattern_length:
        return 0
    # Contacts, tax IDs, correspondence dates and letter numbers stay exact/normalized.
    if alias.field_name in (
        "inn",
        "email",
        "reply_email",
        "incoming_letter_date",
        "preliminary_response_due_date",
        "incoming_letter_number",
        "return_address",
        "reply_address",
    ):
        return 0
    match alias.entity_type:
        case EntityType.PERSON:
            policy_distance = PersonMatchingPolicy().allowed_distance(alias.field_name, normalized)
        case EntityType.CAR:
            policy_distance = CarMatchingPolicy().allowed_distance(alias.field_name, normalized)
        case EntityType.DOCUMENT:
            policy_distance = DocumentMatchingPolicy().allowed_distance(
                alias.field_name, normalized
            )
        case EntityType.LEGAL_ENTITY:
            policy_distance = int(alias.field_name == "name" and len(normalized) >= 6)
        case EntityType.SENDER:
            if alias.field_name == "full_name":
                policy_distance = PersonMatchingPolicy().allowed_distance("full_name", normalized)
            else:
                policy_distance = int(
                    alias.field_name in ("organization_name", "position") and len(normalized) >= 6
                )
        case EntityType.MISC:
            policy_distance = int(alias.field_name == "case_number" and len(normalized) >= 6)
    return min(config.max_errors, policy_distance)
