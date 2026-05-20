from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schemas" / "events" / "v1"


def run_cli(args: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "folio", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_jsonl(stdout: str) -> list[dict[str, object]]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def load_schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


ENVELOPE_VALIDATOR = Draft202012Validator(load_schema("envelope.json"))
INIT_VALIDATOR = Draft202012Validator(load_schema("init.completed.json"))
ERROR_VALIDATOR = Draft202012Validator(load_schema("error.json"))


def validate_schema(validator: Draft202012Validator, payload: dict[str, object]) -> None:
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, "; ".join(err.message for err in errors)


def test_init_emits_v1_envelope(tmp_path: Path) -> None:
    proc = run_cli(["init"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    events = parse_jsonl(proc.stdout)
    assert len(events) == 1
    event = events[0]
    validate_schema(ENVELOPE_VALIDATOR, event)
    validate_schema(INIT_VALIDATOR, event)


def test_open_missing_id_emits_error_schema(tmp_path: Path) -> None:
    init_proc = run_cli(["init"], tmp_path)
    assert init_proc.returncode == 0, init_proc.stderr

    proc = run_cli(["open", "does-not-exist"], tmp_path)
    assert proc.returncode != 0
    events = parse_jsonl(proc.stdout)
    assert len(events) >= 1
    event = events[-1]
    validate_schema(ENVELOPE_VALIDATOR, event)
    validate_schema(ERROR_VALIDATOR, event)
