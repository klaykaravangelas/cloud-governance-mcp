# Specification 002: evaluate Terraform policies

Status: approved for implementation; E1–E5 implemented. See [acceptance evidence](../evaluation-acceptance.md).
Updated: 2026-10-19.

This specification defines tasks E1–E5 in the
[implementation plan](../implementation-plan.md). It refines FR-05, FR-07–FR-10
and the evaluation portions of SEC-01–SEC-07 in
[requirements](../requirements.md). [Specification 001](analyze-terraform-plan.md)
remains the contract for the completed analysis tool. The
[architecture](../architecture.md) supplies the component boundaries.

## Purpose and boundaries

Answer: **Does the desired infrastructure in this plan satisfy the selected
governance policy, and what could not be established?**

Add `evaluate_terraform_policies` beside `analyze_terraform_plan`. Start with one
bundled Rego policy: **AWS-RDS-001**, high severity, version `1.0.0`, requiring
explicit storage encryption on standalone AWS RDS instances. Use real OPA for
decisions; Python validates inputs, projects safe policy inputs, validates engine
results and builds reports. Neither MCP tool calls the other.

Only canonical `registry.terraform.io/hashicorp/aws` resources of type
`aws_db_instance` are supported by this first policy. Provider aliases still use
that provider source. Other provider sources, `aws_rds_cluster`,
`aws_rds_cluster_instance`, and other resource types are outside this increment.
Cluster association or uncertainty about standalone status must be reported
explicitly rather than treated as an encrypted standalone instance.

Do not add `list_policies` yet. An internal catalog is needed for evaluation;
exposing it as a third MCP tool belongs to L1. SSH, tags, S3, full RDS cluster
coverage, AWS connectivity, Terraform execution, mutation, custom policies,
HTTP transport, Docker and CI remain outside E1–E5.

The user authorized implementation on 2026-10-19. E1–E5 now provide the second
MCP tool. Specification drafting installed no dependencies; E1 subsequently
selected and checksum-verified the local OPA runtime. Listing remains L1.

## Tool input and discovery

Tool name: `evaluate_terraform_policies`.

Description: "Evaluate bundled governance policies against a local Terraform
plan JSON file in an allowed directory. Return policy findings, uncertainty and
coverage without resource attribute values. Requires configured OPA; does not
inspect or modify deployed infrastructure."

| Field | Type | Validation |
| --- | --- | --- |
| `plan_path` | strict string, required | Reuse Specification 001's 1–4096 character path contract and contained loader unchanged. |
| `policy_ids` | array of strict strings, optional | Omission selects all enabled catalog entries. If supplied, require a nonempty, duplicate-free list of exact enabled IDs. Reject null, unknown IDs and extra fields. Bound item count by enabled catalog size and IDs to 64 characters. |

Initially the only accepted selection is `["AWS-RDS-001"]`; omission selects the
same policy. Sort selection by ID for deterministic execution/reporting. Reject
invalid selection before reading a plan or starting OPA. Do not echo rejected
IDs, argument names or values in errors. No tool argument can select an
executable, query, policy file, capability file, timeout or shell command.

Example arguments:

```json
{"plan_path": "unencrypted_rds.json", "policy_ids": ["AWS-RDS-001"]}
```

At E5, discovery exposes exactly two tools, with strict Pydantic-derived input
and output schemas. Use the existing SDK's public low-level `Server` and explicit
handlers, read-only/non-destructive/idempotent/closed-world annotations, and
fixed safe errors. Do not change the analysis input/output schema. Host tool
approval is separate from operator-configured filesystem access.

## Shared parsing and policy projection

Reuse `RestrictedPlanLoader` and the existing adapter's format validation,
identity merge, opaque addresses, ordered actions and mask extraction. Loading,
normalization, projection, report construction and JSON size measurement run off
the event loop. OPA runs as an asynchronous subprocess.

Extend the internal normalized resource with an optional desired-state
projection; its default absence preserves analysis-only use. Keep projection
logic separate from action summarization. Analysis must neither retain new
attribute values unnecessarily nor initialize OPA/catalog resources. Evaluation
may request the projection while normalizing the same decoded plan, before the
adapter discards provider values. Do not read the file twice or normalize twice.

For matched resources, `resource_changes.change.after` is authoritative. Read
`planned_values.values` only for inventory-only resources. An existing change
with absent/null `after` must not fall back to inventory or `before` values.
Merge sensitivity masks from both sources conservatively as in Specification
001. Conflicting value copies do not override change-source precedence.

