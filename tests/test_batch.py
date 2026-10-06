import csv
import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.cli.app import app
from entity_marker.infrastructure.serialization.batch_input import (
    CARS,
    LEGAL_ENTITIES,
    PEOPLE,
    catalog_from_row,
    read_batch_rows,
)

runner = CliRunner()


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return path


def car_row(version: str, plate: str) -> dict[str, str]:
    return {"versionId": version, CARS: json.dumps([{"Гос. номер": plate}])}


def test_export_mapping_preserves_identifiers_and_empty_values() -> None:
    catalog = catalog_from_row(
        {
            PEOPLE: json.dumps(
                [
                    {
                        "Фамилия": "Иванов",
                        "Имя": "Иван",
                        "Отчество": "Иванович",
                        "Дата рождения": "1985-05-15",
                        "Серия документа": "0001",
                        "Номер документа": "000002",
                        "Удостоверение личности": "Паспорт",
                        "Страна": "РФ",
                    },
                    {"Фамилия": "Петров", "Дата рождения": None},
                ]
            ),
            CARS: json.dumps(
                [{"VIN": "ZZZ9999999999999", "Гос. номер": "AB1234CD", "Номер кузова": ""}]
            ),
            LEGAL_ENTITIES: json.dumps(
                [{"ИНН": "0000000000", "Полное наименование": " ", "Краткое наименование": "ООО А"}]
            ),
            "Вид контрагента": "ЮЛ",
            "Контрагент": "ООО Б",
            "ФИО подписанта документа": "Иванов Иван Иванович",
            "Email отправителя": "sender@example.com",
            "Дата регистрации": "04.08.2025",
            "Срок предоставления ответа": "10.08.2025 03:00:00",
            "№ дела": "А53-00001/2026",
        }
    )
    assert len(catalog.people) == 2
    assert catalog.people[0].birth_date == date(1985, 5, 15)
    assert len(catalog.documents) == 1
    assert catalog.documents[0].series == "0001"
    assert catalog.documents[0].number == "000002"
    assert catalog.cars[0].body_number is None
    assert catalog.legal_entities[0].inn == "0000000000"
    assert catalog.legal_entities[0].name == "ООО А"
    assert catalog.senders[0].organization_name == "ООО Б"
    assert catalog.senders[0].full_name == "Иванов Иван Иванович"
    assert catalog.miscellaneous[0].preliminary_response_due_date == date(2025, 8, 10)


def test_multiple_csvs_row_isolation_offsets_and_evidence(tmp_path: Path) -> None:
    txts = tmp_path / "txts"
    txts.mkdir()
    content = "😀\r\nА123ВС77 и В456ЕК99"
    for version in ("one", "two", "three"):
        (txts / f"{version}.txt").write_bytes(content.encode())
    first = write_csv(
        tmp_path / "first.csv",
        [
            {**car_row("one", "А123ВС77"), "fileName": "quoted; name\n.pdf"},
            car_row("two", "В456ЕК99"),
        ],
    )
    second = write_csv(tmp_path / "second.csv", [{"versionId": "three", CARS: "[]"}])
    evidence = tmp_path / "evidence.json"
    result = runner.invoke(
        app,
        [
            "mark-batch",
            "--input",
            str(first),
            "--input",
            str(second),
            "--evidence-output",
            str(evidence),
            "--disable-fuzzy",
            "--pretty",
            "-v",
        ],
    )
    assert result.exit_code == 0, result.output
    tasks = json.loads(result.stdout)
    reports = json.loads(evidence.read_text())
    assert [task["data"]["versionId"] for task in tasks] == ["one", "two", "three"]
    assert [task["data"]["source_row"] for task in tasks] == [2, 3, 2]
    assert tasks[0]["data"]["fileName"] == "quoted; name\n.pdf"
    for index, plate in enumerate(("А123ВС77", "В456ЕК99")):
        assert tasks[index]["data"]["text"] == content
        regions = tasks[index]["predictions"][0]["result"]
        assert len(regions) == 1
        assert regions[0]["value"]["text"] == plate
        occurrence = reports[index]["occurrences"][0]
        assert regions[0]["id"] == occurrence["region_id"]
        assert content[occurrence["start"] : occurrence["end"]] == plate
        assert reports[index]["versionId"] == tasks[index]["data"]["versionId"]
    assert tasks[2]["predictions"][0]["result"] == []
    assert "Processed 3 CSV rows" in result.stderr


def test_custom_txts_directory_and_fuzzy_options(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "input.csv", [car_row("v", "А123ВС77")])
    txts = tmp_path / "ocr"
    txts.mkdir()
    (txts / "v.txt").write_text("А123ВС78", encoding="utf-8")
    args = ["mark-batch", "--input", str(path), "--txts-dir", str(txts), "--format", "occurrences"]
    for options, expected in (([], 1), (["--disable-fuzzy"], 0), (["--max-errors", "0"], 0)):
        result = runner.invoke(app, [*args, *options])
        assert result.exit_code == 0, result.output
        assert len(json.loads(result.stdout)[0]["occurrences"]) == expected


@pytest.mark.parametrize("bad_text", [b"", b"\xff"])
def test_bad_text_does_not_write_partial_batch(tmp_path: Path, bad_text: bytes) -> None:
    path = write_csv(
        tmp_path / "input.csv", [car_row("one", "А123ВС77"), car_row("two", "В456ЕК99")]
    )
    txts = tmp_path / "txts"
    txts.mkdir()
    (txts / "one.txt").write_text("А123ВС77", encoding="utf-8")
    (txts / "two.txt").write_bytes(bad_text)
    output = tmp_path / "out.json"
    output.write_text("previous output")
    evidence = tmp_path / "evidence.json"
    result = runner.invoke(
        app,
        [
            "mark-batch",
            "--input",
            str(path),
            "--output",
            str(output),
            "--evidence-output",
            str(evidence),
        ],
    )
    assert result.exit_code == 2
    assert not result.stdout
    assert "row 3 (versionId=two)" in result.stderr
    assert output.read_text() == "previous output"
    assert not evidence.exists()


