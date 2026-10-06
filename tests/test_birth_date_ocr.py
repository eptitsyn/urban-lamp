import csv
import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.cli.app import app
from entity_marker.domain.models.entities import Document, Misc, ObjectCatalog, Person
from entity_marker.domain.models.matches import MatchMethod
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.policies.matching import MatchingConfig


@pytest.mark.parametrize(
    "text",
    [
        "20.01 1 1973",
        "20.O1.1973",
        "20.01.1974",
        "20.01..1973",
        "20.011973",
        "1973-01-2O",
        "20/01/197B",
    ],
)
def test_birth_date_allows_one_ocr_edit(text: str) -> None:
    catalog = ObjectCatalog(people=(Person("p", birth_date=date(1973, 1, 20)),))
    result = build_handler().handle(MarkOccurrences(SourceText(text), catalog))
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert occurrence.field_name == "birth_date"
    assert occurrence.matched_text == text
    assert occurrence.method == MatchMethod.BITAP
    assert occurrence.edit_distance == 1
    assert text[occurrence.span.start : occurrence.span.end] == text


@pytest.mark.parametrize(
    "text",
    [
        "20.01\n1 1973",
        "20.01        1 1973",
        "X20.01 1 1973Y",
        "20.O1.197B",
    ],
)
def test_birth_date_ocr_keeps_gap_boundaries_and_error_budget(text: str) -> None:
    catalog = ObjectCatalog(people=(Person("p", birth_date=date(1973, 1, 20)),))
    result = build_handler().handle(MarkOccurrences(SourceText(text), catalog))
    assert not result.occurrences


def test_other_date_fields_remain_exact_or_normalized() -> None:
    catalog = ObjectCatalog(
        documents=(Document("d", issue_date=date(1973, 1, 20)),),
        miscellaneous=(
            Misc(
                "m",
                incoming_letter_date=date(1973, 1, 20),
                preliminary_response_due_date=date(1973, 1, 20),
            ),
        ),
    )
    result = build_handler().handle(MarkOccurrences(SourceText("20.01 1 1973"), catalog))
    assert not result.occurrences


@pytest.mark.parametrize("command", ["mark", "mark-batch"])
@pytest.mark.parametrize("options", [[], ["--disable-fuzzy"], ["--max-errors", "0"]])
def test_cli_repeated_exact_and_ocr_birth_dates(
    tmp_path: Path, command: str, options: list[str]
) -> None:
    text = "😀\r\n20.01.1973; 20.01 1 1973; 20.01 1 1973."
    (tmp_path / "v.txt").write_bytes(text.encode("utf-8"))
    if command == "mark":
        objects = tmp_path / "objects.json"
        objects.write_text(json.dumps({"people": [{"id": "p", "birth_date": "1973-01-20"}]}))
        args = [command, "--objects", str(objects), "--text", str(tmp_path / "v.txt")]
    else:
        batch = tmp_path / "input.csv"
        with batch.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["versionId", "Субъект страхования ФЛ"], delimiter=";"
            )
            writer.writeheader()
            writer.writerow(
                {
                    "versionId": "v",
                    "Субъект страхования ФЛ": json.dumps([{"Дата рождения": "1973-01-20"}]),
                }
            )
        args = [command, "--input", str(batch), "--txts-dir", str(tmp_path)]
    evidence_path = tmp_path / "evidence.json"
    result = CliRunner().invoke(app, [*args, *options, "--evidence-output", str(evidence_path)])
    assert result.exit_code == 0, result.output
    task = json.loads(result.stdout)[0]
    report = json.loads(evidence_path.read_text())
    if command == "mark-batch":
        report = report[0]
    regions = task["predictions"][0]["result"]
    expected = ["20.01.1973"] + ([] if options else ["20.01 1 1973", "20.01 1 1973"])
    assert [r["value"]["text"] for r in regions] == expected
    assert [o["method"] for o in report["occurrences"]] == ["exact"] + (
        [] if options else ["bitap", "bitap"]
    )
    assert len({r["id"] for r in regions}) == len(expected)
    for region, occurrence in zip(regions, report["occurrences"], strict=True):
        value = region["value"]
        assert value["labels"] == ["PERSON_BIRTH_DATE"]
        assert text[value["start"] : value["end"]] == value["text"]
        assert (occurrence["start"], occurrence["end"]) == (value["start"], value["end"])
        assert occurrence["region_id"] == region["id"]


def test_birth_date_minimum_fuzzy_length_is_respected() -> None:
    catalog = ObjectCatalog(people=(Person("p", birth_date=date(1973, 1, 20)),))
    result = build_handler(MatchingConfig(min_fuzzy_pattern_length=11)).handle(
        MarkOccurrences(SourceText("20.01 1 1973"), catalog)
    )
    assert not result.occurrences
