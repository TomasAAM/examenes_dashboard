# examenes_dashboard — lab result ingestion

Turns BioNet lab-report PDFs into one long-format table in DuckDB, so an analyte
can be compared across draws without opening several PDFs side by side.

**This repository is ingestion and storage only.** The Streamlit dashboard is a
later piece of work.

Everything runs locally. No cloud APIs, no telemetry. `input/`, `data/`,
`review/` and `config/manual_entries.yaml` are gitignored — health data must
never reach a commit.

---

## Quick start

```bash
uv sync
```

```bash
cp .env.example .env
```

Drop PDFs into `input/`, then:

```bash
uv run python -m examenes.cli ingest
```

That parses every PDF, writes `data/labs.duckdb`, archives each source file to
`data/raw/<sha256>.pdf`, and emits a review CSV in `review/`.

> The console script `examenes` is declared in `pyproject.toml`, but Windows
> Application Control blocks the generated `.exe` shim on this machine, so the
> commands below use `python -m examenes.cli`. Both are the same entry point.

## Commands

| Command | What it does |
|---|---|
| `ingest [PATH]` | Parse a PDF or directory (default `input/`) and load it |
| `ingest --force` | Re-parse files already ingested |
| `ingest --allow-unmapped` | Continue despite unrecognised analyte names |
| `status` | Per-report counts by confidence and verification state |
| `review export` | Write a fresh review CSV |
| `review import FILE` | Load an edited review CSV |
| `manual load [PATH]` | Load hand-entered results from YAML |

```bash
uv run python -m examenes.cli status
```

## Adding a new PDF

1. Copy it into `input/`.
2. Run `uv run python -m examenes.cli ingest`.

Ingestion is keyed on the file's sha256, so re-running is safe and never
duplicates. Files already loaded are skipped unless you pass `--force`.

If the report contains an analyte the parser has not seen, **the ingest fails
loudly**: the names are written to `review/unmapped_analytes.csv` and the
command exits non-zero. Nothing is silently dropped. To teach it the new
analyte, add the raw Spanish name to `config/aliases.yaml`, add the canonical
code to `config/analytes.yaml`, and re-run.

## The verification loop

Parsing medical numbers wrong is worse than not parsing them, so nothing is
trusted until you have looked at it.

1. `ingest` writes every row with `verified = false` and emits
   `review/review_<timestamp>.csv`. Rows are ordered **worst confidence first**
   and carry `source_file` and `source_page` so each number can be checked
   against the original PDF.
2. Open the CSV. Edit only these columns:
   - `verified` — set to `true` once you have checked the row
   - `value_num` / `value_text` — correct a misparse
   - `note` — why you changed it
3. Load your decisions back:

```bash
uv run python -m examenes.cli review import review/review_20260101-120000.csv
```

Only rows you actually touched become overrides, so the override table stays a
record of human judgement rather than a copy of the parse.

**Corrections survive re-parsing.** `observations` is purely derived from the
PDFs and is rebuilt on every ingest; your decisions live in a separate
`overrides` table that ingest never touches. The `v_observations` view joins
them, so readers see corrected, verification-aware rows. Query that view, not
the raw table.

### Confidence grades

| Grade | Meaning |
|---|---|
| `ok` | Parsed cleanly, no ambiguity |
| `check` | Worth a glance — qualitative value, missing reference, range-valued result |
| `suspect` | Look at this one — see below |

Flags that make a row `suspect`: `column_ambiguous`, `duplicate_value_conflict`,
`unit_unexpected`, `asterisk_range_mismatch`, `ref_missing_dash`,
`decimal_comma`.

## Manual entry

For results that never came as a PDF:

```bash
cp config/manual_entries.example.yaml config/manual_entries.yaml
```

Edit it, then:

```bash
uv run python -m examenes.cli manual load
```

Entries are grouped into a synthetic report per `(sample_date, lab_name)`, so
re-loading updates in place. They are stored with `source = manual` and
`verified = true`, since you typed them from the source yourself. An
`analyte_code` not present in `config/analytes.yaml` is a hard error.

## Data model

`observations` — one row per analyte per draw.

