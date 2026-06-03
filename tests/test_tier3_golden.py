"""Tier 3 — Golden-value tests (offline, against fixtures).

These use stable discontinued/historical records whose brand names and DINs
never change, guarding against field-mapping regressions (column shifts, wrong
key names, etc.).

Stable records used:
  DIN 00326925 → SINEQUAN          (doxepin HCl 10 mg capsule, Pfizer, cancelled)
  DIN 00000019 → PLACIDYL CAP 200MG (ethchlorvynol, Abbott, cancelled)
  NOC 3369     → NORINYL 1/50 21DAY (norethindrone + mestranol, Pfizer)
"""
import pytest

from app.sources.dpd import search_dpd
from app.sources.noc import search_noc


# ── DPD golden values ─────────────────────────────────────────────────────────

class TestDPDGolden:
    async def test_sinequan_din_lookup(self, mock_dpd):
        """DIN 00326925 must resolve to SINEQUAN with correct metadata."""
        result = await search_dpd("00326925", field="din")
        assert result.status == "ok", result.error_message
        assert result.count == 1
        r = result.records[0]
        assert r.source == "DPD"
        assert r.brand_name == "SINEQUAN"
        assert r.din == "00326925"
        assert r.company == "PFIZER CANADA INC"
        # Ingredient from the per-code endpoint
        assert "DOXEPIN" in (r.ingredient or "").upper()
        assert r.dosage_form is not None
        assert r.route is not None

    async def test_sinequan_source_specific(self, mock_dpd):
        """source_specific block carries drug_code, class_name, last_update_date."""
        result = await search_dpd("00326925", field="din")
        r = result.records[0]
        assert r.source_specific.get("drug_code") == 11111
        assert r.source_specific.get("class_name") == "Human"
        assert r.source_specific.get("last_update_date") == "2005-06-30"

    async def test_placidyl_din_lookup(self, mock_dpd):
        """DIN 00000019 must resolve to PLACIDYL CAP 200MG."""
        result = await search_dpd("00000019", field="din")
        assert result.status == "ok", result.error_message
        r = result.records[0]
        assert r.brand_name == "PLACIDYL CAP 200MG"
        assert r.din == "00000019"
        assert r.company == "ABBOTT LABORATORIES LIMITED"
        assert "ETHCHLORVYNOL" in (r.ingredient or "").upper()

    async def test_ingredient_search_returns_metformin(self, mock_dpd):
        """Ingredient search for 'metformin' returns records with METFORMIN in ingredient."""
        result = await search_dpd("metformin", field="ingredient")
        assert result.status == "ok"
        found = any("METFORMIN" in (r.ingredient or "").upper() for r in result.records)
        assert found, "No record contains METFORMIN in ingredient"

    async def test_all_ingredients_populated(self, mock_dpd):
        """all_ingredients list must be non-empty for records that have ingredient data."""
        result = await search_dpd("metformin", field="ingredient")
        assert result.status == "ok"
        for r in result.records:
            assert len(r.all_ingredients) > 0, (
                f"all_ingredients empty for {r.brand_name} / {r.din}"
            )

    async def test_record_url_format(self, mock_dpd):
        """Every DPD record must have a valid provenance URL."""
        result = await search_dpd("00326925", field="din")
        r = result.records[0]
        assert r.record_url and r.record_url.startswith("https://health-products.canada.ca")


# ── NOC golden values ─────────────────────────────────────────────────────────

class TestNOCGolden:
    async def test_norinyl_brand_search(self, mock_noc):
        """Brand search for NORINYL 1/50 21DAY returns correct DIN and ingredients."""
        result = await search_noc("NORINYL 1/50 21DAY", field="brand")
        assert result.status == "ok", result.error_message
        assert result.count >= 1
        r = result.records[0]
        assert r.source == "NOC"
        assert "NORINYL" in (r.brand_name or "").upper()
        assert r.din == "02188724"
        # Ingredients must include both active ingredients
        ingredient_upper = (r.ingredient or "").upper()
        assert "NORETHINDRONE" in ingredient_upper
        assert "MESTRANOL" in ingredient_upper

    async def test_norinyl_all_ingredients(self, mock_noc):
        """all_ingredients must be populated from the semicolon-separated ingredient string."""
        result = await search_noc("NORINYL 1/50 21DAY", field="brand")
        r = result.records[0]
        assert len(r.all_ingredients) >= 2
        names_upper = [n.upper() for n in r.all_ingredients]
        assert "NORETHINDRONE" in names_upper
        assert "MESTRANOL" in names_upper

    async def test_norinyl_noc_date_in_source_specific(self, mock_noc):
        """source_specific must carry noc_date."""
        result = await search_noc("NORINYL 1/50 21DAY", field="brand")
        r = result.records[0]
        assert "noc_date" in r.source_specific
        assert r.source_specific["noc_date"] == "1984-01-18"

    async def test_norinyl_record_url_contains_noc_id(self, mock_noc):
        """record_url must link to the NOC detail page with id=3369."""
        result = await search_noc("NORINYL 1/50 21DAY", field="brand")
        r = result.records[0]
        assert r.record_url is not None
        assert "3369" in r.record_url

    async def test_glucophage_brand_search(self, mock_noc):
        """Brand search for Glucophage returns a valid metformin NOC record."""
        result = await search_noc("Glucophage", field="brand")
        assert result.status == "ok"
        r = result.records[0]
        assert r.din == "02229895"
        assert "METFORMIN" in (r.ingredient or "").upper()

    async def test_noc_status_field(self, mock_noc):
        """NOC records have status = 'NOC' (no published_notes) or 'NOC/c'."""
        result = await search_noc("NORINYL 1/50 21DAY", field="brand")
        for r in result.records:
            assert r.status in ("NOC", "NOC/c"), f"Unexpected status: {r.status}"
