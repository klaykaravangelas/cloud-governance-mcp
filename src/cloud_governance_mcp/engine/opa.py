"""Constrained, bounded OPA execution with atomic validation and shielded cleanup.

Only operator configuration selects the executable. Query, flags and package
assets are fixed here; plan content enters exclusively through stdin.
"""

import asyncio
import os
import re
import signal
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

from anyio import CancelScope
from pydantic import ValidationError

from cloud_governance_mcp.catalog import PolicyCatalog
from cloud_governance_mcp.config import EvaluationSettings, validate_evaluation_settings
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import (
    EngineReport,
    EvaluationInput,
    ProjectedResource,
)
from cloud_governance_mcp.json_codec import decode_object

OPA_VERSION = "1.21.2"
QUERY = "data.cloud_governance.report"
CHILD_ENVIRONMENT = {"LANG": "C", "LC_ALL": "C"}


async def _compute[T](function: Callable[..., T], *args: object) -> T:
    """Keep input/output JSON and validation off-loop, including cancellation."""

    def safe() -> T | EvaluationCode:
        try:
            return function(*args)
        except EvaluationFailure as failure:
            return failure.code
        except Exception:
            # No raw exception reaches a shield callback or SDK crash logging.
            return EvaluationCode.OPA_OUTPUT_INVALID

    future = asyncio.get_running_loop().run_in_executor(None, safe)
    try:
        result = await asyncio.shield(future)
    except asyncio.CancelledError:
        await finish_shielded(future)
        raise
    if isinstance(result, EvaluationCode):
        raise EvaluationFailure(result)
    return result


def _input_bytes(request: EvaluationInput, limit: int) -> bytes:
    """Measure the complete compact UTF-8 input, never a truncated projection."""
    request = EvaluationInput.model_validate(request)
    payload = request.model_dump_json().encode("utf-8")
    if len(payload) > limit:
        raise EvaluationFailure(EvaluationCode.OPA_INPUT_LIMIT_EXCEEDED)
    return payload


def _decode_report(
    raw: bytes, request: EvaluationInput, catalog: PolicyCatalog
) -> EngineReport:
    """Decode and validate the entire batch in the same bounded worker."""
    return validate_engine_report(decode_object(raw), request, catalog)


async def finish_shielded[T](task: asyncio.Future[T]) -> T:
    """Join cleanup even under AnyIO scopes and repeated native Task.cancel()."""
    with CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        return task.result()


async def _reap(process: asyncio.subprocess.Process) -> None:
    """Terminate the owned process group, escalate after one second and reap."""
    # A new session isolates this group from the server and the user's shell.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), 1)
    except TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


async def run_process(
    executable: str,
    arguments: list[str],
    payload: bytes,
    settings: EvaluationSettings,
    cwd: str,
) -> bytes:
    """Drain both pipes while writing stdin; never retain diagnostics in errors."""
    process = None
    tasks: list[asyncio.Task] = []

    async def spawn_safe() -> tuple[
        asyncio.subprocess.Process | None, EvaluationCode | None
    ]:
        # Never carry raw spawn exceptions through shield callbacks (Python 3.14).
        try:
            child = await asyncio.create_subprocess_exec(
                executable,
                *arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=CHILD_ENVIRONMENT.copy(),
                cwd=cwd,
                start_new_session=True,
            )
            return child, None
        except FileNotFoundError, PermissionError:
            return None, EvaluationCode.OPA_NOT_FOUND
        except OSError:
            return None, EvaluationCode.OPA_EXECUTION_ERROR

    spawn = asyncio.create_task(spawn_safe())

    async def read(stream: asyncio.StreamReader, limit: int) -> bytes:
        chunks, size = [], 0
        while block := await stream.read(min(65_536, limit + 1)):
            size += len(block)
            if size > limit:
                raise EvaluationFailure(EvaluationCode.OPA_OUTPUT_LIMIT_EXCEEDED)
            chunks.append(block)
        return b"".join(chunks)

    async def write() -> None:
        try:
            # Chunking also bounds asyncio transport buffering for large inputs.
            for offset in range(0, len(payload), 65_536):
                process.stdin.write(payload[offset : offset + 65_536])
                await process.stdin.drain()
        finally:
            process.stdin.close()

    try:
        async with asyncio.timeout(settings.opa_process_timeout_seconds):
            process, spawn_error = await asyncio.shield(spawn)
            if spawn_error is not None:
                raise EvaluationFailure(spawn_error)
            tasks = [
                asyncio.create_task(write()),
                asyncio.create_task(
                    read(process.stdout, settings.max_opa_output_bytes)
                ),
                asyncio.create_task(
                    read(process.stderr, settings.max_opa_stderr_bytes)
                ),
                asyncio.create_task(process.wait()),
            ]
            _, stdout, _, returncode = await asyncio.gather(*tasks)
            if returncode:
                # OPA's own timeout is a structured fixed code, never text parsing.
                try:
                    error_codes = {
                        e.get("code")
                        for e in decode_object(stdout).get("errors", [])
                        if isinstance(e, dict)
                    }
                except ValueError, TypeError, RecursionError:
                    error_codes = set()
                code = (
                    EvaluationCode.OPA_TIMEOUT
                    if "eval_cancel_error" in error_codes
                    else EvaluationCode.OPA_EXECUTION_ERROR
                )
                raise EvaluationFailure(code)
            return stdout
    except TimeoutError:
        raise EvaluationFailure(EvaluationCode.OPA_TIMEOUT) from None
    except FileNotFoundError, PermissionError:
        raise EvaluationFailure(EvaluationCode.OPA_NOT_FOUND) from None
    except OSError, BrokenPipeError, ConnectionError:
        raise EvaluationFailure(EvaluationCode.OPA_EXECUTION_ERROR) from None
    finally:
        # Cancellation during spawn must not leave a newly created child orphaned.
        if process is None:
            try:
                process, _ = await finish_shielded(spawn)
            except OSError, asyncio.CancelledError:
                pass
        if process is not None:

            async def cleanup() -> None:
                if process.returncode is None or any(not t.done() for t in tasks):
                    await _reap(process)
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            await finish_shielded(asyncio.create_task(cleanup()))


