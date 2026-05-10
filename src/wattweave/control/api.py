"""W13 — ControlPlane/RestApi.

FastAPI surface. Routes through `OrchestrationFacade`; no business
logic lives here. The factory pattern lets tests inject a custom facade.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException

from .facade import OrchestrationFacade, build_default_facade


def create_app(facade: OrchestrationFacade | None = None) -> FastAPI:
    facade = facade or build_default_facade()
    app = FastAPI(title="WattWeaveAI Control Plane", version="0.1.0")

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/v1/zones")
    def zones() -> list[dict[str, Any]]:
        return [asdict(z) for z in facade.registry.all()]

    @app.post("/v1/workloads")
    def submit(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            decision, record_id = facade.submit(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "decision": _decision_to_dict(decision),
            "audit_record_id": record_id,
        }

    @app.get("/v1/workloads/{workload_id}/audit")
    def audit(workload_id: str) -> list[dict[str, Any]]:
        return facade.audit.replay(workload_id)

    return app


def _decision_to_dict(decision) -> dict[str, Any]:
    raw = asdict(decision)
    if raw.get("decided_at") is not None:
        raw["decided_at"] = decision.decided_at.isoformat()
    return raw
