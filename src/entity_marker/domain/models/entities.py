from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class EntityType(StrEnum):
    PERSON = "person"
    CAR = "car"
    DOCUMENT = "document"
    LEGAL_ENTITY = "legal_entity"
    SENDER = "sender"
    MISC = "misc"


@dataclass(frozen=True)
class Person:
    id: str
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    birth_date: date | None = None
    previous_last_name: str | None = None


@dataclass(frozen=True)
class Car:
    id: str
    vin: str | None = None
    license_plate: str | None = None
    body_number: str | None = None
    chassis_number: str | None = None


@dataclass(frozen=True)
class Document:
    id: str
    document_type: str | None = None
    series: str | None = None
    number: str | None = None
    issue_date: date | None = None


@dataclass(frozen=True)
class LegalEntity:
    id: str
    inn: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class Sender:
    id: str
    full_name: str | None = None
    position: str | None = None
    organization_name: str | None = None
    return_address: str | None = None
    email: str | None = None
    inn: str | None = None


@dataclass(frozen=True)
class Misc:
    id: str
    incoming_letter_number: str | None = None
    case_number: str | None = None
    incoming_letter_date: date | None = None
    preliminary_response_due_date: date | None = None
    reply_email: str | None = None
    reply_address: str | None = None


@dataclass(frozen=True)
class ObjectCatalog:
    people: tuple[Person, ...] = ()
    cars: tuple[Car, ...] = ()
    documents: tuple[Document, ...] = ()
    legal_entities: tuple[LegalEntity, ...] = ()
    senders: tuple[Sender, ...] = ()
    miscellaneous: tuple[Misc, ...] = ()

    def __post_init__(self) -> None:
        for group in (
            self.people,
            self.cars,
            self.documents,
            self.legal_entities,
            self.senders,
            self.miscellaneous,
        ):
            ids = [entity.id for entity in group]
            if any(not value.strip() for value in ids):
                raise ValueError("Entity IDs must not be blank")
            if len(ids) != len(set(ids)):
                raise ValueError("Entity IDs must be unique within each entity type")
