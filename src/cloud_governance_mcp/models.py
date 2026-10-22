"""Strict analysis contracts, independent of the MCP transport and filesystem."""

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from cloud_governance_mcp.contracts import ContractModel as ContractModel
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.s3_models import S3Projection
from cloud_governance_mcp.ssh_models import SSHProjection
from cloud_governance_mcp.tag_models import TagProjection


def _safe_text(value: str) -> str:
    """Keep reflected text valid for JSON and free of control characters."""
    # Cc covers controls such as NUL/newlines; Cs covers lone Unicode surrogates.
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in value):
        raise ValueError("Text must contain valid Unicode without control characters.")
    return value


def _path_syntax(value: str) -> str:
    """Accept literal local paths without trimming, expanding, or opening them."""
    # Reject URI schemes, including file:, because this tool accepts paths only.
    if not value.strip() or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
        raise ValueError("A nonblank local filesystem path is required.")
    return value


# Reusable field types keep length and text rules consistent across models.
# Annotated constraints also contribute to the JSON schemas exposed to clients.
type IdentityText = Annotated[
    str, StringConstraints(min_length=1, max_length=2048), AfterValidator(_safe_text)
]
type InstanceKey = Annotated[
    str, StringConstraints(max_length=2048), AfterValidator(_safe_text)
]
type PlanPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=4096),
    AfterValidator(_safe_text),
    AfterValidator(_path_syntax),
]
type FormatVersion = Annotated[
    str,
    StringConstraints(max_length=2048, pattern=r"^1\.[0-9]+$"),
    AfterValidator(_safe_text),
]
type Count = Annotated[int, Field(ge=0)]
type PositiveInt = Annotated[int, Field(gt=0)]
# A path such as ["network", 0, "address"] preserves object keys and list indices.
# The empty path [] denotes a mask applying to the whole resource value.
type AttributePath = list[str | Count]
type ResourceMode = Literal["managed", "data"]
type Action = Literal["create", "update", "delete", "no-op", "read"]
type ActionCategory = Literal[
    "create", "update", "delete", "replace", "no_op", "read", "unreported"
]
type ResourceSource = Literal["resource_changes", "planned_values", "both"]
type WarningCode = Literal[
    "PLAN_COMPLETENESS_UNSPECIFIED",
    "PLAN_INCOMPLETE",
    "PLAN_ERRORED",
    "DEFERRED_CHANGES_PRESENT",
    "PLANNED_VALUES_UNAVAILABLE",
    "CHANGE_ACTIONS_UNREPORTED",
    "IMPORTS_NOT_SUMMARIZED",
    "OUTPUT_CHANGES_NOT_SUMMARIZED",
    "RESOURCE_DRIFT_NOT_ANALYZED",
]

# Ordered action sequences stay intact on resources. Both replacement orderings
# count as one replacement; an empty sequence is reserved for inventory-only data.
ACTION_CATEGORIES: Mapping[tuple[str, ...], ActionCategory] = MappingProxyType(
    {
        ("create",): "create",
        ("update",): "update",
        ("delete",): "delete",
        ("delete", "create"): "replace",
        ("create", "delete"): "replace",
        ("no-op",): "no_op",
        ("read",): "read",
        (): "unreported",
    }
)
# Coverage warnings describe what the analysis cannot establish. Their text comes
# from this fixed catalog rather than Terraform attributes or supplied messages.
WARNING_MESSAGES: Mapping[WarningCode, str] = MappingProxyType(
    {
        "PLAN_COMPLETENESS_UNSPECIFIED": "Plan completeness was not reported.",
        "PLAN_INCOMPLETE": "The supplied plan reports incomplete planning.",
        "PLAN_ERRORED": "Only resource actions reported before planning failed are summarized.",
        "DEFERRED_CHANGES_PRESENT": "Deferred changes are excluded from resource counts.",
        "PLANNED_VALUES_UNAVAILABLE": "The summary uses only reported changes.",
        "CHANGE_ACTIONS_UNREPORTED": "Some inventory resources have no reported actions.",
        "IMPORTS_NOT_SUMMARIZED": "Import operations are not summarized separately.",
        "OUTPUT_CHANGES_NOT_SUMMARIZED": "Output changes are excluded from resource counts.",
        "RESOURCE_DRIFT_NOT_ANALYZED": "Resource drift is excluded from resource counts.",
    }
)
# Event warnings need a positive affected-item count; plan-wide flags do not.
_COUNTED_WARNINGS = frozenset(
    {
        "DEFERRED_CHANGES_PRESENT",
        "CHANGE_ACTIONS_UNREPORTED",
        "IMPORTS_NOT_SUMMARIZED",
        "OUTPUT_CHANGES_NOT_SUMMARIZED",
        "RESOURCE_DRIFT_NOT_ANALYZED",
    }
)


