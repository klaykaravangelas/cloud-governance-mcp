# Try RDS cluster encryption

AWS-RDS-001 **v1.1.0** checks standalone `aws_db_instance`, direct
`aws_rds_cluster` encryption, and `aws_rds_cluster_instance` members. It uses the
same `evaluate_terraform_policies` tool and startup configuration. No AWS
credentials or Terraform installation is needed. Set up the pinned local OPA
binary using [OPA setup](opa-setup.md), then run from the checkout:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path cluster_encrypted.json --opa-path .tools/opa/1.21.2/opa
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path cluster_unencrypted.json --opa-path .tools/opa/1.21.2/opa
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path cluster_unknown_arn.json --opa-path .tools/opa/1.21.2/opa
```

Each synthetic plan has one cluster and two members:

| Plan | Compliance | Passed | Failed | Indeterminate |
| --- | --- | --- | --- | --- |
| `cluster_encrypted.json` | pass | 3 | 0 | 0 |
| `cluster_unencrypted.json` | fail | 0 | 3 | 0 |
| `cluster_unknown_arn.json` | indeterminate | 1 | 0 | 2 |

All three return `evaluation_status: complete` and exit zero: a violation or
uncertain resource is a policy outcome, not an engine failure. These are three
resource checks, not three independent root causes. Compare saved real stdio
reports: [pass](../examples/reports/cluster-encrypted.json),
[fail](../examples/reports/cluster-unencrypted.json),
[uncertainty](../examples/reports/cluster-unknown-arn.json).

The cluster's desired `storage_encrypted` must be a known boolean. A member
inherits only from a unique observed eligible cluster whose known identifier and
AWS partition/account/Region context match. Matching uses masked desired values;
the raw identifiers and ARNs do not survive into OPA or results. A member's own
computed encryption copy is ignored, even when it contradicts its cluster. Fix
encryption on the intended cluster, rather than configuring that computed field.

New-resource plans commonly have unknown ARNs. Members then remain indeterminate
even when the cluster passes, because configuration dependency references alone
cannot prove a matching identifier/context. Missing targets, possible uncertain
duplicates and ambiguous keys also block inheritance. No live AWS state,
encryption default or provider alias is guessed. Direct cluster encryption checks
need no identifier or ARN. See [Specification 004](specifications/expanded-rds-encryption.md)
for exact states and supported ARN partitions.

The fixtures are hand-authored synthetic examples with fake identifiers, not
Terraform exports. Their contradictory member encryption copies deliberately
test cluster authority. The [illustrative HCL](../examples/terraform/rds/main.tf)
shows cluster/member configuration but is not executed or used to generate these
fixtures. Never add `storage_encrypted` to a cluster-instance configuration.

For Codex, reconnect the configured MCP server after installing the updated
package, then ask it to call `list_policies` and evaluate each plan above with `policy_ids: ["AWS-RDS-001"]`. Expect
version 1.1.0 and the table's counts. Verify actual tool calls. The
[acceptance record](rds-acceptance.md) distinguishes fresh stdio verification from
the existing Codex process's pending reload test.
