from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import click


@dataclass(frozen=True)
class CliConfig:
    human: bool
    schema: str


SCHEMA_MAP = {"v1": "folio.event.v1"}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit_event(config: CliConfig, command: str, event: str, level: str, data: dict[str, object]) -> None:
    payload = {
        "schema": SCHEMA_MAP[config.schema],
        "event_version": 1,
        "event": event,
        "ts": utc_now_iso(),
        "level": level,
        "command": command,
        "data": data,
    }
    if config.human:
        if event == "init.completed":
            if bool(data.get("created")):
                click.echo(f"Initialized Folio at {data['folio_root']}")
            else:
                click.echo(f"Folio already initialized at {data['folio_root']}")
            return
        click.echo(f"{event}: {data}")
        return
    click.echo(json.dumps(payload, separators=(",", ":")))


def ensure_database(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_rel_path TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                indexed_at TEXT,
                encryption_nonce BLOB NOT NULL,
                encryption_tag BLOB
            );

            CREATE UNIQUE INDEX IF NOT EXISTS documents_sha256_uq ON documents (sha256);
            CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents (created_at);

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                id UNINDEXED,
                content,
                tokenize='porter unicode61'
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                provider TEXT PRIMARY KEY,
                cursor TEXT,
                last_sync_at TEXT,
                status TEXT
            );

            CREATE TABLE IF NOT EXISTS tmp_manifest (
                path TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                pid INTEGER
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


@click.group()
@click.option("--human", is_flag=True, help="Emit human-readable output instead of JSONL.")
@click.option("--schema", "schema_version", default="v1", type=click.Choice(["v1"]), show_default=True)
@click.pass_context
def main(ctx: click.Context, human: bool, schema_version: str) -> None:
    """Folio CLI."""
    ctx.obj = CliConfig(human=human, schema=schema_version)


@main.command()
@click.pass_obj
def init(config: CliConfig) -> None:
    """Initialize Folio storage."""
    folio_root = Path.home() / "Folio"
    paths = [
        folio_root,
        folio_root / "store",
        folio_root / "index",
        folio_root / "tmp",
        folio_root / "exports",
        folio_root / "config",
    ]

    created = False
    for path in paths:
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            created = True

    db_path = folio_root / "index" / "folio.db"
    db_existed = db_path.exists()
    ensure_database(db_path)
    if not db_existed:
        created = True

    emit_event(
        config=config,
        command="init",
        event="init.completed",
        level="info",
        data={"folio_root": str(folio_root), "created": created},
    )


@main.command()
@click.argument("path", type=click.Path(path_type=Path))
def add(path: Path) -> None:
    """Add a document to Folio."""
    click.echo(f"add: not implemented ({path})")


@main.command()
@click.argument("query", type=str)
def search(query: str) -> None:
    """Search documents."""
    click.echo(f"search: not implemented ({query})")


@main.command()
@click.argument("doc_id", type=str)
@click.option("--persist", is_flag=True, help="Persist decrypted file to exports.")
def open(doc_id: str, persist: bool) -> None:
    """Open a document by ID."""
    click.echo(f"open: not implemented (id={doc_id}, persist={persist})")


@main.command()
def sync() -> None:
    """Sync documents to remote provider."""
    click.echo("sync: not implemented")


if __name__ == "__main__":
    main()
