from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class TextSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("A text span must satisfy 0 <= start < end")


@dataclass(frozen=True)
class SourceText:
    text: str


@dataclass(frozen=True)
class NormalizedText:
    original: str
    normalized: str
    source_ranges: tuple[TextSpan, ...]

    def __post_init__(self) -> None:
        if len(self.normalized) != len(self.source_ranges):
            raise ValueError("Every normalized character needs a source range")
        previous = TextSpan(0, 1)
        for span in self.source_ranges:
            if span.end > len(self.original) or span.start < previous.start:
                raise ValueError("Invalid normalization source map")
            previous = span

    def to_original_span(self, span: TextSpan) -> TextSpan:
        if span.end > len(self.normalized):
            raise ValueError("Normalized span out of bounds")
        return TextSpan(self.source_ranges[span.start].start, self.source_ranges[span.end - 1].end)

    def has_complete_boundaries(self, span: TextSpan) -> bool:
        """Reject matches selecting only part of an expanded Unicode character."""
        return (
            span.start == 0 or self.source_ranges[span.start - 1] != self.source_ranges[span.start]
        ) and (
            span.end == len(self.normalized)
            or self.source_ranges[span.end - 1] != self.source_ranges[span.end]
        )
