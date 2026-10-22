"""Pinned real OPA, four-policy accounting and safe MCP output in both modes."""

import itertools
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.engine.opa import OpaEngine
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.policy_definitions import POLICY_IDS
from cloud_governance_mcp.s3_models import S3_FLAGS

pytestmark = pytest.mark.anyio
ROOT = Path(__file__).resolve().parent.parent


async def evaluate(plan, tmp_path, opa_path, ids=None, engine=None):
    """Use the real loader and service, including atomic reporting failures."""
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        return await EvaluationService(
            settings,
            EvaluationSettings(opa_path=str(opa_path)),
            loader=loader,
            engine=engine,
        ).evaluate("plan.json", ids)


@pytest.mark.parametrize("flag", S3_FLAGS)
@pytest.mark.parametrize(
    "case,status,suffix",
    [
        ("true", "pass", "ENABLED"),
        ("false", "fail", "DISABLED"),
        ("missing", "indeterminate", "MISSING"),
        ("null", "indeterminate", "NULL"),
        ("invalid", "indeterminate", "INVALID_TYPE"),
        ("sensitive", "indeterminate", "SENSITIVE"),
        ("unknown", "indeterminate", "UNKNOWN"),
    ],
)
async def test_direct_and_inherited_flag_states(
    s3_plan, tmp_path, opa_path, flag, case, status, suffix
):
    plan = s3_plan()
    change = plan["resource_changes"][1]["change"]
    if case == "false":
        change["after"][flag] = False
    elif case == "missing":
        change["after"].pop(flag)
    elif case == "null":
        change["after"][flag] = None
    elif case == "invalid":
        change["after"][flag] = "SENTINEL_INVALID"
    elif case in {"sensitive", "unknown"}:
        change["after"][flag] = "SENTINEL_SECRET"
        change["after_" + case] = {flag: True}
    report = await evaluate(plan, tmp_path, opa_path, ["AWS-S3-001"])
    assert report.evaluation_status == "complete" and report.compliance_status == status
    assert report.summary.expected_checks == report.summary.evaluated_checks == 2
    checks = report.findings or report.indeterminate_checks
    if status != "pass":
        assert len(checks) == 2
        codes = {c.reason_code for c in checks}
        assert codes == {
            f"S3_{kind}_{flag.upper()}_{suffix}" for kind in ("BLOCK", "BUCKET")
        }
        assert {tuple(c.attribute_path) for c in checks} == {("bucket",), (flag,)}
        assert all(c.severity == "high" for c in checks)
    assert "SENTINEL" not in report.model_dump_json()


@pytest.mark.parametrize(
    "source,state",
    [
        ("after_sensitive", "SENSITIVE"),
        ("after_unknown", "UNKNOWN"),
        ("unverified", "UNVERIFIED"),
        ("unavailable", "UNAVAILABLE"),
    ],
)
async def test_unresolved_whole_block_never_creates_inherited_success(
    s3_plan, tmp_path, opa_path, source, state
):
    plan = s3_plan()
    change = plan["resource_changes"][1]["change"]
    if source == "unverified":
        change.pop("after_unknown")
    elif source == "unavailable":
        change["after"] = None
    else:
        change[source] = True
    report = await evaluate(plan, tmp_path, opa_path, ["AWS-S3-001"])
    assert report.compliance_status == "indeterminate"
    direct = next(
        c
        for c in report.indeterminate_checks
        if c.resource_type.endswith("public_access_block")
    )
    assert direct.reason_code == "S3_BLOCK_BLOCK_PUBLIC_ACLS_" + state
    assert (
        next(
            c for c in report.indeterminate_checks if c.resource_type == "aws_s3_bucket"
        ).reason_code
        == "S3_LINK_CONTEXT_UNVERIFIED"
    )


