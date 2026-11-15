"""Unit tests for value, reference and name normalisation."""

from __future__ import annotations

import pytest

from examenes.extract import is_hidden
from examenes.normalize import (
    compute_out_of_range,
    normalize_key,
    parse_reference,
    parse_value,
)
from examenes.panels import (
    is_note_start,
    is_skippable,
    is_stop,
    parse_chilean_date,
    starts_with_value,
    sub_section_of,
)


class TestHiddenText:
    """White scaffolding must be dropped; real content must never be."""

    @pytest.mark.parametrize(
        "color,expected",
        [
            ((1.0, 1.0, 1.0), True),   # RGB white
            ((1.0,), True),            # greyscale white
            ((0.0,), False),           # greyscale black
            ((0,), False),             # integer black
            ((0.0, 0.0, 0.0), False),  # RGB black
            ((0.0, 0.0, 0.0, 0.0), True),   # CMYK white is no ink
            ((0.0, 0.0, 0.0, 1.0), False),  # CMYK black
            (None, False),             # unknown colour is treated as visible
            ((), False),
        ],
    )
    def test_is_hidden(self, color, expected):
        assert is_hidden(color) is expected


class TestChileanDates:
    """Reports print D/M/YY, so 4/2/24 is 4 February 2024, not 2 April."""

    @pytest.mark.parametrize(
        "text,iso",
        [
            # Ambiguous pairs: both fields <= 12, so ordering is what is tested.
            ("Toma Muestra : 4/2/24 8:11", "2024-02-04"),
            ("Toma Muestra : 11/1/23 8:16", "2023-01-11"),
            ("Toma Muestra : 10/5/23 9:32", "2023-05-10"),
            ("Toma Muestra : 8/11/22 9:15", "2022-11-08"),
            # Unambiguous: day > 12 can only be read one way.
            ("Toma Muestra : 25/12/22 7:05", "2022-12-25"),
            ("F.Nac : 15/03/1985", "1985-03-15"),
            # Two-digit years pivot at 70.
            ("F.Nac : 1/1/69", "2069-01-01"),
            ("F.Nac : 1/1/70", "1970-01-01"),
        ],
    )
    def test_day_first(self, text, iso):
        assert parse_chilean_date(text).isoformat() == iso

    def test_invalid_date_returns_none(self):
        assert parse_chilean_date("Toma Muestra : 45/99/26") is None

    def test_no_date_returns_none(self):
        assert parse_chilean_date("Muestra : Suero") is None


class TestParseValue:
    def test_plain_number(self):
        v = parse_value("2.18")
        assert v.value_num == 2.18
        assert v.value_text is None
        assert v.asterisk is False
        assert v.flags == ()

    @pytest.mark.parametrize("cell,num", [("* 3.7", 3.7), ("*1.012", 1.012), ("*  14", 14.0)])
    def test_asterisk_is_stripped_before_parsing(self, cell, num):
        v = parse_value(cell)
        assert v.value_num == num
        assert v.asterisk is True

    def test_colon_prefixed_value(self):
        # One PERFIL HEPATICO row prints its value after a colon rather than in
        # the plain `name value` shape.
        assert parse_value(": 0.44").value_num == 0.44

    def test_qualitative_text_never_becomes_a_number(self):
        v = parse_value("Muy escasas")
        assert v.value_num is None
        assert v.value_text == "Muy escasas"
        assert "value_is_text" in v.flags

    def test_range_valued_result(self):
        v = parse_value("0 - 2")
        assert v.value_num is None
        assert v.value_text == "0 - 2"
        assert "value_is_range" in v.flags

    def test_bounded_result(self):
        v = parse_value("<0.01")
        assert v.value_num is None
        assert v.value_text == "<0.01"
        assert "value_is_bounded" in v.flags

    def test_empty(self):
        v = parse_value("")
        assert v.value_num is None and v.value_text is None
        assert "empty_value" in v.flags


