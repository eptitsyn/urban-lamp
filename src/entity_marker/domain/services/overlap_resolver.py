import logging

from entity_marker.domain.models.matches import ObjectOccurrence
from entity_marker.domain.services.candidate_resolver import METHOD_PRIORITY

logger = logging.getLogger(__name__)


def occurrence_order(item: ObjectOccurrence) -> tuple[int, int, str, str, str]:
    return item.span.start, item.span.end, item.entity_type.value, item.entity_id, item.field_name


class OverlapResolver:
    """Greedy overlap policy; identical spans in distinct domain roles are retained."""

    def resolve(
        self, occurrences: list[ObjectOccurrence]
    ) -> tuple[tuple[ObjectOccurrence, ...], tuple[ObjectOccurrence, ...]]:
        ranked = sorted(
            occurrences,
            key=lambda item: (
                METHOD_PRIORITY[item.method],
                -item.score.value,
                item.edit_distance,
                -(item.span.end - item.span.start),
                occurrence_order(item),
            ),
        )
        kept: list[ObjectOccurrence] = []
        rejected: list[ObjectOccurrence] = []
        for item in ranked:
            if any(
                item.span.start < other.span.end
                and other.span.start < item.span.end
                and not (item.span == other.span and item.entity_type != other.entity_type)
                for other in kept
            ):
                logger.debug("Overlap rejected: %s", item)
                rejected.append(item)
            else:
                kept.append(item)
        return tuple(sorted(kept, key=occurrence_order)), tuple(rejected)
