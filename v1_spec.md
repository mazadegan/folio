# Folio CLI v1 Specification

## 1. Goals and Non-Goals

### Goals
- Provide a local-first CLI for securely storing and retrieving personal documents.
- Support plain-text keyword search across added documents.
- Preserve a stable document ID for later retrieval/opening.
- Provide JSONL-first output for reliable programmatic consumption.
- Keep architecture compatible with future sync providers.

### Non-Goals (v1)
- No remote sync implementation.
- No semantic/vector search.
- No OCR pipeline for scanned image PDFs (best effort text extraction only).
- No multi-user/shared vault support.

## 2. Supported Commands

### `folio init`
Initializes Folio storage in the user home directory.

Behavior:
- Create `~/Folio` if it does not exist.
- Create required subdirectories and local database.
- Generate and store local encryption key material.
- Be idempotent (safe to run multiple times).

Exit behavior:
- `0` on success.
- Non-zero with actionable error if setup cannot be completed.

Output:
- Default: JSONL events.
- `--human`: human-readable text output.

### `folio add <path>`
Adds a file to Folio by copying, encrypting, and indexing it.

Behavior:
- Accept absolute or relative path; expand `~`.
- Validate path exists and points to a regular file.
- Compute file hash (SHA-256) for integrity and dedupe checks.
- If hash already exists, treat as duplicate and do not re-import/encrypt/store again.
- Assign Folio document ID (UUID v4).
- Copy into managed store path.
- Encrypt at rest using local master key (AES-256-GCM).
- Extract plain text for indexing.
- Persist metadata and search index entries.
- Return document ID and filename.

Exit behavior:
- `0` on success.
- Non-zero on invalid file, encryption failure, extraction failure, or DB failure.

Output:
- Default: JSONL events.
- `--human`: human-readable text output.
- Duplicate add should emit `add.duplicate` with existing document ID and return success (`0`).

### `folio search "<query>"`
Searches indexed text and returns matching documents.

Behavior:
- Run full-text query using SQLite FTS5.
- Return ranked results with:
  - `id`
  - `filename`
  - snippet/context around match
  - optional score/rank
- Default output: JSONL stream (`search.result` per match + `search.completed` summary).
- Support `--limit <n>` (default: 10).
- Support `--human` for human-readable table/list.
- Support `--schema v1` (default: `v1`).

Exit behavior:
- `0` when command completes (including zero matches).
- Non-zero on query/index errors.

### `folio open <id>`
Opens a document by Folio ID.

Behavior:
- Resolve `id` in metadata table.
- Default mode: decrypt encrypted file to a temporary plaintext file under `~/Folio/tmp/`.
- `--persist` mode: decrypt file to `~/Folio/exports/` and do not auto-delete.
- Run platform open command for either path:
  - macOS: `open <temp-file>`
- In default mode, enforce TTL-based cleanup and next-run cleanup sweep.

Exit behavior:
- `0` on success.
- Non-zero if ID not found, decrypt fails, or open command fails.

Output:
- Default: JSONL events.
- `--human`: human-readable text output.

### `folio sync`
Placeholder command in v1.

Behavior:
- Return message: sync is not yet implemented.
- Exit code `0` with roadmap hint, or dedicated non-implemented code if desired.

Output:
- Default: JSONL events.
- `--human`: human-readable text output.

## 3. On-Disk Layout

Root:
- `~/Folio/`

Subdirectories:
- `~/Folio/store/` encrypted document blobs.
- `~/Folio/index/` local SQLite DB and search index data.
- `~/Folio/tmp/` transient decrypted files for open operations.
- `~/Folio/exports/` user-persisted decrypted exports (created on demand by `open --persist`).
- `~/Folio/config/` local configuration and provider settings (future sync).

Proposed files:
- `~/Folio/index/folio.db` SQLite database.
- `~/Folio/config/config.json` CLI settings.
- No raw key file in Folio directory on macOS; key material is stored in Keychain (see security section).

## 4. Data Model (SQLite)

### `documents` table
- `id TEXT PRIMARY KEY` (UUID v4).
- `original_name TEXT NOT NULL`.
- `stored_rel_path TEXT NOT NULL` (relative path under `store/`).
- `mime_type TEXT`.
- `size_bytes INTEGER NOT NULL`.
- `sha256 TEXT NOT NULL`.
- `created_at TEXT NOT NULL` (ISO-8601 UTC).
- `indexed_at TEXT` (ISO-8601 UTC).
- `encryption_nonce BLOB NOT NULL`.
- `encryption_tag BLOB` (if stored separately by library format).

