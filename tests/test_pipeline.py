"""End-to-end tests against the real PDFs.

Two things are deliberately kept apart here:

*Structural invariants* -- that an absolute count has no reference range, that a
qualitative result never populates `value_num`, that an asterisk disagreeing with
the computed range raises a flag -- are asserted inline. They are the design
contract and contain no personal data.

*Concrete values and draw dates* are health data, so they come from a gitignored
golden snapshot (`tests/expected_values.json`, see `generate_expected.py`).

Both the PDFs and the snapshot are gitignored, so these tests skip cleanly on a
fresh clone.
"""

from __future__ import annotations

import pytest
from conftest import INPUT_DIR, observation_id, observation_on, snapshot_of

from examenes.review import export_review, import_review
from examenes.store import connect, report_exists, seed_analytes, write_report

pytestmark = pytest.mark.skipif(
    not list(INPUT_DIR.glob("*.pdf")), reason="no source PDFs available"
)


class TestCoverage:
    def test_every_analyte_name_is_mapped(self, parsed):
        _, unmapped = parsed
        assert unmapped == [], f"unmapped names: {[u.name_raw for u in unmapped]}"

    def test_all_draws_present(self, parsed, expected):
        assert {str(o.sample_date) for o in parsed[0]} == set(expected.draws)

    def test_no_observation_lacks_a_value(self, parsed):
        empty = [o for o in parsed[0] if o.value_num is None and o.value_text is None]
        assert empty == [], f"{len(empty)} observations carry no value"

    def test_every_observation_matches_the_golden_snapshot(self, parsed, expected):
        """Full regression net: any change in parser output shows up here."""
        actual = {observation_id(o): snapshot_of(o) for o in parsed[0]}
        assert set(actual) == set(expected.observations), (
            "observation set changed: "
            f"added {sorted(set(actual) - set(expected.observations))[:5]}, "
            f"removed {sorted(set(expected.observations) - set(actual))[:5]}"
        )
        differing = [k for k, v in actual.items() if v != expected.observations[k]]
        assert not differing, f"{len(differing)} observations changed: {differing[:5]}"


class TestPhantomWhiteDigits:
    """The white scaffolding `1` between dash and upper bound must be gone.

    Left in, a printed `1.6 - 1 2.6` yields a reference of 1.6-1 or 1.6-12.6.
    These are BioNet's published reference ranges, not results.
    """

    @pytest.mark.parametrize(
        "code,low,high",
        [
            ("magnesium", 1.6, 2.6),
            ("vitamin_b12", 211.0, 911.0),
            ("t4_free", 0.89, 1.76),
            ("transferrin", 215.0, 365.0),
            ("t3_total", 0.6, 1.81),
        ],
    )
    def test_reference_bounds(self, by_code, expected, code, low, high):
        # Panels change between draws (total T3 was replaced by free T3 in
        # November 2026), so use the most recent draw that reports this analyte.
        draw = max(str(o.sample_date) for o in by_code[code])
        o = observation_on(by_code, code, draw)
        assert (o.ref_low, o.ref_high) == (low, high)


class TestGuideBlockLeakage:
    """Interpretation guides must never be parsed as results."""

    @pytest.mark.parametrize(
        "phrase",
        ["ALTO", "LIMITE ALTO", "OPTIMO", "CERCANO A LO OPTIMO", "DESEABLE",
         "PREDICTIVO POSITIVO DE", "BIBLIOGRAFIA", "PUNTAJE INDICE FIB",
         "NOTA", "NOMBRE", "RUT/ID", "SOLICITANTE"],
    )
    def test_no_analyte_from_a_guide_or_header_block(self, parsed, phrase):
        names = {o.analyte_name_raw.upper() for o in parsed[0]}
        assert not any(n.startswith(phrase) for n in names)

    def test_fib4_is_still_captured(self, by_code, expected):
        """It sits between a `Nota :` line and the interpretation table."""
        o = observation_on(by_code, "fib4", expected.latest)
        assert o.value_num == expected.num("fib4", expected.latest)
        assert o.value_num is not None


class TestUrineMultiWordQualitatives:
    """Column geometry separates a multi-word value from a multi-word reference."""

    def test_epithelial_cells(self, by_code, expected):
        o = observation_on(by_code, "urine_epithelial_cells", expected.latest)
        assert o.value_text == expected.text("urine_epithelial_cells", expected.latest)
        # The value and reference are distinct multi-word phrases, not one blob.
        assert o.value_text and o.ref_text
        assert o.value_text != o.ref_text
        assert o.value_num is None

    def test_casts_keep_their_long_reference(self, by_code, expected):
        o = observation_on(by_code, "urine_casts", expected.latest)
        assert o.value_text == expected.text("urine_casts", expected.latest)
        # The long descriptive reference must not be mined for numbers.
        assert o.ref_operator == "text"
        assert o.ref_low is None and o.ref_high is None
        assert len(o.ref_text) > len(o.value_text)

    def test_range_valued_microscopy(self, by_code, expected):
        o = observation_on(by_code, "urine_leukocytes_micro", expected.latest)
        assert o.value_text == expected.text("urine_leukocytes_micro", expected.latest)
        # A range-valued result stays textual, while its reference is numeric.
        assert o.value_num is None
        assert "value_is_range" in o.flags
        assert (o.ref_low, o.ref_high) == (0.0, 5.0)


