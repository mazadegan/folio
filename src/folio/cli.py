from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class CliConfig:
    human: bool
    schema: str


SCHEMA_MAP = {"v1": "folio.event.v1"}
KEYRING_SERVICE = "folio-cli"
KEYRING_ACCOUNT = "master-key-v1"
PDF_MIME = "application/pdf"
TMP_TTL_MINUTES = 10


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


def emit_error_and_exit(config: CliConfig, command: str, code: str, message: str, **extra: object) -> None:
    payload: dict[str, object] = {"code": code, "message": message}
    payload.update(extra)
    emit_event(config, command=command, event="error", level="error", data=payload)
    raise click.exceptions.Exit(1)


def folio_root() -> Path:
    return Path.home() / "Folio"


def folio_db_path() -> Path:
    return folio_root() / "index" / "folio.db"


def require_initialized(config: CliConfig, command: str) -> None:
    root = folio_root()
    db = folio_db_path()
    if not root.exists() or not db.exists():
        emit_error_and_exit(config, command, "NOT_INITIALIZED", "Folio is not initialized. Run `folio init`.")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def get_or_create_master_key() -> bytes:
    security = shutil.which("security")
    if security is None:
        raise RuntimeError("macOS Keychain tool `security` not found in PATH.")

    find_cmd = [security, "find-generic-password", "-a", KEYRING_ACCOUNT, "-s", KEYRING_SERVICE, "-w"]
    found = subprocess.run(find_cmd, capture_output=True, text=True, check=False)
    if found.returncode == 0:
        return base64.urlsafe_b64decode(found.stdout.strip().encode("utf-8"))

    key = os.urandom(32)
    encoded = base64.urlsafe_b64encode(key).decode("utf-8")

    add_cmd = [
        security,
        "add-generic-password",
        "-U",
        "-a",
        KEYRING_ACCOUNT,
        "-s",
        KEYRING_SERVICE,
        "-w",
        encoded,
    ]
    added = subprocess.run(add_cmd, capture_output=True, text=True, check=False)
    if added.returncode != 0:
        stderr = added.stderr.strip() or "unknown keychain error"
        raise RuntimeError(stderr)
    return key


def encrypt_bytes(plaintext: bytes, key: bytes) -> tuple[bytes, bytes, bytes]:
    nonce = os.urandom(12)
    aes = AESGCM(key)
    sealed = aes.encrypt(nonce, plaintext, associated_data=None)
    ciphertext = sealed[:-16]
    tag = sealed[-16:]
    return nonce, tag, ciphertext


def decrypt_bytes(ciphertext: bytes, nonce: bytes, tag: bytes, key: bytes) -> bytes:
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext + tag, associated_data=None)


