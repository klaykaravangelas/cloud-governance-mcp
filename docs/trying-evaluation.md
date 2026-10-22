# Try Terraform policy evaluation

The server exposes `analyze_terraform_plan`, `evaluate_terraform_policies` and
`list_policies`. Three policies are implemented: **AWS-RDS-001**
v1.1.0 checks standalone instances, clusters and conservatively resolved cluster
members; **AWS-SG-001** v1.0.0 checks direct unrestricted SSH ingress in three
Terraform representations, both high severity. **AWS-TAG-001** v1.0.0 checks
mandatory resource tags with medium severity. The [listing tool](trying-listing.md)
describes all four. AWS-S3-001 checks bucket-level public-access protection; see
the [S3 walkthrough](trying-s3.md). This walkthrough selects RDS explicitly;
see the [SSH](trying-ssh.md) and [tags](trying-tags.md) walkthroughs for other scopes.

## 1. Prepare the local runtime

Use [development setup](development.md) and [OPA setup](opa-setup.md).
Install OPA **1.21.2** under `.tools/opa/1.21.2/opa`, verify its checksum, then:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-tools
```

Expected tools:

```json
["analyze_terraform_plan", "evaluate_terraform_policies", "list_policies"]
```

Listing tools/policies and analyzing plans still work without OPA. The server never
downloads it or looks it up in PATH automatically.

## 2. Compare known encryption outcomes

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path encrypted_rds.json --opa-path .tools/opa/1.21.2/opa
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path unencrypted_rds.json --opa-path .tools/opa/1.21.2/opa
```

Both requests complete normally. The encrypted plan reports `pass`; the other
reports `fail` and one finding for `aws_db_instance.example`, with policy ID,
severity, reason, explanation and remediation text. A violation is a successful
policy evaluation, so both example commands exit zero.

Compare the actual full reports:
[encrypted](../examples/reports/encrypted-rds-evaluation.json) and
[unencrypted](../examples/reports/unencrypted-rds-evaluation.json).
These fixtures are synthetic; no Terraform or AWS execution is required.

## 3. Understand uncertainty and execution errors

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path unknown_sensitive.json --opa-path .tools/opa/1.21.2/opa
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path encrypted_rds.json
```

The first response is a safe report with indeterminate checks and partial plan
coverage. It never includes the sensitive values. The second intentionally omits
the evaluator configuration: it returns `OPA_NOT_CONFIGURED`, failed execution,
indeterminate compliance and no findings, with example-client exit code 1 and the
safe report on stderr. It does not mean encryption was disabled.

`evaluation_status` describes execution/coverage; `compliance_status` describes
the selected rules. Known violations take precedence over uncertain checks.
Complete plans with no applicable resources are `not_applicable`, never `pass`.
Partial plans conservatively cannot establish a pass. Unsupported resource counts
and the policy scope explain what was excluded. The legacy `aws_db_instance`
association guard remains indeterminate. Actual `aws_rds_cluster_instance`
members inherit only from a unique known same-plan cluster and compatible AWS
ARN context; computed or ambiguous links stay indeterminate. Follow the
[cluster walkthrough](trying-rds-clusters.md) for pass/fail/unknown-ARN examples.

## 4. Select a policy and use an AI host

Add `--policy-id AWS-RDS-001` to explicitly select the rule; omission selects the
enabled catalog: all four IDs. Repeat `--policy-id` to select a subset explicitly.
Empty, duplicate and unknown selections fail safely. Add
`--legacy` to any example to test the older MCP initialization mode.

Use an existing absolute plan directory and the absolute OPA path in the host's
process definition:

```json
{
  "command": "/absolute/path/to/cloud-governance-mcp/.venv/bin/cloud-governance-mcp",
  "args": [
    "--allowed-root", "/absolute/path/to/plans",
    "--opa-path", "/absolute/path/to/cloud-governance-mcp/.tools/opa/1.21.2/opa"
  ]
}
```

The enclosing configuration is host-specific. Call `evaluate_terraform_policies`
with `{"plan_path":"plan.json","policy_ids":["AWS-RDS-001"]}`. The host replaces
the example client; server logic stays the same. Root containment, symlink
refusal and plan limits are identical to analysis.

## 5. Verify locally

From the repository root, with the pinned local binary installed:

```sh
uv run --locked --no-editable pytest -q
uv run --locked --no-editable ruff check .
uv run --locked --no-editable ruff format --check .
.tools/opa/1.21.2/opa check --strict --capabilities src/cloud_governance_mcp/policies/capabilities.json src/cloud_governance_mcp/policies/rego
.tools/opa/1.21.2/opa fmt --fail --list src/cloud_governance_mcp/policies/rego tests/policies
.tools/opa/1.21.2/opa test --capabilities src/cloud_governance_mcp/policies/capabilities.json src/cloud_governance_mcp/policies/rego src/cloud_governance_mcp/policies/catalog.json tests/policies
```

Full evaluation/release verification fails if OPA is missing; it never silently
skips real policy tests. Tests can select an alternate absolute binary path using
`CLOUD_GOVERNANCE_OPA`; that test-only environment setting does not configure the
server. To run analysis/listing plus pure evaluation contracts/projection checks without OPA:

```sh
uv run --locked --no-editable pytest -q --ignore=tests/test_policy_execution.py --ignore=tests/test_opa_runner.py --ignore=tests/test_evaluation_service.py --ignore=tests/test_evaluation_mcp.py --ignore=tests/test_rds_evaluation.py --ignore=tests/test_ssh_evaluation.py --ignore=tests/test_tag_evaluation.py --ignore=tests/test_s3_evaluation.py
```

No AWS credentials, network access, Terraform, live resources, or infrastructure
modifications are needed by the verification itself.
