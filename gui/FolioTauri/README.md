# Folio Tauri Wrapper (Scaffold)

Minimal Tauri shell that calls the existing `folio` CLI.

## Prereqs

- Rust toolchain
- Node/npm
- `folio` available in PATH

## Run

```bash
cd gui/FolioTauri
npm install
npm run tauri dev
```

## Scope in this scaffold

- Single window app
- Rust `run_folio` command bridge
- Basic UI that calls `folio search <query>`

## Next steps

1. Add tray/menu bar integration.
2. Add global shortcut (`Option+F`).
3. Add drag-and-drop file ingestion (`folio add <path>`).
4. Stream and parse JSONL events instead of printing raw stdout.
