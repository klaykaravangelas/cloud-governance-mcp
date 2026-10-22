"""Real restricted OPA, three-policy reports and SDK stdio with startup keys."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.catalog import load_catalog
from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.engine.opa import OpaEngine
from cloud_governance_mcp.evaluation_errors import EvaluationFailure
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.listing import PolicyListingService
from cloud_governance_mcp.projection import to_evaluation_input
from cloud_governance_mcp.server import create_server
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
IDS = ["AWS-RDS-001", "AWS-SG-001", "AWS-TAG-001"]
KEYS = {"Environment": "dev", "Owner": "team", "Project": "demo"}


async def test_injected_configuration_cannot_override_operator_settings(tag_plan):
    snapshot = TerraformPlanAdapter(include_policy_values=True).normalize(
        tag_plan(), ["AWS-TAG-001"], ("Other",)
    )
    projected = to_evaluation_input(snapshot, ["AWS-TAG-001"], ("Other",))
    # A graph can be internally consistent yet differ from this engine's keys.
    engine = OpaEngine(EvaluationSettings(opa_path="/not/probed/opa"))
    with pytest.raises(EvaluationFailure) as failure:
        await engine.evaluate(projected, load_catalog())
    assert failure.value.code.value == "OPA_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "resource_type",
    [
        "aws_instance",
        "aws_security_group",
        "aws_db_instance",
        "aws_rds_cluster",
        "aws_s3_bucket",
        "aws_rds_cluster_instance",
        "aws_vpc_security_group_ingress_rule",
    ],
)
async def test_real_exact_tag_type_scope(tag_plan, tmp_path, opa_path, resource_type):
    report = await evaluate(
        tag_plan(resource_type=resource_type), tmp_path, opa_path, ["AWS-TAG-001"]
    )
    supported = resource_type not in {
        "aws_rds_cluster_instance",
        "aws_vpc_security_group_ingress_rule",
    }
    assert report.compliance_status == ("pass" if supported else "not_applicable")


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize(
    "name",
    [
        "tags_compliant",
        "tags_missing_owner",
        "tags_empty_project",
        "tags_unknown_owner",
        "tags_provider_defaults",
        "tags_custom_keys",
        "mixed_rds_ssh_tags",
    ],
)
async def test_saved_reports_match_real_stdio_outside_checkout(mode, name, opa_path):
    root = Path(__file__).resolve().parent.parent
    args = [
        "-I",
        "-m",
        "cloud_governance_mcp",
        "--allowed-root",
        str(root / "tests/fixtures/plans"),
        "--opa-path",
        str(opa_path),
    ]
    if name == "tags_custom_keys":
        args.extend(["--required-tag-key", "CostCenter"])
    async with Client(
        StdioServerParameters(command=sys.executable, args=args, cwd="/private/tmp"),
        mode=mode,
    ) as client:
        arguments = {"plan_path": name + ".json"}
        arguments["policy_ids"] = (
            IDS if name == "mixed_rds_ssh_tags" else ["AWS-TAG-001"]
        )
        result = await client.call_tool("evaluate_terraform_policies", arguments)
    assert not result.is_error
    expected = json.loads(
        (root / "examples/reports" / (name.replace("_", "-") + ".json")).read_text()
    )
    assert result.structured_content == json.loads(result.content[0].text) == expected
    assert "SENTINEL" not in result.model_dump_json()


async def evaluate(plan, tmp_path, opa_path, ids=None, keys=None, engine=None):
    """Actual loader/service; only dependency injection varies failure scenarios."""
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    kwargs = {"required_tag_keys": keys} if keys is not None else {}
    with RestrictedPlanLoader(settings) as loader:
        return await EvaluationService(
            settings,
            EvaluationSettings(opa_path=str(opa_path), **kwargs),
            loader=loader,
            engine=engine,
        ).evaluate("plan.json", ids)


@pytest.mark.parametrize("source", ["tags_all", "tags"])
@pytest.mark.parametrize(
    "case,status,suffix",
    [
        ("nonempty", "pass", "COMPLIANT"),
        ("missing", "fail", "KEY_MISSING"),
        ("blank", "fail", "KEY_EMPTY"),
        ("null", "fail", "KEY_EMPTY"),
        ("invalid", "indeterminate", "KEY_INVALID_TYPE"),
        ("unknown", "indeterminate", "KEY_UNKNOWN"),
        ("sensitive", "indeterminate", "KEY_SENSITIVE"),
    ],
)
async def test_real_tag_policy_per_key_states(
    tag_plan, tmp_path, opa_path, source, case, status, suffix
):
    values = deepcopy(KEYS)
    kwargs = {}
    if case == "missing":
        values.pop("Owner")
    elif case == "blank":
        values["Owner"] = " \t\u2003"
    elif case == "null":
        values["Owner"] = None
    elif case == "invalid":
        values["Owner"] = False
    elif case in {"sensitive", "unknown"}:
        values["Owner"] = "SENTINEL_VALUE"
        kwargs[case] = {source: {"Owner": True}}
    report = await evaluate(
        tag_plan({source: values}, **kwargs), tmp_path, opa_path, ["AWS-TAG-001"]
    )
    assert report.compliance_status == status
    assert report.summary.evaluated_checks == 1
    if status != "pass":
        finding = (report.findings or report.indeterminate_checks)[0]
        assert (
            finding.reason_code
            == ("TAG_ALL_" if source == "tags_all" else "TAG_RESOURCE_") + suffix
        )
        assert (
            finding.attribute_path == [source, "Owner"] and finding.severity == "medium"
        )
    assert "SENTINEL" not in report.model_dump_json()


@pytest.mark.parametrize(
    "after,kwargs,status,reason",
    [
        ({}, {}, "fail", "TAG_RESOURCE_MAP_MISSING"),
        ({"tags_all": None}, {}, "fail", "TAG_ALL_MAP_NULL"),
        (
            {"tags_all": None},
            {"unknown": {"tags_all": {"Owner": True}}},
            "indeterminate",
            "TAG_ALL_MAP_UNKNOWN",
        ),
        ({"tags_all": []}, {}, "indeterminate", "TAG_ALL_MAP_INVALID_TYPE"),
        ({"tags_all": {}, "tags": KEYS}, {}, "fail", "TAG_ALL_KEY_MISSING"),
        (
            {"tags": KEYS},
            {"unknown": {"tags_all": True}},
            "indeterminate",
            "TAG_ALL_MAP_UNKNOWN",
        ),
        (
            {"tags_all": KEYS},
            {"sensitive": {"tags": True}},
            "indeterminate",
            "TAG_ALL_MAP_SENSITIVE",
        ),
        ({"tags_all": KEYS}, {"unknown": True}, "indeterminate", "TAG_UNKNOWN"),
        ({"tags_all": KEYS}, {"sensitive": True}, "indeterminate", "TAG_SENSITIVE"),
    ],
)
async def test_real_map_precedence_and_uncertainty(
    tag_plan, tmp_path, opa_path, after, kwargs, status, reason
):
    report = await evaluate(
        tag_plan(after, **kwargs), tmp_path, opa_path, ["AWS-TAG-001"]
    )
    assert report.compliance_status == status
    assert (report.findings or report.indeterminate_checks)[0].reason_code == reason


@pytest.mark.parametrize(
    "values,kwargs,status,path",
    [
        (
            {"Environment": "", "Owner": None, "Project": "demo"},
            {"unknown": {"tags_all": {"Project": True}}},
            "fail",
            "Environment",
        ),
        (
            KEYS,
            {
                "unknown": {"tags_all": {"Environment": True}},
                "sensitive": {"tags": {"Owner": True}},
            },
            "indeterminate",
            "Owner",
        ),
        (
            {"Environment": False, "Owner": "team", "Project": "demo"},
            {"unknown": {"tags_all": {"Owner": True}}},
            "indeterminate",
            "Owner",
        ),
    ],
)
async def test_real_deterministic_failure_and_uncertainty_priority(
    tag_plan, tmp_path, opa_path, values, kwargs, status, path
):
    report = await evaluate(
        tag_plan({"tags_all": values}, **kwargs), tmp_path, opa_path, ["AWS-TAG-001"]
    )
    assert report.compliance_status == status
    assert (report.findings or report.indeterminate_checks)[0].attribute_path == [
        "tags_all",
        path,
    ]


@pytest.mark.parametrize(
    "ids,checks,candidates,passed,failed,na",
    [
        (["AWS-RDS-001"], 3, 1, 1, 0, 2),
        (["AWS-SG-001"], 3, 1, 0, 1, 2),
        (["AWS-TAG-001"], 3, 3, 3, 0, 0),
        (["AWS-RDS-001", "AWS-SG-001"], 6, 2, 1, 1, 4),
        (["AWS-RDS-001", "AWS-TAG-001"], 6, 3, 4, 0, 2),
        (["AWS-SG-001", "AWS-TAG-001"], 6, 3, 3, 1, 2),
        (None, 12, 3, 4, 1, 6),
        (list(reversed(IDS)), 9, 3, 4, 1, 4),
    ],
)
async def test_three_policy_accounting_and_one_engine_invocation(
    tag_plan, ssh_plan, tmp_path, opa_path, ids, checks, candidates, passed, failed, na
):
    plan = tag_plan(
        {"tags_all": KEYS, "storage_encrypted": True}, resource_type="aws_db_instance"
    )
    ssh = ssh_plan("inline")
    ssh["resource_changes"][0]["change"]["after"]["tags_all"] = deepcopy(KEYS)
    plan["resource_changes"].extend(ssh["resource_changes"])
    plan["resource_changes"].extend(
        tag_plan({"tags_all": KEYS}, resource_type="aws_s3_bucket")["resource_changes"]
    )

    class CountEngine(OpaEngine):
        calls = 0

        async def evaluate(self, request, catalog):
            self.calls += 1
            return await super().evaluate(request, catalog)

    engine = CountEngine(EvaluationSettings(opa_path=str(opa_path)))
    report = await evaluate(plan, tmp_path, opa_path, ids, engine=engine)
    summary = report.summary
    assert (
        summary.expected_checks,
        summary.evaluated_checks,
        summary.candidate_resources,
        summary.passed,
        summary.failed,
        summary.not_applicable,
    ) == (checks, checks, candidates, passed, failed, na)
    assert engine.calls == 1


async def test_captured_real_input_and_atomic_path_failure(
    tag_plan, tmp_path, opa_path, caplog
):
    captured = []

    class CapturingEngine(OpaEngine):
        async def evaluate(self, request, catalog):
            captured.append(request.model_dump_json())
            result = await super().evaluate(request, catalog)
            if self.corrupt:
                next(
                    c for c in result.checks if c.policy_id == "AWS-TAG-001"
                ).attribute_path = ["tags_all", "NOT_CONFIGURED"]
            return result

    engine = CapturingEngine(EvaluationSettings(opa_path=str(opa_path)))
    engine.corrupt = False
    plan = tag_plan(
        {
            "storage_encrypted": True,
            "tags_all": {
                "Environment": "SENTINEL_VALUE",
                "Project": "demo",
                "SENTINEL_KEY": "SENTINEL_SECRET",
            },
        },
        resource_type="aws_db_instance",
    )
    report = await evaluate(plan, tmp_path, opa_path, engine=engine)
    assert report.findings[0].attribute_path == ["tags_all", "Owner"]
    assert "SENTINEL" not in "".join(captured) + report.model_dump_json() + caplog.text
    engine.corrupt = True
    report = await evaluate(plan, tmp_path, opa_path, engine=engine)
    assert (
        report.evaluation_status == "failed"
        and report.errors[0].code == "OPA_OUTPUT_INVALID"
    )
    assert (
        not report.findings
        and report.summary.evaluated_checks == 0
        and report.summary.unevaluated_checks == 4
    )


async def test_custom_keys_and_missing_opa(tag_plan, tmp_path, opa_path):
    report = await evaluate(
        tag_plan(), tmp_path, opa_path, ["AWS-TAG-001"], keys=["Owner", "CostCenter"]
    )
    assert report.findings[0].attribute_path == ["tags_all", "CostCenter"]
    report = await evaluate(tag_plan(), tmp_path, Path("/not/installed/opa"))
    assert report.evaluation_status == "failed" and not report.findings
    assert report.summary.unevaluated_checks == 4


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("transport", ["memory", "stdio"])
@pytest.mark.parametrize("custom", [False, True])
async def test_mcp_three_policies_default_override_safe_errors_and_both_channels(
    tag_plan, tmp_path, opa_path, mode, transport, custom
):
    # Unmarked values and unrequired names must stay out of both MCP channels.
    plan = tag_plan(
        {
            "tags_all": {
                **KEYS,
                "Owner": "SENTINEL_SECRET",
                "SENTINEL_KEY": "SENTINEL_VALUE",
            }
        }
    )
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    kwargs = {"required_tag_keys": ["CostCenter"]} if custom else {}
    with RestrictedPlanLoader(settings) as loader:
        server = create_server(
            AnalysisService(settings, loader=loader),
            EvaluationService(
                settings,
                EvaluationSettings(opa_path=str(opa_path), **kwargs),
                loader=loader,
            ),
            PolicyListingService(),
        )
        args = [
            "-I",
            "-m",
            "cloud_governance_mcp",
            "--allowed-root",
            str(tmp_path),
            "--opa-path",
            str(opa_path),
        ]
        if custom:
            args.extend(["--required-tag-key", "CostCenter"])
        connection = (
            server
            if transport == "memory"
            else StdioServerParameters(
                command=sys.executable, args=args, cwd="/private/tmp", env={"PATH": ""}
            )
        )
        async with Client(connection, mode=mode) as client:
            assert len((await client.list_tools()).tools) == 3
            listing = await client.call_tool("list_policies")
            assert [p["policy_id"] for p in listing.structured_content["policies"]] == [
                "AWS-RDS-001",
                "AWS-S3-001",
                "AWS-SG-001",
                "AWS-TAG-001",
            ]
            assert listing.structured_content["policies"][3][
                "required_configuration"
            ] == ["required_tag_keys"]
            assert "CostCenter" not in listing.model_dump_json()
            result = await client.call_tool(
                "evaluate_terraform_policies", {"plan_path": "plan.json"}
            )
            assert not result.is_error
            report = result.structured_content
            assert report["selected_policy_ids"] == [
                "AWS-RDS-001",
                "AWS-S3-001",
                "AWS-SG-001",
                "AWS-TAG-001",
            ]
            assert report["compliance_status"] == ("fail" if custom else "pass")
            assert json.loads(result.content[0].text) == report
            assert "SENTINEL" not in result.model_dump_json()
            if custom:
                assert report["findings"][0]["attribute_path"] == [
                    "tags_all",
                    "CostCenter",
                ]
            for extra in [
                {"required_tag_keys": []},
                {"policy_ids": []},
                {"policy_ids": None},
                {"policy_ids": ["AWS-TAG-001"] * 2},
                {"policy_ids": ["SENTINEL"]},
                {"policy_ids": IDS + ["AWS-TAG-001"]},
            ]:
                result = await client.call_tool(
                    "evaluate_terraform_policies", {"plan_path": "plan.json", **extra}
                )
                assert result.is_error and result.structured_content is None
                assert "SENTINEL" not in result.model_dump_json()
