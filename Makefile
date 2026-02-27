.PHONY: coverage

coverage:
	uv run pytest --cov --cov-report xml:reports/coverage.xml
	uv run genbadge coverage -i reports/coverage.xml -o reports/coverage-badge.svg