Indexes:
- `UNIQUE(sha256)` required for v1 dedupe behavior.
- `INDEX(created_at)`.

### `documents_fts` virtual table (FTS5)
- `id UNINDEXED`
- `content`
- `tokenize = 'porter unicode61'` (or default unicode tokenizer).

Notes:
- Keep `id` in FTS rows to map quickly to `documents`.
- Snippet/context generated with SQLite snippet/highlight functions where practical.

### `sync_state` table (future-ready, unused in v1)
- `provider TEXT PRIMARY KEY`
- `cursor TEXT`
- `last_sync_at TEXT`
- `status TEXT`

## 5. Encryption and Key Management

### Algorithm
- AES-256-GCM per file.
- Random 96-bit nonce per encryption operation.

### Key
- One local master key generated at `folio init`.
- Store key in macOS Keychain from v1 (required).
- `folio` should use Keychain APIs that support biometric-gated access where available (Touch ID / Apple Watch unlock path as managed by macOS).
- CLI should surface actionable errors if Keychain access is denied or unavailable.

### Integrity
- Preserve auth tag via GCM output format.
- Verify on decrypt; reject tampered content.

### Temp plaintext handling
- Decrypted temp files written only under `~/Folio/tmp/`.
- Default cleanup strategy (v1):
  - Assign temp plaintext TTL of 10 minutes.
  - Schedule best-effort deletion at TTL expiry.
  - Run cleanup sweep on every CLI invocation to delete expired temp artifacts.
  - Track temp files in manifest/state to avoid deleting untracked files.
- `open --persist` outputs to `~/Folio/exports/` and bypasses temp TTL cleanup.

## 6. Text Extraction and Indexing

Priority pipeline:
1. PDF via `pdftotext` (required dependency).
2. Plain text formats via direct read (`.txt`, `.md`, `.csv`, etc.).
3. Unsupported/binary formats: index minimal metadata only.

Rules:
- Store extracted text only in local index DB (not alongside encrypted blob).
- Cap extraction size per file to avoid unbounded index growth (configurable later).
- Normalize whitespace before indexing.

Failure policy:
- If encryption/storage succeeds but extraction fails, add document with `indexed_at = NULL` and warn user.
- If `pdftotext` is missing, `folio add` for PDF files must fail with actionable install guidance.

## 7. Search Behavior

Input:
- Raw query string for FTS matching.

Output fields:
- `id`
- `filename`
- `snippet`
- `rank` (if computed)

Snippet behavior:
- ~30-60 chars around hit using FTS snippet helper where available.

Ordering:
- Rank descending, then `created_at` descending fallback.

No-match behavior:
- Print `No matches found`.

## 8. ID Semantics

- IDs are immutable and unique per document record.
- Use UUID v4 initially.
- Future option: accept short-prefix resolution if unambiguous.

## 9. Error Handling and Exit Codes

Suggested codes:
- `0` success.
- `1` generic/runtime error.
- `2` invalid usage/arguments.
- `3` not initialized (`folio init` required).
- `4` not found (e.g., unknown ID/path).
- `5` crypto failure.
- `6` index/search failure.

All errors should be actionable and concise.

## 10. Output Contract and Diagnostics

v1 defaults:
- JSONL output (one JSON object per line) to `stdout`.
- Human-readable text only when `--human` is passed.
- `--verbose` optional for additional diagnostic fields/events.
- Avoid logging sensitive plaintext content.

Schema selection:
- `--schema v1` is supported and is the default in v1.

### JSONL Envelope

Each line SHOULD include:
- `schema` string schema namespace (v1: `folio.event.v1`).
- `event_version` integer event payload version (v1 starts at `1`).
- `event` string event type.
- `ts` ISO-8601 UTC timestamp.
- `level` one of `info`, `warn`, `error`.
- `command` CLI command name (`init`, `add`, `search`, `open`, `sync`).
- `data` event-specific object.

### Versioning Guarantees

- For `schema=folio.event.v1`, existing fields and meanings are stable.
- Within `v1`, changes must be additive only (new optional fields and/or new event types).
- Removing required fields, renaming fields, or changing field semantics is breaking and requires a new schema namespace (e.g. `folio.event.v2`).
- Existing event names must remain stable; incompatible semantic changes must use new event names.

### Standard Events (v1)

- `init.completed`
- `add.completed`
- `add.duplicate`
- `add.indexing_warning` (non-fatal extraction/indexing failure)
- `search.result` (one line per match)
- `search.completed` (summary, includes result count)
- `open.completed`
- `tmp.cleanup_warning` (non-fatal cleanup failure)
- `sync.not_implemented`
- `error` (fatal; command exits non-zero)
- `error` with `code=AUTH_CANCELED` for user-canceled biometric auth

