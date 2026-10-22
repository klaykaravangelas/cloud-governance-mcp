# S3 public-access protection acceptance record

Specification 007 and implementation were authorized together on 2026-10-22.
M4a–M4e add AWS-S3-001 v1.0.0, high severity, through the existing three tools.
The two exact supported types are aws_s3_bucket and
aws_s3_bucket_public_access_block. RDS/SSH/TAG versions and explicit selections
are preserved. No dependency, CLI setting, capability, transport, AWS connectivity
or Terraform execution was added. M5 release-readiness consolidation is separate.

## Executed verification

Verified on macOS arm64 with Python 3.14.7, MCP SDK 2.3.0 and OPA 1.21.2:

- **1,371 Python tests passed, no skips**, including the required Unix socket
  case under host permissions, actual OPA and SDK auto/legacy stdio.
- **187 new Python cases** cover scalar masks/types, conservative association,
  root/module context, strict graph/catalog guards, real flag aggregation,
  all 15 nonempty selection subsets plus default/reversed selection, atomic
  failures, privacy and seven saved reports in both SDK modes.
- **46/46 real Rego tests passed**, including nine S3 decision tests. Restricted
  strict compilation and format checks passed with unchanged capabilities.
- **1,077 OPA-free tests passed** with an invalid OPA path and the documented
  eight evaluation-module exclusions. Missing OPA still fails full verification.
- Ruff lint/format, uv lock/environment/dependency consistency and diff checks
  passed. Historical report comparisons explicitly select their original policy
  IDs; the default now selects RDS/S3/SSH/TAG.

Commands are in [evaluation verification](trying-evaluation.md#5-verify-locally).
The full suite and OPA-free subset execute locally without AWS credentials,
Terraform or network access. Linux execution and a generated/live-plan
compatibility campaign remain unverified.

## Acceptance traceability

| Cases | Evidence |
| --- | --- |
| S3-01 | Real exact-scope exclusions plus pure action-order tests cover managed changes, replacements, data/delete/other providers/types and inventory-only uncertainty. |
| S3-02–S3-04 | Strict scalar tests for each flag, real direct/inherited truth tables and Rego tests cover all true, each false, seven uncertainty states, false-before-uncertainty and fixed witness priorities. |
| S3-05–S3-06 | Root/scalar descendant masks, sensitivity/unknowns, merged inventory sensitivity and authoritative change-after tests prevent fallback and masked reads. |
| S3-07 | Known unique name/context links resolve regardless of resource order. Captured real OPA input retains only a block address and four safe observations. |
| S3-08 | Missing/null/invalid/unknown/sensitive/unverified/unavailable names, absent blocks/context, aliases, duplicate config identities and computed dependency references stay indeterminate. |
| S3-09 | Explicit unindexed configuration-tree module contexts resolve with opaque addresses; indexed module contexts do not. Indexed resources with explicit unindexed membership work. Missing module metadata never defaults to root without an exact configuration identity. |
| S3-10 | Duplicate buckets/blocks, globally hidden names, provider-context mismatch and deleted duplicate tests prevent unsafe inheritance. Direct block checks remain independent of linkage. |
| S3-11 | Pure serialized projections, captured actual OPA input, logs and both MCP channels exclude transient names/provider keys/unrelated sentinel values. Real stdio captures stderr and asserts it is empty, including safe traversal failures. |
| S3-12 | Schema 5 validates selected scope, exact representation/count, missing/unselected/extra payload, dangling/ineligible targets and shared targets. Existing RDS/SSH/TAG graph checks remain active. |
| S3-13 | Catalog mutations reject per-ID version/severity/type/config/path/reason/outcome changes. SDK listing advertises four entries. Seventeen real selection scenarios assert complete counts and exactly one engine invocation. |
| S3-14 | Real-engine corruptions remove/duplicate checks, change paths/reasons or forge success; every case returns OPA_OUTPUT_INVALID, zero trusted checks and no findings. |
| S3-15 | Pure configuration count/depth tests cover the new work boundary. Existing input/output/resource/runtime/admission/cancellation/containment/process cleanup suites pass unchanged. |
| S3-16 | Invalid S3-specific configuration is ignored by analysis and explicit RDS-only projection. OPA-free tests include listing and pure S3 projection. |
| S3-17 | Fourteen auto/legacy real stdio golden cases verify three-tool discovery, four-policy listing, analysis, identical text/structured reports, containment and empty stderr. |
| S3-18 | Seven new synthetic fixtures/report pairs, separate illustrative HCL and the [walkthrough](trying-s3.md) document observed protection versus effective reachability. |
| S3-19 | Actual pinned OPA strict/fmt/test, complete pytest and OPA-free selection executed; failure/capability/environment/process tests remain active. |
| S3-20 | Source/wheel and independent installed verification below exercise all three tools outside the checkout. |

## Distribution verification

Source and wheel builds succeeded. Both independent fresh uv environments use
hash-checked locked runtime dependencies and isolated Python outside the checkout.
Wheel/source installations each passed auto/legacy SDK stdio with console/module
entrypoints, empty PATH, three-tool discovery, four-policy listing, analysis,
22 saved evaluation reports, custom CostCenter keys, matching output channels,
forbidden tool-level configuration overrides and traversal denial.

All production Python/JSON/Rego bytes in each installed package match the checkout.
The wheel includes exactly four production Rego files and excludes tests,
examples, test-only policies and the OPA binary. Source archive checks compare
all current guidance/docs/tests/examples/lock files byte-for-byte. Build/setup
and verification ran offline using cached locked packages; no dependency changed.

## Runtime boundaries and remaining limitations

Only internal engine input advances to schema **5**. Public reports, engine
output, catalog and listing envelopes remain schema 1. Every selected policy
checks every resource, including exclusions; candidate counts use the selected
resource-type union. The mixed four-policy example has 4 resources, 16 checks,
6 passes, 1 SSH failure and 9 not-applicable checks.

Bucket inheritance requires known unique names and shared provider configuration
metadata. Computed references, unknown names, ambiguous resources and unproved
module context remain indeterminate. In particular, indexed module contexts are
not expanded. A root configuration identity can prove root membership by exact
opaque equality; missing module metadata alone cannot. Sensitive/unknown fields
are never treated as false, absent or enabled defaults.

Direct block decisions check the four observed flags even if their bucket is
outside the plan. A failure means a required protection setting is disabled;
absence of a matching block means insufficient plan evidence. Neither asserts
that an AWS bucket is effectively public. Account/organization settings, arbitrary
policies/ACLs, access points, directory buckets and live AWS are outside scope.

The existing long-lived Codex connection has not been verified after this
increment and may need reloading. Fresh subprocess verification is complete;
no new host configuration or permission is needed. Earlier user testing and the
historical stale-connection observation remain in the previous acceptance records.
No push, publication or remote resource change was performed.
