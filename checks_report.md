# Workbook Accuracy Check Report

**Workbook:** `/tmp/alpelisib_workbook.xlsx`  
**Sheet 1 rows:** 4  
**Family-3/4 sample:** 4 DINs  
**Run date:** 2026-06-04  
**Elapsed:** 1810.5 s  

> These are consistency/faithfulness checks, not absolute accuracy. Absolute accuracy requires a hand-labeled gold set.

## Fabrication / Ghost Section

No Family-3 ERRORs found.

## Family 1: Field Invariants

ERROR: **4**  |  WARN: **0**  |  SKIPPED: **0**

| check_id | din | field | sev | value | reason |
|---|---|---|---|---|---|
| F1_NOC_INCONSISTENT | 02497042 | noc_* | ERROR | real=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm | NOC fields inconsistent: populated=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm |
| F1_NOC_INCONSISTENT | 02497069 | noc_* | ERROR | real=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm | NOC fields inconsistent: populated=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm |
| F1_NOC_INCONSISTENT | 02497077 | noc_* | ERROR | real=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm | NOC fields inconsistent: populated=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm |
| F1_NOC_INCONSISTENT | 02497085 | noc_* | ERROR | real=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm | NOC fields inconsistent: populated=['noc_brand_name', 'noc_company', 'noc_date', 'noc_subm |

## Family 2: Cross-Field Coherence

ERROR: **4**  |  WARN: **0**  |  SKIPPED: **0**

| check_id | din | field | sev | value | reason |
|---|---|---|---|---|---|
| F2_AI_BLANK | 02497042 | active_ingredient | ERROR |  | active_ingredient is blank/sentinel for a DIN row (Tier-A field) |
| F2_AI_BLANK | 02497069 | active_ingredient | ERROR |  | active_ingredient is blank/sentinel for a DIN row (Tier-A field) |
| F2_AI_BLANK | 02497077 | active_ingredient | ERROR |  | active_ingredient is blank/sentinel for a DIN row (Tier-A field) |
| F2_AI_BLANK | 02497085 | active_ingredient | ERROR |  | active_ingredient is blank/sentinel for a DIN row (Tier-A field) |

## Family 3: Anti-Hallucination (live fetch)

ERROR: **0**  |  WARN: **0**  |  SKIPPED: **3**

| check_id | din | field | sev | value | reason |
|---|---|---|---|---|---|
| F3_PATENT_SKIPPED | 02497042 | patent_number | SKIPPED | 2734819 | CPD domain unreachable |
| F3_PATENT_SKIPPED | 02497069 | patent_number | SKIPPED | 2734819 | CPD domain unreachable |
| F3_PATENT_SKIPPED | 02497077 | patent_number | SKIPPED | 2734819 | CPD domain unreachable |

## Family 4: Determinism + OCR Liveness

ERROR: **0**  |  WARN: **2**  |  SKIPPED: **1**

| check_id | din | field | sev | value | reason |
|---|---|---|---|---|---|
| F4_DET_NO_PDF | 02497085 | determinism | SKIPPED |  | No PDF available for re-extraction (drug_code=98694) |
| F4_OCR_PASS | 83088 | ocr_liveness | WARN | 175432 chars, section=§6, ocr_used=False | drug_code=83088: 175432 chars extracted; section=§6; ocr_used=False |
| F4_OCR_NO_PDF | 48982 | ocr_liveness | WARN |  | drug_code=48982: no PDF link on DPD info page |

## Totals

| Severity | Count |
|---|---|
| ERROR    | 8 |
| WARN     | 2 |
| SKIPPED  | 4 |
| **Total**| **14** |

---
*Consistency/faithfulness checks only — absolute accuracy requires a gold set.*