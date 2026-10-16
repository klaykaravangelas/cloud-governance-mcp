"""Test plan interpretation without files, MCP, cloud APIs or provider schemas."""

import copy
import json
from pathlib import Path

import pytest

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.errors import AnalysisError, ConfigurationError, ErrorCode
from cloud_governance_mcp.models import WARNING_MESSAGES, ResourceSnapshot

FIXTURES = Path(__file__).parent / "fixtures" / "plans"


def resource(address: str = "terraform_data.example", **fields: object) -> dict:
    """Return a minimal synthetic identity, with overrides for boundary cases."""
    return {
        "address": address,
        "mode": "managed",
        "type": "terraform_data",
        "name": "example",
        "provider_name": "terraform.io/builtin/terraform",
        **fields,
    }


def change(address: str = "terraform_data.example", **fields: object) -> dict:
    return resource(address, change={"actions": ["create"]}, **fields)


def plan(*changes: dict, inventory: list | None = None, **fields: object) -> dict:
    """Both sources are available by default, isolating each test's warnings."""
    return {
        "format_version": "1.2",
        "complete": True,
        "resource_changes": list(changes),
        "planned_values": {"root_module": {"resources": inventory or []}},
        **fields,
    }


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def normalize(document: object) -> ResourceSnapshot:
    return TerraformPlanAdapter().normalize(document)


def assert_error(document: object, code: ErrorCode = ErrorCode.INVALID_PLAN) -> None:
    with pytest.raises(AnalysisError) as failure:
        normalize(document)
    assert failure.value.code == code


def test_mixed_fixture_preserves_actions_provenance_and_nested_identity() -> None:
    snapshot = normalize(load_fixture("mixed_nested.json"))
    records = {item.resource.address: item.resource for item in snapshot.resources}
    assert list(records) == sorted(records)
    assert len(records) == 7
    assert sorted(item.action_category for item in records.values()) == [
        "create",
        "delete",
        "no_op",
        "read",
        "replace",
        "unreported",
        "update",
    ]
    assert sum(item.mode == "data" for item in records.values()) == 1
    assert records["aws_instance.old"].source == "resource_changes"
    assert records["aws_s3_bucket.new"].source == "both"
    nested = records['module.database.module.storage["a.b"].aws_db_instance.example[0]']
    assert nested.module_address == 'module.database.module.storage["a.b"]'
    assert nested.index == 0
    assert nested.actions == ["delete", "create"]
    inventory = records['google_storage_bucket.archive["a.b"]']
    assert inventory.index == "a.b"
    assert inventory.source == "planned_values"
    assert inventory.actions == []
    assert [(warning.code, warning.count) for warning in snapshot.warnings] == [
        ("CHANGE_ACTIONS_UNREPORTED", 1)
    ]


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
def test_actions_remain_ordered(actions: list[str], category: str) -> None:
    entry = change()
    entry["change"] = {"actions": actions, "before": None, "after": None}
    record = normalize(plan(entry)).resources[0].resource
    assert record.actions == actions
    assert record.action_category == category


@pytest.mark.parametrize("key", [0, 42, "", "a.b", 'quoted"key'])
def test_opaque_instance_keys_and_moved_metadata(key: int | str) -> None:
    address = f"module.child.terraform_data.example[{json.dumps(key)}]"
    entry = change(address, index=key, previous_address="terraform_data.previous")
    record = normalize(plan(entry)).resources[0].resource
    assert record.address == address
    assert record.index == key and type(record.index) is type(key)
    assert record.previous_address == "terraform_data.previous"
    # A change-only address does not establish membership by its spelling.
    assert record.module_address is None


@pytest.mark.parametrize("key", ["index", "previous_address"])
def test_missing_optional_change_metadata_is_filled_from_inventory(key: str) -> None:
    value = 0 if key == "index" else "terraform_data.previous"
    record = (
        normalize(plan(change(), inventory=[resource(**{key: value})]))
        .resources[0]
        .resource
    )
    assert getattr(record, key) == value
    assert record.source == "both"


def test_inventory_alone_does_not_imply_known_values_or_no_op() -> None:
    item = normalize(plan(inventory=[resource()])).resources[0]
    assert item.resource.action_category == "unreported"
    assert not item.unknown_metadata_complete
    assert item.unknown_paths == []