@pytest.mark.parametrize(
    "case,flag,suffix",
    [
        ("failure", "block_public_policy", "DISABLED"),
        ("sensitive", "ignore_public_acls", "SENSITIVE"),
        ("unknown", "block_public_acls", "UNKNOWN"),
    ],
)
async def test_deterministic_failure_and_uncertainty_priority(
    s3_plan, tmp_path, opa_path, case, flag, suffix
):
    plan = s3_plan()
    c = plan["resource_changes"][1]["change"]
    c["after_unknown"] = {"block_public_acls": True}
    c["after"]["restrict_public_buckets"] = None
    if case == "failure":
        c["after"]["block_public_policy"] = False
    if case == "sensitive":
        c["after_sensitive"] = {"ignore_public_acls": True}
    report = await evaluate(plan, tmp_path, opa_path, ["AWS-S3-001"])
    assert {
        r.reason_code for r in (report.findings or report.indeterminate_checks)
    } == {f"S3_{kind}_{flag.upper()}_{suffix}" for kind in ("BLOCK", "BUCKET")}


@pytest.mark.parametrize("scope", ["data", "delete", "provider", "type"])
async def test_exact_scope_not_applicable(s3_plan, tmp_path, opa_path, scope):
    plan = s3_plan()
    plan["resource_changes"] = plan["resource_changes"][1:]
    r = plan["resource_changes"][0]
    if scope == "data":
        r["mode"] = "data"
    elif scope == "delete":
        r["change"]["actions"] = ["delete"]
        r["change"]["after"] = None
    elif scope == "provider":
        r["provider_name"] = "example/other"
    else:
        r["type"] = "aws_s3_bucket_policy"
    report = await evaluate(plan, tmp_path, opa_path, ["AWS-S3-001"])
    assert (
        report.compliance_status == "not_applicable"
        and report.summary.not_applicable == 1
    )


@pytest.mark.parametrize(
    "ids",
    [list(s) for n in range(1, 5) for s in itertools.combinations(POLICY_IDS, n)]
    + [None, list(reversed(POLICY_IDS))],
)
async def test_all_four_policy_subsets_accounting_and_single_invocation(
    tmp_path, opa_path, ids
):
    plan = json.loads(
        (ROOT / "tests/fixtures/plans/mixed_all_policies.json").read_text()
    )

    class CountingEngine(OpaEngine):
        calls = 0

        async def evaluate(self, request, catalog):
            self.calls += 1
            return await super().evaluate(request, catalog)

    engine = CountingEngine(EvaluationSettings(opa_path=str(opa_path)))
    report = await evaluate(plan, tmp_path, opa_path, ids, engine)
    selected = sorted(ids if ids is not None else POLICY_IDS)
    assert report.evaluation_status == "complete"
    assert report.selected_policy_ids == selected
    assert (
        report.summary.expected_checks
        == report.summary.evaluated_checks
        == len(selected) * 4
    )
    assert report.summary.failed == int("AWS-SG-001" in selected)
    assert report.summary.passed == int("AWS-RDS-001" in selected) + 2 * int(
        "AWS-S3-001" in selected
    ) + 3 * int("AWS-TAG-001" in selected)
    assert engine.calls == 1


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "wrong_path", "wrong_reason", "forged_pass"]
)
async def test_invalid_opa_batch_is_atomic(s3_plan, tmp_path, opa_path, mutation):
    class CorruptEngine(OpaEngine):
        async def evaluate(self, request, catalog):
            report = await super().evaluate(request, catalog)
            check = next(
                c
                for c in report.checks
                if c.policy_id == "AWS-S3-001"
                and c.resource_address.endswith("protection")
            )
            if mutation == "missing":
                report.checks.remove(check)
            elif mutation == "duplicate":
                report.checks.append(deepcopy(check))
            elif mutation == "wrong_path":
                check.attribute_path = ["SENTINEL_BAD"]
            elif mutation == "wrong_reason":
                check.reason_code = "S3_LINK_NOT_FOUND"
                check.outcome = "indeterminate"
                check.attribute_path = ["bucket"]
            else:
                check.reason_code = "S3_BLOCK_ENABLED"
                check.outcome = "pass"
                check.attribute_path = []
            return report

    plan = s3_plan()
    plan["resource_changes"][1]["change"]["after"]["block_public_acls"] = False
    report = await evaluate(
        plan,
        tmp_path,
        opa_path,
        engine=CorruptEngine(EvaluationSettings(opa_path=str(opa_path))),
    )
    assert (
        report.evaluation_status == "failed"
        and report.errors[0].code == "OPA_OUTPUT_INVALID"
    )
    assert (
        report.summary.evaluated_checks == 0
        and not report.findings
        and not report.indeterminate_checks
    )


