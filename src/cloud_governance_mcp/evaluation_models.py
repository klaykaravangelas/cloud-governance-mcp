"""Strict policy inputs, engine checks and public reports without MCP imports."""

from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from cloud_governance_mcp.evaluation_errors import (
    EVALUATION_MESSAGES,
    EvaluationCode,
    EvaluationFailure,
)
from cloud_governance_mcp.models import (
    ActionCategory,
    AnalysisWarning,
    AttributePath,
    ContractModel,
    Count,
    DesiredStateProjection,
    FormatVersion,
    IdentityText,
    PlanPath,
    ResourceMode,
)
from cloud_governance_mcp.policy_definitions import (
    AWS_PROVIDER,
    POLICY_IDS,
    RESOURCE_TYPES,
    SSH_TYPES,
    VERSIONS,
    validate_metadata,
    validate_severity,
)
from cloud_governance_mcp.s3_checks import validate_s3_graph
from cloud_governance_mcp.s3_models import S3Projection
from cloud_governance_mcp.ssh_models import (
    MAX_SSH_RULES,
    MAX_SSH_SOURCE_ENTRIES,
    SSHProjection,
)
from cloud_governance_mcp.tag_models import (
    MAX_TAG_KEY_SLOTS,
    TAG_TYPES,
    TagConfiguration,
    TagProjection,
)

