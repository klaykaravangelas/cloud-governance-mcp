# Try governance policy listing

`list_policies` describes the bundled governance rules available to the evaluator.
It needs no plan file, OPA installation, AWS credentials or Terraform. Normal server
startup still requires an explicit existing allowed root.

## 1. Discover functions and governance rules

From the checkout, after installing uv:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-tools
uv run --locked --no-editable python examples/client.py --list-policies
```

`--list-tools` uses MCP function discovery and prints:

```json
["analyze_terraform_plan", "evaluate_terraform_policies", "list_policies"]
```

`--list-policies` calls our third function with `{}` and prints the
[full saved response](../examples/reports/policy-list.json). It contains one rule:

| Field | Value |
| --- | --- |
| `policy_id` | `AWS-RDS-001` |
| `policy_version` | `1.0.0` |
| `title` | `RDS storage encryption` |
| `severity` | `high` |
| `supported_resource_types` | `["aws_db_instance"]` |
| `required_paths` | `[["storage_encrypted"], ["cluster_identifier"]]` |
| `required_configuration` | `[]` |

The response also describes the canonical AWS provider, the encryption rule and
its standalone-only scope. `cluster_identifier` determines standalone scope;
cluster associations are not resolved. SSH, tags, S3 and RDS cluster rules are
not advertised yet. An empty configuration-requirements array means this policy
needs no policy-specific settings; evaluation still requires OPA configuration.

The example client starts and stops the real stdio server using the same Python
environment. It explicitly supplies the fixture directory as the allowed root,
even though this call reads no fixtures. Add `--legacy` to exercise the older MCP
initialization mode. The action flags `--list-tools`, `--list-policies` and
`--evaluate` are mutually exclusive.

## 2. Use the discovered ID for evaluation

After following [OPA setup](opa-setup.md), select the ID from the listing:

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path unencrypted_rds.json --opa-path .tools/opa/1.21.2/opa
```

The plan reports one encryption finding. A listed policy is bundled and
implemented; listing does not check whether the evaluator is installed, certify a
plan or inspect deployed infrastructure. See the
[evaluation walkthrough](trying-evaluation.md) for unknown values and execution
errors.

## 3. Call from an MCP host

Use the existing [host startup configuration](trying-analysis.md#7-connect-an-mcp-host-later)
with a valid `--allowed-root`. Call `list_policies` with `{}` or omit its arguments.
It accepts no filters or file paths. Both textual JSON and structured content
represent the same public report. Invalid extra arguments produce a fixed tool
error without echoing their names or values. Missing/corrupt catalog assets are
errors, not successful empty lists.

## 4. Verify listing without OPA

```sh
uv run --locked --no-editable pytest -q tests/test_listing.py tests/test_listing_mcp.py tests/test_package.py tests/test_walkthrough.py tests/test_stdio.py
```

These tests exercise core behavior, SDK auto/legacy clients, real subprocesses,
saved output, safe errors, concurrency and cancellation without OPA. The
[full verification commands](trying-evaluation.md#5-verify-locally) still require
real OPA for the evaluation regression suite. Acceptance evidence is recorded
[here](listing-acceptance.md).
