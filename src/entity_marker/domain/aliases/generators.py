from dataclasses import replace
from datetime import date

from entity_marker.domain.models.entities import (
    Car,
    Document,
    EntityType,
    LegalEntity,
    Misc,
    ObjectCatalog,
    Person,
    Sender,
)
from entity_marker.domain.models.matches import EntityAlias, NormalizationProfile
from entity_marker.domain.policies.matching import FIELD_WEIGHTS, MatchingConfig
from entity_marker.domain.ports.morphology import PersonInflector


def _alias(
    kind: EntityType,
    identity: str,
    field: str,
    value: str,
    profile: NormalizationProfile,
    factor: float = 1.0,
) -> EntityAlias:
    return EntityAlias(identity, kind, field, value, FIELD_WEIGHTS[field] * factor, profile)


def _date_aliases(
    kind: EntityType, identity: str, field: str, value: date | None
) -> list[EntityAlias]:
    if value is None:
        return []
    return [
        _alias(kind, identity, field, formatted, NormalizationProfile.DATE)
        for formatted in (value.isoformat(), value.strftime("%d.%m.%Y"), value.strftime("%d/%m/%Y"))
    ]


class PersonAliasGenerator:
    def __init__(self, inflector: PersonInflector | None = None) -> None:
        self.inflector = inflector

    def generate(self, person: Person) -> list[EntityAlias]:
        variants = self.inflector.forms(person) if self.inflector else (person,)
        result = [alias for variant in variants for alias in self._generate(variant)]
        if person.previous_last_name:
            previous = replace(person, last_name=person.previous_last_name, previous_last_name=None)
            previous_variants = self.inflector.forms(previous) if self.inflector else (previous,)
            for variant in previous_variants:
                for alias in self._generate(variant):
                    if alias.field_name == "last_name":
                        result.append(replace(alias, field_name="previous_" + alias.field_name))
        return list(dict.fromkeys(result))

    @staticmethod
    def _generate(person: Person) -> list[EntityAlias]:
        kind, profile = EntityType.PERSON, NormalizationProfile.NAME
        result = [
            _alias(kind, person.id, field, value, profile)
            for field, value in (
                ("first_name", person.first_name),
                ("last_name", person.last_name),
                ("middle_name", person.middle_name),
            )
            if value
        ]
        result.extend(_date_aliases(kind, person.id, "birth_date", person.birth_date))
        return result


class CarAliasGenerator:
    def generate(self, car: Car) -> list[EntityAlias]:
        return [
            _alias(EntityType.CAR, car.id, field, value, profile)
            for field, value, profile in (
                ("vin", car.vin, NormalizationProfile.VIN),
                ("license_plate", car.license_plate, NormalizationProfile.PLATE),
                ("body_number", car.body_number, NormalizationProfile.IDENTIFIER),
                ("chassis_number", car.chassis_number, NormalizationProfile.IDENTIFIER),
            )
            if value
        ]


class DocumentAliasGenerator:
    def generate(self, document: Document) -> list[EntityAlias]:
        kind, profile = EntityType.DOCUMENT, NormalizationProfile.IDENTIFIER
        result = [
            _alias(kind, document.id, field, value, profile)
            for field, value in (("series", document.series), ("number", document.number))
            if value
        ]
        if document.series and document.number:
            result.append(
                _alias(
                    kind,
                    document.id,
                    "series_number",
                    f"{document.series} {document.number}",
                    profile,
                )
            )
        if document.document_type:
            result.append(
                _alias(
                    kind,
                    document.id,
                    "document_type",
                    document.document_type,
                    NormalizationProfile.TEXT,
                )
            )
        result.extend(_date_aliases(kind, document.id, "issue_date", document.issue_date))
        return result


class LegalEntityAliasGenerator:
    def generate(self, entity: LegalEntity) -> list[EntityAlias]:
        return [
            _alias(EntityType.LEGAL_ENTITY, entity.id, field, value, profile)
            for field, value, profile in (
                ("inn", entity.inn, NormalizationProfile.TAX_ID),
                ("name", entity.name, NormalizationProfile.TEXT),
            )
            if value
        ]


