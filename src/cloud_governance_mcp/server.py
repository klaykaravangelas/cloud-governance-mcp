"""Expose the analysis service through the official SDK's public Server API.

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
from cloud_governance_mcp.models import (
    AnalyzeTerraformPlanInput,
    PlanAnalysis,
    validate_analysis_input,
)
from cloud_governance_mcp.service import AnalysisService

TOOL_NAME = "analyze_terraform_plan"
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


def create_server(service: AnalysisService) -> Server:
    """Register exactly one read-only tool around an existing shared service.

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

    async def list_tools(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        """Advertise implemented behavior only; no policy tools exist yet."""
        return ListToolsResult(tools=[tool])

    async def call_tool(
        ctx: ServerRequestContext, params: CallToolRequestParams
    ) -> CallToolResult:
        """Validate all tool arguments before the service can touch a file."""
        if params.name != TOOL_NAME:
            # Unknown tools are protocol errors. Never reflect the supplied name.
            raise MCPError(code=INVALID_PARAMS, message="Unknown tool.")
        try:
            request = validate_analysis_input(params.arguments)
            report = PlanAnalysis.model_validate(
                await service.analyze(request.plan_path)
            )
            # Both channels describe exactly the same validated public object.
            # Masks and raw plan values never reach this module.
            text = report.model_dump_json()
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=json.loads(text),
                is_error=False,
            )
        except AnalysisError as error:
            return _tool_error(error.code)
        except Exception:
            # Includes invalid service results and serialization failures. SDK
            # crash logging must not receive their raw exceptions/tracebacks.
            _LOGGER.error("Tool failed code=INTERNAL_ERROR request_id=%s", uuid4().hex)
            return _tool_error(ErrorCode.INTERNAL_ERROR)

    return Server(
        "cloud-governance-mcp",
        version=version("cloud-governance-mcp"),
        instructions="Read-only Terraform plan analysis within operator-configured directories.",
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
