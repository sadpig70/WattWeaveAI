"""W10 — Compliance/ComplianceTagger.

Maps a workload's sovereign + kind into the regulatory tag travelling
with it. Compliance metadata is an *input* to scheduling, not a post-hoc
audit — this is the "regulation as scheduling dimension" property called
out in DESIGN §0 and the source documents' creative-emergence strength.
"""

from __future__ import annotations

from ..types import ComplianceTag, EuAiActTier, Workload


def tag_compliance(workload: Workload) -> ComplianceTag:
    eu_tier: EuAiActTier | None = None
    locality: str | None = None
    carbon_reporting = False
    retention = 90  # baseline

    if workload.sovereign_class == "eu":
        eu_tier = _infer_eu_tier(workload)
        locality = "eu"

    if workload.sovereign_class == "us":
        locality = "us"

    if workload.sovereign_class == "kr":
        locality = "kr"

    if workload.sovereign_class == "jp":
        locality = "jp"

    if workload.sovereign_class == "regulated_health":
        eu_tier = "high"
        locality = locality or "regulated_health"
        retention = max(retention, 365 * 7)

    if workload.kind in ("training", "fine_tuning") and workload.estimated_kwh >= 100.0:
        carbon_reporting = True

    if workload.energy_intensity in ("high", "extreme"):
        carbon_reporting = True

    return ComplianceTag(
        workload_id=workload.workload_id,
        eu_ai_act_tier=eu_tier,
        data_locality_required=locality,
        carbon_reporting_required=carbon_reporting,
        audit_retention_days=retention,
    )


def _infer_eu_tier(workload: Workload) -> EuAiActTier:
    text = workload.description.lower()
    if any(k in text for k in ("biometric", "law enforcement", "credit scoring")):
        return "high"
    if any(k in text for k in ("recommendation", "content", "moderation")):
        return "limited"
    if workload.kind in ("training", "fine_tuning"):
        return "limited"
    return "minimal"
