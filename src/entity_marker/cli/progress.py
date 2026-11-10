import sys
from time import monotonic

from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


class ProcessingLive(Live):
    """Use periodic plain lines when a console cannot render a live terminal bar."""

    _last_snapshot = float("-inf")

    def refresh(self) -> None:
        if self.console.is_terminal and not self.console.is_dumb_terminal:
            super().refresh()
            return
        with self._lock:
            now = monotonic()
            if not self.is_started or now - self._last_snapshot >= 1:
                with self.console.capture() as capture:
                    self.console.print(self.renderable)
                snapshot = capture.get()
                if snapshot.strip():
                    self.console.file.write(snapshot)
                    self.console.file.flush()
                    self._last_snapshot = now


def processing_progress(enabled: bool | None, *, output_file: bool = False) -> Progress:
    """Show stderr status for terminals or file output, unless explicitly disabled."""
    display = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TextColumn("Elapsed"),
        TimeElapsedColumn(),
        TextColumn("ETA"),
        TimeRemainingColumn(),
        console=Console(file=sys.stderr),
        disable=not (output_file or sys.stderr.isatty() if enabled is None else enabled),
    )
    display.live = ProcessingLive(
        console=display.console,
        get_renderable=display.get_renderable,
        refresh_per_second=4,
        redirect_stdout=False,
    )
    return display
