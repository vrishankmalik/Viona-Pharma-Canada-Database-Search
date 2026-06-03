"""Tier 5 — Normalization & join unit tests (offline, pure functions).

No network, no fixtures — just function calls.
"""
import pytest

from app.din_utils import normalize_din, parse_dins, is_valid_din
from app.grouping import make_combination_key, combination_label, group_records, COMBINATION_SEPARATOR
from app.join import join_by_din, MasterRow
from app.models import DrugRecord
from app.normalize import _static_synonyms


# ── DIN normalization ─────────────────────────────────────────────────────────

class TestNormalizeDIN:
    def test_7digit_zero_padded(self):
        assert normalize_din("2252805") == "02252805"

    def test_8digit_unchanged(self):
        assert normalize_din("02252805") == "02252805"

    def test_strips_non_digits(self):
        assert normalize_din("02,535,742") == "02535742"

    def test_strips_spaces(self):
        assert normalize_din("  0222 9895  ") == "02229895"

    def test_empty_returns_none(self):
        assert normalize_din("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_din("   ") is None

    def test_non_numeric_returns_none(self):
        assert normalize_din("N/A") is None

    def test_6digit_pads_to_8(self):
        assert normalize_din("123456") == "00123456"


class TestParseDINs:
    def test_single_din(self):
        assert parse_dins("02229895") == ["02229895"]

    def test_semicolon_separated(self):
        result = parse_dins("02229895; 02229896")
        assert result == ["02229895", "02229896"]

    def test_comma_semicolon_mixed(self):
        result = parse_dins("02535742,; 02535750,; 02535734")
        assert result == ["02535742", "02535750", "02535734"]

    def test_none_returns_empty(self):
        assert parse_dins(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_dins("") == []

    def test_whitespace_only_returns_empty(self):
        assert parse_dins("   ") == []

    def test_pads_short_dins(self):
        result = parse_dins("2229895")
        assert result == ["02229895"]

    def test_skips_empty_segments(self):
        result = parse_dins(",;,;02229895,;,;")
        assert result == ["02229895"]


class TestIsValidDIN:
    def test_8_digits_valid(self):
        assert is_valid_din("02229895") is True

    def test_7_digits_invalid(self):
        assert is_valid_din("2229895") is False

    def test_9_digits_invalid(self):
        assert is_valid_din("022298950") is False

    def test_with_letters_invalid(self):
        assert is_valid_din("0222989X") is False

    def test_all_zeros_valid(self):
        assert is_valid_din("00000000") is True


# ── Ingredient normalization ──────────────────────────────────────────────────

class TestIngredientNormalization:
    def test_acetaminophen_synonyms(self):
        syns = _static_synonyms("acetaminophen")
        assert "paracetamol" in syns

    def test_paracetamol_synonyms(self):
        syns = _static_synonyms("paracetamol")
        assert "acetaminophen" in syns

    def test_case_insensitive_lookup(self):
        syns = _static_synonyms("ACETAMINOPHEN")
        # _static_synonyms uses .lower() internally via normalize_ingredient
        # Direct call uses key.lower()
        syns2 = _static_synonyms("acetaminophen")
        assert syns == syns2

    def test_unknown_ingredient_returns_empty(self):
        assert _static_synonyms("zzznodrug") == []

    def test_metformin_to_salt(self):
        syns = _static_synonyms("metformin")
        assert "metformin hydrochloride" in syns

    def test_salt_to_base(self):
        syns = _static_synonyms("metformin hydrochloride")
        assert "metformin" in syns


# ── Combination key ───────────────────────────────────────────────────────────

class TestCombinationKey:
    def _rec(self, all_ingredients=None, ingredient=None) -> DrugRecord:
        return DrugRecord(
            source="DPD",
            all_ingredients=all_ingredients or [],
            ingredient=ingredient,
        )

    def test_ab_and_ba_same_key(self):
        r1 = self._rec(all_ingredients=["B", "A"])
        r2 = self._rec(all_ingredients=["A", "B"])
        assert make_combination_key(r1) == make_combination_key(r2)

    def test_sorted_alphabetically(self):
        r = self._rec(all_ingredients=["ZOLOFT", "ACETAMINOPHEN"])
        key = make_combination_key(r)
        assert key == ("ACETAMINOPHEN", "ZOLOFT")

    def test_deduplication(self):
        r = self._rec(all_ingredients=["ACETAMINOPHEN", "ACETAMINOPHEN"])
        assert make_combination_key(r) == ("ACETAMINOPHEN",)

    def test_normalizes_casing(self):
        r1 = self._rec(all_ingredients=["acetaminophen"])
        r2 = self._rec(all_ingredients=["ACETAMINOPHEN"])
        assert make_combination_key(r1) == make_combination_key(r2)

    def test_normalizes_extra_whitespace(self):
        r1 = self._rec(all_ingredients=["  ACETAMINOPHEN  "])
        r2 = self._rec(all_ingredients=["ACETAMINOPHEN"])
        assert make_combination_key(r1) == make_combination_key(r2)

    def test_fallback_to_ingredient_string(self):
        r = self._rec(ingredient="NORETHINDRONE; MESTRANOL")
        key = make_combination_key(r)
        assert "NORETHINDRONE" in key
        assert "MESTRANOL" in key

    def test_empty_record_returns_empty_tuple(self):
        assert make_combination_key(self._rec()) == ()


# ── DIN join ─────────────────────────────────────────────────────────────────

class TestDINJoin:
    def _dpd(self, din: str, brand: str) -> DrugRecord:
        return DrugRecord(source="DPD", din=din, brand_name=brand, all_ingredients=["METFORMIN"])

    def _noc(self, din: str, noc_date: str) -> DrugRecord:
        return DrugRecord(
            source="NOC", din=din, brand_name="GLUCOPHAGE",
            all_ingredients=["METFORMIN"], source_specific={"noc_date": noc_date},
        )

    def test_shared_din_merges_into_one_row(self):
        records = [self._dpd("02229895", "GLUCOPHAGE"), self._noc("02229895", "1972-12-31")]
        rows = join_by_din(records)
        din_rows = [r for r in rows if r.din == "02229895"]
        assert len(din_rows) == 1
        assert din_rows[0].dpd_record is not None
        assert len(din_rows[0].noc_records) == 1

    def test_shared_din_match_method_is_exact(self):
        records = [self._dpd("02229895", "X"), self._noc("02229895", "2000-01-01")]
        rows = join_by_din(records)
        assert rows[0].match_method == "exact_din"

    def test_one_to_many_noc_events(self):
        """A DIN with 3 NOC events produces one MasterRow with noc_count=3."""
        records = [
            self._dpd("02229895", "GLUCOPHAGE"),
            self._noc("02229895", "1972-12-31"),
            self._noc("02229895", "1980-01-01"),
            self._noc("02229895", "1995-06-15"),
        ]
        rows = join_by_din(records)
        assert len(rows) == 1
        row = rows[0]
        assert row.noc_count == 3

    def test_latest_noc_date_correct(self):
        records = [
            self._noc("02229895", "1972-12-31"),
            self._noc("02229895", "1995-06-15"),
            self._noc("02229895", "1980-01-01"),
        ]
        rows = join_by_din(records)
        assert rows[0].latest_noc_date == "1995-06-15"

    def test_all_noc_dates_sorted(self):
        records = [
            self._noc("02229895", "1995-06-15"),
            self._noc("02229895", "1972-12-31"),
            self._noc("02229895", "1980-01-01"),
        ]
        rows = join_by_din(records)
        assert rows[0].all_noc_dates == ["1972-12-31", "1980-01-01", "1995-06-15"]

    def test_din_less_row_stays_standalone_and_is_never_dropped(self):
        """A record with no DIN must appear as a standalone row, never silently dropped."""
        records = [
            self._dpd("02229895", "GLUCOPHAGE"),
            DrugRecord(source="GenericSubmissions", din=None, ingredient="METFORMIN"),
        ]
        rows = join_by_din(records)
        din_less = [r for r in rows if r.din == ""]
        assert len(din_less) == 1
        assert din_less[0].match_method == "no_din"
        total_records = sum(
            (1 if r.dpd_record else 0) + len(r.noc_records) + len(r.gsur_records)
            for r in rows
        )
        assert total_records == 2, "No record should be silently dropped"

    def test_partial_din_row_match_method(self):
        records = [self._dpd("02229895", "GLUCOPHAGE")]
        rows = join_by_din(records)
        assert rows[0].match_method == "partial"

    def test_different_dins_stay_separate(self):
        records = [self._dpd("02229895", "A"), self._dpd("02282291", "B")]
        rows = join_by_din(records)
        assert len(rows) == 2


# ── Fuzzy linkage (Patent Register ingredient matching) ───────────────────────

class TestFuzzyLinkage:
    def test_close_match_found(self):
        from app.sources.patent_register import _find_matching_options
        opts = ["METFORMIN HYDROCHLORIDE", "METFORMIN HYDROCHLORIDE / CANAGLIFLOZIN", "INSULIN GLARGINE"]
        result = _find_matching_options("metformin", opts)
        assert len(result) >= 1
        assert "METFORMIN HYDROCHLORIDE" in result

    def test_distant_term_not_matched(self):
        from app.sources.patent_register import _find_matching_options
        opts = ["METFORMIN HYDROCHLORIDE", "INSULIN GLARGINE", "ADALIMUMAB"]
        result = _find_matching_options("xyzabc", opts)
        assert result == []

    def test_exact_substring_caseinsensitive(self):
        from app.sources.patent_register import _find_matching_options
        opts = ["NORETHINDRONE", "NORETHINDRONE / ETHINYL ESTRADIOL"]
        result = _find_matching_options("norethindrone", opts)
        assert "NORETHINDRONE" in result