Project only the paths needed by this policy: `storage_encrypted` and
`cluster_identifier`. These are provider-specific fields; do not invent a
universal cloud encryption attribute. Preserve full existing typed mask metadata
internally, but send OPA only states for these fixed paths, identities and action
categories. No arbitrary provider dictionary, output, variable, configuration
expression, unrelated mask key, or `before` value reaches OPA.

The projection represents encryption with these states:

| State | Meaning / retained value |
| --- | --- |
| `known` | A strict JSON boolean; retain only this boolean. |
| `missing` | Required key absent; retain no value. |
| `null` | Explicit JSON null; retain no value. |
| `unknown` | An unknown mask covers the path; retain no value. |
| `sensitive` | A sensitivity mask covers the path; retain no value. |
| `unverified` | Unknown metadata is incomplete; retain no value. |
| `invalid_type` | Known value has another JSON type; retain no value. |
| `unavailable` | No usable desired object; retain no value. |

State precedence is sensitive, unknown, unverified, unavailable, then observed
missing/null/type/value. A mask on `[]` covers the whole object; a mask on
`["storage_encrypted"]` covers that attribute. Preserve integer list indices
in shared masks; unrelated paths do not cover this field. A mask below a scalar-required field also
blocks knowledge: contradictory nested mask shapes cannot establish a known
boolean or cluster string. Never coerce `0`, `1`, `"true"` or `"false"` to booleans.
Malformed mask/envelope structures remain
invalid-plan errors; a structurally valid provider attribute with an unexpected
type becomes an indeterminate check, without retaining the rejected value.

Derive standalone status with the same mask/metadata precedence. Known missing,
null or empty-string `cluster_identifier` means `standalone`; a known nonempty
string means `cluster_associated`. Other types mean `invalid_type`. Unknown,
sensitive, unverified or unavailable states cannot establish standalone status.
Never retain the cluster identifier string, compare resources using it, infer
associations from addresses, trim it, or query AWS. This field is an exclusion
guard, not cluster support.

Inventory-only resources have incomplete unknown metadata in the existing
adapter. They are observed and considered, but cannot pass even when their
inventory contains a literal encryption boolean. Missing `after_unknown` also
remains incomplete; do not manufacture a complete mask from its absence.

## Policy decisions and reason codes

OPA emits exactly one check for every selected-policy/resource pair, including
explicit `not_applicable` checks. For this increment, one resource means one
expected check. Empty input requires a defined report with an empty checks list.

Apply rules in this order:

| Condition | Outcome | Stable reason code |
| --- | --- | --- |
| Resource mode is `data` | `not_applicable` | `DATA_SOURCE_SKIPPED` |
| Managed action category is deletion only | `not_applicable` | `DELETED_RESOURCE_SKIPPED` |
| Provider source or resource type unsupported | `not_applicable` | `RESOURCE_NOT_SUPPORTED` |
| Standalone status is sensitive | `indeterminate` | `RDS_SCOPE_SENSITIVE` |
| Standalone status is unknown | `indeterminate` | `RDS_SCOPE_UNKNOWN` |
| Standalone status is unverified | `indeterminate` | `UNKNOWN_METADATA_INCOMPLETE` |
| Desired object unavailable | `indeterminate` | `DESIRED_STATE_UNAVAILABLE` |
| Standalone status has invalid type | `indeterminate` | `RDS_SCOPE_INVALID_TYPE` |
| Known cluster association | `indeterminate` | `RDS_CLUSTER_ASSOCIATION_UNSUPPORTED` |
| Standalone; encryption is sensitive | `indeterminate` | `RDS_ENCRYPTION_SENSITIVE` |
| Standalone; encryption is unknown | `indeterminate` | `RDS_ENCRYPTION_UNKNOWN` |
| Standalone; encryption metadata unverified | `indeterminate` | `UNKNOWN_METADATA_INCOMPLETE` |
| Standalone; encryption absent | `indeterminate` | `RDS_ENCRYPTION_MISSING` |
| Standalone; encryption null | `indeterminate` | `RDS_ENCRYPTION_NULL` |
| Standalone; encryption invalid type | `indeterminate` | `RDS_ENCRYPTION_INVALID_TYPE` |
| Standalone; encryption is strict `true` | `pass` | `RDS_ENCRYPTION_ENABLED` |
| Standalone; encryption is strict `false` | `fail` | `RDS_ENCRYPTION_DISABLED` |