class TestNameCollisions:
    """The three LEUCOCITOS and two each of HEMOGLOBINA/GLUCOSA stay distinct."""

    def test_three_distinct_leukocyte_analytes(self, by_code, expected):
        draw = expected.latest
        for code in ("wbc", "urine_leukocytes_chem", "urine_leukocytes_micro"):
            assert code in by_code, code
        # Same printed name, three different shapes of result.
        assert observation_on(by_code, "wbc", draw).value_num is not None
        assert observation_on(by_code, "urine_leukocytes_chem", draw).value_num is None
        assert observation_on(by_code, "urine_leukocytes_micro", draw).value_num is None
        for code in ("wbc", "urine_leukocytes_chem", "urine_leukocytes_micro"):
            o = observation_on(by_code, code, draw)
            assert (o.value_num, o.value_text) == (
                expected.num(code, draw),
                expected.text(code, draw),
            )

    def test_haemoglobin_split(self, by_code, expected):
        draw = expected.latest
        blood = observation_on(by_code, "hemoglobin", draw)
        urine = observation_on(by_code, "urine_hemoglobin", draw)
        assert blood.panel == "HEMOGRAMA"
        assert urine.sub_section == "quimico"
        assert blood.value_num == expected.num("hemoglobin", draw)
        assert urine.value_text == expected.text("urine_hemoglobin", draw)

    def test_glucose_split(self, by_code, expected):
        draw = expected.latest
        blood = observation_on(by_code, "glucose", draw)
        urine = observation_on(by_code, "urine_glucose", draw)
        assert blood.panel == "PERFIL BIOQUIMICO"
        assert urine.sub_section == "quimico"
        assert blood.value_num == expected.num("glucose", draw)
        assert urine.value_text == expected.text("urine_glucose", draw)

    def test_blood_glucose_differs_between_draws(self, by_code, expected):
        """Guards against a per-draw value being reused across reports."""
        values = [
            observation_on(by_code, "glucose", d).value_num
            for d in expected.draws
            if any(str(o.sample_date) == d for o in by_code["glucose"])
        ]
        assert len(set(values)) > 1


class TestDifferential:
    """Percentage and absolute count become separate analytes."""

    def test_neutrophils_split(self, by_code, expected):
        draw = expected.latest
        pct = observation_on(by_code, "neutrophils_pct", draw)
        abs_ = observation_on(by_code, "neutrophils_abs", draw)
        assert pct.value_num == expected.num("neutrophils_pct", draw)
        assert abs_.value_num == expected.num("neutrophils_abs", draw)
        # A percentage and a per-microlitre count cannot be the same number.
        assert pct.value_num != abs_.value_num
        assert abs_.value_num > pct.value_num

    def test_ran_is_segmented_plus_bands(self, by_code):
        """R.A.N. counts segmented and band neutrophils, so it is its own analyte.

        It only equals the `Segmentados` absolute count while bands are 0%.
        """
        draws = {str(o.sample_date) for o in by_code["neutrophils_total_abs"]}
        assert draws, "R.A.N. was not captured"
        for draw in sorted(draws):
            total = observation_on(by_code, "neutrophils_total_abs", draw).value_num
            segmented = observation_on(by_code, "neutrophils_abs", draw).value_num
            bands_pct = observation_on(by_code, "band_neutrophils_pct", draw).value_num
            wbc_per_ul = observation_on(by_code, "wbc", draw).value_num * 1000
            # Printed percentages are whole numbers, so allow 1% of the WBC count.
            assert abs(total - (segmented + bands_pct / 100 * wbc_per_ul)) <= 0.01 * wbc_per_ul

    def test_percentage_owns_the_reference_and_absolute_does_not(self, by_code, expected):
        draw = expected.latest
        pct = observation_on(by_code, "neutrophils_pct", draw)
        abs_ = observation_on(by_code, "neutrophils_abs", draw)
        # The printed range describes the percentage; the printed unit the count.
        assert (pct.ref_low, pct.ref_high) == (50.0, 75.0)
        assert pct.unit == "%"
        # The absolute count must never be compared against a percentage range.
        assert abs_.ref_low is None and abs_.ref_high is None
        assert abs_.out_of_range is None
        assert abs_.unit == "/uL"

    def test_every_differential_absolute_lacks_a_range(self, by_code):
        for code in ("neutrophils_abs", "lymphocytes_abs", "monocytes_abs",
                     "eosinophils_abs", "basophils_abs"):
            for o in by_code[code]:
                assert o.ref_low is None and o.ref_high is None, code
                assert o.unit == "/uL", code

    def test_esr_value_recovered_from_the_absolute_column(self, by_code, expected):
        """V.H.S prints its only value under the absolute-count column."""
        o = observation_on(by_code, "esr", expected.latest)
        assert o.value_num == expected.num("esr", expected.latest)
        assert o.value_num is not None


