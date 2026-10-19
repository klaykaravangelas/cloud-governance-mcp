# Implementation plan

Status: Specifications 001 and 002 implemented; A1–A7 and E1–E5 complete.
L1 (policy listing) is the next increment. Updated: 2026-10-19.

Build in this order: `analyze_terraform_plan`, `evaluate_terraform_policies`,
`list_policies`, then expanded policy coverage. Each task has a narrow result and
explicit verification. Dependencies establish a clear progression while allowing
each task to be verified on its own. Do not build the entire MVP at once.

## Completed planning work

- Inspected the repository and ancestor guidance.
- Wrote requirements/acceptance criteria, architecture, roadmap, and `AGENTS.md`.
- Consulted official MCP SDK, OPA, and Terraform JSON documentation.
- Revised the first slice to expose analysis through the shared loader/parser.
- User reviewed and approved [Specification 001](specifications/analyze-terraform-plan.md)
  with explicit contracts and acceptance cases AN-01–AN-15.
- Completed A1: Python 3.14.7 package/environment, locked dependencies, pytest/Ruff
  setup, source/wheel builds, quiet import smoke test and independent wheel install.
  See [verified versions and commands](development.md).
- Completed A2: strict inputs/settings, action/identity/mask/snapshot/report
  contracts, safe error/warning catalogs, and 131 passing tests including package
  and transport-independence checks.
- Completed A3: pinned roots, descriptor-relative no-follow reads, file-kind
  checks, byte/depth limits, strict JSON, safe errors, and descriptor cleanup.
  At A3, the suite had 191 passing tests, including 60 loader cases.
- Completed A4: Terraform envelope validation, exact-address inventory merge,
  recursive module identities, ordered actions, typed masks and coverage warnings.
  Added synthetic JSON fixtures and illustrative HCL. At A4, 369 tests passed,
  including 178 new mask/adapter/pipeline cases.
- Completed A5: deterministic public summaries and an async analysis service with
  output byte limits, nonblocking admission, safe error mapping, and cancellation
  cleanup. At A5, 427 tests passed, including 58 new summary/service cases. The service
  declares the existing AnyIO dependency directly for cancellation shielding.
- Completed A6: public SDK `Server` handlers, strict schemas and safe tool errors,
  one analysis tool, required roots/limit CLI options, console/module entrypoints,
  and real stdio serving. At A6, 511 tests passed, including 84 new MCP/CLI/stdio cases.
  Both modern auto mode and legacy initialization are exercised, with matching
  text/structured output and cancellation reaching real file cleanup.
- Completed A7: hands-on guide, standalone SDK example client, saved real report,
  AN-01–AN-15 evidence, updated README/boundaries, and source-distribution docs/lock
  assets. All 521 tests pass, including 10 new walkthrough cases. Full Ruff,
  lock/environment/dependency, source/wheel and independent installed-stdio checks
  pass. No runtime functionality or policy scope was added.

## Analysis specification

The [analysis specification](specifications/analyze-terraform-plan.md) is approved.
It defines:

- Bounded path input, configured roots, and supported Terraform plan envelopes.
- Typed resource identity/action output, deterministic ordering, action/type
  counts, inventory merge/deduplication, and coverage warnings.
- Root/nested/indexed resources, both replacement orderings, deletion, no-op,
  data-source reads, empty plans, and partial/deferred input behavior.
- Unknown/sensitive masking, safe errors, file and resource limits, and secret
  non-disclosure in logs and both MCP output channels.
- Synthetic fixture scenarios, unit/integration acceptance cases, and exact
  completion criteria for the tasks below.

Keep that specification focused on analysis. OPA, compliance decisions, and policy
listing belong to subsequent increments. Bootstrap, contracts, contained loading,
Terraform normalization, the analysis service/summaries and MCP stdio are
implemented and verified. [The walkthrough](trying-analysis.md) is ready for the
user to try; [acceptance evidence](analysis-acceptance.md) records all 15 cases.
The user approved and authorized implementing the next specification;
[Specification 002](specifications/evaluate-terraform-policies.md) now defines
evaluation contracts, the standalone RDS policy, OPA boundaries and EV-01–EV-24.
E1–E5 now implement it; [evaluation acceptance](evaluation-acceptance.md) records
verification. L1 is the next increment.
Dependency installation occurred in A1; specification drafting requires no
dependency installation.
Task completion checks below are technical checkpoints, not additional user
approval gates.

## Increment 1: analyze Terraform plans

