"""Pure masked parsing, source precedence and bounds; no OPA/AWS prerequisite."""

from copy import deepcopy

import pytest

import cloud_governance_mcp.ssh_projection as module
from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.errors import AnalysisError
from cloud_governance_mcp.ssh_projection import project_ssh_resources


def project(plan):
    """Use real source merging/masks while isolating the optional SSH parser."""
    snapshot = TerraformPlanAdapter().normalize(plan)
    desired = {
        entry["address"]: entry["change"].get("after")
        for entry in plan["resource_changes"]
    }
    return project_ssh_resources(snapshot.resources, desired)[
        snapshot.resources[0].resource.address
    ]


@pytest.mark.parametrize("representation", ["inline", "legacy", "modern"])
def test_three_formats_preserve_only_numeric_observations(ssh_plan, representation):
    plan = ssh_plan(representation)
    original = deepcopy(plan)
    projection = project(plan)
    rule = projection.rules.items[0]
    assert projection.representation == representation
    assert rule.protocol.number == 6
    assert rule.ports.from_port == rule.ports.to_port == 22
    assert rule.sources.ipv4.items[0].prefix_length == 0
    assert "0.0.0.0" not in projection.model_dump_json() + repr(projection)
    assert plan == original
    assert summarize(TerraformPlanAdapter().normalize(plan)).resources[0].address


@pytest.mark.parametrize(
    "value,state,number",
    [
        ("tcp", "known", 6),
        ("6", "known", 6),
        ("udp", "known", 17),
        ("icmpv6", "known", 58),
        ("-1", "known", -1),
        ("all", "invalid_type", None),
        ("06", "invalid_type", None),
        ("TCP", "invalid_type", None),
        (6, "invalid_type", None),
        (True, "invalid_type", None),
        ({}, "invalid_type", None),
        ("256", "invalid_type", None),
    ],
)
def test_protocol_parsing_does_not_guess(ssh_plan, value, state, number):
    observed = project(ssh_plan(ip_protocol=value)).rules.items[0].protocol
    assert observed.state == state
    if state == "known":
        assert observed.number == number


def test_all_alias_is_legacy_only(ssh_plan):
    assert (
        project(ssh_plan("legacy", protocol="all")).rules.items[0].protocol.number == -1
    )
    assert (
        project(ssh_plan("inline", protocol="all")).rules.items[0].protocol.state
        == "invalid_type"
    )


@pytest.mark.parametrize(
    "start,end,state",
    [
        (0, 65535, "known"),
        (23, 22, "invalid_type"),
        (True, 22, "invalid_type"),
        ("22", 22, "invalid_type"),
        (-1, 22, "invalid_type"),
        (22, 65536, "invalid_type"),
        (None, 22, "null"),
    ],
)
def test_port_bounds_and_strict_types(ssh_plan, start, end, state):
    assert (
        project(ssh_plan(from_port=start, to_port=end)).rules.items[0].ports.state
        == state
    )


@pytest.mark.parametrize(
    "value,state,prefix",
    [
        ("192.0.2.17/24", "known", 24),
        ("192.0.2.17/0", "known", 0),
        ("::/0", "invalid_type", None),
        ("0.0.0.0/33", "invalid_type", None),
        ("0.0.0.0/0 ", "invalid_type", None),
        ("0.0.0.0/0.0.0.0", "invalid_type", None),
        ("0.0.0.0", "invalid_type", None),
        (123, "invalid_type", None),
    ],
)
def test_cidr_syntax_family_and_host_bit_normalization(ssh_plan, value, state, prefix):
    observed = project(ssh_plan(cidr_ipv4=value)).rules.items[0].sources.ipv4.items[0]
    assert observed.state == state
    if state == "known":
        assert observed.prefix_length == prefix


def test_ipv6_and_reference_strings_are_discarded(ssh_plan):
    p = project(
        ssh_plan(
            cidr_ipv4=None,
            cidr_ipv6="0000:0000:0000:0000:0000:0000:0000:0000/0",
            prefix_list_id="SENTINEL_PREFIX",
            referenced_security_group_id="SENTINEL_GROUP",
            description="SENTINEL_SECRET",
        )
    )
    assert p.rules.items[0].sources.ipv6.items[0].prefix_length == 0
    assert p.rules.items[0].sources.prefix_lists.state == "present"
    assert p.rules.items[0].sources.security_groups.state == "present"
    assert "SENTINEL" not in p.model_dump_json() + repr(p)


