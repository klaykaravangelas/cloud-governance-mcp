"""Require real pinned OPA for policy execution and capability-denial evidence."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "cloud_governance_mcp" / "policies"


@pytest.fixture
def opa_path() -> Path:
    """Local development pin or an explicit test-only operator override."""
    path = Path(os.environ.get("CLOUD_GOVERNANCE_OPA", ROOT / ".tools/opa/1.21.2/opa"))
    if not path.is_file():
        pytest.fail(
            "Real OPA is required; follow docs/opa-setup.md. No tests were skipped."
        )
    return path.resolve()


def run_opa(opa_path: Path, *args: str, input: str | None = None):
    """Tests may load test policies; production always fixes its own asset paths."""
    return subprocess.run(
        [str(opa_path), *args],
        input=input,
        capture_output=True,
        text=True,
        timeout=15,
        env={"LANG": "C", "LC_ALL": "C"},
    )


def test_pinned_runtime_strict_compile_format_and_real_rego_tests(opa_path) -> None:
    assert "Version: 1.21.2\n" in run_opa(opa_path, "version").stdout
    for args in [
        [
            "check",
            "--strict",
            "--capabilities",
            str(ASSETS / "capabilities.json"),
            str(ASSETS / "rego"),
        ],
        ["fmt", "--fail", str(ASSETS / "rego"), str(ROOT / "tests/policies")],
        [
            "test",
            "--capabilities",
            str(ASSETS / "capabilities.json"),
            str(ASSETS / "rego"),
            str(ASSETS / "catalog.json"),
            str(ROOT / "tests/policies"),
        ],
    ]:
        result = run_opa(opa_path, *args)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "expression",
    ['http.send({"method":"GET","url":"https://example.invalid"})', "opa.runtime()"],
)
def test_capabilities_reject_network_and_runtime_builtins(
    opa_path, tmp_path, expression
) -> None:
    policy = tmp_path / "forbidden.rego"
    policy.write_text(
        "package forbidden\nimport rego.v1\nvalue := " + expression + "\n"
    )
    result = run_opa(
        opa_path,
        "check",
        "--strict",
        "--capabilities",
        str(ASSETS / "capabilities.json"),
        str(policy),
    )
    assert result.returncode != 0
    assert "undefined function" in result.stderr


def test_remote_schema_fetch_is_denied_before_network_access(
    opa_path, tmp_path
) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"$ref": "https://example.invalid/schema.json"}))
    policy = tmp_path / "schema_policy.rego"
    policy.write_text("package schema_policy\nimport rego.v1\nvalue := input.value\n")
    result = run_opa(
        opa_path,
        "check",
        "--strict",
        "--capabilities",
        str(ASSETS / "capabilities.json"),
        "--schema",
        str(schema),
        str(policy),
    )
    assert result.returncode != 0
    assert "example.invalid" in result.stdout + result.stderr
    assert "remote reference loading disabled" in result.stdout + result.stderr