class AnalyzeTerraformPlanInput(ContractModel):
    """The analysis tool's single path argument; access checks belong to the loader."""

    plan_path: PlanPath = Field(
        repr=False, description="Local path within an allowed root."
    )


def validate_analysis_input(value: object) -> AnalyzeTerraformPlanInput:
    """Discard raw Pydantic errors, including rejected extra-field names."""
    try:
        return AnalyzeTerraformPlanInput.model_validate(value)
    except ValidationError:
        # Input hiding alone does not hide rejected field names or errors() data.
        raise AnalysisError(ErrorCode.INVALID_ARGUMENT) from None


class ResourceAnalysis(ContractModel):
    """Public identity, action, and provenance of one resource in the plan.

    Addresses are opaque strings; instance keys can themselves contain dots.
    Attribute values and mask metadata are deliberately absent from this shape.
    """

    # Identities appear in the intended JSON response, but not debug repr() output.
    address: IdentityText = Field(repr=False)
    resource_type: IdentityText = Field(repr=False)
    name: IdentityText = Field(repr=False)
    provider_name: IdentityText = Field(repr=False)
    mode: ResourceMode
    module_address: IdentityText | None = Field(default=None, repr=False)
    index: Count | InstanceKey | None = Field(default=None, repr=False)
    previous_address: IdentityText | None = Field(default=None, repr=False)
    actions: list[Action] = Field(max_length=2)
    action_category: ActionCategory
    source: ResourceSource

    @model_validator(mode="after")
    def consistent_actions(self) -> Self:
        """Ensure the action label and source agree with the ordered action list."""
        expected = ACTION_CATEGORIES.get(tuple(self.actions))
        if expected is None or self.action_category != expected:
            raise ValueError("Actions must match a supported action category.")
        # Missing change information is not evidence that a resource is unchanged.
        if (self.source == "planned_values") != (expected == "unreported"):
            raise ValueError("Only inventory-only resources have unreported actions.")
        return self


class AnalysisWarning(ContractModel):
    """A fixed coverage explanation with an affected-item count where relevant."""

    code: WarningCode
    message: str
    count: Count | None = None

    @model_validator(mode="after")
    def catalog_message_and_count(self) -> Self:
        """Reject supplied message text or counts that contradict the warning code."""
        if self.message != WARNING_MESSAGES[self.code]:
            raise ValueError("Warning messages must match the warning catalog.")
        if self.code in _COUNTED_WARNINGS:
            if self.count is None or self.count == 0:
                raise ValueError("This warning requires a positive count.")
        elif self.count is not None:
            raise ValueError("This warning does not carry a count.")
        return self


class KnownEncryption(ContractModel):
    """The only provider value retained for the first evaluation policy."""

    state: Literal["known"] = "known"
    value: bool = Field(repr=False)


class UncertainEncryption(ContractModel):
    """A value-free state: missing, masked and malformed are different facts."""

    state: Literal[
        "missing",
        "null",
        "unknown",
        "sensitive",
        "unverified",
        "invalid_type",
        "unavailable",
    ]