Create, update, no-op and both replacement orders assess desired state once.
An admitted managed read action follows the same desired-state rules; do not
mistake it for a data source. Inventory-only/unreported resources remain
indeterminate, not inferred no-ops. Scope exclusions happen before reading
policy values; an unsupported resource's apparent encryption flag is irrelevant.

Supported standalone resources with missing/null/unknown/sensitive encryption
are applicable checks with uncertain outcomes, not exclusions. Cluster-associated
`aws_db_instance` resources likewise remain indeterminate so the limitation is
visible. Other RDS resource types are counted as unsupported.

Catalog metadata owns policy ID, version, title, description, severity, supported
provider/type, required paths, scope limitation and reason/message templates.
Only AWS-RDS-001 is enabled. Invalid or duplicate packaged metadata is an engine
configuration error. OPA returns enums/reason codes, not prose or remediation.
Python permits only the documented reason/outcome/path combinations and formats
messages from the catalog. Attribute paths are `[]` for exclusions,
`["cluster_identifier"]` for scope reasons, and `["storage_encrypted"]` for
encryption reasons; metadata/unavailable reasons use `[]`.

## OPA input and result boundaries

Use a versioned internal input containing `schema_version="1"`, sorted selected
policy IDs and sorted projected resource records. A projected record includes
address, provider source, type, mode, action category, standalone state and
encryption state. Only encryption state `known` can carry a boolean value; all
other states must forbid a value field. Full masks stay in the internal snapshot.

The fixed Rego entrypoint `data.cloud_governance.report` returns
`{"schema_version": "1", "checks": [...]}`. Each check contains exactly
`policy_id`, `resource_address`, `outcome`, `reason_code` and `attribute_path`.
Report/check fields are strict and reject additions. Use Rego v1 syntax.

Decode bounded strict UTF-8 JSON with duplicate-key, non-finite-number and depth
checks. Validate the OPA envelope, accepting exactly one result and one expression
whose value is the defined report object. Ignore only documented non-decision
envelope metadata; never surface expression text or diagnostics. Undefined,
null, scalar or multiple report values are errors even if OPA exits zero.

Validate the complete expected pair set, uniqueness, selected IDs, exact observed
resource addresses, allowed outcomes/reasons/paths, and exclusion-versus-candidate
membership. Missing or extra checks invalidate the entire batch. Python may
validate applicability but must not substitute its own encryption decision for
Rego. Sorting is a presentation operation; never silently deduplicate duplicate
engine checks or infer passes from an empty violations list.

The first engine call is atomic. On nonzero exit or invalid output, discard the
whole untrusted batch; do not preserve apparent findings from a corrupt response.
A valid empty plan still goes through OPA so engine availability and the defined
empty-result contract are verified.

## Runtime selection, configuration and limits

Analysis continues to work with no OPA executable configured or installed.
Specification drafting needs no dependency installation. E1 selects and documents
one exact OPA 1.x release, platform assets and published SHA-256 verification
steps; E2/E3 verify its actual flags/capabilities before claiming support.

At drafting, the official release page identifies **OPA v1.21.2**. It was the
candidate during drafting and is now the verified macOS arm64 pin. See
[OPA setup](../opa-setup.md) for artifact/checksum provenance. Use versioned
downloads rather than a moving `latest` URL; no OPA Python wrapper or automatic
runtime download is introduced.

Add optional operator-only `--opa-path`, an absolute executable path. Omission
does not trigger PATH lookup, downloads or startup failure. Capture/resolve the
trusted path once at startup when possible; missing files remain a safe
evaluation-time availability error. Invalid path syntax is a fixed startup
configuration error. Bound a lazy version probe before first evaluation, cache
successful verification for the process lifetime, and reject a runtime version
other than the tested pin. A probe failure must not disable analysis or close its
loader. The installed executable and packaged assets are operator-trusted;
capabilities restrict Rego features, not a malicious executable.

Reuse the existing four analysis/input limits and root settings. Add:

| Setting / startup option | Default | Enforcement |
| --- | --- | --- |
| `--max-opa-input-bytes` | 4,194,304 | Compact projected UTF-8 input, before spawning OPA. |
| `--max-opa-output-bytes` | 2,097,152 | Raw stdout bytes before decoding. |
| `--max-opa-stderr-bytes` | 65,536 | Captured diagnostics; overflow is an error, never returned/logged. |
| `--opa-eval-timeout-seconds` | 5 | OPA evaluation timeout. |
| `--opa-process-timeout-seconds` | 10 | Deadline covering spawn, stdin, both pipes and wait for each process, including the version probe. |
| `--max-evaluation-bytes` | 4,194,304 | Complete compact UTF-8 public report, including nulls and zero buckets. |

