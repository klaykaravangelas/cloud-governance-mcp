"""Exercise expanded RDS coverage through real OPA, services and MCP stdio."""

import json
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.evaluation_models import EvaluationReport
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.listing import PolicyListingService
from cloud_governance_mcp.server import create_server
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("encrypted", [True, False])
@pytest.mark.parametrize("engine", ["aurora-postgresql", "postgres"])
async def test_cluster_and_two_members_count_three_checks(
    rds_graph, tmp_path, opa_path, encrypted, engine
):
    data = rds_graph(encrypted=encrypted, members=2)
    # Nested addresses, including quoted instance keys, are opaque graph keys.
    prefix = 'module.database["blue"]'
    for source, entries in [
        ("change", data["resource_changes"]),
        ("inventory", data["planned_values"]["root_module"]["resources"]),
    ]:
        for entry in entries:
            entry["address"] = prefix + "." + entry["address"] + "[0]"
            entry["module_address"] = prefix
            values = entry["change"]["after"] if source == "change" else entry["values"]
            values["engine"] = engine
    data["planned_values"]["root_module"] = {
        "child_modules": [
            {
                "address": prefix,
                "resources": data["planned_values"]["root_module"]["resources"],
            }
        ]
    }
    (tmp_path / "plan.json").write_text(json.dumps(data))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        report = await EvaluationService(
            settings, EvaluationSettings(opa_path=str(opa_path)), loader=loader
        ).evaluate("plan.json", ["AWS-RDS-001"])
    assert report.evaluation_status == "complete"
    assert report.compliance_status == ("pass" if encrypted else "fail")
    assert (
        report.summary.candidate_resources
        == report.summary.expected_checks
        == report.summary.evaluated_checks
        == 3
    )
    assert (report.summary.passed if encrypted else report.summary.failed) == 3
    if not encrypted:
        assert [item.reason_code for item in report.findings] == [
            "RDS_ENCRYPTION_DISABLED",
            "RDS_CLUSTER_ENCRYPTION_DISABLED",
            "RDS_CLUSTER_ENCRYPTION_DISABLED",
        ]
        assert all(
            "cluster" in item.remediation.lower() for item in report.findings[1:]
        )


@pytest.mark.parametrize(
    "state",
    [
        "missing",
        "null",
        "string",
        "number",
        "container",
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
    ],
)
async def test_target_uncertainty_and_missing_linkage_do_not_invent_defaults(
    rds_graph, tmp_path, opa_path, state
):
    plan = rds_graph()
    target = plan["resource_changes"][0]["change"]
    if state == "missing":
        target["after"].pop("storage_encrypted")
    elif state in {"null", "string", "number", "container"}:
        target["after"]["storage_encrypted"] = {
            "null": None,
            "string": "SENTINEL_ENCRYPTION",
            "number": 1,
            "container": {"secret": "SENTINEL"},
        }[state]
    elif state in {"sensitive", "unknown"}:
        target["after_sensitive" if state == "sensitive" else "after_unknown"] = {
            "storage_encrypted": True
        }
    elif state == "unverified":
        target.pop("after_unknown")
    else:
        target["after"] = None
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        report = await EvaluationService(
            settings, EvaluationSettings(opa_path=str(opa_path)), loader=loader
        ).evaluate("plan.json", ["AWS-RDS-001"])
    assert report.compliance_status == "indeterminate"
    assert report.evaluation_status == "complete"
    assert report.summary.indeterminate == report.summary.evaluated_checks == 2
    assert "SENTINEL" not in report.model_dump_json()


async def test_direct_cluster_requires_no_linkage_metadata(
    rds_graph, tmp_path, opa_path
):
    plan = rds_graph(members=0)
    plan["resource_changes"][0]["change"]["after"] = {"storage_encrypted": True}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        report = await EvaluationService(
            settings, EvaluationSettings(opa_path=str(opa_path)), loader=loader
        ).evaluate("plan.json", ["AWS-RDS-001"])
    assert report.compliance_status == "pass"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("transport", ["memory", "stdio"])
async def test_same_three_tools_inherit_without_raw_linkage_leaks(
    rds_graph, tmp_path, opa_path, mode, transport, caplog
):
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        server = create_server(
            AnalysisService(settings, loader=loader),
            EvaluationService(
                settings, EvaluationSettings(opa_path=str(opa_path)), loader=loader
            ),
            PolicyListingService(),
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
            assert [item.name for item in (await client.list_tools()).tools] == [
                "analyze_terraform_plan",
                "evaluate_terraform_policies",
                "list_policies",
            ]
            catalog = (await client.call_tool("list_policies")).structured_content
            assert catalog["policies"][0]["policy_version"] == "1.1.0"
            for encrypted, unknown, status in [
                (True, False, "pass"),
                (False, False, "fail"),
                (True, True, "indeterminate"),
            ]:
                plan = rds_graph(encrypted=encrypted, members=2)
                if unknown:
                    for entry in plan["resource_changes"]:
                        entry["change"]["after_unknown"] = {"arn": True}
                (tmp_path / "plan.json").write_text(json.dumps(plan))
                result = await client.call_tool(
                    "evaluate_terraform_policies",
                    {"plan_path": "plan.json", "policy_ids": ["AWS-RDS-001"]},
                )
                assert not result.is_error
                report = EvaluationReport.model_validate(result.structured_content)
                assert report.compliance_status == status
                assert json.loads(result.content[0].text) == result.structured_content
                assert (
                    report.policy_scope[0].supported_resource_types
                    == catalog["policies"][0]["supported_resource_types"]
                )
                text = result.model_dump_json() + caplog.text
                for value in ["demo-cluster", "arn:aws", "111122223333", "us-east-1"]:
                    assert value not in text


@pytest.mark.parametrize(
    "name,status",
    [
        ("cluster_encrypted", "pass"),
        ("cluster_unencrypted", "fail"),
        ("cluster_unknown_arn", "indeterminate"),
    ],
)
async def test_saved_cluster_reports_match_real_stdio(name, status, opa_path):
    """Saved artifacts remain executable documentation, not hand-written reports."""
    root = Path(__file__).resolve().parent.parent
    async with Client(
        StdioServerParameters(
            command=sys.executable,
            args=[
                "-I",
                "-m",
                "cloud_governance_mcp",
                "--allowed-root",
                str(root / "tests/fixtures/plans"),
                "--opa-path",
                str(opa_path),
            ],
            cwd="/private/tmp",
        )
    ) as client:
        result = await client.call_tool(
            "evaluate_terraform_policies",
            {"plan_path": name + ".json", "policy_ids": ["AWS-RDS-001"]},
        )
    assert not result.is_error
    assert result.structured_content["compliance_status"] == status
    assert result.structured_content == json.loads(
        (root / "examples/reports" / (name.replace("_", "-") + ".json")).read_text()
    )
