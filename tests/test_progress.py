import json
from io import StringIO
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.cli.app import app
from entity_marker.cli.progress import processing_progress
from entity_marker.domain.models.entities import Car, ObjectCatalog
from entity_marker.domain.models.text import SourceText

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_nonterminal_progress_is_visible_before_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = StringIO()
    monkeypatch.setattr("sys.stderr", stream)
    now = [0.0]
    monkeypatch.setattr("entity_marker.cli.progress.monotonic", lambda: now[0])
    display = processing_progress(None, output_file=True)
    display.live.auto_refresh = False
    with display:
        task = display.add_task("Processing", total=10)
        assert "0%" in stream.getvalue()
        stream.seek(0)
        stream.truncate()
        now[0] = 2.0
        display.update(task, completed=3, refresh=True)
        assert "30%" in stream.getvalue()
        assert "ETA" in stream.getvalue()
        assert "100%" not in stream.getvalue()
        assert "\x1b" not in stream.getvalue()


def test_loading_is_visible_before_csv_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_read(*args: object) -> None:
        import sys

        assert "Loading CSV rows" in sys.stderr.buffer.getvalue().decode()  # type: ignore[attr-defined]
        raise ValueError("invalid input")

    monkeypatch.setattr("entity_marker.cli.app.read_batch_rows", fail_read)
    result = runner.invoke(
        app, ["mark-batch", "--input", "unused.csv", "--output", str(tmp_path / "out.json")]
    )
    assert result.exit_code == 2, result.output
    assert "invalid input" in result.stderr


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
@pytest.mark.parametrize("output_file", [False, True])
def test_progress_keeps_json_stdout_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    args: list[str],
    description: str,
    option: str | None,
    output_file: bool,
) -> None:
    monkeypatch.chdir(ROOT)
    output = tmp_path / "predictions.json"
    result = runner.invoke(
        app,
        [*args, *([option] if option else []), *(["--output", str(output)] if output_file else [])],
    )
    assert result.exit_code == 0, result.output
    if output_file:
        assert not result.stdout
        assert isinstance(json.loads(output.read_text()), list)
    else:
        assert isinstance(json.loads(result.stdout), list)
    if option == "--progress" or (option is None and output_file):
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
