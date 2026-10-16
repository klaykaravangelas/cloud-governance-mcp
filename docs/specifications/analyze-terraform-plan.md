# Specification 001: analyze Terraform plans

Status: implemented and verified; A1–A7 complete.
Updated: 2026-10-16. See [acceptance evidence](../analysis-acceptance.md) and
[the hands-on walkthrough](../trying-analysis.md).

This specification defines the first independently usable increment in
[the implementation plan](../implementation-plan.md), tasks A1–A7. It refines
FR-01 through FR-04, the parsing/masking portion of FR-09, and the applicable
security criteria in [requirements](../requirements.md). The architecture remains
layered as described in [architecture](../architecture.md).

## Purpose and boundaries

Answer: **What resource changes does this Terraform plan propose?**

Expose one local stdio tool, `analyze_terraform_plan`. Read an existing JSON plan,
validate it, normalize resource identities/actions, and return a deterministic
summary. Support resource identities across providers and resource types without
requiring a provider schema or policy-specific implementation.

This increment makes no security/compliance judgment and includes no OPA, Rego,
policy catalog, evaluation tool, listing tool, Terraform execution, AWS clients,
network calls, or infrastructure modification. Input files are never modified.
Resource attributes, variables, output values, and configuration expressions are
excluded from tool responses even if Terraform does not mark them sensitive.

## Prerequisites and installation timing

Writing/reviewing this specification requires no project dependencies. The
development environment was checked during specification drafting on 2026-10-16:
`python3 --version` reported
Python 3.14.7, `uv --version` reports uv 0.12.18, and OPA is absent from PATH.
At that point no `pyproject.toml`, `uv.lock`, or project environment existed. A1
has since created them. See [development setup](../development.md) for current
version pins and bootstrap verification; the observations above are historical.

At A1, select the development interpreter, verify published stable package
compatibility with Python 3.14, declare the official `mcp` package and Pydantic
as runtime dependencies, and add pytest, Ruff, and an async test integration if
needed. Create `.venv` with uv, commit `uv.lock`, and verify a reproducible install.
Use the official SDK's installed API generation. Do not install dependencies
globally, lower the Python requirement silently, or require an OPA/Terraform/AWS
installation for analysis. OPA installation/version selection belongs to E1.

## Tool input and discovery

Tool name: `analyze_terraform_plan`.

Description: "Summarize resource identities and proposed actions from a local
Terraform plan JSON file in an allowed directory. Returns no resource attribute
values and performs no compliance evaluation or infrastructure changes."

The input object has exactly one required property:

| Field | Type | Validation |
| --- | --- | --- |
| `plan_path` | strict string | 1–4096 characters; cannot be whitespace-only, contain NUL/control characters, or be a URI. Reject extra arguments and type coercion. |

Do not trim or expand the path: spaces inside a filename are meaningful, `~` is
not expanded, and environment-variable expressions remain literal. Relative
paths resolve against the first configured root, never the process working
directory. Absolute paths must lie within a configured root. A `.json` extension
is not required; content determines whether the input is a valid plan.

Example arguments:

```json
{"plan_path": "plans/mixed.json"}
```

Advertise input and output JSON schemas and read-only, non-destructive,
idempotent, closed-world tool annotations using the pinned SDK's API. Repeating
a call against unchanged file bytes/settings returns the same analysis. The file
may change between calls; annotations do not imply a persistent snapshot.
Only this tool is discoverable in increment 1.

## Operator configuration and limits

Provide repeatable `--allowed-root` startup arguments, in order. At least one
existing, absolute directory is required; no default root exists. Resolve and
open each trusted root once at startup. Invalid configuration prevents startup
with a safe diagnostic on stderr. Client-supplied MCP roots cannot grant access.

All limits below are defaults with validated positive integer startup overrides;
they are not tool arguments. Include their documented option names in A1/A3.

