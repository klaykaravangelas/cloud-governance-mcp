"""Selected-policy projection, strict graphs, catalog integrity and work limits."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

import cloud_governance_mcp.adapters.terraform as adapter_module
import cloud_governance_mcp.ssh_projection as ssh_module
from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog
from cloud_governance_mcp.engine.opa import validate_checks
from cloud_governance_mcp.errors import AnalysisError
from cloud_governance_mcp.evaluation_errors import EvaluationFailure
from cloud_governance_mcp.evaluation_models import (
    EvaluationInput,
    validate_evaluation_input,
)
from cloud_governance_mcp.projection import to_evaluation_input

IDS = ["AWS-RDS-001", "AWS-SG-001"]


def request(plan, ids=None):
    ids = ids if ids is not None else IDS
    snapshot = TerraformPlanAdapter(include_policy_values=True).normalize(plan, ids)
    return to_evaluation_input(snapshot, ids)


def test_unselected_policy_values_and_limits_are_never_consumed(
    ssh_plan, rds_graph, monkeypatch
):
    def forbidden(*args):
        raise AssertionError("Unselected projection called")

    monkeypatch.setattr(adapter_module, "project_ssh_resources", forbidden)
    p = request(ssh_plan(), ["AWS-RDS-001"])
    assert p.resources[0].ssh_state is None
    monkeypatch.undo()
    monkeypatch.setattr(adapter_module, "project_rds_resources", forbidden)
    p = request(rds_graph(), ["AWS-SG-001"])
    assert all(r.desired_state.scope == "unavailable" for r in p.resources)
    assert all(r.desired_state.association.state == "not_required" for r in p.resources)


@pytest.mark.parametrize(
    "defect",
    [
        "schema",
        "wrong_representation",
        "missing_ssh",
        "unselected_ssh",
        "wrong_provider",
        "data",
        "deleted",
        "raw_payload",
    ],
)
def test_engine_schema_rejects_malformed_or_out_of_scope_projections(ssh_plan, defect):
    p = request(ssh_plan(), ["AWS-SG-001"]).model_dump()
    r = p["resources"][0]
    if defect == "schema":
        p["schema_version"] = "2"
    elif defect == "wrong_representation":
        r["ssh_state"]["representation"] = "inline"
    elif defect == "missing_ssh":
        r["ssh_state"] = None
    elif defect == "unselected_ssh":
        p["selected_policy_ids"] = ["AWS-RDS-001"]
    elif defect == "wrong_provider":
        r["provider_name"] = "other/provider"
    elif defect == "data":
        r["mode"] = "data"
    elif defect == "deleted":
        r["action_category"] = "delete"
    else:
        r["ssh_state"]["cidr"] = "SENTINEL"
    # Inline with a singleton modern-shaped rule is otherwise structurally valid;
    # the resource-type/representation graph check must still reject it.
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(p)


@pytest.mark.parametrize(
    "defect", ["version", "type", "paths", "reason_family", "missing_reason", "outcome"]
)
def test_catalog_guards_each_policy_not_just_total_counts(defect):
    p = load_catalog().model_dump()
    ssh = next(p for p in p["policies"] if p["policy_id"] == "AWS-SG-001")
    if defect == "version":
        ssh["policy_version"] = "1.1.0"
    elif defect == "type":
        ssh["supported_resource_types"] = p["policies"][0]["supported_resource_types"]
    elif defect == "paths":
        ssh["required_paths"] = []
    elif defect == "reason_family":
        ssh["reasons"]["RDS_ENCRYPTION_ENABLED"] = p["policies"][0]["reasons"][
            "RDS_ENCRYPTION_ENABLED"
        ]
    elif defect == "missing_reason":
        ssh["reasons"].pop("SSH_RULE_UNKNOWN")
    else:
        ssh["reasons"]["SSH_RULE_UNKNOWN"]["outcome"] = "pass"
    with pytest.raises(ValidationError):
        PolicyCatalog.model_validate(p)


def test_selection_defaults_and_reverse_order_are_canonical():
    assert validate_evaluation_input({"plan_path": "x"}).policy_ids == [
        "AWS-RDS-001",
        "AWS-S3-001",
        "AWS-SG-001",
        "AWS-TAG-001",
    ]
    assert (
        validate_evaluation_input(
            {"plan_path": "x", "policy_ids": list(reversed(IDS))}
        ).policy_ids
        == IDS
    )


@pytest.mark.parametrize(
    "code",
    [
        "RDS_ENCRYPTION_ENABLED",
        "SSH_INLINE_UNRESTRICTED_INGRESS",
        "SSH_RULE_NO_UNRESTRICTED_INGRESS",
    ],
)
def test_complete_but_wrong_reason_batches_fail_atomically(ssh_plan, code):
    plan = ssh_plan()
    plan["resource_changes"][0]["change"]["after_sensitive"] = True
    p = request(plan, ["AWS-SG-001"])
    template = next(
        p
        for p in load_catalog().policies
        if p.policy_id == ("AWS-RDS-001" if code.startswith("RDS") else "AWS-SG-001")
    ).reasons[code]
    with pytest.raises(EvaluationFailure, match="OPA_OUTPUT_INVALID"):
        validate_checks(
            {
                "schema_version": "1",
                "checks": [
                    {
                        "policy_id": "AWS-SG-001",
                        "resource_address": p.resources[0].address,
                        "reason_code": code,
                        "outcome": template.outcome,
                        "attribute_path": template.attribute_path,
                    }
                ],
            },
            p,
            load_catalog(),
        )


@pytest.mark.parametrize(
    "actions",
    [
        ["create"],
        ["update"],
        ["no-op"],
        ["read"],
        ["delete", "create"],
        ["create", "delete"],
    ],
)
def test_after_wins_without_changing_analysis(actions, ssh_plan):
    plan = ssh_plan()
    plan["resource_changes"][0]["change"]["actions"] = actions
    plan["planned_values"]["root_module"]["resources"][0]["values"] = {
        "ip_protocol": "udp",
        "cidr_ipv4": "SENTINEL",
        "from_port": 443,
        "to_port": 443,
    }
    before = deepcopy(plan)
    snapshot = TerraformPlanAdapter(include_policy_values=True).normalize(plan, IDS)
    rule = snapshot.resources[0].ssh_state.rules.items[0]
    assert rule.protocol.number == 6 and rule.ports.from_port == 22
    assert summarize(snapshot) == summarize(TerraformPlanAdapter().normalize(plan))
    assert plan == before
    assert "SENTINEL" not in snapshot.model_dump_json()


@pytest.mark.parametrize("kind", ["rules", "sources"])
def test_work_ceiling_exact_boundary_and_one_over(kind, ssh_plan, monkeypatch):
    plan = ssh_plan("inline")
    rules = plan["resource_changes"][0]["change"]["after"]["ingress"]
    if kind == "rules":
        monkeypatch.setattr(ssh_module, "MAX_SSH_RULES", 1)
    else:
        # One IPv4 entry plus the optional self slot are consumed.
        monkeypatch.setattr(ssh_module, "MAX_SSH_SOURCE_ENTRIES", 2)
    request(plan, ["AWS-SG-001"])
    if kind == "rules":
        rules.append(deepcopy(rules[0]))
    else:
        rules[0]["cidr_blocks"].append("192.0.2.0/24")
    with pytest.raises(AnalysisError, match="PLAN_LIMIT_EXCEEDED"):
        request(plan, ["AWS-SG-001"])
    assert len(summarize(TerraformPlanAdapter().normalize(plan)).resources) == 1


def test_large_inline_graph_has_one_field_view_per_resource(ssh_plan, monkeypatch):
    plan = ssh_plan("inline")
    rules = plan["resource_changes"][0]["change"]["after"]["ingress"]
    rules[:] = [deepcopy(rules[0]) for _ in range(10000)]
    calls = []
    original = ssh_module._View.__init__

    def observed(self, *args):
        calls.append(None)
        original(self, *args)

    monkeypatch.setattr(ssh_module._View, "__init__", observed)
    p = request(plan, ["AWS-SG-001"])
    assert len(p.resources[0].ssh_state.rules.items) == 10000
    assert len(calls) == 1


@pytest.mark.parametrize("representation", ["inline", "legacy", "modern"])
@pytest.mark.parametrize(
    "kind,expected",
    [("inventory", "unverified"), ("null", "unavailable"), ("missing", "unavailable")],
)
def test_missing_desired_never_falls_back_to_inventory_or_before(
    ssh_plan, representation, kind, expected
):
    plan = ssh_plan(representation)
    change = plan["resource_changes"][0]["change"]
    change["before"] = deepcopy(change["after"])
    if kind == "inventory":
        plan["resource_changes"] = []
    elif kind == "null":
        change["after"] = None
    else:
        change.pop("after")
    p = request(plan, ["AWS-SG-001"]).resources[0].ssh_state
    observed = (
        p.direction
        if representation == "legacy"
        else p.rules
        if representation == "inline"
        else p.rules.items[0]
    )
    assert observed.state == expected


def test_injected_graph_cannot_bypass_global_projected_rule_ceiling(ssh_plan):
    payload = request(ssh_plan("inline"), ["AWS-SG-001"]).model_dump()
    payload["resources"][0]["ssh_state"]["rules"]["items"] = [
        {"state": "unknown"}
    ] * 10001
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(payload)
