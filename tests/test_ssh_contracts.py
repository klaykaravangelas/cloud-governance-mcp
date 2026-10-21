"""Strict network observations cannot carry raw or invented provider values."""

import pytest
from pydantic import ValidationError

from cloud_governance_mcp.ssh_models import (
    KnownCIDR,
    KnownPorts,
    KnownProtocol,
    SSHProjection,
    SSHSources,
    UncertainSSH,
)


@pytest.mark.parametrize(
    "model,payload",
    [
        (KnownProtocol, {"number": True}),
        (KnownCIDR, {"family": 4.0, "prefix_length": 0}),
        (KnownProtocol, {"number": "6"}),
        (KnownProtocol, {"number": 256}),
        (KnownPorts, {"from_port": True, "to_port": 22}),
        (KnownPorts, {"from_port": 23, "to_port": 22}),
        (KnownPorts, {"from_port": -1, "to_port": 22}),
        (KnownPorts, {"from_port": 22, "to_port": 65536}),
        (KnownCIDR, {"family": 4, "prefix_length": 33}),
        (KnownCIDR, {"family": 6, "prefix_length": 129}),
        (KnownCIDR, {"family": 4, "prefix_length": 0, "cidr": "SENTINEL"}),
        (UncertainSSH, {"state": "unknown", "value": "SENTINEL"}),
    ],
)
def test_invalid_or_raw_payload_is_rejected(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "state",
    [
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
        "missing",
        "null",
        "invalid_type",
    ],
)
def test_uncertainty_carries_only_state(state):
    assert UncertainSSH(state=state).model_dump() == {"state": state}


def test_family_must_match_its_source_slot():
    absent = {"state": "absent"}
    with pytest.raises(ValidationError):
        SSHSources(
            ipv4={
                "state": "known",
                "items": [{"state": "known", "family": 6, "prefix_length": 64}],
            },
            ipv6=absent,
            prefix_lists=absent,
            security_groups=absent,
            self_reference=absent,
        )


@pytest.mark.parametrize(
    "representation,direction,items",
    [
        ("modern", {"state": "known", "value": "egress"}, [{"state": "unavailable"}]),
        ("inline", {"state": "unknown"}, []),
        ("legacy", {"state": "unknown"}, []),
        (
            "legacy",
            {"state": "known", "value": "ingress"},
            [{"state": "unknown"}, {"state": "unknown"}],
        ),
        ("legacy", {"state": "known", "value": "egress"}, [{"state": "unknown"}]),
    ],
)
def test_representation_direction_and_rule_counts_are_consistent(
    representation, direction, items
):
    with pytest.raises(ValidationError):
        SSHProjection(
            representation=representation,
            direction=direction,
            rules={"state": "known", "items": items},
        )


def test_empty_inline_and_excluded_standalone_are_explicit():
    inline = SSHProjection(
        representation="inline",
        direction={"state": "known", "value": "ingress"},
        rules={"state": "known", "items": []},
    )
    egress = SSHProjection(
        representation="legacy",
        direction={"state": "known", "value": "egress"},
        rules={"state": "known", "items": [{"state": "unavailable"}]},
    )
    assert inline.rules.items == []
    assert egress.rules.items[0].state == "unavailable"
