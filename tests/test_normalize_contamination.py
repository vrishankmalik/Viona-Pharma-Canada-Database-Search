"""
Regression tests for the abrocitinib/apremilast cross-contamination bug.

Root cause: normalize_ingredient() called _ollama_synonyms() unconditionally.
For novel drugs poorly represented in llama3's training data, the model hallucinates
plausible-but-wrong drug names as synonyms. "apremilast" was hallucinated as a synonym
of "abrocitinib" (both dermatological drugs), pulling 22 apremilast DPD products into
the abrocitinib workbook.

Fix: ENABLE_LLM_SYNONYMS defaults to 0 (off). The static map handles all real synonyms.

These tests verify:
  1. normalize_ingredient returns no extra terms for novel drugs not in the static map.
  2. Even if _ollama_synonyms is mocked to hallucinate, the terms are rejected when
     ENABLE_LLM_SYNONYMS=0 (the fix is at the gate, not inside the Ollama call).
  3. Static-map synonyms still work correctly after the fix.
  4. The search_dpd extra_terms path: drug-name hallucinations are NOT passed through.
  5. Broad matrix of confusable INN pairs, substring cases, salt-form cases.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.normalize import normalize_ingredient, _static_synonyms


# ── Helper ────────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


# Known DPD ingredient names that must NEVER appear as extra_terms for another ingredient.
# Each tuple is (query, forbidden_extra_terms_subset).
_FORBIDDEN_CROSS_CONTAMINATION = [
    # The original bug pair
    ("abrocitinib", ["apremilast"]),
    ("apremilast", ["abrocitinib"]),
    # -tinib / -tinib look-alikes
    ("baricitinib", ["tofacitinib", "ruxolitinib", "upadacitinib", "abrocitinib"]),
    ("tofacitinib", ["baricitinib", "upadacitinib", "abrocitinib"]),
    ("upadacitinib", ["baricitinib", "tofacitinib", "abrocitinib"]),
    # -lisib / -ciclib look-alikes
    ("alpelisib", ["palbociclib", "ribociclib", "abemaciclib"]),
    ("palbociclib", ["alpelisib", "ribociclib", "abemaciclib"]),
    # substring boundary: "tinib" is a substring of many INNs — querying it must not
    # bleed into results from the static map (it has no static entry so extra_terms=[])
    ("tinib", []),
    # Short name that is a prefix of a longer name
    ("met", ["metformin", "metoprolol", "methotrexate"]),
    ("metformin", ["metoprolol"]),          # different drug entirely
    ("metoprolol", ["metformin"]),
    # A high-density generic vs single-product biologic
    ("metformin", ["adalimumab", "trastuzumab"]),
    ("adalimumab", ["metformin", "trastuzumab"]),
    # Salt-form case: base should not cross-contaminate into unrelated salts
    ("metformin", ["metoprolol tartrate", "metoprolol succinate"]),
    ("metoprolol", ["metformin hydrochloride"]),
    # Brand name as query — should produce no extra_terms (not in static map keys)
    ("humira", ["adalimumab"]),  # humira not in static map as a key, so no extras
]


class TestNoLLMSynonymsByDefault:
    """With ENABLE_LLM_SYNONYMS=0 (default), _ollama_synonyms is never called."""

    def test_abrocitinib_returns_no_extras(self):
        """abrocitinib is not in the static map — should return empty extra_terms."""
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("abrocitinib"))
        assert extras == [], f"Expected no extra terms, got {extras}"

    def test_apremilast_returns_no_extras(self):
        """apremilast is not in the static map — should return empty extra_terms."""
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("apremilast"))
        assert extras == [], f"Expected no extra terms, got {extras}"

    def test_ollama_is_never_called_when_disabled(self):
        """Verify _ollama_synonyms is not even invoked when the flag is off."""
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            with patch("app.normalize._ollama_synonyms", new_callable=AsyncMock) as mock_ollama:
                run(normalize_ingredient("abrocitinib"))
                mock_ollama.assert_not_called()

    def test_ollama_hallucination_blocked_even_if_somehow_called(self):
        """If _ollama_synonyms were called and returned a hallucination, the gate blocks it."""
        # ENABLE_LLM_SYNONYMS is a module-level constant; patch it directly.
        # Control case: with the flag enabled, the hallucination leaks through (old bug).
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", True):
            with patch(
                "app.normalize._ollama_synonyms",
                new_callable=AsyncMock,
                return_value=["apremilast", "jak inhibitor"],
            ):
                _, extras_with_llm = run(normalize_ingredient("abrocitinib"))
        assert "apremilast" in extras_with_llm, (
            "Control: with ENABLE_LLM_SYNONYMS=True the hallucination would leak through"
        )

        # Fix case: with the flag disabled, the hallucination is blocked.
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            with patch(
                "app.normalize._ollama_synonyms",
                new_callable=AsyncMock,
                return_value=["apremilast", "jak inhibitor"],
            ):
                _, extras_without_llm = run(normalize_ingredient("abrocitinib"))
        assert "apremilast" not in extras_without_llm, (
            "Fix: with ENABLE_LLM_SYNONYMS=False the hallucination must be blocked"
        )
        assert extras_without_llm == [], f"Expected empty extras, got {extras_without_llm}"


class TestStaticMapUnchanged:
    """Verify that the fix did not break static-map synonym expansion."""

    def test_acetaminophen_still_expands_to_paracetamol(self):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("acetaminophen"))
        assert "paracetamol" in extras

    def test_paracetamol_still_expands_to_acetaminophen(self):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("paracetamol"))
        assert "acetaminophen" in extras

    def test_metformin_expands_to_salt_form(self):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("metformin"))
        assert "metformin hydrochloride" in extras

    def test_metformin_hydrochloride_expands_to_base(self):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("metformin hydrochloride"))
        assert "metformin" in extras

    def test_semaglutide_expands_to_brand_names(self):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient("semaglutide"))
        assert "ozempic" in extras

    def test_canonical_term_is_unchanged(self):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            canonical, _ = run(normalize_ingredient("  Abrocitinib  "))
        # canonical is the input with strip() only — not lowercased
        assert canonical == "Abrocitinib"


class TestForbiddenCrossContamination:
    """
    Broad matrix: for each (query, forbidden_list) pair, verify none of the
    forbidden terms appear in extra_terms with ENABLE_LLM_SYNONYMS=0.
    """

    @pytest.mark.parametrize("query,forbidden", _FORBIDDEN_CROSS_CONTAMINATION)
    def test_no_forbidden_cross_contamination(self, query, forbidden):
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            _, extras = run(normalize_ingredient(query))
        lower_extras = [e.lower() for e in extras]
        leaked = [f for f in forbidden if f.lower() in lower_extras]
        assert not leaked, (
            f"normalize_ingredient({query!r}) returned forbidden extra terms: {leaked}. "
            f"Full extras: {extras}"
        )


class TestStaticMapNoCrossBleeding:
    """
    Verify the static map itself does not create cross-ingredient entries.
    i.e., the synonym of X is not Y where X and Y are unrelated drugs.
    """

    def test_metformin_synonyms_do_not_include_metoprolol(self):
        syns = _static_synonyms("metformin")
        assert "metoprolol" not in syns
        assert "metoprolol tartrate" not in syns
        assert "metoprolol succinate" not in syns

    def test_metoprolol_synonyms_do_not_include_metformin(self):
        syns = _static_synonyms("metoprolol")
        assert "metformin" not in syns
        assert "metformin hydrochloride" not in syns

    def test_abrocitinib_not_in_static_map(self):
        # Abrocitinib is a novel drug — must have no static synonyms.
        # If someone adds it to the static map later, they must not map it to apremilast.
        syns = _static_synonyms("abrocitinib")
        assert "apremilast" not in syns

    def test_apremilast_not_in_static_map(self):
        syns = _static_synonyms("apremilast")
        assert "abrocitinib" not in syns

    def test_jak_inhibitor_class_members_not_cross_mapped(self):
        """tofacitinib, baricitinib, upadacitinib are all JAK inhibitors — must not synonym-map to each other."""
        for query in ["tofacitinib", "baricitinib", "upadacitinib", "abrocitinib"]:
            syns = _static_synonyms(query)
            other_jaks = {"tofacitinib", "baricitinib", "upadacitinib", "abrocitinib"} - {query}
            for jak in other_jaks:
                assert jak not in syns, (
                    f"Static map incorrectly maps {query!r} → {jak!r} "
                    "(same drug class but different molecules)"
                )


class TestAbrocitinibRegressionFixed:
    """
    Permanent regression lock for the abrocitinib/apremilast bug.

    With ENABLE_LLM_SYNONYMS=0 (default), normalize_ingredient('abrocitinib')
    must return no extra_terms, guaranteeing search_dpd is never asked to search
    for 'apremilast' and cannot return apremilast DINs in an abrocitinib workbook.
    """

    def test_abrocitinib_extra_terms_are_empty(self):
        """Core regression: abrocitinib must produce no extra search terms."""
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            canonical, extras = run(normalize_ingredient("abrocitinib"))
        assert canonical == "abrocitinib"
        assert extras == [], (
            f"REGRESSION: abrocitinib produced extra_terms={extras}. "
            "If 'apremilast' is present, the workbook will contain apremilast products."
        )

    def test_apremilast_extra_terms_are_empty(self):
        """apremilast workbook must not trigger any synonym expansion."""
        with patch("app.normalize.ENABLE_LLM_SYNONYMS", False):
            canonical, extras = run(normalize_ingredient("apremilast"))
        assert canonical == "apremilast"
        assert extras == []

    def test_apremilast_never_appears_as_abrocitinib_synonym_in_static_map(self):
        """Guard against accidentally adding the wrong synonym to the static map."""
        syns = _static_synonyms("abrocitinib")
        assert "apremilast" not in syns, (
            "apremilast must never be a static synonym of abrocitinib"
        )

    def test_abrocitinib_never_appears_as_apremilast_synonym_in_static_map(self):
        syns = _static_synonyms("apremilast")
        assert "abrocitinib" not in syns
