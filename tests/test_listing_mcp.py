"""Exercise policy discovery over public SDK clients and installed stdio."""

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.catalog import load_catalog
from cloud_governance_mcp.config import AnalysisSettings, EvaluationSettings
from cloud_governance_mcp.engine.opa import OpaEngine
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.listing import PolicyListingService, project_catalog
from cloud_governance_mcp.listing_errors import (
    LISTING_MESSAGES,
    ListingCode,
    ListingFailure,
)
from cloud_governance_mcp.listing_models import ListPoliciesInput, PolicyList
from cloud_governance_mcp.server import create_server
from cloud_governance_mcp.service import AnalysisService

pytestmark = pytest.mark.anyio
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("opa_kind", ["unconfigured", "missing", "unsupported"])
async def test_sdk_listing_has_no_plan_or_evaluator_dependency(
    mode, opa_kind, tmp_path, monkeypatch, caplog
):
    def forbidden(*args, **kwargs):
        pytest.fail("Listing crossed a plan/evaluation boundary")

    # An executable with a sentinel side effect proves that even version probing
    # is absent. This is a synthetic test runtime, never a production executable.
    binary = tmp_path / "unsupported-opa"
    marker = tmp_path / "SENTINEL_PROBED"
    binary.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 1\n')
    binary.chmod(0o700)
    opa = (
        None
        if opa_kind == "unconfigured"
        else str(binary if opa_kind == "unsupported" else tmp_path / "missing")
    )
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        evaluation = EvaluationService(
            settings, EvaluationSettings(opa_path=opa), loader=loader
        )
        server = create_server(
            AnalysisService(settings, loader=loader), evaluation, PolicyListingService()
        )
        monkeypatch.setattr(RestrictedPlanLoader, "read_plan", forbidden)
        monkeypatch.setattr(TerraformPlanAdapter, "normalize", forbidden)
        monkeypatch.setattr(EvaluationService, "evaluate", forbidden)
        monkeypatch.setattr(OpaEngine, "evaluate", forbidden)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
        async with Client(server, mode=mode) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == [
                "analyze_terraform_plan",
                "evaluate_terraform_policies",
                "list_policies",
            ]
            tool = tools[2]
            assert tool.input_schema == ListPoliciesInput.model_json_schema()
            assert tool.output_schema == PolicyList.model_json_schema()
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.open_world_hint is False
            for arguments in ({}, None):
                result = await client.call_tool("list_policies", arguments)
                assert result.is_error is False
                assert json.loads(result.content[0].text) == result.structured_content
                assert PolicyList.model_validate(
                    result.structured_content
                ) == project_catalog(load_catalog())
            invalid = await client.call_tool(
                "list_policies", {"SENTINEL_KEY": "SENTINEL_VALUE"}
            )
            assert invalid.is_error and invalid.structured_content is None
            assert (
                invalid.content[0].text
                == "INVALID_ARGUMENT: Invalid policy listing arguments."
            )
            assert "SENTINEL" not in invalid.model_dump_json()
            assert not (await client.call_tool("list_policies")).is_error
    assert not marker.exists()
    assert "SENTINEL" not in caplog.text


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize(
    "failure_kind",
    ["exception", "invalid_result", "mutated_error", "asset", "limit", "busy"],
)
async def test_transport_sanitizes_listing_failures_and_invalid_service_reports(
    mode, failure_kind, tmp_path, caplog
):
    class BrokenListing:
        async def list_policies(self):
            if failure_kind == "invalid_result":
                return {"SENTINEL_KEY": "SENTINEL_VALUE"}
            codes = {
                "mutated_error": ListingCode.INVALID_ARGUMENT,
                "asset": ListingCode.POLICY_ASSETS_INVALID,
                "limit": ListingCode.POLICY_LIST_LIMIT_EXCEEDED,
                "busy": ListingCode.SERVER_BUSY,
            }
            if failure_kind in codes:
                error = ListingFailure(codes[failure_kind])
                error.args = ("SENTINEL_EXCEPTION",)
                raise error
            raise RuntimeError("SENTINEL_EXCEPTION")

    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        server = create_server(
            AnalysisService(settings, loader=loader), listing_service=BrokenListing()
        )
        async with Client(server, mode=mode) as client:
            result = await client.call_tool("list_policies", {})
    code = {
        "mutated_error": ListingCode.INVALID_ARGUMENT,
        "asset": ListingCode.POLICY_ASSETS_INVALID,
        "limit": ListingCode.POLICY_LIST_LIMIT_EXCEEDED,
        "busy": ListingCode.SERVER_BUSY,
    }.get(failure_kind, ListingCode.INTERNAL_ERROR)
    assert result.is_error and result.structured_content is None
    assert result.content[0].text == f"{code.value}: {LISTING_MESSAGES[code]}"
    assert "SENTINEL" not in result.model_dump_json() + caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_real_stdio_listing_recovers_and_leaves_analysis_usable(mode, tmp_path):
    shutil.copyfile(ROOT / "tests/fixtures/plans/empty.json", tmp_path / "empty.json")
    connection = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-m", "cloud_governance_mcp", "--allowed-root", str(tmp_path)],
        cwd=tmp_path,
        env={"PATH": ""},
    )
    async with Client(connection, mode=mode) as client:
        assert len((await client.list_tools()).tools) == 3
        assert not (await client.call_tool("list_policies")).is_error
        assert (
            await client.call_tool("list_policies", {"SENTINEL": "SENTINEL"})
        ).is_error
        assert not (
            await client.call_tool(
                "analyze_terraform_plan", {"plan_path": "empty.json"}
            )
        ).is_error
        assert not (await client.call_tool("list_policies", {})).is_error


@pytest.mark.parametrize("legacy", [False, True])
async def test_listing_example_matches_saved_report_outside_checkout(legacy, tmp_path):
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            str(ROOT / "examples/client.py"),
            "--list-policies",
            *(["--legacy"] if legacy else []),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    expected = json.loads((ROOT / "examples/reports/policy-list.json").read_text())
    assert json.loads(result.stdout) == expected
    assert PolicyList.model_validate(expected) == project_catalog(load_catalog())


async def test_active_listing_does_not_block_analysis_or_evaluation(tmp_path):
    """Separate admission slots let the two plan tools run during a catalog read."""
    shutil.copyfile(ROOT / "tests/fixtures/plans/empty.json", tmp_path / "empty.json")
    entered, release = Event(), Event()

    def slow_catalog():
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Listing test did not release its worker")
        return load_catalog()

    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    with RestrictedPlanLoader(settings) as loader:
        analysis = AnalysisService(settings, loader=loader)
        evaluation = EvaluationService(settings, EvaluationSettings(), loader=loader)
        listing = PolicyListingService(catalog_loader=slow_catalog)
        async with Client(create_server(analysis, evaluation, listing)) as client:
            pending = asyncio.create_task(client.call_tool("list_policies"))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                busy = await client.call_tool("list_policies")
                assert busy.is_error and busy.content[0].text.startswith("SERVER_BUSY:")
                assert not (
                    await client.call_tool(
                        "analyze_terraform_plan", {"plan_path": "empty.json"}
                    )
                ).is_error
                # The evaluator reaches its own configuration check, independently
                # of listing admission. Its missing-OPA error remains unchanged.
                result = await client.call_tool(
                    "evaluate_terraform_policies", {"plan_path": "empty.json"}
                )
                assert result.is_error
                assert (
                    result.structured_content["errors"][0]["code"]
                    == "OPA_NOT_CONFIGURED"
                )
            finally:
                release.set()
                assert not (await pending).is_error
