"""Validate TAG reason/path provenance without duplicating Rego aggregation."""

from cloud_governance_mcp.evaluation_models import CheckResult, ProjectedResource
from cloud_governance_mcp.policy_definitions import COMMON_REASONS


def valid_tag_check(check: CheckResult, resource: ProjectedResource) -> bool:
    """Only configured entry names may extend a TAG catalog's fixed map path.

    Input graph validation has already proved exact entry/config membership.
    Rego chooses the winning key; here each emitted reason must describe a real
    observation, and withheld states can never carry a successful known result.
    """
    code, path = check.reason_code, check.attribute_path
    if code in COMMON_REASONS:
        return path == []
    projection = resource.tag_state
    if projection is None:
        return False
    if projection.source == "unresolved":
        return code == "TAG_" + projection.state.upper() and path == []
    prefix = "TAG_ALL_" if projection.source == "tags_all" else "TAG_RESOURCE_"
    if projection.state != "known":
        return code == prefix + "MAP_" + projection.state.upper() and path == [
            projection.source
        ]
    if code == prefix + "COMPLIANT":
        return path == [projection.source] and all(
            e.state == "nonempty" for e in projection.entries
        )
    if len(path) != 2 or path[0] != projection.source or type(path[1]) is not str:
        return False
    entry = next((e for e in projection.entries if e.key == path[1]), None)
    suffix = (
        {
            "missing": "KEY_MISSING",
            "blank": "KEY_EMPTY",
            "null": "KEY_EMPTY",
            "sensitive": "KEY_SENSITIVE",
            "unknown": "KEY_UNKNOWN",
            "invalid_type": "KEY_INVALID_TYPE",
        }.get(entry.state)
        if entry is not None
        else None
    )
    return suffix is not None and code == prefix + suffix
