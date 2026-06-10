import os

# Ingredient-combination grouping
COMBINATION_SEPARATOR = " + "
# Salt-form normalization (default off — keeps "DIPHENHYDRAMINE HCL" as-is)
NORMALIZE_SALT_FORMS = bool(int(os.getenv("NORMALIZE_SALT_FORMS", "0")))

# LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
# LLM synonym expansion for ingredient searches — off by default.
# When off, only the static synonym map (_STATIC_SYNONYMS) is used, which is safe.
# LLM expansion is disabled by default because language models hallucinate plausible
# but incorrect drug names as synonyms (e.g. apremilast → abrocitinib), pulling
# foreign-ingredient products into the result set.
ENABLE_LLM_SYNONYMS = bool(int(os.getenv("ENABLE_LLM_SYNONYMS", "0")))

# Concurrency / timeouts
DPD_SEMAPHORE = int(os.getenv("DPD_SEMAPHORE", "10"))
SOURCE_TIMEOUT = float(os.getenv("SOURCE_TIMEOUT", "60.0"))  # seconds per source
# Cap DPD results when an ingredient matches hundreds of products
DPD_MAX_RESULTS = int(os.getenv("DPD_MAX_RESULTS", "150"))

# Cache
CACHE_DIR = os.getenv("CACHE_DIR", "/tmp/canadian_drug_db_cache")
CACHE_TTL = int(os.getenv("CACHE_TTL", str(60 * 60 * 4)))  # 4 hours default

# Base URLs
DPD_BASE = "https://health-products.canada.ca/api/drug"
GENERIC_SUBS_URL = (
    "https://www.canada.ca/en/health-canada/services/drug-health-product-review-approval"
    "/generic-submissions-under-review.html"
)
NOC_BASE = "https://health-products.canada.ca/noc-ac"
PATENT_BASE = "https://pr-rdb.hc-sc.gc.ca/pr-rdb"

# HTTP
USER_AGENT = (
    "Mozilla/5.0 (compatible; CanadaDrugAggregator/1.0; "
    "+https://github.com/local/canadian-drug-db)"
)
HTTP_TIMEOUT = 20.0  # seconds per individual HTTP request

# OCR for scanned product monograph PDFs (requires pdf2image + pytesseract + poppler)
ENABLE_OCR = bool(int(os.getenv("ENABLE_OCR", "1")))

# Concurrent PDF downloads + labeling enrichments in the async export job
LABELING_SEMAPHORE = int(os.getenv("LABELING_SEMAPHORE", "8"))

# Enrichment store TTLs: records older than these are re-fetched on the next export.
# HTTP caches (DPD API, Patent.zip) are unaffected — only the stored results are refreshed.
LABELING_STORE_TTL = int(os.getenv("LABELING_STORE_TTL", str(2 * 60 * 60)))   # 2 hours
PATENT_STORE_TTL   = int(os.getenv("PATENT_STORE_TTL",   str(4 * 60 * 60)))   # 4 hours

# Workbook column pruning: drop Sheet 1 columns whose non-empty fill rate is at or below
# this threshold.  0.0 = strict (only truly-all-empty columns dropped).
# 0.02 = drop any column filled in ≤2% of rows — removes single-stray-value patent groups
# (1/223 ≈ 0.45%) while preserving columns with meaningful coverage (≥5 rows ≈ 2.2%).
WORKBOOK_MIN_FILL_RATE = float(os.getenv("WORKBOOK_MIN_FILL_RATE", "0.02"))
