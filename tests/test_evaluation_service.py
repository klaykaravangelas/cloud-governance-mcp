"""E4: real policy outcomes, conservative coverage, safe errors and admission."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from threading import Event

import pytest

from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.engine.opa import OpaEngine
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import EngineReport
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures/plans"


def plan():
    return json.loads((FIXTURES / "encrypted_rds.json").read_text())


async def evaluate(data, tmp_path, opa_path, **budgets):
    (tmp_path / "plan.json").write_text(json.dumps(data))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        service = EvaluationService(
            settings,
            EvaluationSettings(opa_path=str(opa_path), **budgets),
            loader=loader,
        )
        return await service.evaluate("plan.json")


@pytest.mark.parametrize(
    "state,reason",
    [
        ("missing", "RDS_ENCRYPTION_MISSING"),
        ("null", "RDS_ENCRYPTION_NULL"),
        ("invalid", "RDS_ENCRYPTION_INVALID_TYPE"),
        ("unknown", "RDS_ENCRYPTION_UNKNOWN"),
        ("sensitive", "RDS_ENCRYPTION_SENSITIVE"),
        ("incomplete", "UNKNOWN_METADATA_INCOMPLETE"),
        ("cluster", "RDS_CLUSTER_ASSOCIATION_UNSUPPORTED"),
        ("unavailable", "DESIRED_STATE_UNAVAILABLE"),
    ],
)
async def test_real_opa_uncertainty_is_explicit_and_has_no_sensitive_values(
    tmp_path, opa_path, state, reason, caplog
):
    data = plan()
    change = data["resource_changes"][0]["change"]
    if state == "missing":
        del change["after"]["storage_encrypted"]
    elif state == "null":
        change["after"]["storage_encrypted"] = None
    elif state == "invalid":
        change["after"]["storage_encrypted"] = "SENTINEL_SECRET"
    elif state in {"unknown", "sensitive"}:
        change["after"]["storage_encrypted"] = "SENTINEL_SECRET"
        change["after_unknown" if state == "unknown" else "after_sensitive"] = {
            "storage_encrypted": True
        }
    elif state == "incomplete":
        del change["after_unknown"]
    elif state == "cluster":
        change["after"]["cluster_identifier"] = "SENTINEL_CLUSTER"
    elif state == "unavailable":
        change["after"] = None
    report = await evaluate(data, tmp_path, opa_path)
    assert report.evaluation_status == "complete"
    assert report.compliance_status == "indeterminate"
    assert report.indeterminate_checks[0].reason_code == reason
    assert report.summary.indeterminate == 1
    assert "SENTINEL_" not in report.model_dump_json() + caplog.text


@pytest.mark.parametrize(
    "actions",
    [
        ["create"],
        ["update"],
        ["no-op"],
        ["read"],
        ["delete", "create"],
        ["create", "delete"],
    ],
)
async def test_managed_actions_check_desired_state_once(tmp_path, opa_path, actions):
    data = plan()
    data["resource_changes"][0]["change"]["actions"] = actions
    report = await evaluate(data, tmp_path, opa_path)
    assert report.compliance_status == "pass"
    assert report.summary.passed == report.summary.expected_checks == 1


@pytest.mark.parametrize(
    "kind", ["empty", "data", "delete", "unsupported", "wrong_provider"]
)
async def test_no_applicable_checks_never_becomes_pass(tmp_path, opa_path, kind):
    data = plan()
    data["planned_values"] = {}
    r = data["resource_changes"][0]
    if kind == "empty":
        data["resource_changes"] = []
    elif kind == "data":
        r["mode"] = "data"
    elif kind == "delete":
        r["change"]["actions"] = ["delete"]
        r["change"]["after"] = None
    elif kind == "unsupported":
        r["type"] = "aws_rds_cluster"
    else:
        r["provider_name"] = "example.invalid/other/provider"
    report = await evaluate(data, tmp_path, opa_path)
    assert report.evaluation_status == "complete"
    assert report.compliance_status == "not_applicable"
    assert report.summary.not_applicable == (0 if kind == "empty" else 1)


@pytest.mark.parametrize("encrypted,status", [(True, "indeterminate"), (False, "fail")])
async def test_partial_coverage_blocks_pass_but_preserves_verified_failures(
    tmp_path, opa_path, encrypted, status
):
    data = plan()
    data["complete"] = False
    data["resource_changes"][0]["change"]["after"]["storage_encrypted"] = encrypted
    report = await evaluate(data, tmp_path, opa_path)
    assert report.evaluation_status == "partial"
    assert report.compliance_status == status


async def test_engine_failure_is_atomic_and_analysis_remains_independent(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps(plan()))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        service = EvaluationService(settings, EvaluationSettings(), loader=loader)
        report = await service.evaluate("plan.json")
        assert report.evaluation_status == "failed"
        assert report.compliance_status == "indeterminate"
        assert report.errors[0].code == "OPA_NOT_CONFIGURED"
        assert report.summary.unevaluated_checks == 1
        assert report.summary.evaluated_checks == 0
        assert not report.findings
        assert (
            await AnalysisService(settings, loader=loader).analyze("plan.json")
        ).summary.total_resources == 1


async def test_injected_incomplete_result_is_revalidated(tmp_path):
    class IncompleteEngine:
        async def evaluate(self, *args):
            return EngineReport(checks=[])

    (tmp_path / "plan.json").write_text(json.dumps(plan()))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        service = EvaluationService(
            settings, EvaluationSettings(), loader=loader, engine=IncompleteEngine()
        )
        report = await service.evaluate("plan.json")
        assert report.errors[0].code == "OPA_OUTPUT_INVALID"
        assert report.summary.unevaluated_checks == 1


async def test_invalid_selection_denied_path_and_busy_precede_engine_work(tmp_path):
    class BlockingLoader:
        def read_plan(self, path):
            started.set()
            release.wait(5)
            return plan()

    started, release = Event(), Event()
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    service = EvaluationService(settings, EvaluationSettings(), loader=BlockingLoader())
    with pytest.raises(EvaluationFailure) as error:
        await service.evaluate("plan.json", ["SENTINEL_POLICY"])
    assert error.value.code == EvaluationCode.INVALID_POLICY_SELECTION
    assert not started.is_set()
    active = asyncio.create_task(service.evaluate("plan.json"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        with pytest.raises(EvaluationFailure) as error:
            await service.evaluate("plan.json")
        assert error.value.code == EvaluationCode.SERVER_BUSY
        active.cancel()
        await asyncio.sleep(0.02)
        assert not active.done()  # Cancellation cannot abandon a file worker.
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert (await service.evaluate("plan.json")).evaluation_status == "failed"
    with RestrictedPlanLoader(settings) as loader:
        safe = EvaluationService(settings, EvaluationSettings(), loader=loader)
        with pytest.raises(AnalysisError) as error:
            await safe.evaluate("../outside.json")
        assert error.value.code == ErrorCode.PATH_NOT_ALLOWED


async def test_report_budget_is_exact_and_never_truncates(tmp_path, opa_path):
    report = await evaluate(plan(), tmp_path, opa_path)
    size = len(report.model_dump_json().encode("utf-8"))
    assert (
        await evaluate(plan(), tmp_path, opa_path, max_evaluation_bytes=size)
    ) == report
    with pytest.raises(EvaluationFailure) as error:
        await evaluate(plan(), tmp_path, opa_path, max_evaluation_bytes=size - 1)
    assert error.value.code == EvaluationCode.EVALUATION_LIMIT_EXCEEDED


async def test_resource_order_does_not_change_report(tmp_path, opa_path):
    data = plan()
    data["planned_values"] = {}
    other = deepcopy(data["resource_changes"][0])
    other["address"] = "module.child.aws_db_instance.other"
    other["name"] = "other"
    other["change"]["after"]["storage_encrypted"] = False
    data["resource_changes"].append(other)
    first = await evaluate(data, tmp_path, opa_path)
    data["resource_changes"].reverse()
    assert await evaluate(data, tmp_path, opa_path) == first


async def test_opa_input_excludes_sensitive_and_unrelated_values(
    tmp_path, opa_path, caplog
):
    data = plan()
    change = data["resource_changes"][0]["change"]
    change["after"].update(
        storage_encrypted="SENTINEL_ENCRYPTION", password="SENTINEL_PASSWORD"
    )
    change["after_sensitive"] = {"storage_encrypted": True, "password": True}
    data["variables"] = {"password": {"value": "SENTINEL_VARIABLE"}}
    captured = []
    engine = OpaEngine(EvaluationSettings(opa_path=str(opa_path)))

    class CapturingEngine:
        async def evaluate(self, request, catalog):
            captured.append(request.model_dump_json())
            return await engine.evaluate(request, catalog)

    (tmp_path / "plan.json").write_text(json.dumps(data))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        service = EvaluationService(
            settings,
            EvaluationSettings(opa_path=str(opa_path)),
            loader=loader,
            engine=CapturingEngine(),
        )
        report = await service.evaluate("plan.json")
    assert report.indeterminate_checks[0].reason_code == "RDS_ENCRYPTION_SENSITIVE"
    assert "SENTINEL_" not in "".join(captured) + report.model_dump_json() + caplog.text
    assert "password" not in captured[0]


async def test_analysis_runs_while_evaluation_owns_its_independent_slot(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()

    class BlockingEngine:
        async def evaluate(self, request, catalog):
            started.set()
            await release.wait()
            raise EvaluationFailure(EvaluationCode.OPA_EXECUTION_ERROR)

    (tmp_path / "plan.json").write_text(json.dumps(plan()))
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        service = EvaluationService(
            settings, EvaluationSettings(), loader=loader, engine=BlockingEngine()
        )
        active = asyncio.create_task(service.evaluate("plan.json"))
        try:
            await asyncio.wait_for(started.wait(), 2)
            report = await AnalysisService(settings, loader=loader).analyze("plan.json")
            assert report.summary.total_resources == 1
        finally:
            release.set()
        assert (await active).errors[0].code == "OPA_EXECUTION_ERROR"
