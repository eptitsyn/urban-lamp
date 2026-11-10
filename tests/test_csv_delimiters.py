import csv
import json
from pathlib import Path

import pytest

from entity_marker.infrastructure.serialization.batch_input import LEGAL_ENTITIES, read_batch_rows


@pytest.mark.parametrize("delimiter", [",", ";"])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_detect_delimiter_with_quoted_headers_and_json(
    tmp_path: Path, delimiter: str, encoding: str
) -> None:
    path = tmp_path / "input.csv"
    name = 'ООО "Восток, Запад; Север"\r\nфилиал'
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, delimiter=delimiter, quoting=csv.QUOTE_ALL)
        writer.writerow(["fileName", "versionId", "extra,;\r\nheader", LEGAL_ENTITIES])
        writer.writerow(
            ["report,;\r\n.pdf", "001", "", json.dumps([{"Полное наименование": name}])]
        )
    (row,) = read_batch_rows([path])
    assert row.version_id == "001"
    assert row.identifiers["fileName"] == "report,;\r\n.pdf"
    assert row.catalog.legal_entities[0].name == name


def test_detect_delimiter_independently_for_each_file(tmp_path: Path) -> None:
    paths = [tmp_path / "comma.csv", tmp_path / "semicolon.csv"]
    paths[0].write_text("versionId,fileName\none,first.pdf\n")
    paths[1].write_text("versionId;fileName\ntwo;second.pdf\n")
    rows = read_batch_rows(paths)
    assert [row.version_id for row in rows] == ["one", "two"]
    assert [row.identifiers["fileName"] for row in rows] == ["first.pdf", "second.pdf"]


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_detected_delimiter_preserves_row_validation(tmp_path: Path, delimiter: str) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(f"versionId{delimiter}fileName\nv{delimiter}file.pdf{delimiter}extra\n")
    with pytest.raises(ValueError, match="different number of cells"):
        read_batch_rows([path])


def test_single_column_header_does_not_infer_delimiter_from_data(tmp_path: Path) -> None:
    path = tmp_path / "single.csv"
    path.write_text("versionId\nv,1\n")
    assert read_batch_rows([path])[0].version_id == "v,1"
