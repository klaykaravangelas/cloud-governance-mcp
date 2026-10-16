"""Exercise untrusted input and operator settings without reading any files."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from cloud_governance_mcp.config import AnalysisSettings, validate_analysis_settings
from cloud_governance_mcp.errors import (
    ERROR_MESSAGES,
    AnalysisError,
    ConfigurationError,
    ErrorCode,
)
from cloud_governance_mcp.models import (
    AnalyzeTerraformPlanInput,
    validate_analysis_input,
)


@pytest.mark.parametrize(
    "path",
    [
        "plans/example.json",
        "/allowed/plan",
        " a plan with spaces.json ",
        "~/plan.json",
        "$PLAN_DIR/plan.json",
        "../plan.json",  # Containment is a loader responsibility, not URI syntax.
        "p" * 4096,
    ],
)
def test_valid_paths_are_preserved_without_expansion(path: str) -> None:
    assert validate_analysis_input({"plan_path": path}).plan_path == path


@pytest.mark.parametrize(
    "value",
    [
        {},
        None,
        [],
        {"plan_path": 1},
        {"plan_path": True},
        {"plan_path": b"plan.json"},
        {"plan_path": Path("plan.json")},
        {"plan_path": ""},
        {"plan_path": "  "},
        {"plan_path": "p" * 4097},
        {"plan_path": "plan\x00.json"},
        {"plan_path": "plan\n.json"},
        {"plan_path": "plan\x7f.json"},
        {"plan_path": "plan\x85.json"},
        {"plan_path": "plan\ud800.json"},
        {"plan_path": "file:/allowed/plan.json"},
        {"plan_path": "file:///allowed/plan.json"},
        {"plan_path": "https://example.com/plan.json"},
        {"plan_path": "s3://bucket/plan.json"},
        {"plan_path": "plan.json", "command": "ignored"},
    ],
)
def test_invalid_input_has_a_stable_public_error(value: object) -> None:
    with pytest.raises(AnalysisError) as caught:
        validate_analysis_input(value)
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT
    assert str(caught.value) == "INVALID_ARGUMENT: Invalid analysis arguments."


@pytest.mark.parametrize(
    "value",
    [
        {"plan_path": {"INPUT_SECRET": "value"}},
        {"plan_path": "file:///INPUT_SECRET"},
        {"plan_path": "plan.json", "INPUT_SECRET": "value"},
    ],
)
def test_rejected_values_and_extra_field_names_are_not_public(
    value: object, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(AnalysisError) as caught:
        validate_analysis_input(value)
    assert "INPUT_SECRET" not in str(caught.value)
    assert "INPUT_SECRET" not in repr(caught.value)
    assert caplog.records == []


def test_input_schema_forbids_extras_and_repr_hides_path() -> None:
    schema = AnalyzeTerraformPlanInput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["plan_path"]
    path_schema = schema["properties"]["plan_path"]
    if "$ref" in path_schema:
        path_schema = schema["$defs"][path_schema["$ref"].rsplit("/", 1)[1]]
    assert path_schema["maxLength"] == 4096
    value = validate_analysis_input({"plan_path": "PRIVATE_PATH"})
    assert "PRIVATE_PATH" not in repr(value)


def test_configuration_preserves_roots_without_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_stat(*args: object, **kwargs: object) -> None:
        pytest.fail("Settings must not access the filesystem.")

    monkeypatch.setattr(Path, "stat", unexpected_stat)
    settings = validate_analysis_settings({"allowed_roots": ["/first", "/second"]})
    assert settings.allowed_roots == ["/first", "/second"]
    assert settings.max_plan_bytes == 10_485_760
    assert settings.max_json_depth == 128
    assert settings.max_resources == 10_000
    assert settings.max_analysis_bytes == 4_194_304
    assert "/first" not in repr(settings)


@pytest.mark.parametrize("roots", [None, [], ["relative"], ["~/plans"], [1], "/plans"])
def test_configuration_requires_an_explicit_list_of_absolute_roots(
    roots: object,
) -> None:
    with pytest.raises(ConfigurationError, match="^Invalid analysis configuration.$"):
        validate_analysis_settings({"allowed_roots": roots})
    with pytest.raises(ConfigurationError):
        validate_analysis_settings({})


@pytest.mark.parametrize(
    "field",
    ["max_plan_bytes", "max_json_depth", "max_resources", "max_analysis_bytes"],
)
@pytest.mark.parametrize("value", [0, -1, True, 1.0, "10", None])
def test_limits_require_positive_strict_integers(field: str, value: object) -> None:
    with pytest.raises(ConfigurationError):
        validate_analysis_settings({"allowed_roots": ["/plans"], field: value})


def test_configuration_override_and_safe_failures() -> None:
    settings = validate_analysis_settings(
        {"allowed_roots": ["/plans"], "max_plan_bytes": 1}
    )
    assert settings.max_plan_bytes == 1
    with pytest.raises(ConfigurationError) as caught:
        validate_analysis_settings({"allowed_roots": ["CONFIG_SECRET/relative"]})
    assert "CONFIG_SECRET" not in str(caught.value)
    assert "CONFIG_SECRET" not in repr(caught.value)
    with pytest.raises(ConfigurationError):
        validate_analysis_settings({"allowed_roots": ["/plans"], "opa_path": "/opa"})


def test_internal_validation_errors_hide_values_but_are_not_public_errors() -> None:
    with pytest.raises(ValidationError) as caught:
        AnalysisSettings.model_validate(
            {"allowed_roots": ["/plans"], "max_plan_bytes": "CONFIG_SECRET"}
        )
    assert "CONFIG_SECRET" not in str(caught.value)
    # errors() is intentionally internal; the boundary must not return it.
    assert "input" not in caught.value.errors(include_input=False)[0]


def test_all_error_codes_have_fixed_explanations() -> None:
    assert set(ErrorCode) == set(ERROR_MESSAGES)
    for code in ErrorCode:
        error = AnalysisError(code)
        assert str(error) == f"{code.value}: {ERROR_MESSAGES[code]}"
        assert error.args == (str(error),)
    with pytest.raises(TypeError, match="known error code"):
        AnalysisError("INPUT_SECRET")  # type: ignore[arg-type]