def test_mask_projection_unions_sensitivity_and_discards_all_attribute_values(
    caplog,
) -> None:
    document = load_fixture("unknown_sensitive.json")
    snapshot = normalize(document)
    nested, whole = snapshot.resources
    assert nested.unknown_paths == [["endpoints", 1, "address"], ["identifier"]]
    assert nested.sensitive_paths == [["credentials"]]
    assert nested.unknown_metadata_complete
    assert whole.unknown_paths == [[]]
    assert whole.sensitive_paths == [[]]
    assert whole.unknown_metadata_complete
    assert "SENTINEL_" not in snapshot.model_dump_json()
    assert "SENTINEL_" not in repr(snapshot)
    assert caplog.text == ""
    assert "SENTINEL_MARKED_SECRET" in json.dumps(document)  # Input remains untouched.


@pytest.mark.parametrize("present", [True, False])
def test_missing_unknown_mask_is_distinct_from_explicit_known_mask(
    present: bool,
) -> None:
    entry = change()
    if present:
        entry["change"]["after_unknown"] = {}
    item = normalize(plan(entry)).resources[0]
    assert item.unknown_paths == []
    assert item.unknown_metadata_complete is present


def test_source_and_module_order_permutations_are_deterministic_and_nonmutating() -> (
    None
):
    original = load_fixture("mixed_nested.json")
    shuffled = copy.deepcopy(original)
    shuffled["resource_changes"].reverse()
    root = shuffled["planned_values"]["root_module"]
    root["resources"].reverse()
    root["child_modules"].append({"address": "module.empty", "resources": []})
    expected = copy.deepcopy(shuffled)
    assert normalize(original) == normalize(shuffled)
    assert shuffled == expected


def test_empty_and_additive_plans_keep_safe_metadata() -> None:
    snapshot = normalize(load_fixture("empty.json"))
    assert snapshot.resources == snapshot.warnings == []
    minimal = normalize(
        {"format_version": "1.999", "planned_values": {}, "complete": True}
    )
    assert minimal.format_version == "1.999"
    assert minimal.terraform_version is None
    assert minimal.resources == minimal.warnings == []
    changes_only = normalize({"format_version": "1.0", "resource_changes": []})
    assert [warning.code for warning in changes_only.warnings] == [
        "PLANNED_VALUES_UNAVAILABLE",
        "PLAN_COMPLETENESS_UNSPECIFIED",
    ]
    assert normalize(plan(unknown_additive={"secret": object()})).resources == []


def test_partial_coverage_warnings_are_sorted_counted_and_fixed(caplog) -> None:
    snapshot = normalize(load_fixture("partial.json"))
    assert len(snapshot.resources) == 1
    assert snapshot.resources[0].resource.actions == ["no-op"]
    assert [(warning.code, warning.count) for warning in snapshot.warnings] == [
        ("DEFERRED_CHANGES_PRESENT", 2),
        ("IMPORTS_NOT_SUMMARIZED", 1),
        ("OUTPUT_CHANGES_NOT_SUMMARIZED", 1),
        ("PLANNED_VALUES_UNAVAILABLE", None),
        ("PLAN_ERRORED", None),
        ("PLAN_INCOMPLETE", None),
        ("RESOURCE_DRIFT_NOT_ANALYZED", 1),
    ]
    for warning in snapshot.warnings:
        assert warning.message == WARNING_MESSAGES[warning.code]
    assert "SENTINEL_" not in snapshot.model_dump_json()
    assert caplog.text == ""


def test_import_warning_counts_changes_and_uses_nested_change_metadata() -> None:
    first, second = change("terraform_data.first"), change("terraform_data.second")
    for entry in (first, second):
        entry["change"]["importing"] = {"opaque": None}
    snapshot = normalize(plan(first, second, importing={"ignored": True}))
    assert [(warning.code, warning.count) for warning in snapshot.warnings] == [
        ("IMPORTS_NOT_SUMMARIZED", 2)
    ]


@pytest.mark.parametrize("name", ["encrypted_rds.json", "unencrypted_rds.json"])
def test_analysis_has_no_compliance_decision(name: str) -> None:
    snapshot = normalize(load_fixture(name))
    assert snapshot.resources[0].resource.action_category == "create"
    assert "storage_encrypted" not in snapshot.model_dump_json()
    assert "compliance" not in snapshot.model_dump_json()


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {},
        {"format_version": "1.0"},
        {"format_version": "1.0", "values": {}, "resource_changes": []},
        {"format_version": "1.0", "resource_changes": None},
        {"format_version": "1.0", "planned_values": []},
    ],
)
def test_invalid_envelopes(document: object) -> None:
    assert_error(document)