| Setting / startup option | Default | Boundary behavior |
| --- | --- | --- |
| `--max-plan-bytes` | 10,485,760 (10 MiB) | Read at most limit + 1 bytes; reject overflow before JSON parsing. |
| `--max-json-depth` | 128 | Root object has depth 1; each nested object/array increments depth. Reject over-limit input before recursive decoding/processing. Braces inside JSON strings do not increase depth. |
| `--max-resources` | 10,000 | Maximum unique resource records after merging; also bound entries in each source inventory/change list to prevent duplicate-heavy inputs. |
| `--max-analysis-bytes` | 4,194,304 (4 MiB) | Maximum compact UTF-8 JSON encoding of the analysis object. Fail rather than truncate resources or counts. |

Limit identity strings to 2048 characters each and reject control characters;
`type`/`name`/provider/module/address fields are data, never message templates.
Keep one analysis active at a time with no pending work queue; concurrent calls
beyond that return `SERVER_BUSY`. File reading/parsing must not block the MCP
event loop. Release the active slot and close descriptors on success, error, or
cancellation. This increment spawns no runtime child processes.

A5 implements this through an asyncio service. Cancellation waits for its
synchronous worker to finish and close per-read descriptors before releasing the
active slot, then propagates cancellation without a report. Cancellation cannot
forcibly interrupt a thread or a slow underlying filesystem read. AnyIO's asyncio
backend is supported; Trio is outside the current service boundary.

The descriptor-based containment implementation initially targets macOS/Linux.
On a platform lacking the needed secure-open primitives, startup must report an
unsupported platform rather than substitute a race-prone check/open sequence.
Document this initial platform boundary in the eventual setup guide.

## Safe file loading and decoding

1. Validate the argument, select an allowed root by path-component containment,
   and reject any `..` component, including one that would return inside a root.
2. Walk/open beneath the trusted directory descriptor without following symlink
   components. Never authorize by string prefix alone. Symlinks below a root are
   rejected even when their destination is inside the root.
3. Check the opened descriptor is a regular file. Open safely without blocking on
   FIFOs; reject directories, sockets, devices, and other special files. A changed
   pathname must not redirect the descriptor to another target.
4. Perform the bounded read, enforce structural depth, and decode strict UTF-8
   JSON. Reject duplicate JSON object keys and non-finite numbers, including NaN,
   Infinity, or numeric overflow during decoding. Reject a BOM rather than
   silently changing encodings.
5. Validate the plan envelope and every consumed structure. Never include raw
   bytes, filenames/paths, JSON parser excerpts, or Pydantic inputs in errors.

The filesystem is controlled by the local operator; in-place changes to an
already-open file are not guaranteed to produce a consistent external snapshot.
Document that callers should supply a completed, stable plan file. A malformed
or inconsistent read must fail validation, not yield guessed counts.

## Accepted plan shape

Require a JSON object with `format_version` matching decimal `major.minor` and
major 1. Accept additive fields in that major without echoing them. The reported
Terraform version is an optional bounded nonempty string, not a compatibility
gate; return null when absent.

Require at least one plan discriminator: `resource_changes` as an array or
`planned_values` as an object. Reject state envelopes with top-level `values`,
even when another plan discriminator is present. Accept these intentionally small
synthetic examples as empty plans:

```json
{"format_version": "1.0", "complete": true, "resource_changes": []}
```

```json
{"format_version": "1.0", "complete": true, "planned_values": {}}
```

An omitted root module is empty inventory. In consumed module objects,
`resources` and `child_modules` may be omitted (empty); when present they must be
arrays, not null. Each child module requires a bounded nonempty `address` and
is traversed recursively. Reject duplicate child-module addresses across the
inventory. `resource_changes`, `planned_values`, mask fields, and optional plan
flags must have their documented types when present; null does not mean omitted.

For each change or planned inventory entry, require nonempty `address`, `mode`
(`managed` or `data`), `type`, `name`, and `provider_name`. Optional `index` is a
nonnegative integer excluding bool, or a bounded string. Preserve it exactly;
absence maps to null in output. A supplied `module_address` is a bounded nonempty
string. Unknown modes or malformed identity fields fail the call.

For change entries, require a `change` object with a supported nonempty ordered
`actions` array. `before`/`after` and inventory `values` may be null or JSON objects;
their provider-specific members are not schema-validated in this increment.
Sensitivity/unknown masks accept boolean leaves, objects, and arrays of those
shapes, including a true root marking the entire value. Do not coerce leaf types.

