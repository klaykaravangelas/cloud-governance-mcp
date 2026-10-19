"""Verify the installed package and runtime dependencies outside the repository."""

import subprocess
import sys
from pathlib import Path


def test_installed_package_imports_without_side_effects(tmp_path: Path) -> None:
    # Isolated Python in an unrelated directory must use the installed package;
    # repository/PYTHONPATH discovery cannot mask a broken package installation.
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import cloud_governance_mcp; "
            "import cloud_governance_mcp.server; "
            "import cloud_governance_mcp.__main__; "
            "from importlib.metadata import distribution; "
            "from mcp.server import MCPServer; "
            "from pydantic import BaseModel; "
            "distribution('cloud-governance-mcp')",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_core_contracts_import_without_loading_mcp(tmp_path: Path) -> None:
    # Core validation stays usable without importing the transport dependency.
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; "
            "import cloud_governance_mcp.config; "
            "import cloud_governance_mcp.models; "
            "import cloud_governance_mcp.errors; "
            "import cloud_governance_mcp.files; "
            "import cloud_governance_mcp.normalization; "
            "import cloud_governance_mcp.adapters.terraform; "
            "import cloud_governance_mcp.analysis; "
            "import cloud_governance_mcp.service; "
            "import cloud_governance_mcp.evaluation_models; "
            "import cloud_governance_mcp.evaluation_errors; "
            "import cloud_governance_mcp.catalog; "
            "import cloud_governance_mcp.projection; "
            "import cloud_governance_mcp.engine.opa; "
            "import cloud_governance_mcp.reporting; "
            "import cloud_governance_mcp.evaluation_service; "
            "import cloud_governance_mcp.listing_models; "
            "import cloud_governance_mcp.listing_errors; "
            "import cloud_governance_mcp.listing; "
            "assert not any(name == 'mcp' or name.startswith('mcp.') "
            "for name in sys.modules)",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_listing_imports_never_read_catalog_assets(tmp_path: Path) -> None:
    """Importing the core must stay quiet even when asset access would fail."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import importlib.resources
import sys
def forbidden(*args, **kwargs):
    raise RuntimeError('Unexpected import-time asset access')
importlib.resources.files = forbidden
import cloud_governance_mcp.listing
import cloud_governance_mcp.listing_models
import cloud_governance_mcp.listing_errors
assert not any(name == 'mcp' or name.startswith('mcp.') for name in sys.modules)
""",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