type Outcome = Literal["pass", "fail", "indeterminate", "not_applicable"]
type PolicyID = Annotated[str, StringConstraints(min_length=1, max_length=64)]
type ReasonCode = Literal[
    "DATA_SOURCE_SKIPPED",
    "DELETED_RESOURCE_SKIPPED",
    "RESOURCE_NOT_SUPPORTED",
    "RDS_SCOPE_SENSITIVE",
    "RDS_SCOPE_UNKNOWN",
    "UNKNOWN_METADATA_INCOMPLETE",
    "DESIRED_STATE_UNAVAILABLE",
    "RDS_SCOPE_INVALID_TYPE",
    "RDS_CLUSTER_ASSOCIATION_UNSUPPORTED",
    "RDS_ENCRYPTION_SENSITIVE",
    "RDS_ENCRYPTION_UNKNOWN",
    "RDS_ENCRYPTION_MISSING",
    "RDS_ENCRYPTION_NULL",
    "RDS_ENCRYPTION_INVALID_TYPE",
    "RDS_ENCRYPTION_ENABLED",
    "RDS_ENCRYPTION_DISABLED",
    "RDS_CLUSTER_LINK_SENSITIVE",
    "RDS_CLUSTER_LINK_UNKNOWN",
    "RDS_CLUSTER_LINK_UNVERIFIED",
    "RDS_CLUSTER_LINK_UNAVAILABLE",
    "RDS_CLUSTER_LINK_MISSING",
    "RDS_CLUSTER_LINK_NULL",
    "RDS_CLUSTER_LINK_INVALID_TYPE",
    "RDS_CLUSTER_LINK_CONTEXT_UNVERIFIED",
    "RDS_CLUSTER_LINK_NOT_FOUND",
    "RDS_CLUSTER_LINK_AMBIGUOUS",
    "RDS_CLUSTER_ENCRYPTION_ENABLED",
    "RDS_CLUSTER_ENCRYPTION_DISABLED",
    "RDS_CLUSTER_ENCRYPTION_SENSITIVE",
    "RDS_CLUSTER_ENCRYPTION_UNKNOWN",
    "RDS_CLUSTER_ENCRYPTION_UNVERIFIED",
    "RDS_CLUSTER_ENCRYPTION_UNAVAILABLE",
    "RDS_CLUSTER_ENCRYPTION_MISSING",
    "RDS_CLUSTER_ENCRYPTION_NULL",
    "RDS_CLUSTER_ENCRYPTION_INVALID_TYPE",
    "SSH_INLINE_UNRESTRICTED_INGRESS",
    "SSH_INLINE_NO_UNRESTRICTED_INGRESS",
    "SSH_INLINE_SENSITIVE",
    "SSH_INLINE_UNKNOWN",
    "SSH_INLINE_UNVERIFIED",
    "SSH_INLINE_UNAVAILABLE",
    "SSH_INLINE_MISSING",
    "SSH_INLINE_NULL",
    "SSH_INLINE_INVALID_TYPE",
    "SSH_INLINE_PREFIX_LIST_UNRESOLVED",
    "SSH_RULE_UNRESTRICTED_INGRESS",
    "SSH_RULE_NO_UNRESTRICTED_INGRESS",
    "SSH_RULE_SENSITIVE",
    "SSH_RULE_UNKNOWN",
    "SSH_RULE_UNVERIFIED",
    "SSH_RULE_UNAVAILABLE",
    "SSH_RULE_MISSING",
    "SSH_RULE_NULL",
    "SSH_RULE_INVALID_TYPE",
    "SSH_RULE_PREFIX_LIST_UNRESOLVED",
    "SSH_EGRESS_SKIPPED",
    "TAG_SENSITIVE",
    "TAG_UNKNOWN",
    "TAG_UNVERIFIED",
    "TAG_UNAVAILABLE",
    "TAG_ALL_COMPLIANT",
    "TAG_ALL_KEY_MISSING",
    "TAG_ALL_KEY_EMPTY",
    "TAG_ALL_KEY_SENSITIVE",
    "TAG_ALL_KEY_UNKNOWN",
    "TAG_ALL_KEY_INVALID_TYPE",
    "TAG_ALL_MAP_NULL",
    "TAG_ALL_MAP_SENSITIVE",
    "TAG_ALL_MAP_UNKNOWN",
    "TAG_ALL_MAP_INVALID_TYPE",
    "TAG_RESOURCE_COMPLIANT",
    "TAG_RESOURCE_KEY_MISSING",
    "TAG_RESOURCE_KEY_EMPTY",
    "TAG_RESOURCE_KEY_SENSITIVE",
    "TAG_RESOURCE_KEY_UNKNOWN",
    "TAG_RESOURCE_KEY_INVALID_TYPE",
    "TAG_RESOURCE_MAP_NULL",
    "TAG_RESOURCE_MAP_SENSITIVE",
    "TAG_RESOURCE_MAP_UNKNOWN",
    "TAG_RESOURCE_MAP_INVALID_TYPE",
    "TAG_RESOURCE_MAP_MISSING",
    "S3_BLOCK_ENABLED",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_SENSITIVE",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_UNKNOWN",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_UNVERIFIED",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_UNAVAILABLE",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_MISSING",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_NULL",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_INVALID_TYPE",
    "S3_BLOCK_BLOCK_PUBLIC_ACLS_DISABLED",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_SENSITIVE",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_UNKNOWN",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_UNVERIFIED",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_UNAVAILABLE",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_MISSING",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_NULL",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_INVALID_TYPE",
    "S3_BLOCK_IGNORE_PUBLIC_ACLS_DISABLED",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_SENSITIVE",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_UNKNOWN",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_UNVERIFIED",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_UNAVAILABLE",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_MISSING",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_NULL",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_INVALID_TYPE",
    "S3_BLOCK_BLOCK_PUBLIC_POLICY_DISABLED",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_SENSITIVE",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_UNKNOWN",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_UNVERIFIED",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_UNAVAILABLE",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_MISSING",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_NULL",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_INVALID_TYPE",
    "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_DISABLED",
    "S3_BUCKET_ENABLED",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_SENSITIVE",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_UNKNOWN",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_UNVERIFIED",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_UNAVAILABLE",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_MISSING",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_NULL",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_INVALID_TYPE",
    "S3_BUCKET_BLOCK_PUBLIC_ACLS_DISABLED",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_SENSITIVE",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_UNKNOWN",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_UNVERIFIED",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_UNAVAILABLE",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_MISSING",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_NULL",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_INVALID_TYPE",
    "S3_BUCKET_IGNORE_PUBLIC_ACLS_DISABLED",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_SENSITIVE",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_UNKNOWN",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_UNVERIFIED",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_UNAVAILABLE",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_MISSING",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_NULL",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_INVALID_TYPE",
    "S3_BUCKET_BLOCK_PUBLIC_POLICY_DISABLED",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_SENSITIVE",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_UNKNOWN",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_UNVERIFIED",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_UNAVAILABLE",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_MISSING",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_NULL",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_INVALID_TYPE",
    "S3_BUCKET_RESTRICT_PUBLIC_BUCKETS_DISABLED",
    "S3_LINK_SENSITIVE",
    "S3_LINK_UNKNOWN",
    "S3_LINK_UNVERIFIED",
    "S3_LINK_UNAVAILABLE",
    "S3_LINK_MISSING",
    "S3_LINK_NULL",
    "S3_LINK_INVALID_TYPE",
    "S3_LINK_NOT_FOUND",
    "S3_LINK_AMBIGUOUS",
    "S3_LINK_CONTEXT_UNVERIFIED",
]


