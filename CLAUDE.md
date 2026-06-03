# Canadian Drug Database Aggregator

A local web application that searches four Canadian health-product databases simultaneously and returns consolidated results viewable in a web UI or downloadable as XLSX.

## Architecture Overview

```
app/
  main.py                # FastAPI app, routes, HTML UI embedded
  config.py              # All configuration (URLs, timeouts, model name, TTLs)
  sources/
    dpd.py               # Drug Product Database — official REST API only (no scraping)
    generic_submissions.py  # Static HTML table, httpx + BeautifulSoup
    noc.py               # NOC — CSRF-protected form POST, session cookie handling
    patent_register.py   # Patent Register — JSP form POST, SSL workaround
  normalize.py           # Static synonym map + optional Ollama llama3 expansion
  match.py               # Optional llama3 AI summary generation
  export.py              # XLSX builder (pandas + openpyxl)
  cache.py               # SQLite disk cache with TTL
  models.py              # Shared Pydantic result schema
tests/                   # pytest tests per source (require live network)
```

## Running

```bash
cd /Users/vmalik/canadian-drug-db
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# then open http://localhost:8000
```

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3` | Model for normalization/summary |
| `DPD_SEMAPHORE` | `5` | Max concurrent DPD per-drug-code requests |
| `SOURCE_TIMEOUT` | `30.0` | Seconds before a source is marked timed-out |
| `CACHE_DIR` | `/tmp/canadian_drug_db_cache` | Disk cache location |
| `CACHE_TTL` | `14400` | Cache TTL in seconds (4h default) |

## Data Sources

### 1. Drug Product Database (DPD)
- **Method:** Official REST API — no scraping
- **Base URL:** `https://health-products.canada.ca/api/drug/`
- **Key API behaviour:** `/drugproduct/?id=<code>` returns a **dict**, not a list. `/status/?id=<code>` also returns a dict. All other enrichment endpoints (`/form/`, `/route/`, `/schedule/`) return lists.
- **Supports:** ingredient, brand, company, DIN
- **Rate limiting:** semaphore-capped at 5 concurrent requests

### 2. Generic Submissions Under Review
- **Method:** httpx + BeautifulSoup table parse
- **URL:** `https://www.canada.ca/en/health-canada/services/drug-health-product-review-approval/generic-submissions-under-review.html`
- **Table columns:** Medicinal Ingredient(s) | Company Name | Therapeutic Area | Year/Month Accepted
- **Note:** Table uses `wb-tables` class. Company "Not available" for pre-April 2024 entries.
- **Supports:** ingredient, company only (brand/DIN → unsupported)

### 3. Notice of Compliance (NOC)
- **Method:** Session cookie + CSRF token, POST to `/noc-ac/doSearch`
- **URL:** `https://health-products.canada.ca/noc-ac/`
- **Form fields:** medicinalIngredient, productName, din, manufacturer, submissionClass, therapeuticClass, submissionType, productType, nocFromDate, nocToDate
- **Behaviour:** Returns "too many records" error for broad ingredient searches (e.g. plain "metformin"). Use full salt form ("metformin hydrochloride") or brand name.
- **Table columns:** Product(s) | Manufacturer | Published Notes | NOC Date | Medicinal ingredient(s) | DIN(s)
- **Supports:** ingredient, brand, company, DIN

### 4. Patent Register (PR-RDB)
- **Method:** Session cookie (JSESSIONID), POST to `/pr-rdb/search`
- **URL:** `https://pr-rdb.hc-sc.gc.ca/pr-rdb/`
- **SSL note:** Server certificate does not chain to trusted CA — `verify=False` is intentional
- **Ingredient field:** dropdown select — values must exactly match listed options. Our code fetches the dropdown and does substring + fuzzy matching.
- **Table columns:** Medicinal ingredient | Brand name | Strength | Dosage | DIN | Patent | CSP
- **Supports:** ingredient, brand, DIN (not company)

## LLM Usage (Ollama)

LLM is **never used for data extraction**. It is used only for:

1. **Ingredient synonym expansion** (before querying) — `normalize.py`
   - Primary: static synonym map (`_STATIC_SYNONYMS`)
   - Secondary: Ollama llama3 (disabled gracefully if Ollama is offline)
   - Searches run for the original term + all synonyms in parallel