Treat addresses and module addresses as opaque identities. Obtain module
membership from the containing inventory module or explicit change metadata;
do not split addresses on dots or interpret quoted instance keys. Preserve
`previous_address` on moved entries as optional identity metadata. Do not parse
or execute Terraform configuration expressions.

## Normalization and inventory merge

The normalized snapshot is shared core data with no MCP types. This increment
needs identities/actions, source provenance, coverage, and mask paths. A2 models
this as `NormalizedResource.resource` (a public `ResourceAnalysis`) plus separate
internal mask paths and `unknown_metadata_complete`. The snapshot need
not retain provider attribute payloads after extracting masks; future evaluation
can extend the adapter with a redacted desired-state projection without changing
the public analysis schema.

1. Index current `resource_changes` by exact address. Duplicate keys within this
   source are errors; never silently choose the last entry.
2. Recursively index planned inventory by exact address. Duplicate keys within
   this source are errors even when their metadata agrees.
3. Merge overlap into one record. Identity fields (`mode`, type, name, provider,
   and any supplied index/module metadata) must agree; a mismatch is an invalid
   plan. Missing optional change module metadata can be filled from its containing
   inventory module. Change actions take precedence over inventory's lack of
   action information.
4. Include change-only deletions and all data-source identities. Do not confuse
   absence from planned inventory with deletion; explicit actions decide that.
5. For inventory-only resources, return `actions=[]`, category `unreported`, and
   provenance `planned_values`. Do not infer `no-op`. Emit an aggregate coverage
   warning for their count.
6. Sort final resources lexicographically by exact address; identical inputs and
   settings must produce identical output without timestamps or generated IDs.

Terraform can represent deposed objects alongside a current object at the same
address. A supplied `deposed` must be a nonempty string (otherwise `INVALID_PLAN`).
This first specification rejects valid deposed entries as
`UNSUPPORTED_PLAN_FEATURE`; it does not merge those objects and lose actions.
A future specification may support compound identity keys explicitly.

Internally preserve unknown and sensitive paths as arrays of string keys and
integer indices. A true ancestor marks its whole subtree; retain the ancestor
path rather than expanding it. Extract `after_unknown`, `after_sensitive`, and
planned `sensitive_values`; union sensitive masks conservatively on overlap.
Keep unknown and sensitive metadata separate, and never replace either with false,
empty collections, or a string sentinel. No raw `before` values are retained.
For change records, `unknown_metadata_complete` is true only when `after_unknown`
was supplied; an omitted mask does not establish known values. For inventory-only
records, flag unknown metadata as incomplete internally:
planned values alone cannot prove that omitted/null attributes are known. The
analysis tool neither exports these attribute paths nor uses them for decisions.

## Actions and counting rules

Only the following ordered arrays are supported in this specification:

| Terraform actions | Analysis category |
| --- | --- |
| `["create"]` | `create` |
| `["update"]` | `update` |
| `["delete"]` | `delete` |
| `["delete", "create"]` | `replace` |
| `["create", "delete"]` | `replace` |
| `["no-op"]` | `no_op` |
| `["read"]` | `read` |
| No change entry; inventory only | `unreported` with `actions=[]` |

Unknown actions/combinations (including lifecycle operations outside this table)
return `UNSUPPORTED_PLAN_FEATURE`; do not silently omit or reinterpret them.

- Each merged resource contributes exactly one to `total_resources`, one action
  bucket, one type bucket, and one mode bucket. Keep all seven action keys even
  when zero. Type counts include both modes; `by_mode` separates them.
- `changing_resources` counts managed entries in create/update/delete/replace.
  Data-source reads and no-op/unreported entries do not increase it.
- Replacement contributes one to `replace` and none to create/delete counts.
  Ordered `actions` preserves destruction/creation order for the caller.
- `unreported` is uncertainty about action reporting, not a new Terraform action.
- Moved/import metadata does not turn a no-op into create/update. Preserve moved
  identity metadata; emit an aggregate warning when import metadata exists
  because this increment does not summarize import operations separately.
- Output-only changes and `resource_drift` are outside resource action counts;
  emit warnings when present and nonempty, without reading/displaying values.

## Coverage and warnings

