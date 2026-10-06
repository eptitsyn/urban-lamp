import json
import logging
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from entity_marker.application.mark_occurrences import MarkOccurrences
from entity_marker.bootstrap import build_handler
from entity_marker.domain.models.text import SourceText
from entity_marker.domain.policies.matching import MatchingConfig
from entity_marker.infrastructure.serialization.batch_input import read_batch_rows
from entity_marker.infrastructure.serialization.evidence_report import export_evidence
from entity_marker.infrastructure.serialization.files import read_utf8, write_utf8_atomic
from entity_marker.infrastructure.serialization.input_dto import parse_objects
from entity_marker.infrastructure.serialization.label_studio import export_predictions

app = typer.Typer(help="Mark known entity occurrences for Label Studio.")


class OutputFormat(StrEnum):
    LABEL_STUDIO = "label-studio"
    OCCURRENCES = "occurrences"


def configure_logging(verbosity: int) -> None:
    logger = logging.getLogger("entity_marker")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(
        logging.DEBUG if verbosity >= 2 else logging.INFO if verbosity else logging.WARNING
    )


@app.command()
def mark(
    objects: Annotated[Path, typer.Option(help="Predefined objects JSON file.")],
    text: Annotated[Path | None, typer.Option(help="UTF-8 text; defaults to stdin.")] = None,
    output: Annotated[Path | None, typer.Option(help="Output JSON; defaults to stdout.")] = None,
    evidence_output: Annotated[
        Path | None, typer.Option(help="Entity links and resolution report.")
    ] = None,
    max_errors: Annotated[
        int, typer.Option(min=0, help="Global ceiling on field edit budgets.")
    ] = 1,
    disable_fuzzy: Annotated[
        bool, typer.Option(help="Keep exact and normalized matching only.")
    ] = False,
    pretty: Annotated[bool, typer.Option(help="Indent output JSON.")] = False,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format.")
    ] = OutputFormat.LABEL_STUDIO,
    verbose: Annotated[
        int, typer.Option("--verbose", "-v", count=True, help="-v summary; -vv decisions.")
    ] = 0,
) -> None:
    """Detect known entities using exact, normalized, and Bitap matching."""
    configure_logging(verbose)
    try:
        inputs = {objects.resolve()}
        if text is not None:
            inputs.add(text.resolve())
        destinations = [path.resolve() for path in (output, evidence_output) if path is not None]
        if len(set(destinations)) != len(destinations) or any(
            path in inputs for path in destinations
        ):
            raise ValueError("Output paths must differ from input paths and from each other")
        catalog = parse_objects(read_utf8(objects))
        if text is None and sys.stdin.isatty():
            raise ValueError("Supply --text or pipe UTF-8 text through stdin")
        content = read_utf8(text) if text is not None else sys.stdin.buffer.read().decode("utf-8")
        if not content:
            raise ValueError("Input text must not be empty")
        source = SourceText(content)
        config = MatchingConfig(fuzzy_enabled=not disable_fuzzy, max_errors=max_errors)
        result = build_handler(config).handle(MarkOccurrences(source, catalog))
        payload = (
            export_predictions(source, result.occurrences, pretty=pretty)
            if output_format == OutputFormat.LABEL_STUDIO
            else export_evidence(result, pretty=pretty)
        )
        if evidence_output is not None:
            write_utf8_atomic(evidence_output, export_evidence(result, pretty=pretty))
        if output is None:
            typer.echo(payload)
        else:
            write_utf8_atomic(output, payload)
        logging.getLogger("entity_marker").info(
            "Accepted %d occurrences; rejected %d candidates",
            len(result.occurrences),
            len(result.rejected),
        )
    except (ValueError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def mark_batch(
    inputs: Annotated[
        list[Path], typer.Option("--input", help="Semicolon CSV export; repeat for multiple files.")
    ],
    txts_dir: Annotated[
        Path | None,
        typer.Option(help="Folder of <versionId>.txt files; defaults to txts beside each CSV."),
    ] = None,
    output: Annotated[Path | None, typer.Option(help="Output JSON; defaults to stdout.")] = None,
    evidence_output: Annotated[
        Path | None, typer.Option(help="Per-row entity links and resolution reports.")
    ] = None,
    max_errors: Annotated[
        int, typer.Option(min=0, help="Global ceiling on field edit budgets.")
    ] = 1,
    disable_fuzzy: Annotated[
        bool, typer.Option(help="Keep exact and normalized matching only.")
    ] = False,
    pretty: Annotated[bool, typer.Option(help="Indent output JSON.")] = False,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format.")
    ] = OutputFormat.LABEL_STUDIO,
    verbose: Annotated[
        int, typer.Option("--verbose", "-v", count=True, help="-v summary; -vv decisions.")
    ] = 0,
) -> None:
    """Match each CSV row against txts/<versionId>.txt using only that row's objects."""
    configure_logging(verbose)
    try:
        rows = read_batch_rows(inputs, txts_dir)
        input_paths = {path.resolve() for path in inputs}
        input_paths.update(row.text_path.resolve() for row in rows)
        destinations = [path.resolve() for path in (output, evidence_output) if path is not None]
        if len(set(destinations)) != len(destinations) or any(
            path in input_paths for path in destinations
        ):
            raise ValueError("Output paths must differ from input paths and from each other")
        handler = build_handler(
            MatchingConfig(fuzzy_enabled=not disable_fuzzy, max_errors=max_errors)
        )
        tasks = []
        reports = []
        skipped = 0
        for row in rows:
            try:
                try:
                    content = read_utf8(row.text_path)
                except FileNotFoundError:
                    skipped += 1
                    logging.getLogger("entity_marker").warning(
                        "%s: skipping row; text file not found: %s", row.context, row.text_path
                    )
                    continue
                if not content:
                    raise ValueError("Input text must not be empty")
                source = SourceText(content)
                result = handler.handle(MarkOccurrences(source, row.catalog))
            except (ValueError, OSError) as exc:
                raise ValueError(f"{row.context}: {exc}") from exc
            if output_format == OutputFormat.LABEL_STUDIO:
                task = json.loads(export_predictions(source, result.occurrences))[0]
                task["data"].update(row.metadata)
                tasks.append(task)
            if evidence_output is not None or output_format == OutputFormat.OCCURRENCES:
                reports.append({**row.metadata, **json.loads(export_evidence(result))})
            logging.getLogger("entity_marker").info(
                "%s: accepted %d occurrences; rejected %d candidates",
                row.context,
                len(result.occurrences),
                len(result.rejected),
            )
        payload = json.dumps(
            tasks if output_format == OutputFormat.LABEL_STUDIO else reports,
            ensure_ascii=False,
            indent=2 if pretty else None,
        )
        if evidence_output is not None:
            write_utf8_atomic(
                evidence_output,
                json.dumps(reports, ensure_ascii=False, indent=2 if pretty else None),
            )
        if output is None:
            typer.echo(payload)
        else:
            write_utf8_atomic(output, payload)
        logging.getLogger("entity_marker").info(
            "Processed %d CSV rows; skipped %d missing text files", len(rows) - skipped, skipped
        )
    except (ValueError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def validate(objects: Annotated[Path, typer.Option(help="Predefined objects JSON file.")]) -> None:
    """Validate the schema and entity IDs without matching."""
    try:
        parse_objects(read_utf8(objects))
    except (ValueError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo("Objects are valid.")
