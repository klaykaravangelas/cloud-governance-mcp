"""Resolve bounded RDS relationships from masked, transient desired values.

No AWS call or compliance decision belongs here. Raw matching strings live only
in this invocation; snapshots and OPA receive states and Terraform addresses.
"""

import re
from collections import Counter
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from cloud_governance_mcp.models import (
    IdentityText,
    NormalizedResource,
    ResolvedAssociation,
    UnresolvedAssociation,
)
from cloud_governance_mcp.projection import (
    AWS_PROVIDER,
    RDS_RESOURCE_TYPES,
    attribute_state,
    project_desired,
)

_TEXT = TypeAdapter(IdentityText)
_ARN = re.compile(
    r"arn:(aws|aws-cn|aws-us-gov):rds:([a-z0-9-]{1,64}):([0-9]{12}):(cluster|db):([^:]+)"
)
type _Context = tuple[str, str, str]
type _Key = tuple[_Context, str]


@dataclass(repr=False)
class _Linkage:
    """Private lookup evidence; unknown dimensions remain wildcard blockers."""

    state: str
    identifier: str | None = None
    context: _Context | None = None


def _known_text(state: str, value: object) -> str | None:
    """Never parse a masked value or let rejected provider values escape."""
    if state != "known":
        return None
    try:
        return _TEXT.validate_python(value, strict=True)
    except ValidationError:
        return None


def _linkage(
    resource: NormalizedResource, desired: dict[str, object] | None
) -> _Linkage:
    """Retain only independently known dimensions for collision/exclusion tests."""
    keys = ("cluster_identifier", "arn", "region")
    states = {key: attribute_state(resource, desired, key) for key in keys}
    values = desired if desired is not None else {}
    identifier = _known_text(
        states["cluster_identifier"], values.get("cluster_identifier")
    )
    arn = _known_text(states["arn"], values.get("arn"))
    region = _known_text(states["region"], values.get("region"))
    match = _ARN.fullmatch(arn) if arn is not None else None
    kind = "cluster" if resource.resource.resource_type == "aws_rds_cluster" else "db"
    context = (match[1], match[3], match[2]) if match and match[4] == kind else None
    # Conflicting known fields invalidate the entire key. Neither contradictory
    # value is reliable evidence for excluding a possible duplicate cluster.
    conflict = context is not None and (
        (kind == "cluster" and identifier is not None and match[5] != identifier)
        or (states["region"] == "known" and region != context[2])
    )
    if conflict:
        identifier, context = None, None
    elif states["region"] not in {"known", "missing", "null"}:
        context = None

    # Privacy and uncertainty precede missing/type observations across all fields.
    for state in ("sensitive", "unknown", "unverified", "unavailable"):
        if state in states.values():
            return _Linkage(state, identifier, context)
    if states["cluster_identifier"] in {"missing", "null"}:
        return _Linkage(states["cluster_identifier"], identifier, context)
    if (
        identifier is None
        or conflict
        or (states["region"] == "known" and region is None)
    ):
        return _Linkage("invalid_type", identifier, context)
    if states["arn"] in {"missing", "null"}:
        return _Linkage("context_unverified", identifier, context)
    if context is None:
        return _Linkage("invalid_type", identifier, context)
    return _Linkage("known", identifier, context)


def project_rds_resources(
    resources: list[NormalizedResource],
    desired_by_address: dict[str, dict[str, object] | None],
) -> None:
    """Attach direct projections and proved links in two linear passes.

    The caller supplies authoritative desired objects after mask union. Hash
    indexes cover exact keys plus each possible incomplete-key combination, so
    unknown clusters cannot be omitted and no cluster/member pair scan is needed.
    All indexes and strings are discarded on return; only projections are mutated.
    """
    exact: Counter[_Key] = Counter()
    addresses: dict[_Key, str] = {}
    unknown_context: set[str] = set()
    unknown_identifier: set[_Context] = set()
    unscoped = False
    members: list[tuple[NormalizedResource, _Linkage]] = []
    for resource in resources:
        identity = resource.resource
        if (
            identity.provider_name != AWS_PROVIDER
            or identity.mode != "managed"
            or identity.action_category == "delete"
            or identity.resource_type not in RDS_RESOURCE_TYPES
        ):
            continue
        desired = desired_by_address.get(identity.address)
        resource.desired_state = project_desired(resource, desired)
        if identity.resource_type == "aws_db_instance":
            continue
        link = _linkage(resource, desired)
        if identity.resource_type == "aws_rds_cluster_instance":
            members.append((resource, link))
        elif link.identifier is not None and link.context is not None:
            key = (link.context, link.identifier)
            exact[key] += 1
            addresses[key] = identity.address
        elif link.identifier is not None:
            unknown_context.add(link.identifier)
        elif link.context is not None:
            unknown_identifier.add(link.context)
        else:
            unscoped = True

    for resource, link in members:
        state = link.state
        if state == "known":
            key = (link.context, link.identifier)
            if exact[key] > 1:
                state = "ambiguous"
            elif (
                unscoped
                or link.identifier in unknown_context
                or link.context in unknown_identifier
            ):
                state = "context_unverified"
            elif exact[key] == 1:
                resource.desired_state.association = ResolvedAssociation(
                    cluster_address=addresses[key]
                )
                continue
            else:
                state = "not_found"
        resource.desired_state.association = UnresolvedAssociation(state=state)
