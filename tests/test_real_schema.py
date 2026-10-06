import json
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.cli.app import app
from entity_marker.domain.aliases.generators import generate_aliases
from entity_marker.domain.models.entities import LegalEntity, Misc, ObjectCatalog, Person, Sender
from entity_marker.domain.models.matches import MarkingResult, MatchMethod
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.policies.matching import MatchingConfig
from entity_marker.infrastructure.serialization.input_dto import ObjectCatalogDTO, parse_objects

ROOT = Path(__file__).resolve().parents[1]


def mark(text: str, catalog: ObjectCatalog, fuzzy: bool = False) -> MarkingResult:
    return build_handler(MatchingConfig(fuzzy_enabled=fuzzy)).handle(
        MarkOccurrences(SourceText(text), catalog)
    )


def test_russian_and_english_schema() -> None:
    payload = (ROOT / "examples/real_objects.json").read_text(encoding="utf-8")
    dto = ObjectCatalogDTO.model_validate_json(payload)
    catalog = dto.to_domain()
    assert parse_objects(dto.model_dump_json()) == catalog
    assert catalog.legal_entities[0] == LegalEntity("org-1", "7701234567", "ООО «Ромашка»")
    assert catalog.people[0].previous_last_name == "Петров"
    assert catalog.people[0].birth_date == date(1980, 1, 1)
    assert catalog.senders[0].position == "директор"
    assert catalog.miscellaneous[0].preliminary_response_due_date == date(2026, 10, 10)
    assert catalog.documents[0].document_type == "паспорт"


@pytest.mark.parametrize("group", ["legal_entities", "senders", "miscellaneous"])
def test_duplicate_ids_in_new_groups(group: str) -> None:
    with pytest.raises(ValueError, match="unique"):
        parse_objects(json.dumps({group: [{"id": "x"}, {"id": "x"}]}))


@pytest.mark.parametrize("inn", [1234567890, "123", "123456789x", "1234567890123"])
def test_invalid_tax_id(inn: object) -> None:
    with pytest.raises(ValueError):
        parse_objects(json.dumps({"Юр Лицо": [{"id": "x", "ИНН": inn}]}))


def test_leading_zero_tax_id_preserved() -> None:
    catalog = parse_objects('{"legal_entities":[{"id":"l","inn":"0012345678"}]}')
    assert catalog.legal_entities[0].inn == "0012345678"


@pytest.mark.parametrize("value", ["31.02.2026", "2026-13-01", 0, True])
def test_invalid_dates(value: object) -> None:
    with pytest.raises(ValueError):
        parse_objects(json.dumps({"Прочее": [{"id": "x", "дата вх письма": value}]}))


def test_conflicting_aliases_are_rejected() -> None:
    with pytest.raises(ValueError):
        parse_objects('{"people":[{"id":"p","first_name":"Иван","Имя":"Павел"}]}')


def test_previous_surname_inflected_and_initials() -> None:
    catalog = ObjectCatalog(
        people=(Person("p", "Иван", "Иванов", "Иванович", previous_last_name="Петров"),)
    )
    result = mark("Петрову Ивану Ивановичу; Петрова И.И.; Иванов И.И.", catalog)
    assert [(o.field_name, o.matched_text) for o in result.occurrences] == [
        ("previous_last_name", "Петрову"),
        ("first_name", "Ивану"),
        ("middle_name", "Ивановичу"),
        ("previous_last_name", "Петрова"),
        ("last_name", "Иванов"),
    ]
    assert {o.entity_id for o in result.occurrences} == {"p"}
    assert all(o.edit_distance == 0 for o in result.occurrences)


def test_previous_surname_keeps_ambiguity_checks() -> None:
    catalog = ObjectCatalog(
        people=(
            Person("p1", last_name="Иванов", previous_last_name="Петров"),
            Person("p2", last_name="Петров"),
        )
    )
    assert not mark("Петров", catalog).occurrences


def test_sender_morphology_initials_and_role() -> None:
    catalog = ObjectCatalog(senders=(Sender("s", full_name="Иванов Иван Иванович"),))
    result = mark("Иванову Ивану Ивановичу; Иванова И.И.", catalog)
    assert len(result.occurrences) == 2
    assert {o.entity_type.value for o in result.occurrences} == {"sender"}
    assert {o.field_name for o in result.occurrences} == {"full_name"}


