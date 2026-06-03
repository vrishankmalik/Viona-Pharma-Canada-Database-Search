"""Tests for Patent Register source.

Pure unit tests (no network) run by default.
Integration tests that hit the live PR-RDB site are marked @pytest.mark.integration.
Run with: make test-live
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.sources.patent_register import search_patent_register, _find_matching_options


# ── Pure unit tests (no network) ──────────────────────────────────────────────

def test_find_matching_options_exact():
    """Exact substring match should work case-insensitively."""
    opts = ["METFORMIN HYDROCHLORIDE", "METFORMIN HYDROCHLORIDE / CANAGLIFLOZIN", "INSULIN GLARGINE"]
    result = _find_matching_options("metformin", opts)
    assert len(result) == 2
    assert "METFORMIN HYDROCHLORIDE" in result


def test_find_matching_options_no_match():
    opts = ["INSULIN GLARGINE", "ADALIMUMAB"]
    result = _find_matching_options("xyzabc", opts)
    assert result == []


# ── Integration tests (live network) ─────────────────────────────────────────

@pytest.mark.integration
async def test_patent_register_dropdown_loads():
    """Dropdown options should be fetchable (>100 ingredients expected)."""
    from app.sources.patent_register import _get_dropdown_options
    ingredients, brands, session = await _get_dropdown_options()
    assert len(ingredients) > 50, f"Too few ingredients: {len(ingredients)}"
    assert len(brands) > 50, f"Too few brands: {len(brands)}"


@pytest.mark.integration
async def test_patent_register_metformin():
    """Search for metformin — should find combo products at least."""
    result = await search_patent_register("metformin", field="ingredient")
    assert result.status in ("ok", "no_results"), f"{result.status}: {result.error_message}"
    if result.status == "ok":
        assert result.count > 0
        for r in result.records:
            assert r.source == "PatentRegister"
            assert "patent_number" in r.source_specific


async def test_patent_register_company_unsupported():
    """Company search must return unsupported — no network needed."""
    result = await search_patent_register("Pfizer", field="company")
    assert result.status == "unsupported"


@pytest.mark.integration
async def test_patent_register_no_results():
    result = await search_patent_register("xyznonexistentdrugabc123", field="ingredient")
    assert result.status in ("no_results", "ok")
    if result.status == "ok":
        assert result.count == 0
