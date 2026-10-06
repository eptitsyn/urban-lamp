import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.cli.app import app
from entity_marker.domain.models.text import TextSpan
from entity_marker.infrastructure.matching.exact import ExactMatcher

runner = CliRunner()


def catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "objects.json"
    path.write_text(
        json.dumps({"cars": [{"id": "c1", "license_plate": "А123ВС77"}]}), encoding="utf-8"
    )
    return path


def test_cli_file_export_preserves_original_offsets(tmp_path: Path) -> None:
    objects = catalog_file(tmp_path)
    text = tmp_path / "input.txt"
    original = "Авто\r\nА123ВС77 и А123ВС77"
    text.write_bytes(original.encode("utf-8"))
    output = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "mark",
            "--objects",
            str(objects),
            "--text",
            str(text),
            "--output",
            str(output),
            "--pretty",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    task = json.loads(output.read_text(encoding="utf-8"))[0]
    assert task["data"]["text"] == original
    regions = task["predictions"][0]["result"]
    assert len(regions) == 2
    for region in regions:
        value = region["value"]
        assert original[value["start"] : value["end"]] == value["text"] == "А123ВС77"
        assert value["labels"] == ["CAR_LICENSE_PLATE"]
        assert region["from_name"] == "entities"


def test_stdin_and_deterministic_json(tmp_path: Path) -> None:
    args = ["mark", "--objects", str(catalog_file(tmp_path))]
    first = runner.invoke(app, args, input="А123ВС77")
    second = runner.invoke(app, args, input="А123ВС77")
    assert first.exit_code == second.exit_code == 0
    assert first.stdout == second.stdout
    assert len(json.loads(first.stdout)[0]["predictions"][0]["result"]) == 1


def test_empty_input_is_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["mark", "--objects", str(catalog_file(tmp_path))], input="")
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Input text must not be empty" in result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '{"cars":[{"id":"c1","unexpected":true}]}',
        '{"cars":[{"id":"c1"},{"id":"c1"}]}',
        '{"people":[{"id":" "}]}',
    ],
)
def test_invalid_objects(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(payload, encoding="utf-8")
    result = runner.invoke(app, ["validate", "--objects", str(path)])
    assert result.exit_code == 2
    assert "Error:" in result.stderr


def test_help_and_validate(tmp_path: Path) -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["mark", "--help"]).exit_code == 0
    assert runner.invoke(app, ["validate", "--objects", str(catalog_file(tmp_path))]).exit_code == 0


def test_exact_overlap_and_unicode() -> None:
    matcher = ExactMatcher()
    assert matcher.find("ааа", "аа") == [TextSpan(0, 2), TextSpan(1, 3)]
    assert matcher.find("abc", "z") == []
    with pytest.raises(ValueError, match="empty"):
        matcher.find("abc", "")


def test_example_all_entity_types() -> None:
    root = Path(__file__).resolve().parents[1]
    result = runner.invoke(
        app,
        [
            "mark",
            "--objects",
            str(root / "examples/objects.json"),
            "--text",
            str(root / "examples/input.txt"),
        ],
    )
    assert result.exit_code == 0, result.output
    regions = json.loads(result.stdout)[0]["predictions"][0]["result"]
    assert len(regions) == 6
    assert {r["value"]["labels"][0] for r in regions} == {
        "PERSON_FIRST_NAME",
        "PERSON_LAST_NAME",
        "CAR_VIN",
        "CAR_LICENSE_PLATE",
        "DOCUMENT_NUMBER",
    }