class DirectAssociation(ContractModel):
    """Direct encryption checks do not depend on another resource."""

    state: Literal["not_required"] = "not_required"


class ResolvedAssociation(ContractModel):
    """Retain a proved Terraform identity, never the raw AWS matching values."""

    state: Literal["resolved"] = "resolved"
    cluster_address: IdentityText = Field(repr=False)


class UnresolvedAssociation(ContractModel):
    """Uncertainty carries no target address and cannot silently become a link."""

    state: Literal[
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
        "missing",
        "null",
        "invalid_type",
        "context_unverified",
        "not_found",
        "ambiguous",
    ]


class DesiredStateProjection(ContractModel):
    """Minimal RDS-specific input; cluster identifiers and raw values are absent."""

    scope: Literal[
        "standalone",
        "cluster",
        "cluster_member",
        "cluster_associated",
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
        "invalid_type",
    ]
    encryption: Annotated[
        KnownEncryption | UncertainEncryption, Field(discriminator="state")
    ] = Field(repr=False)
    association: Annotated[
        DirectAssociation | ResolvedAssociation | UnresolvedAssociation,
        Field(discriminator="state"),
    ] = Field(default_factory=DirectAssociation, repr=False)

    @model_validator(mode="after")
    def association_scope(self) -> Self:
        """Members require relationship evidence and never use a computed copy."""
        if self.scope == "cluster_member":
            if (
                self.association.state == "not_required"
                or self.encryption.state != "unavailable"
            ):
                raise ValueError("Invalid member projection.")
        elif self.association.state != "not_required":
            raise ValueError("Unexpected association.")
        return self


class NormalizedResource(ContractModel):
    """Internal resource projection used by adapters and, later, policy evaluation.

    Mask paths record which values are unknown or sensitive without storing those
    values. Only the nested ResourceAnalysis belongs in the public response.
    """

    resource: ResourceAnalysis = Field(repr=False)
    unknown_paths: list[AttributePath] = Field(default_factory=list, repr=False)
    sensitive_paths: list[AttributePath] = Field(default_factory=list, repr=False)
    unknown_metadata_complete: bool
    desired_state: DesiredStateProjection | None = Field(default=None, repr=False)
    ssh_state: SSHProjection | None = Field(default=None, repr=False)
    tag_state: TagProjection | None = Field(default=None, repr=False)
    s3_state: S3Projection | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def inventory_uncertainty(self) -> Self:
        """Planned inventory alone cannot distinguish missing from unknown values."""
        if self.resource.source == "planned_values" and self.unknown_metadata_complete:
            raise ValueError("Inventory-only unknown metadata must remain incomplete.")
        return self


class ResourceSnapshot(ContractModel):
    """Adapter output before reporting: normalized resources and coverage warnings."""

    # Our contract version is separate from Terraform's input format version.
    schema_version: Literal["1"] = "1"
    source_kind: Literal["terraform_plan"] = "terraform_plan"
    format_version: FormatVersion
    terraform_version: IdentityText | None = Field(default=None, repr=False)
    resources: list[NormalizedResource] = Field(repr=False)
    warnings: list[AnalysisWarning]

    @model_validator(mode="after")
    def unique_addresses(self) -> Self:
        """Catch duplicate identities after the adapter merges its input sources."""
        addresses = [item.resource.address for item in self.resources]
        if len(set(addresses)) != len(addresses):
            raise ValueError("Normalized resource addresses must be unique.")
        return self


class ActionCounts(ContractModel):
    """Required action buckets, including zeros, so totals are predictable."""

    create: Count
    update: Count
    delete: Count
    replace: Count
    no_op: Count
    read: Count
    unreported: Count


class ModeCounts(ContractModel):
    """Separate managed infrastructure from data-source observations."""

    managed: Count
    data: Count


