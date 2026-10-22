"""Explicit stdio entrypoint with required operator roots and safe diagnostics."""

import argparse
import logging
import sys
from collections.abc import Sequence
from importlib.metadata import version
from uuid import uuid4

import anyio

from cloud_governance_mcp.config import (
    AnalysisSettings,
    EvaluationSettings,
    validate_analysis_settings,
    validate_evaluation_settings,
)
from cloud_governance_mcp.errors import ConfigurationError, UnsupportedPlatformError
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.listing import PolicyListingService
from cloud_governance_mcp.server import create_server, run_stdio
from cloud_governance_mcp.service import AnalysisService
from cloud_governance_mcp.tag_models import DEFAULT_TAG_KEYS


class _SafeArgumentParser(argparse.ArgumentParser):
    """Replace argparse errors that would otherwise echo rejected option values."""

    def error(self, message: str) -> None:
        raise ConfigurationError() from None


def parse_configuration(
    argv: Sequence[str] | None = None,
) -> tuple[AnalysisSettings, EvaluationSettings]:
    """Parse both tools' operator settings without opening roots or probing OPA."""
    parser = _SafeArgumentParser(
        prog="cloud-governance-mcp",
        description="Read-only Terraform plan analysis and policy evaluation over MCP stdio.",
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
        "--opa-path",
        help="Absolute path to the pinned OPA executable; optional for analysis.",
    )
    parser.add_argument(
        "--required-tag-key",
        dest="required_tag_keys",
        action="append",
        help="Required tag key; repeat to replace default Environment/Owner/Project keys.",
    )
    for name in EvaluationSettings.model_fields:
        if name in {"opa_path", "required_tag_keys"}:
            continue
        default = EvaluationSettings.model_fields[name].default
        parser.add_argument(
            "--" + name.replace("_", "-"),
            type=int,
            default=default,
            help=f"Evaluation budget (default: {default}).",
        )
    parser.add_argument(
        "--version", action="version", version=version("cloud-governance-mcp")
    )
    arguments = vars(parser.parse_args(argv))
    if arguments["required_tag_keys"] is None:
        arguments["required_tag_keys"] = list(DEFAULT_TAG_KEYS)
    return (
        validate_analysis_settings(
            {key: arguments[key] for key in AnalysisSettings.model_fields}
        ),
        validate_evaluation_settings(
            {key: arguments[key] for key in EvaluationSettings.model_fields}
        ),
    )


def parse_settings(argv: Sequence[str] | None = None) -> AnalysisSettings:
    """Keep the existing analysis settings helper compatible for Python callers."""
    return parse_configuration(argv)[0]


def main(argv: Sequence[str] | None = None) -> int:
    """Pin trusted roots before serving; close them after all handlers finish."""
    # Stdout belongs exclusively to MCP. SDK debug output can include transport
    # payloads, so disable it and expose no client-controlled logging level.
    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    logging.getLogger("mcp").setLevel(logging.WARNING)
    try:
        settings, evaluation_settings = parse_configuration(argv)
        with RestrictedPlanLoader(settings) as loader:
            service = AnalysisService(settings, loader=loader)
            evaluation = EvaluationService(settings, evaluation_settings, loader=loader)
            listing = PolicyListingService()
            anyio.run(
                run_stdio,
                create_server(service, evaluation, listing),
                backend="asyncio",
            )
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
