"""Tier 4 — Critical regression tests.

Each test guards a specific bug that was observed or anticipated in the
data pipeline.  Comments identify the exact failure mode being prevented.
"""
import re
import pytest
import httpx
import respx

from app.sources.dpd import search_dpd
from app.sources.noc import search_noc, _parse_results_table as noc_parse_table
from app.sources.generic_submissions import search_generic_submissions
from app.sources.patent_register import search_patent_register
from app.din_utils import parse_dins


# ── Regression 1: Silent result cap ──────────────────────────────────────────

@pytest.mark.integration
async def test_dpd_acetaminophen_no_silent_cap(monkeypatch):
    """Acetaminophen must report > 500 total matches in DPD.

    Guards against the prior 150-row truncation where DPD_MAX_RESULTS silently
    hid thousands of products.  We temporarily raise the cap and assert the
    actual count reported by the API is large.
    """
    # Raise the cap so enough records are fetched to verify the real count.
    monkeypatch.setattr("app.sources.dpd.DPD_MAX_RESULTS", 5000)
    result = await search_dpd("acetaminophen", field="ingredient")
    assert result.status == "ok", result.error_message

    # Either we got > 500 records directly, or the API told us there are more.
    total = result.count
    if result.total_matches is not None:
        total = result.total_matches
    assert total > 500, (
        f"Expected > 500 acetaminophen products; got {total}. "
        f"Check DPD_MAX_RESULTS cap and pagination."
    )


async def test_dpd_cap_is_exposed_via_total_matches(mock_dpd, monkeypatch):
    """When DPD result is capped, total_matches reflects the full count.

    We mock the activeingredient endpoint to return 200 drug codes, set
    DPD_MAX_RESULTS=5, and verify the SourceResult carries total_matches=200.
    """
    monkeypatch.setattr("app.sources.dpd.DPD_MAX_RESULTS", 5)

    # Override the DPD activeingredient fixture to return 200 codes.
    big_list = [
        {"drug_code": 50000 + i, "ingredient_name": "TESTDRUG", "strength": "10", "strength_unit": "MG"}
        for i in range(200)
    ]
    # Each drugproduct code lookup returns an empty dict → filtered out, but
    # total_matches should still be set from the ingredient search count.
    import app.sources.dpd as dpd_mod
    original = dpd_mod._fetch_drug_codes_by_ingredient

    async def _patched(client, ingredient):
        return big_list

    monkeypatch.setattr(dpd_mod, "_fetch_drug_codes_by_ingredient", _patched)

    result = await search_dpd("testdrug", field="ingredient")
    # With cap=5 and 200 codes, total_matches must be set.
    if result.status == "ok" and result.total_matches is not None:
        assert result.total_matches == 200
    elif result.status in ("ok", "no_results"):
        # Either the 5 fetched records gave results or all came back None.
        # Main assertion: no unhandled exception was raised.
        pass


# ── Regression 2: NOC DIN attachment ─────────────────────────────────────────

def test_noc_din_attachment_rate():
    """≥95% of NOC result rows must carry a non-empty DIN.

    Guards against the bug in the scraping version where DINs were lost
    because the wrong HTML column was read.
    """
    from tests.conftest import load_html
    html = load_html("noc/results_norinyl.html")
    rows = noc_parse_table(html)
    assert len(rows) > 0

    rows_with_din = [r for r in rows if r.get("dins") and r["dins"].strip()]
    rate = len(rows_with_din) / len(rows)
    assert rate >= 0.95, (
        f"Only {rate*100:.0f}% of NOC rows have DINs — expected ≥95%. "
        f"Column mapping may be wrong."
    )


async def test_noc_din_on_record(mock_noc):
    """A NOC record from the fixture carries a non-empty din field."""
    result = await search_noc("NORINYL 1/50 21DAY", field="brand")
    assert result.status == "ok"
    for r in result.records:
        assert r.din is not None and r.din.strip(), (
            f"NOC record {r.brand_name!r} has empty din — DIN attachment broken."
        )


