# Try mandatory resource tags

AWS-TAG-001 v1.0.0 checks required tags with **medium** severity through the
existing `evaluate_terraform_policies` tool. Defaults are `Environment`, `Owner`
and `Project`, case sensitive. It supports EC2 instances, security groups, RDS
instances, RDS clusters and S3 buckets. No AWS credentials or Terraform are needed.

After [development setup](development.md) and [OPA setup](opa-setup.md), run:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-policies
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-TAG-001 --plan-path tags_missing_owner.json --opa-path .tools/opa/1.21.2/opa
```

The listing describes four policies, including TAG's medium severity, five
types, default keys and `required_configuration: ["required_tag_keys"]`. That
field names the setting the evaluator consumes; startup defaults satisfy it
without extra flags. Listing reads no plan, invokes no OPA, and does not reveal
this server's configured override values.

The evaluation completes with failed compliance. Its single finding identifies
`aws_instance.example`, reason `TAG_ALL_KEY_MISSING`, severity `medium` and path
`["tags_all", "Owner"]`. The explanation is fixed; no tag value is returned.
Compare the [actual saved report](../examples/reports/tags-missing-owner.json).

## Compare known and uncertain outcomes

Replace the plan filename in the TAG-only command above:

| Plan | Result |
| --- | --- |
| `tags_compliant.json` | pass: all three required values are known nonblank strings. |
| `tags_missing_owner.json` | fail: Owner is missing. |
| `tags_empty_project.json` | fail: Project contains only whitespace. |
| `tags_unknown_owner.json` | indeterminate: Owner is masked unknown, not known missing. |
| `tags_provider_defaults.json` | pass: tags_all contains inherited defaults absent from resource-only tags. |

There is one check per resource and selected policy. Several bad tags produce
one finding, pointing to the first failing key in sorted configuration order.
A known missing/blank/null value wins over an uncertain sibling. Without a known
failure, sensitivity wins over unknown, then invalid type. Empty findings alone
do not establish compliance; inspect status and coverage. Engine failures are
errors with no trusted findings, separate from policy violations.

## Configure different required keys

`--required-tag-key` is a repeatable **server-startup** option. The first occurrence
replaces all defaults; subsequent occurrences extend that explicit list. For a
server that requires only CostCenter:

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-TAG-001 --plan-path tags_custom_keys.json --required-tag-key CostCenter --opa-path .tools/opa/1.21.2/opa
```

This passes and matches [the saved custom-key report](../examples/reports/tags-custom-keys.json).
The same fixture under default settings fails because the three default keys
are absent. To require CostCenter **as well as** the defaults, supply all four:

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-TAG-001 --plan-path tags_compliant.json --required-tag-key Environment --required-tag-key Owner --required-tag-key Project --required-tag-key CostCenter --opa-path .tools/opa/1.21.2/opa
```

That fixture fails at `tags_all.CostCenter`. Add the same repeated flags to an
MCP host's existing server arguments to set its requirements. The example client
forwards them to the server it launches; it does not send them as tool inputs.
Changing startup settings requires a new server process. A tool call cannot
override or relax the requirement.

Use 1–50 distinct keys, 1–128 ASCII characters from letters, digits and
`_./:=+@-`. Spaces, control characters and case-insensitive `aws:` prefixes are
rejected. Keys are case sensitive and sorted; exact duplicates fail rather than
silently disappearing. Invalid settings yield fixed startup diagnostics.

## Reproduce the three-policy checkpoint

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --policy-id AWS-SG-001 --policy-id AWS-TAG-001 --plan-path mixed_rds_ssh_tags.json --opa-path .tools/opa/1.21.2/opa
```

This explicit selection uses RDS, SSH and TAG. Omission now also selects S3. This synthetic plan has one encrypted RDS
instance, one world-open inline SSH group and one S3 bucket; all have complete
required tags. Expect **3 resources, 3 candidates, 9 checks: 4 pass, 1 SSH failure,
4 not applicable**. S3 is a tagging candidate; this does not check public access.
See [the saved combined report](../examples/reports/mixed-rds-ssh-tags.json).

Use `--policy-id AWS-RDS-001 --policy-id AWS-SG-001` to reproduce the previous
six-check scope. Explicit old-policy results are unchanged; default reports
include all four policies. Use the [S3 walkthrough](trying-s3.md) for the current default report.
Older untagged fixtures can fail tag requirements.
Add `--legacy` to exercise the older MCP initialization mode.

## What is checked and protected

The selected desired `tags_all` map is authoritative. Fallback to `tags` happens
only when tags_all is provably absent, not when it is unknown, sensitive, null or
empty. Known null/absent maps supply no required values and fail; masked null
placeholders remain uncertain. The server does not reconstruct provider defaults,
ignored/external tags or live AWS state. Results concern the supplied plan only.

Required known strings must contain a non-whitespace character. Null/blank/missing
values fail; known nonstring values are indeterminate. Raw values, unrequired tag
names, hashes and excerpts never reach OPA or reports. Sensitivity is conservatively
combined across tags/tags_all copies. A field path can name only a configured key.
Fixed work, byte and runtime limits can reject a plan safely; no report is truncated.

Fixtures are hand-authored with fake values. The
[illustrative HCL](../examples/terraform/tags/main.tf) shows provider defaults plus
a resource Owner tag; it was not run or used to generate these fixtures.

## Test through an MCP host

After the updated server is loaded, request actual cloud-governance-mcp calls:

1. List policies; expect RDS/SSH high severity and TAG medium, with default keys
   explained and no configured override values exposed.
2. Evaluate `tags_missing_owner.json` using only AWS-TAG-001; expect one Owner finding.
3. Evaluate `tags_unknown_owner.json` using only AWS-TAG-001; explain the uncertainty.
4. Evaluate `mixed_rds_ssh_tags.json` with omitted policy IDs; expect nine checks.

The host uses `{"plan_path":"tags_missing_owner.json","policy_ids":["AWS-TAG-001"]}`.
`required_tag_keys` is not an accepted tool argument. Confirm actual MCP calls,
not shell inspection of fixtures. Fresh subprocess evidence and live host checks
are distinguished in the [acceptance record](tags-acceptance.md).
