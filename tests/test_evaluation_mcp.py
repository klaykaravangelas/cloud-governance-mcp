"""E5 SDK and real stdio verification in modern/legacy modes, with real OPA."""

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.evaluation_models import (
    EvaluateTerraformPoliciesInput,
    EvaluationReport,
)
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.server import create_server
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures/plans"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("transport", ["memory", "stdio"])
async def test_both_tools_real_policy_results_and_safe_failures(
    mode, transport, tmp_path, opa_path, caplog
):
    for fixture in FIXTURES.glob("*.json"):
        shutil.copyfile(fixture, tmp_path / fixture.name)
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        server = create_server(
            AnalysisService(settings, loader=loader),
            EvaluationService(
                settings, EvaluationSettings(opa_path=str(opa_path)), loader=loader
            ),
        )
        connection = (
            server
            if transport == "memory"
            else StdioServerParameters(
                command=sys.executable,
                args=[
                    "-I",
                    "-m",
                    "cloud_governance_mcp",
                    "--allowed-root",
                    str(tmp_path),
                    "--opa-path",
                    str(opa_path),
                ],
                cwd=tmp_path,
                env={"PATH": ""},
            )
        )
        async with Client(connection, mode=mode) as client:
            tools = (await client.list_tools()).tools
            assert [t.name for t in tools] == [
                "analyze_terraform_plan",
                "evaluate_terraform_policies",
            ]
            assert (
                tools[1].input_schema
                == EvaluateTerraformPoliciesInput.model_json_schema()
            )
            assert tools[1].output_schema == EvaluationReport.model_json_schema()
            assert tools[1].annotations.read_only_hint
            for filename, status in [
                ("encrypted_rds.json", "pass"),
                ("unencrypted_rds.json", "fail"),
                ("empty.json", "not_applicable"),
                ("unknown_sensitive.json", "indeterminate"),
            ]:
                result = await client.call_tool(
                    "evaluate_terraform_policies", {"plan_path": filename}
                )
                assert not result.is_error
                report = EvaluationReport.model_validate(result.structured_content)
                assert report.compliance_status == status
                assert json.loads(result.content[0].text) == result.structured_content
                assert "SENTINEL_" not in result.model_dump_json()
            for arguments in [
                {"plan_path": "encrypted_rds.json", "policy_ids": ["SENTINEL_POLICY"]},
                {"plan_path": "encrypted_rds.json", "policy_ids": None},
                {"plan_path": "encrypted_rds.json", "SENTINEL_KEY": "SENTINEL_VALUE"},
                {"plan_path": "../SENTINEL_OUTSIDE.json"},
                {"plan_path": "malformed.json"},
            ]:
                result = await client.call_tool(
                    "evaluate_terraform_policies", arguments
                )
                assert result.is_error and result.structured_content is None
                assert "SENTINEL_" not in result.model_dump_json()
            assert not (
                await client.call_tool(
                    "analyze_terraform_plan", {"plan_path": "mixed_nested.json"}
                )
            ).is_error
    assert "SENTINEL_" not in caplog.text


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_missing_opa_returns_structured_error_and_does_not_disable_analysis(
    mode, tmp_path
):
    shutil.copyfile(FIXTURES / "encrypted_rds.json", tmp_path / "plan.json")
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        server = create_server(
            AnalysisService(settings, loader=loader),
            EvaluationService(settings, EvaluationSettings(), loader=loader),
        )
        async with Client(server, mode=mode) as client:
            result = await client.call_tool(
                "evaluate_terraform_policies", {"plan_path": "plan.json"}
            )
            assert result.is_error
            assert json.loads(result.content[0].text) == result.structured_content
            report = EvaluationReport.model_validate(result.structured_content)
            assert report.errors[0].code == "OPA_NOT_CONFIGURED"
            assert report.compliance_status == "indeterminate"
            assert not (
                await client.call_tool(
                    "analyze_terraform_plan", {"plan_path": "plan.json"}
                )
            ).is_error


@pytest.mark.parametrize("name", ["encrypted", "unencrypted"])
async def test_example_evaluation_matches_saved_report_outside_checkout(
    name, tmp_path, opa_path
):
    root = Path(__file__).resolve().parent.parent
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            str(root / "examples/client.py"),
            "--evaluate",
            "--plan-path",
            f"{name}_rds.json",
            "--opa-path",
            str(opa_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    expected = json.loads(
        (root / f"examples/reports/{name}-rds-evaluation.json").read_text()
    )
    assert json.loads(result.stdout) == expected
    EvaluationReport.model_validate(expected)
