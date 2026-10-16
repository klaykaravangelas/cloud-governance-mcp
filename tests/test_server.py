"""Exercise MCP tool discovery/calls through SDK clients in both protocol modes."""

import asyncio
import json
import logging
import os
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from threading import Event

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

import cloud_governance_mcp.files as files_module
import cloud_governance_mcp.service as service_module
from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.errors import ERROR_MESSAGES, AnalysisError, ErrorCode
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.models import AnalyzeTerraformPlanInput, PlanAnalysis
from cloud_governance_mcp.server import TOOL_NAME, create_server
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures" / "plans"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def plan_root(tmp_path: Path) -> Path:
    for fixture in FIXTURES.glob("*.json"):
        shutil.copyfile(fixture, tmp_path / fixture.name)
    return tmp_path


@pytest.fixture(params=["auto", "legacy"])
async def client(request, plan_root: Path) -> AsyncIterator[Client]:
    """Auto exercises modern MCP; legacy exercises initialize and JSON-RPC streams."""
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        async with Client(
            create_server(AnalysisService(settings, loader=loader)), mode=request.param
        ) as connected:
            yield connected


def assert_tool_error(result: CallToolResult, code: ErrorCode) -> None:
    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == f"{code.value}: {ERROR_MESSAGES[code]}"
    assert "SENTINEL_" not in result.model_dump_json()


async def test_discovery_publishes_only_analysis_and_the_exact_contracts(
    client: Client,
) -> None:
    result = await client.list_tools()
    assert len(result.tools) == 1
    tool = result.tools[0]
    assert tool.name == TOOL_NAME
    assert tool.input_schema == AnalyzeTerraformPlanInput.model_json_schema()
    assert tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["required"] == ["plan_path"]
    assert set(tool.input_schema["properties"]) == {"plan_path"}
    assert tool.output_schema == PlanAnalysis.model_json_schema()
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is False
    assert client.server_capabilities.tools is not None
    assert client.server_capabilities.resources is None
    assert client.server_capabilities.prompts is None


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
async def test_text_and_structured_output_are_the_same_validated_public_report(
    client: Client, filename: str, total: int, changing: int, status: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    result = await client.call_tool(TOOL_NAME, {"plan_path": filename})
    assert not result.is_error
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert json.loads(result.content[0].text) == result.structured_content
    report = PlanAnalysis.model_validate(result.structured_content)
    assert report.summary.total_resources == total
    assert report.summary.changing_resources == changing
    assert report.analysis_status == status
    assert "SENTINEL_" not in result.model_dump_json()
    for key in (
        "unknown_paths",
        "sensitive_paths",
        "unknown_metadata_complete",
        "credentials",
        "password",
        "compliance_status",
    ):
        assert key not in result.content[0].text
    assert "SENTINEL_" not in caplog.text


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {},
        {"SENTINEL_EXTRA_KEY": "SENTINEL_VALUE"},
        {"plan_path": "empty.json", "SENTINEL_EXTRA_KEY": "SENTINEL_VALUE"},
        {"plan_path": None},
        {"plan_path": 1},
        {"plan_path": True},
        {"plan_path": ["SENTINEL_VALUE"]},
        {"plan_path": {"SENTINEL_KEY": "SENTINEL_VALUE"}},
        {"plan_path": ""},
        {"plan_path": " "},
        {"plan_path": "SENTINEL_SECRET\x00.json"},
        {"plan_path": "file:///SENTINEL_SECRET"},
        {"plan_path": "SENTINEL_" + "x" * 4096},
    ],
)
async def test_bad_tool_arguments_are_sanitized_before_sdk_validation_or_file_access(
    client: Client, arguments: dict | None, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def unexpected_read(*args, **kwargs):
        pytest.fail("Rejected tool input reached file access")

    monkeypatch.setattr(RestrictedPlanLoader, "read_plan", unexpected_read)
    result = await client.call_tool(TOOL_NAME, arguments)
    assert_tool_error(result, ErrorCode.INVALID_ARGUMENT)
    assert "SENTINEL_" not in caplog.text


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("../SENTINEL_SECRET.json", ErrorCode.PATH_NOT_ALLOWED),
        ("SENTINEL_MISSING.json", ErrorCode.PLAN_FILE_UNAVAILABLE),
        ("malformed.json", ErrorCode.INVALID_PLAN),
        ('"empty.json"', ErrorCode.PLAN_FILE_UNAVAILABLE),
    ],
)
async def test_expected_service_failures_are_safe_tool_errors(
    client: Client, path: str, code: ErrorCode, caplog
) -> None:
    result = await client.call_tool(TOOL_NAME, {"plan_path": path})
    assert_tool_error(result, code)
    assert "SENTINEL_" not in caplog.text
    assert not (await client.call_tool(TOOL_NAME, {"plan_path": "empty.json"})).is_error


