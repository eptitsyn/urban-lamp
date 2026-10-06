import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.cli.app import app
from entity_marker.domain.models.text import SourceText
from entity_marker.infrastructure.serialization.input_dto import parse_objects

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("command", ["mark", "mark-batch"])
@pytest.mark.parametrize("fuzzy", [False, True])
@pytest.mark.parametrize("year", ["25", "2025"])
def test_repeated_case_numbers_and_emails_keep_separate_regions(
    tmp_path: Path, command: str, fuzzy: bool, year: str
) -> None:
    case_number = f"A41-20769/{year}"
    email = "reply@example.org"
    mentions = ["A41-20769/2025", email, "a41 - 20769 / 25", "REPLY@EXAMPLE.ORG", "A41-20769/25"]
    text = "😀\r\n" + "\r\nПовторное упоминание: ".join(mentions)
    text_path = tmp_path / "v.txt"
    text_path.write_bytes(text.encode("utf-8"))
    if command == "mark":
        objects = tmp_path / "objects.json"
        objects.write_text(
            json.dumps(
                {"miscellaneous": [{"id": "m", "case_number": case_number, "reply_email": email}]}
            ),
            encoding="utf-8",
        )
        args = [command, "--objects", str(objects), "--text", str(text_path)]
    else:
        batch = tmp_path / "input.csv"
        with batch.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["versionId", "№ дела", "Email для ответа"], delimiter=";"
            )
            writer.writeheader()
            writer.writerow({"versionId": "v", "№ дела": case_number, "Email для ответа": email})
        args = [command, "--input", str(batch), "--txts-dir", str(tmp_path)]
    evidence_path = tmp_path / "evidence.json"
    args.extend(["--evidence-output", str(evidence_path)])
    if not fuzzy:
        args.append("--disable-fuzzy")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    task = json.loads(result.stdout)[0]
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    if command == "mark-batch":
        report = report[0]
    regions = task["predictions"][0]["result"]
    assert task["data"]["text"] == text
    assert [r["value"]["text"] for r in regions] == mentions
    assert [r["value"]["labels"] for r in regions] == [
        ["MISC_CASE_NUMBER"],
        ["MISC_REPLY_EMAIL"],
        ["MISC_CASE_NUMBER"],
        ["MISC_REPLY_EMAIL"],
        ["MISC_CASE_NUMBER"],
    ]
    assert len({r["id"] for r in regions}) == len(mentions)
    assert [o["method"] for o in report["occurrences"]] == [
        "exact",
        "exact",
        "normalized",
        "normalized",
        "exact",
    ]
    offset = 0
    for region, occurrence, mention in zip(regions, report["occurrences"], mentions, strict=True):
        start = text.index(mention, offset)
        end = start + len(mention)
        assert (region["value"]["start"], region["value"]["end"]) == (start, end)
        assert (occurrence["start"], occurrence["end"]) == (start, end)
        assert occurrence["region_id"] == region["id"]
        offset = end


@pytest.mark.parametrize(
    ("objects", "source"),
    [
        ("objects.json", "input.txt"),
        ("real_objects.json", "real_text.txt"),
        ("morphology_objects.json", "morphology.txt"),
    ],
)
def test_all_example_labels_survive_repeated_passages(objects: str, source: str) -> None:
    catalog = parse_objects((ROOT / "examples" / objects).read_text(encoding="utf-8"))
    passage = (ROOT / "examples" / source).read_text(encoding="utf-8")
    handler = build_handler()
    single = handler.handle(MarkOccurrences(SourceText(passage), catalog))
    assert single.occurrences
    separator = "\n" + "—" * 100 + "\n"
    text = separator.join([passage] * 3)
    repeated = handler.handle(MarkOccurrences(SourceText(text), catalog))
    assert [
        (o.entity_type, o.entity_id, o.field_name, o.span.start, o.span.end, o.matched_text)
        for o in repeated.occurrences
    ] == [
        (
            o.entity_type,
            o.entity_id,
            o.field_name,
            o.span.start + index * (len(passage) + len(separator)),
            o.span.end + index * (len(passage) + len(separator)),
            o.matched_text,
        )
        for index in range(3)
        for o in single.occurrences
    ]
