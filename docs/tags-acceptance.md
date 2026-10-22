# Mandatory resource tags acceptance record

The user authorized Specification 006 implementation on 2026-10-22. M3a–M3e add
AWS-TAG-001 v1.0.0, medium severity, through the existing three tools. Defaults
are Environment/Owner/Project; startup flags replace that list. Five exact AWS
resource types are supported. RDS/SSH versions and explicit-selection outcomes
are preserved. No dependency, OPA capability, MCP argument, transport, Terraform
execution or cloud access was added.

## Executed verification

On macOS arm64 with Python 3.14.7, MCP SDK 2.3.0 and OPA 1.21.2:

- **1,184 Python tests passed, no skips**, including the real local Unix socket
  fixture under host permissions, actual OPA, SDK auto/legacy and real stdio.
- The **175 new Python cases** cover settings, pure projection, strict graph/
  metadata/path guards, real aggregation, all seven selection subsets, safe
  errors, default/custom startup keys and seven saved reports in both modes.
- **37/37 real Rego tests passed** with unchanged restricted capabilities;
  strict compilation and format checks passed. TAG adds eight decision tests.
- Seven new reports and the three-policy listing were captured from actual SDK
  stdio calls. Existing analysis, explicit RDS and explicit RDS+SSH saved reports
  remain unchanged. The example client forwards startup keys as literal arguments.

