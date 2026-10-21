"""Parse masked network observations without retaining source addresses/IDs.

This pure adapter component knows field syntax and intrinsic numeric bounds.
Port-22 inclusion, world-prefix decisions and compliance belong exclusively to
Rego. All transient desired objects and mask indexes die with this invocation.
"""

import ipaddress
import re
from dataclasses import dataclass, field

from pydantic import TypeAdapter, ValidationError

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import IdentityText, NormalizedResource
from cloud_governance_mcp.policy_definitions import AWS_PROVIDER
from cloud_governance_mcp.policy_definitions import SSH_TYPES as SSH_TYPES
from cloud_governance_mcp.ssh_models import MAX_SSH_RULES as MAX_SSH_RULES
from cloud_governance_mcp.ssh_models import (
    MAX_SSH_SOURCE_ENTRIES as MAX_SSH_SOURCE_ENTRIES,
)
from cloud_governance_mcp.ssh_models import (
    UNCERTAINTY_ORDER,
    AbsentSource,
    CIDRObservation,
    KnownCIDR,
    KnownCIDRs,
    KnownDirection,
    KnownPorts,
    KnownProtocol,
    KnownSelfReference,
    KnownSSHRule,
    KnownSSHRules,
    PresentSource,
    ReferenceObservation,
    SSHProjection,
    SSHSources,
    UncertainSSH,
)

_TEXT = TypeAdapter(IdentityText)
_MISSING = object()
type MaskPath = tuple[str | int, ...]

_CONSUMED = {
    "protocol",
    "from_port",
    "to_port",
    "cidr_blocks",
    "ipv6_cidr_blocks",
    "prefix_list_ids",
    "security_groups",
    "self",
}


@dataclass(repr=False)
class _Mask:
    """A typed trie avoids rescanning every mask for every rule/field."""

    masked: bool = False
    children: dict[str | int, _Mask] = field(default_factory=dict)

    @classmethod
    def build(cls, paths: list[list[str | int]]) -> _Mask:
        root = cls()
        for path in paths:
            node = root
            for component in path:
                node = node.children.setdefault(component, cls())
            node.masked = True
        return root

    def at(self, path: tuple[str | int, ...]) -> _Mask:
        node = self
        for component in path:
            if node.masked:
                return node
            node = node.children.get(component, _EMPTY_MASK)
        return node


_EMPTY_MASK = _Mask()


@dataclass(repr=False)
class _Budget:
    """Bound total projected work before allocating payload-sized collections."""

    rules: int = 0
    sources: int = 0

    def reserve(self, kind: str, count: int) -> None:
        current = getattr(self, kind) + count
        limit = MAX_SSH_RULES if kind == "rules" else MAX_SSH_SOURCE_ENTRIES
        if current > limit:
            raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
        setattr(self, kind, current)


class _View:
    """Short-lived mask-aware access to a single authoritative desired object."""

    def __init__(
        self,
        resource: NormalizedResource,
        desired: dict[str, object] | None,
        budget: _Budget,
    ) -> None:
        self.desired = desired
        self.complete = resource.unknown_metadata_complete
        self.sensitive = _Mask.build(resource.sensitive_paths)
        self.unknown = _Mask.build(resource.unknown_paths)
        self.budget = budget

    def value(self, path: MaskPath) -> object:
        value = self.desired
        for component in path:
            if isinstance(value, dict) and isinstance(component, str):
                value = value.get(component, _MISSING)
            elif (
                isinstance(value, list)
                and type(component) is int
                and 0 <= component < len(value)
            ):
                value = value[component]
            else:
                return _MISSING
        return value

    def state(self, path: tuple[str | int, ...], *, descendants: bool = True) -> str:
        """Classify before accessing values; containers can inspect their children."""
        for root, state in ((self.sensitive, "sensitive"), (self.unknown, "unknown")):
            node = root.at(path)
            if node.masked or (descendants and node.children):
                return state
        if not self.complete:
            return "unverified"
        if self.desired is None:
            return "unavailable"
        value = self.value(path)
        return "missing" if value is _MISSING else "null" if value is None else "known"

    def array_state(
        self, path: tuple[str | int, ...], *, sensitive_descendants: bool = True
    ) -> str:
        """Withhold sensitive sets; never silently truncate unknown list tails."""
        if self.sensitive.at(path).masked or (
            sensitive_descendants and self.sensitive.at(path).children
        ):
            return "sensitive"
        state = self.state(path, descendants=False)
        unknown = self.unknown.at(path)
        if state != "known":
            return (
                "unknown"
                if unknown.children and state in {"missing", "null"}
                else state
            )
        values = self.value(path)
        if not isinstance(values, list):
            return "unknown" if unknown.children else "invalid_type"
        # Out-of-bounds/non-index masks make correspondence unprovable. Withhold
        # the collection instead of inventing holes or shifting known elements.
        if any(
            type(key) is not int or key < 0 or key >= len(values)
            for key in unknown.children
        ):
            return "unknown"
        return "known"


