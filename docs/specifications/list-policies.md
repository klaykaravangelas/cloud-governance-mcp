# Specification 003: list governance policies

Status: approved for implementation; L1a–L1d implemented. See
[acceptance evidence](../listing-acceptance.md).
Updated: 2026-10-19.

This specification defines L1 in the [implementation plan](../implementation-plan.md)
and refines FR-06 plus the discovery, validation, confidentiality and resource-limit
requirements in [requirements](../requirements.md). Specifications
[001](analyze-terraform-plan.md) and [002](evaluate-terraform-policies.md) remain
the contracts for the two implemented tools.

## Purpose and boundaries

Answer: **Which governance policies can I select, what do they check, and what
configuration do they require?**

Add `list_policies` as the third MCP tool. Read the same packaged catalog used
for evaluation and return a deliberately selected public metadata projection.
Initially return exactly **AWS-RDS-001**, version `1.0.0`, high severity, covering
standalone `aws_db_instance` storage encryption.

MCP `tools/list` discovers functions such as `analyze_terraform_plan`.
Calling our `list_policies` function discovers governance rules such as
`AWS-RDS-001`. Its returned `policy_id` can be supplied in
`evaluate_terraform_policies.policy_ids`.

Listing reads no plan, invokes no OPA executable or version probe, and makes no
compliance or runtime-health claim. A listed policy is bundled and implemented;
evaluation still requires a configured, supported OPA executable. Listing must
work when OPA is unconfigured, missing, or incompatible.

Do not add policy filters, pagination, uploaded policies, new governance rules,
RDS cluster support, AWS connectivity, Terraform execution, new transports or
dependencies. Server startup still requires an explicit valid `--allowed-root`;
listing grants no additional filesystem access.

## Tool input and discovery

Tool name: `list_policies`.

Description: "List the bundled governance policies available for Terraform plan
evaluation, including their versions, severity, supported resources, scope and
required configuration. Does not read plans or invoke OPA."

The input is an empty object. Publish a strict Pydantic-derived JSON Schema with
`type: object`, `properties: {}` and `additionalProperties: false`.
Accept `{}` and the SDK's no-arguments representation (`None` for an omitted or
null MCP `arguments` member), normalizing the latter to `{}` before validating
the strict core input. Reject extra keys, arrays and scalar inputs without
echoing their names or values. Protocol-level malformed requests may be rejected
by the SDK before the handler; use the existing protocol error boundary.

Use the pinned official MCP Python SDK 2.3.0 public low-level `Server` API and
explicit handlers, as in A6/E5. Declare read-only, non-destructive, idempotent and
closed-world annotations. The runnable server advertises exactly three tools;
existing analysis-only service injection remains supported for isolated tests.

## Public response

Return a strict `PolicyList` object. Both MCP output channels must represent the
same validated object: JSON in one text block and the matching structured content.
Successful calls have `is_error=false`.

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | literal `"1"` | Version of the public listing contract, independent of policy versions. |
| `policies` | array of `ListedPolicy` | Enabled, implemented policies ordered by exact `policy_id`. No duplicates. |

Each `ListedPolicy` contains exactly:

| Field | Type | Meaning |
| --- | --- | --- |
| `policy_id` | strict bounded string | Exact selectable catalog ID; initially `AWS-RDS-001`. |
| `policy_version` | strict bounded string | Catalog policy version; initially `1.0.0`. |
| `title` | existing `IdentityText` | Policy name from the catalog; avoid a second `name` alias. |
| `description` | existing `IdentityText` | What the rule checks. |
| `severity` | current catalog severity | Initially `high`; do not broaden implemented coverage. |
| `supported_provider_names` | array of `IdentityText` | Canonical provider sources supported by the rule. |
| `supported_resource_types` | array of `IdentityText` | Supported Terraform resource types. |
| `required_paths` | array of existing typed `AttributePath` | Desired-state fields the rule needs, including scope checks. These are field names, never observed values. |
| `scope_description` | existing `IdentityText` | Supported scope and limitations in plain language. |
| `required_configuration` | array of `IdentityText` | Names of policy-specific operator settings needed to use the rule; empty for AWS-RDS-001. Never include configured values. |

Reuse current catalog ID/version validation. Preserve catalog order inside
metadata arrays; sort the policy collection by ID. Do not expose `enabled`, reason
templates, internal engine checks, package paths, OPA paths, allowed roots, plan
attributes or operator configuration values. Do not return timestamps or request
IDs in successful reports, so identical catalogs produce identical output.

