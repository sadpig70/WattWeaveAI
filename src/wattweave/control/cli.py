"""W14 — ControlPlane/Cli.

stdlib argparse CLI. Delegates to the same `OrchestrationFacade` as the
REST API so behavior is identical across channels.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .facade import OrchestrationFacade, build_default_facade


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wattweave")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_submit = sub.add_parser("submit", help="Route a workload from a JSON file")
    p_submit.add_argument("path", type=Path)

    p_batch = sub.add_parser("submit-batch", help="Route a JSONL batch")
    p_batch.add_argument("path", type=Path)

    p_audit = sub.add_parser("audit", help="Print audit records for a workload id")
    p_audit.add_argument("workload_id")

    sub.add_parser("zones", help="Print the active zone registry")

    args = parser.parse_args(argv)
    facade = build_default_facade()

    if args.cmd == "submit":
        return _cmd_submit(facade, args.path)
    if args.cmd == "submit-batch":
        return _cmd_submit_batch(facade, args.path)
    if args.cmd == "audit":
        return _cmd_audit(facade, args.workload_id)
    if args.cmd == "zones":
        return _cmd_zones(facade)
    parser.error(f"unknown command: {args.cmd}")
    return 2


def _cmd_submit(facade: OrchestrationFacade, path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    decision, record_id = facade.submit(payload)
    out = {"audit_record_id": record_id, "decision": _decision_dict(decision)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_submit_batch(facade: OrchestrationFacade, path: Path) -> int:
    routed = 0
    blocked = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            decision, _ = facade.submit(json.loads(line))
            if decision.chosen_zone_id is None:
                blocked += 1
            else:
                routed += 1
    print(json.dumps({"routed": routed, "blocked": blocked}))
    return 0


def _cmd_audit(facade: OrchestrationFacade, workload_id: str) -> int:
    records = facade.audit.replay(workload_id)
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


def _cmd_zones(facade: OrchestrationFacade) -> int:
    rows = [asdict(z) for z in facade.registry.all()]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def _decision_dict(decision) -> dict:
    raw = asdict(decision)
    if raw.get("decided_at") is not None:
        raw["decided_at"] = decision.decided_at.isoformat()
    return raw


if __name__ == "__main__":
    sys.exit(main())
