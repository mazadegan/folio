# Folio CLI

Local-first document vault CLI for macOS.

## Setup

1. Create/activate your virtualenv.
2. Install editable package:
   - `pip install -e '.[dev]'`
3. Build the macOS keychain helper:
   - `swift build --package-path helpers/keychain-helper`

## Commands

- `folio init`
- `folio add <path>`
- `folio search "<query>" [--limit N]`
- `folio open <id> [--persist]`
- `folio sync` (placeholder)

## Output

- Default output is JSONL events (`schema=folio.event.v1`).
- Use `--human` for human-readable output.

## Security

- Files are encrypted at rest.
- `search` and `open` require biometric auth via the native helper.
- Canceling auth returns `error` with `code=AUTH_CANCELED`.
