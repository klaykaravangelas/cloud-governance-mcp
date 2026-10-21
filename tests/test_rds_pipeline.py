"""Verify the actual adapter/graph boundary without requiring OPA or AWS."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

import cloud_governance_mcp.rds_associations as associations
from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog
from cloud_governance_mcp.engine.opa import validate_checks
from cloud_governance_mcp.evaluation_errors import EvaluationFailure
from cloud_governance_mcp.evaluation_models import EvaluationInput
from cloud_governance_mcp.projection import to_evaluation_input


def project(plan):
    """Use the real merged-source pipeline rather than calling its resolver twice."""
    return TerraformPlanAdapter(include_policy_values=True).normalize(plan)


@pytest.mark.parametrize(
    "actions",
    [["create"], ["update"], ["no-op"], ["delete", "create"], ["create", "delete"]],
)
def test_authoritative_after_wins_and_analysis_is_identical(rds_graph, actions):
    plan = rds_graph()
    for entry in plan["resource_changes"]:
        entry["change"]["actions"] = actions
    for entry in plan["planned_values"]["root_module"]["resources"]:
        entry["values"].update(
            cluster_identifier="SENTINEL_OTHER",
            arn="SENTINEL_ARN",
            storage_encrypted=False,
        )
    original = deepcopy(plan)
    snapshot = project(plan)
    assert snapshot.resources[1].desired_state.association.state == "resolved"
    assert snapshot.resources[0].desired_state.encryption.value is True
    assert summarize(snapshot) == summarize(TerraformPlanAdapter().normalize(plan))
    assert all(
        item.desired_state is None
        for item in TerraformPlanAdapter().normalize(plan).resources
    )
    assert plan == original
    text = (
        snapshot.model_dump_json()
        + repr(snapshot)
        + to_evaluation_input(snapshot, ["AWS-RDS-001"]).model_dump_json()
    )
    for value in ["SENTINEL_", "demo-cluster", "arn:aws", "111122223333", "us-east-1"]:
        assert value not in text


@pytest.mark.parametrize(
    "field", ["cluster_identifier", "arn", "region", "storage_encrypted"]
)
@pytest.mark.parametrize("mask", [True, {"child": [True]}])
def test_inventory_sensitive_union_dominates_change_unknown(rds_graph, field, mask):
    plan = rds_graph()
    plan["resource_changes"][0]["change"]["after_unknown"] = {field: True}
    plan["planned_values"]["root_module"]["resources"][0]["sensitive_values"] = {
        field: mask
    }
    snapshot = project(plan)
    target, member = snapshot.resources
    if field == "storage_encrypted":
        assert target.desired_state.encryption.state == "sensitive"
        assert member.desired_state.association.state == "resolved"
    else:
        assert member.desired_state.association.state == "context_unverified"


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("source", ["inventory_only", "missing_after", "null_after"])
def test_inventory_or_before_cannot_supply_authoritative_link_values(
    rds_graph, index, source
):
    plan = rds_graph()
    change = plan["resource_changes"][index]["change"]
    change["before"] = deepcopy(change["after"])
    if source == "inventory_only":
        plan["resource_changes"].pop(index)
    elif source == "missing_after":
        change.pop("after")
    else:
        change["after"] = None
    target, member = project(plan).resources
    if index == 0:
        assert target.desired_state.encryption.state == (
            "unverified" if source == "inventory_only" else "unavailable"
        )
        assert member.desired_state.association.state == "context_unverified"
    else:
        assert member.desired_state.association.state == (
            "unverified" if source == "inventory_only" else "unavailable"
        )


@pytest.mark.parametrize("kind", ["data", "delete", "provider", "type"])
def test_ineligible_targets_never_supply_inheritance(rds_graph, kind):
    plan = rds_graph()
    plan["planned_values"] = {}
    target = plan["resource_changes"][0]
    if kind == "data":
        target["mode"] = "data"
    elif kind == "delete":
        target["change"].update(actions=["delete"], after=None)
    elif kind == "provider":
        target["provider_name"] = "example.invalid/other/provider"
    else:
        target["type"] = "aws_rds_global_cluster"
    assert project(plan).resources[1].desired_state.association.state == "not_found"


def test_large_graph_indexes_each_link_once(rds_graph, monkeypatch):
    # 10,000 resources exercise the configured resource ceiling. Count evidence
    # extraction rather than using a machine-dependent timing assertion.
    plan = rds_graph(members=0)
    cluster = plan["resource_changes"][0]
    member = rds_graph()["resource_changes"][1]
    plan["planned_values"] = {}
    plan["resource_changes"] = []
    for index in range(5000):
        for entry, kind in [(cluster, "cluster"), (member, "db")]:
            copy = deepcopy(entry)
            copy["address"] += f"[{index}]"
            copy["change"]["after"].update(
                cluster_identifier=f"cluster-{index}",
                arn=f"arn:aws:rds:us-east-1:111122223333:{kind}:cluster-{index}",
            )
            plan["resource_changes"].append(copy)
    original, calls = associations._linkage, []

    def observed(*args):
        calls.append(None)
        return original(*args)

    monkeypatch.setattr(associations, "_linkage", observed)
    snapshot = project(plan)
    assert len(calls) == len(snapshot.resources) == 10000
    assert (
        sum(
            item.desired_state.association.state == "resolved"
            for item in snapshot.resources
        )
        == 5000
    )


@pytest.mark.parametrize(
    "defect",
    [
        "schema",
        "duplicate",
        "dangling",
        "self",
        "deleted",
        "data",
        "provider",
        "type",
        "scope",
        "extra",
    ],
)
def test_input_graph_rejects_invalid_targets_and_shapes(rds_graph, defect):
    payload = to_evaluation_input(project(rds_graph()), ["AWS-RDS-001"]).model_dump()
    target, member = payload["resources"]
    if defect == "schema":
        payload["schema_version"] = "1"
    elif defect == "duplicate":
        payload["resources"].append(deepcopy(target))
    elif defect in {"dangling", "self"}:
        member["desired_state"]["association"]["cluster_address"] = (
            member["address"] if defect == "self" else "missing"
        )
    elif defect == "deleted":
        target["action_category"] = "delete"
    elif defect == "data":
        target["mode"] = "data"
    elif defect == "provider":
        target["provider_name"] = "other/provider"
    elif defect == "type":
        target["resource_type"] = "aws_db_instance"
    elif defect == "scope":
        target["desired_state"]["scope"] = "standalone"
    else:
        member["desired_state"]["association"]["arn"] = "SENTINEL_ARN"
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(payload)


@pytest.mark.parametrize(
    "code",
    [
        "RDS_ENCRYPTION_ENABLED",
        "RDS_CLUSTER_LINK_UNKNOWN",
        "RDS_CLUSTER_ENCRYPTION_UNKNOWN",
        "RESOURCE_NOT_SUPPORTED",
    ],
)
def test_engine_rejects_complete_batches_with_wrong_member_reason(rds_graph, code):
    request = to_evaluation_input(project(rds_graph()), ["AWS-RDS-001"])
    catalog = load_catalog()
    checks = []
    for item, reason in zip(
        request.resources, ["RDS_ENCRYPTION_ENABLED", code], strict=True
    ):
        template = catalog.policies[0].reasons[reason]
        checks.append(
            dict(
                policy_id="AWS-RDS-001",
                resource_address=item.address,
                reason_code=reason,
                outcome=template.outcome,
                attribute_path=template.attribute_path,
            )
        )
    with pytest.raises(EvaluationFailure, match="OPA_OUTPUT_INVALID"):
        validate_checks({"schema_version": "1", "checks": checks}, request, catalog)


@pytest.mark.parametrize("defect", ["missing", "unknown", "path", "outcome"])
def test_catalog_checks_exact_reason_membership_and_semantics(defect):
    payload = load_catalog().model_dump()
    reasons = payload["policies"][0]["reasons"]
    if defect == "missing":
        reasons.pop("RDS_CLUSTER_LINK_AMBIGUOUS")
    elif defect == "unknown":
        reasons["SENTINEL_UNKNOWN"] = reasons.pop("RDS_CLUSTER_LINK_AMBIGUOUS")
    elif defect == "path":
        reasons["RDS_CLUSTER_LINK_AMBIGUOUS"]["attribute_path"] = ["storage_encrypted"]
    else:
        reasons["RDS_CLUSTER_ENCRYPTION_UNKNOWN"]["outcome"] = "pass"
    with pytest.raises(ValidationError):
        PolicyCatalog.model_validate(payload)
