.PHONY: coverage release

coverage:
	uv run pytest --cov --cov-report xml:reports/coverage.xml
	uv run genbadge coverage -i reports/coverage.xml -o reports/coverage-badge.svg

release:
	@VERSION=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	echo "Creating release for version $$VERSION..."; \
	git tag -a "v$$VERSION" -m "Release version $$VERSION" || (echo "Tag v$$VERSION already exists. Delete it first with: git tag -d v$$VERSION" && exit 1); \
	git push origin "v$$VERSION" && \
	echo "✓ Tag v$$VERSION created and pushed successfully!" && \
	echo "✓ Go to https://github.com/ac3673/snekquiz/releases/new?tag=v$$VERSION to create the release"
