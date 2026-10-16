"""Test real service pipelines, safe failures and cancellation with local files."""

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from threading import Event, get_ident

import anyio
import pytest

import cloud_governance_mcp.files as files_module
import cloud_governance_mcp.service as service_module
from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.models import PlanAnalysis, ResourceSnapshot
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures" / "plans"


@pytest.fixture
def anyio_backend() -> str:
    """The service targets asyncio, also used by the planned stdio entrypoint."""
    return "asyncio"


@pytest.fixture
def plan_root(tmp_path: Path) -> Path:
    for fixture in FIXTURES.glob("*.json"):
        shutil.copyfile(fixture, tmp_path / fixture.name)
    return tmp_path


@pytest.mark.parametrize(
    ("filename", "total", "changing", "status"),
    [
        ("mixed_nested.json", 7, 4, "partial"),
        ("empty.json", 0, 0, "complete"),
        ("partial.json", 1, 0, "partial"),
        ("unknown_sensitive.json", 2, 2, "partial"),
        ("encrypted_rds.json", 1, 1, "complete"),
        ("unencrypted_rds.json", 1, 1, "complete"),
    ],
)
async def test_real_analysis_pipeline(
    filename: str, total: int, changing: int, status: str, plan_root: Path, caplog
) -> None:
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    original = (plan_root / filename).read_bytes()
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)
        report = await service.analyze(filename)
        assert await service.analyze(str(plan_root / filename)) == report
    assert report.summary.total_resources == total
    assert report.summary.changing_resources == changing
    assert report.analysis_status == status
    assert "SENTINEL_" not in report.model_dump_json()
    assert str(plan_root) not in report.model_dump_json()
    assert caplog.text == ""
    assert (plan_root / filename).read_bytes() == original


@pytest.mark.parametrize(
    "value", [None, 3, True, {}, [], "", " ", "file:///secret", "bad\x00name"]
)
async def test_arguments_are_validated_before_file_access(
    value: object, plan_root: Path
) -> None:
    class UntouchedLoader:
        def read_plan(self, plan_path: str) -> object:
            pytest.fail("Invalid arguments reached the loader")

    service = AnalysisService(
        AnalysisSettings(allowed_roots=[str(plan_root)]), loader=UntouchedLoader()
    )
    with pytest.raises(AnalysisError) as failure:
        await service.analyze(value)
    assert failure.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("missing.json", ErrorCode.PLAN_FILE_UNAVAILABLE),
        ("../escape.json", ErrorCode.PATH_NOT_ALLOWED),
        ("malformed.json", ErrorCode.INVALID_PLAN),
        ("invalid.json", ErrorCode.INVALID_JSON),
        ("state.json", ErrorCode.INVALID_PLAN),
        ("future.json", ErrorCode.UNSUPPORTED_PLAN_VERSION),
        ("unsupported.json", ErrorCode.UNSUPPORTED_PLAN_FEATURE),
    ],
)
async def test_known_failures_preserve_safe_codes_and_release_admission(
    filename: str, code: ErrorCode, plan_root: Path, caplog
) -> None:
    (plan_root / "invalid.json").write_text('{"SENTINEL_BAD_JSON":')
    (plan_root / "state.json").write_text('{"format_version":"1.0","values":{}}')
    (plan_root / "future.json").write_text(
        '{"format_version":"2.0","resource_changes":[]}'
    )
    document = json.loads((plan_root / "encrypted_rds.json").read_text())
    document["resource_changes"][0]["change"]["actions"] = ["SENTINEL_UNKNOWN_ACTION"]
    (plan_root / "unsupported.json").write_text(json.dumps(document))
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)
        with pytest.raises(AnalysisError) as failure:
            await service.analyze(filename)
        assert failure.value.code == code
        assert failure.value.__suppress_context__
        assert "SENTINEL_" not in str(failure.value)
        assert str(plan_root) not in str(failure.value)
        assert (await service.analyze("empty.json")).summary.total_resources == 0
    assert caplog.text == ""


