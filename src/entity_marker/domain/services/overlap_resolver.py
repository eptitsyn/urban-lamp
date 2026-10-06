import logging

from entity_marker.domain.models.entities import EntityType
from entity_marker.domain.models.matches import ObjectOccurrence
from entity_marker.domain.services.candidate_resolver import METHOD_PRIORITY

logger = logging.getLogger(__name__)


def occurrence_order(item: ObjectOccurrence) -> tuple[int, int, str, str, str]:
    return item.span.start, item.span.end, item.entity_type.value, item.entity_id, item.field_name


def _compatible_roles(first: ObjectOccurrence, second: ObjectOccurrence) -> bool:
    if first.entity_type == second.entity_type:
        return False
    if first.span == second.span:
        return True
    person, sender = (first, second) if first.entity_type == EntityType.PERSON else (second, first)
    # A sender's full name and a person's name components describe different roles.
    return (
        person.entity_type == EntityType.PERSON
        and sender.entity_type == EntityType.SENDER
        and person.field_name in {"first_name", "last_name", "middle_name", "previous_last_name"}
        and sender.field_name == "full_name"
        and sender.span.start <= person.span.start
        and person.span.end <= sender.span.end
    )


class OverlapResolver:
    """Greedy overlap policy with compatible domain-role annotations retained."""

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
                and not _compatible_roles(item, other)
                for other in kept
            ):
                logger.debug("Overlap rejected: %s", item)
                rejected.append(item)
            else:
                kept.append(item)
        return tuple(sorted(kept, key=occurrence_order)), tuple(rejected)