def test_legal_name_quotes_case_and_whitespace() -> None:
    catalog = ObjectCatalog(legal_entities=(LegalEntity("l", name="ООО «Ромашка»"),))
    text = 'ооо  "ромашка"'
    result = mark(text, catalog)
    assert len(result.occurrences) == 1
    assert result.occurrences[0].method == MatchMethod.NORMALIZED
    assert result.occurrences[0].matched_text == text


def test_shared_organization_and_tax_id_keep_both_roles() -> None:
    catalog = ObjectCatalog(
        legal_entities=(LegalEntity("l", "7701234567", "Ромашка"),),
        senders=(Sender("s", organization_name="Ромашка", inn="7701234567"),),
    )
    result = mark("Ромашка, ИНН 7701234567", catalog)
    assert len(result.occurrences) == 4
    assert {o.entity_type.value for o in result.occurrences} == {"sender", "legal_entity"}


@pytest.mark.parametrize(
    "text",
    [
        "xreply@example.org",
        "reply@example.org.ru",
        "reply@example.orgx",
        "a.reply@example.org",
        "reply@example.org-other",
    ],
)
def test_email_substrings_rejected(text: str) -> None:
    catalog = ObjectCatalog(miscellaneous=(Misc("m", reply_email="reply@example.org"),))
    assert not mark(text, catalog, fuzzy=True).occurrences


def test_email_case_punctuation_and_wrong_character() -> None:
    catalog = ObjectCatalog(miscellaneous=(Misc("m", reply_email="reply@example.org"),))
    text = "Пишите REPLY@EXAMPLE.ORG."
    result = mark(text, catalog, fuzzy=True)
    assert [o.matched_text for o in result.occurrences] == ["REPLY@EXAMPLE.ORG"]
    assert not mark("replx@example.org", catalog, fuzzy=True).occurrences


def test_tax_id_normalization_without_fuzzy() -> None:
    catalog = ObjectCatalog(legal_entities=(LegalEntity("l", inn="7701234567"),))
    result = mark("77 01 234567", catalog, fuzzy=True)
    assert [o.matched_text for o in result.occurrences] == ["77 01 234567"]
    assert not mark("7701234568", catalog, fuzzy=True).occurrences


@pytest.mark.parametrize("text", ["А40-12345/2027", "А40-12345/2026-2", "XА40-12345/2026"])
def test_case_numbers_not_fuzzed_or_matched_inside_larger_values(text: str) -> None:
    catalog = ObjectCatalog(miscellaneous=(Misc("m", case_number="А40-12345/2026"),))
    assert not mark(text, catalog, fuzzy=True).occurrences


def test_case_number_spacing_and_address_normalization() -> None:
    catalog = ObjectCatalog(
        miscellaneous=(
            Misc("m", case_number="А40-12345/2026", reply_address="Москва, ул. Лесная, д. 10"),
        )
    )
    text = "А40 - 12345 / 2026; москва,  ул. лесная, д. 10"
    assert [o.matched_text for o in mark(text, catalog).occurrences] == [
        "А40 - 12345 / 2026",
        "москва,  ул. лесная, д. 10",
    ]


def test_all_fields_example_cli_and_labels(tmp_path: Path) -> None:
    objects = ROOT / "examples/real_objects.json"
    text_path = ROOT / "examples/real_text.txt"
    evidence = tmp_path / "evidence.json"
    result = CliRunner().invoke(
        app,
        [
            "mark",
            "--objects",
            str(objects),
            "--text",
            str(text_path),
            "--disable-fuzzy",
            "--evidence-output",
            str(evidence),
        ],
    )
    assert result.exit_code == 0, result.output
    task = json.loads(result.stdout)[0]
    occurrences = json.loads(evidence.read_text())["occurrences"]
    assert len(occurrences) == 23
    assert {o["entity_type"] for o in occurrences} == {
        "person",
        "document",
        "legal_entity",
        "sender",
        "misc",
    }
    assert {o["field_name"] for o in occurrences if o["entity_type"] == "misc"} == {
        "incoming_letter_number",
        "case_number",
        "incoming_letter_date",
        "preliminary_response_due_date",
        "reply_email",
        "reply_address",
    }
    labels = {
        label.attrib["value"]
        for label in ElementTree.parse(ROOT / "examples/labeling_config.xml").iter("Label")
    }
    for region in task["predictions"][0]["result"]:
        value = region["value"]
        assert task["data"]["text"][value["start"] : value["end"]] == value["text"]
        assert set(value["labels"]) <= labels
    catalog = parse_objects(objects.read_text())
    assert {
        f"{a.entity_type.value}_{a.field_name}".upper() for a in generate_aliases(catalog)
    } <= labels
