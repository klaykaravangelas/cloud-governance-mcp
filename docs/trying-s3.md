# Try S3 public-access protection

AWS-S3-001 v1.0.0 is high severity. It checks four observed bucket-level
public-access-block flags through `evaluate_terraform_policies`; there is no new
MCP tool or startup option. Analysis and listing still need no OPA.

## Run locally

From the checkout, follow [OPA setup](opa-setup.md), then run:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-policies
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-S3-001 --plan-path s3_compliant.json --opa-path .tools/opa/1.21.2/opa
```

The compliant fixture has a bucket and one matching block: **2 resources,
2 checks, 2 passes**. Replace the plan filename to try:

| Synthetic plan | Expected S3-only result |
| --- | --- |
| `s3_disabled_flag.json` | Fail: block_public_policy is false; two findings, one direct and one inherited. |
| `s3_unknown_flag.json` | Indeterminate: restrict_public_buckets is unknown; two uncertain checks. |
| `s3_missing_block.json` | Indeterminate: no matching protection resource; one uncertain bucket check. |
| `s3_computed_link.json` | One passing block and one indeterminate bucket: the bucket argument is computed. |
| `s3_ambiguous_link.json` | Two passing blocks and one indeterminate bucket: matching blocks are ambiguous. |

Add `--legacy` to exercise the older SDK handshake. Compare the
[compliant plan](../tests/fixtures/plans/s3_compliant.json) with its
[report](../examples/reports/s3-compliant.json), and the
[computed-link report](../examples/reports/s3-computed-link.json).
These fixtures are synthetic, not Terraform-generated AWS exports. The
[illustrative HCL](../examples/terraform/s3/main.tf) has not been executed.

## What a result means

The policy requires `block_public_acls`, `ignore_public_acls`,
`block_public_policy` and `restrict_public_buckets` to be known true. A known
false flag fails even when siblings are uncertain. Missing/null flags remain
indeterminate; the server does not fill in provider defaults. Sensitive and
unknown masks are applied before values are read.

A block is checked directly even if its bucket is outside the plan. A bucket
inherits only from one uniquely matching known name, with the same known provider
configuration key. Unresolved names elsewhere can conceal duplicates and prevent
inheritance. Missing provider metadata, ambiguous matches, unproved module context
and computed expression references remain indeterminate. Root membership needs
an exact opaque configuration identity when explicit module metadata is absent;
indexed module contexts are conservatively unsupported for inheritance.

Raw bucket names and provider keys are discarded before OPA. Direct findings
identify the failed flag; bucket findings identify `bucket`. A missing block
is not proof that a deployed bucket is public. The policy checks observed
bucket-level protection, not effective public reachability, arbitrary ACLs/bucket
policies, account settings or live AWS defaults.

## Evaluate all four policies

```sh
uv run --locked --no-editable python examples/client.py --evaluate --plan-path mixed_all_policies.json --opa-path .tools/opa/1.21.2/opa
```

Omission selects RDS, S3, SSH and TAG. This example has **4 resources, 4 candidates,
16 checks: 6 pass, 1 SSH failure and 9 not applicable**. See its
[saved report](../examples/reports/mixed-all-policies.json).
Use explicit policy IDs to reproduce historical single/two/three-policy reports.
All selections use one OPA invocation; a malformed engine batch fails atomically.

## Call from your MCP host

Reload the existing server connection after reinstalling the package; a running
process does not reload Python modules. The existing allowed fixture root and OPA
path are sufficient. No new permission or startup setting is needed.

1. Ask it to list governance policies; expect AWS-S3-001 v1.0.0, high severity.
2. Ask it to evaluate `s3_disabled_flag.json` using only AWS-S3-001.
3. Ask it to compare `s3_missing_block.json` and `s3_computed_link.json`, explaining uncertainty.
4. Ask it to evaluate `mixed_all_policies.json` using all available policies.

The direct MCP arguments for step 2 are:

```json
{"plan_path":"s3_disabled_flag.json","policy_ids":["AWS-S3-001"]}
```

See [the specification](specifications/s3-public-access-protection.md) for the
complete contract and [acceptance evidence](s3-acceptance.md) for executed checks
and separately recorded platform/host limitations.
