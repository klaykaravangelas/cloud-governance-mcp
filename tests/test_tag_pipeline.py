"""Strict three-policy contracts, safe path provenance and projection separation."""

import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

import cloud_governance_mcp.adapters.terraform as adapter_module
import cloud_governance_mcp.evaluation_models as model_module
from cloud_governance_mcp.__main__ import main, parse_configuration
from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog
from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.engine.opa import validate_checks
from cloud_governance_mcp.evaluation_errors import EvaluationFailure
from cloud_governance_mcp.evaluation_models import EvaluationInput
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.projection import to_evaluation_input

TAG = ["AWS-TAG-001"]


def request(plan):
    """Use the actual selected adapter/projection contract, not a mirror model."""
    snapshot = TerraformPlanAdapter(include_policy_values=True).normalize(plan, TAG)
    return to_evaluation_input(snapshot, TAG)


@pytest.mark.parametrize(
    "path",
    [
        ["tags_all", "NotConfigured"],
        ["tags", "Owner"],
        ["tags_all", "Owner", 0],
        [],
        ["tags_all", 0],
    ],
)
def test_output_cannot_inject_paths_or_unconfigured_keys(tag_plan, path):
    projected = request(
        tag_plan({"tags_all": {"Environment": "dev", "Project": "demo"}})
    )
    check = {
        "policy_id": TAG[0],
        "resource_address": projected.resources[0].address,
        "outcome": "fail",
        "reason_code": "TAG_ALL_KEY_MISSING",
        "attribute_path": path,
    }
    with pytest.raises(EvaluationFailure):
        validate_checks(
            {"schema_version": "1", "checks": [check]}, projected, load_catalog()
        )


def test_valid_dynamic_path_is_preserved_and_wrong_state_or_pass_is_rejected(tag_plan):
    projected = request(
        tag_plan({"tags_all": {"Environment": "dev", "Project": "demo"}})
    )
    check = {
        "policy_id": TAG[0],
        "resource_address": projected.resources[0].address,
        "outcome": "fail",
        "reason_code": "TAG_ALL_KEY_MISSING",
        "attribute_path": ["tags_all", "Owner"],
    }
    assert validate_checks(
        {"schema_version": "1", "checks": [check]}, projected, load_catalog()
    ).checks[0].attribute_path == ["tags_all", "Owner"]
    for code, outcome, path in [
        ("TAG_ALL_KEY_UNKNOWN", "indeterminate", ["tags_all", "Owner"]),
        ("TAG_ALL_COMPLIANT", "pass", ["tags_all"]),
        ("TAG_ALL_MAP_NULL", "fail", ["tags_all"]),
    ]:
        invalid = {
            **check,
            "reason_code": code,
            "outcome": outcome,
            "attribute_path": path,
        }
        with pytest.raises(EvaluationFailure):
            validate_checks(
                {"schema_version": "1", "checks": [invalid]}, projected, load_catalog()
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "old_schema",
        "missing_config",
        "empty_config",
        "extra_config",
        "missing_projection",
        "extra_value",
        "foreign_key",
        "missing_entry",
        "duplicate_entry",
        "unordered_entries",
        "unordered_config",
        "unselected_projection",
        "wrong_type",
    ],
)
def test_engine_graph_rejects_injected_tag_contract_violations(tag_plan, mutation):
    data = request(tag_plan()).model_dump()
    p = data["resources"][0]["tag_state"]
    if mutation == "old_schema":
        data["schema_version"] = "3"
    elif mutation == "missing_config":
        data["tag_configuration"] = None
    elif mutation == "empty_config":
        data["tag_configuration"] = {}
    elif mutation == "extra_config":
        data["tag_configuration"]["value"] = "SENTINEL"
    elif mutation == "missing_projection":
        data["resources"][0]["tag_state"] = None
    elif mutation == "extra_value":
        p["entries"][0]["value"] = "SENTINEL"
    elif mutation == "foreign_key":
        p["entries"][0]["key"] = "AnotherKey"
    elif mutation == "missing_entry":
        p["entries"].pop()
    elif mutation == "duplicate_entry":
        p["entries"][1] = p["entries"][0]
    elif mutation == "unordered_entries":
        p["entries"].reverse()
    elif mutation == "unordered_config":
        data["tag_configuration"]["required_tag_keys"].reverse()
    elif mutation == "unselected_projection":
        data["selected_policy_ids"] = ["AWS-SG-001"]
    elif mutation == "wrong_type":
        data["resources"][0]["resource_type"] = "aws_rds_cluster_instance"
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(data)


def test_injected_work_ceiling_and_exact_boundary(tag_plan, monkeypatch):
    data = request(tag_plan()).model_dump()
    monkeypatch.setattr(model_module, "MAX_TAG_KEY_SLOTS", 3)
    assert EvaluationInput.model_validate(data)
    monkeypatch.setattr(model_module, "MAX_TAG_KEY_SLOTS", 2)
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(data)


def test_policy_selection_never_parses_unselected_values(tag_plan, monkeypatch):
    def forbidden(*args):
        raise AssertionError("Unselected parser called")

    adapter = TerraformPlanAdapter(include_policy_values=True)
    with monkeypatch.context() as patch:
        patch.setattr(adapter_module, "project_tag_resources", forbidden)
        assert (
            adapter.normalize(tag_plan(), ["AWS-RDS-001", "AWS-SG-001"])
            .resources[0]
            .tag_state
            is None
        )
    monkeypatch.setattr(adapter_module, "project_rds_resources", forbidden)
    monkeypatch.setattr(adapter_module, "project_ssh_resources", forbidden)
    assert adapter.normalize(tag_plan(), TAG).resources[0].tag_state.state == "known"


