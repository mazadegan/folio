# Folio macOS GUI Wrapper Spec (v1)

## 1. Scope

Build a native macOS app wrapper for the existing `folio` CLI that:
- Lives in the menu bar.
- Can be summoned with a global shortcut (`Option + F`).
- Shows a window for search and drag-and-drop add.
- Uses CLI JSONL events as the single integration contract.

Out of scope for this phase:
- Replacing core vault logic from CLI.
- Sync provider UI.
- Semantic search UX.

## 2. Platform and Stack

- App runtime: native Swift binary (`SwiftUI` app).
- Primary shell: macOS app bundle.
- Backend operations: invoke local `folio` CLI via `Process`.
- Build workflow:
  - Prototype may use SwiftPM.
  - Shipping workflow uses Xcode for signing/entitlements/distribution.

## 3. Product Behavior

### Menu Bar Presence
- App runs as a menu bar app (`MenuBarExtra`).
- Menu includes:
  - `Open Folio` (shows/focuses main window)
  - `Search...` (focuses query field)
  - `Add File...` (opens file picker and calls `folio add`)
  - `Quit`

### Global Shortcut
- Default shortcut: `Option + F`.
- Trigger opens/focuses the main window and focuses search field.
- Shortcut should be configurable later; fixed default in v1.

### Main Window
- Compact, always-available utility window.
- Sections:
  - Search input
  - Search results list
  - Drag-and-drop drop zone
  - Optional status footer (last event/error)
- Dragging files into drop zone runs `folio add <path>`.

### Search Flow
- Typing in search field performs debounced query.
- App runs `folio search "<query>" --limit N`.
- Parse streamed JSONL events:
  - `search.result` => append row
  - `search.completed` => finalize state
  - `error` => show error inline

### Open Flow
- Selecting/clicking a result runs `folio open <id>`.
- App reacts to:
  - `open.completed` => success UI hint
  - `error` with `AUTH_CANCELED` => non-fatal “Canceled” state
  - other `error` => user-visible failure

### Add Flow
- DnD or file picker runs `folio add <path>`.
- Event handling:
  - `add.completed` => success row/toast
  - `add.duplicate` => non-fatal duplicate notice
  - `add.indexing_warning` => warning badge/message
  - `error` => failure display

## 4. CLI Integration Contract

### Invocation
- Use `Process` with explicit executable path for `folio`.
- Capture `stdout` as line stream.
- Decode each line as JSON object.

### Required Event Envelope
Expect:
- `schema = "folio.event.v1"`
- `event_version = 1`
- `event`
- `level`
- `command`
- `data`

### Error Semantics
- `AUTH_CANCELED` is a first-class, non-fatal user action state.
- Other `error.code` values should be displayed with actionable text.

## 5. Initialization and Health

At launch:
1. Verify `folio` executable is discoverable.
2. Run `folio init` (idempotent).
3. If init fails, show setup error UI with retry.

Optional health command:
- Run `folio doctor` and display warning badge in menu if degraded.

## 6. UX Requirements

- Search should feel instant:
  - Debounce input (~150-250ms).
  - Cancel stale searches when new query starts.
- Window reopen should preserve recent query and results for session.
- DnD target should visibly react on hover/acceptance.
- Clear, quiet feedback for auth cancel vs actual errors.

## 7. Security Model

- GUI does not handle vault keys directly.
- All key access and biometric prompts are delegated to `folio` + helper.
- GUI stores no plaintext document content outside transient UI memory.

## 8. Packaging and Distribution Notes

- Final app should bundle or reliably reference the `folio` CLI binary.
- If bundled, define a deterministic path and process-launch strategy.
- Use Xcode-managed signing for release builds.

## 9. Acceptance Criteria (GUI v1)

- App appears in menu bar and can quit from menu.
- `Option + F` opens/focuses main window.
- Dragging a file into the window triggers `folio add` and shows result.
- Searching shows streamed results from `folio search`.
- Selecting a result triggers `folio open`.
- `AUTH_CANCELED` is handled distinctly from hard failures.
- App launch runs `folio init` safely and handles failure states.