def _uncertain(states: list[str]) -> str | None:
    """Choose a fixed uncertainty priority, independently of field iteration."""
    return next((state for state in UNCERTAINTY_ORDER if state in states), None)


def _protocol(
    view: _View, path: MaskPath, legacy: bool
) -> KnownProtocol | UncertainSSH:
    """Canonicalize only documented aliases and strict decimal protocol strings."""
    state = view.state(path)
    if state != "known":
        return UncertainSSH(state=state)
    value = view.value(path)
    aliases = {"tcp": 6, "udp": 17, "icmp": 1, "icmpv6": 58, "-1": -1}
    if legacy:
        aliases["all"] = -1
    if type(value) is str:
        if value in aliases:
            return KnownProtocol(number=aliases[value])
        if re.fullmatch(r"0|[1-9][0-9]{0,2}", value) and int(value) <= 255:
            return KnownProtocol(number=int(value))
    return UncertainSSH(state="invalid_type")


def _ports(view: _View, base: MaskPath) -> KnownPorts | UncertainSSH:
    """Validate intervals without testing whether port 22 is contained."""
    values, states = [], []
    for key in ("from_port", "to_port"):
        path = (*base, key)
        state = view.state(path)
        value = view.value(path) if state == "known" else None
        if state == "known" and (type(value) is not int or not 0 <= value <= 65535):
            state = "invalid_type"
        values.append(value)
        states.append(state)
    if state := _uncertain(states):
        return UncertainSSH(state=state)
    if values[0] > values[1]:
        return UncertainSSH(state="invalid_type")
    return KnownPorts(from_port=values[0], to_port=values[1])


def _cidr(view: _View, path: MaskPath, family: int) -> KnownCIDR | UncertainSSH:
    """Discard network addresses after intrinsic syntax/family validation."""
    state = view.state(path)
    if state != "known":
        return UncertainSSH(state=state)
    raw = view.value(path)
    if (
        type(raw) is str
        and len(raw) <= 2048
        and raw.count("/") == 1
        and "%" not in raw
        and not any(c.isspace() for c in raw)
    ):
        suffix = raw.rsplit("/", 1)[1]
        if re.fullmatch(r"[0-9]{1,3}", suffix):
            try:
                parsed = ipaddress.ip_network(raw, strict=False)
                if parsed.version == family:
                    return KnownCIDR(family=family, prefix_length=parsed.prefixlen)
            except ValueError:
                pass  # Rejected text must never appear in logs or exceptions.
    return UncertainSSH(state="invalid_type")


def _cidrs(view: _View, path: MaskPath, family: int, scalar: bool) -> CIDRObservation:
    """Preserve unknown entries, withhold sensitive sets and normalize scalars."""
    if scalar:
        view.budget.reserve("sources", 1)
        state = view.state(path)
        if state in {"missing", "null"} or (
            state == "known" and view.value(path) == ""
        ):
            return AbsentSource()
        return (
            KnownCIDRs(items=[_cidr(view, path, family)])
            if state == "known"
            else UncertainSSH(state=state)
        )
    state = view.array_state(path)
    if state in {"missing", "null"}:
        return AbsentSource()
    if state != "known":
        return UncertainSSH(state=state)
    values = view.value(path)
    view.budget.reserve("sources", len(values))
    return KnownCIDRs(
        items=[_cidr(view, (*path, index), family) for index in range(len(values))]
    )


def _reference(view: _View, path: MaskPath, scalar: bool) -> ReferenceObservation:
    """Retain presence only after validating every unmasked reference string."""
    state = view.state(path)
    if state in {"missing", "null"}:
        return AbsentSource()
    if state != "known":
        return UncertainSSH(state=state)
    raw = view.value(path)
    if scalar and raw == "":
        return AbsentSource()
    values = [raw] if scalar else raw
    if not isinstance(values, list):
        return UncertainSSH(state="invalid_type")
    view.budget.reserve("sources", len(values))
    if not values:
        return AbsentSource()
    try:
        for value in values:
            _TEXT.validate_python(value, strict=True)
    except ValidationError:
        return UncertainSSH(state="invalid_type")
    return PresentSource()


