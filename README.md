# Entity Marker

Python 3.12+ CLI for finding occurrences of **known objects** in text and producing
Label Studio predictions. Input objects have fixed schemas for legal entities,
people, documents, senders, and correspondence metadata. The original car schema
is also supported for compatibility. See [the real data schema in Russian](docs/SCHEMA.ru.md)
and [the complete example](examples/real_objects.json). This is known-entity matching/linking, not open-ended NER.

## Install and run

```bash
uv sync
uv run entity-marker --help
uv run entity-marker mark --help
uv run entity-marker validate --objects examples/objects.json
uv run entity-marker mark \
  --text examples/input.txt \
  --objects examples/objects.json \
  --output examples/predictions.json \
  --evidence-output examples/evidence.json \
  --pretty
cat examples/input.txt | uv run entity-marker mark --objects examples/objects.json
```

Everything runs locally. Dependencies are Typer, Pydantic, and pymorphy3 with its Russian dictionaries.
Dictionaries are installed by `uv sync`; matching needs no external APIs or
database and performs no runtime downloads. `uv.lock` pins dependencies.

## Input

`--text` is UTF-8 text. Without it, stdin is read as UTF-8. `--text` takes
precedence over stdin. Empty input and invalid UTF-8 are errors.

```json
{
  "people": [
    {"id": "p1", "first_name": "Иван", "last_name": "Петров", "birth_date": "1980-01-01"}
  ],
  "cars": [
    {"id": "c1", "vin": "X7LHSRDVN12345678", "license_plate": "А123ВС77"}
  ],
  "documents": [
    {"id": "d1", "document_type": "passport", "series": "4501", "number": "987654"}
  ]
}
```

Groups default to empty lists. IDs are required and unique within their type;
optional fields may be omitted or null. Empty/whitespace-only strings, unknown
fields, and invalid dates are rejected, except that `email` and `reply_email`
accept any string without email-format validation, including empty strings.
Dates accept ISO `YYYY-MM-DD` and `DD.MM.YYYY` in input.
Document type is searchable as weak evidence requiring local corroboration.
Dates also accept `DD.MM.YYYY`; the Russian/English field mappings and identifier
validation rules are documented in [SCHEMA.ru.md](docs/SCHEMA.ru.md).

## Multiple files and CSV rows

Use `mark-batch` for semicolon-separated UTF-8 CSV exports like `new 4.csv`.
Each CSV record supplies its own people, cars, legal entities, documents, sender,
and correspondence metadata. Its `versionId` selects a separate UTF-8 text file:

```text
dataset/
├── first.csv
├── second.csv
└── txts/
    ├── <versionId-from-first-row>.txt
    └── <versionId-from-second-row>.txt
```

```bash
uv run entity-marker mark-batch \
  --input '/Users/ep/Downloads/Telegram/new 4.csv' \
  --txts-dir /path/to/txts \
  --output predictions.json \
  --evidence-output evidence.json \
  --pretty

# Repeat --input to process multiple CSVs in the given order.
uv run entity-marker mark-batch \
  --input dataset/first.csv --input dataset/second.csv \
  --output predictions.json

# Runnable synthetic example included in this repository:
uv run entity-marker mark-batch --input examples/batch/input.csv --pretty
```

Without `--txts-dir`, each CSV uses the `txts` folder beside that CSV.
The command reads local `.txt` files only; `minioPath`, URLs, and PDF filenames
are metadata, not instructions to download or extract documents.
Standard CSV quoting, quoted multiline cells, CRLF, and an optional UTF-8 BOM
are supported. CSV cells can exceed Python's default 131,072-character limit;
the reader temporarily raises it to the platform-supported maximum.
One *CSV record* is one input, even when a cell spans physical lines.