`analysis_status` is `complete` when represented resource actions were fully
analyzed without a coverage warning, otherwise `partial`. It describes this
bounded analysis of the supplied plan, never the deployed account or compliance.
Coverage warnings are successful results, not tool errors. Do not return a
partial result for invalid input or a limit violation.

Use this fixed warning catalog. Messages are application-controlled text, with
optional numeric `count`; never interpolate paths, attributes, or plan strings.
Return each code once, sorted by code.

| Code | Condition / fixed meaning |
| --- | --- |
| `PLAN_COMPLETENESS_UNSPECIFIED` | `complete` is absent; plan completeness was not reported. |
| `PLAN_INCOMPLETE` | `complete=false`; the supplied plan reports incomplete planning. |
| `PLAN_ERRORED` | `errored=true`; only the resource actions present before planning failed are summarized. |
| `DEFERRED_CHANGES_PRESENT` | Nonempty `deferred_changes` array; deferred entries are excluded from resource counts and `count` reports their number. |
| `PLANNED_VALUES_UNAVAILABLE` | `planned_values` is absent; summary uses only reported changes. |
| `CHANGE_ACTIONS_UNREPORTED` | Inventory-only records exist; `count` is their number. |
| `IMPORTS_NOT_SUMMARIZED` | Change entries contain import metadata; `count` is their number. |
| `OUTPUT_CHANGES_NOT_SUMMARIZED` | Nonempty `output_changes` object; `count` is its entry count. |
| `RESOURCE_DRIFT_NOT_ANALYZED` | Nonempty `resource_drift` array; `count` is its entry count. |

Optional `complete` and `errored` values must be strict booleans. An errored plan
with a valid accepted envelope can be summarized, with the warning above. Validate
the container types used for warning detection; ignore the interior payloads of
deferred entries/drift/output/import metadata. Preserve neither their strings nor
their values in analysis results or logs. Do not infer plan completeness from an
empty change list. `complete=true` with empty available inventories and no warning
can return `complete` with all zero counts.

## Output contract

Return a Pydantic-validated object with exactly these fields; reject extra fields
in internal response construction. All counts are nonnegative integers. Serialize
null optionals consistently. Human-facing text must be generated from this same
safe object, not from the raw plan.

| Object | Fields |
| --- | --- |
| `PlanAnalysis` | `schema_version`: literal `"1"`; `format_version`: accepted input version; `terraform_version`: string or null; `analysis_status`: `complete` or `partial`; `summary`; `resources`; `warnings`. |
| `summary` | `total_resources`; `changing_resources`; `by_action` with exactly `create/update/delete/replace/no_op/read/unreported`; `by_type` map; `by_mode` with exactly `managed/data`. |
| Resource item | `address`; `resource_type` (from `type`); `name`; `provider_name`; `mode`; `module_address` (string or null); `index` (int/string/null); `previous_address` (string or null); `actions` (ordered strings); `action_category`; `source` (`resource_changes`, `planned_values`, or `both`). |
| Warning item | Catalog `code`; fixed `message`; `count` (integer or null). |

`module_address=null` means no module metadata was supplied, including root
resources. Do not claim it proves root membership for a change-only entry.
Sort `by_type` keys and resource items lexicographically. Return empty arrays/maps
where specified rather than omitting required fields. No findings, compliance
status, raw file paths, attribute values, or mask paths appear in this response.

Illustrative complete response for one synthetic resource:

```json
{
  "schema_version": "1",
  "format_version": "1.2",
  "terraform_version": "1.14.0",
  "analysis_status": "complete",
  "summary": {
    "total_resources": 1,
    "changing_resources": 1,
    "by_action": {
      "create": 0, "update": 0, "delete": 0, "replace": 1,
      "no_op": 0, "read": 0, "unreported": 0
    },
    "by_type": {"aws_db_instance": 1},
    "by_mode": {"managed": 1, "data": 0}
  },
  "resources": [{
    "address": "module.database.aws_db_instance.example",
    "resource_type": "aws_db_instance",
    "name": "example",
    "provider_name": "registry.terraform.io/hashicorp/aws",
    "mode": "managed",
    "module_address": "module.database",
    "index": null,
    "previous_address": null,
    "actions": ["delete", "create"],
    "action_category": "replace",
    "source": "both"
  }],
  "warnings": []
}
```