def validate_engine_report(
    document: dict, request: EvaluationInput, catalog: PolicyCatalog
) -> EngineReport:
    """Require exactly one valid result for every selected policy/resource pair."""
    try:
        if set(document) != {"result"}:
            raise ValueError("Unexpected engine envelope.")
        results = document["result"]
        if not isinstance(results, list) or len(results) != 1:
            raise ValueError("Expected one result.")
        expressions = results[0]["expressions"]
        if not isinstance(expressions, list) or len(expressions) != 1:
            raise ValueError("Expected one expression.")
        return validate_checks(expressions[0]["value"], request, catalog)
    except ValueError, KeyError, TypeError, IndexError, ValidationError:
        raise EvaluationFailure(EvaluationCode.OPA_OUTPUT_INVALID) from None


def validate_checks(
    value: object, request: EvaluationInput, catalog: PolicyCatalog
) -> EngineReport:
    """Revalidate injected engines as well as subprocess output before reporting."""
    try:
        request = EvaluationInput.model_validate(request)
        report = EngineReport.model_validate(value)
        policies = {p.policy_id: p for p in catalog.select(request.selected_policy_ids)}
        resources = {r.address: r for r in request.resources}
        expected = {(p, r) for p in policies for r in resources}
        seen = set()
        for check in report.checks:
            key = (check.policy_id, check.resource_address)
            if key not in expected or key in seen:
                raise ValueError("Invalid pair membership.")
            seen.add(key)
            template = policies[check.policy_id].reasons[check.reason_code]
            if (
                check.outcome != template.outcome
                or check.attribute_path != template.attribute_path
            ):
                raise ValueError("Invalid reason combination.")
            resource = resources[check.resource_address]
            excluded = (
                "DATA_SOURCE_SKIPPED"
                if resource.mode == "data"
                else "DELETED_RESOURCE_SKIPPED"
                if resource.action_category == "delete"
                else "RESOURCE_NOT_SUPPORTED"
                if resource.provider_name
                not in policies[check.policy_id].supported_provider_names
                or resource.resource_type
                not in policies[check.policy_id].supported_resource_types
                else None
            )
            if (excluded is not None and check.reason_code != excluded) or (
                excluded is None
                and check.outcome == "not_applicable"
                and not (
                    check.policy_id == "AWS-SG-001"
                    and resource.ssh_state is not None
                    and resource.ssh_state.direction.state == "known"
                    and resource.ssh_state.direction.value == "egress"
                    and check.reason_code == "SSH_EGRESS_SKIPPED"
                )
            ):
                raise ValueError("Invalid applicability.")
            if excluded is None and check.reason_code not in _allowed_reasons(
                resource, resources
            ):
                raise ValueError("Invalid reason scope/state.")
        if seen != expected:
            raise ValueError("Missing checks.")
        report.checks.sort(key=lambda c: (c.policy_id, c.resource_address))
        return report
    except ValueError, KeyError, TypeError, IndexError, ValidationError:
        raise EvaluationFailure(EvaluationCode.OPA_OUTPUT_INVALID) from None


