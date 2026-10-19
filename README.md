# cloud-governance-mcp

An open-source Model Context Protocol (MCP) server for cloud infrastructure
governance. The project is being built to help AI assistants inspect infrastructure,
evaluate governance policies, and explain security and compliance findings.

The initial focus is Terraform plan JSON, with policy-as-code using Open Policy
Agent (OPA) and Rego. The architecture separates MCP interfaces from
the governance engine so future adapters can support read-only AWS inspection.
The project demonstrates platform engineering, infrastructure security,
policy-as-code, and MCP integration through small, tested increments.

## Tools and project scope

The v0.1 target has three complementary tools:

| Tool | Purpose | Status |
| --- | --- | --- |
| `analyze_terraform_plan` | Explain proposed changes through resource identities, action/type/mode counts, and coverage warnings. | Implemented |
| `evaluate_terraform_policies` | Evaluate a plan against governance rules and return structured findings with resource addresses, policy IDs, severity, and explanations. | Implemented; standalone RDS encryption (AWS-RDS-001) |
| `list_policies` | Describe implemented governance policies, versions, severity, supported resources and configuration requirements. | Implemented; uses the shared evaluation catalog without OPA |

The first policy checks standalone RDS storage encryption. Planned coverage adds
RDS clusters, unrestricted SSH ingress, mandatory resource tags and S3 public
access protection. Only the implemented RDS policy is selectable today.

Analysis explains changes; evaluation adds compliance decisions; policy
listing describes the available rules. AWS connectivity is a later milestone.

## Current status

Terraform plan analysis is available locally over stdio. The first analysis
increment (A1–A7) is complete, with real MCP client/server tests, synthetic plans,
and a hands-on walkthrough. Package version is `0.1.0.dev0`; all three tools are
available, while the full v0.1 policy coverage remains in progress. Evaluation
uses pinned OPA 1.21.2. All tools operate locally without AWS credentials or
Terraform. Analysis and policy listing need no OPA configuration or installation.

## Try the analysis tool locally

From the repository directory, with uv installed:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-tools
uv run --locked --no-editable python examples/client.py
```

The first call lists all three implemented tools. The second analyzes our synthetic
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

## Try policy evaluation

Follow [OPA setup](docs/opa-setup.md) to install and checksum-verify the pinned
local binary. Then evaluate the synthetic unencrypted RDS plan:

```sh
uv run --locked --no-editable python examples/client.py --evaluate --plan-path unencrypted_rds.json --opa-path .tools/opa/1.21.2/opa
```

The result reports `complete` execution and a `fail` compliance finding for
`aws_db_instance.example`. Missing/unknown/sensitive encryption yields
`indeterminate`; engine failures are separate tool errors. See the
[evaluation walkthrough](docs/trying-evaluation.md) and
[saved full report](examples/reports/unencrypted-rds-evaluation.json).

## List available governance policies

```sh
uv run --locked --no-editable python examples/client.py --list-policies
```

This returns AWS-RDS-001 metadata from the same catalog used by evaluation,
including its standalone-only scope and empty policy configuration requirements.
It reads no plan and invokes no OPA process. Compare the
[saved response](examples/reports/policy-list.json) or follow the
[listing walkthrough](docs/trying-listing.md). `--list-tools` discovers MCP
functions; `--list-policies` discovers governance rules.

## Run the server for an MCP host

To use the tools directly in Codex, follow the
[Codex stdio connection guide](docs/connecting-codex.md).

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

## Current analysis behavior and boundaries

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
- No tool executes Terraform, applies changes, or connects to AWS.
  Provide a completed, stable plan file; it does not freeze concurrent file writes.

Development uses Python 3.14.7 with locked dependencies and a `src/` layout.
The package requires Python 3.14+. Secure file loading targets macOS/Linux;
macOS arm64 is verified, Linux execution remains unverified here, and unsupported
platforms fail startup. The regular-install `--no-editable` workflow avoids an
observed local macOS editable-import issue. See [development notes](docs/development.md).

## Verification

Install the pinned OPA runtime for the full suite, which includes real policy
tests. The documented [analysis-only command](docs/trying-evaluation.md#5-verify-locally)
works without it. Current verification: **702 Python tests and 7 Rego tests pass**.

```sh
uv run --locked --no-editable pytest
uv run --locked --no-editable ruff check .
uv run --locked --no-editable ruff format --check .
uv build
```

The original analysis increment had **521 passing tests**, including
real MCP stdio and example-client tests. The
[acceptance record](docs/analysis-acceptance.md) maps AN-01–AN-15 to tests and
records versions, independent wheel/stdio checks, and tested limitations.
The [synthetic fixtures](tests/fixtures/plans/README.md) use fake values; illustrative
[Terraform configuration](examples/terraform/analysis/main.tf) is not executed by
tests. No OPA setup or policy tests belong to this analysis increment.

## Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| First analysis increment | Local Terraform plan analysis, safe file loading, deterministic reports, MCP stdio, examples and tests. | Complete |
| v0.1 | All three tools and the four initial governance policy families using OPA/Rego. | In progress |
| v0.2 | Docker packaging, expanded policies, GitHub Actions CI/CD, and contributor documentation. | Planned |
| v0.3 | Read-only AWS discovery through boto3, cross-account support, and mocked integration tests. | Planned |
| v0.4+ | Potential drift analysis, module documentation retrieval, cost/operational insights, and optional RAG. | Exploratory |

Future capabilities are not included in the current server. See the
[release roadmap](docs/roadmap.md) for scope and completion criteria.

## Documentation

- [Requirements and acceptance criteria](docs/requirements.md)
- [Architecture and decisions](docs/architecture.md)
- [Connect Codex over stdio](docs/connecting-codex.md)
- [Specification 001](docs/specifications/analyze-terraform-plan.md)
- [Specification 002: policy evaluation](docs/specifications/evaluate-terraform-policies.md)
- [Specification 003: policy listing](docs/specifications/list-policies.md)
- [Policy listing walkthrough](docs/trying-listing.md)
- [Policy listing acceptance evidence](docs/listing-acceptance.md)
- [Evaluation walkthrough](docs/trying-evaluation.md)
- [Evaluation acceptance evidence](docs/evaluation-acceptance.md)
- [Implementation plan](docs/implementation-plan.md)
- [Release roadmap](docs/roadmap.md)
- [Repository guidance](AGENTS.md)

Stack: Python 3.14+, the official MCP Python SDK, Pydantic, AnyIO, uv, pytest and
Ruff. Policy evaluation uses OPA/Rego.

License: [Apache 2.0](LICENSE).
