import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.cli.app import app
from entity_marker.domain.models.entities import Car, ObjectCatalog
from entity_marker.domain.models.text import SourceText

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("args", "description"),
    [
        (
            ["mark", "--objects", "examples/objects.json", "--text", "examples/input.txt"],
            "Matching aliases",
        ),
        (["mark-batch", "--input", "examples/batch/input.csv"], "Processing CSV rows"),
    ],
)
@pytest.mark.parametrize("option", ["--progress", "--no-progress", None])
def test_progress_keeps_json_stdout_clean(
    monkeypatch: pytest.MonkeyPatch, args: list[str], description: str, option: str | None
) -> None:
    monkeypatch.chdir(ROOT)
    result = runner.invoke(app, [*args, *([option] if option else [])])
    assert result.exit_code == 0, result.output
    assert isinstance(json.loads(result.stdout), list)
    if option == "--progress":
        assert description in result.stderr
        assert "100%" in result.stderr
        assert "ETA" in result.stderr
    else:
        assert not result.stderr


def test_skipped_rows_advance_progress(tmp_path: Path) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("versionId\nmissing\nmissing-too\n", encoding="utf-8")
    result = runner.invoke(app, ["mark-batch", "--input", str(csv), "--progress"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
    assert "2/2" in result.stderr
    assert "100%" in result.stderr


@pytest.mark.parametrize("catalog", [ObjectCatalog(), ObjectCatalog(cars=(Car("c", "VIN"),))])
def test_progress_callback_preserves_matching(catalog: ObjectCatalog) -> None:
    handler = build_handler()
    command = MarkOccurrences(SourceText("VIN"), catalog)
    updates: list[tuple[int, int]] = []
    result = handler.handle(command, lambda completed, total: updates.append((completed, total)))
    assert result == handler.handle(command)
    total = updates[-1][1]
    assert updates == [(completed, total) for completed in range(total + 1)]
