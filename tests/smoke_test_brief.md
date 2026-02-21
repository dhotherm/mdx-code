# Smoke Test Fix Instructions

When smoke tests fail, follow this process:

1. Run: `python tests/smoke_test.py --fast --verbose --fix`
2. Read each failure carefully — the fix_hint tells you which file to look at
3. Fix one failure at a time, re-running after each fix
4. Run the full unit test suite after all fixes: `python -m pytest tests/ -x -q`
5. Run smoke tests again to confirm: `python tests/smoke_test.py --fast`

## Common Patterns

- **Import error** → Module was renamed or moved. Check the import path.
- **Exit code 2** → Typer/Click rejected a flag. Check command definitions.
- **Exit code 1 with no output** → Exception before any print. Run with --verbose.
- **Missing command** → Command function exists but isn't registered on `app`.
- **Latency over 500ms** → Heavy import at module level. Move to lazy import inside function.
