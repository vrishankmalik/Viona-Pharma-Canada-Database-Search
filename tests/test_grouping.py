"""Unit tests for ingredient-combination grouping logic (no network required)."""
import pytest
from app.grouping import (
    COMBINATION_SEPARATOR,
    UNKNOWN_GROUP,
    combination_label,
    group_records,
    make_combination_key,
)
from app.models import DrugRecord


def _rec(all_ingredients=None, ingredient=None, source="DPD", company=None):
    return DrugRecord(
        source=source,
        all_ingredients=all_ingredients or [],
        ingredient=ingredient,
        company=company,
    )


# ---- make_combination_key ----

def test_key_uses_all_ingredients():
    r = _rec(all_ingredients=["ACETAMINOPHEN", "DIPHENHYDRAMINE HCL"])
    assert make_combination_key(r) == ("ACETAMINOPHEN", "DIPHENHYDRAMINE HCL")


def test_key_sorts_alphabetically():
    r = _rec(all_ingredients=["IBUPROFEN", "ACETAMINOPHEN"])
    assert make_combination_key(r) == ("ACETAMINOPHEN", "IBUPROFEN")


def test_key_normalizes_casing_and_whitespace():
    r1 = _rec(all_ingredients=["acetaminophen", "  DIPHENHYDRAMINE  HCL  "])
    r2 = _rec(all_ingredients=["ACETAMINOPHEN", "DIPHENHYDRAMINE HCL"])
    assert make_combination_key(r1) == make_combination_key(r2)


def test_key_deduplicates():
    r = _rec(all_ingredients=["ACETAMINOPHEN", "ACETAMINOPHEN"])
    assert make_combination_key(r) == ("ACETAMINOPHEN",)


def test_key_falls_back_to_ingredient_string():
    r = _rec(ingredient="ACETAMINOPHEN; DIPHENHYDRAMINE HCL")
    assert make_combination_key(r) == ("ACETAMINOPHEN", "DIPHENHYDRAMINE HCL")


def test_key_empty_when_no_ingredients():
    r = _rec()
    assert make_combination_key(r) == ()


# ---- combination_label ----

def test_label_joins_with_separator():
    key = ("ACETAMINOPHEN", "DIPHENHYDRAMINE HCL")
    assert combination_label(key) == "ACETAMINOPHEN" + COMBINATION_SEPARATOR + "DIPHENHYDRAMINE HCL"


def test_label_single():
    assert combination_label(("METFORMIN HYDROCHLORIDE",)) == "METFORMIN HYDROCHLORIDE"


def test_label_empty_key_returns_unknown():
    assert combination_label(()) == UNKNOWN_GROUP


# ---- group_records ----

def test_three_groups_correct_membership():
    """Searching ACETAMINOPHEN returns products with {A}, {A+D}, {A+I} — exactly 3 groups."""
    records = [
        _rec(all_ingredients=["ACETAMINOPHEN"]),
        _rec(all_ingredients=["ACETAMINOPHEN"]),
        _rec(all_ingredients=["ACETAMINOPHEN", "DIPHENHYDRAMINE HCL"]),
        _rec(all_ingredients=["ACETAMINOPHEN", "IBUPROFEN"]),
    ]
    groups = group_records(records, searched_ingredient="ACETAMINOPHEN")
    assert len(groups) == 3
    by_label = {g.label: g.product_count for g in groups}
    assert by_label["ACETAMINOPHEN"] == 2
    assert by_label["ACETAMINOPHEN" + COMBINATION_SEPARATOR + "DIPHENHYDRAMINE HCL"] == 1
    assert by_label["ACETAMINOPHEN" + COMBINATION_SEPARATOR + "IBUPROFEN"] == 1


def test_ab_and_ba_collapse_into_one_group():
    """{A, B} and {B, A} must produce exactly one group."""
    records = [
        _rec(all_ingredients=["ACETAMINOPHEN", "DIPHENHYDRAMINE HCL"]),
        _rec(all_ingredients=["DIPHENHYDRAMINE HCL", "ACETAMINOPHEN"]),
    ]
    groups = group_records(records)
    assert len(groups) == 1
    assert groups[0].product_count == 2


def test_exact_ingredient_group_sorts_first():
    """Exact single-ingredient group appears before larger combos when searched."""
    records = [
        _rec(all_ingredients=["ACETAMINOPHEN", "IBUPROFEN"]),
        _rec(all_ingredients=["ACETAMINOPHEN", "IBUPROFEN"]),
        _rec(all_ingredients=["ACETAMINOPHEN"]),
        _rec(all_ingredients=["ACETAMINOPHEN", "DIPHENHYDRAMINE HCL"]),
    ]
    groups = group_records(records, searched_ingredient="ACETAMINOPHEN")
    assert groups[0].label == "ACETAMINOPHEN"


def test_no_searched_ingredient_sorts_by_count_desc():
    records = [
        _rec(all_ingredients=["B"]),
        _rec(all_ingredients=["A"]),
        _rec(all_ingredients=["A"]),
        _rec(all_ingredients=["A"]),
    ]
    groups = group_records(records)
    assert groups[0].label == "A"
    assert groups[0].product_count == 3


def test_missing_ingredients_go_to_unknown_group():
    """Records with no ingredient data land in UNKNOWN group rather than being dropped."""
    records = [_rec(), _rec(all_ingredients=["ASPIRIN"])]
    groups = group_records(records)
    labels = {g.label for g in groups}
    assert UNKNOWN_GROUP in labels
    total = sum(g.product_count for g in groups)
    assert total == 2


def test_company_count():
    records = [
        _rec(all_ingredients=["METFORMIN"], company="Apotex"),
        _rec(all_ingredients=["METFORMIN"], company="Teva"),
        _rec(all_ingredients=["METFORMIN"], company="Apotex"),
    ]
    groups = group_records(records)
    assert len(groups) == 1
    assert groups[0].company_count == 2
    assert groups[0].companies == ["Apotex", "Teva"]