@pytest.mark.parametrize("output_format", ["label-studio", "occurrences"])
@pytest.mark.parametrize("has_text", [True, False])
def test_missing_text_rows_are_skipped(tmp_path: Path, output_format: str, has_text: bool) -> None:
    path = write_csv(
        tmp_path / "input.csv",
        [car_row("missing", "А123ВС77"), car_row("available", "В456ЕК99")],
    )
    if has_text:
        (tmp_path / "txts").mkdir()
        (tmp_path / "txts/available.txt").write_text("В456ЕК99", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    result = runner.invoke(
        app,
        [
            "mark-batch",
            "--input",
            str(path),
            "--format",
            output_format,
            "--evidence-output",
            str(evidence),
            "--disable-fuzzy",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    reports = json.loads(evidence.read_text())
    assert len(payload) == len(reports) == int(has_text)
    assert "versionId=missing" in result.stderr
    assert "skipping row; text file not found" in result.stderr
    if has_text:
        metadata = payload[0]["data"] if output_format == "label-studio" else payload[0]
        assert metadata["versionId"] == reports[0]["versionId"] == "available"
        assert reports[0]["occurrences"][0]["matched_text"] == "В456ЕК99"


@pytest.mark.parametrize("destination", ["csv", "text", "same_outputs"])
def test_batch_output_collisions(tmp_path: Path, destination: str) -> None:
    path = write_csv(tmp_path / "input.csv", [car_row("one", "А123ВС77")])
    txts = tmp_path / "txts"
    txts.mkdir()
    text = txts / "one.txt"
    text.write_text("А123ВС77", encoding="utf-8")
    before = path.read_bytes(), text.read_bytes()
    output = {"csv": path, "text": text, "same_outputs": tmp_path / "out.json"}[destination]
    args = ["mark-batch", "--input", str(path), "--output", str(output)]
    if destination == "same_outputs":
        args += ["--evidence-output", str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "Output paths must differ" in result.stderr
    assert before == (path.read_bytes(), text.read_bytes())


@pytest.mark.parametrize("version", ["", "../outside", "/outside", "a\\b", ".", ".."])
def test_unsafe_version_ids(tmp_path: Path, version: str) -> None:
    path = write_csv(tmp_path / "input.csv", [{"versionId": version}])
    with pytest.raises(ValueError, match="row 2.*versionId"):
        read_batch_rows([path])


@pytest.mark.parametrize("value", ["broken", "null", "{}", "[1]", '[{"VIN": 123}]'])
def test_invalid_entity_cells_have_row_context(tmp_path: Path, value: str) -> None:
    path = write_csv(tmp_path / "input.csv", [{"versionId": "v", CARS: value}])
    with pytest.raises(ValueError, match="row 2"):
        read_batch_rows([path])


@pytest.mark.parametrize(
    "content",
    [
        "",
        "fileId\nv\n",
        "versionId\n",
        "versionId;versionId\na;b\n",
        "versionId;fileId\na\n",
        "versionId\na;b\n",
        'versionId\n"unterminated',
    ],
)
def test_malformed_csv(tmp_path: Path, content: str) -> None:
    path = tmp_path / "input.csv"
    path.write_text(content)
    result = runner.invoke(app, ["mark-batch", "--input", str(path)])
    assert result.exit_code == 2
    assert str(path) in result.stderr
    assert not result.stdout


def test_each_csv_uses_its_own_txts_and_repeated_versions_are_independent(tmp_path: Path) -> None:
    args = ["mark-batch"]
    for name, plate in (("a", "А123ВС77"), ("b", "В456ЕК99")):
        directory = tmp_path / name
        (directory / "txts").mkdir(parents=True)
        (directory / "txts/v.txt").write_text(plate, encoding="utf-8")
        path = write_csv(directory / "input.csv", [car_row("v", plate)])
        args += ["--input", str(path)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    tasks = json.loads(result.stdout)
    assert [t["data"]["text"] for t in tasks] == ["А123ВС77", "В456ЕК99"]
    assert all(len(t["predictions"][0]["result"]) == 1 for t in tasks)


def test_text_symlink_cannot_escape_txts(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "input.csv", [{"versionId": "v"}])
    (tmp_path / "txts").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("text")
    (tmp_path / "txts/v.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="inside the txts directory"):
        read_batch_rows([path])


@pytest.mark.parametrize("column", [LEGAL_ENTITIES, "Содержание письма"])
def test_large_csv_cells_are_read_without_truncation(tmp_path: Path, column: str) -> None:
    large_value = 'Текст; "цитата"\r\n' * 20_000
    cell = (
        json.dumps([{"Полное наименование": large_value}], ensure_ascii=False)
        if column == LEGAL_ENTITIES
        else large_value
    )
    path = write_csv(tmp_path / "large.csv", [{"versionId": "v", column: cell}])
    previous = csv.field_size_limit(131072)
    try:
        rows = read_batch_rows([path])
        assert len(rows) == 1
        assert rows[0].version_id == "v"
        if column == LEGAL_ENTITIES:
            assert rows[0].catalog.legal_entities[0].name == large_value.strip()
        assert csv.field_size_limit() == 131072
    finally:
        csv.field_size_limit(previous)


def test_csv_field_limit_restored_on_failure(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "invalid.csv", [{"versionId": "../outside"}])
    previous = csv.field_size_limit()
    with pytest.raises(ValueError, match="versionId"):
        read_batch_rows([path])
    assert csv.field_size_limit() == previous
