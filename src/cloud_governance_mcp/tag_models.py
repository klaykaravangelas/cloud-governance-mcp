"""Strict tag configuration and value-free observations, without transport or I/O."""

import re
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from cloud_governance_mcp.contracts import ContractModel

DEFAULT_TAG_KEYS = ("Environment", "Owner", "Project")
MAX_TAG_KEY_SLOTS = 50_000
TAG_TYPES = (
    "aws_instance",
    "aws_security_group",
    "aws_db_instance",
    "aws_rds_cluster",
    "aws_s3_bucket",
)


def _valid_key(key: str) -> str:
    """Restrict operator names, including reserved prefixes and final newlines."""
    if re.fullmatch(r"[A-Za-z0-9_./:=+@-]+", key) is None or key.lower().startswith(
        "aws:"
    ):
        raise ValueError("Invalid required tag key.")
    return key


type TagKey = Annotated[
    str, StringConstraints(min_length=1, max_length=128), AfterValidator(_valid_key)
]
type TagKeys = Annotated[list[TagKey], Field(min_length=1, max_length=50)]


class TagConfiguration(ContractModel):
    """Validate operator keys without accepting arbitrary plan-derived names."""

    required_tag_keys: TagKeys = Field(repr=False)

    @model_validator(mode="after")
    def canonical_keys(self) -> Self:
        """Reject invalid/duplicate keys; preserve case and canonicalize order."""
        keys = self.required_tag_keys
        if len(set(keys)) != len(keys):
            raise ValueError("Invalid required tag keys.")
        self.required_tag_keys = sorted(keys)
        return self


class TagEntry(ContractModel):
    """Only a configured key and its knowledge/content class may survive."""

    key: TagKey = Field(repr=False)
    state: Literal[
        "nonempty", "blank", "missing", "null", "invalid_type", "sensitive", "unknown"
    ]


class UnresolvedTags(ContractModel):
    """No map source can safely be chosen from the desired resource."""

    source: Literal["unresolved"] = "unresolved"
    state: Literal["sensitive", "unknown", "unverified", "unavailable"]


class UncertainTagMap(ContractModel):
    """A selected map is withheld, absent, null or malformed; no payload allowed."""

    source: Literal["tags_all", "tags"]
    state: Literal["sensitive", "unknown", "missing", "null", "invalid_type"]

    @model_validator(mode="after")
    def missing_falls_back(self) -> Self:
        """Known absence of tags_all must choose the resource-only tags source."""
        if self.source == "tags_all" and self.state == "missing":
            raise ValueError("Invalid absent tag source.")
        return self


class KnownTagMap(ContractModel):
    """A bounded ordered observation for each configured key, with no values."""

    source: Literal["tags_all", "tags"]
    state: Literal["known"] = "known"
    entries: list[TagEntry] = Field(min_length=1, max_length=50, repr=False)

    @model_validator(mode="after")
    def ordered_unique_keys(self) -> Self:
        """Validate standalone maps; the engine graph also checks exact config."""
        keys = [entry.key for entry in self.entries]
        configuration = TagConfiguration(required_tag_keys=keys)
        if keys != configuration.required_tag_keys:
            raise ValueError("Unordered tag entries.")
        return self


type TagProjection = UnresolvedTags | UncertainTagMap | KnownTagMap