def _self_reference(
    view: _View, path: MaskPath
) -> KnownSelfReference | AbsentSource | UncertainSSH:
    """Treat optional absence separately from a known false self-reference."""
    view.budget.reserve("sources", 1)
    state = view.state(path)
    if state in {"missing", "null"}:
        return AbsentSource()
    if state != "known":
        return UncertainSSH(state=state)
    value = view.value(path)
    return (
        KnownSelfReference(value=value)
        if type(value) is bool
        else UncertainSSH(state="invalid_type")
    )


def _rule(
    view: _View, base: MaskPath, representation: str
) -> KnownSSHRule | UncertainSSH:
    """Read only the fields consumed by this rule representation."""
    state = view.state(base, descendants=False)
    if state != "known":
        return UncertainSSH(state=state)
    if not isinstance(view.value(base), dict):
        return UncertainSSH(state="invalid_type")
    modern = representation == "modern"
    return KnownSSHRule(
        protocol=_protocol(
            view,
            (*base, "ip_protocol" if modern else "protocol"),
            representation == "legacy",
        ),
        ports=_ports(view, base),
        sources=SSHSources(
            ipv4=_cidrs(
                view, (*base, "cidr_ipv4" if modern else "cidr_blocks"), 4, modern
            ),
            ipv6=_cidrs(
                view, (*base, "cidr_ipv6" if modern else "ipv6_cidr_blocks"), 6, modern
            ),
            prefix_lists=_reference(
                view, (*base, "prefix_list_id" if modern else "prefix_list_ids"), modern
            ),
            security_groups=_reference(
                view,
                (
                    *base,
                    "referenced_security_group_id"
                    if modern
                    else "source_security_group_id"
                    if representation == "legacy"
                    else "security_groups",
                ),
                representation != "inline",
            ),
            self_reference=AbsentSource()
            if modern
            else _self_reference(view, (*base, "self")),
        ),
    )


def project_ssh_resources(
    resources: list[NormalizedResource],
    desired_by_address: dict[str, dict[str, object] | None],
) -> dict[str, SSHProjection]:
    """Build a bounded observation map; caller attaches it only for selected SSH."""
    budget, result = _Budget(), {}
    for resource in resources:
        identity = resource.resource
        if (
            identity.provider_name != AWS_PROVIDER
            or identity.mode != "managed"
            or identity.action_category == "delete"
            or identity.resource_type not in SSH_TYPES
        ):
            continue
        representation = dict(
            zip(SSH_TYPES, ("inline", "legacy", "modern"), strict=True)
        )[identity.resource_type]
        view = _View(resource, desired_by_address.get(identity.address), budget)
        direction = KnownDirection(value="ingress")
        if representation == "inline":
            promoted = any(
                not path
                or (path[0] == "ingress" and (len(path) <= 2 or path[2] in _CONSUMED))
                for path in resource.sensitive_paths
            )
            # Only consumed sensitive paths promote the inline collection; a
            # description-only mask must not prevent evaluating rule fields.
            state = (
                "sensitive"
                if promoted
                else view.array_state(("ingress",), sensitive_descendants=False)
            )
            if state == "known":
                size = len(view.value(("ingress",)))
                budget.reserve("rules", size)
                rules = KnownSSHRules(
                    items=[
                        _rule(view, ("ingress", index), representation)
                        for index in range(size)
                    ]
                )
            else:
                rules = UncertainSSH(state=state)
        else:
            budget.reserve("rules", 1)
            if representation == "legacy":
                state = view.state(("type",))
                value = view.value(("type",)) if state == "known" else None
                direction = (
                    KnownDirection(value=value)
                    if state == "known"
                    and type(value) is str
                    and value in {"ingress", "egress"}
                    else UncertainSSH(
                        state=state if state != "known" else "invalid_type"
                    )
                )
            excluded = direction.state != "known" or direction.value == "egress"
            rules = KnownSSHRules(
                items=[
                    UncertainSSH(state="unavailable")
                    if excluded
                    else _rule(view, (), representation)
                ]
            )
        result[identity.address] = SSHProjection(
            representation=representation, direction=direction, rules=rules
        )
    return result
