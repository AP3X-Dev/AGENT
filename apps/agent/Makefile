.PHONY: test test-watch test-coverage test-unit test-integration install-test help

# Default target
all: help

help:
	@echo "AG3NT Agent - Test Commands"
	@echo ""
	@echo "Available targets:"
	@echo "  test              - Run all tests"
	@echo "  test-watch        - Run tests in watch mode"
	@echo "  test-coverage     - Run tests with coverage report"
	@echo "  test-unit         - Run only unit tests"
	@echo "  test-integration  - Run only integration tests"
	@echo "  install-test      - Install test dependencies"
	@echo "  clean             - Remove test artifacts"

# Install test dependencies
install-test:
	pip install -e ".[test]"

# Run all tests
test:
	pytest

# Run tests in watch mode
test-watch:
	pytest-watch

# Run tests with coverage
test-coverage:
	pytest --cov=ag3nt_agent --cov-report=html --cov-report=term

# Run only unit tests
test-unit:
	pytest tests/unit

# Run only integration tests
test-integration:
	pytest tests/integration

# Clean test artifacts
clean:
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf **/__pycache__
	find . -type d -name "*.egg-info" -exec rm -rf {} +

