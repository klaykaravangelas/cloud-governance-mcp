"""Strict S3 observations; raw bucket/provider names never cross this boundary."""

from typing import Literal, Self

from pydantic import Field, model_validator

from cloud_governance_mcp.contracts import ContractModel

S3_TYPES = ("aws_s3_bucket", "aws_s3_bucket_public_access_block")
S3_FLAGS = (
    "block_public_acls",
    "ignore_public_acls",
    "block_public_policy",
    "restrict_public_buckets",
)
S3_UNCERTAIN = (
    "sensitive",
    "unknown",
    "unverified",
    "unavailable",
    "missing",
    "null",
    "invalid_type",
)
S3_LINK_STATES = (*S3_UNCERTAIN, "not_found", "ambiguous", "context_unverified")


class KnownS3Flag(ContractModel):
    """Only a strict boolean is retained from a known desired flag."""

    state: Literal["known"] = "known"
    value: bool


class UncertainS3Flag(ContractModel):
    """An uncertain flag never carries its withheld or invalid payload."""

    state: Literal[
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
        "missing",
        "null",
        "invalid_type",
    ]


type S3Flag = KnownS3Flag | UncertainS3Flag


class S3Block(ContractModel):
    """Exactly four flag observations, in the policy's fixed order."""

    representation: Literal["block"] = "block"
    flags: list[S3Flag] = Field(min_length=4, max_length=4, repr=False)


class S3Bucket(ContractModel):
    """A proved Terraform target address or a value-free unresolved association."""

    representation: Literal["bucket"] = "bucket"
    state: Literal[
        "resolved",
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
        "missing",
        "null",
        "invalid_type",
        "not_found",
        "ambiguous",
        "context_unverified",
    ]
    block_address: str | None = Field(
        default=None, min_length=1, max_length=2048, repr=False
    )

    @model_validator(mode="after")
    def target_only_when_resolved(self) -> Self:
        """Do not let uncertain links carry a guessed target identity."""
        if (self.state == "resolved") != (self.block_address is not None):
            raise ValueError("Invalid S3 target.")
        return self


type S3Projection = S3Block | S3Bucket
