import json
from collections.abc import Sequence

from entity_marker.domain.models.matches import ObjectOccurrence
from entity_marker.domain.models.text import SourceText


def export_predictions(
    source: SourceText, occurrences: Sequence[ObjectOccurrence], *, pretty: bool = False
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
                "predictions": [
                    {"model_version": "entity-marker-0.4-domain-schema", "result": results}
                ],
            }
        ],
        ensure_ascii=False,
        indent=2 if pretty else None,
    )
