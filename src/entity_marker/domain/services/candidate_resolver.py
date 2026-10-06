import logging
from collections import defaultdict

from entity_marker.domain.models.entities import EntityType
from entity_marker.domain.models.matches import (
    MatchCandidate,
    MatchEvidence,
    MatchMethod,
    MatchScore,
    ObjectOccurrence,
    ResolutionDecision,
)
from entity_marker.domain.models.text import SourceText, TextSpan
from entity_marker.domain.policies.matching import MatchingConfig

logger = logging.getLogger(__name__)
METHOD_PRIORITY = {MatchMethod.EXACT: 0, MatchMethod.NORMALIZED: 1, MatchMethod.BITAP: 2}


def candidate_rank(candidate: MatchCandidate) -> tuple[int, float, int, int, str]:
    return (
        METHOD_PRIORITY[candidate.method],
        -candidate.score.value,
        candidate.edit_distance,
        -(candidate.span.end - candidate.span.start),
        candidate.alias.value,
    )


def _local(
    first: MatchCandidate, second: MatchCandidate, source: SourceText, config: MatchingConfig
) -> bool:
    if first.span == second.span or first.alias.field_name == second.alias.field_name:
        return False
    # Overlapping aliases are alternative explanations, not independent evidence.
    if first.span.start < second.span.end and second.span.start < first.span.end:
        return False
    left, right = sorted((first.span, second.span))
    gap = source.text[left.end : right.start]
    return len(gap) <= config.evidence_window and not any(char in gap for char in ".!?;\n\r")


class CandidateResolver:
    def __init__(self, config: MatchingConfig) -> None:
        self.config = config

    def resolve(
        self, candidates: tuple[MatchCandidate, ...], source: SourceText
    ) -> tuple[list[ObjectOccurrence], list[ResolutionDecision]]:
        unique: dict[tuple[EntityType, str, str, TextSpan], MatchCandidate] = {}
        rejected: list[ResolutionDecision] = []
        for candidate in sorted(candidates, key=candidate_rank):
            alias = candidate.alias
            key = (alias.entity_type, alias.entity_id, alias.field_name, candidate.span)
            if key in unique:
                rejected.append(ResolutionDecision(candidate, "duplicate alias or method"))
            else:
                unique[key] = candidate
        by_entity: dict[tuple[EntityType, str], list[MatchCandidate]] = defaultdict(list)
        for candidate in unique.values():
            by_entity[(candidate.alias.entity_type, candidate.alias.entity_id)].append(candidate)
        evidence: dict[MatchCandidate, MatchEvidence] = {}
        for candidate in unique.values():
            neighbors = [
                other
                for other in by_entity[(candidate.alias.entity_type, candidate.alias.entity_id)]
                if _local(candidate, other, source, self.config)
            ]
            # One strongest observation per field avoids counting repeated aliases.
            fields: dict[str, MatchCandidate] = {}
            for other in sorted(neighbors, key=candidate_rank):
                fields.setdefault(other.alias.field_name, other)
            support = tuple(fields.values())
            bonus = self.config.evidence_bonus * max((c.score.value for c in support), default=0)
            # A partial composite must not outrank its complete alias by borrowing
            # the very component that completes it as independent evidence.
            if candidate.alias.field_name in ("full_name", "previous_full_name", "series_number"):
                bonus = 0
            evidence[candidate] = MatchEvidence(
                support, MatchScore(min(1, candidate.score.value + bonus))
            )
        groups: dict[tuple[EntityType, TextSpan], list[MatchCandidate]] = defaultdict(list)
        for candidate in unique.values():
            groups[(candidate.alias.entity_type, candidate.span)].append(candidate)
        accepted: list[ObjectOccurrence] = []
        for group in groups.values():
            for candidate in group:
                item = evidence[candidate]
                rivals = [
                    other for other in group if other.alias.entity_id != candidate.alias.entity_id
                ]
                rival_score = max((evidence[r].score.value for r in rivals), default=-1)
                if rival_score >= item.score.value - self.config.ambiguity_margin:
                    reason = "ambiguous entity identity"
                elif item.score.value < self.config.acceptance_threshold:
                    reason = "insufficient local evidence"
                else:
                    alias = candidate.alias
                    accepted.append(
                        ObjectOccurrence(
                            alias.entity_id,
                            alias.entity_type,
                            alias.field_name,
                            candidate.span,
                            candidate.matched_text,
                            alias.value,
                            item.score,
                            candidate.method,
                            candidate.edit_distance,
                            item,
                        )
                    )
                    continue
                logger.debug("Rejected %s: %s", candidate, reason)
                rejected.append(ResolutionDecision(candidate, reason))
        return accepted, rejected
