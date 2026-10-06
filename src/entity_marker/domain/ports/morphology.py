from typing import Protocol

from entity_marker.domain.models.entities import Person


class PersonInflector(Protocol):
    """Return case-aligned name variants while preserving the person's identity."""

    def forms(self, person: Person) -> tuple[Person, ...]: ...