class EvaluateTerraformPoliciesInput(ContractModel):
    """Omission selects enabled policies; explicit null never means omission."""

    plan_path: PlanPath = Field(repr=False)
    policy_ids: list[PolicyID] = Field(
        default_factory=lambda: list(POLICY_IDS), min_length=1, max_length=4
    )

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        """Reject duplicates instead of silently changing the user's selection."""
        if len(self.policy_ids) != len(set(self.policy_ids)):
            raise ValueError("Duplicate selection.")
        self.policy_ids.sort()
        return self


def validate_evaluation_input(value: object) -> EvaluateTerraformPoliciesInput:
    """Replace input-bearing Pydantic errors, including extra field names."""
    try:
        return EvaluateTerraformPoliciesInput.model_validate(value)
    except ValidationError:
        # Classify only the documented selection field; never reflect locations.
        code = (
            EvaluationCode.INVALID_POLICY_SELECTION
            if isinstance(value, dict) and "policy_ids" in value
            else EvaluationCode.INVALID_ARGUMENT
        )
        raise EvaluationFailure(code) from None


class ReasonTemplate(ContractModel):
    """Trusted reason/outcome/path and safe prose shared by policy/reporting."""

    outcome: Outcome
    attribute_path: AttributePath
    explanation: IdentityText
    remediation: IdentityText


class PolicyMetadata(ContractModel):
    """One implemented policy's metadata; the catalog does not advertise plans."""

    policy_id: Literal["AWS-RDS-001", "AWS-S3-001", "AWS-SG-001", "AWS-TAG-001"]
    policy_version: Literal["1.1.0", "1.0.0"]
    title: IdentityText
    description: IdentityText
    severity: Literal["high", "medium"]
    enabled: Literal[True]
    supported_provider_names: list[IdentityText] = Field(min_length=1, max_length=1)
    supported_resource_types: list[IdentityText] = Field(min_length=2, max_length=5)
    required_paths: list[AttributePath]
    scope_description: IdentityText
    required_configuration: list[IdentityText] = Field(max_length=1)
    reasons: dict[ReasonCode, ReasonTemplate]

    @model_validator(mode="after")
    def implemented_metadata(self) -> Self:
        """Validate each ID's version and scope without reading assets."""
        validate_metadata(
            self.policy_id,
            self.policy_version,
            self.supported_provider_names,
            self.supported_resource_types,
            self.required_paths,
            self.required_configuration,
            self.severity,
        )
        return self


