# Contributing to MDx Code

First off, thanks for taking the time to contribute! 🎉

## How Can I Contribute?

### Reporting Bugs

- Use the GitHub issue tracker
- Include your Python version, OS, and steps to reproduce
- Include the full error message and stack trace

### Suggesting Features

- Open an issue with the tag `enhancement`
- Describe the use case and why it would be valuable
- Be open to discussion about implementation approaches

### Pull Requests

1. Fork the repo and create your branch from `main`
2. If you've added code, add tests
3. Ensure the test suite passes
4. Make sure your code follows the existing style
5. Write a clear PR description

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/mdx-code.git
cd mdx-code

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest
```

## Code Style

- We use Python type hints
- Keep functions focused and small
- Write docstrings for public functions
- Follow PEP 8

## Questions?

Feel free to open an issue with the tag `question`.

---

Thanks for helping make MDx Code better! 🚀