`required_configuration` describes policy-specific settings, not general server
prerequisites such as roots or the OPA executable. Add the explicit empty array to
the packaged RDS metadata and its strict internal model. Keep this field required
and validate it as empty for the current policy. Future policy settings need their
own specification; L1 adds no tag configuration or configuration framework.
This additive metadata change does not change Rego decisions or the RDS policy
version. Existing analysis and evaluation response schemas remain unchanged.

The expected initial response is:

```json
{
  "schema_version": "1",
  "policies": [
    {
      "policy_id": "AWS-RDS-001",
      "policy_version": "1.0.0",
      "title": "RDS storage encryption",
      "description": "Require explicit storage encryption for standalone AWS RDS instances.",
      "severity": "high",
      "supported_provider_names": ["registry.terraform.io/hashicorp/aws"],
      "supported_resource_types": ["aws_db_instance"],
      "required_paths": [["storage_encrypted"], ["cluster_identifier"]],
      "scope_description": "Standalone aws_db_instance resources only; cluster associations are not resolved.",
      "required_configuration": []
    }
  ]
}
```

## Components and execution

Keep transport, public projection and catalog loading separate:

1. `listing_models.py` defines strict empty input, `ListedPolicy`, `PolicyList`
   and safe boundary validation without MCP imports.
2. `catalog.py` remains the only production loader for catalog metadata. Use
   packaged assets, the existing 65,536-byte catalog limit, strict JSON decoding
   and scope/completeness validation. Do not weaken its one-policy guard or add
   working-directory discovery, Rego loading or runtime probes.
3. `listing.py` projects validated metadata into the public report and provides
   `await PolicyListingService.list_policies() -> PolicyList`. Inject the catalog
   loader for tests; production uses `load_catalog`. Load per request rather than
   maintaining a separate metadata copy or cached health state.
4. `server.py` validates input, calls the injected service, revalidates its public
   result and builds the MCP response. The normal entrypoint creates one listing
   service alongside the analysis and evaluation services.

Run catalog reads, decoding, validation, projection and compact JSON size
measurement in an executor thread. Allow one active listing per service with
nonblocking admission and no wait queue, independently of analysis/evaluation.
On cancellation, finish worker cleanup before releasing admission and propagate
cancellation. Preserve the existing protection against AnyIO scope cancellation,
repeated native cancellation and raw worker exceptions reaching SDK logging.
Do not introduce a general job framework for this small operation.

Bound the complete compact UTF-8 `PolicyList` JSON to **65,536 bytes**, including
all fields and empty arrays. Protocol envelopes and text formatting are outside
this budget. Use a named internal constant and test exact byte boundaries with a
smaller test-only budget and valid metadata. Never truncate or return a partial
list. No new CLI limit option is needed in L1.

The listing and evaluator must use the same validated catalog metadata. Do not
duplicate the RDS description or severity in the handler. A missing, malformed,
oversized or unsupported catalog produces an error, never an empty successful
list or a fallback hard-coded policy. The existing catalog requires one enabled
implemented entry; this increment introduces no disabled or empty-catalog mode.

## Safe failures

Listing failures return `is_error=true`, one fixed text diagnostic in
`CODE: message` form and no structured success payload. Use a small listing error
catalog rather than evaluation-specific wording. Preserve existing analysis and
evaluation error contracts.

| Code | Fixed message |
| --- | --- |
| `INVALID_ARGUMENT` | `Invalid policy listing arguments.` |
| `POLICY_ASSETS_INVALID` | `The packaged policy assets are invalid.` |
| `POLICY_LIST_LIMIT_EXCEEDED` | `The policy list exceeds its limit.` |
| `SERVER_BUSY` | `Another policy listing is already running.` |
| `INTERNAL_ERROR` | `The policy list could not be completed.` |

Translate the existing loader's `POLICY_ASSETS_INVALID` into the matching listing
failure. Unexpected failures log only a fixed code and generated request ID, with
no traceback, validation details, catalog contents or rejected argument names.
Unknown tool names retain the existing fixed protocol error. No listing failure
may disable the other tools or turn an evaluation error into a compliance result.

## Acceptance cases

Use synthetic inputs, injected loaders/failures, the installed SDK client and real
stdio subprocesses. Listing-specific tests require no OPA, Terraform, AWS
credentials or network. Real OPA remains mandatory for full evaluation/release
regression checks.