class PolicyScope(ContractModel):
    """Public, catalog-controlled limits on what a pass means."""

    policy_id: PolicyID
    policy_version: IdentityText
    severity: Literal["high", "medium"]
    supported_provider_names: list[IdentityText]
    supported_resource_types: list[IdentityText]
    scope_description: IdentityText

    @model_validator(mode="after")
    def policy_scope(self) -> Self:
        """Public scope remains exact per ID, including its severity and types."""
        validate_severity(self.policy_id, self.severity)
        if (
            self.policy_version != VERSIONS[self.policy_id]
            or self.supported_provider_names != [AWS_PROVIDER]
            or self.supported_resource_types != list(RESOURCE_TYPES[self.policy_id])
        ):
            raise ValueError("Invalid policy scope.")
        return self


class ProjectedResource(ContractModel):
    """Only the allowlisted fields cross the OPA process boundary."""

    address: IdentityText = Field(repr=False)
    provider_name: IdentityText = Field(repr=False)
    resource_type: IdentityText = Field(repr=False)
    mode: ResourceMode
    action_category: ActionCategory
    desired_state: DesiredStateProjection = Field(repr=False)
    ssh_state: SSHProjection | None = Field(default=None, repr=False)
    tag_state: TagProjection | None = Field(default=None, repr=False)
    s3_state: S3Projection | None = Field(default=None, repr=False)


class EvaluationInput(ContractModel):
    """Versioned, deterministic engine input; no raw Terraform envelope."""

    schema_version: Literal["5"] = "5"
    selected_policy_ids: list[PolicyID]
    tag_configuration: TagConfiguration | None = Field(default=None, repr=False)
    resources: list[ProjectedResource] = Field(repr=False)

    @field_validator("tag_configuration", mode="before")
    @classmethod
    def canonical_tag_input(cls, value: object) -> object:
        """Engine inputs must already be canonical; operator settings may sort."""
        keys = (
            value.get("required_tag_keys")
            if isinstance(value, dict)
            else getattr(value, "required_tag_keys", None)
        )
        if (
            isinstance(keys, list)
            and all(type(k) is str for k in keys)
            and keys != sorted(keys)
        ):
            raise ValueError("Unordered engine tag configuration.")
        return value

    @model_validator(mode="after")
    def valid_resource_graph(self) -> Self:
        """Only eligible same-batch clusters may be association targets.

        Addresses are opaque keys. Reject inconsistent graphs before OPA rather
        than allowing an undefined lookup to remove a required check.
        """
        if (
            self.selected_policy_ids != sorted(set(self.selected_policy_ids))
            or not self.selected_policy_ids
            or any(p not in POLICY_IDS for p in self.selected_policy_ids)
        ):
            raise ValueError("Invalid engine selection.")
        tag_selected = "AWS-TAG-001" in self.selected_policy_ids
        if tag_selected != (self.tag_configuration is not None):
            raise ValueError("Invalid tag configuration scope.")
        keys = self.tag_configuration.required_tag_keys if tag_selected else []
        tag_slots = 0
        by_address = {item.address: item for item in self.resources}
        if len(by_address) != len(self.resources):
            raise ValueError("Duplicate resource address.")
        validate_s3_graph(self.resources, self.selected_policy_ids)
        rule_slots, cidr_slots = 0, 0
        for item in self.resources:
            eligible = (
                item.mode == "managed"
                and item.action_category != "delete"
                and item.provider_name == "registry.terraform.io/hashicorp/aws"
            )
            tag_eligible = eligible and item.resource_type in TAG_TYPES and tag_selected
            if tag_eligible:
                tag_slots += len(keys)
                if tag_slots > MAX_TAG_KEY_SLOTS or item.tag_state is None:
                    raise ValueError("Invalid tag work or projection.")
                if (
                    item.tag_state.state == "known"
                    and [e.key for e in item.tag_state.entries] != keys
                ):
                    raise ValueError("Invalid configured tag entries.")
            elif item.tag_state is not None:
                raise ValueError("Unexpected tag projection.")
            scope = item.desired_state.scope
            expected_scope = {
                "aws_rds_cluster": "cluster",
                "aws_rds_cluster_instance": "cluster_member",
            }.get(item.resource_type)
            ssh_eligible = (
                eligible
                and item.resource_type in SSH_TYPES
                and "AWS-SG-001" in self.selected_policy_ids
            )
            if ssh_eligible:
                expected = dict(
                    zip(SSH_TYPES, ("inline", "legacy", "modern"), strict=True)
                )[item.resource_type]
                if item.ssh_state is None or item.ssh_state.representation != expected:
                    raise ValueError("Invalid SSH scope.")
                if item.ssh_state.rules.state == "known":
                    rule_slots += len(item.ssh_state.rules.items)
                    for rule in item.ssh_state.rules.items:
                        if rule.state == "known":
                            for source in (rule.sources.ipv4, rule.sources.ipv6):
                                if source.state == "known":
                                    cidr_slots += len(source.items)
                if rule_slots > MAX_SSH_RULES or cidr_slots > MAX_SSH_SOURCE_ENTRIES:
                    raise ValueError("Projected work exceeds limits.")
            elif item.ssh_state is not None:
                raise ValueError("Unexpected SSH projection.")
            rds_selected = "AWS-RDS-001" in self.selected_policy_ids
            if (
                not rds_selected
                or not eligible
                or item.resource_type not in RESOURCE_TYPES["AWS-RDS-001"]
            ):
                if (
                    scope != "unavailable"
                    or item.desired_state.encryption.state != "unavailable"
                    or item.desired_state.association.state != "not_required"
                ):
                    raise ValueError("Unexpected RDS projection.")
            if rds_selected and eligible and expected_scope is not None:
                if scope != expected_scope:
                    raise ValueError("Invalid resource scope.")
            elif scope in {"cluster", "cluster_member"}:
                raise ValueError("Invalid resource scope.")
            association = item.desired_state.association
            if association.state != "resolved":
                continue
            target = by_address.get(association.cluster_address)
            if (
                target is None
                or target.address == item.address
                or target.mode != "managed"
                or target.action_category == "delete"
                or target.provider_name != "registry.terraform.io/hashicorp/aws"
                or target.resource_type != "aws_rds_cluster"
                or target.desired_state.scope != "cluster"
            ):
                raise ValueError("Invalid cluster target.")
        return self


