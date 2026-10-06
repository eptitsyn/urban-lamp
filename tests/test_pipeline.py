from datetime import date

import pytest

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.domain.aliases.generators import generate_aliases
from entity_marker.domain.models.entities import Car, Document, ObjectCatalog, Person
from entity_marker.domain.models.matches import MarkingResult, MatchMethod
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.policies.matching import MatchingConfig, allowed_distance


def mark(text: str, catalog: ObjectCatalog, config: MatchingConfig | None = None) -> MarkingResult:
    return build_handler(config).handle(MarkOccurrences(SourceText(text), catalog))


def test_required_ocr_example() -> None:
    catalog = ObjectCatalog(cars=(Car("c1", "X7LHSRDVN12345678", "А123ВС77"),))
    text = "Автомобиль А 123 ВС 77 с VIN X7LHSR0VN12345678 принадлежит Птицыну."
    result = mark(text, catalog)
    assert [(m.field_name, m.method) for m in result.occurrences] == [
        ("license_plate", MatchMethod.NORMALIZED),
        ("vin", MatchMethod.BITAP),
    ]
    assert result.occurrences[1].edit_distance == 1
    assert all(text[m.span.start : m.span.end] == m.matched_text for m in result.occurrences)


def test_exact_does_not_hide_later_fuzzy_occurrence() -> None:
    catalog = ObjectCatalog(cars=(Car("c1", vin="X7LHSRDVN12345678"),))
    result = mark("X7LHSRDVN12345678 затем X7LHSR0VN12345678", catalog)
    assert [m.method for m in result.occurrences] == [MatchMethod.EXACT, MatchMethod.BITAP]


@pytest.mark.parametrize("text", ["X7LHSRXDVN12345678", "X7LHSRVN12345678"])
def test_insert_delete_end_to_end(text: str) -> None:
    result = mark(text, ObjectCatalog(cars=(Car("c1", vin="X7LHSRDVN12345678"),)))
    assert len(result.occurrences) == 1
    assert result.occurrences[0].matched_text == text
    assert result.occurrences[0].edit_distance == 1


@pytest.mark.parametrize("text", ["xxА123ВС77yy", "А 123\nВС 77"])
def test_no_substrings_or_unbounded_gaps(text: str) -> None:
    assert not mark(text, ObjectCatalog(cars=(Car("c", license_plate="А123ВС77"),))).occurrences


@pytest.mark.parametrize("fuzzy", [False, True])
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Иванов Иван Иванович",
            [("last_name", "Иванов"), ("first_name", "Иван"), ("middle_name", "Иванович")],
        ),
        (
            "Иван Иванович Иванов",
            [("first_name", "Иван"), ("middle_name", "Иванович"), ("last_name", "Иванов")],
        ),
        ("Иванов Иван", [("last_name", "Иванов"), ("first_name", "Иван")]),
        ("Иван Иванович", [("first_name", "Иван"), ("middle_name", "Иванович")]),
        (
            "ИВАНОВ  ИВАН  ИВАНОВИЧ",
            [("last_name", "ИВАНОВ"), ("first_name", "ИВАН"), ("middle_name", "ИВАНОВИЧ")],
        ),
    ],
)
def test_person_name_components_are_separate(
    text: str, expected: list[tuple[str, str]], fuzzy: bool
) -> None:
    person = Person("p", "Иван", "Иванов", "Иванович", date(1980, 1, 1))
    catalog = ObjectCatalog(people=(person,))
    aliases = generate_aliases(catalog)
    assert {a.field_name for a in aliases} == {
        "first_name",
        "last_name",
        "middle_name",
        "birth_date",
    }
    assert "01.01.1980" in {a.value for a in aliases}
    result = mark(text, catalog, MatchingConfig(fuzzy_enabled=fuzzy))
    assert [(o.field_name, o.matched_text) for o in result.occurrences] == expected
    assert all(text[o.span.start : o.span.end] == o.matched_text for o in result.occurrences)
    assert not any(d.candidate.alias.field_name == "full_name" for d in result.rejected)


def test_ambiguous_surname_is_rejected_without_id_tiebreak() -> None:
    people = (Person("a", "Иван", "Петров"), Person("b", "Павел", "Петров"))
    result = mark("Петров", ObjectCatalog(people=people))
    assert not result.occurrences
    assert any(d.reason == "ambiguous entity identity" for d in result.rejected)
    assert mark("Петров", ObjectCatalog(people=people[::-1])) == result


def test_local_evidence_resolves_identity_but_remote_does_not() -> None:
    people = (Person("a", "Иван", "Петров"), Person("b", "Павел", "Петров"))
    local = mark("Петров, имя Иван", ObjectCatalog(people=people))
    assert {m.entity_id for m in local.occurrences} == {"a"}
    remote = mark("Петров. Имя Иван", ObjectCatalog(people=people))
    assert not remote.occurrences


def test_weak_first_name_and_short_values() -> None:
    assert not mark("Иван", ObjectCatalog(people=(Person("p", first_name="Иван"),))).occurrences
    assert not mark("124", ObjectCatalog(documents=(Document("d", number="123"),))).occurrences


def test_series_number_normalization() -> None:
    catalog = ObjectCatalog(documents=(Document("d", series="4501", number="123456"),))
    result = mark("Паспорт 45 01 № 123456", catalog)
    # Exact number wins over normalized enclosing identifier under the flat overlap policy.
    assert any(m.field_name == "number" for m in result.occurrences)
    assert any(d.candidate.alias.field_name == "series_number" for d in result.rejected)


def test_dates_are_exact_only() -> None:
    catalog = ObjectCatalog(people=(Person("p", birth_date=date(1980, 1, 1)),))
    assert mark("01.01.1980", catalog).occurrences[0].field_name == "birth_date"
    assert not mark("01.01.1981", catalog).occurrences


def test_disabled_fuzzy_retains_normalized_matches() -> None:
    catalog = ObjectCatalog(cars=(Car("c", "X7LHSRDVN12345678", "А123ВС77"),))
    text = "А 123 ВС 77 X7LHSR0VN12345678"
    for config in (MatchingConfig(fuzzy_enabled=False), MatchingConfig(max_errors=0)):
        result = mark(text, catalog, config)
        assert [m.method for m in result.occurrences] == [MatchMethod.NORMALIZED]


def test_policy_ceiling_and_weight_override() -> None:
    aliases = generate_aliases(ObjectCatalog(cars=(Car("c", vin="X7LHSRDVN12345678"),)))
    assert allowed_distance(aliases[0], aliases[0].value, MatchingConfig(max_errors=9)) == 1
    assert not mark(
        "X7LHSRDVN12345678",
        ObjectCatalog(cars=(Car("c", vin="X7LHSRDVN12345678"),)),
        MatchingConfig(field_weights=(("vin", 0.2),)),
    ).occurrences
    with pytest.raises(ValueError):
        MatchingConfig(max_errors=-1)


def test_normalization_does_not_bridge_large_gap() -> None:
    result = mark(
        "А        123 ВС77",
        ObjectCatalog(cars=(Car("c", license_plate="А123ВС77"),)),
        MatchingConfig(fuzzy_enabled=False),
    )
    assert not result.occurrences
