"""Run the installed server as real stdio subprocesses outside the checkout."""

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from cloud_governance_mcp.errors import ERROR_MESSAGES, ErrorCode
from cloud_governance_mcp.models import PlanAnalysis
from cloud_governance_mcp.server import TOOL_NAME

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures" / "plans"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_real_sdk_stdio_discovery_analysis_safe_errors_and_shutdown(
    mode: str, tmp_path: Path
) -> None:
    root, outside = tmp_path / "plans", tmp_path / "untrusted-cwd"
    root.mkdir()
    outside.mkdir()
    for fixture in FIXTURES.glob("*.json"):
        shutil.copyfile(fixture, root / fixture.name)
    shutil.copyfile(FIXTURES / "empty.json", outside / "SENTINEL_OUTSIDE.json")
    # Exercise the console script and isolated module launch. A blank executable
    # search path also proves the server needs no Terraform/OPA commands.
    if mode == "auto":
        command = str(Path(sys.executable).parent / "cloud-governance-mcp")
        arguments = []
    else:
        command = sys.executable
        arguments = ["-I", "-m", "cloud_governance_mcp"]
    parameters = StdioServerParameters(
        command=command,
        args=[*arguments, "--allowed-root", str(root)],
        cwd=outside,
        env={"PATH": ""},
    )
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
        async with Client(
            stdio_client(parameters, errlog=stderr), mode=mode, read_timeout_seconds=5
        ) as client:
            discovery = await client.list_tools()
            assert [tool.name for tool in discovery.tools] == [
                TOOL_NAME,
                "evaluate_terraform_policies",
            ]
            tool = discovery.tools[0]
            assert tool.input_schema["additionalProperties"] is False
            assert tool.output_schema is not None
            for filename, total in [
                ("mixed_nested.json", 7),
                ("unknown_sensitive.json", 2),
            ]:
                result = await client.call_tool(TOOL_NAME, {"plan_path": filename})
                assert not result.is_error
                assert json.loads(result.content[0].text) == result.structured_content
                assert (
                    PlanAnalysis.model_validate(
                        result.structured_content
                    ).summary.total_resources
                    == total
                )
                assert "SENTINEL_" not in result.model_dump_json()
                assert "unknown_paths" not in result.model_dump_json()
            for arguments, code in [
                (
                    {"plan_path": str(outside / "SENTINEL_OUTSIDE.json")},
                    ErrorCode.PATH_NOT_ALLOWED,
                ),
                ({"plan_path": "malformed.json"}, ErrorCode.INVALID_PLAN),
                (
                    {"plan_path": "empty.json", "SENTINEL_EXTRA_KEY": "SENTINEL_VALUE"},
                    ErrorCode.INVALID_ARGUMENT,
                ),
                (
                    {"plan_path": {"SENTINEL_KEY": "SENTINEL_VALUE"}},
                    ErrorCode.INVALID_ARGUMENT,
                ),
            ]:
                result = await client.call_tool(TOOL_NAME, arguments)
                assert result.is_error
                assert result.structured_content is None
                assert result.content[0].text == f"{code.value}: {ERROR_MESSAGES[code]}"
                assert "SENTINEL_" not in result.model_dump_json()
            # An error must not leave the shared service's active slot occupied.
            assert not (
                await client.call_tool(TOOL_NAME, {"plan_path": "empty.json"})
            ).is_error
        stderr.seek(0)
        assert stderr.read() == ""


async def test_raw_stdio_frames_have_safe_pre_handler_errors_and_protocol_only_stdout(
    tmp_path: Path,
) -> None:
    shutil.copyfile(FIXTURES / "empty.json", tmp_path / "empty.json")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        "cloud_governance_mcp",
        "--allowed-root",
        str(tmp_path),
        cwd=tmp_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    frames: list[dict] = []

    async def send(message: dict) -> None:
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()

    async def exchange(request_id: int, method: str, params: dict) -> dict:
        await send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        line = await asyncio.wait_for(process.stdout.readline(), 5)
        frame = json.loads(line)
        assert frame["jsonrpc"] == "2.0"
        assert frame["id"] == request_id
        frames.append(frame)
        return frame

    try:
        initialized = await exchange(
            1,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "synthetic-test-client", "version": "1"},
            },
        )
        assert "tools" in initialized["result"]["capabilities"]
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listing = await exchange(2, "tools/list", {})
        assert [tool["name"] for tool in listing["result"]["tools"]] == [
            TOOL_NAME,
            "evaluate_terraform_policies",
        ]

        # These fail protocol validation before our handler. The SDK must use its
        # fixed INVALID_PARAMS response, never Pydantic excerpts or input keys.
        for request_id, arguments in [
            (3, ["SENTINEL_BAD_SHAPE"]),
            (4, "SENTINEL_BAD_SHAPE"),
        ]:
            result = await exchange(
                request_id, "tools/call", {"name": TOOL_NAME, "arguments": arguments}
            )
            assert result["error"]["code"] == -32602
            assert result["error"]["message"] == "Invalid request parameters"
            assert "SENTINEL_" not in json.dumps(result)

        invalid_tool_input = await exchange(
            5,
            "tools/call",
            {
                "name": TOOL_NAME,
                "arguments": {
                    "plan_path": "empty.json",
                    "SENTINEL_EXTRA_KEY": "SENTINEL_VALUE",
                },
            },
        )
        assert invalid_tool_input["result"]["isError"] is True
        assert (
            invalid_tool_input["result"]["content"][0]["text"]
            == "INVALID_ARGUMENT: Invalid analysis arguments."
        )

        # A malformed JSON frame is outside the tool API. Confirm the connection
        # recovers without printing its parser exception or the rejected payload.
        process.stdin.write(b'{"SENTINEL_MALFORMED_FRAME":\n')
        await process.stdin.drain()
        success = await exchange(
            6,
            "tools/call",
            {"name": TOOL_NAME, "arguments": {"plan_path": "empty.json"}},
        )
        assert success["result"]["isError"] is False
        assert success["result"]["structuredContent"]["summary"]["total_resources"] == 0
        assert (
            json.loads(success["result"]["content"][0]["text"])
            == success["result"]["structuredContent"]
        )
    finally:
        process.stdin.close()
        try:
            remaining_stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
    assert process.returncode == 0
    assert remaining_stdout == stderr == b""
    assert "SENTINEL_" not in json.dumps(frames)