@pytest.mark.parametrize("budget_offset", [0, -1])
async def test_output_limit_uses_compact_utf8_bytes_without_truncation(
    budget_offset: int, plan_root: Path
) -> None:
    # Non-ASCII identities distinguish UTF-8 bytes from Python character count.
    document = json.loads((plan_root / "encrypted_rds.json").read_text())
    for entry in (
        document["resource_changes"][0],
        document["planned_values"]["root_module"]["resources"][0],
    ):
        entry["address"] = "aws_db_instance.例子"
        entry["name"] = "例子"
    (plan_root / "unicode.json").write_text(json.dumps(document))
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        expected = await AnalysisService(settings, loader=loader).analyze(
            "unicode.json"
        )
        encoded = expected.model_dump_json()
        assert len(encoded.encode("utf-8")) > len(encoded)
        bounded = settings.model_copy(
            update={"max_analysis_bytes": len(encoded.encode("utf-8")) + budget_offset}
        )
        service = AnalysisService(bounded, loader=loader)
        if budget_offset == 0:
            assert await service.analyze("unicode.json") == expected
        else:
            with pytest.raises(AnalysisError) as failure:
                await service.analyze("unicode.json")
            assert failure.value.code == ErrorCode.ANALYSIS_LIMIT_EXCEEDED
            assert (await service.analyze("empty.json")).summary.total_resources == 0


@pytest.mark.parametrize("field", ["max_plan_bytes", "max_json_depth", "max_resources"])
async def test_configured_input_limits_reach_the_real_pipeline(
    field: str, plan_root: Path
) -> None:
    settings = AnalysisSettings(allowed_roots=[str(plan_root)], **{field: 1})
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)
        with pytest.raises(AnalysisError) as failure:
            await service.analyze("mixed_nested.json")
    assert failure.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED


async def test_entire_pipeline_runs_off_the_event_loop(
    monkeypatch, plan_root: Path
) -> None:
    main_thread = get_ident()
    stages: dict[str, int] = {}
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    real_summarize = service_module.summarize
    real_serialize = PlanAnalysis.model_dump_json

    class ObservedAdapter:
        def normalize(self, document: object) -> ResourceSnapshot:
            stages["normalize"] = get_ident()
            return TerraformPlanAdapter().normalize(document)

    def summarize(snapshot: ResourceSnapshot) -> PlanAnalysis:
        stages["summarize"] = get_ident()
        return real_summarize(snapshot)

    def serialize(report: PlanAnalysis, **kwargs) -> str:
        stages["serialize"] = get_ident()
        return real_serialize(report, **kwargs)

    monkeypatch.setattr(service_module, "summarize", summarize)
    monkeypatch.setattr(PlanAnalysis, "model_dump_json", serialize)
    with RestrictedPlanLoader(settings) as loader:

        class ObservedLoader:
            def read_plan(self, path: str) -> object:
                stages["read"] = get_ident()
                return loader.read_plan(path)

        service = AnalysisService(
            settings, loader=ObservedLoader(), adapter=ObservedAdapter()
        )
        assert (await service.analyze("empty.json")).summary.total_resources == 0
    assert set(stages) == {"read", "normalize", "summarize", "serialize"}
    assert all(thread != main_thread for thread in stages.values())
    assert len(set(stages.values())) == 1


