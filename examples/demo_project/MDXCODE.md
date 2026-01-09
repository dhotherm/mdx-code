# MDXCODE.md

## Project
- **Name:** Demo Calculator
- **Domain:** Platform
- **Team:** Demo Team
- **Owner:** @md

## Quick Commands
| Command | Description |
|---------|-------------|
| `python -m pytest` | Run tests |
| `python -m pytest -v` | Run tests verbose |

## Architecture
- `src/` → Source code
- `src/calculator.py` → Calculator functions
- `src/auth.py` → Authentication (has security issues!)
- `tests/` → Test files

## Conventions
- Python 3.11+
- Functions should have docstrings
- All edge cases should be handled

## Compliance
- No hardcoded credentials
- No SQL injection vulnerabilities
- Use secure random for tokens

## Guardrails
- ⚠️ This is a demo project with intentional bugs
- ⚠️ Security issues are for demonstration

## Known Issues
- `divide()` doesn't handle zero division
- `power()` doesn't work for negative exponents
- `factorial()` will crash on negative input
- `average()` crashes on empty list
- `auth.py` has multiple security vulnerabilities
