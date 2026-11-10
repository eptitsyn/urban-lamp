import sys

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


def processing_progress(enabled: bool | None) -> Progress:
    """Keep status on stderr and stay quiet in redirected/noninteractive runs."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TextColumn("Elapsed"),
        TimeElapsedColumn(),
        TextColumn("ETA"),
        TimeRemainingColumn(),
        console=Console(file=sys.stderr),
        disable=not (sys.stderr.isatty() if enabled is None else enabled),
    )
