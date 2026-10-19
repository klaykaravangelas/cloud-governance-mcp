"""E1 contracts/projections run without OPA, Terraform, AWS or MCP imports."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.catalog import load_catalog
from cloud_governance_mcp.config import EvaluationSettings, validate_evaluation_settings
from cloud_governance_mcp.errors import ConfigurationError
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import validate_evaluation_input
from cloud_governance_mcp.models import KnownEncryption, UncertainEncryption

FIXTURES = Path(__file__).parent / "fixtures" / "plans"


def rds_plan() -> dict:
    """Use complete masks and both source copies to exercise precedence safely."""
    return json.loads((FIXTURES / "encrypted_rds.json").read_text())


def normalized(plan):
    return TerraformPlanAdapter(include_policy_values=True).normalize(plan)


@pytest.mark.parametrize(
    "selection", [None, [], ["AWS-RDS-001"] * 2, [True], "AWS-RDS-001"]
)
def test_invalid_selection_has_no_input_details(selection) -> None:
    with pytest.raises(EvaluationFailure) as error:
        validate_evaluation_input({"plan_path": "x", "policy_ids": selection})
    assert error.value.code == EvaluationCode.INVALID_POLICY_SELECTION
    assert repr(selection) not in str(error.value)


def test_catalog_selection_and_reason_templates_are_consistent() -> None:
    catalog = load_catalog()
    default = validate_evaluation_input({"plan_path": "x"})
    policy = catalog.select(default.policy_ids)[0]
    assert policy.policy_id == "AWS-RDS-001"
    assert policy.reasons["RDS_ENCRYPTION_DISABLED"].outcome == "fail"
    assert policy.reasons["RDS_ENCRYPTION_ENABLED"].outcome == "pass"
    with pytest.raises(EvaluationFailure, match="INVALID_POLICY_SELECTION"):
        catalog.select(["SENTINEL_UNKNOWN_POLICY"])


@pytest.mark.parametrize(
    "value,state",
    [
        (True, "known"),
        (False, "known"),
        (None, "null"),
        (1, "invalid_type"),
        (0, "invalid_type"),
        ("true", "invalid_type"),
        ("SENTINEL_SECRET", "invalid_type"),
        ([], "invalid_type"),
        ({"secret": "SENTINEL_SECRET"}, "invalid_type"),
    ],
)
def test_strict_encryption_projection_discards_invalid_values(value, state) -> None:
    plan = rds_plan()
    plan["resource_changes"][0]["change"]["after"]["storage_encrypted"] = value
    projection = normalized(plan).resources[0].desired_state
    assert projection.encryption.state == state
    if state == "known":
        assert projection.encryption.value is value
    else:
        assert "value" not in projection.encryption.model_dump()
    assert "SENTINEL_" not in projection.model_dump_json()


@pytest.mark.parametrize("mask", [True, {"storage_encrypted": True}])
def test_sensitivity_from_inventory_dominates_known_change_and_unknown(mask) -> None:
    plan = rds_plan()
    change = plan["resource_changes"][0]["change"]
    change["after"]["storage_encrypted"] = "SENTINEL_ENCRYPTION"
    change["after_unknown"] = {"storage_encrypted": True}
    plan["planned_values"]["root_module"]["resources"][0]["sensitive_values"] = mask
    projection = normalized(plan).resources[0].desired_state
    assert projection.encryption.state == "sensitive"
    assert "SENTINEL_" not in projection.model_dump_json()


@pytest.mark.parametrize(
    "cluster,scope",
    [
        (None, "standalone"),
        ("", "standalone"),
        ("SENTINEL_CLUSTER", "cluster_associated"),
        (False, "invalid_type"),
        (5, "invalid_type"),
        ({"key": "SENTINEL_CLUSTER"}, "invalid_type"),
    ],
)
def test_cluster_guard_never_retains_the_identifier(cluster, scope) -> None:
    plan = rds_plan()
    plan["resource_changes"][0]["change"]["after"]["cluster_identifier"] = cluster
    projection = normalized(plan).resources[0].desired_state
    assert projection.scope == scope
    assert "SENTINEL_" not in projection.model_dump_json()


@pytest.mark.parametrize(
    "mode", ["missing_mask", "inventory", "missing_after", "null_after"]
)
def test_no_fallback_or_invented_unknown_metadata(mode) -> None:
    plan = rds_plan()
    change = plan["resource_changes"][0]["change"]
    if mode == "missing_mask":
        del change["after_unknown"]
    elif mode == "inventory":
        plan["resource_changes"] = []
    elif mode == "missing_after":
        del change["after"]
    else:
        change["after"] = None
    projection = normalized(plan).resources[0].desired_state
    expected = "unverified" if mode in {"missing_mask", "inventory"} else "unavailable"
    assert projection.scope == expected
    assert projection.encryption.state == expected


def test_projection_is_opt_in_and_public_analysis_is_byte_identical() -> None:
    plan = rds_plan()
    original = deepcopy(plan)
    plain = TerraformPlanAdapter().normalize(plan)
    projected = normalized(plan)
    assert plain.resources[0].desired_state is None
    assert summarize(plain).model_dump_json() == summarize(projected).model_dump_json()
    assert plan == original


@pytest.mark.parametrize(
    "data",
    [
        {"state": "known", "value": 1},
        {"state": "known", "value": "true"},
        {"state": "unknown", "value": "SENTINEL_SECRET"},
    ],
)
def test_projection_models_cannot_carry_unknown_or_coerced_values(data) -> None:
    with pytest.raises(ValidationError):
        (
            KnownEncryption if data["state"] == "known" else UncertainEncryption
        ).model_validate(data)


@pytest.mark.parametrize(
    "settings",
    [
        {"opa_path": "relative"},
        {"opa_path": "file:///tmp/opa"},
        {"opa_eval_timeout_seconds": True},
        {"max_opa_output_bytes": 0},
        {"opa_eval_timeout_seconds": 10, "opa_process_timeout_seconds": 10},
    ],
)
def test_invalid_operator_settings_are_safe(settings) -> None:
    with pytest.raises(ConfigurationError, match="Invalid analysis configuration"):
        validate_evaluation_settings(settings)


def test_evaluation_configuration_never_requires_an_installed_binary() -> None:
    assert EvaluationSettings().opa_path is None
    assert (
        EvaluationSettings(opa_path="/not/installed/opa").opa_path
        == "/not/installed/opa"
    )


@pytest.mark.parametrize(
    "mask,state",
    [
        ({"other": [True]}, "known"),
        ({"storage_encrypted": [True]}, "unknown"),
        ({"storage_encrypted": {"child": True}}, "unknown"),
        (True, "unknown"),
        ({"storage_encrypted": False}, "known"),
    ],
)
def test_required_scalar_mask_overlap_blocks_knowledge_but_unrelated_paths_do_not(
    mask, state
):
    data = rds_plan()
    data["resource_changes"][0]["change"]["after_unknown"] = mask
    assert normalized(data).resources[0].desired_state.encryption.state == state
