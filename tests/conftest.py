"""Shared test runtime configuration; analysis-only tests never request OPA."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Services explicitly target asyncio, including AnyIO's asyncio backend."""
    return "asyncio"


@pytest.fixture
def opa_path() -> Path:
    """Missing real OPA is an actionable failure for full verification, not a skip."""
    root = Path(__file__).resolve().parent.parent
    path = Path(os.environ.get("CLOUD_GOVERNANCE_OPA", root / ".tools/opa/1.21.2/opa"))
    if not path.is_file():
        pytest.fail("Real OPA is required; follow docs/opa-setup.md.")
    return path.resolve()