class AnalysisSummary(ContractModel):
    """Aggregate resource counts computed by the analysis summary builder."""

    total_resources: Count
    changing_resources: Count
    by_action: ActionCounts
    by_type: dict[IdentityText, Count] = Field(repr=False)
    by_mode: ModeCounts

    @model_validator(mode="after")
    def consistent_totals(self) -> Self:
        """Check arithmetic consistency without calculating a summary for callers."""
        # Each grouping partitions the same resource set, so all sums must agree.
        totals = (
            sum(self.by_action.model_dump().values()),
            sum(self.by_type.values()),
            self.by_mode.managed + self.by_mode.data,
        )
        if any(total != self.total_resources for total in totals):
            raise ValueError("Every count grouping must sum to total resources.")
        # Reads and no-ops do not change managed infrastructure. A replacement
        # occupies its own bucket rather than increasing create/delete totals.
        changing_actions = (
            self.by_action.create
            + self.by_action.update
            + self.by_action.delete
            + self.by_action.replace
        )
        if self.changing_resources > min(self.by_mode.managed, changing_actions):
            raise ValueError(
                "Changing resources cannot exceed managed changing actions."
            )
        return self


class PlanAnalysis(ContractModel):
    """Complete public analysis response, with no attributes or compliance claims."""

    schema_version: Literal["1"] = "1"
    format_version: FormatVersion
    terraform_version: IdentityText | None = Field(default=None, repr=False)
    analysis_status: Literal["complete", "partial"]
    summary: AnalysisSummary
    resources: list[ResourceAnalysis] = Field(repr=False)
    warnings: list[AnalysisWarning]

    @model_validator(mode="after")
    def consistent_report(self) -> Self:
        """Prevent a response from contradicting its own resources or coverage."""
        # Unique, ordered identities make output stable across source-list order.
        addresses = [resource.address for resource in self.resources]
        if addresses != sorted(set(addresses)):
            raise ValueError("Analysis resources must have unique, sorted addresses.")
        if len(addresses) != self.summary.total_resources:
            raise ValueError("Resource count must match the analysis summary.")
        # Arithmetic alone can look valid while assigning counts to wrong buckets.
        # Check the supplied aggregates against the actual resource records too.
        actual_actions = Counter(
            resource.action_category for resource in self.resources
        )
        actual_types = Counter(resource.resource_type for resource in self.resources)
        actual_modes = Counter(resource.mode for resource in self.resources)
        if (
            self.summary.by_action.model_dump()
            != {key: actual_actions[key] for key in ActionCounts.model_fields}
            or self.summary.by_type != dict(actual_types)
            or self.summary.by_mode.model_dump()
            != {key: actual_modes[key] for key in ModeCounts.model_fields}
        ):
            raise ValueError("Summary groupings must match the resource records.")
        # Only managed create/update/delete/replace actions count as changes.
        changing = sum(
            resource.mode == "managed"
            and resource.action_category in {"create", "update", "delete", "replace"}
            for resource in self.resources
        )
        if changing != self.summary.changing_resources:
            raise ValueError("Changing count must match managed changing resources.")
        # Coverage limitations require partial status and one warning per reason.
        codes = [warning.code for warning in self.warnings]
        if codes != sorted(set(codes)):
            raise ValueError("Analysis warnings must have unique, sorted codes.")
        if (self.analysis_status == "partial") != bool(self.warnings):
            raise ValueError("Partial analysis requires coverage warnings.")
        # Every resource without reported actions must be represented in coverage.
        unreported = actual_actions["unreported"]
        unreported_warning = next(
            (
                item
                for item in self.warnings
                if item.code == "CHANGE_ACTIONS_UNREPORTED"
            ),
            None,
        )
        if (unreported_warning.count if unreported_warning else 0) != unreported:
            raise ValueError("Unreported actions require a matching coverage warning.")
        # Stable map ordering keeps serialized JSON and human-facing output aligned.
        if list(self.summary.by_type) != sorted(self.summary.by_type):
            raise ValueError("Resource type counts must be sorted.")
        return self
