"""Adapt semicolon CSV exports to the existing, code-defined object catalog."""

import csv
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from entity_marker.domain.models.entities import ObjectCatalog
from entity_marker.infrastructure.serialization.input_dto import ObjectCatalogDTO

PEOPLE = "Субъект страхования ФЛ"
LEGAL_ENTITIES = "Субъект страхования ЮЛ"
CARS = "Субъект страхования ТС"


@dataclass(frozen=True)
class BatchRow:
    csv_path: Path
    row_number: int
    version_id: str
    text_path: Path
    catalog: ObjectCatalog
    identifiers: dict[str, str]

    @property
    def context(self) -> str:
        return f"{self.csv_path}: row {self.row_number} (versionId={self.version_id})"

    @property
    def metadata(self) -> dict[str, object]:
        return {
            **self.identifiers,
            "versionId": self.version_id,
            "source_csv": str(self.csv_path),
            "source_row": self.row_number,
            "text_file": str(self.text_path),
        }


def _value(record: dict[str, object], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key}: expected a string or null")
    return value.strip() or None


def _objects(row: dict[str, str], column: str) -> list[dict[str, object]]:
    raw = row.get(column, "").strip()
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{column}: invalid JSON: {exc}") from exc
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError(f"{column}: expected a JSON array of objects")
    return values


def _mapped(record: dict[str, object], entity_id: str, fields: dict[str, str]) -> dict[str, object]:
    return {"id": entity_id, **{target: _value(record, key) for key, target in fields.items()}}


def _date(value: str | None) -> str | None:
    if value is None:
        return None
    # The export includes time of day for deadlines; the domain stores calendar dates.
    for pattern in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return value


def catalog_from_row(row: dict[str, str]) -> ObjectCatalog:
    people = []
    documents = []
    for index, person in enumerate(_objects(row, PEOPLE), 1):
        people.append(
            _mapped(
                person,
                f"person-{index}",
                {
                    "Фамилия": "last_name",
                    "Имя": "first_name",
                    "Отчество": "middle_name",
                    "Дата рождения": "birth_date",
                    "Предыдущая фамилия": "previous_last_name",
                },
            )
        )
        document = _mapped(
            person,
            f"person-{index}-document",
            {
                "Удостоверение личности": "document_type",
                "Серия документа": "series",
                "Номер документа": "number",
            },
        )
        if any(value is not None for key, value in document.items() if key != "id"):
            documents.append(document)
    cars = [
        _mapped(
            car,
            f"car-{index}",
            {
                "VIN": "vin",
                "Гос. номер": "license_plate",
                "Номер кузова": "body_number",
                "Номер шасси": "chassis_number",
            },
        )
        for index, car in enumerate(_objects(row, CARS), 1)
    ]
    legal_entities = [
        {
            "id": f"legal-entity-{index}",
            "inn": _value(entity, "ИНН"),
            "name": _value(entity, "Полное наименование") or _value(entity, "Краткое наименование"),
        }
        for index, entity in enumerate(_objects(row, LEGAL_ENTITIES), 1)
    ]
    record: dict[str, object] = dict(row)
    sender = _mapped(
        record,
        "sender-1",
        {
            "Должность": "position",
            "Email отправителя": "email",
            "Адрес отправителя": "return_address",
        },
    )
    is_organization = _value(record, "Вид контрагента") == "ЮЛ"
    sender["full_name"] = (
        _value(record, "ФИО подписанта документа")
        or _value(record, "Отправитель")
        or (None if is_organization else _value(record, "Контрагент"))
    )
    sender["organization_name"] = _value(record, "Контрагент") if is_organization else None
    misc = _mapped(
        record,
        "misc-1",
        {
            "Порядковый номер": "incoming_letter_number",
            "№ дела": "case_number",
            "Email для ответа": "reply_email",
            "Адрес для ответа": "reply_address",
        },
    )
    misc["incoming_letter_date"] = _date(_value(record, "Дата регистрации"))
    misc["preliminary_response_due_date"] = _date(_value(record, "Срок предоставления ответа"))
    return ObjectCatalogDTO.model_validate(
        {
            "people": people,
            "documents": documents,
            "cars": cars,
            "legal_entities": legal_entities,
            "senders": [sender]
            if any(v is not None for k, v in sender.items() if k != "id")
            else [],
            "miscellaneous": [misc]
            if any(v is not None for k, v in misc.items() if k != "id")
            else [],
        }
    ).to_domain()


@contextmanager
def _large_csv_fields() -> Iterator[None]:
    # Exports can contain large JSON arrays or correspondence text in a single cell.
    previous = csv.field_size_limit()
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            # Some platforms use a smaller C integer for the CSV parser's limit.
            limit //= 10
    try:
        yield
    finally:
        csv.field_size_limit(previous)


def read_batch_rows(paths: list[Path], txts_dir: Path | None = None) -> list[BatchRow]:
    rows = []
    for path in paths:
        text_root = (txts_dir if txts_dir is not None else path.parent / "txts").resolve()
        try:
            with _large_csv_fields(), path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, delimiter=";", strict=True)
                fields = reader.fieldnames
                if not fields or "versionId" not in fields:
                    raise ValueError("CSV header must contain versionId")
                if len(fields) != len(set(fields)) or any(not name for name in fields):
                    raise ValueError("CSV column names must be nonempty and unique")
                count = 0
                for number, row in enumerate(reader, 2):
                    count += 1
                    try:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError(
                                "CSV row has a different number of cells than the header"
                            )
                        version_id = row["versionId"].strip()
                        if (
                            not version_id
                            or version_id in {".", ".."}
                            or any(c in version_id for c in "/\\")
                            or any(ord(c) < 32 for c in version_id)
                        ):
                            raise ValueError("versionId must be a nonempty filename component")
                        text_path = text_root / f"{version_id}.txt"
                        if text_path.resolve().parent != text_root:
                            raise ValueError("Text file must resolve inside the txts directory")
                        rows.append(
                            BatchRow(
                                path,
                                number,
                                version_id,
                                text_path,
                                catalog_from_row(row),
                                {
                                    key: row[key]
                                    for key in ("cardId", "fileId", "fileName")
                                    if row.get(key)
                                },
                            )
                        )
                    except ValueError as exc:
                        raise ValueError(f"row {number}: {exc}") from exc
                if not count:
                    raise ValueError("CSV must contain at least one data row")
        except (ValueError, OSError, csv.Error) as exc:
            raise ValueError(f"{path}: {exc}") from exc
    return rows