async def test_unknown_tool_is_a_fixed_protocol_error(client: Client, caplog) -> None:
    with pytest.raises(MCPError) as failure:
        await client.call_tool(
            "SENTINEL_UNKNOWN_TOOL", {"SENTINEL_KEY": "SENTINEL_VALUE"}
        )
    assert failure.value.error.code == -32602
    assert failure.value.error.message == "Unknown tool."
    assert "SENTINEL_" not in str(failure.value)
    assert "SENTINEL_" not in caplog.text


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize(
    "failure_kind", ["exception", "invalid_report", "mutated_error"]
)
async def test_transport_sanitizes_unexpected_service_and_response_failures(
    mode: str, failure_kind: str, monkeypatch, plan_root: Path, caplog
) -> None:
    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)

        async def fail(path: str):
            if failure_kind == "invalid_report":
                return {"SENTINEL_REJECTED_FIELD": "SENTINEL_VALUE"}
            if failure_kind == "mutated_error":
                error = AnalysisError(ErrorCode.INVALID_PLAN)
                error.args = ("SENTINEL_EXCEPTION_TEXT",)
                raise error
            raise RuntimeError(f"SENTINEL_EXCEPTION_TEXT {plan_root}")

        monkeypatch.setattr(service, "analyze", fail)
        async with Client(create_server(service), mode=mode) as connected:
            result = await connected.call_tool(TOOL_NAME, {"plan_path": "empty.json"})
    code = (
        ErrorCode.INVALID_PLAN
        if failure_kind == "mutated_error"
        else ErrorCode.INTERNAL_ERROR
    )
    assert_tool_error(result, code)
    assert "SENTINEL_" not in caplog.text
    assert str(plan_root) not in caplog.text
    if code == ErrorCode.INTERNAL_ERROR:
        records = [
            item
            for item in caplog.records
            if item.name == "cloud_governance_mcp.server"
        ]
        assert len(records) == 1
        assert records[0].exc_info is None
        assert re.fullmatch(
            r"Tool failed code=INTERNAL_ERROR request_id=[a-f0-9]{32}",
            records[0].getMessage(),
        )


@pytest.mark.parametrize("limit", ["max_resources", "max_analysis_bytes"])
async def test_limits_become_tool_errors_not_partial_reports(
    limit: str, plan_root: Path
) -> None:
    settings = AnalysisSettings(allowed_roots=[str(plan_root)], **{limit: 1})
    with RestrictedPlanLoader(settings) as loader:
        async with Client(
            create_server(AnalysisService(settings, loader=loader))
        ) as connected:
            result = await connected.call_tool(
                TOOL_NAME, {"plan_path": "mixed_nested.json"}
            )
    assert_tool_error(
        result,
        ErrorCode.PLAN_LIMIT_EXCEEDED
        if limit == "max_resources"
        else ErrorCode.ANALYSIS_LIMIT_EXCEEDED,
    )


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_concurrent_sdk_calls_reject_overlap_without_queuing(
    mode: str, plan_root: Path, monkeypatch
) -> None:
    entered, release = Event(), Event()
    read = files_module._read_bounded

    def blocked_read(descriptor: int, limit: int) -> bytes:
        entered.set()
        assert release.wait(5), "Test did not release active MCP analysis"
        return read(descriptor, limit)

    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        async with Client(
            create_server(AnalysisService(settings, loader=loader)), mode=mode
        ) as connected:
            with monkeypatch.context() as patch:
                patch.setattr(files_module, "_read_bounded", blocked_read)
                first = asyncio.create_task(
                    connected.call_tool(TOOL_NAME, {"plan_path": "empty.json"})
                )
                try:
                    assert await asyncio.to_thread(entered.wait, 2)
                    result = await connected.call_tool(
                        TOOL_NAME, {"plan_path": "empty.json"}
                    )
                    assert_tool_error(result, ErrorCode.SERVER_BUSY)
                finally:
                    release.set()
                    assert not (await asyncio.wait_for(first, 3)).is_error
            assert not (
                await connected.call_tool(TOOL_NAME, {"plan_path": "empty.json"})
            ).is_error


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_sdk_cancellation_reaches_service_and_closes_the_active_file(
    mode: str, plan_root: Path, monkeypatch, caplog
) -> None:
    entered, release = Event(), Event()
    cleanup_started, cleanup_finished = asyncio.Event(), asyncio.Event()
    descriptors: list[int] = []
    read = files_module._read_bounded
    finish = service_module._finish_worker

    def blocked_read(descriptor: int, limit: int) -> bytes:
        descriptors.append(descriptor)
        entered.set()
        assert release.wait(5), "Test did not release cancelled MCP analysis"
        return read(descriptor, limit)

    async def observe_cleanup(worker):
        cleanup_started.set()
        try:
            await finish(worker)
        finally:
            cleanup_finished.set()

    settings = AnalysisSettings(allowed_roots=[str(plan_root)])
    with RestrictedPlanLoader(settings) as loader:
        async with Client(
            create_server(AnalysisService(settings, loader=loader)), mode=mode
        ) as connected:
            with monkeypatch.context() as patch:
                patch.setattr(files_module, "_read_bounded", blocked_read)
                patch.setattr(service_module, "_finish_worker", observe_cleanup)
                pending = asyncio.create_task(
                    connected.call_tool(TOOL_NAME, {"plan_path": "empty.json"})
                )
                try:
                    assert await asyncio.to_thread(entered.wait, 2)
                    pending.cancel()
                    # Wait for actual server-side cancellation, rather than
                    # assuming client cancellation reached the handler already.
                    # The direct in-process client joins the handler before its
                    # cancellation finishes; the legacy client can return sooner.
                    await asyncio.wait_for(cleanup_started.wait(), 2)
                    os.fstat(descriptors[0])
                    busy = await connected.call_tool(
                        TOOL_NAME, {"plan_path": "empty.json"}
                    )
                    assert_tool_error(busy, ErrorCode.SERVER_BUSY)
                finally:
                    release.set()
                    if not pending.done():
                        pending.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(pending, 3)
                await asyncio.wait_for(cleanup_finished.wait(), 3)
            with pytest.raises(OSError):
                os.fstat(descriptors[0])
            assert not (
                await connected.call_tool(TOOL_NAME, {"plan_path": "empty.json"})
            ).is_error
    assert "SENTINEL_" not in caplog.text
