.PHONY: test lint typecheck mutate quality

test:
	python3 -m pytest tests/ -q --tb=short

test-fast:
	python3 -m pytest tests/ -x -q --tb=short

lint:
	ruff check src/ tests/

typecheck:
	python3 -m mypy src/faultray/model/ --ignore-missing-imports

mutate:
	mutmut run --paths-to-mutate=src/faultray/model/ --runner="python3 -m pytest tests/test_engine.py tests/test_scenarios.py -x -q"

quality: lint typecheck test
	@echo "All quality checks passed"