@pytest.mark.parametrize(
    "version", [None, 1, "", "1", "v1.0", "1.0.0", "1.-1", "1.0\n"]
)
def test_malformed_versions(version: object) -> None:
    assert_error(plan(format_version=version))


@pytest.mark.parametrize("version", ["0.1", "2.0", "99.9"])
def test_unsupported_major_versions(version: str) -> None:
    assert_error(plan(format_version=version), ErrorCode.UNSUPPORTED_PLAN_VERSION)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("complete", 1),
        ("complete", None),
        ("errored", "false"),
        ("errored", None),
        ("terraform_version", None),
        ("terraform_version", ""),
        ("deferred_changes", {}),
        ("deferred_changes", None),
        ("resource_drift", {}),
        ("resource_drift", None),
        ("output_changes", []),
        ("output_changes", None),
        ("resource_changes", {}),
        ("planned_values", None),
    ],
)
def test_invalid_consumed_envelope_fields(field: str, value: object) -> None:
    assert_error(plan(**{field: value}))


@pytest.mark.parametrize("field", ["address", "mode", "type", "name", "provider_name"])
@pytest.mark.parametrize("value", [None, "", 1])
def test_missing_or_malformed_resource_identity(field: str, value: object) -> None:
    entry = change()
    del entry[field]
    assert_error(plan(entry))
    entry[field] = value
    assert_error(plan(entry))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "ephemeral"),
        ("index", True),
        ("index", -1),
        ("index", 0.0),
        ("index", None),
        ("module_address", None),
        ("previous_address", None),
        ("module_address", ""),
        ("previous_address", ""),
        ("name", "secret\nname"),
        ("name", "\ud800"),
    ],
)
def test_invalid_optional_or_unsafe_identities(field: str, value: object) -> None:
    assert_error(plan(change(**{field: value})))


@pytest.mark.parametrize(
    "field",
    [
        "change",
        "before",
        "after",
        "before_sensitive",
        "after_sensitive",
        "after_unknown",
        "importing",
    ],
)
@pytest.mark.parametrize("value", ["SENTINEL_REJECTED_SECRET", None])
def test_change_structures_validate_types(field: str, value: object, caplog) -> None:
    entry = change()
    if field == "change":
        entry[field] = value
    else:
        entry["change"][field] = value
    if field in {"before", "after"} and value is None:
        assert len(normalize(plan(entry)).resources) == 1
    else:
        assert_error(plan(entry))
    assert caplog.text == ""


@pytest.mark.parametrize("actions", [None, [], "create", [1], [True], [{}]])
def test_malformed_actions_are_invalid(actions: object) -> None:
    entry = change()
    entry["change"]["actions"] = actions
    assert_error(plan(entry))


@pytest.mark.parametrize(
    "actions",
    [
        ["forget"],
        ["create", "update"],
        ["create", "create"],
        ["create", "delete", "create"],
    ],
)
def test_unknown_actions_are_unsupported(actions: list[str]) -> None:
    entry = change()
    entry["change"]["actions"] = actions
    assert_error(plan(entry), ErrorCode.UNSUPPORTED_PLAN_FEATURE)


@pytest.mark.parametrize("value", [None, "", 0, "synthetic-deposed-key"])
def test_deposed_objects_are_never_collapsed(value: object) -> None:
    code = (
        ErrorCode.UNSUPPORTED_PLAN_FEATURE
        if isinstance(value, str) and value
        else ErrorCode.INVALID_PLAN
    )
    assert_error(plan(change(deposed=value)), code)


@pytest.mark.parametrize("field", ["root_module", "resources", "child_modules"])
@pytest.mark.parametrize("value", [None, "SENTINEL_MODULE_SECRET"])
def test_malformed_module_containers(field: str, value: object) -> None:
    document = plan()
    if field == "root_module":
        document["planned_values"][field] = value
    else:
        document["planned_values"]["root_module"][field] = value
    assert_error(document)


@pytest.mark.parametrize("child", [{}, {"address": None}, {"address": ""}, None])
def test_children_require_valid_module_addresses(child: object) -> None:
    document = plan()
    document["planned_values"]["root_module"]["child_modules"] = [child]
    assert_error(document)


def test_duplicate_module_addresses_across_branches_fail() -> None:
    document = plan()
    document["planned_values"]["root_module"]["child_modules"] = [
        {"address": "module.a", "child_modules": [{"address": "module.duplicate"}]},
        {"address": "module.b", "child_modules": [{"address": "module.duplicate"}]},
    ]
    assert_error(document)


