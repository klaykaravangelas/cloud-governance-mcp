"""Load the one trusted catalog lazily; share metadata across execution/reporting."""

from importlib.resources import files
from typing import Literal, Self, get_args

from pydantic import Field, ValidationError, model_validator

from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import PolicyMetadata, ReasonCode
from cloud_governance_mcp.json_codec import decode_object
from cloud_governance_mcp.models import ContractModel
from cloud_governance_mcp.policy_definitions import (
    COMMON_REASONS,
    POLICY_IDS,
    S3_REASON_SPECS,
    TAG_REASON_SPECS,
)


class PolicyCatalog(ContractModel):
    """Validate scope and completeness, not just syntactically valid JSON."""

    schema_version: Literal["1"]
    policies: list[PolicyMetadata] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def implemented_scope(self) -> Self:
        """Prevent an edited catalog from advertising unimplemented coverage."""
        if [p.policy_id for p in self.policies] != list(POLICY_IDS):
            raise ValueError("Incomplete policy catalog.")
        codes = set(get_args(ReasonCode.__value__))
        for policy in self.policies:
            expected = {
                code
                for code in codes
                if (
                    code.startswith("SSH_")
                    if policy.policy_id == "AWS-SG-001"
                    else code.startswith("TAG_")
                    if policy.policy_id == "AWS-TAG-001"
                    else code.startswith("S3_")
                    if policy.policy_id == "AWS-S3-001"
                    else not code.startswith(("SSH_", "TAG_", "S3_"))
                )
            }
            expected |= COMMON_REASONS
            if set(policy.reasons) != expected:
                raise ValueError("Incomplete reason catalog.")
            for code, reason in policy.reasons.items():
                outcome = (
                    "not_applicable"
                    if code in COMMON_REASONS or code == "SSH_EGRESS_SKIPPED"
                    else "pass"
                    if code.endswith("_ENABLED")
                    or code.endswith("_NO_UNRESTRICTED_INGRESS")
                    else "fail"
                    if code.endswith("_DISABLED")
                    or code.endswith("_UNRESTRICTED_INGRESS")
                    else "indeterminate"
                )
                path = (
                    ["ingress"]
                    if code.startswith("SSH_INLINE_")
                    else ["type"]
                    if code == "SSH_EGRESS_SKIPPED"
                    else ["cluster_identifier"]
                    if code.startswith(("RDS_SCOPE_", "RDS_CLUSTER_"))
                    else ["storage_encrypted"]
                    if code.startswith("RDS_ENCRYPTION_")
                    else []
                )
                if code in S3_REASON_SPECS:
                    outcome, path = S3_REASON_SPECS[code]
                if code in TAG_REASON_SPECS:
                    outcome, path = TAG_REASON_SPECS[code]
                if reason.outcome != outcome or reason.attribute_path != path:
                    raise ValueError("Invalid reason semantics.")
        return self

    def select(self, ids: list[str]) -> list[PolicyMetadata]:
        """Resolve exact IDs without accepting client-controlled policy content."""
        enabled = {p.policy_id: p for p in self.policies if p.enabled}
        if (
            not ids
            or len(ids) > len(enabled)
            or len(set(ids)) != len(ids)
            or any(i not in enabled for i in ids)
        ):
            raise EvaluationFailure(EvaluationCode.INVALID_POLICY_SELECTION)
        return [enabled[i] for i in sorted(ids)]


def load_catalog() -> PolicyCatalog:
    """Read package assets for evaluation or listing, never on import."""
    try:
        payload = (
            files("cloud_governance_mcp.policies").joinpath("catalog.json").read_bytes()
        )
        if len(payload) > 65_536:
            raise ValueError("Catalog exceeds limit.")
        document = decode_object(payload)
        if set(document) != {"cloud_governance_catalog"}:
            raise ValueError("Invalid catalog namespace.")
        return PolicyCatalog.model_validate(document["cloud_governance_catalog"])
    except OSError, ValueError, ValidationError:
        raise EvaluationFailure(EvaluationCode.POLICY_ASSETS_INVALID) from None
