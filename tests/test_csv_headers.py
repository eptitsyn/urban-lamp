import csv
import json
from pathlib import Path

import pytest

from entity_marker.infrastructure.serialization.batch_input import catalog_from_row, read_batch_rows

# Explicit pairs keep this fixture independent of the implementation's alias table.
FIELDS = [
    (
        "InsuranceSubjects",
        "Субъект страхования ФЛ",
        json.dumps(
            [
                {
                    "Фамилия": "Иванов",
                    "Имя": "Иван",
                    "Отчество": "Иванович",
                    "Дата рождения": "1985-05-15",
                    "Предыдущая фамилия": "Петров",
                    "Удостоверение личности": "Паспорт",
                    "Серия документа": "0001",
                    "Номер документа": "000002",
                }
            ]
        ),
    ),
    (
        "InsuranceSubjectsOrganization",
        "Субъект страхования ЮЛ",
        json.dumps(
            [
                {"ИНН": "0000000000", "Полное наименование": 'ООО "Ромашка"'},
            ]
        ),
    ),
    (
        "InsuranceSubjectsVehicle",
        "Субъект страхования ТС",
        json.dumps(
            [
                {"VIN": "ZZZ9999999999999", "Гос. номер": "А123ВС77"},
            ]
        ),
    ),
    ("PartnerKindName", "Вид контрагента", "ЮЛ"),
    ("PartnerName", "Контрагент", "ООО Б"),
    ("SignerName", "ФИО подписанта документа", "Иванов Иван Иванович"),
    ("Sender", "Отправитель", "Петров Петр Петрович"),
    ("SignerPosition", "Должность", "Директор"),
    ("OutgoingOrganizationEmail", "Email отправителя", "sender@example.com"),
    ("SenderAddress", "Адрес отправителя", "Москва"),
    ("FullNumber", "Порядковый номер", "000123"),
    ("CourtCase", "№ дела", "А53-00001/2026"),
    ("RegDate", "Дата регистрации", "04.08.2025"),
    ("AnswerDeadline", "Срок предоставления ответа", "10.08.2025 03:00:00"),
    ("EmailForAnswer", "Email для ответа", "reply@example.com"),
    ("AddressForAnswer", "Адрес для ответа", "Тула"),
]


@pytest.mark.parametrize("delimiter", [",", ";"])
@pytest.mark.parametrize("english", [True, False])
def test_header_formats_produce_same_catalog(tmp_path: Path, delimiter: str, english: bool) -> None:
    row = {"versionId": "001", "cardId": "002", "fileId": "003", "fileName": "test.pdf"}
    row.update({en if english else ru: value for en, ru, value in FIELDS})
    path = tmp_path / "input.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(row), delimiter=delimiter, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerow(row)
    (result,) = read_batch_rows([path])
    assert result.catalog == catalog_from_row({ru: value for _, ru, value in FIELDS})
    assert result.version_id == "001"
    assert result.identifiers == {"cardId": "002", "fileId": "003", "fileName": "test.pdf"}
    assert len(result.catalog.people) == len(result.catalog.documents) == 1
    assert len(result.catalog.cars) == len(result.catalog.legal_entities) == 1


@pytest.mark.parametrize("column", ["Sender", "PartnerName"])
def test_english_sender_fallback(column: str) -> None:
    assert catalog_from_row({column: "Иванов"}).senders[0].full_name == "Иванов"


@pytest.mark.parametrize("legacy", ["", " ", " Иванов "])
def test_mixed_headers_accept_empty_or_matching_aliases(legacy: str) -> None:
    catalog = catalog_from_row({"Sender": "Иванов", "Отправитель": legacy})
    assert catalog.senders[0].full_name == "Иванов"


def test_conflicting_headers_report_row_context(tmp_path: Path) -> None:
    path = tmp_path / "conflict.csv"
    path.write_text("versionId,Sender,Отправитель\nv,Иванов,Петров\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row 2: Conflicting CSV columns: Sender and Отправитель"):
        read_batch_rows([path])


def test_invalid_json_in_english_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        catalog_from_row({"InsuranceSubjects": "not JSON"})
