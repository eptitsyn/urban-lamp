from entity_marker.domain.aliases.generators import PersonAliasGenerator, generate_aliases
from entity_marker.domain.models.entities import ObjectCatalog
from entity_marker.domain.models.matches import (
    MarkingResult,
    ResolutionDecision,
)
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.services.candidate_generator import CandidateGenerator
from entity_marker.domain.services.candidate_resolver import CandidateResolver
from entity_marker.domain.services.overlap_resolver import OverlapResolver


class OccurrenceMarker:
    def __init__(
        self,
        generator: CandidateGenerator,
        resolver: CandidateResolver,
        overlaps: OverlapResolver,
        person_aliases: PersonAliasGenerator | None = None,
    ) -> None:
        self.person_aliases = person_aliases
        self.generator = generator
        self.resolver = resolver
        self.overlaps = overlaps

    def mark(self, source: SourceText, catalog: ObjectCatalog) -> MarkingResult:
        aliases = generate_aliases(catalog, self.generator.config, self.person_aliases)
        candidates = self.generator.generate(source, aliases)
        accepted, rejected = self.resolver.resolve(candidates, source)
        kept, overlaps = self.overlaps.resolve(accepted)
        for item in overlaps:
            # Recover the original candidate for a lossless rejection report.
            candidate = next(
                c
                for c in candidates
                if (
                    c.alias.entity_id == item.entity_id
                    and c.alias.entity_type == item.entity_type
                    and c.alias.field_name == item.field_name
                    and c.span == item.span
                    and c.method == item.method
                    and c.alias.value == item.source_value
                )
            )
            rejected.append(ResolutionDecision(candidate, "overlap with stronger occurrence"))
        return MarkingResult(kept, tuple(rejected))
