"""Real restricted OPA, two-policy services and both MCP protocol modes."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cloud_governance_mcp.catalog import load_catalog
from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.engine.opa import OpaEngine
from cloud_governance_mcp.evaluation_models import EvaluationReport
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.listing import PolicyListingService
from cloud_governance_mcp.server import create_server
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
IDS = ["AWS-RDS-001", "AWS-SG-001"]


async def evaluate(plan, tmp_path, opa_path, ids=None, engine=None):
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        return await EvaluationService(
            settings,
            EvaluationSettings(opa_path=str(opa_path)),
            loader=loader,
            engine=engine,
        ).evaluate("plan.json", IDS if ids is None else ids)


@pytest.mark.parametrize("representation", ["inline", "legacy", "modern"])
@pytest.mark.parametrize(
    "case,status",
    [
        ("world", "fail"),
        ("ipv6", "fail"),
        ("range", "fail"),
        ("all", "fail"),
        ("udp", "pass"),
        ("other_port", "pass"),
        ("private", "pass"),
        ("unknown_protocol", "indeterminate"),
        ("prefix", "indeterminate"),
        ("self_or_group", "pass"),
        ("empty_source", "indeterminate"),
    ],
)
async def test_real_policy_decisions_for_every_representation(
    ssh_plan, tmp_path, opa_path, representation, case, status
):
    plan = ssh_plan(representation)
    after = plan["resource_changes"][0]["change"]["after"]
    rule = after["ingress"][0] if representation == "inline" else after
    modern = representation == "modern"
    proto = "ip_protocol" if modern else "protocol"
    v4, v6 = (
        ("cidr_ipv4", "cidr_ipv6") if modern else ("cidr_blocks", "ipv6_cidr_blocks")
    )
    if case == "ipv6":
        rule.pop(v4)
        rule[v6] = "::/0" if modern else ["::/0"]
    elif case == "range":
        rule.update(from_port=20, to_port=23)
    elif case == "all":
        rule[proto] = "-1"
        rule.pop("from_port")
        rule.pop("to_port")
    elif case == "udp":
        rule[proto] = "udp"
    elif case == "other_port":
        rule.update(from_port=443, to_port=443)
    elif case == "private":
        rule[v4] = "192.0.2.1/24" if modern else ["192.0.2.1/24"]
    elif case == "unknown_protocol":
        plan["resource_changes"][0]["change"]["after_unknown"] = (
            {"ingress": [{proto: True}]}
            if representation == "inline"
            else {proto: True}
        )
    elif case == "prefix":
        rule.pop(v4)
        rule["prefix_list_id" if modern else "prefix_list_ids"] = (
            "SENTINEL_PREFIX" if modern else ["SENTINEL_PREFIX"]
        )
    elif case == "self_or_group":
        rule.pop(v4)
        rule["referenced_security_group_id" if modern else "self"] = (
            "SENTINEL_GROUP" if modern else True
        )
    elif case == "empty_source":
        rule.pop(v4)
    report = await evaluate(plan, tmp_path, opa_path, ["AWS-SG-001"])
    assert report.evaluation_status == "complete"
    assert report.compliance_status == status
    assert report.summary.expected_checks == report.summary.evaluated_checks == 1
    assert "SENTINEL" not in report.model_dump_json()


@pytest.mark.parametrize(
    "kind,status",
    [
        ("failure_unknown", "fail"),
        ("safe_unknown", "indeterminate"),
        ("empty", "pass"),
        ("sensitive", "indeterminate"),
    ],
)
async def test_inline_aggregation_and_conservative_collection_masks(
    ssh_plan, tmp_path, opa_path, kind, status
):
    plan = ssh_plan("inline")
    change = plan["resource_changes"][0]["change"]
    if kind == "empty":
        change["after"]["ingress"] = []
    elif kind == "sensitive":
        change["after_sensitive"] = {"ingress": [{"protocol": True}]}
    else:
        if kind == "safe_unknown":
            change["after"]["ingress"][0]["to_port"] = 20
            change["after"]["ingress"][0]["from_port"] = 20
        change["after"]["ingress"].append({})
        change["after_unknown"] = {"ingress": [False, True]}
    report = await evaluate(plan, tmp_path, opa_path, ["AWS-SG-001"])
    assert report.compliance_status == status
    assert report.summary.evaluated_checks == 1
    assert len(report.findings) == (1 if status == "fail" else 0)


@pytest.mark.parametrize(
    "ids,expected,candidates,passed,failed,na",
    [
        (None, 6, 2, 1, 1, 4),
        (["AWS-RDS-001"], 3, 1, 1, 0, 2),
        (["AWS-SG-001"], 3, 1, 0, 1, 2),
        (list(reversed(IDS)), 6, 2, 1, 1, 4),
    ],
)
async def test_selected_policy_resource_union_and_cross_scope_checks(
    ssh_plan, tmp_path, opa_path, ids, expected, candidates, passed, failed, na
):
    root = Path(__file__).parent / "fixtures/plans"
    plan = json.loads((root / "encrypted_rds.json").read_text())
    network = ssh_plan()
    plan["resource_changes"].extend(network["resource_changes"])
    bucket = deepcopy(network["resource_changes"][0])
    bucket.update(address="aws_s3_bucket.example", type="aws_s3_bucket", name="example")
    plan["resource_changes"].append(bucket)
    plan["planned_values"] = {}
    calls = []

    class CountingEngine(OpaEngine):
        async def evaluate(self, request, catalog):
            calls.append(request.model_dump_json())
            return await super().evaluate(request, catalog)

    report = await evaluate(
        plan,
        tmp_path,
        opa_path,
        ids,
        CountingEngine(EvaluationSettings(opa_path=str(opa_path))),
    )
    s = report.summary
    assert (s.resources_observed, s.candidate_resources, s.unsupported_resources) == (
        3,
        candidates,
        3 - candidates,
    )
    assert (
        s.expected_checks,
        s.evaluated_checks,
        s.passed,
        s.failed,
        s.not_applicable,
    ) == (expected, expected, passed, failed, na)
    assert len(calls) == 1


async def test_real_opa_input_and_public_reports_do_not_retain_raw_source_values(
    ssh_plan, tmp_path, opa_path, caplog
):
    plan = ssh_plan(
        cidr_ipv4="192.0.2.17/24",
        prefix_list_id="SENTINEL_PREFIX",
        referenced_security_group_id="SENTINEL_GROUP",
        description="SENTINEL_SECRET",
    )
    captured = []

    class CapturingEngine(OpaEngine):
        async def evaluate(self, request, catalog):
            captured.append(request.model_dump_json() + repr(request))
            return await super().evaluate(request, catalog)

    report = await evaluate(
        plan,
        tmp_path,
        opa_path,
        None,
        CapturingEngine(EvaluationSettings(opa_path=str(opa_path))),
    )
    assert report.compliance_status == "indeterminate"
    for text in [*captured, report.model_dump_json(), caplog.text]:
        assert "SENTINEL" not in text and "192.0.2.17" not in text


async def test_egress_is_not_applicable_and_engine_failure_discards_both_policies(
    ssh_plan, tmp_path, opa_path
):
    report = await evaluate(ssh_plan("legacy", type="egress"), tmp_path, opa_path)
    assert report.compliance_status == "not_applicable"
    assert report.summary.not_applicable == 2
    report = await evaluate(ssh_plan(), tmp_path, Path("/not/installed/opa"))
    assert report.evaluation_status == "failed"
    assert (
        report.summary.evaluated_checks == 0 and report.summary.unevaluated_checks == 2
    )
    assert not report.findings and report.errors


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("transport", ["memory", "stdio"])
async def test_two_policy_mcp_discovery_selection_and_both_output_channels(
    ssh_plan, tmp_path, opa_path, mode, transport
):
    (tmp_path / "plan.json").write_text(json.dumps(ssh_plan()))
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
            assert [t.name for t in (await client.list_tools()).tools] == [
                "analyze_terraform_plan",
                "evaluate_terraform_policies",
                "list_policies",
            ]
            listing = await client.call_tool("list_policies")
            assert [p["policy_id"] for p in listing.structured_content["policies"]] == [
                "AWS-RDS-001",
                "AWS-S3-001",
                "AWS-SG-001",
                "AWS-TAG-001",
            ]
            assert [
                p["policy_version"] for p in listing.structured_content["policies"]
            ] == ["1.1.0", "1.0.0", "1.0.0", "1.0.0"]
            for ids in [None, ["AWS-SG-001"], ["AWS-RDS-001"], list(reversed(IDS))]:
                args = {"plan_path": "plan.json"}
                if ids is not None:
                    args["policy_ids"] = ids
                result = await client.call_tool("evaluate_terraform_policies", args)
                assert not result.is_error
                report = EvaluationReport.model_validate(result.structured_content)
                assert json.loads(result.content[0].text) == result.structured_content
                assert report.selected_policy_ids == sorted(
                    ids
                    if ids is not None
                    else ["AWS-RDS-001", "AWS-S3-001", "AWS-SG-001", "AWS-TAG-001"]
                )
                assert report.compliance_status == (
                    "not_applicable" if ids == ["AWS-RDS-001"] else "fail"
                )
                assert "0.0.0.0" not in result.model_dump_json()
            for ids in [None, [], ["AWS-SG-001"] * 2, ["SENTINEL"], ["AWS-SG-001", 1]]:
                result = await client.call_tool(
                    "evaluate_terraform_policies",
                    {"plan_path": "plan.json", "policy_ids": ids},
                )
                assert result.is_error and result.structured_content is None
                assert "SENTINEL" not in result.model_dump_json()
    assert load_catalog().select(["AWS-SG-001"])[0].policy_id == "AWS-SG-001"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize(
    "name,status",
    [
        ("ssh_inline_open", "fail"),
        ("ssh_legacy_restricted", "pass"),
        ("ssh_modern_open", "fail"),
        ("ssh_unknown", "indeterminate"),
        ("mixed_rds_ssh", "fail"),
    ],
)
async def test_saved_ssh_reports_match_real_stdio_outside_checkout(
    mode, name, status, opa_path
):
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
        ),
        mode=mode,
    ) as client:
        result = await client.call_tool(
            "evaluate_terraform_policies",
            {"plan_path": name + ".json", "policy_ids": IDS},
        )
    assert not result.is_error
    assert result.structured_content["compliance_status"] == status
    assert result.structured_content == json.loads(
        (root / "examples/reports" / (name.replace("_", "-") + ".json")).read_text()
    )
