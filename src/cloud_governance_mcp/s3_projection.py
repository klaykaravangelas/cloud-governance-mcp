"""Bounded S3 flag projection and conservative same-plan association.

Bucket names and provider keys are transient lookup evidence. Only boolean
observations, fixed uncertainty states and proved Terraform addresses survive.
"""

from collections import Counter

from pydantic import TypeAdapter, ValidationError

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import IdentityText, NormalizedResource
from cloud_governance_mcp.projection import attribute_state
from cloud_governance_mcp.s3_models import (
    S3_FLAGS,
    S3_TYPES,
    KnownS3Flag,
    S3Block,
    S3Bucket,
    UncertainS3Flag,
)

_TEXT = TypeAdapter(IdentityText)


def _text(value: object) -> str | None:
    """Validate transient identifiers without exposing rejected input details."""
    try:
        return _TEXT.validate_python(value, strict=True)
    except ValidationError:
        return None


def _provider_contexts(
    configuration: object, max_depth: int, max_resources: int
) -> dict[tuple[str, str, str, str], tuple[str | None, str | None]]:
    """Map explicit configuration-tree membership, never parse resource addresses.

    Indexed module instances cannot be expanded from this tree, so they safely
    miss the lookup. Duplicate identity metadata invalidates that context.
    """
    if configuration is None:
        return {}
    if not isinstance(configuration, dict):
        raise AnalysisError(ErrorCode.INVALID_PLAN)
    result = {}
    stack = [(configuration.get("root_module", {}), "", 1)]
    work = 0
    while stack:
        module, context, depth = stack.pop()
        if depth > max_depth:
            raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
        if not isinstance(module, dict):
            raise AnalysisError(ErrorCode.INVALID_PLAN)
        resources = module.get("resources", [])
        calls = module.get("module_calls", {})
        if not isinstance(resources, list) or not isinstance(calls, dict):
            raise AnalysisError(ErrorCode.INVALID_PLAN)
        work += len(resources) + len(calls)
        if work > max_resources:
            raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
        for item in resources:
            if not isinstance(item, dict):
                raise AnalysisError(ErrorCode.INVALID_PLAN)
            fields = [item.get(k) for k in ("mode", "type", "name")]
            if any(_text(value) is None for value in fields):
                raise AnalysisError(ErrorCode.INVALID_PLAN)
            key = (context, *fields)
            provider = _text(item.get("provider_config_key"))
            result[key] = (
                (None, None)
                if key in result
                else (provider, _text(item.get("address")))
            )
        for name, call in calls.items():
            if _text(name) is None or not isinstance(call, dict):
                raise AnalysisError(ErrorCode.INVALID_PLAN)
            # Tree keys are explicit module names. Dots/brackets would invent
            # extra membership, so leave such unsupported contexts unmapped.
            if any(c in name for c in ".[]"):
                continue
            child = context + ("." if context else "") + "module." + name
            if len(child) > 2048:
                raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
            stack.append((call.get("module", {}), child, depth + 1))
    return result


def project_s3_resources(
    resources: list[NormalizedResource],
    desired_by_address: dict[str, dict[str, object] | None],
    configuration: object = None,
    *,
    max_depth: int = 128,
    max_resources: int = 10_000,
) -> None:
    """Attach flags and links with linear indexes; discard matching values.

    A concealed name can hide a duplicate in any provider configuration. Global
    blockers deliberately favor uncertainty over a false proof of uniqueness.
    """
    contexts = _provider_contexts(configuration, max_depth, max_resources)
    buckets, blocks = [], []
    names: dict[str, tuple[str, str | None]] = {}
    counts = {kind: Counter() for kind in S3_TYPES}
    hidden = False
    for resource in resources:
        identity = resource.resource
        if (
            identity.provider_name != "registry.terraform.io/hashicorp/aws"
            or identity.mode != "managed"
            or identity.action_category == "delete"
            or identity.resource_type not in S3_TYPES
        ):
            continue
        desired = desired_by_address.get(identity.address)
        state = attribute_state(resource, desired, "bucket")
        name = _text(desired.get("bucket")) if state == "known" else None
        if state == "known" and name is None:
            state = "invalid_type"
        names[identity.address] = (state, name)
        if name is None:
            hidden = True
        else:
            counts[identity.resource_type][name] += 1
        if identity.resource_type == S3_TYPES[0]:
            buckets.append(resource)
            continue
        blocks.append(resource)
        flags = []
        for flag in S3_FLAGS:
            flag_state = attribute_state(resource, desired, flag)
            value = desired.get(flag) if flag_state == "known" else None
            if flag_state == "known" and type(value) is not bool:
                flag_state = "invalid_type"
            flags.append(
                KnownS3Flag(value=value)
                if flag_state == "known"
                else UncertainS3Flag(state=flag_state)
            )
        resource.s3_state = S3Block(flags=flags)

    by_name = {
        names[r.resource.address][1]: r
        for r in blocks
        if names[r.resource.address][1] is not None
    }

    def provider(resource: NormalizedResource) -> str | None:
        """Only the explicit module context and shared configuration key prove scope."""
        i = resource.resource
        context = contexts.get(
            (i.module_address or "", i.mode, i.resource_type, i.name)
        )
        if context is None:
            return None
        provider_key, config_address = context
        # Missing module metadata does not establish root membership. An exact
        # opaque configuration identity can prove it without parsing addresses.
        if i.module_address is None and config_address != i.address:
            return None
        return provider_key

    for resource in buckets:
        state, name = names[resource.resource.address]
        if state == "known":
            if any(counts[t][name] > 1 for t in S3_TYPES):
                state = "ambiguous"
            elif hidden:
                state = "context_unverified"
            elif counts[S3_TYPES[1]][name] == 0:
                state = "not_found"
            else:
                block = by_name[name]
                context = provider(resource)
                if context is None or context != provider(block):
                    state = "context_unverified"
                else:
                    resource.s3_state = S3Bucket(
                        state="resolved", block_address=block.resource.address
                    )
                    continue
        resource.s3_state = S3Bucket(state=state)
