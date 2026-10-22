"""Pure source selection, masks, observation privacy and bounded tag work."""

from copy import deepcopy

import pytest

import cloud_governance_mcp.tag_projection as module
from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.errors import AnalysisError
from cloud_governance_mcp.tag_models import DEFAULT_TAG_KEYS, TAG_TYPES


def project(plan):
    """Real adapter mask merging, with the prospective TAG parser isolated."""
    snapshot = TerraformPlanAdapter().normalize(plan)
    desired = {e["address"]: e["change"].get("after") for e in plan["resource_changes"]}
    result = module.project_tag_resources(
        snapshot.resources, desired, list(DEFAULT_TAG_KEYS)
    )
    return next(iter(result.values()))


@pytest.mark.parametrize(
    "value,state",
    [
        ("hello", "nonempty"),
        (" false ", "nonempty"),
        ("0", "nonempty"),
        ("é", "nonempty"),
        ("", "blank"),
        (" \n\t", "blank"),
        ("\u2003", "blank"),
        (None, "null"),
        (False, "invalid_type"),
        (1, "invalid_type"),
        ([], "invalid_type"),
        ({}, "invalid_type"),
    ],
)
def test_required_values_are_observations_never_raw_evidence(tag_plan, value, state):
    plan = tag_plan(
        {"tags_all": {"Owner": value, "UNREQUIRED_SECRET": "SENTINEL_VALUE"}}
    )
    before = deepcopy(plan)
    result = project(plan)
    assert [(e.key, e.state) for e in result.entries] == [
        ("Environment", "missing"),
        ("Owner", state),
        ("Project", "missing"),
    ]
    assert "SENTINEL" not in result.model_dump_json() + repr(result)
    assert plan == before


@pytest.mark.parametrize(
    "after,source,state",
    [
        ({}, "tags", "missing"),
        ({"tags": None}, "tags", "null"),
        ({"tags": []}, "tags", "invalid_type"),
        ({"tags": {}}, "tags", "known"),
        ({"tags_all": None, "tags": {"Owner": "team"}}, "tags_all", "null"),
        ({"tags_all": {}, "tags": {"Owner": "team"}}, "tags_all", "known"),
        ({"tags_all": False}, "tags_all", "invalid_type"),
    ],
)
def test_source_precedence_does_not_merge_or_bypass_null(
    tag_plan, after, source, state
):
    result = project(tag_plan(after))
    assert (result.source, result.state) == (source, state)
    if state == "known":
        assert all(e.state == "missing" for e in result.entries)


@pytest.mark.parametrize(
    "mask,expected",
    [
        (True, "unknown"),
        ({"tags_all": True}, "unknown"),
        ({"tags_all": {"Owner": True}}, "known"),
    ],
)
def test_root_map_and_key_unknown_masks(tag_plan, mask, expected):
    result = project(tag_plan(unknown=mask))
    assert result.state == expected
    if expected == "known":
        assert result.entries[1].state == "unknown"


@pytest.mark.parametrize("source", ["tags", "tags_all"])
@pytest.mark.parametrize(
    "mask", [True, {"Owner": True}, {"Owner": {"nested": True}}, [True]]
)
def test_sensitivity_crosses_duplicate_copies_before_reading(tag_plan, source, mask):
    result = project(tag_plan(sensitive={source: mask}))
    if mask is True or isinstance(mask, list):
        assert result.state == "sensitive"
    else:
        assert result.entries[1].state == "sensitive"


@pytest.mark.parametrize("value", [None, [], "bad"])
@pytest.mark.parametrize("kind", ["unknown", "sensitive"])
def test_descendant_masks_override_unusable_container_placeholders(
    tag_plan, value, kind
):
    result = project(
        tag_plan(
            {"tags_all": value, "tags": {"Owner": "team"}},
            **{kind: {"tags_all": {"Owner": True}}},
        )
    )
    assert (result.source, result.state) == ("tags_all", kind)


def test_omitted_masked_tags_all_never_falls_back_and_unrelated_known_keys_are_safe(
    tag_plan,
):
    result = project(
        tag_plan({"tags": {"Owner": "team"}}, unknown={"tags_all": {"Owner": True}})
    )
    assert (result.source, result.state) == ("tags_all", "unknown")
    result = project(
        tag_plan(
            unknown={"tags_all": {"unrelated": True}, "tags": True},
            sensitive={"tags": {"unrelated": True}},
        )
    )
    assert all(e.state == "nonempty" for e in result.entries)


@pytest.mark.parametrize("resource_type", TAG_TYPES)
def test_five_exact_types_are_supported(tag_plan, resource_type):
    assert project(tag_plan(resource_type=resource_type)).state == "known"


def test_unknown_metadata_and_unavailable_desired_are_not_known_absence(tag_plan):
    plan = tag_plan()
    del plan["resource_changes"][0]["change"]["after_unknown"]
    assert project(plan).state == "unverified"
    assert project(tag_plan(None)).state == "unavailable"


def test_work_is_bounded_before_desired_access(tag_plan, monkeypatch):
    snapshot = TerraformPlanAdapter().normalize(tag_plan())
    address = snapshot.resources[0].resource.address
    desired = {address: {"tags_all": {}}}
    monkeypatch.setattr(module, "MAX_TAG_KEY_SLOTS", 3)
    assert module.project_tag_resources(
        snapshot.resources, desired, list(DEFAULT_TAG_KEYS)
    )
    monkeypatch.setattr(module, "MAX_TAG_KEY_SLOTS", 2)
    with pytest.raises(AnalysisError) as failure:
        module.project_tag_resources(
            snapshot.resources, desired, list(DEFAULT_TAG_KEYS)
        )
    assert failure.value.code.value == "PLAN_LIMIT_EXCEEDED"