| ID | Case and required result |
| --- | --- |
| LP-01 | Normal runnable-server discovery exposes exactly the three named tools, strict listing input/output schemas and read-only annotations. Existing analysis-only test wiring remains usable. |
| LP-02 | `{}`, omitted `arguments` and the SDK's null no-arguments representation return the example metadata above; text JSON equals structured content and passes the public output schema. |
| LP-03 | Extra keys, arrays and scalar arguments fail safely at the application or SDK boundary. Sentinel secrets in keys/values never appear in either output channel or captured logs. |
| LP-04 | Every listed ID is selectable by the evaluator's catalog selection. Shared descriptions, versions, severity, provider names, resource types, paths and scope match the loaded catalog exactly; configuration requirements come from that same catalog. |
| LP-05 | Only AWS-RDS-001 is advertised. Cluster resources, SSH, tags and S3 remain absent; the standalone-only limitation is explicit. Existing catalog guards reject unsupported or incomplete metadata rather than advertising it. |
| LP-06 | Unconfigured, nonexistent and unsupported OPA paths all leave listing successful. Assert no OPA probe, subprocess, plan-loader, Terraform adapter or evaluation-service call occurs. |
| LP-07 | Missing, invalid UTF-8, duplicate-key, malformed, oversized and invalid-schema catalogs produce only the fixed asset error. Missing configuration requirements also fail validation; no successful empty/partial result is returned. |
| LP-08 | Public projection excludes internal reason templates, enabled flags, paths to local assets and configured values. Core listing modules import without MCP and perform no import-time reads or startup. |
| LP-09 | Repeated requests produce identical ordering/content. Duplicate public IDs and invalid service results fail validation safely rather than bypassing the output schema. |
| LP-10 | With a smaller test-only budget, complete compact UTF-8 output at the byte limit succeeds; a report one byte over fails with the fixed limit error. Include non-ASCII metadata so character count cannot substitute for byte count; verify the production constant remains 65,536. |
| LP-11 | A slow injected loader leaves the event loop responsive; concurrent listing fails immediately as busy. Cancellation joins worker cleanup, releases admission and allows a later successful call, including native and AnyIO cancellation cases. |
| LP-12 | Auto and legacy SDK clients call listing over real stdio from outside the checkout with no OPA configured. Errors do not corrupt stdout or prevent subsequent analysis/listing calls. |
| LP-13 | A representative listed ID drives a real OPA evaluation with unchanged findings and scope. Existing analysis/evaluation tests pass; adding metadata does not change either public contract or Rego decisions. |
| LP-14 | Installed wheel/source examples load the packaged catalog independently of the working directory. The example client's listing flag and saved response match actual stdio output, and no new runtime dependencies or test-only policies enter the wheel. |

## Implementation tasks and completion

L1 is divided into small tasks, completed in order with their relevant checks:

| Task | Deliverable | Verification |
| --- | --- | --- |
| L1a: Contracts and catalog metadata | Listing models/errors, explicit RDS configuration requirements, strict catalog validation and public projection. | LP-02–LP-05, LP-07–LP-09; model/projection tests require no OPA. |
| L1b: Listing service | Lazy injected catalog loading, bounded output, executor work, independent admission and cancellation cleanup. | LP-06–LP-11, including safe worker failures and recovery. |
| L1c: MCP wiring | Third tool, strict validation/output schemas, startup service injection and safe failures. | LP-01–LP-03, LP-06, LP-08–LP-09 and LP-12 through SDK auto/legacy and stdio. |
| L1d: Walkthrough and package verification | Add `--list-policies` to `examples/client.py`, a saved report, listing walkthrough/acceptance record, and accurate three-tool documentation. Keep `--list-tools` for MCP function discovery. | LP-12–LP-14; verify source/wheel assets and installed operation outside the checkout. |

For implementation, run the documented locked, non-editable Python tests and
Ruff checks, real OPA check/format/tests and evaluation integrations, plus source/
wheel and installed-stdio verification. Record actual results in a listing
acceptance document; do not mark cases complete before execution. Add meaningful
comments/docstrings as each component is written, following `AGENTS.md`.

The user authorized implementation on 2026-10-19. Drafting required only
documentation checks; implementation adds the checks and evidence above without
new dependencies. Expanded policy coverage remains a separately scoped increment;
L1 does not complete the full v0.1 MVP.

## Official reference and decisions

The [official SDK 2.3.0 migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/migration.md)
documents constructor-registered low-level handlers and explicit `CallToolResult`
construction with text and structured content. The
[official error guide](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/servers/handling-errors.md)
documents tool errors using `is_error`. Retain the pinned generation and our
explicit safe validation rather than migrating SDK APIs in this increment.

No OPA execution decision changes: Specification 002 and the existing pinned
runtime/capabilities remain authoritative. Listing consumes packaged metadata
without invoking the engine.