@pytest.mark.parametrize(
    "mutation",
    [
        "severity",
        "types",
        "version",
        "configuration",
        "path",
        "reason",
        "missing_policy",
    ],
)
def test_catalog_cannot_mix_other_policies_valid_metadata(mutation):
    doc = json.loads(
        files("cloud_governance_mcp.policies").joinpath("catalog.json").read_text()
    )["cloud_governance_catalog"]
    p = next(p for p in doc["policies"] if p["policy_id"] == "AWS-TAG-001")
    if mutation == "severity":
        p["severity"] = "high"
    elif mutation == "types":
        p["supported_resource_types"] = doc["policies"][0]["supported_resource_types"]
    elif mutation == "version":
        p["policy_version"] = "1.1.0"
    elif mutation == "configuration":
        p["required_configuration"] = []
    elif mutation == "path":
        p["reasons"]["TAG_ALL_KEY_MISSING"]["attribute_path"] = ["tags_all", "Owner"]
    elif mutation == "reason":
        p["reasons"]["SSH_RULE_UNRESTRICTED_INGRESS"] = next(
            p for p in doc["policies"] if p["policy_id"] == "AWS-SG-001"
        )["reasons"]["SSH_RULE_UNRESTRICTED_INGRESS"]
    elif mutation == "missing_policy":
        doc["policies"].pop()
    with pytest.raises(ValidationError):
        PolicyCatalog.model_validate(doc)


@pytest.mark.parametrize("bad", ["", "aws:Owner", "Owner\n", "SENTINEL key", "x" * 129])
def test_invalid_startup_keys_do_not_open_roots_or_echo_input(bad, monkeypatch, capsys):
    import cloud_governance_mcp.__main__ as entry

    def forbidden(*args):
        raise AssertionError("Roots opened")

    monkeypatch.setattr(entry, "RestrictedPlanLoader", forbidden)
    assert main(["--allowed-root", "/not/opened", "--required-tag-key", bad]) == 2
    captured = capsys.readouterr()
    assert (
        not captured.out
        and "SENTINEL" not in captured.err
        and "aws:Owner" not in captured.err
    )


def test_override_and_immutable_service_snapshot(tag_plan, tmp_path):
    _, settings = parse_configuration(
        ["--allowed-root", str(tmp_path), "--required-tag-key", "Owner"]
    )
    assert settings.required_tag_keys == ["Owner"]
    (tmp_path / "plan.json").write_text(json.dumps(tag_plan()))
    analysis = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(analysis) as loader:
        service = EvaluationService(analysis, settings, loader=loader)
        settings.required_tag_keys.append("CostCenter")
        projected = service._prepare("plan.json", TAG)[2]
    assert projected.tag_configuration.required_tag_keys == ["Owner"]
    assert parse_configuration(
        ["--allowed-root", str(tmp_path), "--required-tag-key=--help"]
    )[1].required_tag_keys == ["--help"]


@pytest.mark.parametrize(
    "actions",
    [["create"], ["update"], ["no-op"], ["delete", "create"], ["create", "delete"]],
)
def test_authoritative_after_wins_over_conflicting_inventory(tag_plan, actions):
    plan = tag_plan({"tags_all": {"Owner": "SENTINEL"}})
    entry = plan["resource_changes"][0]
    entry["change"]["actions"] = actions
    inventory = {k: v for k, v in entry.items() if k != "change"}
    inventory["values"] = {
        "tags_all": {"Environment": "dev", "Owner": "team", "Project": "demo"}
    }
    inventory["sensitive_values"] = {}
    plan["planned_values"] = {"root_module": {"resources": [inventory]}}
    projection = request(plan).resources[0].tag_state
    assert [e.state for e in projection.entries] == ["missing", "nonempty", "missing"]


def test_full_fixed_work_boundary_includes_withheld_maps(tag_plan):
    """Fifty keys × 1,000 resources is the actual fixed 50,000-slot limit."""
    template = request(tag_plan()).resources[0].model_dump()
    template["tag_state"] = {"source": "tags", "state": "missing"}
    data = {
        "schema_version": "5",
        "selected_policy_ids": TAG,
        "tag_configuration": {"required_tag_keys": [f"Key{i:02}" for i in range(50)]},
        "resources": [
            {**template, "address": f"aws_instance.example[{i}]"} for i in range(1000)
        ],
    }
    assert EvaluationInput.model_validate(data)
    data["resources"].append({**template, "address": "aws_instance.extra"})
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(data)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "ids",
    [
        [],
        ["UNKNOWN"],
        ["AWS-TAG-001"] * 2,
        ["AWS-RDS-001", "AWS-SG-001", "AWS-TAG-001", "OTHER"],
        [1],
    ],
)
async def test_invalid_selection_precedes_file_access(ids, tmp_path):
    class ForbiddenLoader:
        def read_plan(self, path):
            raise AssertionError("Plan accessed for an invalid selection")

    service = EvaluationService(
        AnalysisSettings(allowed_roots=[str(tmp_path)]),
        EvaluationSettings(),
        loader=ForbiddenLoader(),
    )
    with pytest.raises(EvaluationFailure) as failure:
        await service.evaluate("not-read.json", ids)
    assert failure.value.code.value == "INVALID_POLICY_SELECTION"