| Column | Notes |
|---|---|
| `obs_key` | Primary key, `sha256(file_hash \| analyte_code)`. Stable across re-parses |
| `sample_date` | From `Toma Muestra`, parsed day-first |
| `lab_name`, `panel`, `sub_section` | `sub_section` separates urine chemistry from microscopy |
| `analyte_code`, `analyte_name_raw` | Canonical code and the name as printed |
| `value_num`, `value_text` | Mutually exclusive. `Negativo`, `Muy escasas`, `<0.01`, `0 - 2` go to text |
| `unit`, `unit_raw` | Canonical spelling and as-printed |
| `ref_low`, `ref_high`, `ref_operator`, `ref_text` | Stored **per row** — reference ranges are per-lab and change over time |
| `ref_operator` | `range`, `lt`, `lte`, `gt`, `gte`, `text`, `categorical`, `none` |
| `method` | The `Método:` declaration owning the result |
| `out_of_range` | **Computed** from value vs reference |
| `asterisk_flag` | As printed. Disagreement with `out_of_range` raises a flag |
| `source_file`, `source_page`, `file_hash`, `cod_lis` | Provenance. `cod_lis` is BioNet's own report id |
| `confidence`, `flags`, `verified`, `also_in_panels` | Review metadata |

`analytes` — the dimension: canonical code, Spanish and English display names,
category, canonical unit, and `concerning_direction` (`high`/`low`/`both`/`none`)
so a dashboard can colour a trend without per-analyte logic.

`overrides` — the human layer. Never written by ingest.

Query example:

```bash
uv run python -c "import duckdb;print(duckdb.connect('data/labs.duckdb').execute(\"SELECT sample_date,value_num,unit FROM v_observations WHERE analyte_code='ferritin' ORDER BY 1\").fetchall())"
```

## Units

Only **cosmetic** normalisation is applied (`gr/dL` → `g/dL`, `ug/dL` → `µg/dL`),
configured in `config/units.yaml`. No numeric conversion is ever performed — a
value is never silently rescaled. If a known analyte appears in a unit other
than its canonical one the row is flagged `unit_unexpected` for review.

The sample reports all use identical units, so nothing rescales anything today.
The mapping exists so a future unit change fails loudly.

---

## How the parser works

> Result values in the examples below are **illustrative**, not real readings.
> Reference ranges are kept as printed — those are BioNet's published metadata,
> not anyone's results.

### Extraction is column-based, not regex-based

`extract.py` reads words with x/y coordinates. `columns.py` derives column
boundaries from the table header (`RESULTADO` / `UNIDAD` / `VALOR DE REFERENCIA`)
and assigns each word to a cell by position. Flattening the line and splitting it
with a regex cannot handle:

- `CELULAS EPITELIALES  Muy escasas | Escasa Cantidad` — a multi-word value
  followed by a multi-word reference with no delimiter between them
- `Segmentados  NN | NNNN | uL | 50 - 75` — the differential's percentage and
  absolute count are two numbers on one row, in different columns
- reference cells with irregular dash spacing (`50 - 200`, `15-85`, `1.015- 1.025`)

### Hidden text is dropped first

These PDFs embed layout scaffolding as **white** text: ruler digits and the
literal strings `linea`, `line`, `123`, `xx`. Left in, they corrupt reference
ranges — `MAGNESIO 2.00 mg/dL 1.6 - 1 2.6`, where the `1` between dash and upper
bound is scaffolding and the true range is 1.6–2.6. Read naively it becomes
1.6–1 or 1.6–12.6.

Words whose `non_stroking_color` is white are dropped before anything else. That
is 13% of the word stream, and the dropped vocabulary contains no clinical
values. Unknown colour spaces are treated as *visible*, so an unrecognised colour
can never delete a result.

### Format quirks handled

- **Chilean D/M/YY dates.** `4/2/24` is 4 February 2024. Confirmed per report by
  cross-checking the printed `Edad` against `F.Nac`, not assumed from locale.
- **Interpretation guides.** The lipid page prints `Alto >= 240`, `Normal < 150`
  as patient education. These land wholly in the name column with an empty value
  and are rejected; the scan also stops at `GUIA PARA` and friends.
- **`Método:` is context-dependent.** On a titled panel it closes the table. On
  the untitled pages it merely separates stacked single-metric blocks.
