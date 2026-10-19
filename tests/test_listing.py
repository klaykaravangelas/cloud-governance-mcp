"""Verify catalog-only listing, safe failures, budgets and worker cleanup."""

import asyncio
import json
import logging
from threading import Event, get_ident

import anyio
import pytest
from pydantic import ValidationError

import cloud_governance_mcp.catalog as catalog_module
import cloud_governance_mcp.listing as listing_module
from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.listing import PolicyListingService, project_catalog
from cloud_governance_mcp.listing_errors import ListingCode, ListingFailure
from cloud_governance_mcp.listing_models import (
    ListPoliciesInput,
    PolicyList,
    validate_listing_input,
)


@pytest.mark.parametrize("arguments", [{}, None])
def test_empty_input_and_sdk_no_arguments_are_accepted(arguments):
    assert validate_listing_input(arguments) == ListPoliciesInput()
    schema = ListPoliciesInput.model_json_schema()
    assert schema["properties"] == {}
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "arguments",
    [{"SENTINEL_KEY": "SENTINEL_VALUE"}, [], ["SENTINEL"], "SENTINEL", 1, True],
)
def test_invalid_input_has_no_rejected_keys_or_values(arguments):
    with pytest.raises(ListingFailure) as failure:
        validate_listing_input(arguments)
    assert str(failure.value) == "INVALID_ARGUMENT: Invalid policy listing arguments."
    assert failure.value.__suppress_context__


def test_public_metadata_is_the_selectable_catalog_projection():
    catalog = load_catalog()
    report = project_catalog(catalog)
    assert report == project_catalog(catalog)
    assert report.schema_version == "1"
    assert len(report.policies) == 1
    public = report.policies[0]
    internal = catalog.select([public.policy_id])[0]
    for field in type(public).model_fields:
        assert getattr(public, field) == getattr(internal, field)
    assert public.supported_resource_types == ["aws_db_instance"]
    assert public.required_configuration == []
    assert "cluster associations are not resolved" in public.scope_description
    assert set(internal.model_dump()) - set(public.model_dump()) == {
        "enabled",
        "reasons",
    }
    assert PolicyList.model_validate_json(report.model_dump_json()) == report
    # Modifying a caller's public list cannot alter the internal catalog.
    public.supported_resource_types.clear()
    assert internal.supported_resource_types == ["aws_db_instance"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"required_configuration": ["SENTINEL_CONFIG"]},
        {"supported_resource_types": ["aws_rds_cluster"]},
        {"enabled": False},
        {"policy_id": "AWS-SG-001"},
        {"reasons": {}},
    ],
)
def test_catalog_cannot_advertise_unimplemented_or_incomplete_scope(mutation):
    document = load_catalog().model_dump()
    document["policies"][0].update(mutation)
    with pytest.raises(ValidationError):
        PolicyCatalog.model_validate(document)


def test_public_contract_rejects_duplicates_and_internal_fields():
    document = project_catalog(load_catalog()).model_dump()
    document["policies"] *= 2
    with pytest.raises(ValidationError):
        PolicyList.model_validate(document)
    document["policies"] = document["policies"][:1]
    document["policies"][0]["reasons"] = {"SENTINEL": "SENTINEL"}
    with pytest.raises(ValidationError):
        PolicyList.model_validate(document)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        b"\xff",
        b'{"secret":',
        b'{"a":1,"a":2}',
        b" " * 65_537,
        b"{}",
        b'{"cloud_governance_catalog":{}}',
    ],
)
async def test_real_asset_loading_failures_are_safe_and_never_empty_success(
    payload, tmp_path, monkeypatch, caplog
):
    if payload is not None:
        (tmp_path / "catalog.json").write_bytes(payload)
    monkeypatch.setattr(catalog_module, "files", lambda _: tmp_path)
    with pytest.raises(ListingFailure) as failure:
        await PolicyListingService().list_policies()
    assert failure.value.code == ListingCode.POLICY_ASSETS_INVALID
    assert caplog.text == ""


@pytest.mark.anyio
async def test_configuration_requirements_are_required_in_packaged_metadata(
    tmp_path, monkeypatch
):
    document = load_catalog().model_dump()
    del document["policies"][0]["required_configuration"]
    (tmp_path / "catalog.json").write_text(
        json.dumps({"cloud_governance_catalog": document})
    )
    monkeypatch.setattr(catalog_module, "files", lambda _: tmp_path)
    with pytest.raises(ListingFailure, match="^POLICY_ASSETS_INVALID:"):
        await PolicyListingService().list_policies()