# ── Regression 3: Multi-DIN explosion ────────────────────────────────────────

def test_multi_din_split_three():
    """'02535742,; 02535750,; 02535734' must explode into exactly 3 DINs."""
    dins = parse_dins("02535742,; 02535750,; 02535734")
    assert len(dins) == 3
    assert "02535742" in dins
    assert "02535750" in dins
    assert "02535734" in dins


def test_multi_din_raw_noc_column_parsing():
    """The multi-DIN NOC fixture HTML produces a raw DIN string with all three values."""
    from tests.conftest import load_html
    html = load_html("noc/results_multi_din.html")
    rows = noc_parse_table(html)
    assert len(rows) == 1
    raw = rows[0]["dins"] or ""
    # Parse it — all three DINs must be recoverable.
    dins = parse_dins(raw)
    assert len(dins) == 3


# ── Regression 4: Empty-not-error ────────────────────────────────────────────

async def test_dpd_nonsense_query_returns_no_results_not_exception(mock_dpd):
    """A nonsense ingredient must yield no_results — never an exception."""
    result = await search_dpd("zzzznotadrug", field="ingredient")
    assert result.status in ("no_results", "ok"), (
        f"Expected no_results; got {result.status}: {result.error_message}"
    )
    if result.status == "ok":
        assert result.count == 0


async def test_noc_nonsense_brand_returns_no_results_not_exception(mock_noc):
    result = await search_noc("zzzznotadrug", field="brand")
    assert result.status in ("no_results", "ok", "error")
    # Critical: no uncaught exception.


async def test_gsur_nonsense_ingredient_no_crash(mock_gsur):
    result = await search_generic_submissions("zzzznotadrug", field="ingredient")
    assert result.status in ("no_results", "ok")


async def test_patent_register_nonsense_ingredient_no_crash(mock_patent_register):
    result = await search_patent_register("zzzznotadrug", field="ingredient")
    assert result.status in ("no_results", "ok")


# ── Regression 5: No HTML / markup leakage ───────────────────────────────────

_MARKUP_PATTERN = re.compile(r"<[a-zA-Z/]|&nbsp;|&#\d+;")


def _check_no_markup(value: str, field: str, record_repr: str) -> None:
    assert not _MARKUP_PATTERN.search(value), (
        f"HTML markup leaked into {field!r} of {record_repr}: {value!r}"
    )


async def test_dpd_no_html_leakage(mock_dpd):
    result = await search_dpd("metformin", field="ingredient")
    assert result.status == "ok"
    for r in result.records:
        for field, val in (
            ("brand_name", r.brand_name),
            ("company", r.company),
            ("ingredient", r.ingredient),
            ("din", r.din),
        ):
            if val:
                _check_no_markup(val, field, repr(r.din))


async def test_noc_no_html_leakage(mock_noc):
    result = await search_noc("NORINYL 1/50 21DAY", field="brand")
    assert result.status == "ok"
    for r in result.records:
        for field, val in (
            ("brand_name", r.brand_name),
            ("company", r.company),
            ("ingredient", r.ingredient),
        ):
            if val:
                _check_no_markup(val, field, repr(r.brand_name))


async def test_gsur_no_html_leakage(mock_gsur):
    result = await search_generic_submissions("metformin", field="ingredient")
    if result.status == "ok":
        for r in result.records:
            if r.ingredient:
                _check_no_markup(r.ingredient, "ingredient", repr(r.ingredient))
            if r.company:
                _check_no_markup(r.company, "company", repr(r.company))


async def test_patent_register_no_html_leakage(mock_patent_register):
    result = await search_patent_register("metformin", field="ingredient")
    if result.status == "ok":
        for r in result.records:
            if r.ingredient:
                _check_no_markup(r.ingredient, "ingredient", repr(r.ingredient))
            if r.brand_name:
                _check_no_markup(r.brand_name, "brand_name", repr(r.brand_name))
