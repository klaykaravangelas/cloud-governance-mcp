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

The illustrative HCL in `examples/terraform/analysis` uses the built-in
`terraform_data` resource to show root, child-module, count, and for_each
identities. It is independent of these fixtures; tests do not run Terraform.
