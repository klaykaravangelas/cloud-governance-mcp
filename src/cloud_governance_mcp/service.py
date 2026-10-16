"""Coordinate bounded read-only analysis without importing MCP or starting I/O.

The async API targets asyncio, including AnyIO's asyncio backend. The caller owns
the loader's lifetime; keep its root descriptors open until active calls finish.
"""

import asyncio
import logging
from threading import Lock
from typing import Protocol
from uuid import uuid4

from anyio import CancelScope
from anyio.lowlevel import checkpoint_if_cancelled

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.analysis import summarize
from cloud_governance_mcp.config import AnalysisSettings, validate_analysis_settings
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import (
    PlanAnalysis,
    ResourceSnapshot,
    validate_analysis_input,
)

_LOGGER = logging.getLogger(__name__)
type _AnalysisOutcome = PlanAnalysis | ErrorCode


class PlanLoader(Protocol):
    """Injected loader boundary; production uses RestrictedPlanLoader."""

    def read_plan(self, plan_path: str) -> object:
        """Return internal JSON after enforcing the configured file limits."""
        ...


class PlanAdapter(Protocol):
    """Injected interpretation boundary; production uses TerraformPlanAdapter."""

    def normalize(self, plan: object) -> ResourceSnapshot:
        """Validate a decoded plan and return normalized resources and coverage."""
        ...


async def _finish_worker(worker: asyncio.Future[_AnalysisOutcome]) -> None:
    """Join a protected thread before releasing admission after cancellation.

    An asyncio shield protects the executor future from Task.cancel(). AnyIO's
    shield also prevents repeated scope cancellation from spinning during cleanup.
    Repeated direct Task.cancel() calls are deferred until the worker finishes.
    """
    with CancelScope(shield=True):
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # Consume the future state even when cancellation discards the outcome.
        # Ordinary worker failures are codes, keeping shield callbacks value-free.
        if not worker.cancelled():
            worker.exception()


class AnalysisService:
    """Validate paths and run one loader/adapter/summary pipeline at a time.

    Inject a loader configured with the same settings. The default adapter uses
    those settings' resource/depth limits. A nonblocking slot rejects concurrent
    analyses immediately rather than queuing them, including across event loops.
    """

    def __init__(
        self,
        settings: AnalysisSettings,
        *,
        loader: PlanLoader,
        adapter: PlanAdapter | None = None,
    ) -> None:
        self._settings = validate_analysis_settings(settings)
        self._loader = loader
        self._adapter = (
            adapter
            if adapter is not None
            else TerraformPlanAdapter(
                max_resources=self._settings.max_resources,
                max_depth=self._settings.max_json_depth,
            )
        )
        self._active = Lock()

    async def analyze(self, plan_path: str) -> PlanAnalysis:
        """Return a validated public report or a fixed, safe application error.

        File reading, decoding, normalization, counting, and size measurement run
        in an executor thread. Cancellation waits for that work to finish safely;
        threads cannot be forcibly killed. No partial result is returned.
        """
        request = validate_analysis_input({"plan_path": plan_path})
        await checkpoint_if_cancelled()
        if not self._active.acquire(blocking=False):
            raise AnalysisError(ErrorCode.SERVER_BUSY)
        try:
            worker = asyncio.get_running_loop().run_in_executor(
                None, self._analyze_sync, request.plan_path
            )
            try:
                outcome = await asyncio.shield(worker)
                # A ready future may not yield; honor a pending AnyIO scope
                # cancellation before handing a success back to the transport.
                await checkpoint_if_cancelled()
                if isinstance(outcome, ErrorCode):
                    raise AnalysisError(outcome)
                return outcome
            except asyncio.CancelledError:
                await _finish_worker(worker)
                raise
        except AnalysisError as error:
            # Reconstruct from the catalog; never forward arbitrary exception text.
            raise AnalysisError(error.code) from None
        except Exception:
            self._log_internal_failure()
            raise AnalysisError(ErrorCode.INTERNAL_ERROR) from None
        finally:
            self._active.release()

    def _analyze_sync(self, plan_path: str) -> _AnalysisOutcome:
        """Run the bounded pipeline, returning failures as safe codes, not exceptions.

        Python 3.14 can log exceptions from cancelled shielded futures even after
        retrieval. Keep raw exceptions inside this worker: only a report or a
        catalog code crosses the future boundary, including during cancellation.
        """
        try:
            snapshot = self._adapter.normalize(self._loader.read_plan(plan_path))
            report = summarize(snapshot)
            # Measure compact JSON, including nulls/zero buckets, as UTF-8 bytes.
            # Protocol framing/whitespace is outside this analysis-object budget.
            if (
                len(report.model_dump_json().encode("utf-8"))
                > self._settings.max_analysis_bytes
            ):
                return ErrorCode.ANALYSIS_LIMIT_EXCEEDED
            return report
        except AnalysisError as error:
            if error.code == ErrorCode.INTERNAL_ERROR:
                self._log_internal_failure()
            return error.code
        except Exception:
            self._log_internal_failure()
            return ErrorCode.INTERNAL_ERROR

    @staticmethod
    def _log_internal_failure() -> None:
        """Log a correlation ID and fixed code without exception text/tracebacks."""
        _LOGGER.error("Analysis failed code=INTERNAL_ERROR request_id=%s", uuid4().hex)