Use strict positive integer overrides; process timeout must exceed evaluation
timeout. Bound OPA result JSON depth at 128 before decoding. Input/output/error
report limits apply at exact byte boundaries with no truncation. Protocol
envelopes and duplicated MCP text/structured channels are outside report budgets.
If even an error report exceeds its budget, return a fixed tool error without
structured content.

Allow one active evaluation per server, including loading, version verification,
OPA and reporting, with no pending evaluation queue. A second evaluation returns
`SERVER_BUSY` before file work. Keep the existing independent one-analysis slot;
one analysis may run alongside one evaluation. At most one OPA child exists,
including version probes. This replaces the architecture's earlier proposed
four-request OPA queue: immediate rejection bounds retained plans and matches the
existing analysis admission model.

## Constrained OPA execution and cleanup

Use direct subprocess execution with an argument array, no shell. The intended
fixed evaluation command is:

```text
<trusted-opa> eval --format=json --stdin-input --strict --strict-builtin-errors
  --timeout=<validated-duration> --capabilities <packaged-capabilities>
  --data <packaged-rds.rego> --data <packaged-catalog>
  data.cloud_governance.report
```

Validate exact flags against the selected binary in E2/E3. Do not use
`--fail-defined`: a defined report containing violations is successful policy
execution. Explicitly validate undefined results regardless of exit status.
Queries and policy paths are application constants; durations come only from
validated operator settings. Stream projected input through stdin, never argv or
a temporary plan file. Close stdin after writing, including the empty-plan case.

Load catalog, capabilities and production Rego through `importlib.resources`;
keep resolved assets alive until the child is reaped. Do not load working-directory
policies, test Rego, arbitrary files beneath plan roots, remote bundles or remote
schemas. Package capabilities with a minimal allowlist of required deterministic
built-ins and `allow_net: []`; exclude network, runtime/environment introspection,
time, randomness and other unused features. E2 must demonstrate rejection of
`http.send`, `opa.runtime` and remote schema retrieval under that capabilities
file. Capabilities are a language restriction, not an OS sandbox.

Start the child with an explicit minimal environment, not an inherited
environment followed by removal of a few named secrets. In particular, no
credentials, proxy settings, `OPA_*` flag overrides or loader-injection variables
are inherited. Use an absolute executable and asset paths, an empty private temporary working
directory independent of the requested plan, and deterministic locale settings.
A broadly authorized root can include the temporary directory; fixed asset
paths and no working-directory policy discovery still determine exactly what
OPA loads.
Document any platform-required environment allowance in E3 and test it.

Write stdin and drain stdout/stderr concurrently with bounded reads. Broken
pipes, child exit, timeout and overflow cannot deadlock the parent. On failure or
cancellation, close stdin, terminate the child, allow a bounded one-second grace,
kill if necessary, reap it and join pipe tasks before releasing admission.
The cleanup grace is additional to the execution deadline. Shield cleanup against
AnyIO cancellation and repeated native task cancellation. If loading/projection
is still running in a worker, join it as the existing analysis service does.
Cancellation propagates after cleanup without a fabricated success/error report.

Never return or log raw OPA stdout/stderr, traces, commands, executable/asset/plan
paths, raw attributes or validation inputs. Unexpected errors log only a fixed
code and generated request ID. Root descriptors remain open until both services
have drained during shutdown. Imports remain quiet and perform no I/O.

## Public report and status semantics

`EvaluationReport` is strict, versioned, deterministic and contains no attribute
values or masks. Its fields are:

| Field | Contract |
| --- | --- |
| `schema_version` | Literal `"1"`, distinct from plan/protocol versions. |
| `format_version`, `terraform_version` | Same validated metadata and field names as analysis; Terraform version nullable. |
| `evaluation_status` | `complete`, `partial` or `failed`, as below. |
| `compliance_status` | `pass`, `fail`, `indeterminate` or `not_applicable`. |
| `selected_policy_ids` | Sorted enabled IDs actually selected. |
| `policy_scope` | Catalog-derived ID/version/severity, supported provider/type, and standalone-only limitation for each selection. |
| `findings` | One item per validated failed check. |
| `indeterminate_checks` | One item per validated indeterminate check. |
| `errors` | Safe structured engine errors; empty after a trustworthy batch. |
| `warnings` | Existing fixed snapshot coverage warnings in deterministic order. |
| `summary` | Nonnegative counts and invariant checks below. |