@pytest.mark.anyio
@pytest.mark.parametrize("offset", [0, -1])
async def test_limit_counts_complete_compact_utf8_bytes(offset, monkeypatch):
    assert listing_module.MAX_POLICY_LIST_BYTES == 65_536
    catalog = load_catalog()
    catalog.policies[0].title = "例子"
    expected = project_catalog(catalog)
    text = expected.model_dump_json()
    assert len(text.encode("utf-8")) > len(text)
    monkeypatch.setattr(
        listing_module, "MAX_POLICY_LIST_BYTES", len(text.encode("utf-8")) + offset
    )
    service = PolicyListingService(catalog_loader=lambda: catalog)
    if offset == 0:
        assert await service.list_policies() == expected
    else:
        with pytest.raises(ListingFailure) as failure:
            await service.list_policies()
        assert failure.value.code == ListingCode.POLICY_LIST_LIMIT_EXCEEDED
        monkeypatch.setattr(listing_module, "MAX_POLICY_LIST_BYTES", 65_536)
        assert await service.list_policies() == expected


@pytest.mark.anyio
async def test_all_catalog_and_serialization_work_runs_off_loop(monkeypatch):
    main_thread = get_ident()
    observed = []
    serialize = PolicyList.model_dump_json

    def loader():
        observed.append(get_ident())
        return load_catalog()

    def measured(self, *args, **kwargs):
        observed.append(get_ident())
        return serialize(self, *args, **kwargs)

    monkeypatch.setattr(PolicyList, "model_dump_json", measured)
    service = PolicyListingService(catalog_loader=loader)
    assert await service.list_policies() == project_catalog(load_catalog())
    assert len(observed) == 2 and all(t != main_thread for t in observed)


@pytest.mark.anyio
@pytest.mark.parametrize("failure_kind", ["unexpected", "evaluation", "invalid_result"])
async def test_worker_failures_are_codes_with_safe_logs_and_recovery(
    failure_kind, caplog
):
    attempts = 0

    def loader():
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            return load_catalog()
        if failure_kind == "unexpected":
            raise RuntimeError("SENTINEL_WORKER")
        if failure_kind == "evaluation":
            raise EvaluationFailure(EvaluationCode.OPA_EXECUTION_ERROR)
        return {"SENTINEL": "SENTINEL"}

    service = PolicyListingService(catalog_loader=loader)
    with caplog.at_level(logging.ERROR), pytest.raises(ListingFailure) as failure:
        await service.list_policies()
    assert failure.value.code == ListingCode.INTERNAL_ERROR
    assert "code=INTERNAL_ERROR request_id=" in caplog.text
    assert "SENTINEL" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert await service.list_policies() == project_catalog(load_catalog())


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_kind", ["native", "repeated", "anyio"])
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_busy_and_cancellation_wait_for_worker_cleanup_then_recover(
    cancel_kind, worker_fails, caplog
):
    entered, release, finished = Event(), Event(), Event()
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            try:
                if not release.wait(5):
                    raise RuntimeError("SENTINEL_DEADLOCK")
                if worker_fails:
                    raise RuntimeError("SENTINEL_CANCELLED_FAILURE")
            finally:
                finished.set()
        return load_catalog()

    service = PolicyListingService(catalog_loader=loader)
    scope = anyio.CancelScope()

    async def call():
        with scope:
            await service.list_policies()

    task = asyncio.create_task(call())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        # The blocked worker leaves the event loop responsive and admission closed.
        with pytest.raises(ListingFailure, match="^SERVER_BUSY:"):
            await service.list_policies()
        if cancel_kind == "anyio":
            scope.cancel()
        else:
            task.cancel()
        await asyncio.sleep(0.01)
        if cancel_kind == "repeated":
            task.cancel()
            await asyncio.sleep(0.01)
        assert not task.done() and not finished.is_set()
        with pytest.raises(ListingFailure, match="^SERVER_BUSY:"):
            await service.list_policies()
    finally:
        release.set()
        if cancel_kind == "anyio":
            await asyncio.wait_for(task, 3)
        else:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
    assert finished.is_set()
    assert await service.list_policies() == project_catalog(load_catalog())
    assert "SENTINEL" not in caplog.text