async def test_input_and_logs_do_not_leak_matching_evidence(
    s3_plan, tmp_path, opa_path, caplog
):
    captured = []

    class Capture(OpaEngine):
        async def evaluate(self, request, catalog):
            captured.append(request.model_dump_json())
            return await super().evaluate(request, catalog)

    plan = s3_plan()
    for r in plan["resource_changes"]:
        r["change"]["after"]["bucket"] = "SENTINEL_BUCKET_NAME"
    for r in plan["configuration"]["root_module"]["resources"]:
        r["provider_config_key"] = "SENTINEL_PROVIDER_KEY"
    plan["resource_changes"][1]["change"]["after"]["extra"] = "SENTINEL_SECRET"
    report = await evaluate(
        plan,
        tmp_path,
        opa_path,
        ["AWS-S3-001"],
        Capture(EvaluationSettings(opa_path=str(opa_path))),
    )
    assert report.compliance_status == "pass"
    assert "SENTINEL" not in "".join(captured) + report.model_dump_json() + caplog.text


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize(
    "name",
    [
        "s3_compliant",
        "s3_disabled_flag",
        "s3_unknown_flag",
        "s3_missing_block",
        "s3_computed_link",
        "s3_ambiguous_link",
        "mixed_all_policies",
    ],
)
async def test_saved_reports_real_stdio_both_channels(mode, name, opa_path, tmp_path):
    args = [
        "-I",
        "-m",
        "cloud_governance_mcp",
        "--allowed-root",
        str(ROOT / "tests/fixtures/plans"),
        "--opa-path",
        str(opa_path),
    ]
    args.extend(["--allowed-root", str(tmp_path)])
    with (tmp_path / "stderr.txt").open("w+") as stderr:
        async with Client(
            stdio_client(
                StdioServerParameters(
                    command=sys.executable,
                    args=args,
                    cwd="/private/tmp",
                    env={"PATH": ""},
                ),
                errlog=stderr,
            ),
            mode=mode,
        ) as client:
            assert len((await client.list_tools()).tools) == 3
            listing = await client.call_tool("list_policies")
            assert [
                p["policy_id"] for p in listing.structured_content["policies"]
            ] == list(POLICY_IDS)
            analysis = await client.call_tool(
                "analyze_terraform_plan", {"plan_path": name + ".json"}
            )
            assert not analysis.is_error
            arguments = {"plan_path": name + ".json"}
            if name != "mixed_all_policies":
                arguments["policy_ids"] = ["AWS-S3-001"]
            result = await client.call_tool("evaluate_terraform_policies", arguments)
            assert not result.is_error
            expected = json.loads(
                (
                    ROOT / "examples/reports" / (name.replace("_", "-") + ".json")
                ).read_text()
            )
            assert (
                result.structured_content
                == json.loads(result.content[0].text)
                == expected
            )
            assert "SENTINEL" not in result.model_dump_json()
            invalid = await client.call_tool(
                "evaluate_terraform_policies",
                {"plan_path": "../SENTINEL.json", "policy_ids": ["AWS-S3-001"]},
            )
            assert invalid.is_error and "SENTINEL" not in invalid.model_dump_json()
            if name == "s3_compliant":
                private = json.loads(
                    (ROOT / "tests/fixtures/plans/s3_compliant.json").read_text()
                )
                for r in private["resource_changes"]:
                    r["change"]["after"]["bucket"] = "SENTINEL_BUCKET"
                    r["change"]["after"]["unrelated"] = "SENTINEL_SECRET"
                private_path = tmp_path / "private.json"
                private_path.write_text(json.dumps(private))
                result = await client.call_tool(
                    "evaluate_terraform_policies",
                    {"plan_path": str(private_path), "policy_ids": ["AWS-S3-001"]},
                )
                assert not result.is_error
                assert result.structured_content["compliance_status"] == "pass"
                assert json.loads(result.content[0].text) == result.structured_content
                assert "SENTINEL" not in result.model_dump_json()
        stderr.seek(0)
        assert stderr.read() == ""
