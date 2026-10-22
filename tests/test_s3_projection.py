"""Pure S3 parsing, conservative links, strict contracts and privacy boundaries."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.errors import AnalysisError
from cloud_governance_mcp.evaluation_models import EvaluationInput
from cloud_governance_mcp.projection import to_evaluation_input
from cloud_governance_mcp.s3_models import S3_FLAGS, S3Block, S3Bucket

IDS = ["AWS-S3-001"]


def s3_plan(*, bucket=True, context=True):
    """Two synthetic resources plus only the configuration metadata we consume."""
    changes, config = [], []
    for kind, name, values in (
        ("aws_s3_bucket", "example", {"bucket": "SENTINEL_BUCKET_NAME"}),
        (
            "aws_s3_bucket_public_access_block",
            "protection",
            {"bucket": "SENTINEL_BUCKET_NAME", **dict.fromkeys(S3_FLAGS, True)},
        ),
    ):
        if kind == "aws_s3_bucket" and not bucket:
            continue
        changes.append(
            {
                "address": kind + "." + name,
                "type": kind,
                "name": name,
                "mode": "managed",
                "provider_name": "registry.terraform.io/hashicorp/aws",
                "change": {
                    "actions": ["create"],
                    "after": values,
                    "after_unknown": {},
                    "after_sensitive": {},
                },
            }
        )
        config.append(
            {
                "type": kind,
                "name": name,
                "mode": "managed",
                "provider_config_key": "SENTINEL_PROVIDER_CONTEXT",
                "address": kind + "." + name,
            }
        )
    plan = {
        "format_version": "1.2",
        "complete": True,
        "resource_changes": changes,
        "planned_values": {"root_module": {}},
    }
    if context:
        plan["configuration"] = {"root_module": {"resources": config}}
    return plan


def project(plan, **kwargs):
    """Exercise normalization and the strict graph boundary together."""
    snapshot = TerraformPlanAdapter(include_policy_values=True, **kwargs).normalize(
        plan, IDS
    )
    return to_evaluation_input(snapshot, IDS)


def bucket_projection(request):
    return next(
        r.s3_state for r in request.resources if r.resource_type == "aws_s3_bucket"
    )


def block_projection(request):
    return next(
        r.s3_state
        for r in request.resources
        if r.resource_type.endswith("public_access_block")
    )


def test_unique_known_names_need_shared_provider_context_and_discard_names():
    request = project(s3_plan())
    assert bucket_projection(request).state == "resolved"
    assert "SENTINEL" not in request.model_dump_json()
    assert request.schema_version == "5"
    assert all(f.state == "known" and f.value for f in block_projection(request).flags)


@pytest.mark.parametrize("field", S3_FLAGS)
@pytest.mark.parametrize(
    "value,state",
    [
        (True, "known"),
        (False, "known"),
        (None, "null"),
        (0, "invalid_type"),
        ("true", "invalid_type"),
        ([], "invalid_type"),
        ({}, "invalid_type"),
    ],
)
def test_strict_scalar_flag_states(field, value, state):
    plan = s3_plan()
    plan["resource_changes"][1]["change"]["after"][field] = value
    observation = block_projection(project(plan)).flags[S3_FLAGS.index(field)]
    assert observation.state == state
    if state != "known":
        assert "value" not in observation.model_dump()


@pytest.mark.parametrize("field", S3_FLAGS)
@pytest.mark.parametrize("mask", [True, {"child": True}, [True]])
@pytest.mark.parametrize(
    "source,state", [("after_sensitive", "sensitive"), ("after_unknown", "unknown")]
)
def test_scalar_descendant_masks_withhold_values(field, mask, source, state):
    plan = s3_plan()
    change = plan["resource_changes"][1]["change"]
    change["after"][field] = "SENTINEL_FLAG_VALUE"
    change[source] = {field: mask}
    result = project(plan)
    assert block_projection(result).flags[S3_FLAGS.index(field)].state == state
    assert "SENTINEL" not in result.model_dump_json()


@pytest.mark.parametrize(
    "source,state", [("after_sensitive", "sensitive"), ("after_unknown", "unknown")]
)
def test_root_masks_override_all_fields(source, state):
    plan = s3_plan()
    for r in plan["resource_changes"]:
        r["change"][source] = True
    request = project(plan)
    assert bucket_projection(request).state == state
    assert all(f.state == state for f in block_projection(request).flags)


@pytest.mark.parametrize(
    "value,state",
    [
        (None, "null"),
        (False, "invalid_type"),
        ("", "invalid_type"),
        ([], "invalid_type"),
    ],
)
def test_bad_bucket_link_values_do_not_resolve(value, state):
    plan = s3_plan()
    plan["resource_changes"][0]["change"]["after"]["bucket"] = value
    assert bucket_projection(project(plan)).state == state


@pytest.mark.parametrize(
    "case,state",
    [
        ("missing", "missing"),
        ("unknown", "unknown"),
        ("sensitive", "sensitive"),
        ("unverified", "unverified"),
        ("unavailable", "unavailable"),
        ("no_context", "context_unverified"),
        ("different_context", "context_unverified"),
        ("no_block", "not_found"),
        ("different_name", "not_found"),
        ("duplicate_block", "ambiguous"),
        ("duplicate_bucket", "ambiguous"),
        ("hidden_block", "context_unverified"),
        ("hidden_bucket", "context_unverified"),
    ],
)
def test_unproved_links_have_explicit_states(case, state):
    plan = s3_plan()
    r = plan["resource_changes"][0]
    change = r["change"]
    if case == "missing":
        change["after"].pop("bucket")
    elif case in {"sensitive", "unknown"}:
        change["after_" + case] = {"bucket": True}
    elif case == "unverified":
        change.pop("after_unknown")
    elif case == "unavailable":
        change["after"] = None
    elif case == "no_context":
        plan.pop("configuration")
    elif case == "different_context":
        plan["configuration"]["root_module"]["resources"][1]["provider_config_key"] = (
            "other"
        )
    elif case == "no_block":
        plan["resource_changes"].pop()
    elif case == "different_name":
        plan["resource_changes"][1]["change"]["after"]["bucket"] = "other"
    else:
        index = 1 if case.endswith("block") else 0
        extra = deepcopy(plan["resource_changes"][index])
        extra["address"] += "_other"
        extra["name"] += "_other"
        if case.startswith("hidden"):
            extra["change"]["after_unknown"] = {"bucket": True}
        plan["resource_changes"].append(extra)
    assert bucket_projection(project(plan)).state == state


def test_computed_expression_reference_cannot_prove_equality():
    plan = s3_plan()
    plan["resource_changes"][1]["change"]["after_unknown"] = {"bucket": True}
    plan["configuration"]["root_module"]["resources"][1]["expressions"] = {
        "bucket": {"references": ["aws_s3_bucket.example.id"]}
    }
    assert bucket_projection(project(plan)).state == "context_unverified"


@pytest.mark.parametrize("module", ["module.storage", "module.storage[0]"])
def test_explicit_tree_module_membership_without_address_parsing(module):
    plan = s3_plan()
    config = plan["configuration"]["root_module"]
    plan["configuration"]["root_module"] = {
        "module_calls": {"storage": {"module": config}}
    }
    for i, r in enumerate(plan["resource_changes"]):
        r["module_address"] = module
        r["address"] = "opaque-identity-" + str(i)
    assert bucket_projection(project(plan)).state == (
        "resolved" if module == "module.storage" else "context_unverified"
    )


def test_indexed_resources_in_unindexed_module_keep_exact_opaque_targets():
    plan = s3_plan()
    for i, r in enumerate(plan["resource_changes"]):
        r["index"] = i
        r["module_address"] = "module.storage"
        r["address"] = "opaque[" + str(i) + "]"
    config = plan["configuration"]["root_module"]
    plan["configuration"]["root_module"] = {
        "module_calls": {"storage": {"module": config}}
    }
    assert bucket_projection(project(plan)).block_address == "opaque[1]"


def test_order_does_not_change_links_and_deleted_duplicate_is_ignored():
    plan = s3_plan()
    extra = deepcopy(plan["resource_changes"][1])
    extra["address"] += "_deleted"
    extra["change"]["actions"] = ["delete"]
    extra["change"]["after"] = None
    plan["resource_changes"].append(extra)
    a = project(plan).model_dump()
    plan["resource_changes"].reverse()
    assert project(plan).model_dump() == a


def test_change_after_and_merged_inventory_masks_are_authoritative():
    plan = s3_plan()
    r = plan["resource_changes"][1]
    plan["planned_values"]["root_module"]["resources"] = [
        {
            **{k: v for k, v in r.items() if k != "change"},
            "values": dict.fromkeys(S3_FLAGS, True),
            "sensitive_values": {"block_public_acls": True},
        }
    ]
    r["change"]["after"] = {
        "bucket": "SENTINEL_BUCKET_NAME",
        "block_public_acls": False,
    }
    p = block_projection(project(plan))
    assert p.flags[0].state == "sensitive"
    assert all(f.state == "missing" for f in p.flags[1:])


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "wrong_kind",
        "dangling",
        "deleted",
        "wrong_provider",
        "wrong_type",
        "extra_unselected",
        "shared_target",
    ],
)
def test_engine_graph_rejects_invalid_s3_projection_or_target(mutation):
    document = project(s3_plan()).model_dump()
    bucket, block = document["resources"]
    if mutation == "missing":
        block["s3_state"] = None
    elif mutation == "wrong_kind":
        bucket["s3_state"] = deepcopy(block["s3_state"])
    elif mutation == "dangling":
        bucket["s3_state"]["block_address"] = "missing"
    elif mutation == "deleted":
        block["action_category"] = "delete"
    elif mutation == "wrong_provider":
        block["provider_name"] = "other"
    elif mutation == "wrong_type":
        block["resource_type"] = "aws_s3_bucket_policy"
    elif mutation == "shared_target":
        document["resources"].append({**deepcopy(bucket), "address": "another_bucket"})
    else:
        document["selected_policy_ids"] = ["AWS-RDS-001"]
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(document)


@pytest.mark.parametrize(
    "payload", [{"state": "resolved"}, {"state": "unknown", "block_address": "guessed"}]
)
def test_uncertain_link_never_retains_guessed_target(payload):
    with pytest.raises(ValidationError):
        S3Bucket.model_validate(payload)


@pytest.mark.parametrize("count", [0, 3, 5])
def test_flag_count_cannot_silently_omit_checks(count):
    with pytest.raises(ValidationError):
        S3Block(flags=[{"state": "known", "value": True}] * count)


def test_selected_configuration_validation_and_limits_do_not_affect_analysis():
    plan = s3_plan()
    plan["configuration"] = "SENTINEL_INVALID"
    TerraformPlanAdapter().normalize(plan)
    TerraformPlanAdapter(include_policy_values=True).normalize(plan, ["AWS-RDS-001"])
    with pytest.raises(AnalysisError) as failure:
        project(plan)
    assert failure.value.code.value == "INVALID_PLAN" and "SENTINEL" not in str(
        failure.value
    )
    plan = s3_plan()
    plan["configuration"]["root_module"]["resources"] *= 2
    with pytest.raises(AnalysisError) as failure:
        project(plan, max_resources=2)
    assert failure.value.code.value == "PLAN_LIMIT_EXCEEDED"
    plan = s3_plan()
    plan["configuration"]["root_module"] = {
        "module_calls": {"x": {"module": {"module_calls": {"y": {"module": {}}}}}}
    }
    with pytest.raises(AnalysisError) as failure:
        project(plan, max_depth=2)
    assert failure.value.code.value == "PLAN_LIMIT_EXCEEDED"


def test_missing_module_metadata_is_not_implicitly_root():
    plan = s3_plan()
    for i, resource in enumerate(plan["resource_changes"]):
        resource["address"] = "opaque-missing-membership-" + str(i)
    assert bucket_projection(project(plan)).state == "context_unverified"


@pytest.mark.parametrize("case", ["duplicate", "missing", "null", "invalid"])
def test_incomplete_configuration_metadata_cannot_prove_provider_context(case):
    plan = s3_plan()
    entries = plan["configuration"]["root_module"]["resources"]
    if case == "duplicate":
        entries.append(deepcopy(entries[0]))
    elif case == "missing":
        entries[0].pop("provider_config_key")
    elif case == "null":
        entries[0]["provider_config_key"] = None
    else:
        entries[0]["provider_config_key"] = {"SENTINEL": "SECRET"}
    request = project(plan)
    assert bucket_projection(request).state == "context_unverified"
    assert "SENTINEL" not in request.model_dump_json()


@pytest.mark.parametrize(
    "case",
    [
        "schema",
        "version",
        "severity",
        "types",
        "configuration",
        "path",
        "reason",
        "outcome",
    ],
)
def test_catalog_rejects_invalid_s3_metadata_and_reason_semantics(case):
    from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog

    document = load_catalog().model_dump()
    policy = next(p for p in document["policies"] if p["policy_id"] == "AWS-S3-001")
    if case == "schema":
        document["schema_version"] = "5"
    elif case == "version":
        policy["policy_version"] = "1.1.0"
    elif case == "severity":
        policy["severity"] = "medium"
    elif case == "types":
        policy["supported_resource_types"] = ["aws_s3_bucket_policy", "aws_s3_bucket"]
    elif case == "configuration":
        policy["required_configuration"] = ["required_tag_keys"]
    elif case == "path":
        policy["reasons"]["S3_BUCKET_ENABLED"]["attribute_path"] = []
    elif case == "reason":
        policy["reasons"].pop("S3_LINK_AMBIGUOUS")
    else:
        policy["reasons"]["S3_LINK_NOT_FOUND"]["outcome"] = "pass"
    with pytest.raises(ValidationError):
        PolicyCatalog.model_validate(document)


@pytest.mark.parametrize(
    "actions",
    [["create"], ["update"], ["no-op"], ["delete", "create"], ["create", "delete"]],
)
def test_supported_action_orders_keep_s3_projection(actions):
    plan = s3_plan()
    for resource in plan["resource_changes"]:
        resource["change"]["actions"] = actions
    assert bucket_projection(project(plan)).state == "resolved"


def test_inventory_only_does_not_manufacture_complete_unknown_metadata():
    plan = s3_plan()
    inventory = []
    for resource in plan.pop("resource_changes"):
        inventory.append(
            {
                **{k: v for k, v in resource.items() if k != "change"},
                "values": resource["change"]["after"],
                "sensitive_values": {},
            }
        )
    plan["planned_values"]["root_module"]["resources"] = inventory
    request = project(plan)
    assert bucket_projection(request).state == "unverified"
    assert all(flag.state == "unverified" for flag in block_projection(request).flags)
