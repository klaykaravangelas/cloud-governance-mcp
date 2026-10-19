"""Strict public policy metadata and empty input contracts, without MCP imports."""

from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from cloud_governance_mcp.listing_errors import ListingCode, ListingFailure
from cloud_governance_mcp.models import AttributePath, ContractModel, IdentityText


class ListPoliciesInput(ContractModel):
    """Listing accepts no filters, paths, executable choices or configuration."""


def validate_listing_input(value: object) -> ListPoliciesInput:
    """Normalize SDK no-arguments input and hide rejected keys as well as values."""
    try:
        return ListPoliciesInput.model_validate({} if value is None else value)
    except ValidationError:
        raise ListingFailure(ListingCode.INVALID_ARGUMENT) from None


class ListedPolicy(ContractModel):
    """Public allowlist of metadata; reason templates and local settings stay out."""

    policy_id: Literal["AWS-RDS-001"]
    policy_version: Literal["1.0.0"]
    title: IdentityText
    description: IdentityText
    severity: Literal["high"]
    supported_provider_names: list[IdentityText] = Field(min_length=1, max_length=1)
    supported_resource_types: list[IdentityText] = Field(min_length=1, max_length=1)
    required_paths: list[AttributePath]
    scope_description: IdentityText
    required_configuration: list[IdentityText] = Field(max_length=0)


class PolicyList(ContractModel):
    """Versioned deterministic listing of the currently implemented policy set."""

    schema_version: Literal["1"] = "1"
    policies: list[ListedPolicy] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def ordered_unique_policies(self) -> Self:
        """Reject duplicates or unstable order rather than silently fixing output."""
        ids = [policy.policy_id for policy in self.policies]
        if ids != sorted(set(ids)):
            raise ValueError("Invalid policy ordering.")
        return self
