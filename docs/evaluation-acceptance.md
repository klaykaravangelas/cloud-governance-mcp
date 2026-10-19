# Evaluation increment acceptance evidence

Specification 002 was approved for implementation on 2026-10-19. E1–E5 add
`evaluate_terraform_policies` beside analysis, using real OPA **1.21.2** and only
**AWS-RDS-001 v1.0.0** for standalone `aws_db_instance` resources from the
canonical HashiCorp AWS provider. Policy listing and expanded policy coverage
remain outside this increment. No AWS connectivity or Terraform execution exists.

This is the E5 checkpoint record. Specification 003 subsequently adds policy
listing and updates runnable-server discovery to three tools; see
[listing evidence](listing-acceptance.md) for current regression verification.

## Verification result

The full Python suite passed: **643 tests, no skips** (26.01 seconds). Ruff lint
and formatting checks pass. Real OPA strict compilation, format checks and all
**7 Rego tests** pass. uv lock/environment/dependency checks pass. The environment is macOS
arm64, Python 3.14.7, with the existing uv lockfile and MCP SDK 2.3.0. OPA's
versioned macOS arm64 release asset was downloaded into ignored local development
storage, checksum-verified against official GitHub release metadata, and executed
locally. See [OPA setup](opa-setup.md) for all digests and installation commands.

Fresh installed-wheel verification passed outside the checkout in both SDK auto
and legacy modes: two-tool discovery, encrypted/unencrypted real OPA results and
analysis. The wheel contains only production catalog/capability/Rego assets, and
the source archive contains test Rego, docs, fixtures and examples. The extracted
source example reproduced its saved full report against the independent wheel.

Executed checks used the documented locked/non-editable workflow, with uv cache
under `/private/tmp/cloud-governance-mcp-uv-cache`. The full suite used authorized
host permissions for the existing real Unix socket fixture; none were skipped.
The documented analysis-only selection also passed **569 tests** with
`CLOUD_GOVERNANCE_OPA=/not/installed/opa`, confirming OPA is not its prerequisite.

## Acceptance traceability

| Case | Evidence |
| --- | --- |
| EV-01 | `test_evaluation_contracts.py`: strict selection/metadata; service tests prove unknown IDs are rejected before file work; SDK tests cover null/unknown/extra arguments. |
| EV-02 | Real Rego known-value tests, `test_opa_runner.py`, service/MCP tests and saved encrypted/unencrypted reports. Violations are successful tool execution. |
| EV-03 | Contract/service parameter cases for missing, null and invalid values; strict booleans reject numbers/strings/containers. |
| EV-04 | Projection tests for source mask union, root/attribute/descendant masks, unrelated paths, incomplete inventory and missing unknown metadata; existing typed mask tests remain active. |
| EV-05 | Cluster guard projection tests and real Rego scope uncertainty cases; identifiers are discarded before engine input. |
| EV-06 | Existing opaque identity/module/index tests; provider/type exclusion tests; Rego preserves a nested indexed address. |
| EV-07 | Source precedence, absent/null desired objects and inventory-only tests; service cases cover all desired-state action categories and both replacement orders. |
| EV-08 | Real empty/data/deleted/unsupported/wrong-provider cases and a defined empty Rego report; no applicable resources cannot pass. |
| EV-09 | Partial plan tests preserve verified failure and block pass. Existing warnings are carried intact; uncertain fields can coexist with complete execution. |
| EV-10 | Runner integrity tests reject duplicate/missing/extra checks, wrong IDs/addresses/reasons/outcomes/paths and inappropriate exclusions; injected incomplete engines are revalidated. |
| EV-11 | JSON/envelope tests reject undefined, empty, scalar, malformed UTF-8, duplicate keys, non-finite numbers and excessive depth. Real undefined-query execution is also tested. |
| EV-12 | Real version pin; unconfigured/missing/nonexecutable/wrong-version tests; quiet imports and analysis without OPA. |
| EV-13 | Real OPA compiler/runtime-conflict failures and test-only invalid query; nonzero process diagnostics remain absent from errors. Test policies are outside runtime assets. |
| EV-14 | Exact/over projected-input, stdout, stderr and public-report limits; overflow terminates/reaps and never truncates success. |
| EV-15 | Blocked stdin/no-output deadline; TERM-resistant child is killed/reaped; repeated native and AnyIO scope cancellation finish cleanup before returning. |
| EV-16 | Service admission test proves no queued file work and joins a cancelled worker; separate test runs analysis during active evaluation. SDK lifecycle and child cancellation tests cover cleanup. |
| EV-17 | Real capability checks reject `http.send`, `opa.runtime` and remote schemas. Child environment tests exclude inherited credentials/OPA overrides and prove payload uses stdin, not arguments. |
| EV-18 | Evaluation reuses the existing loader; denied-path service/SDK tests and the complete existing loader suite preserve containment/race/special-file checks. |
| EV-19 | Capturing engine inspects actual projected input; marked/unmarked attribute and variable sentinels are absent. SDK checks cover both channels/logs; subprocess diagnostic sentinels are safe. Resource identities intentionally remain public. |
| EV-20 | Report model invariants plus real service outcome/coverage cases, exact budgets and input-order permutations. Failed atomic batches have all checks unevaluated and no trusted findings. |
| EV-21 | `test_evaluation_mcp.py`: exact two tools/schemas/read-only hints; complete reports and structured engine errors in auto/legacy modes. Analysis-only factory injection remains for isolated regression tests. |
| EV-22 | Real stdio tests run outside checkout; independent installed-wheel verification checks assets and auto/legacy evaluation; source package contents are checked separately. |
| EV-23 | Existing analysis regressions/default walkthrough remain active, with intentional discovery expectation updated to two tools. Pure/core imports do not load MCP; analysis never requires an evaluator. |
| EV-24 | OPA setup, walkthrough, saved full reports, specification and implementation status are aligned. Full checks require real OPA; analysis-only selection is documented separately. |

## Implementation clarifications

- Catalog parse failures are fixed pre-report tool errors. A report cannot contain
  trusted policy scope when its sole source is corrupt. Missing OPA or later
  Rego/capability execution failures can return a structured failed report after
  normalization and catalog validation.
- OPA 1.21.2 has plain `version` output, not a JSON-format version flag. The bounded
  lazy probe requires exactly one matching `Version: 1.21.2` line and caches success
  for the server lifetime. The server performs no update checks.
- The child receives only explicit locale variables. macOS may itself add
  `__CF_USER_TEXT_ENCODING`; tests permit that OS-added marker while checking that
  inherited credentials/configuration do not reach the child.
- Each child uses an empty private temporary working directory. Even if an
  operator authorizes a broad root containing it, absolute fixed policy paths
  determine loaded assets; there is no working-directory policy discovery.
- Required scalar fields with masked descendants remain uncertain. A contradictory
  nested mask must not turn an untrusted scalar input into a known pass.

## Limits and remaining scope

Only macOS arm64 execution is verified here. Linux artifacts are documented but
not claimed as executed. Plans are synthetic; no Terraform-generated/live-account
compatibility campaign is claimed. Parsing threads cannot forcibly interrupt a
slow filesystem read; cancellation joins them before releasing admission.

The policy does not resolve cluster associations, inspect live databases, verify
KMS configuration or certify unsupported resources. Missing/unknown/sensitive
inputs and incomplete plans remain explicit. A pass covers only selected policy
scope in the supplied plan. At E5, L1 and expanded policies were planned; L1 is now
implemented separately, while expanded v0.1 policies remain planned.