class CheckResult(ContractModel):
    """Rego output contains controlled codes, never arbitrary explanation text."""

    policy_id: PolicyID
    resource_address: IdentityText = Field(repr=False)
    outcome: Outcome
    reason_code: ReasonCode
    attribute_path: AttributePath


class EngineReport(ContractModel):
    """The one defined Rego entrypoint result, before public reporting."""

    schema_version: Literal["1"] = "1"
    checks: list[CheckResult] = Field(repr=False)


class Finding(ContractModel):
    """Safe identity and catalog prose; no value/evidence dictionary is allowed."""

    policy_id: PolicyID
    severity: Literal["high", "medium"]
    resource_address: IdentityText = Field(repr=False)
    resource_type: IdentityText = Field(repr=False)
    reason_code: ReasonCode
    attribute_path: AttributePath
    explanation: IdentityText
    remediation: IdentityText

    @model_validator(mode="after")
    def policy_severity(self) -> Self:
        """Do not accept another policy's otherwise valid severity on findings."""
        validate_severity(self.policy_id, self.severity)
        if self.resource_type not in RESOURCE_TYPES[self.policy_id]:
            raise ValueError("Invalid finding resource type.")
        return self


class EvaluationError(ContractModel):
    """Public execution error with an immutable message and optional policy ID."""

    code: str
    message: str
    policy_id: PolicyID | None = None

    @model_validator(mode="after")
    def fixed_message(self) -> Self:
        """An error cannot smuggle raw subprocess output through its message."""
        if (
            self.code not in EVALUATION_MESSAGES
            or self.message != EVALUATION_MESSAGES[self.code]
        ):
            raise ValueError("Unknown error message.")
        return self