def test_duplicate_resources_in_either_source_fail() -> None:
    assert_error(plan(change(), change()))
    assert_error(plan(inventory=[resource(), resource()]))
    document = plan(inventory=[resource()])
    document["planned_values"]["root_module"]["child_modules"] = [
        {"address": "module.child", "resources": [resource()]}
    ]
    assert_error(document)


@pytest.mark.parametrize(
    ("field", "left", "right"),
    [
        ("mode", "managed", "data"),
        ("type", "a", "b"),
        ("name", "a", "b"),
        ("provider_name", "a", "b"),
        ("index", 0, "0"),
        ("previous_address", "old.a", "old.b"),
        ("module_address", "module.child", None),
    ],
)
def test_cross_source_conflicts_fail(field: str, left: object, right: object) -> None:
    inventory = resource(**({field: right} if right is not None else {}))
    assert_error(plan(change(**{field: left}), inventory=[inventory]))


def test_inventory_explicit_module_must_agree_with_containing_tree() -> None:
    assert_error(plan(inventory=[resource(module_address="module.child")]))


@pytest.mark.parametrize("field", ["values", "sensitive_values"])
def test_inventory_payload_shapes_are_checked(field: str) -> None:
    assert_error(plan(inventory=[resource(**{field: "SENTINEL_INVENTORY_SECRET"})]))
    if field == "values":
        assert normalize(plan(inventory=[resource(values=None)])).resources
    else:
        assert_error(plan(inventory=[resource(sensitive_values=None)]))


def test_resource_limits_apply_to_each_source_and_the_union() -> None:
    adapter = TerraformPlanAdapter(max_resources=1)
    assert len(adapter.normalize(plan(change(), inventory=[resource()])).resources) == 1
    documents = [
        plan(change("terraform_data.a"), change("terraform_data.b")),
        plan(inventory=[resource("terraform_data.a"), resource("terraform_data.b")]),
        plan(change("terraform_data.a"), inventory=[resource("terraform_data.b")]),
        plan(change(), change()),  # Count the raw source before deduplication.
    ]
    nested = plan(inventory=[resource("terraform_data.a")])
    nested["planned_values"]["root_module"]["child_modules"] = [
        {"address": "module.child", "resources": [resource("terraform_data.b")]}
    ]
    documents.append(nested)
    for document in documents:
        with pytest.raises(AnalysisError) as failure:
            adapter.normalize(document)
        assert failure.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED


@pytest.mark.parametrize(
    "field",
    [
        "address",
        "type",
        "name",
        "provider_name",
        "index",
        "module_address",
        "previous_address",
    ],
)
def test_identity_length_limit(field: str) -> None:
    assert normalize(plan(change(**{field: "x" * 2048}))).resources
    assert_error(plan(change(**{field: "x" * 2049})), ErrorCode.PLAN_LIMIT_EXCEEDED)


def test_direct_call_module_and_mask_depth_guards() -> None:
    adapter = TerraformPlanAdapter(max_depth=1)
    document = plan()
    document["planned_values"]["root_module"]["child_modules"] = [
        {"address": "module.child"}
    ]
    entry = change()
    entry["change"]["after_unknown"] = {"nested": {"secret": True}}
    for invalid in (document, plan(entry)):
        with pytest.raises(AnalysisError) as failure:
            adapter.normalize(invalid)
        assert failure.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED
    entry["change"]["after_unknown"] = {"secret": True}
    assert adapter.normalize(plan(entry)).resources[0].unknown_paths == [["secret"]]


@pytest.mark.parametrize("field", ["max_resources", "max_depth"])
@pytest.mark.parametrize("value", [0, -1, True, "1", 1.0])
def test_adapter_configuration_is_strict(field: str, value: object) -> None:
    with pytest.raises(ConfigurationError):
        TerraformPlanAdapter(**{field: value})


def test_rejected_secret_keys_and_values_are_absent_from_errors_and_logs(
    caplog,
) -> None:
    documents = [
        plan(change(mode="SENTINEL_REJECTED_MODE")),
        plan(change(index={"SENTINEL_REJECTED_KEY": "SENTINEL_REJECTED_VALUE"})),
        plan(change(name="SENTINEL_REJECTED_NAME\n")),
    ]
    for document in documents:
        with pytest.raises(AnalysisError) as failure:
            normalize(document)
        assert failure.value.code == ErrorCode.INVALID_PLAN
        assert "SENTINEL_" not in str(failure.value)
        assert "SENTINEL_" not in repr(failure.value)
        assert failure.value.__suppress_context__
    assert caplog.text == ""
