from __future__ import annotations

from pathlib import Path

import click


@click.group()
def main() -> None:
    """Folio CLI."""


@main.command()
def init() -> None:
    """Initialize Folio storage."""
    click.echo("init: not implemented")


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

