"""W3 — Sensing/WorkloadClassifier.

Decode an external dict into a normalized Workload. Strict fields are
parsed deterministically; only ambiguous cases (sovereign inference,
energy-intensity estimation) defer to AI_ stub helpers.

The AI_ helpers here are rule-based stubs — they expose the AI-friendly
signature so a future model can replace the body without callers
changing. This is the Co-evolutionary Property in PG.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..types import (
    ChipType,
    EnergyIntensity,
    LatencyClass,
    SovereignClass,
    Workload,
    WorkloadKind,
)

_VALID_KINDS = {"training", "inference", "fine_tuning", "batch_eval"}
_VALID_LATENCY = {"realtime", "interactive", "batch", "deferred"}
_VALID_SOVEREIGN = {"none", "eu", "us", "kr", "jp", "regulated_health"}
_VALID_CHIPS = {"gpu_h100", "gpu_a100", "gpu_l4", "cpu", "any"}


class ClassificationError(ValueError):
    """Raised when a request cannot be classified into a Workload."""


def classify_workload(raw: dict[str, Any]) -> Workload:
    workload_id = str(raw.get("workload_id") or _missing("workload_id"))

    kind = _enum(raw, "kind", _VALID_KINDS, default="inference")
    latency_class = _enum(raw, "latency_class", _VALID_LATENCY, default="batch")
    chip_required = _enum(raw, "chip_required", _VALID_CHIPS, default="any")

    estimated_kwh = float(raw.get("estimated_kwh", 0.0))
    if estimated_kwh < 0:
        raise ClassificationError("estimated_kwh must be >= 0")
    estimated_minutes = int(raw.get("estimated_minutes", 1))
    if estimated_minutes < 0:
        raise ClassificationError("estimated_minutes must be >= 0")

    sovereign_class: SovereignClass
    explicit_sovereign = raw.get("sovereign_class")
    if explicit_sovereign:
        if explicit_sovereign not in _VALID_SOVEREIGN:
            raise ClassificationError(f"sovereign_class invalid: {explicit_sovereign}")
        sovereign_class = explicit_sovereign  # type: ignore[assignment]
    else:
        sovereign_class = AI_infer_sovereign_class(
            description=str(raw.get("description", "")),
            kind=kind,
        )

    energy_intensity: EnergyIntensity
    explicit_intensity = raw.get("energy_intensity")
    if explicit_intensity:
        energy_intensity = explicit_intensity  # type: ignore[assignment]
    else:
        energy_intensity = AI_estimate_energy_intensity(
            kind=kind,
            estimated_kwh=estimated_kwh,
            estimated_minutes=estimated_minutes,
        )

    submitted_raw = raw.get("submitted_at")
    submitted_at = _parse_dt(submitted_raw) if submitted_raw else datetime.now(timezone.utc)

    return Workload(
        workload_id=workload_id,
        kind=kind,  # type: ignore[arg-type]
        latency_class=latency_class,  # type: ignore[arg-type]
        energy_intensity=energy_intensity,
        sovereign_class=sovereign_class,
        estimated_kwh=estimated_kwh,
        estimated_minutes=estimated_minutes,
        chip_required=chip_required,  # type: ignore[arg-type]
        submitted_at=submitted_at,
        description=str(raw.get("description", "")),
    )


def AI_infer_sovereign_class(description: str, kind: WorkloadKind) -> SovereignClass:
    text = description.lower()
    if any(k in text for k in ("hipaa", "phi ", "patient", "clinical")):
        return "regulated_health"
    if any(k in text for k in ("gdpr", "eu citizen", "european", "schrems")):
        return "eu"
    if any(k in text for k in ("kvkk", "korea ai act", "korean residents")):
        return "kr"
    if "japan" in text or "apjc" in text:
        return "jp"
    if any(k in text for k in ("ccpa", "us federal", "doc us")):
        return "us"
    return "none"


def AI_estimate_energy_intensity(
    kind: WorkloadKind,
    estimated_kwh: float,
    estimated_minutes: int,
) -> EnergyIntensity:
    if estimated_minutes <= 0:
        return "low"
    rate = estimated_kwh / max(estimated_minutes, 1) * 60.0
    if kind == "training" and rate >= 50.0:
        return "extreme"
    if rate >= 20.0:
        return "high"
    if rate >= 5.0:
        return "medium"
    return "low"


def _enum(raw: dict[str, Any], field: str, choices: set[str], default: str) -> str:
    value = raw.get(field, default)
    if value not in choices:
        raise ClassificationError(f"{field} invalid: {value!r} (choices={sorted(choices)})")
    return value


def _missing(field: str) -> str:
    raise ClassificationError(f"required field missing: {field}")


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ClassificationError(f"submitted_at must be ISO string or datetime: {value!r}")
