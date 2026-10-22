"""Required-key settings and closed tag variants need no OPA or filesystem."""

import pytest
from pydantic import TypeAdapter, ValidationError

from cloud_governance_mcp.config import EvaluationSettings, validate_evaluation_settings
from cloud_governance_mcp.errors import ConfigurationError
from cloud_governance_mcp.tag_models import TagConfiguration, TagProjection


@pytest.mark.parametrize(
    "keys",
    [
        [],
        [""],
        [" Owner"],
        ["Owner\n"],
        ["é"],
        [1],
        [True],
        ["aws:Owner"],
        ["AWS:Owner"],
        ["Owner", "Owner"],
        ["a" * 129],
        [f"k{i}" for i in range(51)],
    ],
)
def test_settings_reject_invalid_keys_with_fixed_error(keys):
    with pytest.raises(ConfigurationError) as failure:
        validate_evaluation_settings({"required_tag_keys": keys})
    assert "Owner" not in str(failure.value)


def test_defaults_override_sort_case_and_independent_lists():
    first, second = EvaluationSettings(), EvaluationSettings()
    assert first.required_tag_keys == ["Environment", "Owner", "Project"]
    first.required_tag_keys.append("extra")
    assert second.required_tag_keys == ["Environment", "Owner", "Project"]
    config = EvaluationSettings(required_tag_keys=["owner", "CostCenter", "Owner"])
    assert config.required_tag_keys == ["CostCenter", "Owner", "owner"]
    assert "CostCenter" not in repr(config)
    assert (
        len(
            TagConfiguration(
                required_tag_keys=[f"k{i}" for i in range(50)]
            ).required_tag_keys
        )
        == 50
    )
    assert TagConfiguration(required_tag_keys=["a" * 128]).required_tag_keys == [
        "a" * 128
    ]


@pytest.mark.parametrize(
    "projection",
    [
        {"source": "tags_all", "state": "missing"},
        {"source": "unresolved", "state": "null"},
        {"source": "tags", "state": "unknown", "entries": []},
        {"source": "tags", "state": "known", "entries": []},
        {
            "source": "tags",
            "state": "known",
            "entries": [{"key": "Owner", "state": "nonempty", "value": "secret"}],
        },
        {
            "source": "tags",
            "state": "known",
            "entries": [
                {"key": "Project", "state": "missing"},
                {"key": "Owner", "state": "missing"},
            ],
        },
        {
            "source": "tags",
            "state": "known",
            "entries": [
                {"key": "Owner", "state": "missing"},
                {"key": "Owner", "state": "unknown"},
            ],
        },
    ],
)
def test_projection_rejects_payload_and_variant_mismatches(projection):
    with pytest.raises(ValidationError):
        TypeAdapter(TagProjection).validate_python(projection, strict=True)
