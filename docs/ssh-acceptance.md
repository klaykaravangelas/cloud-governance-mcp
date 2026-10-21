# SSH ingress acceptance record

The user approved Specification 005 for implementation on 2026-10-21. M2a–M2d
implement masked SSH observations, real Rego and two-policy integration; M2e adds
examples, documentation and verification. Current coverage is AWS-RDS-001 v1.1.0
and AWS-SG-001 v1.0.0 through the existing three tools. No dependency, tool, CLI
setting, Terraform execution or cloud API was added.

## Executed verification

Verified on macOS arm64 with Python 3.14.7, MCP SDK 2.3.0 and OPA 1.21.2:

- **1,009 Python tests passed, no skips**, including the local Unix socket fixture
  under host permissions, real OPA, SDK auto/legacy and real stdio.
- **29/29 Rego tests passed**. SSH cases include direct world sources, port ranges,
  all protocols, source/permission short-circuiting, references/prefix lists,
  every uncertainty state, deterministic aggregation and exclusions. Dispatch
  tests cover both policies and cross-scope not-applicable checks.
- Ruff lint and format checks passed (88 Python files). Real Rego strict check,
  format check and all 29 tests passed with the restricted capabilities.
- uv lock/environment consistency and installed dependency checks passed without
  dependency additions. **857 OPA-free tests passed** with a deliberately invalid
  OPA path and the documented six evaluation-module exclusions.
- New saved reports and the two-policy listing were captured from actual SDK
  stdio requests. RDS-only report goldens remain unchanged; their commands/tests
  now select RDS explicitly. Public analysis remains unchanged.

See [development](development.md), [verification commands](trying-evaluation.md#5-verify-locally)
and [the SSH walkthrough](trying-ssh.md). Full evaluation verification requires
the real pinned OPA and fails clearly if it is absent. Pure checks remain OPA-free.

## Acceptance traceability

| Cases | Evidence |
| --- | --- |
| SG-01–SG-04 | `test_ssh_projection.py`, `test_ssh_evaluation.py`, `ssh_test.rego`: three formats, scope/exclusions, IPv4/IPv6, TCP/ranges/all protocols, strict numeric syntax/bounds, non-SSH controls. |
| SG-05–SG-06 | Sources/reference/prefix-list/empty-ingress tests; family/prefix validation and host-bit normalization; real source and uncertainty outcomes. No live source expansion is performed. |
| SG-07–SG-08 | Root/attribute/index/descendant mask tests, metadata completeness and inventory sensitivity union; reordered sensitive inline set is withheld and unknown tails cannot disappear. |
| SG-09–SG-10 | Real Rego and services verify one aggregate reason, failure over unknown siblings, deterministic necessary uncertainty and safe-predicate short-circuiting. |
| SG-11–SG-12 | `test_ssh_pipeline.py` exercises authoritative after across six action orderings, null/missing after, inventory-only state and no before fallback. Existing address/module/index tests and no-group-lookup projection remain active. |
| SG-13–SG-14 | Pure snapshot/repr checks plus capturing real engine inputs and both SDK channels/logs exclude source/reference/description sentinels. Strict contract/graph tests reject state payloads, family coercion, wrong representation/direction/type and old schema; existing RDS graph tests pass. |
| SG-15–SG-17 | Complete wrong-reason batches, cross-policy reason catalog/version/scope mutations and existing exhaustive engine-failure tests; selection tests in both MCP modes; listing still works without OPA or plan access. |
| SG-18–SG-20 | The three-resource accounting matrix runs through real OPA with one engine invocation. Egress-only and atomic-failure cases pass; RDS-only controls and explicit forbidden unselected-projection callbacks prove separation. |
| SG-21–SG-22 | SDK memory/stdio × auto/legacy tests, old and new schema/error tests, real restricted OPA runner, environment/network/runtime/schema-fetch denial and owned subprocess cleanup regressions. |
| SG-23 | Exact/over work ceilings, a 10,000-rule graph with one resource view, injected global-rule overflow rejection, and existing byte/depth/resource/runtime/admission/cancellation tests. |
| SG-24 | Five synthetic plan/report pairs, separate HCL examples, real stdio golden tests in both modes, updated selection and host prompts. This observer's live host reload is recorded separately below. |
| SG-25 | Source/wheel inclusion and two independent fresh installed environments passed the checks below. |

## Distribution verification

Both source and wheel built successfully. All 34 production Python/JSON/Rego
files in the wheel matched the checkout byte-for-byte; exactly the two production
Rego files were included, with no test assets or OPA binary. All 95 current
guidance/docs/tests/examples/lock files were included byte-for-byte in the source
archive at the packaging checkpoint.

Fresh wheel and source installations in separate uv environments under
`/private/tmp`, with locked runtime dependencies, ran isolated Python outside the
checkout. Each exercised console/module startup and SDK auto/legacy stdio modes:
three-tool discovery, both catalog entries, unchanged analysis golden, five SSH/
mixed saved reports, three explicitly RDS-only cluster reports, the one/both-policy
selection matrix, identical text/structured output and traversal denial. Imports
came from each installed environment and all installed production files matched
the source. This verifies packaged operation rather than importing the checkout.

## Important implementation boundaries

- Engine input schema is **3**; public/engine output and catalog envelopes remain
  schema 1. Strict per-ID metadata guards replace single-policy assumptions.
- Omission selects both enabled IDs. Resource buckets use the selected-policy
  union, while expected/evaluated checks include every resource/policy pair.
- Projection is selected per call. RDS-only calls never inspect SSH fields/work
  ceilings; SSH-only calls do not build RDS associations. Shared adapter settings
  are not mutated per request.
- Rego owns exposure decisions. Python retains numeric protocol/port/prefix and
  reference-presence observations only. `lte` is the sole added capability;
  network/runtime capabilities stay unavailable.
- Rule/source work is bounded before payload allocation/parsing. OPA's existing
  byte/output/deadline budgets can still reject plans below work ceilings; they
  were not enlarged. Unsupported/missing checks and engine errors cannot pass.

## Host observation and limitations

The user reported successful MCP use after the prior RDS increment. That report
is preserved in [RDS evidence](rds-acceptance.md). It is not claimed as an observed
SSH test. This chat had a stale running MCP process during that increment; no
targeted restart control is exposed here. Fresh subprocesses provide the
automated stdio evidence. After reconnecting, use the SSH walkthrough's four
prompts and record actual two-policy calls before claiming a successful live
new-version Codex smoke test. This does not require repeating prior familiarization
or block implementation/automated acceptance.

No Linux execution, live AWS/generated-plan compatibility campaign, prefix-list
expansion, CIDR-union analysis or effective network reachability is claimed.
Inline sensitivity can conservatively withhold otherwise apparently known rules
because provider sets cannot be aligned by cross-source array positions.
Illustrative HCL was not executed. Changes remain local; no GitHub push occurred.
