# py-standard — Python ruleset

Language: python
Ruleset id: py-standard

## Security
- No hardcoded credentials, tokens, or passwords.
- Prefer parameterized queries over string-built SQL.
- Avoid `os.system` / `shell=True` with untrusted input.

## Tests
- New behavior needs at least one happy-path and one failure-path test.
- Avoid time-dependent and order-dependent assertions.

## Style
- Prefer clear names over abbreviations.
- No dead code; remove unused imports.
- Keep functions small and single-purpose.
