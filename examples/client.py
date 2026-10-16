"""Try the real MCP stdio server with the official SDK and synthetic local plans.

This is a standalone example client, not another server tool. It launches the
fixed server module using the same Python environment, then closes the connection
and child process on exit. It never reads plan contents itself.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent


async def run_client(
    root: Path, plan_path: str, *, list_tools: bool, legacy: bool
) -> int:
    """Discover tools or call analysis; display only the server's public result."""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-m", "cloud_governance_mcp", "--allowed-root", str(root)],
    )
    # Client manages connection/version negotiation and subprocess cleanup.
    # Legacy mode explicitly exercises the older initialization handshake.
    async with Client(parameters, mode="legacy" if legacy else "auto") as client:
        tools = await client.list_tools()
        if list_tools:
            print(json.dumps([tool.name for tool in tools.tools], indent=2))
            return 0
        result = await client.call_tool(
            "analyze_terraform_plan", {"plan_path": plan_path}
        )
        if result.is_error:
            # A failed call has fixed text, not a structured success report.
            for content in result.content:
                if isinstance(content, TextContent):
                    print(content.text, file=sys.stderr)
            return 1
        if result.structured_content is None:
            print("The server returned no structured analysis.", file=sys.stderr)
            return 1
        print(json.dumps(result.structured_content, indent=2, ensure_ascii=False))
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Use checked-in fixtures by default; allow an explicit directory of plans."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allowed-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "plans",
        help="Directory to authorize for this example (default: repository fixtures).",
    )
    parser.add_argument(
        "--plan-path",
        default="mixed_nested.json",
        help="Literal plan path within the allowed root.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print discovered tool names instead of analyzing a plan.",
    )
    parser.add_argument(
        "--legacy", action="store_true", help="Use the legacy initialization handshake."
    )
    arguments = parser.parse_args(argv)
    try:
        # Resolving an operator-chosen root is allowed. The tool's plan_path stays
        # literal so traversal, quoting and symlink rules remain server decisions.
        return asyncio.run(
            run_client(
                arguments.allowed_root.resolve(),
                arguments.plan_path,
                list_tools=arguments.list_tools,
                legacy=arguments.legacy,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception:
        # The example never dumps protocol/connection exception internals.
        print(
            "Could not complete the MCP request. Check the allowed root and server startup diagnostics.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
