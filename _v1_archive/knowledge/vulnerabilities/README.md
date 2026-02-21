# Vulnerability Knowledge Base

This directory contains vulnerability patterns that MDx Code uses for security scanning.

## Structure

```
vulnerabilities/
├── README.md           # This file
├── injection.json      # SQL, command, code injection
├── secrets.json        # Hardcoded secrets, keys
├── crypto.json         # Weak cryptography
└── misc.json           # Other vulnerabilities
```

## Adding New Patterns

Create a JSON file with an array of pattern objects:

```json
[
  {
    "name": "Descriptive Name",
    "pattern": "regex pattern to match",
    "severity": "critical|high|medium|low",
    "description": "Why this is a problem",
    "fix_pattern": "optional regex replacement"
  }
]
```

## Learned Patterns

Patterns added via `mdxcode security learn` are stored in:
`../learnings/discovered.jsonl`

These are automatically loaded on each scan.