class TestAsteriskCrossCheck:
    """out_of_range is computed; the printed asterisk is only corroboration."""

    def test_out_of_range_is_computed_not_copied(self, by_code, expected):
        o = observation_on(by_code, "urine_ph", expected.latest)
        # This lab does not asterisk every out-of-range result.
        assert (o.ref_low, o.ref_high) == (5.0, 7.0)
        assert o.value_num > o.ref_high
        assert o.out_of_range is True
        assert o.asterisk_flag is False
        assert "asterisk_range_mismatch" in o.flags
        assert o.confidence == "suspect"

    def test_agreement_produces_no_flag(self, by_code, expected):
        o = observation_on(by_code, "ggt", expected.latest)
        assert o.asterisk_flag is True and o.out_of_range is True
        assert "asterisk_range_mismatch" not in o.flags

    def test_mismatch_never_silently_accepted(self, parsed):
        for o in parsed[0]:
            if o.out_of_range is not None and o.asterisk_flag != o.out_of_range:
                assert "asterisk_range_mismatch" in o.flags
                assert o.confidence == "suspect"


class TestCrossPanelDedup:
    """Analytes printed in two panels collapse to one row."""

    @pytest.mark.parametrize(
        "code", ["cholesterol_total", "alkaline_phosphatase", "bilirubin_total", "ast"]
    )
    def test_single_row_per_draw(self, by_code, expected, code):
        for draw in expected.draws:
            rows = [o for o in by_code[code] if str(o.sample_date) == draw]
            assert len(rows) <= 1, f"{code} duplicated on {draw}"

    def test_other_panel_is_recorded(self, by_code, expected):
        assert observation_on(by_code, "cholesterol_total", expected.latest).also_in_panels

    def test_obs_keys_are_unique(self, parsed):
        keys = [o.obs_key for o in parsed[0]]
        assert len(keys) == len(set(keys))


class TestStore:
    def test_ingest_is_idempotent_and_preserves_verification(self, tmp_path, catalog, parsed):
        observations, _ = parsed
        con = connect(tmp_path / "test.duckdb")
        seed_analytes(con, catalog)

        by_file: dict[str, list] = {}
        for o in observations:
            by_file.setdefault(o.file_hash, []).append(o)

        def load_all():
            for fhash, obs in by_file.items():
                write_report(
                    con,
                    file_hash=fhash,
                    source_file=obs[0].source_file,
                    cod_lis=obs[0].cod_lis,
                    sample_date=obs[0].sample_date,
                    lab_name=obs[0].lab_name,
                    page_count=10,
                    observations=obs,
                )

        load_all()
        first = con.execute("SELECT count(*) FROM observations").fetchone()[0]
        assert first == len(observations)
        assert report_exists(con, next(iter(by_file)))

        # Mark one row verified, then re-ingest everything.
        key = observations[0].obs_key
        con.execute(
            "INSERT INTO overrides VALUES (?, true, NULL, NULL, 'checked', now())", [key]
        )
        load_all()

        assert con.execute("SELECT count(*) FROM observations").fetchone()[0] == first
        verified = con.execute(
            "SELECT verified FROM v_observations WHERE obs_key = ?", [key]
        ).fetchone()[0]
        assert verified is True, "verification must survive a forced re-ingest"
        con.close()

    def test_review_csv_round_trip(self, tmp_path, catalog, parsed):
        observations, _ = parsed
        con = connect(tmp_path / "rt.duckdb")
        seed_analytes(con, catalog)
        first_hash = observations[0].file_hash
        subset = [o for o in observations if o.file_hash == first_hash]
        write_report(
            con,
            file_hash=first_hash,
            source_file=subset[0].source_file,
            cod_lis=subset[0].cod_lis,
            sample_date=subset[0].sample_date,
            lab_name=subset[0].lab_name,
            page_count=10,
            observations=subset,
        )

        path, rows = export_review(con, tmp_path)
        assert rows == len(subset) and path.exists()

        text = path.read_text(encoding="utf-8").splitlines()
        header = text[0].split(",")
        assert {"obs_key", "verified", "value_num", "value_text", "note"} <= set(header)

        # An untouched CSV must produce no overrides.
        assert import_review(con, path) == (0, 0)

        # Marking one row verified must produce exactly one override.
        cells = text[1].split(",")
        cells[header.index("verified")] = "true"
        text[1] = ",".join(cells)
        edited = tmp_path / "edited.csv"
        edited.write_text("\n".join(text), encoding="utf-8")

        assert import_review(con, edited) == (1, 0)
        con.close()
