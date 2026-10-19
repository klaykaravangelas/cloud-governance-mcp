"""Coordinate independent evaluation admission, safe workers and real OPA.

The caller owns the shared restricted loader. No MCP import or cloud operation
belongs here; worker futures carry only data or safe codes on failure.
"""

import asyncio
import logging
from collections.abc import Callable
from threading import Lock
from typing import Protocol
from uuid import uuid4

from anyio.lowlevel import checkpoint_if_cancelled

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog
from cloud_governance_mcp.config import (
    AnalysisSettings,
    EvaluationSettings,
    validate_analysis_settings,
    validate_evaluation_settings,
)
from cloud_governance_mcp.engine.opa import OpaEngine, finish_shielded, validate_checks
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import (
    EngineReport,
    EvaluationInput,
    EvaluationReport,
    validate_evaluation_input,
)
from cloud_governance_mcp.models import ResourceSnapshot
from cloud_governance_mcp.projection import to_evaluation_input
from cloud_governance_mcp.reporting import build_report
from cloud_governance_mcp.service import PlanLoader

_LOGGER = logging.getLogger(__name__)


class PolicyEngine(Protocol):
    """Injection boundary for the constrained runtime, not arbitrary tool code."""

    async def evaluate(
        self, request: EvaluationInput, catalog: PolicyCatalog
    ) -> EngineReport:
        """Return a batch; service revalidates it before reporting."""
        ...


def _internal_code() -> EvaluationCode:
    """Unexpected failures never cross executor futures as raw exceptions."""
    _LOGGER.error("Evaluation failed code=INTERNAL_ERROR request_id=%s", uuid4().hex)
    return EvaluationCode.INTERNAL_ERROR


def _safe_call[T](
    function: Callable[..., T], *args: object
) -> T | ErrorCode | EvaluationCode:
    """Execute synchronous work off-loop, translating exceptions inside the worker."""
    try:
        return function(*args)
    except AnalysisError as error:
        return error.code
    except EvaluationFailure as error:
        return error.code
    except Exception:
        return _internal_code()


async def _worker[T](function: Callable[..., T], *args: object) -> T:
    """Cancellation joins the worker before roots/admission can be released."""
    future = asyncio.get_running_loop().run_in_executor(
        None, _safe_call, function, *args
    )
    try:
        result = await asyncio.shield(future)
        await checkpoint_if_cancelled()
    except asyncio.CancelledError:
        await finish_shielded(future)
        raise
    if isinstance(result, ErrorCode):
        raise AnalysisError(result)
    if isinstance(result, EvaluationCode):
        raise EvaluationFailure(result)
    return result


class EvaluationService:
    """One evaluation at a time, independent of the existing analysis slot."""

    def __init__(
        self,
        settings: AnalysisSettings,
        evaluation_settings: EvaluationSettings,
        *,
        loader: PlanLoader,
        engine: PolicyEngine | None = None,
    ) -> None:
        self._settings = validate_analysis_settings(settings)
        self._evaluation_settings = validate_evaluation_settings(evaluation_settings)
        self._loader = loader
        self._engine = (
            engine if engine is not None else OpaEngine(self._evaluation_settings)
        )
        self._adapter = TerraformPlanAdapter(
            max_resources=settings.max_resources,
            max_depth=settings.max_json_depth,
            include_policy_values=True,
        )
        self._active = Lock()

    def _prepare(
        self, path: str, ids: list[str]
    ) -> tuple[ResourceSnapshot, PolicyCatalog, EvaluationInput]:
        """Resolve selection before file I/O, then load/normalize exactly once."""
        catalog = load_catalog()
        catalog.select(ids)
        snapshot = self._adapter.normalize(self._loader.read_plan(path))
        return snapshot, catalog, to_evaluation_input(snapshot, ids)

    def _report(
        self,
        snapshot: ResourceSnapshot,
        ids: list[str],
        catalog: PolicyCatalog,
        result: EngineReport | None,
        error: EvaluationCode | None,
    ) -> EvaluationReport:
        """Bound serialization off-loop, including failed engine reports."""
        report = build_report(snapshot, ids, catalog, result, error)
        if (
            len(report.model_dump_json().encode("utf-8"))
            > self._evaluation_settings.max_evaluation_bytes
        ):
            raise EvaluationFailure(EvaluationCode.EVALUATION_LIMIT_EXCEEDED)
        return report

    async def evaluate(
        self, plan_path: str, policy_ids: list[str] | None = None
    ) -> EvaluationReport:
        """Return a trustworthy report or safe pre-report failure, never raw data."""
        arguments = {"plan_path": plan_path}
        if policy_ids is not None:
            arguments["policy_ids"] = policy_ids
        request = validate_evaluation_input(arguments)
        await checkpoint_if_cancelled()
        if not self._active.acquire(blocking=False):
            raise EvaluationFailure(EvaluationCode.SERVER_BUSY)
        try:
            snapshot, catalog, projected = await _worker(
                self._prepare, request.plan_path, request.policy_ids
            )
            result, error = None, None
            try:
                raw_result = await self._engine.evaluate(projected, catalog)
                result = await _worker(validate_checks, raw_result, projected, catalog)
            except EvaluationFailure as failure:
                error = failure.code
            except Exception:
                error = _internal_code()
            return await _worker(
                self._report, snapshot, request.policy_ids, catalog, result, error
            )
        except AnalysisError, EvaluationFailure:
            raise
        except Exception:
            raise EvaluationFailure(_internal_code()) from None
        finally:
            self._active.release()
