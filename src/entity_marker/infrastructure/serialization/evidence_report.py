import json
from dataclasses import asdict

from entity_marker.domain.models.matches import MarkingResult


def export_evidence(result: MarkingResult, *, pretty: bool = False) -> str:
    occurrences = []
    for index, item in enumerate(result.occurrences, start=1):
        value = asdict(item)
        value["region_id"] = f"r{index:06d}"
        value["start"] = item.span.start
        value["end"] = item.span.end
        value.pop("span")
        value["score"] = item.score.value
        occurrences.append(value)
    return json.dumps(
        {
            "schema_version": 1,
            "offset_unit": "unicode_code_points",
            "occurrences": occurrences,
            "rejected": [asdict(decision) for decision in result.rejected],
        },
        ensure_ascii=False,
        indent=2 if pretty else None,
    )