class SenderAliasGenerator:
    def __init__(self, people: PersonAliasGenerator) -> None:
        self.people = people

    def generate(self, sender: Sender) -> list[EntityAlias]:
        result = [
            _alias(EntityType.SENDER, sender.id, field, value, profile)
            for field, value, profile in (
                ("full_name", sender.full_name, NormalizationProfile.NAME),
                ("position", sender.position, NormalizationProfile.TEXT),
                ("organization_name", sender.organization_name, NormalizationProfile.TEXT),
                ("return_address", sender.return_address, NormalizationProfile.TEXT),
                ("email", sender.email, NormalizationProfile.EMAIL),
                ("inn", sender.inn, NormalizationProfile.TAX_ID),
            )
            if value
        ]
        # The input contract for full ФИО is surname, given name, optional patronymic.
        # Initials and unusual formats stay literal instead of guessing name parts.
        if sender.full_name:
            parts = sender.full_name.split()
            if len(parts) in (2, 3) and all(part.replace("-", "").isalpha() for part in parts):
                person = Person(
                    sender.id,
                    first_name=parts[1],
                    last_name=parts[0],
                    middle_name=parts[2] if len(parts) == 3 else None,
                )
                inflector = self.people.inflector
                variants = inflector.forms(person) if inflector else (person,)
                result.extend(
                    alias for variant in variants for alias in self._full_name_aliases(variant)
                )
        return list(dict.fromkeys(result))

    @staticmethod
    def _full_name_aliases(person: Person) -> list[EntityAlias]:
        kind, profile = EntityType.SENDER, NormalizationProfile.NAME
        result: list[EntityAlias] = []
        first, last, middle = person.first_name, person.last_name, person.middle_name
        if first and last:
            result.append(_alias(kind, person.id, "full_name", f"{last} {first}", profile, 0.9))
            if middle:
                result.extend(
                    _alias(kind, person.id, "full_name", value, profile)
                    for value in (f"{last} {first} {middle}", f"{first} {middle} {last}")
                )
                result.append(
                    _alias(
                        kind,
                        person.id,
                        "full_name",
                        f"{last} {first[0]}. {middle[0]}.",
                        profile,
                        0.85,
                    )
                )
                result.append(
                    _alias(
                        kind,
                        person.id,
                        "full_name",
                        f"{last} {first[0]}.{middle[0]}.",
                        profile,
                        0.85,
                    )
                )
            else:
                result.append(_alias(kind, person.id, "full_name", f"{first} {last}", profile, 0.9))
        return result


class MiscAliasGenerator:
    def generate(self, item: Misc) -> list[EntityAlias]:
        result = [
            _alias(EntityType.MISC, item.id, field, value, profile)
            for field, value, profile in (
                (
                    "incoming_letter_number",
                    item.incoming_letter_number,
                    NormalizationProfile.REFERENCE,
                ),
                ("case_number", item.case_number, NormalizationProfile.REFERENCE),
                ("reply_email", item.reply_email, NormalizationProfile.EMAIL),
                ("reply_address", item.reply_address, NormalizationProfile.TEXT),
            )
            if value
        ]
        for field, value in (
            ("incoming_letter_date", item.incoming_letter_date),
            ("preliminary_response_due_date", item.preliminary_response_due_date),
        ):
            result.extend(_date_aliases(EntityType.MISC, item.id, field, value))
        return result


def generate_aliases(
    catalog: ObjectCatalog,
    config: MatchingConfig | None = None,
    person_generator: PersonAliasGenerator | None = None,
) -> tuple[EntityAlias, ...]:
    person_generator = person_generator or PersonAliasGenerator()
    aliases = [alias for person in catalog.people for alias in person_generator.generate(person)]
    aliases.extend(alias for car in catalog.cars for alias in CarAliasGenerator().generate(car))
    aliases.extend(
        alias for doc in catalog.documents for alias in DocumentAliasGenerator().generate(doc)
    )
    aliases.extend(
        alias
        for entity in catalog.legal_entities
        for alias in LegalEntityAliasGenerator().generate(entity)
    )
    aliases.extend(
        alias
        for sender in catalog.senders
        for alias in SenderAliasGenerator(person_generator).generate(sender)
    )
    aliases.extend(
        alias for item in catalog.miscellaneous for alias in MiscAliasGenerator().generate(item)
    )
    if config is not None:
        overrides = dict(config.field_weights)
        aliases = [
            replace(
                alias,
                weight=(alias.weight / FIELD_WEIGHTS[alias.field_name])
                * overrides[alias.field_name],
            )
            if alias.field_name in overrides
            else alias
            for alias in aliases
        ]
    return tuple(
        sorted(
            set(aliases),
            key=lambda a: (
                a.entity_type.value,
                a.entity_id,
                a.field_name,
                a.value,
                a.weight,
            ),
        )
    )