Finding/indeterminate items contain policy ID, severity, resource address/type,
reason code, safe attribute path, catalog-controlled explanation and remediation.
Each `policy_scope` item has exactly `policy_id`, `policy_version`, `severity`,
`supported_provider_names`, `supported_resource_types` and `scope_description`.
Provider/type lists and scope prose come only from the catalog. Initially these
lists contain the canonical AWS source and `aws_db_instance`, and the description
states that only standalone instances are checked and cluster associations are
not resolved. All counts are strict integers, excluding booleans.
No arbitrary evidence field is allowed. For example, a failure explains
"RDS storage encryption is explicitly disabled." and advises
"Configure storage encryption for the intended RDS resource." It never echoes
the provider value or proposes executing remediation. Addresses are intentionally
returned, including operator-chosen instance keys; they are excluded from logs.

Summary fields are `resources_observed`, `candidate_resources`, `skipped_data`,
`skipped_deleted`, `unsupported_resources`, `expected_checks`, `evaluated_checks`,
`unevaluated_checks`, `applicable_checks`, `passed`, `failed`, `indeterminate`
and `not_applicable`. Classification order is data, managed deletion, unsupported
provider/type, then candidate. These resource buckets are disjoint and sum to
`resources_observed`. Cluster-associated/unverified RDS instances are candidates.

`expected_checks = resources_observed * number_of_selected_policies`.
`evaluated_checks = passed + failed + indeterminate + not_applicable` and
`applicable_checks = passed + failed + indeterminate`.
`expected_checks = evaluated_checks + unevaluated_checks`. A valid batch has
zero unevaluated checks; a failed atomic batch has zero evaluated checks and all
expected checks unevaluated. `failed == len(findings)` and
`indeterminate == len(indeterminate_checks)`. Do not claim passes or exclusions
from an invalid batch. Resource classification counts remain available if the
plan was successfully normalized before engine failure.

Evaluation status:

- `complete`: the entire expected batch validated and no snapshot warnings exist.
  Unknown/sensitive checks alone can coexist with complete execution.
- `partial`: the batch validated, but snapshot warnings limit plan coverage.
  Conservatively retain all existing warning types in this increment, even those
  about outputs or drift; narrowing warnings requires explicit later tests/design.
- `failed`: OPA/configuration/output failed; no check from that batch is trusted.

Compliance precedence:

1. At least one validated failure: `fail`, including a partial-coverage plan.
2. Engine errors, indeterminate checks or snapshot warnings: `indeterminate`.
3. At least one applicable check and all applicable checks passed: `pass`.
4. Otherwise: `not_applicable`.

A complete empty, deleted-only, data-only or unsupported-only plan therefore
returns `not_applicable`, never `pass`. If such a plan has coverage warnings it
returns `indeterminate`. Unsupported counts do not negate a pass on supported
resources, but `policy_scope` and coverage counts must make that limited claim
visible. A pass is not a certification of every resource or a deployed account.

Sort findings/checks by policy ID, exact resource address and typed attribute
path; codes break any remaining ties. One outcome per pair means no duplicate
finding keys. Use catalog order for safe errors and warning-code order for
warnings. Do not include timestamps, durations, random IDs or paths in reports;
unchanged bytes/settings/policy versions yield identical reports.

## Error contracts and MCP mapping

Reuse fixed loading/plan errors without exposing raw Pydantic errors. Add fixed
evaluation errors with these meanings; `evaluation_errors.py` supplies immutable messages:

| Code | Meaning |
| --- | --- |
| `INVALID_POLICY_SELECTION` | Empty, duplicate, unknown or invalid policy selection. |
| `OPA_NOT_CONFIGURED` | Operator supplied no OPA executable path. |
| `OPA_NOT_FOUND` | Configured executable unavailable or not executable. |
| `OPA_VERSION_UNSUPPORTED` | Bounded version probe cannot establish the exact supported runtime. |
| `POLICY_ASSETS_INVALID` | Missing or invalid packaged catalog/Rego/capability assets. |
| `OPA_INPUT_LIMIT_EXCEEDED` | Projected input exceeds its byte limit. |
| `OPA_TIMEOUT` | Version/evaluation process exceeds its execution budget. |
| `OPA_OUTPUT_LIMIT_EXCEEDED` | Either captured output stream exceeds its byte limit. |
| `OPA_EXECUTION_ERROR` | Spawn/pipe failure or nonzero evaluation exit, including compiler/builtin failure. |
| `OPA_OUTPUT_INVALID` | Undefined, malformed, incomplete, duplicate or inconsistent check output. |
| `EVALUATION_LIMIT_EXCEEDED` | Complete public report exceeds its byte budget. |

