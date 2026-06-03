.PHONY: test test-live test-all coverage refresh-fixtures

# Offline unit suite (default — fast, no network, must pass in CI)
test:
	python3 -m pytest tests/ -v --tb=short

# Integration suite — hits live government sites (run nightly or on demand)
test-live:
	python3 -m pytest tests/ -v --tb=short -m integration

# Run everything: offline + integration
test-all:
	python3 -m pytest tests/ -v --tb=short -m "unit or integration"

# Coverage report (offline suite only)
coverage:
	python3 -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=html --tb=short
	@echo "HTML report: htmlcov/index.html"

# Re-record all HTTP fixtures from live sources.
# Requires network access; writes fixture JSON/HTML to tests/fixtures/.
refresh-fixtures:
	python3 tests/scripts/refresh_fixtures.py