@pytest.mark.parametrize("representation", ["modern", "legacy", "inline"])
@pytest.mark.parametrize(
    "kind",
    [
        "root_sensitive",
        "unknown",
        "sensitive_descendant",
        "missing_metadata",
        "null_after",
        "missing_after",
        "irrelevant",
    ],
)
def test_masks_and_desired_object_priority(ssh_plan, representation, kind):
    plan = ssh_plan(representation)
    change = plan["resource_changes"][0]["change"]
    field = "ip_protocol" if representation == "modern" else "protocol"
    mask = {"ingress": [{field: True}]} if representation == "inline" else {field: True}
    if kind == "root_sensitive":
        change["after_sensitive"] = True
    elif kind == "unknown":
        change["after_unknown"] = mask
    elif kind == "sensitive_descendant":
        change["after_sensitive"] = (
            {"ingress": [{field: {"child": True}}]}
            if representation == "inline"
            else {field: {"child": True}}
        )
    elif kind == "missing_metadata":
        change.pop("after_unknown")
    elif kind == "null_after":
        change["after"] = None
    elif kind == "missing_after":
        change.pop("after")
    else:
        change["after_sensitive"] = (
            {"ingress": [{"description": True}]}
            if representation == "inline"
            else {"description": True}
        )
    p = project(plan)
    if representation == "inline":
        observed = p.rules if p.rules.state != "known" else p.rules.items[0].protocol
    else:
        observed = (
            p.rules.items[0]
            if p.rules.items[0].state != "known"
            else p.rules.items[0].protocol
        )
    expected = {
        "root_sensitive": "sensitive",
        "unknown": "unknown",
        "sensitive_descendant": "sensitive",
        "missing_metadata": "unverified",
        "null_after": "unavailable",
        "missing_after": "unavailable",
        "irrelevant": "known",
    }[kind]
    # A legacy unknown root makes direction unresolved, with an unavailable rule.
    if representation == "legacy" and kind in {
        "root_sensitive",
        "missing_metadata",
        "null_after",
        "missing_after",
    }:
        observed = p.direction
    assert observed.state == expected


def test_reordered_inventory_sensitive_mask_withholds_whole_inline_set(ssh_plan):
    plan = ssh_plan("inline")
    rule = deepcopy(plan["resource_changes"][0]["change"]["after"]["ingress"][0])
    plan["resource_changes"][0]["change"]["after"]["ingress"].append(
        {**rule, "cidr_blocks": ["SENTINEL_SECRET"]}
    )
    inventory = plan["planned_values"]["root_module"]["resources"][0]
    inventory["values"]["ingress"] = list(
        reversed(plan["resource_changes"][0]["change"]["after"]["ingress"])
    )
    inventory["sensitive_values"] = {"ingress": [{"cidr_blocks": [True]}, {}]}
    p = project(plan)
    assert p.rules.state == "sensitive"
    assert "SENTINEL" not in p.model_dump_json()


@pytest.mark.parametrize("collection", ["rules", "cidrs"])
def test_unknown_tails_are_never_truncated_to_empty_success(ssh_plan, collection):
    plan = ssh_plan("inline" if collection == "rules" else "legacy")
    change = plan["resource_changes"][0]["change"]
    change["after_unknown"] = (
        {"ingress": [{}, True]}
        if collection == "rules"
        else {"cidr_blocks": [False, True]}
    )
    p = project(plan)
    observed = p.rules if collection == "rules" else p.rules.items[0].sources.ipv4
    assert observed.state == "unknown"


@pytest.mark.parametrize("kind", ["rules", "sources"])
def test_work_budgets_fail_before_oversized_projection(ssh_plan, monkeypatch, kind):
    monkeypatch.setattr(
        module, "MAX_SSH_RULES" if kind == "rules" else "MAX_SSH_SOURCE_ENTRIES", 0
    )
    with pytest.raises(AnalysisError, match="PLAN_LIMIT_EXCEEDED"):
        project(ssh_plan())


@pytest.mark.parametrize("direction", ["egress", "SENTINEL", {}, None])
def test_excluded_or_invalid_direction_never_retains_rule_values(ssh_plan, direction):
    p = project(ssh_plan("legacy", type=direction, cidr_blocks=["SENTINEL_SECRET"]))
    assert p.rules.items[0].state == "unavailable"
    assert "SENTINEL" not in p.model_dump_json()
