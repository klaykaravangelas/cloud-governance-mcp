"""Validate identity/action fidelity and safe public analysis contracts."""

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from cloud_governance_mcp.models import (
    WARNING_MESSAGES,
    AnalysisWarning,
    NormalizedResource,
    PlanAnalysis,
    ResourceAnalysis,
    ResourceSnapshot,
)


def resource_data(**overrides: object) -> dict[str, object]:
    """Build a fresh synthetic replacement with nested and indexed identities."""
    return {
        "address": 'module.database["a.b"].aws_db_instance.example[0]',
        "resource_type": "aws_db_instance",
        "name": "example",
        "provider_name": "registry.terraform.io/hashicorp/aws",
        "mode": "managed",
        "module_address": 'module.database["a.b"]',
        "index": 0,
        "previous_address": None,
        "actions": ["delete", "create"],
        "action_category": "replace",
        "source": "both",
        **overrides,
    }


def analysis_data() -> dict[str, object]:
    """Provide a consistent single-resource report for focused contract mutations."""
    return {
        "schema_version": "1",
        "format_version": "1.2",
        "terraform_version": "1.14.0",
        "analysis_status": "complete",
        "summary": {
            "total_resources": 1,
            "changing_resources": 1,
            "by_action": {
                "create": 0,
                "update": 0,
                "delete": 0,
                "replace": 1,
                "no_op": 0,
                "read": 0,
                "unreported": 0,
            },
            "by_type": {"aws_db_instance": 1},
            "by_mode": {"managed": 1, "data": 0},
        },
        "resources": [resource_data()],
        "warnings": [],
    }


@pytest.mark.parametrize(
    ("actions", "category"),
    [
        (["create"], "create"),
        (["update"], "update"),
        (["delete"], "delete"),
        (["delete", "create"], "replace"),
        (["create", "delete"], "replace"),
        (["no-op"], "no_op"),
        (["read"], "read"),
    ],
)
def test_actions_and_opaque_addresses_are_preserved(
    actions: list[str], category: str
) -> None:
    item = ResourceAnalysis.model_validate(
        resource_data(actions=actions, action_category=category)
    )
    assert item.actions == actions
    assert item.index == 0
    assert item.module_address == 'module.database["a.b"]'
    assert item.address == 'module.database["a.b"].aws_db_instance.example[0]'


@pytest.mark.parametrize("index", ["", "a.b", 'a"b', 0, 2, None])
def test_instance_keys_retain_type_and_value(index: str | int | None) -> None:
    item = ResourceAnalysis.model_validate(resource_data(index=index))
    assert item.index == index
    assert type(item.index) is type(index)


