from dataclasses import dataclass

from entity_marker.domain.models.entities import ObjectCatalog
from entity_marker.domain.models.matches import MarkingResult
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.services.marking import OccurrenceMarker


@dataclass(frozen=True)
class MarkOccurrences:
    source: SourceText
    objects: ObjectCatalog


class MarkOccurrencesHandler:
    def __init__(self, marker: OccurrenceMarker) -> None:
        self.marker = marker

    def handle(self, command: MarkOccurrences) -> MarkingResult:
        return self.marker.mark(command.source, command.objects)
