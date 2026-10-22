# Try unrestricted SSH ingress

This walkthrough selects AWS-RDS-001 v1.1.0 and **AWS-SG-001 v1.0.0** explicitly.
The server also supports AWS-TAG-001; omitted policy IDs now select all three.
Use the [tags walkthrough](trying-tags.md) for default combined-policy examples. Each observed
resource receives one check per selected policy, including not-applicable checks.
No AWS credentials or Terraform execution is needed. Follow [setup](development.md)
and [OPA installation](opa-setup.md), then run from the checkout:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable python examples/client.py --list-policies
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --policy-id AWS-SG-001 --plan-path mixed_rds_ssh.json --opa-path .tools/opa/1.21.2/opa
```

Under the explicit RDS + SSH selection, the mixed synthetic plan has an encrypted RDS instance, a world-open SSH group,
and an unsupported S3 bucket. It returns complete execution and failed compliance:
**3 resources, 2 candidates, 6 checks: 1 pass, 1 fail, 4 not applicable**.
The bucket remains outside the selected policies; the opposite-policy checks on
RDS/network resources are also not applicable. See the
[saved report](../examples/reports/mixed-rds-ssh.json).

## Select one policy or both

```sh
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-RDS-001 --plan-path mixed_rds_ssh.json --opa-path .tools/opa/1.21.2/opa
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-SG-001 --plan-path mixed_rds_ssh.json --opa-path .tools/opa/1.21.2/opa
uv run --locked --no-editable python examples/client.py --evaluate --policy-id AWS-SG-001 --policy-id AWS-RDS-001 --plan-path mixed_rds_ssh.json --opa-path .tools/opa/1.21.2/opa
```

RDS-only returns 3 checks (one pass, two N/A); SSH-only returns 3 checks (one fail,
two N/A). Both IDs, in either order, produce the same sorted two-policy selection. Omission
now additionally selects TAG; old fixtures may fail its required-tag checks.
Empty/null/duplicate/unknown selections fail safely before file access. Add
`--legacy` to exercise the older MCP initialization mode. Historical RDS guides
now explicitly select RDS so their saved report counts remain unchanged.

## Exercise the three Terraform rule formats

Substitute each filename into `--plan-path` in the command above:

| Plan | Format | Default combined result |
| --- | --- | --- |
| `ssh_inline_open.json` | `aws_security_group.ingress` | fail: one SSH failure and one RDS N/A |
| `ssh_legacy_restricted.json` | `aws_security_group_rule` | pass: one SSH pass and one RDS N/A |
| `ssh_modern_open.json` | `aws_vpc_security_group_ingress_rule` | fail: IPv6 world access with all protocols; one SSH failure and one RDS N/A |
| `ssh_unknown.json` | Modern rule with unknown CIDR | indeterminate: one SSH uncertainty and one RDS N/A |

Reports are saved under `examples/reports/` with matching hyphenated names.
These are hand-authored synthetic plans with fake/example identifiers, not
Terraform exports. Separate illustrative configurations live under
[examples/terraform/ssh](../examples/terraform/ssh). Tests do not run them or
combine different rule-management formats on one real security group.

A violating policy outcome is successful evaluation: the example client exits
zero. An engine failure, such as missing OPA, returns a safe error report and a
nonzero exit; no trusted findings survive that failure.

## What the result establishes

SSH fails for a known individual IPv4/IPv6 world CIDR with TCP port 22, a range
containing 22, or all protocols. Known non-SSH permissions and complete known
non-world source sets can pass. Nonzero prefixes are not automatically private
or trusted. Prefix-list contents, CIDR unions and effective reachability are not
analyzed; a relevant unresolved prefix list is indeterminate. Self/group references
are presence observations, not an expansion of permissions from other groups.

The parser retains only protocol numbers, port intervals, CIDR family/prefix
lengths and presence/uncertainty states. Raw CIDRs, descriptions and reference
IDs never reach OPA or public reports. Rego makes the exposure decision. A known
violating inline rule wins over unknown siblings, but consumed sensitivity in
an unordered inline collection withholds the whole collection before evaluation.
This deliberately favors privacy over guessing which reordered element was masked.
Unknown tails and missing ingress cannot become empty, passing arrays.

Findings use the resource address and a fixed reason. Inline findings point to
`ingress` as a whole, without a provider-set index. Multiple violating inline
rules still produce one resource-policy finding, not multiple root-cause counts.

## Test directly through Codex

After installing/reconnecting the updated configured server, ask Codex to call
the **cloud-governance-mcp tools**:

1. “List the policies.” Expect RDS v1.1.0 and SSH v1.0.0 high severity, plus TAG v1.0.0 medium.
2. “Evaluate `mixed_rds_ssh.json` using only AWS-RDS-001 and AWS-SG-001.” Expect the
   six-check result above and one SSH finding.
3. “Evaluate the same plan using only AWS-RDS-001, then only AWS-SG-001.” Expect
   three checks in each case and the different compliance statuses above.
4. “Evaluate `ssh_unknown.json` using only AWS-RDS-001 and AWS-SG-001 and explain why it cannot pass.” Expect explicit
   uncertainty, without the raw source value.

Confirm actual MCP calls rather than shell inspection of JSON. Fresh SDK stdio
traces and user-reported tests are recorded separately in
[SSH acceptance](ssh-acceptance.md). A stale existing host process must load the
new package before it can advertise newly added policies.
