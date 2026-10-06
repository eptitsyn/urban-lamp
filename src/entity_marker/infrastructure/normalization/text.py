import unicodedata

from entity_marker.domain.models.matches import NormalizationProfile
from entity_marker.domain.models.text import NormalizedText, TextSpan

# Only visually equivalent letters; never global cross-script transliteration.
_CONFUSABLES = str.maketrans("АВЕКМНОРСТУХавекмнорстух", "ABEKMHOPCTYXABEKMHOPCTYX")


def _joins(segment: str, char: str) -> bool:
    # A new starter normally begins a mapping unit. Hangul and compatibility
    # decompositions can still compose across starters, so detect that boundary.
    return unicodedata.category(char).startswith("M") or (
        unicodedata.normalize("NFKC", segment + char)
        != unicodedata.normalize("NFKC", segment) + unicodedata.normalize("NFKC", char)
    )


class MappedNormalizer:
    def normalize(self, text: str, profile: NormalizationProfile) -> NormalizedText:
        chars: list[str] = []
        ranges: list[TextSpan] = []
        start = 0
        while start < len(text):
            end = start + 1
            # Never split a Unicode composition sequence across source ranges.
            while end < len(text) and _joins(text[start:end], text[end]):
                end += 1
            # NFKC turns № into "No"; handle the separator before normalization.
            if text[start:end] == "№" and profile == NormalizationProfile.IDENTIFIER:
                start = end
                continue
            value = unicodedata.normalize("NFKC", text[start:end])
            if profile == NormalizationProfile.NAME:
                value = value.casefold().replace("ё", "е")
            elif profile in (NormalizationProfile.TEXT, NormalizationProfile.EMAIL):
                value = value.casefold()
                if profile == NormalizationProfile.TEXT:
                    value = value.translate(str.maketrans("«»“”„", '"""""'))
            elif profile in (NormalizationProfile.VIN, NormalizationProfile.PLATE):
                value = value.translate(_CONFUSABLES).upper()
            else:
                value = value.upper()
            for char in value:
                if profile in (
                    NormalizationProfile.VIN,
                    NormalizationProfile.PLATE,
                    NormalizationProfile.IDENTIFIER,
                ):
                    # Keep line breaks and sentence punctuation as hard barriers.
                    if char in " \t-№":
                        continue
                if (
                    profile
                    in (
                        NormalizationProfile.TAX_ID,
                        NormalizationProfile.REFERENCE,
                        NormalizationProfile.DATE,
                    )
                    and char in " \t"
                ):
                    continue
                if (
                    profile
                    in (
                        NormalizationProfile.NAME,
                        NormalizationProfile.TEXT,
                        NormalizationProfile.REFERENCE,
                    )
                    and char in " \t"
                ):
                    char = " "
                    if chars and chars[-1] == " ":
                        ranges[-1] = TextSpan(ranges[-1].start, end)
                        continue
                chars.append(char)
                ranges.append(TextSpan(start, end))
            start = end
        return NormalizedText(text, "".join(chars), tuple(ranges))