class TestParseReference:
    @pytest.mark.parametrize(
        "cell,low,high",
        [
            ("50 - 200", 50.0, 200.0),
            ("15-85", 15.0, 85.0),
            ("1.015- 1.025", 1.015, 1.025),
            ("16.0-63.0", 16.0, 63.0),
            ("3.4 - 5", 3.4, 5.0),
        ],
    )
    def test_dash_spacing_variants(self, cell, low, high):
        r = parse_reference(cell)
        assert (r.ref_low, r.ref_high, r.ref_operator) == (low, high, "range")

    @pytest.mark.parametrize("cell,low,high", [("46 116", 46.0, 116.0), ("5.0 37.0", 5.0, 37.0)])
    def test_range_printed_without_a_dash(self, cell, low, high):
        # PERFIL HEPATICO prints some ranges with no dash at all.
        r = parse_reference(cell)
        assert (r.ref_low, r.ref_high) == (low, high)
        assert "ref_missing_dash" in r.flags

    @pytest.mark.parametrize(
        "cell,op,low,high",
        [
            ("< 150", "lt", None, 150.0),
            ("<= 150", "lte", None, 150.0),
            (">= 60", "gte", 60.0, None),
            (">5.38", "gt", 5.38, None),
        ],
    )
    def test_single_bounds(self, cell, op, low, high):
        r = parse_reference(cell)
        assert (r.ref_operator, r.ref_low, r.ref_high) == (op, low, high)

    def test_range_with_trailing_description(self):
        r = parse_reference("0-5 por campo (40x)")
        assert (r.ref_low, r.ref_high) == (0.0, 5.0)
        assert r.ref_text == "0-5 por campo (40x)"
        assert "ref_has_trailing_text" in r.flags

    @pytest.mark.parametrize("cell", ["Negativo", "Escasa Cantidad", "No se observan", "Normal"])
    def test_textual_reference(self, cell):
        r = parse_reference(cell)
        assert r.ref_operator == "text"
        assert r.ref_text == cell
        assert r.ref_low is None and r.ref_high is None

    def test_long_descriptive_reference_is_not_mined_for_numbers(self):
        r = parse_reference("No se observan o escasa cantidad por campo en C. hialino(10x)")
        assert r.ref_operator == "text"
        assert r.ref_low is None

    def test_empty(self):
        r = parse_reference("")
        assert r.ref_operator == "none"
        assert "no_reference" in r.flags


class TestOutOfRange:
    @pytest.mark.parametrize(
        "value,cell,expected",
        [
            (8.5, "5.0 - 7.0", True),
            (6.0, "5.0 - 7.0", False),
            (5.0, "5.0 - 7.0", False),
            (119, "< 150", False),
            (160, "< 150", True),
            (50, ">= 60", True),
            (70, ">= 60", False),
        ],
    )
    def test_computed_from_numbers(self, value, cell, expected):
        assert compute_out_of_range(value, parse_reference(cell)) is expected

    def test_undecidable_without_numeric_reference(self):
        assert compute_out_of_range(1.0, parse_reference("Negativo")) is None
        assert compute_out_of_range(None, parse_reference("1 - 2")) is None


class TestNormalizeKey:
    @pytest.mark.parametrize(
        "raw,key",
        [
            ("BILIRRUBINA INDIRECTA.", "BILIRRUBINA INDIRECTA"),
            ("DESHIDROGENASA LACTICA (LDH).", "DESHIDROGENASA LACTICA (LDH)"),
            ("Deshidrogenasa  Láctica (LDH)", "DESHIDROGENASA LACTICA (LDH)"),
            ("pH", "PH"),
            ("  Segmentados  ", "SEGMENTADOS"),
        ],
    )
    def test_folding(self, raw, key):
        assert normalize_key(raw) == key


class TestPageStructure:
    @pytest.mark.parametrize(
        "line",
        [
            "GUIA PARA LA INTERPRETACION DEL PERFIL LIPIDICO",
            "CARACTERISTICAS MORFOLOGICAS",
            "Ejecutado y Emitido por: T.M NOMBRE APELLIDO 4/2/24 15:40",
            "Ejecutado y emitido por: T.M NOMBRE APELLIDO",
            "PUNTAJE INDICE FIB 4 INTERPRETACIÓN",
            "VALOR DE REFERENCIA:",
        ],
    )
    def test_stop_markers(self, line):
        assert is_stop(line)

    def test_nota_does_not_stop_the_table(self):
        # `INDICE FIB 4` is a real result printed *below* a Nota line.
        line = "Nota : Valores de referencia actualizados el 08.05.2025."
        assert not is_stop(line)
        assert is_skippable(line)

    def test_nota_opens_a_note(self):
        assert is_note_start("Nota: Conforme al Oficio CP N° 1 (2026), se informa que")
        assert not is_note_start("HEMOGLOBINA 14.4 gr/dL")

    @pytest.mark.parametrize(
        "cell,expected",
        [
            ("28.0", True),
            ("* 1.17", True),
            ("< 0.5", True),
            ("-1.2", True),
            (": 0.44", True),  # INDICE FIB 4 prints its value after a colon
            ("en reemplazo", False),  # wrapped Nota prose split into the value column
            ("de 2026.", False),
            ("Negativo", False),
            ("", False),
            (None, False),
        ],
    )
    def test_starts_with_value(self, cell, expected):
        assert starts_with_value(cell) is expected

    @pytest.mark.parametrize(
        "line,code",
        [
            ("EXAMEN FÍSICO:", "fisico"),
            ("EXAMEN QUÍMICO:", "quimico"),
            ("ANÁLISIS ELEMENTOS FIGURADOS:", "elementos_figurados"),
            ("HEMOGLOBINA 14.4 gr/dL", None),
        ],
    )
    def test_sub_sections(self, line, code):
        assert sub_section_of(line) == code