def _allowed_reasons(
    resource: ProjectedResource, resources: dict[str, ProjectedResource]
) -> set[str]:
    """Validate reason applicability without deciding a known boolean's outcome.

    Rego owns pass/fail. This guard prevents an otherwise valid catalog reason
    from describing a different resource, association state or encryption state.
    """
    if resource.resource_type in {
        "aws_security_group",
        "aws_security_group_rule",
        "aws_vpc_security_group_ingress_rule",
    }:
        # Policy/type applicability was checked above; SSH boolean decisions stay
        # in Rego. Validate representation/direction and available reason states.
        projection = resource.ssh_state
        if projection is None:
            return set()
        if projection.direction.state != "known":
            return {"SSH_RULE_" + projection.direction.state.upper()}
        if projection.direction.value == "egress":
            return {"SSH_EGRESS_SKIPPED"}
        prefix = "SSH_INLINE_" if projection.representation == "inline" else "SSH_RULE_"
        if projection.rules.state != "known":
            return {prefix + projection.rules.state.upper()}
        observed_states = _ssh_states(projection.rules.model_dump())
        states = {
            value
            for value in observed_states
            if value not in {"known", "absent", "present"}
        }
        known_rules = [r for r in projection.rules.items if r.state == "known"]
        if any(r.sources.prefix_lists.state == "present" for r in known_rules):
            states.add("prefix_list_unresolved")
        # Empty source sets can synthesize a missing observation in Rego.
        states.add("missing")
        allowed = {prefix + state.upper() for state in states}
        if known_rules or not projection.rules.items:
            allowed.add(prefix + "NO_UNRESTRICTED_INGRESS")
        if known_rules:
            allowed.add(prefix + "UNRESTRICTED_INGRESS")
        return allowed
    desired = resource.desired_state
    if desired.scope == "cluster_member":
        association = desired.association
        if association.state != "resolved":
            return {"RDS_CLUSTER_LINK_" + association.state.upper()}
        encryption = resources[association.cluster_address].desired_state.encryption
        prefix = "RDS_CLUSTER_ENCRYPTION_"
    else:
        scope_codes = {
            "sensitive": "RDS_SCOPE_SENSITIVE",
            "unknown": "RDS_SCOPE_UNKNOWN",
            "unverified": "UNKNOWN_METADATA_INCOMPLETE",
            "unavailable": "DESIRED_STATE_UNAVAILABLE",
            "invalid_type": "RDS_SCOPE_INVALID_TYPE",
            "cluster_associated": "RDS_CLUSTER_ASSOCIATION_UNSUPPORTED",
        }
        if desired.scope in scope_codes:
            return {scope_codes[desired.scope]}
        encryption = desired.encryption
        prefix = "RDS_ENCRYPTION_"
        if encryption.state in {"unverified", "unavailable"}:
            return {
                "UNKNOWN_METADATA_INCOMPLETE"
                if encryption.state == "unverified"
                else "DESIRED_STATE_UNAVAILABLE"
            }
    if encryption.state == "known":
        return {prefix + "ENABLED", prefix + "DISABLED"}
    return {prefix + encryption.state.upper()}


def _ssh_states(value: object) -> set[str]:
    """Walk only sanitized contract states, never provider payloads."""
    result = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if "state" in item:
                result.add(item["state"])
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return result


class OpaEngine:
    """One server-owned evaluator; the service serializes all calls and probes."""

    def __init__(self, settings: EvaluationSettings) -> None:
        self.settings = validate_evaluation_settings(settings)
        self._verified = False
        self._path = settings.opa_path
        if self._path is not None:
            try:
                self._path = str(Path(self._path).resolve())
            except OSError, RuntimeError:
                pass  # Evaluation reports availability errors; analysis can start.

    async def evaluate(
        self, request: EvaluationInput, catalog: PolicyCatalog
    ) -> EngineReport:
        """Evaluate package policies, returning only a validated complete batch."""
        payload = await _compute(
            _input_bytes, request, self.settings.max_opa_input_bytes
        )
        if self._path is None:
            raise EvaluationFailure(EvaluationCode.OPA_NOT_CONFIGURED)
        with ExitStack() as stack:
            cwd = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="cloud-governance-opa-")
            )
            if not self._verified:
                raw = await run_process(
                    self._path, ["version"], b"", self.settings, cwd
                )
                try:
                    if re.findall(
                        r"^Version: ([0-9]+\.[0-9]+\.[0-9]+)$",
                        raw.decode("utf-8"),
                        re.M,
                    ) != [OPA_VERSION]:
                        raise ValueError("Unsupported runtime.")
                except ValueError, KeyError, TypeError, RecursionError:
                    raise EvaluationFailure(
                        EvaluationCode.OPA_VERSION_UNSUPPORTED
                    ) from None
                self._verified = True
            try:
                assets = stack.enter_context(
                    as_file(files("cloud_governance_mcp.policies"))
                )
                for relative in (
                    "capabilities.json",
                    "catalog.json",
                    "rego/rds.rego",
                    "rego/ssh.rego",
                ):
                    if not assets.joinpath(relative).is_file():
                        raise ValueError("Missing assets.")
            except OSError, ValueError:
                raise EvaluationFailure(EvaluationCode.POLICY_ASSETS_INVALID) from None
            arguments = [
                "eval",
                "--format=json",
                "--stdin-input",
                "--strict",
                "--strict-builtin-errors",
                f"--timeout={self.settings.opa_eval_timeout_seconds}s",
                "--capabilities",
                str(assets / "capabilities.json"),
                "--data",
                str(assets / "rego/rds.rego"),
                "--data",
                str(assets / "rego/ssh.rego"),
                "--data",
                str(assets / "catalog.json"),
                QUERY,
            ]
            raw = await run_process(self._path, arguments, payload, self.settings, cwd)
            return await _compute(_decode_report, raw, request, catalog)