Use existing `SERVER_BUSY` and a safe internal failure code as appropriate.
Exceptions and error objects store catalog codes, not raw underlying exceptions.
An `EvaluationError` has code, fixed message and nullable selected policy ID;
whole-engine failures use null. Do not guess a policy ID from subprocess text.

| Situation | MCP result |
| --- | --- |
| Valid report, including violations, uncertainty or no applicable checks | `isError=false`; text and structured content encode the same public report. |
| Argument, selection, file/plan, admission or pre-report failure | `isError=true`; fixed text, no structured report. |
| Engine failure after normalization provides a bounded safe report | `isError=true`; matching text/structured failed report with `errors`, no trusted findings/checks. |
| Cancellation | Propagate only after cleanup; no invented report. |
| Unknown tool / malformed protocol envelope | Existing safe protocol behavior. |

Evaluation errors after normalization use the structured form even for missing
OPA or Rego/capability assets; validate/normalize first to establish trusted report
metadata. A malformed catalog is a pre-report error: without trusted policy
metadata no safe policy scope can be constructed, so return fixed text only.
Do not invoke the engine for invalid plans. Report serialization/limit failures
fall back to fixed errors, never truncated JSON. Verify explicit error-report
results against SDK 2.3.0 in both modern auto and legacy modes. Python fields use
`is_error`/`structured_content`; wire aliases remain SDK-managed. Analysis must
not require OPA while evaluation is registered but unconfigured. Future listing
must remain independent as well.

## Components and interfaces

| Component | Planned responsibility |
| --- | --- |
| Evaluation models/settings/errors | Strict input, projection, catalog, engine checks/report, public report, budgets and safe error entrypoints; no MCP imports. |
| Adapter/projection | Optional evaluation projection during the existing normalization pass, before discarding values; shared analysis identities/masks unchanged. |
| Catalog/assets | Load one validated packaged source of metadata/templates; production Rego/capabilities beside it, test policies outside runtime assets. |
| `OpaEngine.evaluate(input)` | Async constrained version check/execution, bounded parsing and complete batch validation; injected runtime configuration. |
| `EvaluationService.evaluate(plan_path, policy_ids=None)` | Validate selection/admission, load/project off-loop, call injected engine, build/size safe report, clean up cancellation. |
| Report builder | Pure mapping from trusted snapshot/catalog/validated checks or safe engine error to report/status/counts. |
| MCP/CLI | Inject both services into the existing server, dispatch exactly two tools, add operator-only OPA options, drain both before root closure. |

Use small modules and ordinary constructor/function injection. New evaluation
models may live in `evaluation_models.py` rather than growing the analysis model
module. Extend configuration/errors only where shared behavior warrants it. Avoid
a generic plugin framework or refactoring the proven analysis concurrency code
without a concrete need. Add docstrings/comments while implementing each task.

## Examples and fixtures

The existing `encrypted_rds.json` and `unencrypted_rds.json` fixtures are
hand-authored synthetic plans with complete masks; use them for initial pass/fail
cases. They are not output from the illustrative HCL. Add small focused fixtures
for missing/null/incorrect-type values, uncertainty, scope and coverage cases.
Use fake identifiers and sentinel secrets; never require Terraform or credentials.

For the existing unencrypted fixture, expected public essentials are:

```json
{
  "evaluation_status": "complete",
  "compliance_status": "fail",
  "selected_policy_ids": ["AWS-RDS-001"],
  "findings": [{
    "policy_id": "AWS-RDS-001",
    "severity": "high",
    "resource_address": "aws_db_instance.example",
    "resource_type": "aws_db_instance",
    "reason_code": "RDS_ENCRYPTION_DISABLED",
    "attribute_path": ["storage_encrypted"],
    "explanation": "RDS storage encryption is explicitly disabled.",
    "remediation": "Configure storage encryption for the intended RDS resource."
  }],
  "indeterminate_checks": [],
  "errors": []
}
```

