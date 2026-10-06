from dataclasses import replace
from typing import Protocol, cast

from pymorphy3 import MorphAnalyzer  # type: ignore[import-untyped]

from entity_marker.domain.models.entities import Person

_CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")


class _Tag(Protocol):
    @property
    def grammemes(self) -> frozenset[str]: ...


class _Parse(Protocol):
    @property
    def tag(self) -> _Tag: ...

    @property
    def word(self) -> str: ...

    @property
    def is_known(self) -> bool: ...

    def inflect(self, grammemes: set[str]) -> "_Parse | None": ...


class _Analyzer(Protocol):
    def parse(self, word: str) -> list[_Parse]: ...


class RussianPersonInflector:
    """Dictionary-backed singular name forms, never arbitrary suffix replacement.

    Only parses tagged Name/Surn/Patr are eligible. Unrecognized or ambiguous
    components stay unchanged. Case forms are aligned, not a Cartesian product.
    Dictionaries are loaded lazily and no network access occurs during matching.
    """

    def __init__(self) -> None:
        self._analyzer: _Analyzer | None = None
        self._parse_cache: dict[tuple[str, str], tuple[_Parse, ...]] = {}

    def _parses(self, word: str, role: str) -> tuple[_Parse, ...]:
        key = (word, role)
        if key in self._parse_cache:
            return self._parse_cache[key]
        if self._analyzer is None:
            self._analyzer = cast(_Analyzer, MorphAnalyzer(lang="ru"))
        result = tuple(
            p
            for p in self._analyzer.parse(word)
            if p.is_known and {role, "sing"} <= p.tag.grammemes
        )
        self._parse_cache[key] = result
        return result

    def forms(self, person: Person) -> tuple[Person, ...]:
        components = (
            (person.first_name, "Name"),
            (person.last_name, "Surn"),
            (person.middle_name, "Patr"),
        )
        parses = [self._parses(value, role) if value else () for value, role in components]
        # Prefer the gender of unambiguous nominative first name/patronymic.
        genders: set[str] = set()
        for index in (0, 2):
            gender_options = {
                value
                for p in parses[index]
                if "nomn" in p.tag.grammemes
                for value in ("masc", "femn")
                if value in p.tag.grammemes
            }
            if len(gender_options) == 1:
                genders.update(gender_options)
        if len(genders) > 1:
            return (person,)
        gender = next(iter(genders)) if len(genders) == 1 else None
        selected: list[_Parse | None] = []
        for options in parses:
            compatible = [
                p
                for p in options
                if gender is None or gender in p.tag.grammemes or "ms-f" in p.tag.grammemes
            ]
            nominative = [p for p in compatible if "nomn" in p.tag.grammemes]
            choices = nominative or compatible
            # Do not guess between male/female paradigms if context cannot decide.
            # Use plain grammeme sets: pymorphy's typed gender values can raise
            # when compared with an absent or unsupported gender.
            if len({p.tag.grammemes & {"masc", "femn", "neut"} for p in choices}) > 1:
                selected.append(None)
            else:
                selected.append(choices[0] if choices else None)
        variants = [person]
        for case in _CASES:
            values: list[str | None] = []
            for (original, _), parsed in zip(components, selected, strict=True):
                inflected = parsed.inflect({case, "sing"}) if parsed else None
                if inflected is None or original is None:
                    values.append(original)
                else:
                    # Match usual title case literally; other casing is normalized later.
                    values.append(
                        inflected.word.upper()
                        if original.isupper()
                        else inflected.word.title()
                        if original.istitle()
                        else inflected.word
                    )
            variants.append(
                replace(person, first_name=values[0], last_name=values[1], middle_name=values[2])
            )
        return tuple(dict.fromkeys(variants))
