"""Project the packaged catalog without plans, OPA or MCP dependencies.

Each service admits one request without queuing. Catalog I/O, validation and size
measurement happen off the event loop; cancellation joins that bounded worker.
"""

import asyncio
import logging
from collections.abc import Callable
from threading import Lock
from uuid import uuid4

from anyio import CancelScope
from anyio.lowlevel import checkpoint_if_cancelled

from cloud_governance_mcp.catalog import PolicyCatalog, load_catalog
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.listing_errors import ListingCode, ListingFailure
from cloud_governance_mcp.listing_models import ListedPolicy, PolicyList

MAX_POLICY_LIST_BYTES = 65_536
_LOGGER = logging.getLogger(__name__)
type _ListingOutcome = PolicyList | ListingCode


def project_catalog(catalog: PolicyCatalog) -> PolicyList:
    """Copy only public fields from validated metadata, retaining catalog prose."""
    catalog = PolicyCatalog.model_validate(catalog)
    return PolicyList(
        policies=[
            ListedPolicy(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                title=policy.title,
                description=policy.description,
                severity=policy.severity,
                supported_provider_names=policy.supported_provider_names,
                supported_resource_types=policy.supported_resource_types,
                required_paths=policy.required_paths,
                scope_description=policy.scope_description,
                required_configuration=policy.required_configuration,
            )
            for policy in sorted(catalog.policies, key=lambda item: item.policy_id)
            if policy.enabled
        ]
    )


async def _finish_worker(worker: asyncio.Future[_ListingOutcome]) -> None:
    """Protect cleanup from scope cancellation and repeated native cancellation."""
    with CancelScope(shield=True):
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
        # Workers return safe codes, so shield callbacks never see raw failures.
        if not worker.cancelled():
            worker.exception()


class PolicyListingService:
    """Load trusted metadata lazily, independently of analysis/evaluation slots."""

    def __init__(
        self, *, catalog_loader: Callable[[], PolicyCatalog] = load_catalog
    ) -> None:
        self._catalog_loader = catalog_loader
        self._active = Lock()

    async def list_policies(self) -> PolicyList:
        """Return a complete bounded report or a value-free listing failure."""
        await checkpoint_if_cancelled()
        if not self._active.acquire(blocking=False):
            raise ListingFailure(ListingCode.SERVER_BUSY)
        try:
            worker = asyncio.get_running_loop().run_in_executor(None, self._list_sync)
            try:
                outcome = await asyncio.shield(worker)
                await checkpoint_if_cancelled()
            except asyncio.CancelledError:
                await _finish_worker(worker)
                raise
            if isinstance(outcome, ListingCode):
                raise ListingFailure(outcome)
            return outcome
        except ListingFailure as error:
            raise ListingFailure(error.code) from None
        except Exception:
            self._log_internal_failure()
            raise ListingFailure(ListingCode.INTERNAL_ERROR) from None
        finally:
            self._active.release()

    def _list_sync(self) -> _ListingOutcome:
        """Contain all worker exceptions before they cross executor futures."""
        try:
            report = project_catalog(self._catalog_loader())
            # Count the complete compact public object, including empty arrays.
            if len(report.model_dump_json().encode("utf-8")) > MAX_POLICY_LIST_BYTES:
                return ListingCode.POLICY_LIST_LIMIT_EXCEEDED
            return report
        except EvaluationFailure as error:
            if error.code == EvaluationCode.POLICY_ASSETS_INVALID:
                return ListingCode.POLICY_ASSETS_INVALID
            self._log_internal_failure()
            return ListingCode.INTERNAL_ERROR
        except Exception:
            self._log_internal_failure()
            return ListingCode.INTERNAL_ERROR

    @staticmethod
    def _log_internal_failure() -> None:
        """Log a fixed code and correlation ID without metadata or tracebacks."""
        _LOGGER.error("Listing failed code=INTERNAL_ERROR request_id=%s", uuid4().hex)