| Task | Depends on | Deliverable | Verification / done when |
| --- | --- | --- | --- |
| A1: Bootstrap package (complete) | Approved analysis specification; bootstrap authorized | `pyproject.toml`, `.python-version` (3.14.7), `uv.lock`, `src/` package, pytest/Ruff configuration, official MCP 2.3.0 and Pydantic 2.14.1 verified. | Completed: one quiet import smoke test, Ruff lint/format, lock/environment/dependency checks, source/wheel builds, independent wheel installation outside the repository. No OPA dependency/check or policy assets introduced. |
| A2: Define analysis contracts (complete) | A1 | `config.py`, `models.py`, and `errors.py`: strict root/input settings, ordered actions, identity/mask/snapshot models, `PlanAnalysis` response, fixed errors/warnings. | Completed: 131 tests pass, including strict types, identity/order preservation, uncertainty, summary/status invariants, safe boundary failures, JSON/schema round trips, and imports without MCP. Ruff checks pass. Filesystem, parser, and MCP behavior remain later tasks. |
| A3: Implement contained loader (complete) | A2 | `files.py`: context-managed startup roots, descriptor-relative no-follow file opens, byte/depth bounds, strict JSON, safe failures, and cleanup. | Completed: 191 total tests pass, including 60 loader cases for containment, symlinks, component-swap/FIFO races, special files, malformed/oversized/deep JSON, invalid roots/platforms, short/growing reads, and interrupted/error cleanup. Verified on macOS; Linux still needs execution there. |
| A4: Parse and normalize Terraform plans (complete) | A2, A3 | `adapters/terraform.py` and `normalization.py`: format/envelope validation, generic identities/actions, recursive inventory merge, typed unknown/sensitive masks, fixed coverage warnings, synthetic fixtures and illustrative HCL. | Completed: 369 total tests pass, including 178 new mask/adapter/real-loader pipeline cases. Covers source conflicts/duplicates, both replacement orders, nested/indexed resources, partial coverage, strict structures, limits and secret omission. Ruff and distribution checks pass; core imports remain independent of MCP. |
| A5: Build analysis service and summaries (complete) | A4 | `analysis.py` builds deterministic public summaries; `service.py` coordinates validated inputs, threaded loading/normalization/counting, output limits, single active admission, cancellation cleanup and safe errors. | Completed: 427 total tests pass, including 58 new summary/service cases for exact mixed counts, both replacement orders, empty/partial coverage, no secret/mask disclosure, UTF-8 budget boundaries, no queue, event-loop responsiveness, failure recovery, and native/AnyIO cancellation with real descriptor cleanup. Ruff and distribution checks pass. |
| A6: Expose analysis over MCP (complete) | A5 | `server.py`: public SDK low-level `Server`, exact core schemas, explicit input/result validation, one tool, read-only hints and safe failures. `__main__.py`/console script: required roots, limits and stdio lifecycle. | Completed: 511 total tests pass, including 84 new SDK/CLI/stdio cases. Both auto/legacy discovery and output contracts pass; malformed inputs and pre-handler errors omit secrets. Real subprocesses work outside the checkout, recover from errors and shut down cleanly; SDK cancellation drains real file cleanup. Ruff and installed-wheel checks pass. |
| A7: Verify and document analysis (complete) | A6 | `docs/trying-analysis.md`, `examples/client.py`, saved public report, README, AN-01–AN-15 evidence, source docs/lock inclusion and independent wheel verification. | Completed: 521 tests pass (10 new walkthrough cases), Ruff/lock/environment/dependency checks and source/wheel builds pass. Fresh installed SDK stdio works outside the checkout; walkthrough commands/outputs are tested. Verified on macOS arm64; Linux and live/generated plan campaigns remain unverified. |

Completed checkpoint: a client can ask what a plan changes and receive a tested,
safe summary. Only `analyze_terraform_plan` is registered. No policy assets,
evaluator, catalog, policy-listing tool, or compliance reports exist yet.

## Increment 2: evaluate one policy

Follow the implemented [Specification 002](specifications/evaluate-terraform-policies.md).
Its decisions refine the earlier architecture proposals:
one active evaluation with no queue, explicit policy projection states, complete
policy/resource-pair validation and atomic engine failures. Install/pin OPA during
implementation, not specification drafting. Analysis and evaluation are exposed;
listing and expanded coverage remain subsequent increments.

