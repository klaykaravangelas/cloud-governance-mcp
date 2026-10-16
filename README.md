# cloud-governance-mcp

A read-only MCP server that explains proposed Terraform infrastructure changes.
It reads an existing plan JSON file and returns resource identities, action/type/
mode counts, and coverage warnings through `analyze_terraform_plan`.

**Status:** the first analysis increment (A1–A7) is complete. **521 tests pass**,
including real MCP stdio and example-client tests. Package version is
`0.1.0.dev0`; the full three-tool v0.1 governance MVP remains in progress.
OPA/Rego policy evaluation is the next development increment.

## Try it locally

From the repository directory, with uv installed:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-tools
uv run --locked --no-editable python examples/client.py
```

The first call lists `analyze_terraform_plan`. The second analyzes our synthetic
mixed plan: **7 resources, 4 managed changes**, and `partial` coverage because
one inventory resource has no reported action. Compare the
[input plan](tests/fixtures/plans/mixed_nested.json) with the
[full example response](examples/reports/mixed-analysis.json).

The example client starts and stops its own server. No second terminal, AI model,
API key, AWS credentials, Terraform or OPA is needed. Initial dependency/interpreter
installation may need internet access; analysis itself is local.

Follow the [hands-on walkthrough](docs/trying-analysis.md) to understand the report,
try other fixtures and safe failures, supply your own plan, and connect an MCP
host. The [client source](examples/client.py) shows the official SDK calls.

## Run the server for an MCP host

After setup, launch with an existing absolute directory containing plan files:

```sh
uv run --locked --no-editable cloud-governance-mcp --allowed-root /absolute/path/to/plans
```

The host calls `analyze_terraform_plan` with `{"plan_path": "plan.json"}`. Repeat
`--allowed-root` for more directories; relative plan paths use the first root.
The process waits for MCP messages on stdin, and stdout carries protocol frames
only. There is no terminal prompt or HTTP page. See
[host process settings](docs/trying-analysis.md#7-connect-an-mcp-host-later) and
[all CLI options](docs/development.md#mcp-interface-and-stdio-a6).

## Supported behavior and boundaries

- Terraform plan JSON format major 1; state JSON, HCL and binary plans are rejected.
- Generic provider identities, recursive modules and exact numeric/string instance
  keys. Inventories merge by resource address without double counting.
- Create, update, delete, both replacement orders, no-op and data-source read.
  Inventory-only resources remain `unreported`; they are never guessed to be no-op.
- Deterministic public reports with fixed warnings/errors. `complete`/`partial`
  describes coverage of the supplied plan, not compliance or deployment state.
- Explicit allowed roots; no traversal, symlinks beneath roots, special files or
  implicit current-directory access. Input/depth/resource/output limits and one
  active analysis are enforced. Run `--help` for startup options.
- Attribute values, variables, outputs and internal sensitive/unknown paths are
  absent from responses. Resource identities are intentionally returned.
- The server never executes Terraform, applies changes, or connects to AWS.
  Provide a completed, stable plan file; it does not freeze concurrent file writes.

Development uses Python 3.14.7 with locked dependencies and a `src/` layout.
The package requires Python 3.14+. Secure file loading targets macOS/Linux;
macOS arm64 is verified, Linux execution remains unverified here, and unsupported
platforms fail startup. The regular-install `--no-editable` workflow avoids an
observed local macOS editable-import issue. See [development notes](docs/development.md).

## Verification

```sh
uv run --locked --no-editable pytest
uv run --locked --no-editable ruff check .
uv run --locked --no-editable ruff format --check .
uv build
```

The [acceptance record](docs/analysis-acceptance.md) maps AN-01–AN-15 to tests and
records versions, independent wheel/stdio checks, and tested limitations.
The [synthetic fixtures](tests/fixtures/plans/README.md) use fake values; illustrative
[Terraform configuration](examples/terraform/analysis/main.tf) is not executed by
tests. No OPA setup or policy tests belong to this analysis increment.

## Project progression

1. **Implemented:** `analyze_terraform_plan` for proposed infrastructure changes.
2. **Planned:** `evaluate_terraform_policies`, starting with one RDS encryption
   policy using OPA/Rego and the shared parsing foundation.
3. **Planned:** `list_policies`, then the remaining initial policy families.

AWS connectivity is planned after v0.1. No cloud adapter, Docker, CI workflow,
drift, cost or retrieval capability is implemented in this increment.

- [Requirements and acceptance criteria](docs/requirements.md)
- [Architecture and decisions](docs/architecture.md)
- [Specification 001](docs/specifications/analyze-terraform-plan.md)
- [Implementation plan](docs/implementation-plan.md)
- [Release roadmap](docs/roadmap.md)
- [Repository guidance](AGENTS.md)

Stack: Python 3.14+, the official MCP Python SDK, Pydantic, AnyIO, uv, pytest and
Ruff. Policy evaluation will introduce OPA/Rego.

License: [Apache 2.0](LICENSE).