This is a partial illustration, not a complete response or executed output.
The real report must also include schema/source metadata, policy scope, warnings
and all summary fields. With the encrypted fixture, expect complete/pass, one
passed applicable check and no findings. With unknown encryption, expect
complete/indeterminate and one indeterminate check, provided coverage is complete.
With a missing OPA binary and a valid plan, expect failed/indeterminate, one safe
engine error and `isError=true`, not an unencrypted-resource finding.

At E5 extend the standalone example client with an explicit evaluation action,
operator OPA path and optional selection; its default analysis walkthrough stays
usable without OPA. Save full actual reports only after they are generated and
verified. Document host configuration and commands using the established
`uv run --locked --no-editable` workflow.

## Tasks and acceptance cases

| Task | Deliverable / completion checkpoint |
| --- | --- |
| E1 | Strict models, exact messages/catalog, pure projection states and optional adapter integration, runtime pin/install/checksum documentation, package-data rules. Contract/projection tests pass without invoking OPA; existing analysis remains unchanged. |
| E2 | One Rego v1 policy, fixed report entrypoint, minimal capabilities and separate test modules. Real strict compile, format and Rego tests cover the decision table and reject prohibited capabilities. |
| E3 | Async OPA runner, version verification, minimal environment, bounded input/output/deadlines and cancellation cleanup. Real OPA integration plus targeted failure-process tests pass. |
| E4 | Evaluation service/reporting, complete pair validation, admission, coverage/status/counts and safe error reports. Pure/core integration and cancellation tests pass; analysis remains independent. |
| E5 | Second MCP tool and CLI options, modern/legacy client tests, real stdio, examples, complete reports, acceptance evidence and installed-wheel asset verification. Exactly two tools; no listing or other policies. |

| ID | Scenario | Required evidence |
| --- | --- | --- |
| EV-01 | Contracts/selection | Omitted/explicit selection equivalent; reject null/empty/duplicates/unknown/coerced values/extra fields safely before file/engine work. Catalog metadata/reasons are strict. |
| EV-02 | Known encryption | Existing complete synthetic true/false fixtures produce pass/fail respectively in real Rego, runner, service and MCP. |
| EV-03 | Missing/null/type | Separate indeterminate codes for missing, null and invalid type; strings/numbers/arrays/objects never coerce or leak. |
| EV-04 | Masks/precedence | Attribute/root masks, unrelated and list-index paths, sensitive+unknown overlap, missing mask metadata and incomplete inventory stay conservative; sensitive values absent before OPA. |
| EV-05 | Standalone scope | Missing/null/empty-string known cluster guard permits standalone checks; nonempty, unknown, sensitive, invalid and unverified guard states remain indeterminate without retaining identifiers. |
| EV-06 | Identity/provider | Root/nested/indexed opaque addresses preserved; wrong provider and cluster/other resource types not applicable with unsupported counts. |
| EV-07 | Actions/sources | Create/update/no-op/managed read and both replacements evaluate desired state once; data/deletions skipped first; authoritative after, missing after, merged masks and inventory-only uncertainty tested. |
| EV-08 | No applicable scope | Complete empty/data-only/deleted-only/unsupported-only plans give not applicable, never pass; OPA returns the full expected set or defined empty set. |
| EV-09 | Partial coverage | Every existing warning blocks overall pass; validated failure still wins. Complete execution with uncertain values differs from partial input coverage. |
| EV-10 | Pair/result integrity | Missing/extra/duplicate pair, unknown ID/address, forbidden fields, invalid reason/outcome/path, wrong schema and exclusion mismatch discard the whole batch. |
| EV-11 | Undefined/corrupt output | Undefined/empty envelope, null/scalar/multiple expression, invalid UTF-8/JSON/depth, duplicate keys and non-finite numbers are errors even on zero exit. |
| EV-12 | Runtime availability | Unconfigured/missing/nonexecutable/wrong-version OPA safe; bounded probe; analysis still serves and imports remain quiet. Real runtime matches documented pin. |
| EV-13 | Process failures | Real test-only bad Rego/query and runtime/builtin failure; fake processes for spawn/pipe failures; nonzero exits never create passes. Test policies excluded from wheel. |
| EV-14 | Input/output limits | Exact and over UTF-8 input/stdout/stderr/report boundaries, including error reports; no truncation, deadlock or raw output. |
| EV-15 | Timeout/cancellation | Stalled writes, either pipe and process wait; TERM-resistant test child requires kill/reap; repeated native/AnyIO cancellation joins workers/child/tasks then frees admission. |
| EV-16 | Admission/shutdown | Second evaluation rejected with no file/child work; analysis can run concurrently; at most one OPA child; later request succeeds after failure/cancellation; shutdown drains before closing roots. |
| EV-17 | Capabilities/environment | Prohibited built-ins and remote schemas rejected; inherited OPA overrides/credentials/proxies/injection variables absent; no plan-controlled executable/query/path/flag. |
| EV-18 | File regression | Existing traversal/symlink/special-file/race/size/depth protections apply to evaluation; no second read or insecure loader. |
| EV-19 | Confidentiality | Marked/unmarked sentinels, cluster IDs, outputs, variables, rejected field names and subprocess diagnostics absent from OPA input where excluded, both public channels and logs. Required resource identities deliberately remain public. |
| EV-20 | Reporting invariants | Count partitions, expected/evaluated/unevaluated relations, findings lengths, status precedence and stable ordering hold for valid/failed reports and resource permutations. |
| EV-21 | SDK contract | Exactly two tools; strict schemas, annotations, matching text/structured reports, violations are successful calls, errors use fixed/structured forms as specified, in auto and legacy modes. |
| EV-22 | Real stdio/package | Outside checkout, installed wheel includes only production assets, resolves without working-directory assumptions, evaluates real OPA and closes cleanly. Source distribution includes test/example/docs assets. |
| EV-23 | Analysis regression | All existing analysis acceptance cases and default walkthrough work without OPA. Evaluation attributes/masks never enter `PlanAnalysis`; analysis never probes OPA. |
| EV-24 | Documentation/verification | Runtime pin/checksum provenance, exact checks, full reports, setup/limitations and EV evidence agree with executed behavior. No unimplemented tools/policies advertised. |