The example Terraform version is fixture metadata, not a required executable.
The example `format_version` illustrates a supported major with an additive minor.

## Error contract and MCP behavior

Tool failures return `isError=true` on the wire with one safe text message
containing a stable code and catalog-controlled explanation. No success analysis
object is returned. Do not embed validation inputs, raw exception text, absolute
paths, plan content, or tracebacks in text or structured output. Invalid protocol
requests remain SDK-managed; sanitize any tool-argument errors raised before the
handler as well as errors inside it. Test the pinned SDK path explicitly.

| Code | Meaning |
| --- | --- |
| `INVALID_ARGUMENT` | Missing/extra argument, wrong type, invalid string/path syntax. |
| `PATH_NOT_ALLOWED` | Traversal, path outside allowed roots, or disallowed symlink component. |
| `PLAN_FILE_UNAVAILABLE` | Missing/unreadable file, descriptor-open failure, or non-regular target. |
| `PLAN_LIMIT_EXCEEDED` | Input bytes/depth/resource count/identity length exceeds a configured bound. |
| `INVALID_JSON` | UTF-8/JSON failure, duplicate object key, non-finite numeric token, or BOM. |
| `INVALID_PLAN` | Wrong envelope, missing/invalid consumed fields, duplicate resources/modules, or identity conflicts. |
| `UNSUPPORTED_PLAN_VERSION` | Well-formed format version has a major other than 1. Malformed version strings are `INVALID_PLAN`. |
| `UNSUPPORTED_PLAN_FEATURE` | Unsupported action combination or deposed object. |
| `ANALYSIS_LIMIT_EXCEEDED` | Safe analysis object exceeds the output budget; nothing is truncated. |
| `SERVER_BUSY` | Another analysis is active. |
| `INTERNAL_ERROR` | Unexpected failure; generic safe message and request ID in logs only. |

Validate arguments before file access; validate bounded bytes/JSON before plan
semantics. For multiple plan semantic errors, deterministic traversal order is
sufficient; the public contract does not promise an exhaustive diagnostic list.
Cancellation follows SDK behavior and must release resources, not return a
fabricated complete result.

## Confidentiality and internal boundaries

Use `server -> service -> restricted loader -> Terraform adapter -> analysis
builder`. Models, parser and summarizer contain no MCP imports. The service can
be tested directly. Tool handlers handle protocol mapping; they do not implement
filesystem checks or resource counting.

The response intentionally includes resource identity strings, which may contain
operator-chosen instance keys. Encode them as data, never instructions or markup;
do not log identities. Do not echo unknown plan keys, attribute paths, or values.
Use safe log codes/counts/durations/request IDs and keep debug logging disabled.
In particular, SDK validation error handling must not log or echo rejected input.

## Acceptance cases

Create synthetic fixtures during implementation. No fixture generation needs
Terraform, AWS, network access, or OPA. These named cases are the acceptance
matrix. A2 provides contract unit tests and A3 provides file/JSON boundary tests.
A4 adds parser/mask and loader-to-adapter tests plus representative plan fixtures
under `tests/fixtures/plans`. A5 adds summary/service tests for counts, output limits,
errors, admission and cancellation cleanup. A6 adds SDK discovery/calls, CLI
startup failures and real stdio tests outside the checkout, in both modern auto
and legacy initialization modes. A7 adds the working example client, saved report,
walkthrough tests and [final acceptance record](../analysis-acceptance.md).

