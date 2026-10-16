"""Build deterministic public summaries from value-free normalized resources."""

from collections import Counter

from pydantic import ValidationError

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import (
    ActionCounts,
    AnalysisSummary,
    ModeCounts,
    PlanAnalysis,
    ResourceSnapshot,
)


def summarize(snapshot: ResourceSnapshot) -> PlanAnalysis:
    """Count each merged resource once and project only public identities/actions.

    Coverage warnings determine complete/partial status. Neither missing actions
    nor an empty resource set establishes compliance. Invalid internal contracts
    fail safely instead of returning inconsistent counts or validation inputs.
    """
    try:
        # Revalidate even existing models: their mutable collections may have
        # changed since construction. No raw Terraform attributes are needed here.
        snapshot = ResourceSnapshot.model_validate(snapshot)
        resources = sorted(
            (item.resource for item in snapshot.resources),
            key=lambda resource: resource.address,
        )
        actions = Counter(resource.action_category for resource in resources)
        types = Counter(resource.resource_type for resource in resources)
        modes = Counter(resource.mode for resource in resources)
        warnings = sorted(snapshot.warnings, key=lambda warning: warning.code)

        # A replacement has its own category and contributes one resource.
        # Data sources contribute to observed totals but never managed changes.
        changing = sum(
            resource.mode == "managed"
            and resource.action_category in {"create", "update", "delete", "replace"}
            for resource in resources
        )
        return PlanAnalysis(
            format_version=snapshot.format_version,
            terraform_version=snapshot.terraform_version,
            analysis_status="partial" if warnings else "complete",
            summary=AnalysisSummary(
                total_resources=len(resources),
                changing_resources=changing,
                # Include every bucket, even when no resources have that action.
                by_action=ActionCounts.model_validate(
                    {key: actions[key] for key in ActionCounts.model_fields}
                ),
                by_type={key: types[key] for key in sorted(types)},
                by_mode=ModeCounts(managed=modes["managed"], data=modes["data"]),
            ),
            resources=resources,
            warnings=warnings,
        )
    except ValidationError:
        raise AnalysisError(ErrorCode.INTERNAL_ERROR) from None