Record tests against EV IDs as each task lands. Rego tests and real OPA runner
tests are required; mocks cannot replace successful real policy execution. Missing
OPA must fail full evaluation/release verification clearly, not skip it. Keep a
documented analysis-only test command runnable without OPA. Execute required Unix
socket loader tests with authorized host permissions if the local sandbox blocks
fixture creation; do not omit them.

## Completion and verification

E1–E5 are complete only when EV-01–EV-24 have recorded evidence, existing analysis
acceptance remains valid, Python/Ruff checks pass, production Rego passes strict
compile/format/tests, real runner/SDK/stdio tests pass and installed assets work
outside the checkout. Full v0.1 remains incomplete until L1 and the remaining
policy increments land.

Use the existing locked, non-editable uv commands. E2 will document exact
`opa check --strict`, `opa fmt --fail` and `opa test` asset paths/flags for the
pinned runtime/capabilities once those files exist. Add package asset paths to
uv cache keys so non-editable installs rebuild when catalog/Rego/capabilities
change. Check wheel production assets and source-distribution test/documentation
contents separately. Do not claim these planned checks ran while drafting.

Documentation-only review requires local link/example/invariant consistency and
`git diff --check`, not installing OPA or running nonexistent evaluation tests.

## Official references and decision provenance

Consulted 2026-10-19. Runtime limits, classification precedence, atomic batch
validation, catalog IDs and conservative coverage rules are project decisions.
The following sources establish upstream interfaces/semantics, not proof that
this proposed implementation has passed tests:

- [OPA CLI reference](https://www.openpolicyagent.org/docs/cli): eval flags,
  environment flag overrides and capabilities; in particular strict builtin
  errors, stdin input and disabled remote schema hosts.
- [OPA policy language](https://www.openpolicyagent.org/docs/policy-language)
  and [policy testing](https://www.openpolicyagent.org/docs/policy-testing):
  defined/undefined results, Rego rules and executable policy tests.
- [OPA v1.21.2 release](https://github.com/open-policy-agent/opa/releases/tag/v1.21.2):
  runtime source; macOS arm64 artifact/checksum verification is recorded in OPA setup.
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format):
  desired values, omitted unknowns, ordered changes and separate sensitivity masks.
- [MCP Python SDK 2.3.0 low-level server](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/advanced/low-level-server.md)
  and [migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/migration.md):
  public constructor handlers and explicit result objects matching the lockfile.
- [SDK structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/):
  typed public results and text/structured response channels; verify error results
  explicitly with the pinned SDK rather than assuming decorator behavior.