The `Субъект страхования ФЛ`, `Субъект страхования ЮЛ`, and
`Субъект страхования ТС` cells contain JSON arrays. Empty cells mean empty arrays;
blank strings and JSON nulls in optional entity fields become missing values.
Identifiers stay strings, preserving leading zeros. People's identity-document
fields become document entities. See the [CSV field mapping](docs/SCHEMA.ru.md#csv-выгрузки).

Output is one Label Studio task per record in a single JSON array. Each task's
`data` contains the original `text`, `versionId`, `source_csv`, `source_row`
(header is row 1), `text_file`, and any provided `cardId`, `fileId`, and `fileName`.
Objects are never pooled across records. Entity IDs are generated from array
positions within each record (`person-1`, `car-1`, etc.); identify them together
with the source CSV and row. Repeated version IDs remain separate records.
Evidence output is an array of reports carrying the same source metadata.
Region IDs are local to each task/report pair. `--format occurrences` emits this
report array as the primary output.

`--max-errors`, `--disable-fuzzy`, `--pretty`, and `-v`/`-vv` work as in `mark`.
Without `--output`, JSON goes to stdout. Invalid CSV/entity data, unsafe version
IDs, and empty or invalid UTF-8 text files fail with exit code 2.
Rows with missing `<versionId>.txt` files are skipped with a warning on stderr.
If all text files are missing, the command succeeds with empty output arrays.
All remaining rows must succeed before either output is written.
Input/output collisions are checked against all CSV and text paths.
Outputs are replaced atomically individually, not as a multi-file transaction.
The combined batch output is held in memory, so split very large exports into
smaller batches. The existing single-document `mark` command is unchanged.

## Output and Label Studio

Import prediction JSON into a project configured with
[`examples/labeling_config.xml`](examples/labeling_config.xml). The output follows
[Label Studio's prediction format](https://labelstud.io/guide/predictions), with
`from_name="entities"`, `to_name="text"`, and field-specific labels.

For `VIN X7LHSR0VN12345678` and the known VIN `X7LHSRDVN12345678`:

```json
[
  {
    "data": {"text": "VIN X7LHSR0VN12345678"},
    "predictions": [
      {
        "model_version": "entity-marker-0.4-domain-schema",
        "result": [
          {
            "id": "r000001",
            "from_name": "entities",
            "to_name": "text",
            "type": "labels",
            "value": {
              "start": 4,
              "end": 21,
              "text": "X7LHSR0VN12345678",
              "labels": ["CAR_VIN"]
            }
          }
        ]
      }
    ]
  }
]
```

`--evidence-output evidence.json` writes entity IDs, source values, methods, edit
distances, scores, local supporting matches, and resolution rejections. Its
`region_id` links each accepted occurrence to the prediction result. Candidate
spans rejected at boundary/gap filtering are not included in this report.
`--format occurrences` emits this report as the primary output instead.

Offsets always use Python Unicode code-point slicing `[start:end]` into the
**original** text. File reading preserves CRLF. The embedded text is unchanged;
`original[start:end] == matched_text`. No normalized offsets are exported.
The serializer is covered by Unicode/emoji tests; import/display in a running
Label Studio installation has not been exercised here.

Output order is deterministic: start, end, entity type, entity ID, field.
Without `--output`, JSON goes to stdout. Logs and errors go to stderr. Files are
replaced atomically individually; multiple outputs are not a transaction.
Input/output path collisions are rejected. Invalid input and I/O failures exit
with code 2. A successful run with no matches exports an empty result list.

## Matching

```text
objects → aliases → exact + normalized exact + Bitap candidates
        → original spans and boundaries → local evidence
        → identity/strength resolution → overlap resolution → predictions
```

- **Exact:** literal occurrences, including repeats and overlapping search hits.
- **Normalized:** NFKC with mapped source ranges; names are case-folded with
  `ё → е`; VINs and plates allow specified Latin/Cyrillic lookalikes; structured
  identifiers allow spaces/hyphens and document identifiers allow `№`.
- **Bitap:** approximate normalized matching with substitutions, insertions, and
  deletions. Transposition is two edits. A positive-bit Shift-And automaton locates
  ends, then an anchored reverse automaton recovers every valid start and its
  minimum Levenshtein distance. Empty patterns and negative budgets are errors.
  Budget zero is identical to literal matching at the matcher level.

Normalization records an original range for every emitted character, including
Unicode expansion/composition. Partial matches inside expanded characters are
rejected. Removed separator gaps are bounded; line breaks remain barriers.
Matching inside larger words/identifiers is rejected. There is no global
aggressive normalization across fields.

Person names are marked as separate `PERSON_FIRST_NAME`, `PERSON_LAST_NAME`, and
`PERSON_MIDDLE_NAME` (patronymic) spans, including when all three appear together.
For example, `Иванов Иван Иванович` produces three regions. Previous surnames use
`PERSON_PREVIOUS_LAST_NAME`; person full-name regions are not generated. In
`Иванов И.И.`, only the surname is marked. Birth dates retain ISO/dotted/slashed aliases.

Russian morphology is enabled by default through the
[pymorphy3](https://github.com/no-plagiarism/pymorphy3) infrastructure adapter.
Dictionary-tagged first names, surnames, and patronymics are inflected into six
singular cases, so `Иванову Ивану Ивановичу` produces three component matches linked
to the same person. Senders retain their single `SENDER_FULL_NAME` field, with
full-name aliases in two orders and compact/spaced initials for inflected surnames.

Morphological aliases work with `--disable-fuzzy`; their match method is `exact`
or `normalized` according to how the generated alias matches the text. The
reported `source_value` is the matched alias, while `entity_id` links back to the
original object. Sender initials aliases are exact/normalized only: wrong initials are
not repaired using fuzzy edits. Unknown components are kept unchanged. Gender
hints from first name and patronymic constrain surname parses; uncertain identities
such as a male `Иванов` and female `Иванова` sharing a form remain ambiguous. Car aliases include
VIN, plate, body number, and chassis number. Documents include series, number,
combined series/number, and issue-date aliases.

Fuzzy distance defaults to one, with domain limits:

| Field | Maximum edits |
|---|---:|
| VIN, plate, body/chassis identifiers of length ≥ 4 | 1 |
| Names of length ≥ 4 | 1 |
| Sender full names / surnames of length ≥ 10 | 2, if global ceiling permits |
| Document number/combined identifier of length ≥ 6 | 1 |
| Dates, document series, shorter values | 0 |

```bash
uv run entity-marker mark --text input.txt --objects objects.json --max-errors 2
uv run entity-marker mark --text input.txt --objects objects.json --disable-fuzzy
uv run entity-marker mark --text input.txt --objects objects.json --format occurrences -vv
```

`--max-errors` caps domain budgets, it does not override short-value restrictions.
`--disable-fuzzy` and `--max-errors 0` retain normalization. Exact occurrences
suppress redundant overlapping fuzzy candidates, while later OCR-damaged
occurrences are still searched. Normalized texts, patterns, and search results
are cached within each run. Identical aliases are deduplicated.

## Evidence and resolution

Field/alias weights express discriminative power, not calibrated probabilities.
Strong identifiers and sender full names receive higher weights than isolated given
names. Similarity discounts weight by normalized edit distance.

Evidence is grouped by entity and local mention: distinct non-overlapping fields,
at most 80 characters apart, with no sentence/line boundary between them. Only
the strongest support per field is retained. A bounded evidence bonus can raise
weak candidates above the acceptance threshold. Composite aliases do not borrow
components as score bonuses. Weak isolated names and unresolved competing
identities are rejected; entity ID sorting never establishes identity.

The overlap policy retains identical spans in distinct entity roles, such as a
legal entity and a sender sharing an INN. Otherwise the flat policy prioritizes exact, then normalized, then fuzzy matches;
then score, edit distance, span length, and deterministic ordering. Consequently,
an exact document number can beat an enclosing normalized series/number region.
Rejected candidates remain in the evidence report. Every non-overlapping repeated
mention is retained: if a known case number appears three times, the output contains
three `MISC_CASE_NUMBER` regions, each with its own offsets and region ID. This applies
to all labels in both `mark` and `mark-batch`; labels and matched values are not
deduplicated across text positions. Each mention still passes the matching and
ambiguity checks above.

Case numbers in the form `A41-20769/2025` (Latin `A` or Cyrillic `А`) also accept
the short year form `A41-20769/25`, in either direction. Two-digit years denote
2000–2099. Both mentions receive `MISC_CASE_NUMBER` regions with their original
text and offsets, including with `--disable-fuzzy`. Other digits must match;
this year alias does not apply to incoming letter numbers or other reference formats.

Rules live in immutable `MatchingConfig` and field policies. Python callers can
supply custom thresholds, proximity limits, and field-weight overrides:

```python
from entity_marker.bootstrap import build_handler
from entity_marker.domain.policies.matching import MatchingConfig

handler = build_handler(
    MatchingConfig(
        max_errors=2,
        acceptance_threshold=0.65,
        evidence_window=60,
        field_weights=(("last_name", 0.70),),
    )
)
```

`-v` logs counts; `-vv` logs aliases, candidates, and resolver decisions, including
matched values. Logging is opt-in and never contaminates stdout JSON.

## DDD architecture

```text
CLI → Application → Domain
                       ↑
                 Infrastructure
```

```text
src/entity_marker/
├── domain/
│   ├── models/           # Entities, spans, aliases, candidates, evidence
│   ├── aliases/          # Person/car/document textual representations
│   ├── policies/         # Field budgets, weights, immutable config
│   ├── ports/            # Exact/approximate matcher and normalizer protocols
│   └── services/         # Candidate generation, evidence and overlap resolution
├── application/          # Mark command and handler, no I/O
├── infrastructure/
│   ├── matching/         # Exact and Bitap adapters
│   ├── morphology/       # Russian dictionary-backed name inflection
│   ├── normalization/    # Offset-preserving normalization adapter
│   └── serialization/    # Pydantic input boundary, JSON exports, atomic file I/O
├── cli/                  # Typer commands and errors
├── bootstrap.py          # Constructor injection
└── __main__.py           # python -m entity_marker
```

Domain models are immutable dataclasses, not dictionaries. Pydantic is used only
at the input boundary. Domain/application code cannot import infrastructure,
CLI, Typer, or Pydantic; a test enforces this. No repositories, web service, or
unnecessary DDD infrastructure are introduced.

To add an entity type: add its model and DTO mapping, enum member, alias generator,
policy/weights, labels in the XML, and tests. Existing matcher adapters are shared.
To add an algorithm: implement `ApproximateTextMatcher`, test its span/distance
contract, and inject it in `bootstrap.py`; acceptance policies stay unchanged.
Large-catalog exact search could later use a batch Aho–Corasick port without
changing occurrence or evidence models.

## Validation and development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
make clean
```

Tests include 3,720 exhaustive Bitap/reference comparisons, long patterns,
Unicode, each edit operation, original offsets, normalization, policies, aliases,
ambiguity, local/remote evidence, overlap decisions, CLI options, and file errors.

For VS Code, install the recommended Python extensions, run `uv sync`, select
**Entity Marker: mark example**, and press F5. The debugger uses `.venv`.
`make clean` removes caches/build outputs while preserving `.venv` and examples.

## Limits

- Morphology covers dictionary-recognized Russian singular name paradigms, not
  arbitrary phrase analysis, unknown/compound surname heuristics, or generic entity
  discovery. Unsupported components stay unchanged. Conflicting gender hints do
  not produce new forms.
- Heuristic rules need evaluation/tuning on representative OCR data. A shared
  identifier without sufficient local evidence remains ambiguous.
- Output uses a flat overlap policy (except identical spans in distinct roles),
  not nested annotations or document-wide
  coreference. Independent fields separated by sentence boundaries do not combine.
- Input text and candidates are held in memory. Bitap is intended for modest
  catalogs and small error budgets. For text length n, pattern length m, budget k,
  and H matching ends, work is O(n*k + H*(m+k)*k) big-integer operations plus sorting;
  integer costs grow with m. Large budgets can yield quadratically many spans.
- Input identifiers are nonblank strings; jurisdiction-specific VIN checksum,
  license-plate, and document-format validators are not imposed.
