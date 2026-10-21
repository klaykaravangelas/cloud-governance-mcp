"""Value-minimized SSH observations; real Rego owns all exposure decisions."""

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from cloud_governance_mcp.contracts import ContractModel

MAX_SSH_RULES = 10_000
MAX_SSH_SOURCE_ENTRIES = 50_000

type Uncertainty = Literal[
    "sensitive",
    "unknown",
    "unverified",
    "unavailable",
    "missing",
    "null",
    "invalid_type",
]
UNCERTAINTY_ORDER = (
    "sensitive",
    "unknown",
    "unverified",
    "unavailable",
    "missing",
    "null",
    "invalid_type",
)


class UncertainSSH(ContractModel):
    """No rejected, masked or absent provider value may accompany a state."""

    state: Uncertainty


class AbsentSource(ContractModel):
    """A complete, unmasked optional field was absent, null or empty."""

    state: Literal["absent"] = "absent"


class PresentSource(ContractModel):
    """A known reference exists; its contents are discarded before storage."""

    state: Literal["present"] = "present"


class KnownProtocol(ContractModel):
    """Canonical protocol number, not a Python port-22/exposure verdict."""

    state: Literal["known"] = "known"
    number: int = Field(ge=-1, le=255, repr=False)


class KnownPorts(ContractModel):
    """A syntactically valid strict TCP interval, without an SSH decision."""

    state: Literal["known"] = "known"
    from_port: int = Field(ge=0, le=65535, repr=False)
    to_port: int = Field(ge=0, le=65535, repr=False)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        """Reversed intervals cannot masquerade as a safe permission."""
        if self.from_port > self.to_port:
            raise ValueError("Invalid interval.")
        return self


class KnownCIDR(ContractModel):
    """Only address family and prefix length survive parsing, never an IP."""

    state: Literal["known"] = "known"
    family: Literal[4, 6]
    prefix_length: int = Field(ge=0, le=128, repr=False)

    @field_validator("family", mode="before")
    @classmethod
    def strict_family(cls, value: object) -> object:
        """Literal matching must not coerce numerically equal float values."""
        if type(value) is not int:
            raise ValueError("Invalid address family.")
        return value

    @model_validator(mode="after")
    def valid_prefix(self) -> Self:
        """Validate intrinsic family bounds without classifying world access."""
        if self.family == 4 and self.prefix_length > 32:
            raise ValueError("Invalid prefix.")
        return self


class KnownCIDRs(ContractModel):
    """A complete array, possibly with explicit uncertain element placeholders."""

    state: Literal["known"] = "known"
    items: list[Annotated[KnownCIDR | UncertainSSH, Field(discriminator="state")]] = (
        Field(repr=False)
    )


class KnownSelfReference(ContractModel):
    """A known boolean describing a self reference; no group identity."""

    state: Literal["known"] = "known"
    value: bool = Field(repr=False)


type CIDRObservation = Annotated[
    KnownCIDRs | AbsentSource | UncertainSSH, Field(discriminator="state")
]
type ReferenceObservation = Annotated[
    PresentSource | AbsentSource | UncertainSSH, Field(discriminator="state")
]


class SSHSources(ContractModel):
    """Independent additive sources with no raw CIDRs or reference IDs."""

    ipv4: CIDRObservation = Field(repr=False)
    ipv6: CIDRObservation = Field(repr=False)
    prefix_lists: ReferenceObservation = Field(repr=False)
    security_groups: ReferenceObservation = Field(repr=False)
    self_reference: Annotated[
        KnownSelfReference | AbsentSource | UncertainSSH, Field(discriminator="state")
    ] = Field(repr=False)

    @model_validator(mode="after")
    def matching_families(self) -> Self:
        """A valid IPv6 prefix cannot be injected into the IPv4 source slot."""
        for observation, family in ((self.ipv4, 4), (self.ipv6, 6)):
            if observation.state == "known" and any(
                item.state == "known" and item.family != family
                for item in observation.items
            ):
                raise ValueError("Invalid source family.")
        return self


class KnownSSHRule(ContractModel):
    """A usable rule with independent uncertain fields for Rego short-circuiting."""

    state: Literal["known"] = "known"
    protocol: Annotated[KnownProtocol | UncertainSSH, Field(discriminator="state")] = (
        Field(repr=False)
    )
    ports: Annotated[KnownPorts | UncertainSSH, Field(discriminator="state")] = Field(
        repr=False
    )
    sources: SSHSources = Field(repr=False)


class KnownSSHRules(ContractModel):
    """Inline arrays aggregate into one check; standalone arrays contain one rule."""

    state: Literal["known"] = "known"
    items: list[
        Annotated[KnownSSHRule | UncertainSSH, Field(discriminator="state")]
    ] = Field(repr=False)


class KnownDirection(ContractModel):
    """Ingress/egress is observed explicitly or fixed by representation."""

    state: Literal["known"] = "known"
    value: Literal["ingress", "egress"]


class SSHProjection(ContractModel):
    """Strict transport-independent network input with no raw provider payload."""

    representation: Literal["inline", "legacy", "modern"]
    direction: Annotated[KnownDirection | UncertainSSH, Field(discriminator="state")]
    rules: Annotated[KnownSSHRules | UncertainSSH, Field(discriminator="state")] = (
        Field(repr=False)
    )

    @model_validator(mode="after")
    def consistent_representation(self) -> Self:
        """Reject omitted standalone rules and impossible direction combinations."""
        if self.representation != "legacy" and (
            self.direction.state != "known" or self.direction.value != "ingress"
        ):
            raise ValueError("Invalid fixed direction.")
        if self.representation != "inline":
            if self.rules.state != "known" or len(self.rules.items) != 1:
                raise ValueError("Invalid standalone rule count.")
            if self.direction.state != "known" or self.direction.value == "egress":
                if self.rules.items[0].state != "unavailable":
                    raise ValueError("Excluded direction cannot retain values.")
        return self
