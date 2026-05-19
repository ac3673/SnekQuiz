.PHONY: coverage release

coverage:
	uv run pytest --cov --cov-report xml:reports/coverage.xml
	uv run genbadge coverage -i reports/coverage.xml -o reports/coverage-badge.svg

release:
	uv run cz bump --changelog
	git push origin HEAD --follow-tags
