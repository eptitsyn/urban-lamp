from entity_marker.application.mark_occurrences import MarkOccurrencesHandler
from entity_marker.domain.aliases.generators import PersonAliasGenerator
from entity_marker.domain.policies.matching import MatchingConfig
from entity_marker.domain.services.candidate_generator import CandidateGenerator
from entity_marker.domain.services.candidate_resolver import CandidateResolver
from entity_marker.domain.services.marking import OccurrenceMarker
from entity_marker.domain.services.overlap_resolver import OverlapResolver
from entity_marker.infrastructure.matching.bitap import BitapMatcher
from entity_marker.infrastructure.matching.exact import ExactMatcher
from entity_marker.infrastructure.morphology.russian import RussianPersonInflector
from entity_marker.infrastructure.normalization.text import MappedNormalizer


def build_handler(config: MatchingConfig | None = None) -> MarkOccurrencesHandler:
    config = config or MatchingConfig()
    return MarkOccurrencesHandler(
        OccurrenceMarker(
            CandidateGenerator(ExactMatcher(), BitapMatcher(), MappedNormalizer(), config),
            CandidateResolver(config),
            OverlapResolver(),
            PersonAliasGenerator(RussianPersonInflector()),
        )
    )
