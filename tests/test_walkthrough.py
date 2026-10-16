"""Verify the commands users follow, including the saved example MCP response."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cloud_governance_mcp.models import PlanAnalysis

REPOSITORY = Path(__file__).resolve().parent.parent
CLIENT = REPOSITORY / "examples" / "client.py"
REPORT = REPOSITORY / "examples" / "reports" / "mixed-analysis.json"


def invoke(arguments: list[str], directory: Path) -> subprocess.CompletedProcess[str]:
    """Run the actual example outside the checkout without runtime binaries."""
    return subprocess.run(
        [sys.executable, "-I", str(CLIENT), *arguments],
        cwd=directory,
        env={**os.environ, "PATH": ""},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize("arguments", [[], ["--legacy"]])
def test_default_walkthrough_matches_the_saved_public_report(
    arguments: list[str], tmp_path: Path
) -> None:
    result = invoke(arguments, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    expected = json.loads(REPORT.read_text())
    actual = json.loads(result.stdout)
    assert actual == expected
    report = PlanAnalysis.model_validate(actual)
    assert report.summary.total_resources == 7
    assert report.summary.changing_resources == 4
    assert report.analysis_status == "partial"
    assert "SENTINEL_" not in result.stdout
    assert "unknown_paths" not in result.stdout


def test_walkthrough_lists_the_one_implemented_tool(tmp_path: Path) -> None:
    result = invoke(["--list-tools"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == ["analyze_terraform_plan"]


@pytest.mark.parametrize(
    ("filename", "total", "status"),
    [
        ("empty.json", 0, "complete"),
        ("encrypted_rds.json", 1, "complete"),
        ("unknown_sensitive.json", 2, "partial"),
        ("partial.json", 1, "partial"),
    ],
)
def test_walkthrough_fixture_exercises(
    filename: str, total: int, status: str, tmp_path: Path
) -> None:
    result = invoke(["--plan-path", filename], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = PlanAnalysis.model_validate_json(result.stdout)
    assert report.summary.total_resources == total
    assert report.analysis_status == status
    assert "SENTINEL_" not in result.stdout


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        (
            "malformed.json",
            "INVALID_PLAN: The document is not a valid supported Terraform plan.",
        ),
        (
            "../SENTINEL_DENIED.json",
            "PATH_NOT_ALLOWED: The requested path is not allowed.",
        ),
        (
            "SENTINEL_MISSING.json",
            "PLAN_FILE_UNAVAILABLE: The plan file is unavailable.",
        ),
    ],
)
def test_walkthrough_errors_have_nonzero_exit_and_only_safe_stderr(
    filename: str, message: str, tmp_path: Path
) -> None:
    result = invoke(["--plan-path", filename], tmp_path)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == message + "\n"
    assert "SENTINEL_" not in result.stderr
