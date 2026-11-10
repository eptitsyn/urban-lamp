import json
from collections.abc import Sequence

from entity_marker.domain.models.matches import ObjectOccurrence
from entity_marker.domain.models.text import SourceText


def export_predictions(
    source: SourceText, occurrences: Sequence[ObjectOccurrence], *, pretty: bool = False
) -> str:
    return _export_tasks(source, occurrences, annotations=False, pretty=pretty)


def export_annotations(
    source: SourceText, occurrences: Sequence[ObjectOccurrence], *, pretty: bool = False
) -> str:
    return _export_tasks(source, occurrences, annotations=True, pretty=pretty)


def _export_tasks(
    source: SourceText,
    occurrences: Sequence[ObjectOccurrence],
    *,
    annotations: bool,
    pretty: bool,
) -> str:
    results = [
        {
            "id": f"r{index:06d}",
            "from_name": "entities",
            "to_name": "text",
            "type": "labels",
            "value": {
                "start": item.span.start,
                "end": item.span.end,
                "text": item.matched_text,
                "labels": [f"{item.entity_type.value}_{item.field_name}".upper()],
            },
        }
        for index, item in enumerate(occurrences, start=1)
    ]
    return json.dumps(
        [
            {
                "data": {"text": source.text},
                ("annotations" if annotations else "predictions"): [
                    {"result": results}
                    if annotations
                    else {"model_version": "entity-marker-0.4-domain-schema", "result": results}
                ],
            }
        ],
        ensure_ascii=False,
        indent=2 if pretty else None,
    )
