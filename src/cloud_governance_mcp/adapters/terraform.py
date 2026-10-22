"""Validate Terraform plan JSON and merge its identities/actions into a snapshot.

Only consumed fields are validated. Analysis discards provider attributes;
evaluation can opt into a minimal masked desired-state projection. This adapter has no filesystem, transport,
AWS, Terraform CLI, or policy-engine dependency.
"""

import re
from dataclasses import dataclass
from typing import cast

from pydantic import TypeAdapter, ValidationError

from cloud_governance_mcp.errors import AnalysisError, ConfigurationError, ErrorCode
from cloud_governance_mcp.models import (
    ACTION_CATEGORIES,
    WARNING_MESSAGES,
    AnalysisWarning,
    AttributePath,
    IdentityText,
    NormalizedResource,
    PositiveInt,
    ResourceAnalysis,
    ResourceSnapshot,
    WarningCode,
)
from cloud_governance_mcp.normalization import extract_mask_paths, merge_mask_paths
from cloud_governance_mcp.rds_associations import project_rds_resources
from cloud_governance_mcp.s3_projection import project_s3_resources
from cloud_governance_mcp.ssh_projection import project_ssh_resources
from cloud_governance_mcp.tag_models import DEFAULT_TAG_KEYS
from cloud_governance_mcp.tag_projection import project_tag_resources

_TEXT = TypeAdapter(IdentityText)
_POSITIVE_INT = TypeAdapter(PositiveInt)
_OPTIONAL_IDENTITIES = ("index", "module_address", "previous_address")


