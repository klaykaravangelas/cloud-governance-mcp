"""Project configured tag observations after source/mask union; never compliance.

Raw tag values exist only while classifying required keys. This module performs
no I/O and retains no values, unrequired names, hashes or excerpts.
"""

from dataclasses import dataclass, field

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import NormalizedResource
from cloud_governance_mcp.policy_definitions import AWS_PROVIDER
from cloud_governance_mcp.tag_models import (
    MAX_TAG_KEY_SLOTS,
    TAG_TYPES,
    KnownTagMap,
    TagConfiguration,
    TagEntry,
    TagProjection,
    UncertainTagMap,
    UnresolvedTags,
)


@dataclass(repr=False)
class _MapMask:
    """One linear scan indexes whole-map, malformed-index and key masks."""

    whole: bool = False
    malformed: bool = False
    keys: set[str] = field(default_factory=set)

    def any(self) -> bool:
        """Even a descendant mask prevents treating an omitted map as absent."""
        return self.whole or self.malformed or bool(self.keys)


def _index(paths: list[list[str | int]]) -> tuple[bool, dict[str, _MapMask]]:
    """Key descendants mask their parent value; unrelated fields are ignored."""
    maps = {name: _MapMask() for name in ("tags_all", "tags")}
    root = False
    for path in paths:
        if not path:
            root = True
        elif path[0] in maps:
            mask = maps[path[0]]
            if len(path) == 1:
                mask.whole = True
            elif type(path[1]) is str:
                mask.keys.add(path[1])
            else:
                mask.malformed = True
    return root, maps


def _project(
    resource: NormalizedResource, desired: dict[str, object] | None, keys: list[str]
) -> TagProjection:
    """Choose one authoritative map, then inspect only unmasked required keys."""
    sensitive_root, sensitive = _index(resource.sensitive_paths)
    unknown_root, unknown = _index(resource.unknown_paths)
    for condition, state in (
        (sensitive_root, "sensitive"),
        (unknown_root, "unknown"),
        (not resource.unknown_metadata_complete, "unverified"),
        (desired is None, "unavailable"),
    ):
        if condition:
            return UnresolvedTags(state=state)
    source = (
        "tags_all"
        if "tags_all" in desired
        or sensitive["tags_all"].any()
        or unknown["tags_all"].any()
        else "tags"
    )
    sm, um = sensitive[source], unknown[source]
    sensitive_keys = sensitive["tags_all"].keys | sensitive["tags"].keys
    # Sensitivity crosses duplicate map copies; uncertainty only follows source.
    if any(m.whole or m.malformed for m in sensitive.values()):
        return UncertainTagMap(source=source, state="sensitive")
    if um.whole or um.malformed:
        return UncertainTagMap(source=source, state="unknown")
    value = desired.get(source)
    if type(value) is not dict:
        # Descendant metadata can accompany null/absent placeholders. It cannot
        # disappear simply because the exported container has no known object.
        if sm.any() or any(key in sensitive_keys for key in keys):
            return UncertainTagMap(source=source, state="sensitive")
        if um.any():
            return UncertainTagMap(source=source, state="unknown")
        state = (
            "missing"
            if source not in desired
            else "null"
            if value is None
            else "invalid_type"
        )
        return UncertainTagMap(source=source, state=state)
    entries = []
    for key in keys:
        if key in sensitive_keys:
            state = "sensitive"
        elif key in um.keys:
            state = "unknown"
        elif key not in value:
            state = "missing"
        else:
            item = value[key]
            state = (
                "null"
                if item is None
                else "invalid_type"
                if type(item) is not str
                else "nonempty"
                if item.strip()
                else "blank"
            )
        entries.append(TagEntry(key=key, state=state))
    return KnownTagMap(source=source, entries=entries)


def project_tag_resources(
    resources: list[NormalizedResource],
    desired: dict[str, dict[str, object] | None],
    required_tag_keys: list[str],
) -> dict[str, TagProjection]:
    """Return only eligible observations, bounding work before payload access."""
    keys = TagConfiguration(required_tag_keys=required_tag_keys).required_tag_keys
    result, slots = {}, 0
    for resource in resources:
        identity = resource.resource
        if (
            identity.mode != "managed"
            or identity.action_category == "delete"
            or identity.provider_name != AWS_PROVIDER
            or identity.resource_type not in TAG_TYPES
        ):
            continue
        slots += len(keys)
        if slots > MAX_TAG_KEY_SLOTS:
            raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
        result[identity.address] = _project(
            resource, desired.get(identity.address), keys
        )
    return result
