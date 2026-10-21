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
[full saved response](../examples/reports/policy-list.json). It contains two rules:

| Policy | Version | Severity | Supported resources |
| --- | --- | --- | --- |
| `AWS-RDS-001` | `1.1.0` | `high` | `aws_db_instance`, `aws_rds_cluster`, `aws_rds_cluster_instance` |
| `AWS-SG-001` | `1.0.0` | `high` | `aws_security_group`, `aws_security_group_rule`, `aws_vpc_security_group_ingress_rule` |

The response includes titles, descriptions, canonical AWS provider, required paths
and scope limitations. RDS members need a unique known same-plan cluster with
matching identifier and ARN context; computed or ambiguous links remain
indeterminate. SSH covers direct individual world-wide CIDRs with TCP port 22 or
all protocols; unresolved prefix lists are not expanded. See the
[SSH walkthrough](trying-ssh.md) for its uncertainty rules. Tags, S3 and
global-cluster rules are not advertised.

Both entries explicitly return `required_configuration: []`: neither needs
policy-specific settings. Evaluation still requires OPA configuration.

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
