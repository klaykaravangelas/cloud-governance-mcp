"""Verify report semantics against synthetic plans, independent of transport."""

import copy
import json
from pathlib import Path

import pytest

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import PlanAnalysis, ResourceSnapshot

FIXTURES = Path(__file__).parent / "fixtures" / "plans"


def fixture_snapshot(name: str) -> ResourceSnapshot:
    """Use the real adapter so report cases exercise its actual core contract."""
    return TerraformPlanAdapter().normalize(json.loads((FIXTURES / name).read_text()))


def test_mixed_plan_counts_each_merged_resource_once() -> None:
    report = summarize(fixture_snapshot("mixed_nested.json"))
    assert report.summary.model_dump() == {
        "total_resources": 7,
        "changing_resources": 4,
        "by_action": {
            "create": 1,
            "update": 1,
            "delete": 1,
            "replace": 1,
            "no_op": 1,
            "read": 1,
            "unreported": 1,
        },
        "by_type": {
            "aws_ami": 1,
            "aws_db_instance": 1,
            "aws_instance": 2,
            "aws_s3_bucket": 1,
            "aws_security_group": 1,
            "google_storage_bucket": 1,
        },
        "by_mode": {"managed": 6, "data": 1},
    }
    assert report.analysis_status == "partial"
    assert [(warning.code, warning.count) for warning in report.warnings] == [
        ("CHANGE_ACTIONS_UNREPORTED", 1)
    ]
    records = {resource.address: resource for resource in report.resources}
    assert records["aws_instance.old"].actions == ["delete"]
    assert records["aws_instance.old"].source == "resource_changes"
    assert records["aws_s3_bucket.new"].source == "both"
    assert records["data.aws_ami.base"].mode == "data"
    assert records['google_storage_bucket.archive["a.b"]'].actions == []


@pytest.mark.parametrize("actions", [["delete", "create"], ["create", "delete"]])
def test_replacement_order_is_preserved_without_inflating_create_delete(
    actions: list[str],
) -> None:
    snapshot = fixture_snapshot("encrypted_rds.json")
    snapshot.resources[0].resource.actions = actions
    snapshot.resources[0].resource.action_category = "replace"
    report = summarize(snapshot)
    assert report.summary.total_resources == report.summary.changing_resources == 1
    assert report.summary.by_action.replace == 1
    assert report.summary.by_action.create == report.summary.by_action.delete == 0
    assert report.resources[0].actions == actions


@pytest.mark.parametrize(
    "category", ["create", "update", "delete", "replace", "read", "no_op"]
)
def test_data_resources_never_increase_managed_change_count(category: str) -> None:
    snapshot = fixture_snapshot("encrypted_rds.json")
    record = snapshot.resources[0].resource
    record.mode = "data"
    record.actions = (
        ["delete", "create"] if category == "replace" else [category.replace("_", "-")]
    )
    record.action_category = category
    report = summarize(snapshot)
    assert report.summary.total_resources == report.summary.by_mode.data == 1
    assert report.summary.changing_resources == report.summary.by_mode.managed == 0
    assert report.summary.by_action.model_dump()[category] == 1


def test_empty_complete_plan_includes_all_zero_buckets() -> None:
    report = summarize(fixture_snapshot("empty.json"))
    assert report.analysis_status == "complete"
    assert report.summary.total_resources == report.summary.changing_resources == 0
    assert report.summary.by_action.model_dump() == dict.fromkeys(
        ["create", "update", "delete", "replace", "no_op", "read", "unreported"], 0
    )
    assert report.summary.by_type == {}
    assert report.summary.by_mode.model_dump() == {"managed": 0, "data": 0}
    assert report.resources == report.warnings == []


@pytest.mark.parametrize(
    ("document", "codes"),
    [
        ({"format_version": "1.0", "complete": True, "planned_values": {}}, []),
        (
            {"format_version": "1.0", "complete": True, "resource_changes": []},
            ["PLANNED_VALUES_UNAVAILABLE"],
        ),
        (
            {"format_version": "1.0", "planned_values": {}},
            ["PLAN_COMPLETENESS_UNSPECIFIED"],
        ),
        (
            {"format_version": "1.0", "complete": False, "planned_values": {}},
            ["PLAN_INCOMPLETE"],
        ),
    ],
)
def test_empty_coverage_depends_on_reported_metadata(
    document: dict, codes: list[str]
) -> None:
    report = summarize(TerraformPlanAdapter().normalize(document))
    assert [warning.code for warning in report.warnings] == codes
    assert report.analysis_status == ("partial" if codes else "complete")
    assert report.summary.total_resources == 0


def test_partial_plan_retains_warnings_without_counting_opaque_payloads() -> None:
    snapshot = fixture_snapshot("partial.json")
    report = summarize(snapshot)
    assert report.analysis_status == "partial"
    assert report.summary.total_resources == report.summary.by_action.no_op == 1
    assert report.summary.changing_resources == 0
    assert report.warnings == snapshot.warnings


def test_report_is_deterministic_and_independent_of_mutable_snapshot() -> None:
    snapshot = fixture_snapshot("mixed_nested.json")
    expected = summarize(snapshot).model_dump_json()
    snapshot.resources.reverse()
    snapshot.warnings.reverse()
    before = copy.deepcopy(snapshot)
    report = summarize(snapshot)
    assert report.model_dump_json() == expected
    assert snapshot == before
    snapshot.resources[0].resource.actions.clear()
    snapshot.warnings[0].count = 99
    assert report.model_dump_json() == expected
    assert PlanAnalysis.model_validate_json(expected) == report


def test_report_omits_masks_attributes_and_secret_sentinels(caplog) -> None:
    report = summarize(fixture_snapshot("unknown_sensitive.json"))
    encoded = report.model_dump_json()
    assert "SENTINEL_" not in encoded
    assert "SENTINEL_" not in repr(report)
    assert caplog.text == ""
    assert set(report.model_dump()) == {
        "schema_version",
        "format_version",
        "terraform_version",
        "analysis_status",
        "summary",
        "resources",
        "warnings",
    }
    for forbidden in (
        "unknown_paths",
        "sensitive_paths",
        "unknown_metadata_complete",
        "password",
        "credentials",
        "storage_encrypted",
        "findings",
        "compliance_status",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize("name", ["encrypted_rds.json", "unencrypted_rds.json"])
def test_contrasting_encryption_values_yield_the_same_analysis(name: str) -> None:
    assert summarize(fixture_snapshot(name)) == summarize(
        fixture_snapshot("encrypted_rds.json")
    )


def test_inconsistent_internal_snapshot_fails_without_validation_details() -> None:
    snapshot = fixture_snapshot("mixed_nested.json")
    snapshot.warnings.clear()  # Unreported resources must retain coverage warnings.
    with pytest.raises(AnalysisError) as failure:
        summarize(snapshot)
    assert failure.value.code == ErrorCode.INTERNAL_ERROR
    assert failure.value.__suppress_context__
    assert "google_storage_bucket" not in str(failure.value)
