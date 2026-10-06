import json
from pathlib import Path
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from entity_marker.cli.app import app

runner = CliRunner()


def files(tmp_path: Path) -> tuple[Path, Path]:
    objects = tmp_path / "objects.json"
    objects.write_text(
        json.dumps(
            {"cars": [{"id": "c1", "vin": "X7LHSRDVN12345678", "license_plate": "А123ВС77"}]}
        ),
        encoding="utf-8",
    )
    text = tmp_path / "input.txt"
    text.write_text("😀 А 123 ВС 77 и X7LHSR0VN12345678", encoding="utf-8")
    return objects, text


def test_report_region_links_and_json_only_stdout(tmp_path: Path) -> None:
    objects, text = files(tmp_path)
    report = tmp_path / "evidence.json"
    result = runner.invoke(
        app,
        [
            "mark",
            "--objects",
            str(objects),
            "--text",
            str(text),
            "--evidence-output",
            str(report),
            "-vv",
        ],
    )
    assert result.exit_code == 0, result.output
    task = json.loads(result.stdout)[0]
    evidence = json.loads(report.read_text())
    regions = task["predictions"][0]["result"]
    assert len(regions) == len(evidence["occurrences"]) == 2
    for region, occurrence in zip(regions, evidence["occurrences"], strict=True):
        assert region["id"] == occurrence["region_id"]
        assert occurrence["entity_id"] == "c1"
        assert (
            task["data"]["text"][occurrence["start"] : occurrence["end"]]
            == occurrence["matched_text"]
        )
        assert region["value"]["text"] == occurrence["matched_text"]
    assert "Candidate:" in result.stderr
    assert "Accepted 2" in result.stderr


@pytest.mark.parametrize("options", [["--disable-fuzzy"], ["--max-errors", "0"]])
def test_cli_fuzzy_switches(tmp_path: Path, options: list[str]) -> None:
    objects, text = files(tmp_path)
    result = runner.invoke(
        app,
        [
            "mark",
            "--objects",
            str(objects),
            "--text",
            str(text),
            "--format",
            "occurrences",
            *options,
        ],
    )
    assert result.exit_code == 0, result.output
    occurrences = json.loads(result.stdout)["occurrences"]
    assert len(occurrences) == 1
    assert occurrences[0]["method"] == "normalized"


def test_negative_budget_and_missing_file(tmp_path: Path) -> None:
    objects, text = files(tmp_path)
    for options in (["--max-errors", "-1"], ["--text", str(tmp_path / "missing")]):
        result = runner.invoke(app, ["mark", "--objects", str(objects), *options])
        assert result.exit_code == 2
        assert not result.stdout


def test_output_cannot_overwrite_inputs(tmp_path: Path) -> None:
    objects, text = files(tmp_path)
    original = text.read_bytes()
    result = runner.invoke(
        app, ["mark", "--objects", str(objects), "--text", str(text), "--output", str(text)]
    )
    assert result.exit_code == 2
    assert text.read_bytes() == original


def test_bad_utf8_and_missing_output_directory(tmp_path: Path) -> None:
    objects, text = files(tmp_path)
    text.write_bytes(b"\xff")
    result = runner.invoke(app, ["mark", "--objects", str(objects), "--text", str(text)])
    assert result.exit_code == 2
    text.write_text("А123ВС77")
    result = runner.invoke(
        app,
        [
            "mark",
            "--objects",
            str(objects),
            "--text",
            str(text),
            "--output",
            str(tmp_path / "missing" / "out.json"),
        ],
    )
    assert result.exit_code == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_label_config_covers_generated_aliases() -> None:
    from datetime import date

    from entity_marker.domain.aliases.generators import generate_aliases
    from entity_marker.domain.models.entities import Car, Document, ObjectCatalog, Person

    root = Path(__file__).resolve().parents[1]
    labels = {
        label.attrib["value"]
        for label in ElementTree.parse(root / "examples/labeling_config.xml").iter("Label")
    }
    aliases = generate_aliases(
        ObjectCatalog(
            people=(Person("p", "Иван", "Иванов", "Иванович", date(2000, 1, 1)),),
            cars=(Car("c", "VIN", "PLATE", "BODY", "CHASSIS"),),
            documents=(Document("d", "passport", "SERIES", "NUMBER", date(2000, 1, 1)),),
        )
    )
    assert {f"{alias.entity_type.value}_{alias.field_name}".upper() for alias in aliases} <= labels


def test_atomic_replace_cleans_temporary_file(tmp_path: Path) -> None:
    from entity_marker.infrastructure.serialization.files import write_utf8_atomic

    path = tmp_path / "result.json"
    path.write_text("old")
    write_utf8_atomic(path, '{"new": true}')
    assert json.loads(path.read_text()) == {"new": True}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result.json"]