| ID | Scenario | Required assertions |
| --- | --- | --- |
| AN-01 | Package and startup | Python 3.14 uv install and wheel import outside repo; import starts no server; configured stdio launches without OPA. No roots/invalid roots fail startup safely. |
| AN-02 | Mixed actions | Seven resources: one create, update, delete, replacement, managed no-op, data read, and inventory-only record. Total 7; each action bucket 1; changing 4; managed 6/data 1; unreported warning with count 1. |
| AN-03 | Replacement ordering | Each replacement order remains intact in output and counts once in replace, never create/delete. |
| AN-04 | Recursive identity handling | Root, nested child modules, count index 0, and for_each keys containing dots/quotes retain exact identity/index. No naive address splitting or provider-specific filtering. |
| AN-05 | Inventory merge | Overlap yields one item with source both; change-only delete is retained; inventory-only action is unreported. Duplicate sources/module addresses and conflicting identities fail. |
| AN-06 | Empty plans | Both minimal accepted examples return zero resources. Changes-only empty plan has planned-values warning; both inventories empty with complete=true has no warnings. State/arbitrary JSON fails. |
| AN-07 | Plan coverage | Missing/false completeness, errored planning, deferred entries, imports, output changes and drift produce exactly the specified fixed warning codes/counts; no payload is echoed. |
| AN-08 | Input and format | Missing/extra/wrong-type arguments, whitespace/NUL/URI paths, malformed versions, unsupported majors, invalid consumed shapes, unknown modes/actions, and deposed objects return the appropriate safe errors. Additive fields are ignored. |
| AN-09 | File boundary | Allowed relative/absolute files succeed. Traversal, sibling-prefix escape, external absolute paths, final/intermediate symlinks fail. Directory/FIFO/device targets never block and are rejected. Controlled component-swap tests cannot escape the open root. |
| AN-10 | Size and structure | Exactly-at/over byte/depth/resource/output limits are exercised. Strings with braces/escapes do not confuse depth checks; malformed UTF-8, BOM, duplicate JSON keys, NaN/Infinity fail safely. Oversize input/output returns no truncated success. |
| AN-11 | Masks and confidentiality | Whole-root, nested-object and list masks preserve typed paths internally. Unknown/sensitive mask metadata is not misclassified as known false or absent; inventory-only unknown metadata stays incomplete. Marked/unmarked attribute sentinels, variables, outputs, unknown keys, and rejected tool inputs appear in neither output channel nor captured logs/errors. |
| AN-12 | Determinism and invariants | Resource/source-array order permutations produce equivalent sorted summaries. Sum by_action, by_type, and by_mode each equals total; changing_resources matches managed action categories. Zero buckets remain present. |
| AN-13 | SDK contract | Exactly one tool, strict arguments, input/output schemas, appropriate annotations, typed successful output, sanitized pre-handler validation errors, and isError on tool failure. Text serializes only the same safe response. |
| AN-14 | Real stdio and packaging | SDK client initializes a subprocess outside repo, discovers analysis, calls a valid and denied/invalid case, validates response schema, and shuts down cleanly. Stdout has protocol traffic only. |
| AN-15 | Concurrency and cleanup | Second concurrent analysis gets SERVER_BUSY; cancellation/read/parser failures close descriptors and release the slot so another call succeeds. No AWS, Terraform, OPA, shell, or network execution occurs. |

For every fixture with a complete analysis, assert the full expected count
invariants and source provenance. Tests may call pure parser/service functions;
they must also exercise actual MCP discovery/calls and the file boundary.

## Completion criteria

Tasks A1–A7 are complete: AN-01–AN-15 pass on the verified macOS environment,
setup/launch/error/limit documentation matches behavior, and `uv run pytest`,
`uv run ruff check .`,
`uv run ruff format --check .`, wheel verification and the real stdio test have
been executed successfully. Exact dependencies, results and limitations are in
the [acceptance record](../analysis-acceptance.md). The full 521 tests pass,
including SDK/stdio execution,
strict schemas, safe pre-handler/tool failures, text/structured confidentiality,
and cancellation cleanup. The walkthrough and acceptance traceability are complete;
Linux execution and Terraform-generated/live-account plan campaigns are not claimed.

The deliverable is a useful analysis tool and a tested parsing foundation.
Evaluation subsequently consumes that foundation directly and adds its own
specification for redacted desired-state values and policy outcomes. Do not add
future tool registrations or speculative policy dependencies to complete analysis.

## Official references

Consulted 2026-10-16. Schema semantics from these sources inform this design;
limits, counting conventions, warning/error catalogs, and unsupported-feature
boundaries are explicit project choices.

- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format):
  plan/inventory structures, opaque identities, versions, changes and masks.
- [MCP tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools):
  tool schemas, results, annotations, and tool errors.
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
  [structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/),
  and [SDK error handling](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/).
  Recheck the installed published release during A1; this specification defines
  behavior independently of SDK import names.
