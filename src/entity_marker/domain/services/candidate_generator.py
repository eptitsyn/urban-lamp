import logging
import re
import unicodedata

from entity_marker.domain.models.matches import (
    ApproximateMatch,
    EntityAlias,
    MatchCandidate,
    MatchMethod,
    MatchScore,
    NormalizationProfile,
)
from entity_marker.domain.models.text import NormalizedText, SourceText, TextSpan
from entity_marker.domain.policies.matching import MatchingConfig, allowed_distance
from entity_marker.domain.ports.matching import ApproximateTextMatcher, ExactTextMatcher
from entity_marker.domain.ports.normalization import TextNormalizer

logger = logging.getLogger(__name__)
_DATE_SUFFIX_PATTERN = r"г(?:од(?:а|у|ом)?)?\.?(?:[ \t]*р(?:ождения)?\.?)?(?!\w)"
_DATE_SUFFIX = re.compile(_DATE_SUFFIX_PATTERN, re.IGNORECASE)
_DATE_ENDS_WITH_SUFFIX = re.compile(r"\d[ \t]*" + _DATE_SUFFIX_PATTERN + r"$", re.IGNORECASE)


def _word(char: str) -> bool:
    return char.isalnum() or char == "_" or unicodedata.category(char).startswith("M")


def valid_boundary(text: str, span: TextSpan) -> bool:
    return not (
        (span.start > 0 and _word(text[span.start - 1]))
        or (span.end < len(text) and _word(text[span.end]))
    )


def valid_field_boundary(text: str, span: TextSpan, alias: EntityAlias) -> bool:
    if alias.profile == NormalizationProfile.DATE and _DATE_ENDS_WITH_SUFFIX.search(
        text[span.start : span.end]
    ):
        # A fuzzy insertion must not turn a year suffix into part of the date.
        return False
    if not valid_boundary(text, span):
        # Russian year/birth abbreviations may immediately follow the year.
        # Relax only the right boundary; the suffix stays outside the date span.
        date_suffix = (
            alias.profile == NormalizationProfile.DATE
            and (span.start == 0 or not _word(text[span.start - 1]))
            and text[span.end - 1].isdigit()
            and _DATE_SUFFIX.match(text, span.end) is not None
        )
        if not date_suffix:
            return False
    if alias.profile == NormalizationProfile.EMAIL:
        # Do not find a known mailbox inside another local part or subdomain.
        if span.start and text[span.start - 1] in ".%+-@":
            return False
        if span.end < len(text):
            following = text[span.end]
            if following in "@%+-":
                return False
            if following == "." and span.end + 1 < len(text) and _word(text[span.end + 1]):
                return False
    if alias.profile == NormalizationProfile.REFERENCE:
        left, right = span.start - 1, span.end
        if alias.field_name == "case_number":
            # Spaces around case-number separators do not end the identifier.
            # A bare number must not match inside another court's full number.
            while left >= 0 and text[left] in " \t":
                left -= 1
            while right < len(text) and text[right] in " \t":
                right += 1
        if left >= 0 and text[left] in "/-":
            return False
        if right < len(text) and text[right] in "/-":
            return False
    return True


def _valid_mapped_span(
    mapped: NormalizedText, span: TextSpan, alias: EntityAlias, config: MatchingConfig
) -> bool:
    if not mapped.has_complete_boundaries(span):
        return False
    original = mapped.to_original_span(span)
    if not valid_field_boundary(mapped.original, original, alias):
        return False
    # Gaps removed by identifier profiles cannot bridge arbitrary stretches of text.
    selected = mapped.source_ranges[span.start : span.end]
    if any(
        right.start - left.end > config.max_separator_gap
        for left, right in zip(selected, selected[1:], strict=False)
    ):
        return False
    value = mapped.normalized[span.start : span.end]
    if not value or "\n" in value or "\r" in value:
        return False
    if alias.profile in (
        NormalizationProfile.TEXT,
        NormalizationProfile.EMAIL,
        NormalizationProfile.REFERENCE,
    ):
        if value[0].isspace() or value[-1].isspace():
            return False
        if alias.value[-1].isalnum() and not value[-1].isalnum():
            return False
        return True
    if not value[0].isalnum() or not (value[-1].isalnum() or value[-1] == "."):
        return False
    if alias.profile == NormalizationProfile.TAX_ID:
        return value.isascii() and value.isdigit()
    if alias.profile in (
        NormalizationProfile.VIN,
        NormalizationProfile.PLATE,
        NormalizationProfile.IDENTIFIER,
    ):
        return all(char.isalnum() for char in value)
    if alias.profile == NormalizationProfile.NAME:
        punctuation = " -'’" + ("." if "." in alias.value else "")
        return all(
            char.isalpha() or unicodedata.category(char).startswith("M") or char in punctuation
            for char in value
        )
    return "\n" not in value and "\r" not in value


