from datetime import date, datetime
from typing import Annotated

from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from entity_marker.domain.models.entities import (
    Car,
    Document,
    LegalEntity,
    Misc,
    ObjectCatalog,
    Person,
    Sender,
)

NonBlank = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
TaxId = Annotated[str, StringConstraints(pattern=r"^(?:[0-9]{10}|[0-9]{12})$")]


def parse_date(value: object) -> object:
    if isinstance(value, str):
        for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                continue
        raise ValueError("Dates must use YYYY-MM-DD or DD.MM.YYYY")
    return value


DateValue = Annotated[date, BeforeValidator(parse_date)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def reject_duplicate_aliases(cls, value: object) -> object:
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                alias = field.validation_alias
                if isinstance(alias, AliasChoices):
                    keys = {name, *(choice for choice in alias.choices if isinstance(choice, str))}
                    provided = sorted(key for key in keys if key in value)
                    if len(provided) > 1:
                        raise ValueError(f"Specify only one name for {name}: {', '.join(provided)}")
        return value


class PersonDTO(InputModel):
    id: NonBlank
    first_name: NonBlank | None = Field(None, validation_alias=AliasChoices("first_name", "Имя"))
    last_name: NonBlank | None = Field(None, validation_alias=AliasChoices("last_name", "Фамилия"))
    middle_name: NonBlank | None = Field(
        None, validation_alias=AliasChoices("middle_name", "отчество", "Отчество")
    )
    birth_date: DateValue | None = Field(
        None, validation_alias=AliasChoices("birth_date", "дата рождения")
    )
    previous_last_name: NonBlank | None = Field(
        None, validation_alias=AliasChoices("previous_last_name", "предыдущая фамилия")
    )


class CarDTO(InputModel):
    id: NonBlank
    vin: NonBlank | None = None
    license_plate: NonBlank | None = None
    body_number: NonBlank | None = None
    chassis_number: NonBlank | None = None


class DocumentDTO(InputModel):
    id: NonBlank
    document_type: NonBlank | None = Field(
        None, validation_alias=AliasChoices("document_type", "Тип")
    )
    series: NonBlank | None = Field(None, validation_alias=AliasChoices("series", "серия"))
    number: NonBlank | None = Field(None, validation_alias=AliasChoices("number", "номер"))
    issue_date: DateValue | None = None


class LegalEntityDTO(InputModel):
    id: NonBlank
    inn: TaxId | None = Field(None, validation_alias=AliasChoices("inn", "ИНН"))
    name: NonBlank | None = Field(None, validation_alias=AliasChoices("name", "ИМЯ_ЮЛ"))


class SenderDTO(InputModel):
    id: NonBlank
    full_name: NonBlank | None = Field(None, validation_alias=AliasChoices("full_name", "ФИО"))
    position: NonBlank | None = Field(None, validation_alias=AliasChoices("position", "Должность"))
    organization_name: NonBlank | None = Field(
        None, validation_alias=AliasChoices("organization_name", "Название организации")
    )
    return_address: NonBlank | None = Field(
        None, validation_alias=AliasChoices("return_address", "обратный адрес")
    )
    email: str | None = None
    inn: TaxId | None = Field(None, validation_alias=AliasChoices("inn", "ИНН"))


class MiscDTO(InputModel):
    id: NonBlank
    incoming_letter_number: NonBlank | None = Field(
        None, validation_alias=AliasChoices("incoming_letter_number", "номер вх письма")
    )
    case_number: NonBlank | None = Field(
        None, validation_alias=AliasChoices("case_number", "номер дела")
    )
    incoming_letter_date: DateValue | None = Field(
        None, validation_alias=AliasChoices("incoming_letter_date", "дата вх письма")
    )
    preliminary_response_due_date: DateValue | None = Field(
        None,
        validation_alias=AliasChoices(
            "preliminary_response_due_date",
            "дата истеченияпредв ответа",
            "дата истечения предв ответа",
        ),
    )
    reply_email: str | None = Field(
        None, validation_alias=AliasChoices("reply_email", "email для ответа")
    )
    reply_address: NonBlank | None = Field(
        None, validation_alias=AliasChoices("reply_address", "адрес для ответа")
    )


class ObjectCatalogDTO(InputModel):
    people: list[PersonDTO] = Field(
        default_factory=list, validation_alias=AliasChoices("people", "ФизЛицо")
    )
    cars: list[CarDTO] = Field(default_factory=list)
    documents: list[DocumentDTO] = Field(
        default_factory=list, validation_alias=AliasChoices("documents", "Документ")
    )
    legal_entities: list[LegalEntityDTO] = Field(
        default_factory=list, validation_alias=AliasChoices("legal_entities", "Юр Лицо", "ЮрЛицо")
    )
    senders: list[SenderDTO] = Field(
        default_factory=list, validation_alias=AliasChoices("senders", "Отправитель")
    )
    miscellaneous: list[MiscDTO] = Field(
        default_factory=list, validation_alias=AliasChoices("miscellaneous", "Прочее")
    )

    def to_domain(self) -> ObjectCatalog:
        return ObjectCatalog(
            people=tuple(
                Person(
                    p.id,
                    p.first_name,
                    p.last_name,
                    p.middle_name,
                    p.birth_date,
                    p.previous_last_name,
                )
                for p in self.people
            ),
            cars=tuple(
                Car(c.id, c.vin, c.license_plate, c.body_number, c.chassis_number)
                for c in self.cars
            ),
            documents=tuple(
                Document(d.id, d.document_type, d.series, d.number, d.issue_date)
                for d in self.documents
            ),
            legal_entities=tuple(LegalEntity(e.id, e.inn, e.name) for e in self.legal_entities),
            senders=tuple(
                Sender(
                    s.id,
                    s.full_name,
                    s.position,
                    s.organization_name,
                    s.return_address,
                    s.email,
                    s.inn,
                )
                for s in self.senders
            ),
            miscellaneous=tuple(
                Misc(
                    m.id,
                    m.incoming_letter_number,
                    m.case_number,
                    m.incoming_letter_date,
                    m.preliminary_response_due_date,
                    m.reply_email,
                    m.reply_address,
                )
                for m in self.miscellaneous
            ),
        )


def parse_objects(payload: str) -> ObjectCatalog:
    return ObjectCatalogDTO.model_validate_json(payload).to_domain()
