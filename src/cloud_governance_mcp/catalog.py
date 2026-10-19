"""Load the one trusted catalog lazily; share metadata across execution/reporting."""

from importlib.resources import files
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import PolicyMetadata
from cloud_governance_mcp.json_codec import decode_object
from cloud_governance_mcp.models import ContractModel
from cloud_governance_mcp.projection import AWS_PROVIDER


class PolicyCatalog(ContractModel):
    """Validate scope and completeness, not just syntactically valid JSON."""

    schema_version: Literal["1"]
    policies: list[PolicyMetadata] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def implemented_scope(self) -> Self:
        """Prevent an edited catalog from advertising unimplemented coverage."""
        policy = self.policies[0]
        if (
            policy.supported_provider_names != [AWS_PROVIDER]
            or policy.supported_resource_types != ["aws_db_instance"]
            or policy.required_paths != [["storage_encrypted"], ["cluster_identifier"]]
        ):
            raise ValueError("Unsupported policy scope.")
        if len(policy.reasons) != 16:
            raise ValueError("Incomplete reason catalog.")
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