def extract_text(path: Path, mime_type: str | None) -> tuple[str | None, str | None]:
    if mime_type == PDF_MIME or path.suffix.lower() == ".pdf":
        pdftotext = shutil.which("pdftotext")
        if pdftotext is None:
            return None, "pdftotext is required for PDF files but was not found in PATH."
        proc = subprocess.run(
            [pdftotext, str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None, "Failed to extract text from PDF with pdftotext."
        return proc.stdout.strip(), None

    is_text = (mime_type or "").startswith("text/") or path.suffix.lower() in {".txt", ".md", ".csv", ".json"}
    if not is_text:
        return None, None

    try:
        return path.read_text(encoding="utf-8", errors="replace").strip(), None
    except OSError:
        return None, "Failed to read text content for indexing."


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
    config = click.get_current_context().obj
    assert isinstance(config, CliConfig)
    command = "add"
    require_initialized(config, command)

    source = path.expanduser().resolve()
    if not source.exists():
        emit_error_and_exit(config, command, "NOT_FOUND", "Input path does not exist.", path=str(source))
    if not source.is_file():
        emit_error_and_exit(config, command, "INVALID_PATH", "Input path must be a file.", path=str(source))

    digest = file_sha256(source)
    now = utc_now_iso()
    db_path = folio_db_path()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT id, original_name FROM documents WHERE sha256 = ?", (digest,)).fetchone()
        if row:
            emit_event(
                config,
                command=command,
                event="add.duplicate",
                level="info",
                data={"id": row[0], "filename": row[1], "sha256": digest, "imported": False},
            )
            return

        doc_id = str(uuid.uuid4())
        stored_rel_path = Path("store") / f"{doc_id}.bin"
        stored_abs_path = folio_root() / stored_rel_path
        key = get_or_create_master_key()
        nonce, tag, ciphertext = encrypt_bytes(source.read_bytes(), key)
        stored_abs_path.write_bytes(ciphertext)

        mime_type = mimetypes.guess_type(source.name)[0]
        indexed_at: str | None = None
        indexed = False
        text_content, extraction_error = extract_text(source, mime_type)
        if text_content:
            conn.execute("INSERT INTO documents_fts (id, content) VALUES (?, ?)", (doc_id, text_content))
            indexed_at = now
            indexed = True

        conn.execute(
            """
            INSERT INTO documents (
                id, original_name, stored_rel_path, mime_type, size_bytes, sha256,
                created_at, indexed_at, encryption_nonce, encryption_tag
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                source.name,
                str(stored_rel_path),
                mime_type,
                source.stat().st_size,
                digest,
                now,
                indexed_at,
                nonce,
                tag,
            ),
        )
        conn.commit()
    except click.exceptions.Exit:
        raise
    except RuntimeError as exc:
        conn.rollback()
        emit_error_and_exit(config, command, "KEYCHAIN_ERROR", f"Unable to access Keychain: {exc}")
    except sqlite3.Error as exc:
        conn.rollback()
        emit_error_and_exit(config, command, "INDEX_ERROR", f"Database error while adding file: {exc}")
    finally:
        conn.close()

    if extraction_error:
        if source.suffix.lower() == ".pdf" and "required for PDF" in extraction_error:
            emit_error_and_exit(config, command, "DEPENDENCY_MISSING", extraction_error)
        emit_event(
            config,
            command=command,
            event="add.indexing_warning",
            level="warn",
            data={"id": doc_id, "filename": source.name, "message": extraction_error},
        )

    emit_event(
        config,
        command=command,
        event="add.completed",
        level="info",
        data={"id": doc_id, "filename": source.name, "sha256": digest, "indexed": indexed},
    )


@main.command()
@click.argument("query", type=str)
@click.option("--limit", "limit_", default=10, show_default=True, type=click.IntRange(1, 1000))
@click.pass_obj
def search(config: CliConfig, query: str, limit_: int) -> None:
    """Search documents."""
    command = "search"
    require_initialized(config, command)

    db_path = folio_db_path()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                d.id,
                d.original_name,
                snippet(documents_fts, 1, '[', ']', '...', 12) AS snippet_text,
                bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.id
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit_),
        ).fetchall()
    except sqlite3.Error as exc:
        emit_error_and_exit(config, command, "INDEX_ERROR", f"Search query failed: {exc}")
    finally:
        conn.close()

    for row in rows:
        emit_event(
            config,
            command=command,
            event="search.result",
            level="info",
            data={
                "id": row[0],
                "filename": row[1],
                "snippet": row[2] or "",
                "rank": row[3],
            },
        )

    emit_event(
        config,
        command=command,
        event="search.completed",
        level="info",
        data={"query": query, "count": len(rows), "limit": limit_},
    )


@main.command()
@click.argument("doc_id", type=str)
@click.option("--persist", is_flag=True, help="Persist decrypted file to exports.")
@click.pass_obj
def open(config: CliConfig, doc_id: str, persist: bool) -> None:
    """Open a document by ID."""
    command = "open"
    require_initialized(config, command)

    db_path = folio_db_path()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT original_name, stored_rel_path, encryption_nonce, encryption_tag
            FROM documents
            WHERE id = ?
            """,
            (doc_id,),
        ).fetchone()
        if row is None:
            emit_error_and_exit(config, command, "NOT_FOUND", "Document id not found", id=doc_id)

        original_name, stored_rel_path, nonce, tag = row
        cipher_path = folio_root() / stored_rel_path
        if not cipher_path.exists():
            emit_error_and_exit(
                config,
                command,
                "NOT_FOUND",
                "Encrypted file not found for document id",
                id=doc_id,
                path=str(cipher_path),
            )

        key = get_or_create_master_key()
        ciphertext = cipher_path.read_bytes()
        plaintext = decrypt_bytes(ciphertext, nonce, tag, key)

        name_suffix = Path(original_name).suffix
        if persist:
            out_dir = folio_root() / "exports"
            out_path = out_dir / original_name
            if out_path.exists():
                stem = Path(original_name).stem
                out_path = out_dir / f"{stem}-{doc_id[:8]}{name_suffix}"
        else:
            out_dir = folio_root() / "tmp"
            out_path = out_dir / f"{doc_id}-{uuid.uuid4().hex[:8]}{name_suffix}"
        out_path.write_bytes(plaintext)

        if not persist:
            created_at = utc_now_iso()
            expires_at = (
                datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=TMP_TTL_MINUTES)
            ).isoformat().replace("+00:00", "Z")
            conn.execute(
                """
                INSERT OR REPLACE INTO tmp_manifest (path, created_at, expires_at, pid)
                VALUES (?, ?, ?, ?)
                """,
                (str(out_path), created_at, expires_at, os.getpid()),
            )
            conn.commit()
    except click.exceptions.Exit:
        raise
    except RuntimeError as exc:
        emit_error_and_exit(config, command, "KEYCHAIN_ERROR", f"Unable to access Keychain: {exc}")
    except sqlite3.Error as exc:
        conn.rollback()
        emit_error_and_exit(config, command, "INDEX_ERROR", f"Failed to open document: {exc}", id=doc_id)
    except Exception as exc:
        emit_error_and_exit(config, command, "CRYPTO_ERROR", f"Failed to decrypt document: {exc}", id=doc_id)
    finally:
        conn.close()

    opened = subprocess.run(["open", str(out_path)], capture_output=True, text=True, check=False)
    if opened.returncode != 0:
        stderr = opened.stderr.strip() or "open command failed"
        emit_error_and_exit(config, command, "OPEN_FAILED", stderr, id=doc_id, path=str(out_path))

    emit_event(
        config,
        command=command,
        event="open.completed",
        level="info",
        data={
            "id": doc_id,
            "launched": True,
            "persisted": persist,
            "export_path": str(out_path) if persist else None,
            "tmp_path": str(out_path) if not persist else None,
        },
    )


@main.command()
def sync() -> None:
    """Sync documents to remote provider."""
    click.echo("sync: not implemented")


if __name__ == "__main__":
    main()