def _object(value: object) -> dict[str, object]:
    """Require a JSON object where the adapter consumes an object structure."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise AnalysisError(ErrorCode.INVALID_PLAN)
    return cast(dict[str, object], value)


def _array(value: object) -> list[object]:
    """Distinguish omitted arrays (defaulted by callers) from explicit nulls."""
    if not isinstance(value, list):
        raise AnalysisError(ErrorCode.INVALID_PLAN)
    return value


def _text(value: object) -> str:
    """Validate identity text; the outer adapter translates validation details."""
    return _TEXT.validate_python(value, strict=True)


@dataclass(repr=False)
class _Entry:
    """Transient identity/masks and, only when requested, desired source values.

    Raw desired references stay inside normalization until merged masks have
    been applied. They never become part of the returned snapshot.
    """

    normalized: NormalizedResource
    supplied: frozenset[str]
    desired: dict[str, object] | None = None


class TerraformPlanAdapter:
    """Normalize decoded plans with bounded source inventories and mask traversal.

    The loader enforces bytes and full JSON depth. The adapter also bounds its
    module/mask traversal for direct callers and caps each source and merged
    resource inventory. It never mutates the supplied document.
    """

    def __init__(
        self,
        *,
        max_resources: int = 10_000,
        max_depth: int = 128,
        include_policy_values: bool = False,
    ) -> None:
        if type(include_policy_values) is not bool:
            raise ConfigurationError()
        self._include_policy_values = include_policy_values
        try:
            self._max_resources = _POSITIVE_INT.validate_python(
                max_resources, strict=True
            )
            self._max_depth = _POSITIVE_INT.validate_python(max_depth, strict=True)
        except ValidationError:
            raise ConfigurationError() from None

    def normalize(
        self,
        plan: object,
        selected_policy_ids: list[str] | None = None,
        required_tag_keys: tuple[str, ...] = DEFAULT_TAG_KEYS,
    ) -> ResourceSnapshot:
        """Return a sorted safe snapshot, or fixed errors with no rejected values."""
        try:
            return self._normalize(
                _object(plan),
                selected_policy_ids
                if selected_policy_ids is not None
                else ["AWS-RDS-001"],
                required_tag_keys,
            )
        except ValidationError as error:
            # Only examine error types. Locations, contexts and inputs can contain
            # sensitive names/values and must not enter diagnostics or logs.
            oversized = any(
                item["type"] == "string_too_long"
                for item in error.errors(include_input=False, include_context=False)
            )
            code = (
                ErrorCode.PLAN_LIMIT_EXCEEDED if oversized else ErrorCode.INVALID_PLAN
            )
            raise AnalysisError(code) from None

    def _normalize(
        self,
        plan: dict[str, object],
        selected_policy_ids: list[str],
        required_tag_keys: tuple[str, ...],
    ) -> ResourceSnapshot:
        """Validate the envelope before indexing changes and recursive inventory."""
        version = _text(plan.get("format_version"))
        match = re.fullmatch(r"([0-9]+)\.[0-9]+", version)
        if match is None:
            raise AnalysisError(ErrorCode.INVALID_PLAN)
        if int(match[1]) != 1:
            raise AnalysisError(ErrorCode.UNSUPPORTED_PLAN_VERSION)
        if "values" in plan or not {"resource_changes", "planned_values"} & plan.keys():
            raise AnalysisError(ErrorCode.INVALID_PLAN)
        terraform_version = (
            _text(plan["terraform_version"]) if "terraform_version" in plan else None
        )
        warnings: dict[WarningCode, AnalysisWarning] = {}

        def warn(code: WarningCode, count: int | None = None) -> None:
            warnings[code] = AnalysisWarning(
                code=code, message=WARNING_MESSAGES[code], count=count
            )

        # Coverage metadata is explicit: an absent completeness flag does not
        # become true merely because a plan has no reported changes.
        for flag in ("complete", "errored"):
            if flag in plan and type(plan[flag]) is not bool:
                raise AnalysisError(ErrorCode.INVALID_PLAN)
        if "complete" not in plan:
            warn("PLAN_COMPLETENESS_UNSPECIFIED")
        elif not plan["complete"]:
            warn("PLAN_INCOMPLETE")
        if plan.get("errored", False):
            warn("PLAN_ERRORED")
        for field, code in (
            ("deferred_changes", "DEFERRED_CHANGES_PRESENT"),
            ("resource_drift", "RESOURCE_DRIFT_NOT_ANALYZED"),
        ):
            items = _array(plan.get(field, []))
            if items:
                warn(code, len(items))
        outputs = _object(plan.get("output_changes", {}))
        if outputs:
            warn("OUTPUT_CHANGES_NOT_SUMMARIZED", len(outputs))

        changes: dict[str, _Entry] = {}
        raw_changes = _array(plan.get("resource_changes", []))
        self._check_count(len(raw_changes))
        imports = 0
        for raw in raw_changes:
            entry = _object(raw)
            change = _object(entry.get("change"))
            normalized = self._resource(entry, change=change)
            self._insert(changes, normalized)
            if "importing" in change:
                _object(change["importing"])
                imports += 1
        if imports:
            warn("IMPORTS_NOT_SUMMARIZED", imports)

        inventory: dict[str, _Entry] = {}
        if "planned_values" not in plan:
            warn("PLANNED_VALUES_UNAVAILABLE")
        else:
            values = _object(plan["planned_values"])
            self._index_modules(_object(values.get("root_module", {})), inventory)

        self._check_count(len(changes.keys() | inventory.keys()))
        resources: list[NormalizedResource] = []
        for address in sorted(changes.keys() | inventory.keys()):
            if address in changes and address in inventory:
                resources.append(self._merge(changes[address], inventory[address]))
            else:
                resources.append(
                    (changes.get(address) or inventory[address]).normalized
                )
        # Association needs the complete merged graph, not traversal order. Only
        # evaluation retains these transient authoritative desired objects; a
        # missing/null after never falls back to inventory or before.
        if self._include_policy_values:
            desired = {
                item.resource.address: (
                    changes.get(item.resource.address)
                    or inventory[item.resource.address]
                ).desired
                for item in resources
            }
            if "AWS-S3-001" in selected_policy_ids:
                project_s3_resources(
                    resources,
                    desired,
                    plan.get("configuration"),
                    max_depth=self._max_depth,
                    max_resources=self._max_resources,
                )
            if "AWS-RDS-001" in selected_policy_ids:
                project_rds_resources(resources, desired)
            if "AWS-SG-001" in selected_policy_ids:
                projected = project_ssh_resources(resources, desired)
                for item in resources:
                    item.ssh_state = projected.get(item.resource.address)
            if "AWS-TAG-001" in selected_policy_ids:
                tags = project_tag_resources(
                    resources, desired, list(required_tag_keys)
                )
                for item in resources:
                    item.tag_state = tags.get(item.resource.address)
        unreported = sum(item.resource.source == "planned_values" for item in resources)
        if unreported:
            warn("CHANGE_ACTIONS_UNREPORTED", unreported)
        return ResourceSnapshot(
            format_version=version,
            terraform_version=terraform_version,
            resources=resources,
            warnings=[warnings[code] for code in sorted(warnings)],
        )

    def _check_count(self, count: int) -> None:
        """Enforce limits before duplicate-heavy input can be quietly collapsed."""
        if count > self._max_resources:
            raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)

    def _insert(self, index: dict[str, _Entry], entry: _Entry) -> None:
        """Duplicates within either source are invalid, even if their values agree."""
        address = entry.normalized.resource.address
        if address in index:
            raise AnalysisError(ErrorCode.INVALID_PLAN)
        self._check_count(len(index) + 1)
        index[address] = entry

    def _index_modules(self, root: dict[str, object], index: dict[str, _Entry]) -> None:
        """Traverse structured module metadata without parsing resource addresses."""
        pending: list[tuple[dict[str, object], str | None, int]] = [(root, None, 1)]
        seen: set[str] = set()
        while pending:
            module, module_address, depth = pending.pop()
            if depth > self._max_depth:
                raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
            items = _array(module.get("resources", []))
            self._check_count(len(index) + len(items))
            for raw in items:
                self._insert(index, self._resource(_object(raw), module=module_address))
            for raw_child in _array(module.get("child_modules", [])):
                child = _object(raw_child)
                address = _text(child.get("address"))
                if address in seen:
                    raise AnalysisError(ErrorCode.INVALID_PLAN)
                seen.add(address)
                pending.append((child, address, depth + 1))

    def _resource(
        self,
        raw: dict[str, object],
        *,
        change: dict[str, object] | None = None,
        module: str | None = None,
    ) -> _Entry:
        """Validate one source; defer optional projection until mask merging."""
        if "deposed" in raw:
            _text(raw["deposed"])
            raise AnalysisError(ErrorCode.UNSUPPORTED_PLAN_FEATURE)
        identity: dict[str, object] = {
            "address": _text(raw.get("address")),
            "resource_type": _text(raw.get("type")),
            "name": _text(raw.get("name")),
            "provider_name": _text(raw.get("provider_name")),
            "mode": raw.get("mode"),
        }
        supplied = {field for field in _OPTIONAL_IDENTITIES if field in raw}
        for field in _OPTIONAL_IDENTITIES:
            if field not in supplied:
                continue
            if raw[field] is None:
                raise AnalysisError(ErrorCode.INVALID_PLAN)
            identity[field] = raw[field] if field == "index" else _text(raw[field])
        if change is None and "values" in raw and raw["values"] is not None:
            _object(raw["values"])

        unknown: list[AttributePath] = []
        if change is not None:
            actions = _array(change.get("actions"))
            if not actions or any(not isinstance(action, str) for action in actions):
                raise AnalysisError(ErrorCode.INVALID_PLAN)
            category = ACTION_CATEGORIES.get(tuple(actions))
            if category is None:
                raise AnalysisError(ErrorCode.UNSUPPORTED_PLAN_FEATURE)
            for field in ("before", "after"):
                if field in change and change[field] is not None:
                    _object(change[field])
            # Validate before_sensitive too, but do not carry before-state masks
            # into the desired-state sensitivity projection.
            self._mask(change.get("before_sensitive", {}))
            unknown = self._mask(change.get("after_unknown", {}))
            sensitive = self._mask(change.get("after_sensitive", {}))
            identity.update(
                actions=actions, action_category=category, source="resource_changes"
            )
        else:
            if "module_address" in supplied and identity["module_address"] != module:
                raise AnalysisError(ErrorCode.INVALID_PLAN)
            identity.update(
                module_address=module,
                actions=[],
                action_category="unreported",
                source="planned_values",
            )
            # The module tree also establishes root membership.
            supplied.add("module_address")
            sensitive = self._mask(raw.get("sensitive_values", {}))
        return _Entry(
            NormalizedResource(
                resource=ResourceAnalysis.model_validate(identity),
                unknown_paths=unknown,
                sensitive_paths=sensitive,
                unknown_metadata_complete=change is not None
                and "after_unknown" in change,
            ),
            frozenset(supplied),
            (
                (change.get("after") if change is not None else raw.get("values"))
                if self._include_policy_values
                else None
            ),
        )

    def _mask(self, value: object) -> list[AttributePath]:
        """Apply the same conservative mask rules to every supported representation."""
        return extract_mask_paths(value, max_depth=self._max_depth)

    def _merge(self, change: _Entry, inventory: _Entry) -> NormalizedResource:
        """Combine sources only when their identity metadata is consistent."""
        left, right = change.normalized.resource, inventory.normalized.resource
        for field in ("address", "resource_type", "name", "provider_name", "mode"):
            if getattr(left, field) != getattr(right, field):
                raise AnalysisError(ErrorCode.INVALID_PLAN)
        fields = left.model_dump()
        for field in _OPTIONAL_IDENTITIES:
            if field in change.supplied and field in inventory.supplied:
                if getattr(left, field) != getattr(right, field):
                    raise AnalysisError(ErrorCode.INVALID_PLAN)
            elif field in inventory.supplied:
                fields[field] = getattr(right, field)
        fields["source"] = "both"
        return NormalizedResource(
            resource=ResourceAnalysis.model_validate(fields),
            unknown_paths=change.normalized.unknown_paths,
            sensitive_paths=merge_mask_paths(
                change.normalized.sensitive_paths, inventory.normalized.sensitive_paths
            ),
            unknown_metadata_complete=change.normalized.unknown_metadata_complete,
        )
