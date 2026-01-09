# MDXCODE.md

## Project
- **Name:** Demo Project
- **Domain:** Platform
- **Team:** Engineering
- **Owner:** @md

## Quick Commands
| Command | Description |
|---------|-------------|
| `python -m pytest` | Run all tests |
| `python -m pytest -v` | Run tests verbose |
| `black .` | Format code |
| `mypy src/` | Type check |

## Architecture
- `src/` → Source code
- `src/api/` → API endpoints
- `src/services/` → Business logic
- `src/models/` → Data models
- `tests/` → Test files

## Conventions
- Python 3.11+
- Type hints on all functions
- Docstrings on all public functions
- Black for formatting
- pytest for testing

## Compliance
- No hardcoded secrets
- All inputs validated
- Errors logged, not exposed

## Guardrails
- ❌ Never commit directly to main
- ❌ Never skip tests
- ⚠️ New dependencies require review

## Known Issues
- None yet

## Context Files
- `README.md`
