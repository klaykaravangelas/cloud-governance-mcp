"""Expose governance services through the official SDK's public Server API.

Explicit handlers let us publish the strict core schemas and validate arguments
without the decorator layer's input-bearing validation errors or log messages.
Importing this module starts no server and opens no plan files.
"""

import json
import logging
from importlib.metadata import version
from uuid import uuid4

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.evaluation_models import (
    EvaluateTerraformPoliciesInput,
    EvaluationReport,
    validate_evaluation_input,
)
from cloud_governance_mcp.evaluation_service import EvaluationService
from cloud_governance_mcp.models import (
    AnalyzeTerraformPlanInput,
    PlanAnalysis,
    validate_analysis_input,
)
from cloud_governance_mcp.service import AnalysisService

TOOL_NAME = "analyze_terraform_plan"
EVALUATION_TOOL_NAME = "evaluate_terraform_policies"
_DESCRIPTION = (
    "Summarize resource identities and proposed actions from a local Terraform "
    "plan JSON file in an allowed directory. Returns no resource attribute "
    "values and performs no compliance evaluation or infrastructure changes."
)
_LOGGER = logging.getLogger(__name__)


def _tool_error(code: ErrorCode) -> CallToolResult:
    """Return one catalog-controlled message and no structured success payload."""
    return CallToolResult(
        content=[TextContent(type="text", text=str(AnalysisError(code)))],
        is_error=True,
    )


def create_server(
    service: AnalysisService, evaluation_service: EvaluationService | None = None
) -> Server:
    """Register read-only tools around independently testable services.

    The caller owns the service/loader lifetime. Tool schemas come from the same
    Pydantic contracts used at runtime; the SDK handles protocol envelopes and
    malformed protocol requests, while our handler handles tool arguments.
    """
    tool = Tool(
        name=TOOL_NAME,
        description=_DESCRIPTION,
        input_schema=AnalyzeTerraformPlanInput.model_json_schema(),
        output_schema=PlanAnalysis.model_json_schema(),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    tools = [tool]
    if evaluation_service is not None:
        tools.append(
            Tool(
                name=EVALUATION_TOOL_NAME,
                description=(
                    "Evaluate bundled governance policies against a local Terraform "
                    "plan JSON file in an allowed directory. Return policy findings, "
                    "uncertainty and coverage without resource attribute values. "
                    "Requires configured OPA; does not inspect or modify deployed infrastructure."
                ),
                input_schema=EvaluateTerraformPoliciesInput.model_json_schema(),
                output_schema=EvaluationReport.model_json_schema(),
                annotations=ToolAnnotations(
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=False,
                ),
            )
        )

    async def list_tools(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        """Advertise configured, implemented tools; policy listing remains future work."""
        return ListToolsResult(tools=tools)

    async def call_tool(
        ctx: ServerRequestContext, params: CallToolRequestParams
    ) -> CallToolResult:
        """Validate all tool arguments before the service can touch a file."""
        if params.name not in {item.name for item in tools}:
            # Unknown tools are protocol errors. Never reflect the supplied name.
            raise MCPError(code=INVALID_PARAMS, message="Unknown tool.")
        try:
            if params.name == TOOL_NAME:
                request = validate_analysis_input(params.arguments)
                report = PlanAnalysis.model_validate(
                    await service.analyze(request.plan_path)
                )
                failed = False
            else:
                request = validate_evaluation_input(params.arguments)
                report = EvaluationReport.model_validate(
                    await evaluation_service.evaluate(
                        request.plan_path, request.policy_ids
                    )
                )
                failed = bool(report.errors)
            # Both channels describe exactly the same validated public object.
            # Masks and raw plan values never reach this module.
            text = report.model_dump_json()
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=json.loads(text),
                is_error=failed,
            )
        except EvaluationFailure as error:
            return CallToolResult(
                content=[TextContent(type="text", text=str(error))], is_error=True
            )
        except AnalysisError as error:
            return _tool_error(error.code)
        except Exception:
            # Includes invalid service results and serialization failures. SDK
            # crash logging must not receive their raw exceptions/tracebacks.
            _LOGGER.error("Tool failed code=INTERNAL_ERROR request_id=%s", uuid4().hex)
            if params.name == EVALUATION_TOOL_NAME:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=str(EvaluationFailure(EvaluationCode.INTERNAL_ERROR)),
                        )
                    ],
                    is_error=True,
                )
            return _tool_error(ErrorCode.INTERNAL_ERROR)

    return Server(
        "cloud-governance-mcp",
        version=version("cloud-governance-mcp"),
        instructions="Read-only Terraform plan analysis and bundled policy evaluation within operator-configured directories.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def run_stdio(server: Server) -> None:
    """Serve SDK-managed stdio until EOF or cancellation, then join its handlers."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