@pytest.mark.parametrize(
    "stage", ["read", "normalize", "summarize", "serialize", "submit"]
)
async def test_unexpected_failures_are_sanitized_and_slot_is_reusable(
    stage: str, monkeypatch, plan_root: Path, caplog
) -> None:
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    secret = f"SENTINEL_INTERNAL_SECRET {plan_root}"

    def fail(*args, **kwargs):
        raise RuntimeError(secret)

    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)
        with monkeypatch.context() as patch:
            target, name = {
                "read": (loader, "read_plan"),
                "normalize": (service._adapter, "normalize"),
                "summarize": (service_module, "summarize"),
                "serialize": (PlanAnalysis, "model_dump_json"),
                "submit": (asyncio.get_running_loop(), "run_in_executor"),
            }[stage]
            patch.setattr(target, name, fail)
            with pytest.raises(AnalysisError) as failure:
                await service.analyze("empty.json")
        assert failure.value.code == ErrorCode.INTERNAL_ERROR
        assert failure.value.__suppress_context__
        assert "SENTINEL_" not in str(failure.value)
        assert (await service.analyze("empty.json")).analysis_status == "complete"
    records = [
        record
        for record in caplog.records
        if record.name == "cloud_governance_mcp.service"
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert re.fullmatch(
        r"Analysis failed code=INTERNAL_ERROR request_id=[a-f0-9]{32}",
        records[0].getMessage(),
    )
    assert records[0].exc_info is None
    assert "SENTINEL_" not in caplog.text
    assert str(plan_root) not in caplog.text


@pytest.mark.parametrize("worker_error", [False, True])
async def test_native_cancellation_joins_real_read_closes_descriptor_and_rejects_overlap(
    worker_error: bool, monkeypatch, plan_root: Path, caplog
) -> None:
    entered, release = Event(), Event()
    observed: list[int] = []
    read = files_module._read_bounded

    def blocked_read(descriptor: int, limit: int) -> bytes:
        observed.append(descriptor)
        entered.set()
        assert release.wait(5), "Test did not release blocked file read"
        if worker_error:
            raise RuntimeError("SENTINEL_CANCELLED_WORKER_ERROR")
        return read(descriptor, limit)

    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)
        with monkeypatch.context() as patch:
            patch.setattr(files_module, "_read_bounded", blocked_read)
            task = asyncio.create_task(service.analyze("empty.json"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                os.fstat(observed[0])  # Cancellation begins while a real file is open.
                task.cancel()
                await asyncio.sleep(0)
                with pytest.raises(AnalysisError) as failure:
                    await service.analyze("empty.json")
                assert failure.value.code == ErrorCode.SERVER_BUSY
                task.cancel()  # Repeated cancellation must not abandon the worker.
                await asyncio.sleep(0)
                assert not task.done()
            finally:
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 3)
        with pytest.raises(OSError):
            os.fstat(observed[0])
        assert (await service.analyze("empty.json")).analysis_status == "complete"
    assert "SENTINEL_" not in caplog.text


async def test_anyio_scope_cancellation_waits_for_worker_and_preserves_cancellation(
    monkeypatch, plan_root: Path
) -> None:
    entered, release = Event(), Event()
    finished = anyio.Event()
    succeeded = False
    read = files_module._read_bounded

    def blocked_read(descriptor: int, limit: int) -> bytes:
        entered.set()
        assert release.wait(5), "Test did not release blocked file read"
        return read(descriptor, limit)

    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)

        async def request(*, task_status=anyio.TASK_STATUS_IGNORED) -> None:
            nonlocal succeeded
            with anyio.CancelScope() as scope:
                task_status.started(scope)
                await service.analyze("empty.json")
                succeeded = True
            finished.set()

        with monkeypatch.context() as patch:
            patch.setattr(files_module, "_read_bounded", blocked_read)
            async with anyio.create_task_group() as group:
                scope = await group.start(request)
                try:
                    assert await asyncio.to_thread(entered.wait, 2)
                    scope.cancel()
                    await anyio.sleep(0)
                    with pytest.raises(AnalysisError) as failure:
                        await service.analyze("empty.json")
                    assert failure.value.code == ErrorCode.SERVER_BUSY
                    assert not finished.is_set()
                finally:
                    release.set()
                with anyio.fail_after(3):
                    await finished.wait()
            assert scope.cancelled_caught
            assert not succeeded
        assert (await service.analyze("empty.json")).analysis_status == "complete"


async def test_already_cancelled_scope_never_starts_file_access(
    plan_root: Path,
) -> None:
    class UntouchedLoader:
        def read_plan(self, path: str) -> object:
            pytest.fail("Cancelled request reached the loader")

    service = AnalysisService(
        AnalysisSettings(allowed_roots=[str(plan_root)]), loader=UntouchedLoader()
    )
    with anyio.CancelScope() as scope:
        scope.cancel()
        await service.analyze("empty.json")
    assert scope.cancelled_caught


async def test_overlap_is_rejected_without_queuing_or_blocking_the_event_loop(
    plan_root: Path,
) -> None:
    entered, release = Event(), Event()
    calls = 0
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:

        class GatedLoader:
            def read_plan(self, path: str) -> object:
                nonlocal calls
                calls += 1
                entered.set()
                assert release.wait(5), "Test did not release the active analysis"
                return loader.read_plan(path)

        service = AnalysisService(settings, loader=GatedLoader())
        first = asyncio.create_task(service.analyze("empty.json"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            # Validation happens before admission; malformed arguments do not
            # become misleading busy errors just because another call is active.
            with pytest.raises(AnalysisError) as failure:
                await service.analyze(None)
            assert failure.value.code == ErrorCode.INVALID_ARGUMENT
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(service.analyze("empty.json") for _ in range(3)),
                    return_exceptions=True,
                ),
                2,
            )
            assert all(
                isinstance(result, AnalysisError)
                and result.code == ErrorCode.SERVER_BUSY
                for result in results
            )
            # One shared service also rejects a caller from a different event loop.
            with pytest.raises(AnalysisError) as failure:
                await asyncio.to_thread(asyncio.run, service.analyze("empty.json"))
            assert failure.value.code == ErrorCode.SERVER_BUSY
            assert calls == 1
        finally:
            release.set()
            assert (await asyncio.wait_for(first, 3)).analysis_status == "complete"
        assert (await service.analyze("empty.json")).analysis_status == "complete"
        assert calls == 2
