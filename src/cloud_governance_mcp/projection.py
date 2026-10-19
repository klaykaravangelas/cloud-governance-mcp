"""Project required RDS values only after both sources' masks have been merged.

This module classifies knowledge, not compliance. Real Rego makes the encryption
decision. Raw strings, invalid values and unrelated fields never leave here.
"""

from cloud_governance_mcp.evaluation_models import EvaluationInput, ProjectedResource
from cloud_governance_mcp.models import (
    DesiredStateProjection,
    KnownEncryption,
    NormalizedResource,
    ResourceSnapshot,
    UncertainEncryption,
)

AWS_PROVIDER = "registry.terraform.io/hashicorp/aws"


def is_candidate(resource: NormalizedResource) -> bool:
    """Classify scope without inspecting attributes or making a policy decision."""
    identity = resource.resource
    return (
        identity.mode == "managed"
        and identity.action_category != "delete"
        and identity.provider_name == AWS_PROVIDER
        and identity.resource_type == "aws_db_instance"
    )


def project_desired(
    resource: NormalizedResource, desired: dict[str, object] | None
) -> DesiredStateProjection:
    """Remove values covered by root/attribute masks before forming engine input."""

    def state(key: str) -> str:
        # [] is an ancestor of every path; integer indices never equal keys.
        for paths, label in (
            (resource.sensitive_paths, "sensitive"),
            (resource.unknown_paths, "unknown"),
        ):
            # A descendant mask contradicts a scalar boolean/string shape. It
            # still blocks knowledge rather than letting a malformed plan pass.
            if any(not path or path[0] == key for path in paths):
                return label
        if not resource.unknown_metadata_complete:
            return "unverified"
        if desired is None:
            return "unavailable"
        if key not in desired:
            return "missing"
        if desired[key] is None:
            return "null"
        return "known"

    encryption_state = state("storage_encrypted")
    value = desired.get("storage_encrypted") if desired is not None else None
    if encryption_state == "known" and type(value) is not bool:
        encryption_state = "invalid_type"
    encryption = (
        KnownEncryption(value=value)
        if encryption_state == "known"
        else UncertainEncryption(state=encryption_state)
    )
    scope = state("cluster_identifier")
    if scope in {"missing", "null"}:
        scope = "standalone"
    elif scope == "known":
        cluster = desired["cluster_identifier"]
        scope = (
            ("cluster_associated" if cluster else "standalone")
            if type(cluster) is str
            else "invalid_type"
        )
    return DesiredStateProjection(scope=scope, encryption=encryption)


def to_evaluation_input(
    snapshot: ResourceSnapshot, policy_ids: list[str]
) -> EvaluationInput:
    """Expose identities and fixed projection states, never masks or raw plans."""
    return EvaluationInput(
        selected_policy_ids=sorted(policy_ids),
        resources=[
            ProjectedResource(
                address=item.resource.address,
                provider_name=item.resource.provider_name,
                resource_type=item.resource.resource_type,
                mode=item.resource.mode,
                action_category=item.resource.action_category,
                desired_state=item.desired_state
                or DesiredStateProjection(
                    scope="unavailable",
                    encryption=UncertainEncryption(state="unavailable"),
                ),
            )
            for item in snapshot.resources
        ],
    )
