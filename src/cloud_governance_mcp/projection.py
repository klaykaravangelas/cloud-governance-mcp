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
    UnresolvedAssociation,
)
from cloud_governance_mcp.policy_definitions import AWS_PROVIDER as AWS_PROVIDER
from cloud_governance_mcp.policy_definitions import (
    RDS_RESOURCE_TYPES as RDS_RESOURCE_TYPES,
)
from cloud_governance_mcp.policy_definitions import RESOURCE_TYPES
from cloud_governance_mcp.tag_models import DEFAULT_TAG_KEYS, TagConfiguration


def attribute_state(
    resource: NormalizedResource, desired: dict[str, object] | None, key: str
) -> str:
    """Classify a scalar field before reading it, including contradictory masks."""
    for paths, label in (
        (resource.sensitive_paths, "sensitive"),
        (resource.unknown_paths, "unknown"),
    ):
        if any(not path or path[0] == key for path in paths):
            return label
    if not resource.unknown_metadata_complete:
        return "unverified"
    if desired is None:
        return "unavailable"
    if key not in desired:
        return "missing"
    return "null" if desired[key] is None else "known"


def is_candidate(
    resource: NormalizedResource, policy_ids: list[str] | None = None
) -> bool:
    """Classify scope without inspecting attributes or making a policy decision."""
    identity = resource.resource
    return (
        identity.mode == "managed"
        and identity.action_category != "delete"
        and identity.provider_name == AWS_PROVIDER
        and any(
            identity.resource_type in RESOURCE_TYPES[p]
            for p in (policy_ids if policy_ids is not None else ["AWS-RDS-001"])
        )
    )


def project_desired(
    resource: NormalizedResource, desired: dict[str, object] | None
) -> DesiredStateProjection:
    """Remove values covered by root/attribute masks before forming engine input."""

    def state(key: str) -> str:
        return attribute_state(resource, desired, key)

    if resource.resource.resource_type == "aws_rds_cluster_instance":
        # A member's exported encryption copy is never decision evidence.
        return DesiredStateProjection(
            scope="cluster_member",
            encryption=UncertainEncryption(state="unavailable"),
            association=UnresolvedAssociation(state="unavailable"),
        )

    encryption_state = state("storage_encrypted")
    value = desired.get("storage_encrypted") if desired is not None else None
    if encryption_state == "known" and type(value) is not bool:
        encryption_state = "invalid_type"
    encryption = (
        KnownEncryption(value=value)
        if encryption_state == "known"
        else UncertainEncryption(state=encryption_state)
    )
    if resource.resource.resource_type == "aws_rds_cluster":
        return DesiredStateProjection(scope="cluster", encryption=encryption)
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
    snapshot: ResourceSnapshot,
    policy_ids: list[str],
    required_tag_keys: tuple[str, ...] = DEFAULT_TAG_KEYS,
) -> EvaluationInput:
    """Expose identities and fixed projection states, never masks or raw plans."""
    return EvaluationInput(
        selected_policy_ids=sorted(policy_ids),
        tag_configuration=TagConfiguration(required_tag_keys=list(required_tag_keys))
        if "AWS-TAG-001" in policy_ids
        else None,
        resources=[
            ProjectedResource(
                address=item.resource.address,
                provider_name=item.resource.provider_name,
                resource_type=item.resource.resource_type,
                mode=item.resource.mode,
                action_category=item.resource.action_category,
                s3_state=item.s3_state,
                ssh_state=item.ssh_state,
                tag_state=item.tag_state,
                desired_state=item.desired_state
                or DesiredStateProjection(
                    scope="unavailable",
                    encryption=UncertainEncryption(state="unavailable"),
                ),
            )
            for item in snapshot.resources
        ],
    )