| Task | Depends on | Deliverable | Verification / done when |
| --- | --- | --- | --- |
| E1 (complete): Define evaluation contracts and catalog | A7 | Check outcomes, settings/limits, policy metadata, findings, error/report models, RDS catalog entry, and optional policy projection during shared normalization. Select/document the exact supported OPA 1.x runtime and installation/checksum instructions; OPA 1.21.2 is verified on macOS arm64; see [setup](opa-setup.md). Add policy package-data/cache rules. | Tests validate strict encryption booleans, mask/scope/source precedence, explicit outcomes, selection, count/status contracts and safe reason codes (EV-01, EV-03–EV-07 and relevant EV-20/EV-23 cases). Analysis remains unchanged and runs without OPA. |
| E2 (complete): Implement one Rego policy | E1 | Rego v1 AWS-RDS-001 for standalone `aws_db_instance`, defined report entrypoint with explicit outcomes, and restricted capabilities aligned with the pinned OPA. | `opa check --strict`, formatting checks, and `opa test` pass for true, false, missing, unknown, sensitive, non-applicable, deleted, and nested-address cases. Capabilities reject network/runtime built-ins. |
| E3 (complete): Implement OPA runner | E2 | Async direct invocation, fixed arguments/query, stdin input, minimal environment, bounded pipes/timeouts/concurrency, and validated output. | Real OPA tests return expected checks. Failure tests cover missing/incompatible binary, compilation/runtime errors, undefined query, malformed/missing check output, deadline, output overflow, and cancellation cleanup. No shell or plan values in argv/logs. |
| E4 (complete): Add evaluation service/reporting | E3 | Wire E1's optional adapter projection into a separate evaluation service; validate all expected pairs and render catalog-controlled findings/coverage. Use one active evaluation, no queue, independently of analysis admission. | Tests distinguish violations from engine errors and unknown inputs. Empty, unsupported, or deleted-only scopes cannot pass. Report ordering is stable; sensitive sentinels are absent from reports and logs. Analysis never calls OPA. |
| E5 (complete): Expose and verify evaluation | E4 | Add `evaluate_terraform_policies` alongside analysis, validate policy selection, and return structured findings/errors. Update setup/sample reports and wheel asset checks. | SDK tests discover exactly two tools. Real OPA and stdio evaluation tests pass, including safe failures; analysis still works when OPA is absent. Full evaluation verification fails clearly when OPA is unavailable. |

Completion checkpoint: clients can separately inspect changes and evaluate one
governance rule against the same parsing foundation. Analysis describes changes;
evaluation adds compliance decisions. Neither MCP tool calls the other.

## Increment 3: list implemented policies

| Task | Depends on | Deliverable | Verification / done when |
| --- | --- | --- | --- |
| L1: Expose and verify catalog | E5 | Add `list_policies` from the catalog already used by evaluation; update three-tool docs/examples. | SDK/stdio tests discover all three tools. Listing returns only AWS-RDS-001 with matching description/severity/supported types and selection metadata. It invokes no OPA process and works when OPA is unavailable. Planned policy entries are not advertised. |

## Subsequent v0.1 policy increments

| Task | Depends on | Deliverable | Verification / done when |
| --- | --- | --- | --- |
| M1: Complete RDS family | L1 | `aws_rds_cluster` and conservative instance/cluster association handling. | Known cluster encryption, inheritance, unresolved associations, false/unknown/sensitive cases are tested in OPA and Python integration. |
| M2: Add SSH ingress policy | L1 | AWS-SG-001 for inline and standalone rule representations. | TCP port 22/ranges, all-protocol rules, and IPv4/IPv6 world CIDRs fail; private/self/egress/other-port controls pass or are non-applicable. Unknown/sensitive cases remain explicit. |
| M3: Add mandatory tags policy | L1 | AWS-TAG-001, trusted startup tag-key configuration, and explicit supported taggable types. | Missing/empty keys, case sensitivity, inherited `tags_all`, unsupported/non-taggable types, unknown and sensitive values have tested outcomes. |
| M4: Add S3 public access policy | L1 | AWS-S3-001 block flags and conservative bucket/block linkage. | All true, individual false flags, missing block, known/computed links, nested modules, unknown/sensitive flags, and absent account context have explicit tested coverage. |
| M5: Verify complete v0.1 | M1–M4 | Representative mixed examples, updated docs, three-tool stdio walkthrough, and acceptance traceability against requirement IDs. | Full local verification passes without credentials/network; wheel includes production policies and no test-only Rego. Documented gaps cannot silently pass. No Docker, AWS adapter, or CI workflow is added. |

## Verification approach

For increment 1, record and run `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, and installed-package/stdio checks. OPA is neither
installed nor invoked by this increment's verification.

When increment 2 introduces policies, add `opa check --strict`, an OPA formatting
check, and `opa test` against production/test Rego with the same supported
capabilities. Finalize and exercise exact asset paths/flags when files exist.
Keep analysis-only checks runnable without OPA, while requiring real OPA for full
evaluation and release verification.

These are planned checks, not commands claimed to have run in a documentation-only
change. Do not replace real OPA tests with mocks, skip implemented integration
tests by default, generate plans against live AWS, or add tests that duplicate
implementation details. Record actual validation evidence per increment.