**966 OPA-free tests passed** with an invalid OPA path and the documented seven
real-evaluation-module exclusions. Ruff lint/format (98 files), uv lock/environment
consistency and installed dependency checks passed. Dependencies and capabilities
are unchanged. Distribution evidence is recorded below. These results do not
imply a live Codex connection was reloaded.
Commands are in [evaluation verification](trying-evaluation.md#5-verify-locally);
manual examples are in the [tags walkthrough](trying-tags.md).

## Acceptance traceability

| Cases | Evidence |
| --- | --- |
| TG-01 | `test_tag_projection.py` checks the five exact types; `test_real_exact_tag_type_scope` executes every supported type and member/rule exclusions through OPA. Existing generic nested/indexed-address tests remain active. |
| TG-02–TG-03 | `test_tag_contracts.py`, startup/parser tests and service-snapshot tests cover defaults/replacement, case/order, exact/over key limits, malformed/reserved keys and fixed diagnostics before roots. Literal option-looking keys are accepted through equals syntax. Existing missing-option/abbreviation CLI tests remain active. |
| TG-04–TG-05 | Pure strict string/type/source tests and real per-key/map cases cover nonblank/blank/null/absence, invalid types, tags_all authority, conflicting tags, defaults observations and resource-only fallback. No provider merge or live lookup is implemented. |
| TG-06–TG-07 | Root/map/key/descendant masks, absent/null/malformed placeholders, cross-copy sensitivity and irrelevant sibling masks are tested. Unknown metadata absence remains unverified; existing adapter source-mask union and after precedence apply before TAG. |
| TG-08 | Real Rego and service cases prove deterministic first failing key, failure over uncertainty, sensitivity/unknown/invalid priority and withheld-map outcomes. Eight TAG Rego tests exercise core rules and exclusions, including empty config/entry rejection. |
| TG-09 | Five authoritative-after action cases plus existing source/deletion/inventory regressions preserve changes, replacements and inventory-only uncertainty. |
| TG-10 | `test_tag_pipeline.py` rejects old schema, absent/empty/foreign config, raw payload, missing/duplicate/unordered keys and ineligible/unselected projections. A real-engine test rejects internally consistent config that differs from its operator snapshot before probing OPA. Existing RDS/SSH graph checks pass. |
| TG-11 | Per-ID catalog/version/type/severity/config/reason mutations reject cross-policy mixtures. Listing tests and SDK discovery verify three entries; medium TAG severity does not relax RDS/SSH high severity. Listing remains OPA/plan independent. |
| TG-12 | SDK tests exercise invalid/null/empty/duplicate/unknown/oversized selections and forbidden per-request settings. Separate forbidden-loader tests prove invalid selection precedes file access. Tool schemas remain three read-only tools. |
| TG-13 | Eight real service scenarios cover all seven nonempty policy subsets plus reversed selection/default. They assert counts, candidate union, exclusions and one engine invocation. The mixed saved report contains nine checks, four passes, one SSH failure and four N/A. |
| TG-14 | Complete-batch mutation tests reject unconfigured/wrong-field/nested/numeric paths and wrong states/reasons. Valid configured-key paths survive rendering; corruption in a real three-policy batch yields zero trusted checks/findings. Old paths remain exact. |
| TG-15 | Pure observations/reprs, captured actual OPA input and both SDK channels exclude raw sensitive/unmarked required and unrequired values/names. Existing sentinel/log/validation/subprocess failure tests remain active. Shared masks stay internal. |
| TG-16 | Forbidden projection callbacks prove old-policy calls never parse TAG and TAG-only calls never build RDS/SSH values. Immutable key snapshots prevent later settings mutation. All historical report goldens pass with explicit selection. |
| TG-17 | Pure parser exact/over work tests and injected-graph tests include the actual 50,000-slot boundary and overflow with withheld maps. Indexed masks avoid per-key full-mask scans; existing worker/byte/depth/resource/admission/cancellation checks pass. |
| TG-18–TG-19 | Actual restricted OPA strict/format/test and runner/service tests pass. Existing network/runtime/schema-fetch/environment denial, timeouts, overflows, cleanup and atomic-failure tests remain active. Missing OPA cannot become a pass. |
| TG-20 | SDK memory/stdio × auto/legacy × default/custom startup settings verify listing, matching output channels, safe paths and argument errors. Analysis/listing regressions remain independent of OPA. The local socket fixture ran under host permissions. |
| TG-21 | Seven new synthetic fixtures/reports, independent illustrative HCL, startup forwarding and [the walkthrough](trying-tags.md) document exact commands, default/override behavior and limitations. No HCL execution or generated/live plan compatibility is claimed. |
| TG-22 | Both builds, archive inclusion and two fresh independent installed environments passed the checks below. |

## Distribution verification

Source and wheel builds succeeded. All **38 production Python/JSON/Rego files**
in the wheel matched the checkout byte-for-byte. Exactly RDS, SSH and TAG Rego
were included; no test policy, example/test assets or OPA binary entered the wheel.
The source archive included all **118 guidance/docs/tests/examples/lock files**
byte-for-byte at the packaging checkpoint.

Separate fresh wheel/source uv environments under `/private/tmp` ran isolated
Python outside the checkout with locked runtime dependencies. Each exercised
SDK auto/legacy modes and console/module entrypoints: three-tool discovery,
three-policy listing, the analysis golden, 15 saved evaluation reports, custom
CostCenter startup keys, matching text/structured content, forbidden tool-level
overrides and traversal denial. Imports came from each installed environment;
all installed production files matched the source.

Fresh environment setup initially needed network access to refill missing cache
entries for existing locked dependencies; no dependency/version was added or
changed. Source installation then succeeded offline. Tests and policy evaluation
themselves used local files/processes without AWS credentials or network access.

## Runtime boundaries

Engine input is schema **4**. Public reports, engine output and catalog envelopes
remain schema 1. Omission selects all three policies; older untagged fixtures can
intentionally fail TAG under the new default. Select old IDs explicitly for the
historical scope. Candidate resource counts use the selected-type union; check
counts include every resource/policy pair.

TAG paths may extend a catalog map prefix by one configured key only. Input
membership/state guards and fixed catalog prose prevent OPA from returning raw
plan keys or arbitrary explanations. Rego owns aggregation and selected-key
priority. One check identifies one winning problem, not every bad tag.

Known null/absent maps and null/blank/missing values fail the observed-plan rule.
Unknown/sensitive masks and unusable placeholders preserve uncertainty; malformed
nonstring values cannot pass. Provider ignore/default configuration and live AWS
tags are not reconstructed. Raw values, hashes and excerpts never enter OPA.

## Host observation and limitations

On 2026-10-22 this chat called the connected MCP `list_policies`; it returned
`POLICY_ASSETS_INVALID`. Its advertised schema still described the previous two
high-severity policies. Fresh SDK stdio requests successfully loaded three
policies and the new reports. The existing host process therefore needs to load
the new package; this is separate from server/packaging verification. No targeted
MCP restart control is exposed here, and no process or host configuration was
changed. A successful live new-version Codex smoke test is not claimed.

Earlier user-reported testing is preserved in prior acceptance records. Use the
four TAG host prompts after reloading and record actual calls before marking the
live-host check complete. Linux execution and live/generated Terraform-plan
compatibility remain unverified. Synthetic HCL/plans require no AWS credentials;
none was executed. Changes remain local; no GitHub push occurred.
