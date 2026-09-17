# Contributing to ReWoo

Thank you for your interest in contributing to ReWoo! This document provides guidelines and instructions for contributing.

## Development Setup

1. Fork and clone the repository
2. Run the setup script:
   ```bash
   ./scripts/setup.sh
   source .venv/bin/activate
   ```
3. Install pre-commit hooks (optional):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Code Style

- **Python 3.11+** — use modern Python features (type hints, `|` unions, etc.)
- **Line length:** 100 characters max
- **Formatting:** Ruff (runs as part of CI)
- **Type checking:** MyPy in strict mode
- **Imports:** Use `from __future__ import annotations` for forward references

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=rewoo --cov-report=html

# Run specific test file
pytest tests/unit/test_planner.py

# Run with verbose output
pytest tests/ -v
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all tests pass: `pytest tests/`
4. Ensure linting passes: `ruff check rewoo/`
5. Submit a PR with a clear description of the change

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include your Python version, OS, and ReWoo version
- For security issues, see SECURITY.md

## Areas That Need Help

- Tool implementations (web search providers, file operations)
- Provider integrations (new LLM providers)
- Safety improvements (risk classification rules, sandbox enhancements)
- Documentation (tutorials, examples, architecture docs)
- Gateway implementations (Telegram, Discord)