class EvaluationSummary(ContractModel):
    """Disjoint resource buckets and exhaustive check accounting."""

    resources_observed: Count
    candidate_resources: Count
    skipped_data: Count
    skipped_deleted: Count
    unsupported_resources: Count
    expected_checks: Count
    evaluated_checks: Count
    unevaluated_checks: Count
    applicable_checks: Count
    passed: Count
    failed: Count
    indeterminate: Count
    not_applicable: Count

    @model_validator(mode="after")
    def partitions(self) -> Self:
        """Zero findings or missing checks cannot accidentally represent a pass."""
        if self.resources_observed != (
            self.candidate_resources
            + self.skipped_data
            + self.skipped_deleted
            + self.unsupported_resources
        ):
            raise ValueError("Invalid resource partition.")
        if self.applicable_checks != self.passed + self.failed + self.indeterminate:
            raise ValueError("Invalid applicable count.")
        if self.evaluated_checks != self.applicable_checks + self.not_applicable:
            raise ValueError("Invalid evaluated count.")
        if self.expected_checks != self.evaluated_checks + self.unevaluated_checks:
            raise ValueError("Invalid expected count.")
        return self


def compliance_status(
    summary: EvaluationSummary, *, errors: bool, warnings: bool
) -> Outcome:
    """Verified violations win; uncertainty and missing coverage always block pass."""
    if summary.failed:
        return "fail"
    if errors or summary.indeterminate or warnings:
        return "indeterminate"
    if summary.applicable_checks:
        return "pass"
    return "not_applicable"


class EvaluationReport(ContractModel):
    """Public compliance result, distinct from whether evaluation executed."""

    schema_version: Literal["1"] = "1"
    format_version: FormatVersion
    terraform_version: IdentityText | None = None
    evaluation_status: Literal["complete", "partial", "failed"]
    compliance_status: Outcome
    selected_policy_ids: list[PolicyID] = Field(min_length=1)
    policy_scope: list[PolicyScope]
    findings: list[Finding] = Field(repr=False)
    indeterminate_checks: list[Finding] = Field(repr=False)
    errors: list[EvaluationError]
    warnings: list[AnalysisWarning]
    summary: EvaluationSummary

    @model_validator(mode="after")
    def consistent_report(self) -> Self:
        """Enforce atomic failures, status precedence and full public accounting."""
        s = self.summary
        if self.selected_policy_ids != sorted(set(self.selected_policy_ids)):
            raise ValueError("Invalid selection order.")
        if [p.policy_id for p in self.policy_scope] != self.selected_policy_ids:
            raise ValueError("Scope differs from selection.")
        if s.expected_checks != s.resources_observed * len(self.selected_policy_ids):
            raise ValueError("Invalid check scope.")
        if s.failed != len(self.findings) or s.indeterminate != len(
            self.indeterminate_checks
        ):
            raise ValueError("Invalid finding counts.")
        if self.errors:
            if (
                self.evaluation_status != "failed"
                or s.evaluated_checks != 0
                or self.findings
                or self.indeterminate_checks
            ):
                raise ValueError("Engine failure must discard all checks.")
        elif s.unevaluated_checks or self.evaluation_status != (
            "partial" if self.warnings else "complete"
        ):
            raise ValueError("Invalid evaluation coverage.")
        expected = compliance_status(
            s, errors=bool(self.errors), warnings=bool(self.warnings)
        )
        if self.compliance_status != expected:
            raise ValueError("Invalid compliance status.")
        for items in (self.findings, self.indeterminate_checks):
            keys = [(i.policy_id, i.resource_address) for i in items]
            if keys != sorted(set(keys)) or any(
                i.policy_id not in self.selected_policy_ids for i in items
            ):
                raise ValueError("Invalid finding membership/order.")
        return self
