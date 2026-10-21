# Synthetic plan fixtures

These hand-authored JSON documents model selected Terraform plan structures with
fake identifiers and values. They are not exports from an AWS account and do not
require Terraform, credentials, OPA, or network access.

| File | Purpose |
| --- | --- |
| `mixed_nested.json` | Seven resources across all seven action categories, nested modules, numeric/string indices, multiple providers, and a change-only deletion. |
| `encrypted_rds.json` / `unencrypted_rds.json` | Contrasting encryption values for later policy tests. Analysis treats both as creates and makes no compliance decision. |
| `unknown_sensitive.json` | Object/list/root masks and marked/unmarked secret sentinels, variables, outputs, and additive fields that must not survive normalization. |
| `empty.json` | Available empty inventories with explicit complete planning. |
| `partial.json` | Incomplete/errored planning and opaque deferred, drift, output, and import payloads. |
| `malformed.json` | Valid JSON with an invalid consumed Terraform structure. |
| `cluster_encrypted.json` / `cluster_unencrypted.json` | Complete synthetic existing-cluster no-op plans with one cluster, two members and fake known identifiers/ARNs. Member computed encryption intentionally contradicts the cluster to test authority. Expected three pass/three fail checks. |
| `cluster_unknown_arn.json` | Same graph with unknown ARN masks; direct cluster passes while two member links remain indeterminate. Models the common creation-time limitation without claiming a generated plan. |
| `ssh_inline_open.json` | Inline security group with direct IPv4 world access to TCP 22; fails SSH. |
| `ssh_legacy_restricted.json` | Legacy ingress rule restricted to a documentation-range CIDR; passes the bounded SSH rule. |
| `ssh_modern_open.json` | Modern IPv6 world ingress with all protocols and omitted ports; fails SSH. |
| `ssh_unknown.json` | Modern rule whose source sentinel is masked unknown; indeterminate with no raw source in OPA/output. |
| `mixed_rds_ssh.json` | Encrypted RDS, open SSH and unsupported S3; default two-policy evaluation yields six checks: one pass, one fail and four not applicable. |

The illustrative HCL in `examples/terraform/analysis` uses the built-in
`terraform_data` resource to show root, child-module, count, and for_each
identities. It is independent of these fixtures; tests do not run Terraform.
`examples/terraform/rds/main.tf` separately illustrates cluster/member configuration.
Separate `examples/terraform/ssh/inline`, `legacy` and `modern` directories
illustrate each rule format without combining competing security-group management
styles. They are not run and do not generate these synthetic JSON fixtures.