class CandidateGenerator:
    def __init__(
        self,
        exact: ExactTextMatcher,
        approximate: ApproximateTextMatcher,
        normalizer: TextNormalizer,
        config: MatchingConfig,
    ) -> None:
        self.exact = exact
        self.approximate = approximate
        self.normalizer = normalizer
        self.config = config

    def generate(
        self, source: SourceText, aliases: tuple[EntityAlias, ...]
    ) -> tuple[MatchCandidate, ...]:
        texts: dict[NormalizationProfile, NormalizedText] = {}
        patterns: dict[tuple[NormalizationProfile, str], str] = {}
        exact_cache: dict[str, list[TextSpan]] = {}
        normalized_cache: dict[tuple[NormalizationProfile, str], list[TextSpan]] = {}
        fuzzy_cache: dict[tuple[NormalizationProfile, str, int], list[ApproximateMatch]] = {}
        candidates: list[MatchCandidate] = []
        for alias in aliases:
            logger.debug("Alias: %s", alias)
            if alias.value not in exact_cache:
                exact_cache[alias.value] = self.exact.find(source.text, alias.value)
            explained: set[TextSpan] = set()
            for span in exact_cache[alias.value]:
                if valid_field_boundary(source.text, span, alias):
                    candidates.append(self._candidate(alias, source, span, MatchMethod.EXACT, 0, 1))
                    explained.add(span)
            if alias.profile not in texts:
                texts[alias.profile] = self.normalizer.normalize(source.text, alias.profile)
            mapped = texts[alias.profile]
            key = (alias.profile, alias.value)
            if key not in patterns:
                patterns[key] = self.normalizer.normalize(alias.value, alias.profile).normalized
            pattern = patterns[key]
            if not pattern:
                continue
            normalized_key = (alias.profile, pattern)
            if normalized_key not in normalized_cache:
                normalized_cache[normalized_key] = self.exact.find(mapped.normalized, pattern)
            for normalized_span in normalized_cache[normalized_key]:
                if not _valid_mapped_span(mapped, normalized_span, alias, self.config):
                    continue
                span = mapped.to_original_span(normalized_span)
                if span not in explained:
                    candidates.append(
                        self._candidate(alias, source, span, MatchMethod.NORMALIZED, 0, 1)
                    )
                    explained.add(span)
            budget = allowed_distance(alias, pattern, self.config)
            if not budget:
                continue
            fuzzy_key = (alias.profile, pattern, budget)
            if fuzzy_key not in fuzzy_cache:
                fuzzy_cache[fuzzy_key] = self.approximate.find(mapped.normalized, pattern, budget)
            for match in fuzzy_cache[fuzzy_key]:
                if not match.distance or not _valid_mapped_span(
                    mapped, match.span, alias, self.config
                ):
                    continue
                span = mapped.to_original_span(match.span)
                # Do not skip later OCR mentions just because an earlier exact one exists.
                if any(span.start < known.end and known.start < span.end for known in explained):
                    continue
                quality = 1 - match.distance / max(len(pattern), match.span.end - match.span.start)
                candidates.append(
                    self._candidate(alias, source, span, MatchMethod.BITAP, match.distance, quality)
                )
        return tuple(candidates)

    @staticmethod
    def _candidate(
        alias: EntityAlias,
        source: SourceText,
        span: TextSpan,
        method: MatchMethod,
        distance: int,
        quality: float,
    ) -> MatchCandidate:
        candidate = MatchCandidate(
            alias,
            span,
            source.text[span.start : span.end],
            MatchScore(alias.weight * quality),
            method,
            distance,
        )
        logger.debug("Candidate: %s", candidate)
        return candidate
