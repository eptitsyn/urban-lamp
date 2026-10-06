.PHONY: clean

# Preserve the virtual environment, source files, and example outputs.
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist
	find src tests -type d \( -name __pycache__ -o -name '*.egg-info' \) -prune -exec rm -rf {} +
	find src tests -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
