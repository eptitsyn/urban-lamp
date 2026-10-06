import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.cli.app import app
from entity_marker.domain.aliases.generators import PersonAliasGenerator
from entity_marker.domain.models.entities import ObjectCatalog, Person, Sender
from entity_marker.domain.models.matches import MatchMethod
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.policies.matching import MatchingConfig
from entity_marker.infrastructure.morphology.russian import RussianPersonInflector


@pytest.mark.parametrize(
    "text",
    [
        "Иванов",
        "Иванова",
        "Иванову",
        "Ивановым",
        "Иванове",
        "Иванова Ивана Ивановича",
        "Иванову Ивану Ивановичу",
        "Иванов И.И.",
        "Иванов И. И.",
        "Иванову И.И.",
        "Иванова И. И.",
    ],
)
def test_morphology_and_initials_without_fuzzy(text: str) -> None:
    person = Person("p", "Иван", "Иванов", "Иванович")
    result = build_handler(MatchingConfig(fuzzy_enabled=False)).handle(
        MarkOccurrences(SourceText(text), ObjectCatalog(people=(person,)))
    )
    expected = text.split() if "." not in text else [text.split()[0]]
    assert [o.matched_text for o in result.occurrences] == expected
    for occurrence in result.occurrences:
        assert occurrence.entity_id == "p"
        assert occurrence.field_name in {"first_name", "last_name", "middle_name"}
        assert occurrence.method == MatchMethod.EXACT
        assert occurrence.edit_distance == 0
        assert text[occurrence.span.start : occurrence.span.end] == occurrence.matched_text


def test_inflected_component_aliases() -> None:
    aliases = PersonAliasGenerator(RussianPersonInflector()).generate(
        Person("p", "Иван", "Иванов", "Иванович")
    )
    values = {a.value for a in aliases}
    assert {"Иванову", "Ивану", "Ивановичу", "Ивана", "Ивановича", "Иванова"} <= values
    assert {a.field_name for a in aliases} == {"first_name", "last_name", "middle_name"}
    assert len(aliases) == len(set(aliases))


def test_feminine_person_does_not_get_masculine_surname() -> None:
    variants = RussianPersonInflector().forms(Person("p", "Анна", "Иванова", "Ивановна"))
    assert any(p.last_name == "Ивановой" and p.first_name == "Анне" for p in variants)
    assert not any(p.last_name in ("Иванов", "Ивановым") for p in variants)
    # Feminine accusative Иванову is valid too, paired with Анну.
    assert any(p.last_name == "Иванову" and p.first_name == "Анну" for p in variants)


def test_shared_inflected_surname_is_ambiguous() -> None:
    people = (Person("m", "Иван", "Иванов"), Person("f", "Анна", "Иванова"))
    result = build_handler(MatchingConfig(fuzzy_enabled=False)).handle(
        MarkOccurrences(SourceText("Иванова"), ObjectCatalog(people=people))
    )
    assert not result.occurrences
    assert any(d.reason == "ambiguous entity identity" for d in result.rejected)


def test_unknown_name_preserved() -> None:
    person = Person("p", "Xyzzy", "Qwertxyz")
    assert RussianPersonInflector().forms(person) == (person,)


@pytest.mark.parametrize(
    ("person", "text"),
    [
        (Person("p", "Иван", "Шевченко"), "Шевченко Ивану"),
        (Person("p", "Анна", "Шевченко"), "Шевченко Анне"),
        (Person("p", "Саша", "Иванов", "Иванович"), "Иванову Саше Ивановичу"),
        (Person("p", "Саша", "Иванова", "Ивановна"), "Ивановой Саше Ивановне"),
    ],
)
@pytest.mark.parametrize("role", ["person", "sender"])
def test_missing_gender_parses_do_not_abort_matching(person: Person, text: str, role: str) -> None:
    full_name = " ".join(
        value for value in (person.last_name, person.first_name, person.middle_name) if value
    )
    catalog = (
        ObjectCatalog(people=(person,))
        if role == "person"
        else ObjectCatalog(senders=(Sender("s", full_name=full_name),))
    )
    result = build_handler(MatchingConfig(fuzzy_enabled=False)).handle(
        MarkOccurrences(SourceText(text), catalog)
    )
    expected = text.split() if role == "person" else [text]
    assert [o.matched_text for o in result.occurrences] == expected
    assert all(o.entity_type.value == role for o in result.occurrences)


def test_original_ocr_example_person() -> None:
    text = "Принадлежит Птицыну Евгению Генриховичу."
    person = Person("p", "Евгений", "Птицын", "Генрихович")
    result = build_handler(MatchingConfig(fuzzy_enabled=False)).handle(
        MarkOccurrences(SourceText(text), ObjectCatalog(people=(person,)))
    )
    assert [o.matched_text for o in result.occurrences] == ["Птицыну", "Евгению", "Генриховичу"]


def test_wrong_initials_are_not_fuzzy_corrected() -> None:
    result = build_handler().handle(
        MarkOccurrences(
            SourceText("Иванов И.П."),
            ObjectCatalog(people=(Person("p", "Иван", "Иванов", "Иванович"),)),
        )
    )
    assert [(o.field_name, o.matched_text) for o in result.occurrences] == [("last_name", "Иванов")]


def test_cli_morphology_retains_original_offsets(tmp_path: Path) -> None:
    objects = tmp_path / "objects.json"
    objects.write_text(
        json.dumps(
            {
                "people": [
                    {
                        "id": "p",
                        "first_name": "Иван",
                        "last_name": "Иванов",
                        "middle_name": "Иванович",
                    }
                ]
            }
        )
    )
    text = "😀 Иванову И.И.; Иванова Ивана Ивановича."
    result = CliRunner().invoke(
        app, ["mark", "--objects", str(objects), "--disable-fuzzy"], input=text
    )
    assert result.exit_code == 0, result.output
    task = json.loads(result.stdout)[0]
    regions = task["predictions"][0]["result"]
    assert [r["value"]["text"] for r in regions] == ["Иванову", "Иванова", "Ивана", "Ивановича"]
    assert [r["value"]["labels"] for r in regions] == [
        ["PERSON_LAST_NAME"],
        ["PERSON_LAST_NAME"],
        ["PERSON_FIRST_NAME"],
        ["PERSON_MIDDLE_NAME"],
    ]
    for region in regions:
        value = region["value"]
        assert text[value["start"] : value["end"]] == value["text"]
