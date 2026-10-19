"""Build deterministic compliance reports from trusted metadata and checks only."""

from collections import Counter

from cloud_governance_mcp.catalog import PolicyCatalog
from cloud_governance_mcp.evaluation_errors import EVALUATION_MESSAGES, EvaluationCode
from cloud_governance_mcp.evaluation_models import (
    EngineReport,
    EvaluationError,
    EvaluationReport,
    EvaluationSummary,
    Finding,
    PolicyScope,
    compliance_status,
)
from cloud_governance_mcp.models import ResourceSnapshot
from cloud_governance_mcp.projection import is_candidate


def build_report(
    snapshot: ResourceSnapshot,
    policy_ids: list[str],
    catalog: PolicyCatalog,
    result: EngineReport | None = None,
    error: EvaluationCode | None = None,
) -> EvaluationReport:
    """An atomic engine failure preserves scope/counts but trusts zero checks."""
    if (result is None) == (error is None):
        raise ValueError("Provide either a validated result or a safe error.")
    policies = catalog.select(policy_ids)
    identities = {item.resource.address: item.resource for item in snapshot.resources}
    buckets = Counter()
    for item in snapshot.resources:
        # Classify once, in policy precedence order, so coverage buckets cannot
        # overlap (a deleted data source belongs only to skipped_data).
        if item.resource.mode == "data":
            bucket = "skipped_data"
        elif item.resource.action_category == "delete":
            bucket = "skipped_deleted"
        elif is_candidate(item):
            bucket = "candidate_resources"
        else:
            bucket = "unsupported_resources"
        buckets[bucket] += 1
    counts = Counter(check.outcome for check in result.checks) if result else Counter()
    findings, indeterminate = [], []
    lookup = {p.policy_id: p for p in policies}
    for check in result.checks if result else []:
        if check.outcome not in {"fail", "indeterminate"}:
            continue
        policy = lookup[check.policy_id]
        template = policy.reasons[check.reason_code]
        item = Finding(
            policy_id=check.policy_id,
            severity=policy.severity,
            resource_address=check.resource_address,
            resource_type=identities[check.resource_address].resource_type,
            reason_code=check.reason_code,
            attribute_path=template.attribute_path,
            explanation=template.explanation,
            remediation=template.remediation,
        )
        (findings if check.outcome == "fail" else indeterminate).append(item)
    expected = len(identities) * len(policies)
    evaluated = sum(counts.values())
    summary = EvaluationSummary(
        resources_observed=len(identities),
        **{
            key: buckets[key]
            for key in (
                "candidate_resources",
                "skipped_data",
                "skipped_deleted",
                "unsupported_resources",
            )
        },
        expected_checks=expected,
        evaluated_checks=evaluated,
        unevaluated_checks=expected - evaluated,
        applicable_checks=counts["pass"] + counts["fail"] + counts["indeterminate"],
        passed=counts["pass"],
        failed=counts["fail"],
        indeterminate=counts["indeterminate"],
        not_applicable=counts["not_applicable"],
    )
    scopes = [
        PolicyScope.model_validate(
            {key: getattr(policy, key) for key in PolicyScope.model_fields}
        )
        for policy in policies
    ]
    return EvaluationReport(
        format_version=snapshot.format_version,
        terraform_version=snapshot.terraform_version,
        evaluation_status="failed"
        if error
        else "partial"
        if snapshot.warnings
        else "complete",
        compliance_status=compliance_status(
            summary, errors=error is not None, warnings=bool(snapshot.warnings)
        ),
        selected_policy_ids=sorted(policy_ids),
        policy_scope=scopes,
        findings=sorted(findings, key=lambda x: (x.policy_id, x.resource_address)),
        indeterminate_checks=sorted(
            indeterminate, key=lambda x: (x.policy_id, x.resource_address)
        ),
        errors=[EvaluationError(code=error.value, message=EVALUATION_MESSAGES[error])]
        if error
        else [],
        warnings=snapshot.warnings,
        summary=summary,
    )