2. **Plain-language summary** — `match.py`, only if `?summary=true`
   - Labeled clearly as AI-generated in the UI
   - Skipped entirely if Ollama is offline

### Ollama setup
```bash
# Install Ollama: https://ollama.com/
ollama pull llama3
ollama serve  # runs on http://localhost:11434
```

## Caching

SQLite cache at `$CACHE_DIR/cache.db`. Keyed by `sha256(source:query)`. Default TTL 4 hours. Cache is per-source-and-endpoint so partial results are cached independently.

To clear: delete `/tmp/canadian_drug_db_cache/cache.db`.

## Tests

```bash
python3 -m pytest tests/ -v --asyncio-mode=auto
```

All tests require live network access to Canadian government sites. Tests are marked to handle gracefully when sites return expected error conditions (e.g., NOC "too many records").

## Dependencies

```
fastapi uvicorn httpx beautifulsoup4 openpyxl pandas pydantic python-multipart
```

Optional for tests:
```
pytest pytest-asyncio
```

## Ingredient-Combination Grouping

Results are grouped by each product's **full active-ingredient combination**, not by the single searched ingredient. Implemented in `app/grouping.py`.

### Grouping key definition

For every `DrugRecord`:

1. Use `all_ingredients` (a `list[str]` on the model) if non-empty; otherwise fall back to parsing the `ingredient` string on `;`.
2. Normalize each name: `strip()`, uppercase, collapse internal whitespace. Salt forms are kept as-is by default (e.g. `DIPHENHYDRAMINE HCL` is not further split).
3. Deduplicate and sort alphabetically → the sorted tuple is the **group key**. `{A, B}` and `{B, A}` hash to the same group.
4. **Group label**: join sorted names with `COMBINATION_SEPARATOR` (` + ` by default, defined in `config.py`).

### Salt-form normalization (config flag)

`NORMALIZE_SALT_FORMS` env var (default `0` / off). When enabled, salt forms would be stripped before matching. Currently implemented as a config flag; the normalization pass itself can be added to `_normalize_name()` in `grouping.py` when needed.

### Where all_ingredients is populated

- **DPD**: `_fetch_ingredients_by_code(drug_code)` fetches all active-ingredient rows for the product via `/activeingredient/?id=<code>`. This is always called (not just for ingredient searches) so every record has the complete combination, even for brand/company searches.
- **NOC**: split `ingredients` field on `;`.
- **Generic Submissions**: split on `;` if present; otherwise treat the whole string as one ingredient.
- **Patent Register**: split on `;`; typically a single ingredient per row.

### Group ordering (default)

1. The group whose label exactly equals the searched ingredient (single-ingredient exact match) — first.
2. Remaining groups by descending product count, ties broken alphabetically by label.
3. When no `searched_ingredient` is provided (brand/company/DIN search), sort purely by descending count then alphabetically.

### UI rendering

Combined view and each per-source tab render results as **collapsible `<details>` groups**. Group header shows: combination label, product count, company count, and company chips. First group is expanded by default.

### XLSX export

- Every data row in every tab has a `combination` column (the group label). Rows are sorted by combination within each sheet.
- A `By Combination` summary tab lists each combination with product count, company count, and a comma-separated company list.

## Known Limitations / Gotchas

- **NOC broad searches fail:** The NOC site returns an error for ingredient names that match too many records (>500). The UI surfaces this as an error with a helpful message.
- **Patent Register SSL:** The PR-RDB server has a certificate the standard CA bundle won't verify. We disable verification (`verify=False`) explicitly — this is equivalent to a user clicking "Proceed anyway" in a browser.
- **Patent Register ingredient matching:** The ingredient field is a dropdown of 469 specific values (exact salt forms). Fuzzy substring matching is used to find closest options, but niche ingredients may not appear in the Patent Register at all.
- **Generic Submissions company names:** Pre-April 2024 entries show "Not available" as the company name — this is accurate, not a bug.
- **DPD concurrency cap:** With 242 drug codes for "metformin", all 242 are queried concurrently behind a semaphore of 5. Full results may take 5–15 seconds on first load (cached after).
