"""Validate S3 graph and result provenance without reading provider attributes."""

from typing import TYPE_CHECKING

from cloud_governance_mcp.s3_models import S3_FLAGS, S3_TYPES

if TYPE_CHECKING:
    from cloud_governance_mcp.evaluation_models import ProjectedResource


def _eligible(resource: ProjectedResource) -> bool:
    """Use identity scope only; data and destroyed resources are never targets."""
    return (
        resource.mode == "managed"
        and resource.action_category != "delete"
        and resource.provider_name == "registry.terraform.io/hashicorp/aws"
        and resource.resource_type in S3_TYPES
    )


def validate_s3_graph(resources: list[ProjectedResource], ids: list[str]) -> None:
    """Require exact representations and eligible same-batch block targets."""
    by_address = {r.address: r for r in resources}
    linked_targets: set[str] = set()
    for resource in resources:
        selected = "AWS-S3-001" in ids and _eligible(resource)
        p = resource.s3_state
        if not selected:
            if p is not None:
                raise ValueError("Unexpected S3 projection.")
            continue
        representation = "bucket" if resource.resource_type == S3_TYPES[0] else "block"
        if p is None or p.representation != representation:
            raise ValueError("Invalid S3 representation.")
        if representation == "bucket" and p.state == "resolved":
            target = by_address.get(p.block_address)
            if (
                target is None
                or p.block_address in linked_targets
                or not _eligible(target)
                or target.resource_type != S3_TYPES[1]
                or target.s3_state is None
                or target.s3_state.representation != "block"
            ):
                raise ValueError("Invalid S3 target.")
            # Name uniqueness proves one bucket per block, unlike RDS members.
            # Preserve that invariant when an injected adapter supplies a graph.
            linked_targets.add(p.block_address)


def allowed_s3_reasons(
    resource: ProjectedResource, resources: dict[str, ProjectedResource]
) -> set[str]:
    """Restrict reason provenance to observed flags or the proved link state.

    Rego performs aggregation and deterministic witness selection. The guard
    prevents forged successes and reasons attributed to unavailable evidence.
    """
    p = resource.s3_state
    if p is None:
        return set()
    kind = "BLOCK"
    if p.representation == "bucket":
        if p.state != "resolved":
            return {"S3_LINK_" + p.state.upper()}
        kind = "BUCKET"
        p = resources[p.block_address].s3_state
    codes = set()
    all_true = True
    for name, flag in zip(S3_FLAGS, p.flags, strict=True):
        if flag.state == "known":
            if not flag.value:
                all_true = False
                codes.add(f"S3_{kind}_{name.upper()}_DISABLED")
        else:
            all_true = False
            codes.add(f"S3_{kind}_{name.upper()}_{flag.state.upper()}")
    if all_true:
        codes.add("S3_" + kind + "_ENABLED")
    return codes