### Example Events

`folio init`:
```json
{"schema":"folio.event.v1","event_version":1,"event":"init.completed","ts":"2026-05-20T15:10:02Z","level":"info","command":"init","data":{"folio_root":"/Users/alice/Folio","created":true}}
```

`folio add ~/Downloads/file.pdf`:
```json
{"schema":"folio.event.v1","event_version":1,"event":"add.completed","ts":"2026-05-20T15:12:10Z","level":"info","command":"add","data":{"id":"3d278e8f-3aef-4df5-b62d-f6b36e84a36f","filename":"file.pdf","sha256":"...","indexed":true}}
```

Duplicate `folio add ~/Downloads/file.pdf`:
```json
{"schema":"folio.event.v1","event_version":1,"event":"add.duplicate","ts":"2026-05-20T15:12:22Z","level":"info","command":"add","data":{"id":"3d278e8f-3aef-4df5-b62d-f6b36e84a36f","filename":"file.pdf","sha256":"...","imported":false}}
```

`folio search "tax return"` (2 results):
```json
{"schema":"folio.event.v1","event_version":1,"event":"search.result","ts":"2026-05-20T15:14:00Z","level":"info","command":"search","data":{"id":"3d278e8f-3aef-4df5-b62d-f6b36e84a36f","filename":"file.pdf","snippet":"...federal tax return for 2024...","rank":-3.72}}
{"schema":"folio.event.v1","event_version":1,"event":"search.result","ts":"2026-05-20T15:14:00Z","level":"info","command":"search","data":{"id":"ba772ce8-d86d-43aa-b98a-f6ca82fca73f","filename":"w2.txt","snippet":"...tax withheld from wages...","rank":-2.91}}
{"schema":"folio.event.v1","event_version":1,"event":"search.completed","ts":"2026-05-20T15:14:00Z","level":"info","command":"search","data":{"query":"tax return","count":2,"limit":10}}
```

`folio open <id>`:
```json
{"schema":"folio.event.v1","event_version":1,"event":"open.completed","ts":"2026-05-20T15:15:23Z","level":"info","command":"open","data":{"id":"3d278e8f-3aef-4df5-b62d-f6b36e84a36f","tmp_path":"/Users/alice/Folio/tmp/3d278e8f.pdf","launched":true}}
```

`folio open <id> --persist`:
```json
{"schema":"folio.event.v1","event_version":1,"event":"open.completed","ts":"2026-05-20T15:15:49Z","level":"info","command":"open","data":{"id":"3d278e8f-3aef-4df5-b62d-f6b36e84a36f","persisted":true,"export_path":"/Users/alice/Folio/exports/file.pdf","launched":true}}
```

Fatal error:
```json
{"schema":"folio.event.v1","event_version":1,"event":"error","ts":"2026-05-20T15:16:11Z","level":"error","command":"open","data":{"code":"NOT_FOUND","message":"Document id not found","id":"deadbeef"}}
```

### Schema Testability Requirements

- Commit JSON Schema files under `schemas/events/v1/`.
- Include envelope schema and one schema per event type.
- Add pytest contract tests that run CLI commands and validate each JSONL line against:
  - envelope schema
  - event schema selected by `event`
- CI must fail on schema validation errors.
- Add regression tests to ensure:
  - `--schema v1` always emits `schema=folio.event.v1`
  - required fields in existing v1 events are not removed
  - error-path output also conforms to schema

## 11. Future Sync Extension (Design Seam Only)

Define provider strategy interface now; do not implement providers in v1.

Core components (future):
- `SyncManager` (orchestrator)
- `ProviderRegistry`
- `SyncProvider` strategies (`google-drive`, `onedrive`, `proton-drive`, etc.)
- `SyncStateStore` (backed by `sync_state` table/config)

Provider contract (conceptual):
- authenticate
- status
- push changes
- pull changes
- conflict resolution

Canonical internal model should remain provider-agnostic:
- document IDs
- content hashes
- timestamps
- tombstones for deletes (future)

## 12. Acceptance Criteria for v1

- `folio init` creates required directories and DB idempotently.
- `folio add <path>` returns a new ID and persists encrypted file + metadata.
- `folio search "<query>"` returns matching IDs and snippets from indexed docs.
- `folio open <id>` decrypts and launches document through OS open command.
- `folio sync` returns explicit not-implemented message without side effects.
