"""M1: prove masked associations without leaking AWS lookup values."""

from copy import deepcopy

import pytest

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.rds_associations import project_rds_resources


def project(plan):
    """Isolate resolver behavior from the adapter's evaluation orchestration."""
    snapshot = TerraformPlanAdapter().normalize(plan)
    desired = {r["address"]: r["change"].get("after") for r in plan["resource_changes"]}
    project_rds_resources(snapshot.resources, desired)
    return snapshot


def member(snapshot):
    return next(
        r.desired_state
        for r in snapshot.resources
        if r.resource.resource_type == "aws_rds_cluster_instance"
    )


def test_unique_context_links_and_discards_lookup_values(rds_graph):
    plan = rds_graph(members=2)
    original = deepcopy(plan)
    result = project(plan)
    assert [r.desired_state.association.state for r in result.resources] == [
        "not_required",
        "resolved",
        "resolved",
    ]
    assert member(result).association.cluster_address == "aws_rds_cluster.example"
    assert member(result).encryption.state == "unavailable"
    for text in (result.model_dump_json(), repr(result)):
        for secret in (
            "demo-cluster",
            "demo-member",
            "arn:aws:",
            "111122223333",
            "us-east-1",
        ):
            assert secret not in text
    assert summarize(result) == summarize(TerraformPlanAdapter().normalize(plan))
    assert plan == original


@pytest.mark.parametrize(
    "mask,expected",
    [
        (True, "sensitive"),
        ({"cluster_identifier": True}, "sensitive"),
        ({"arn": {"child": True}}, "sensitive"),
        ({"region": [True]}, "sensitive"),
    ],
)
def test_member_sensitive_masks_block_parsing_even_on_scalar_descendants(
    mask, expected, rds_graph
):
    plan = rds_graph()
    plan["resource_changes"][1]["change"]["after_sensitive"] = mask
    assert member(project(plan)).association.state == expected


@pytest.mark.parametrize("field", ["cluster_identifier", "arn", "region"])
def test_unknown_consumed_fields_never_resolve_from_known_text(field, rds_graph):
    plan = rds_graph()
    plan["resource_changes"][1]["change"]["after_unknown"] = {field: True}
    assert member(project(plan)).association.state == "unknown"


@pytest.mark.parametrize(
    "field,value,state",
    [
        ("cluster_identifier", None, "null"),
        ("cluster_identifier", "", "invalid_type"),
        ("cluster_identifier", 1, "invalid_type"),
        ("cluster_identifier", [], "invalid_type"),
        ("cluster_identifier", "x" * 2049, "invalid_type"),
        ("arn", None, "context_unverified"),
        ("arn", "SENTINEL", "invalid_type"),
        ("arn", "arn:aws:s3:us-east-1:111122223333:db:member", "invalid_type"),
        ("arn", "arn:aws:rds:us-east-1:111122223333:cluster:member", "invalid_type"),
        ("region", "us-west-2", "invalid_type"),
        ("region", 1, "invalid_type"),
        ("region", None, "resolved"),
        ("region", "us-east-1", "resolved"),
    ],
)
def test_member_bad_values_and_region_consistency(field, value, state, rds_graph):
    plan = rds_graph()
    plan["resource_changes"][1]["change"]["after"][field] = value
    assert member(project(plan)).association.state == state


@pytest.mark.parametrize(
    "field,state", [("cluster_identifier", "missing"), ("arn", "context_unverified")]
)
def test_missing_linkage_fields_are_explicit(field, state, rds_graph):
    plan = rds_graph()
    del plan["resource_changes"][1]["change"]["after"][field]
    assert member(project(plan)).association.state == state


@pytest.mark.parametrize(
    "arn",
    [
        "arn:aws:rds:us-west-2:111122223333:cluster:demo-cluster",
        "arn:aws:rds:us-east-1:444455556666:cluster:demo-cluster",
        "arn:aws-cn:rds:us-east-1:111122223333:cluster:demo-cluster",
    ],
)
def test_same_name_in_other_context_is_not_a_link(arn, rds_graph):
    plan = rds_graph()
    plan["resource_changes"][0]["change"]["after"]["arn"] = arn
    assert member(project(plan)).association.state == "not_found"


@pytest.mark.parametrize("partition", ["aws", "aws-cn", "aws-us-gov"])
def test_supported_partitions_compare_exactly(partition, rds_graph):
    plan = rds_graph()
    for r in plan["resource_changes"]:
        r["change"]["after"]["arn"] = r["change"]["after"]["arn"].replace(
            "arn:aws:", f"arn:{partition}:"
        )
    assert member(project(plan)).association.state == "resolved"


@pytest.mark.parametrize(
    "unknown_field", [None, "arn", "cluster_identifier", "both", "conflict"]
)
@pytest.mark.parametrize("reverse", [False, True])
def test_exact_duplicates_and_uncertain_blockers_are_order_independent(
    unknown_field, reverse, rds_graph
):
    plan = rds_graph()
    duplicate = deepcopy(plan["resource_changes"][0])
    duplicate.update(address="aws_rds_cluster.other", name="other")
    if unknown_field == "both":
        duplicate["change"]["after_unknown"] = True
    elif unknown_field == "conflict":
        duplicate["change"]["after"]["cluster_identifier"] = "contradiction"
    elif unknown_field:
        duplicate["change"]["after_unknown"] = {unknown_field: True}
    plan["resource_changes"].append(duplicate)
    if reverse:
        plan["resource_changes"].reverse()
    expected = "ambiguous" if unknown_field is None else "context_unverified"
    assert member(project(plan)).association.state == expected


@pytest.mark.parametrize("dimension", ["identifier", "context"])
def test_proved_unequal_dimension_excludes_an_uncertain_target(dimension, rds_graph):
    plan = rds_graph()
    other = deepcopy(plan["resource_changes"][0])
    other.update(address="aws_rds_cluster.other", name="other")
    if dimension == "identifier":
        other["change"]["after"]["cluster_identifier"] = "unrelated"
        other["change"]["after_unknown"] = {"arn": True}
    else:
        other["change"]["after"]["arn"] = (
            "arn:aws:rds:us-west-2:111122223333:cluster:unrelated"
        )
        other["change"]["after_unknown"] = {"cluster_identifier": True}
    plan["resource_changes"].append(other)
    assert member(project(plan)).association.state == "resolved"


def test_no_target_and_deleted_target_never_use_before_values(rds_graph):
    plan = rds_graph()
    target = plan["resource_changes"][0]["change"]
    target.update(actions=["delete"], before=target["after"], after=None)
    assert member(project(plan)).association.state == "not_found"
    plan["resource_changes"] = plan["resource_changes"][1:]
    plan["planned_values"]["root_module"]["resources"] = plan["planned_values"][
        "root_module"
    ]["resources"][1:]
    plan["configuration"] = {"references": ["aws_rds_cluster.example.id"]}
    assert member(project(plan)).association.state == "not_found"


@pytest.mark.parametrize(
    "mode,state",
    [
        ("missing_mask", "unverified"),
        ("missing_after", "unavailable"),
        ("null_after", "unavailable"),
    ],
)
def test_incomplete_metadata_and_absent_desired_objects(mode, state, rds_graph):
    plan = rds_graph()
    change = plan["resource_changes"][1]["change"]
    if mode == "missing_mask":
        del change["after_unknown"]
    elif mode == "missing_after":
        del change["after"]
    else:
        change["after"] = None
    assert member(project(plan)).association.state == state
