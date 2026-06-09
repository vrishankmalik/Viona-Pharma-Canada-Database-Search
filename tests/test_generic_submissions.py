"""Tests for Generic Submissions source — live network (integration-marked).

All tests in this file hit the live Health Canada page.
Run with: make test-live
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.sources.generic_submissions import search_generic_submissions


@pytest.mark.integration
async def test_generic_submissions_ingredient_search():
    """Search for 'abacavir' — known to be in the table."""
    result = await search_generic_submissions("abacavir", field="ingredient")
    assert result.status in ("ok", "no_results"), f"Unexpected status: {result.status}"
    if result.status == "ok":
        assert result.count > 0
        for r in result.records:
            assert r.source == "GenericSubmissions"
            assert "abacavir" in (r.ingredient or "").lower()


async def test_generic_submissions_brand_unsupported():
    """Brand search should return 'unsupported' status — no network needed."""
    result = await search_generic_submissions("Lipitor", field="brand")
    assert result.status == "unsupported"


async def test_generic_submissions_din_unsupported():
    """DIN search should return 'unsupported' status — no network needed."""
    result = await search_generic_submissions("12345678", field="din")
    assert result.status == "unsupported"


@pytest.mark.integration
async def test_generic_submissions_no_results():
    """Nonexistent ingredient returns no_results."""
    result = await search_generic_submissions("xyznonexistentdrugabc123", field="ingredient")
    assert result.status in ("no_results", "ok")
    if result.status == "ok":
        assert result.count == 0


@pytest.mark.integration
async def test_generic_submissions_columns():
    """Check that source_specific has expected keys."""
    result = await search_generic_submissions("metformin", field="ingredient")
    if result.status == "ok" and result.records:
        r = result.records[0]
        assert "therapeutic_area" in r.source_specific
        assert "date_accepted" in r.source_specific