@pytest.mark.parametrize(
    "override",
    [
        {"index": True},
        {"index": -1},
        {"index": 1.0},
        {"actions": ["forget"]},
        {"actions": ["create", "delete", "create"]},
        {"actions": ["update", "delete"]},
        {"actions": ["delete", "create"], "action_category": "create"},
        {"actions": []},
        {"source": "planned_values"},
        {"mode": "unknown"},
        {"address": ""},
        {"address": "x" * 2049},
        {"name": "name\n"},
        {"provider_name": 1},
        {"module_address": ""},
        {"attributes": {"password": "SECRET"}},
    ],
)
def test_malformed_or_inconsistent_resource_contracts_fail(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ResourceAnalysis.model_validate(resource_data(**override))


def test_inventory_only_resource_requires_explicit_uncertainty() -> None:
    item = ResourceAnalysis.model_validate(
        resource_data(source="planned_values", actions=[], action_category="unreported")
    )
    normalized = NormalizedResource(resource=item, unknown_metadata_complete=False)
    assert not normalized.unknown_metadata_complete
    with pytest.raises(ValidationError):
        NormalizedResource(resource=item, unknown_metadata_complete=True)


def test_mask_paths_preserve_root_objects_and_indices_without_entering_public_output() -> (
    None
):
    resource = ResourceAnalysis.model_validate(resource_data())
    normalized = NormalizedResource(
        resource=resource,
        # An empty path marks the whole value; integer steps identify list entries.
        unknown_paths=[[], ["network", 0, "address"]],
        sensitive_paths=[["SENSITIVE_FIELD", ""]],
        unknown_metadata_complete=True,
    )
    snapshot = ResourceSnapshot(
        format_version="1.2", resources=[normalized], warnings=[]
    )
    restored = ResourceSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored.resources[0].unknown_paths == [[], ["network", 0, "address"]]
    assert restored.resources[0].sensitive_paths == [["SENSITIVE_FIELD", ""]]
    public = PlanAnalysis.model_validate(analysis_data()).model_dump_json()
    assert "unknown_paths" not in public and "sensitive_paths" not in public
    assert "SENSITIVE_FIELD" not in repr(snapshot)
    assert "SENSITIVE_FIELD" not in repr(normalized)


@pytest.mark.parametrize("path", [[True], [-1], [1.0], [None], {"attribute": True}])
def test_mask_path_steps_are_strict_keys_or_nonnegative_indices(path: object) -> None:
    with pytest.raises(ValidationError):
        NormalizedResource(
            resource=ResourceAnalysis.model_validate(resource_data()),
            unknown_paths=[path],
            unknown_metadata_complete=True,
        )


def test_duplicate_snapshot_addresses_fail() -> None:
    normalized = NormalizedResource(
        resource=ResourceAnalysis.model_validate(resource_data()),
        unknown_metadata_complete=True,
    )
    with pytest.raises(ValidationError, match="unique"):
        ResourceSnapshot(format_version="1.0", resources=[normalized] * 2, warnings=[])


def test_response_round_trip_schema_and_explicit_nulls() -> None:
    report = PlanAnalysis.model_validate(analysis_data())
    assert PlanAnalysis.model_validate_json(report.model_dump_json()) == report
    dumped = report.model_dump(mode="json")
    assert dumped["resources"][0]["previous_address"] is None
    assert dumped["summary"]["by_action"]["unreported"] == 0
    schema = PlanAnalysis.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["ResourceAnalysis"]["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "schema_version",
        "format_version",
        "terraform_version",
        "analysis_status",
        "summary",
        "resources",
        "warnings",
    }


@pytest.mark.parametrize("version", ["2.0", "1", "1.x", "1.0\n", 1, True])
def test_output_format_version_is_a_supported_strict_string(version: object) -> None:
    data = analysis_data()
    data["format_version"] = version
    with pytest.raises(ValidationError):
        PlanAnalysis.model_validate(data)


@pytest.mark.parametrize(
    ("location", "value"),
    [
        (("summary", "total_resources"), True),
        (("summary", "total_resources"), -1),
        (("summary", "total_resources"), 2),
        (("summary", "changing_resources"), 0),
        (("summary", "by_action", "replace"), "1"),
        (("summary", "by_action", "replace"), 0),
        (("summary", "by_type"), {"aws_instance": 1}),
        (("summary", "by_mode"), {"managed": 0, "data": 1}),
        (("analysis_status",), "partial"),
        (("summary", "unexpected"), "SECRET"),
        (("findings",), []),
    ],
)
def test_response_rejects_wrong_counts_statuses_and_extra_fields(
    location: tuple[str, ...], value: object
) -> None:
    data = analysis_data()
    target = data
    for key in location[:-1]:
        target = target[key]
    target[location[-1]] = value
    with pytest.raises(ValidationError):
        PlanAnalysis.model_validate(data)


def test_count_keys_and_resource_identity_are_required() -> None:
    data = analysis_data()
    del data["summary"]["by_action"]["unreported"]
    with pytest.raises(ValidationError):
        PlanAnalysis.model_validate(data)
    for key in ["address", "mode", "resource_type", "name", "provider_name"]:
        item = resource_data()
        del item[key]
        with pytest.raises(ValidationError):
            ResourceAnalysis.model_validate(item)


def test_warning_catalog_and_coverage_status_are_enforced() -> None:
    warning = {
        "code": "PLAN_INCOMPLETE",
        "message": WARNING_MESSAGES["PLAN_INCOMPLETE"],
        "count": None,
    }
    data = analysis_data()
    data.update(analysis_status="partial", warnings=[warning])
    assert PlanAnalysis.model_validate(data).analysis_status == "partial"
    for changes in [
        {"analysis_status": "complete"},
        {"warnings": [warning, warning]},
        {"warnings": [{**warning, "message": "UNTRUSTED_MESSAGE"}]},
        {"warnings": [{**warning, "count": 1}]},
    ]:
        with pytest.raises(ValidationError):
            PlanAnalysis.model_validate({**data, **changes})


def test_unreported_actions_require_a_matching_warning_count() -> None:
    data = analysis_data()
    data["resources"] = [
        resource_data(source="planned_values", actions=[], action_category="unreported")
    ]
    data["summary"]["changing_resources"] = 0
    data["summary"]["by_action"].update(replace=0, unreported=1)
    with pytest.raises(ValidationError, match="coverage warning"):
        PlanAnalysis.model_validate(data)
    warning = {
        "code": "CHANGE_ACTIONS_UNREPORTED",
        "message": WARNING_MESSAGES["CHANGE_ACTIONS_UNREPORTED"],
        "count": 1,
    }
    data.update(analysis_status="partial", warnings=[warning])
    assert PlanAnalysis.model_validate(data).summary.changing_resources == 0
    data["warnings"][0]["count"] = 2
    with pytest.raises(ValidationError, match="coverage warning"):
        PlanAnalysis.model_validate(data)


def test_warning_counts_and_unknown_codes_are_not_coerced() -> None:
    for count in [None, 0, -1, True, "1"]:
        with pytest.raises(ValidationError):
            AnalysisWarning(
                code="DEFERRED_CHANGES_PRESENT",
                message=WARNING_MESSAGES["DEFERRED_CHANGES_PRESENT"],
                count=count,
            )
    with pytest.raises(ValidationError):
        AnalysisWarning(code="UNKNOWN", message="SECRET")


def test_empty_response_has_all_zero_buckets_and_no_compliance_claims() -> None:
    data = analysis_data()
    data["resources"] = []
    data["summary"].update(total_resources=0, changing_resources=0, by_type={})
    data["summary"]["by_mode"] = {"managed": 0, "data": 0}
    data["summary"]["by_action"] = dict.fromkeys(data["summary"]["by_action"], 0)
    report = PlanAnalysis.model_validate(data)
    assert report.summary.total_resources == 0
    assert "compliance_status" not in report.model_dump()
    assert json.loads(report.model_dump_json())["resources"] == []


def test_report_rejects_duplicate_and_unsorted_addresses_and_warning_codes() -> None:
    data = analysis_data()
    data["resources"] *= 2
    with pytest.raises(ValidationError, match="unique, sorted"):
        PlanAnalysis.model_validate(data)
    data["resources"][0] = resource_data(address="z")
    data["resources"][1] = resource_data(address="a")
    with pytest.raises(ValidationError, match="unique, sorted"):
        PlanAnalysis.model_validate(data)
    data = analysis_data()
    data.update(
        analysis_status="partial",
        warnings=[
            {"code": code, "message": WARNING_MESSAGES[code]}
            for code in ["PLAN_INCOMPLETE", "PLAN_ERRORED"]
        ],
    )
    with pytest.raises(ValidationError, match="unique, sorted codes"):
        PlanAnalysis.model_validate(data)


def test_data_source_read_does_not_count_as_infrastructure_change() -> None:
    data = deepcopy(analysis_data())
    data["resources"][0].update(mode="data", actions=["read"], action_category="read")
    data["summary"]["by_action"].update(replace=0, read=1)
    data["summary"].update(changing_resources=0, by_mode={"managed": 0, "data": 1})
    assert PlanAnalysis.model_validate(data).summary.changing_resources == 0


def test_type_buckets_must_be_sorted_for_deterministic_output() -> None:
    data = analysis_data()
    data["resources"].append(resource_data(address="z", resource_type="aws_instance"))
    data["summary"].update(
        total_resources=2,
        changing_resources=2,
        by_type={"aws_instance": 1, "aws_db_instance": 1},
        by_mode={"managed": 2, "data": 0},
    )
    data["summary"]["by_action"]["replace"] = 2
    with pytest.raises(ValidationError, match="type counts must be sorted"):
        PlanAnalysis.model_validate(data)
    data["summary"]["by_type"] = {"aws_db_instance": 1, "aws_instance": 1}
    assert PlanAnalysis.model_validate(data).summary.total_resources == 2


def test_previously_valid_instances_are_revalidated_at_the_response_boundary() -> None:
    item = ResourceAnalysis.model_validate(resource_data())
    item.actions.append("delete")
    data = analysis_data()
    data["resources"] = [item]
    with pytest.raises(ValidationError):
        PlanAnalysis.model_validate(data)
