"""Explicit stdio entrypoint with required operator roots and safe diagnostics."""

import argparse
import logging
import sys
from collections.abc import Sequence
from importlib.metadata import version
from uuid import uuid4

import anyio

from cloud_governance_mcp.config import AnalysisSettings, validate_analysis_settings
from cloud_governance_mcp.errors import ConfigurationError, UnsupportedPlatformError
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.server import create_server, run_stdio
from cloud_governance_mcp.service import AnalysisService


class _SafeArgumentParser(argparse.ArgumentParser):
    """Replace argparse errors that would otherwise echo rejected option values."""

    def error(self, message: str) -> None:
        raise ConfigurationError() from None


def parse_settings(argv: Sequence[str] | None = None) -> AnalysisSettings:
    """Parse explicit local roots/positive budgets without opening directories."""
    parser = _SafeArgumentParser(
        prog="cloud-governance-mcp",
        description="Read-only Terraform plan analysis over MCP stdio.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--allowed-root",
        dest="allowed_roots",
        action="append",
        required=True,
        help="Existing absolute directory containing readable plans; repeat in priority order.",
    )
    for name, description in (
        ("max_plan_bytes", "Maximum input bytes"),
        ("max_json_depth", "Maximum JSON container depth"),
        ("max_resources", "Maximum resource entries per source and merged inventory"),
        ("max_analysis_bytes", "Maximum compact UTF-8 analysis bytes"),
    ):
        default = AnalysisSettings.model_fields[name].default
        parser.add_argument(
            "--" + name.replace("_", "-"),
            type=int,
            default=default,
            help=f"{description} (default: {default}).",
        )
    parser.add_argument(
        "--version", action="version", version=version("cloud-governance-mcp")
    )
    return validate_analysis_settings(vars(parser.parse_args(argv)))


def main(argv: Sequence[str] | None = None) -> int:
    """Pin trusted roots before serving; close them after all handlers finish."""
    # Stdout belongs exclusively to MCP. SDK debug output can include transport
    # payloads, so disable it and expose no client-controlled logging level.
    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    logging.getLogger("mcp").setLevel(logging.WARNING)
    try:
        settings = parse_settings(argv)
        with RestrictedPlanLoader(settings) as loader:
            service = AnalysisService(settings, loader=loader)
            anyio.run(run_stdio, create_server(service), backend="asyncio")
        return 0
    except (ConfigurationError, UnsupportedPlatformError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception:
        logging.getLogger(__name__).error(
            "Server failed code=INTERNAL_ERROR request_id=%s", uuid4().hex
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