- **`Nota :` is not a stop marker.** On PERFIL HEPATICO a real result
  (`INDICE FIB 4`) is printed *below* one, so notes are skipped, not terminal.
- **Name collisions.** `LEUCOCITOS` means three different things (urine
  chemistry, urine microscopy, haemogram count). Resolved by panel and
  sub-section in `config/aliases.yaml`.
- **The asterisk is unreliable.** This lab does not mark every out-of-range
  result. In the sample data a urine pH above its `5.0 - 7.0` reference carries
  no asterisk, while an INR *inside* its `0.9 - 1.3` reference carries one it
  should not. So `out_of_range` is computed from the numbers; the asterisk is
  stored separately, cross-checked, and disagreement raises a flag.
- **Missing dashes.** PERFIL HEPATICO prints some ranges as `46 116` with no
  dash, while PERFIL BIOQUIMICO prints `46 - 116` for the same analyte.
- **Cross-panel repeats.** Four analytes appear in two panels with identical
  values; they collapse to one row recording the other panel in
  `also_in_panels`. Repeats that *disagree* are kept as two rows and flagged —
  that is a parser bug, not a dedup case.

## Teaching the parser a new lab format

The BioNet-specific knowledge is deliberately concentrated in three places:

| What | Where |
|---|---|
| Hidden-text rule | `extract.py` — `is_hidden()` |
| Column header tokens | `columns.py` — `detect_layout()`, `ABS_HEADER_TOKENS` |
| Stop markers, skip prefixes, panel titles, sub-sections, date format | `panels.py` |
| Value and reference grammars | `normalize.py` — `parse_value()`, `parse_reference()` |
| Analyte names | `config/aliases.yaml` |

For a second lab:

1. Dump its pages first. Check whether it has a text layer, whether it hides
   scaffolding in white, and where its column headers sit. Do this before
   writing anything — the whole design of this parser came out of that step.
2. If the layout is header-anchored like BioNet's, you may only need new stop
   markers in `panels.py` and new aliases.
3. If it is structurally different, add a lab-specific scanner alongside
   `parse.py::scan_page` and dispatch on the issuing lab, keeping `normalize.py`,
   `build.py` and `store.py` shared.
4. Set `lab_name` from the new report header so per-lab reference ranges stay
   attributable — ranges are stored per row precisely because they differ by lab
   and drift over time.

## Tests

```bash
uv run pytest
```

`tests/test_parsing.py` covers the value, reference, date and hidden-text rules
with synthetic input — it needs nothing else and always runs.

`tests/test_pipeline.py` runs the real PDFs end to end and asserts the traps stay
fixed: the phantom-digit reference ranges, guide-block leakage, urine multi-word
qualitatives, the three `LEUCOCITOS`, the differential percentage/absolute split,
cross-panel dedup, idempotency, and that `verified` survives a forced re-ingest.

### The golden snapshot

Real result values are health data, so they are **not committed**. The split is:

- **Structural invariants** are asserted inline — that an absolute count has no
  reference range, that a qualitative result never populates `value_num`, that a
  disagreeing asterisk always raises a flag. These are the design contract and
  contain nothing personal.
- **Concrete values and draw dates** come from `tests/expected_values.json`, a
  gitignored golden snapshot.

Create it once, after checking the parse against the PDFs:

```bash
uv run python tests/generate_expected.py
```

The snapshot captures parser output at a moment it was known to be correct, so
any later change in output fails the suite. The generator refuses to overwrite an
existing snapshot: it prints a diff and exits non-zero, so a regression is shown
rather than silently blessed. Pass `--force` only once every listed change has
been verified against the source PDFs.

On a fresh clone both the PDFs and the snapshot are absent, so the end-to-end
tests skip and the rest still run.

## Stack

Python ≥3.11, `uv`, pdfplumber, DuckDB, Typer, PyYAML.

`polars` is declared for the future dashboard but the ingest path does not use
it: DuckDB↔Polars interop pulls in `pyarrow`, and DuckDB's native `COPY` and
`executemany` cover everything ingestion needs.

No OCR. Every page of every sample report has a real text layer, so there is no
Tesseract dependency.
