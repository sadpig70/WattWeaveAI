"""W11 — Compliance/AuditLog.

Append-only JSONL store. Each record bundles the workload, the routing
decision, the compliance tag, and the snapshots that were visible at
decision time — the bundle is what makes the decision *replayable*.

NOTE (P2-1, deferred): MVP does not sign records. Future milestone will
add a PQC signature (ML-DSA) over the canonical record bytes so audits
survive insider tampering. The interface below is shaped to accept a
signer callable in v0.2 without breaking callers.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..types import AuditRecord


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, record: AuditRecord) -> None:
        line = json.dumps(_to_jsonable(record), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def replay(self, workload_id: str) -> list[dict]:
        out: list[dict] = []
        if not self.path.exists():
            return out
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("workload", {}).get("workload_id") == workload_id:
                    out.append(row)
        return out

    def iter_records(self) -> Iterator[dict]:
        if not self.path.exists():
            return iter([])
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


def _to_jsonable(record: AuditRecord) -> dict:
    raw = asdict(record)
    return _coerce(raw)


def _coerce(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce(v) for v in value]
    return value
