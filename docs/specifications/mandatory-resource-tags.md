# Specification 006: mandatory resource tags

Status: approved for implementation on 2026-10-22; M3a–M3e implemented.
See [acceptance evidence](../tags-acceptance.md) for executed checks and the
separate pending live-host reload.
Updated: 2026-10-22.

This specification defines M3 in the [implementation plan](../implementation-plan.md).
The user requested the specification and accepted `Environment`, `Owner` and
`Project` as starting defaults, then authorized implementation. The runtime now
exposes AWS-RDS-001 v1.1.0, AWS-SG-001 v1.0.0 and AWS-TAG-001 v1.0.0.
No dependency, tool or host configuration change was needed.

## Outcome and scope

Add **AWS-TAG-001 v1.0.0**, medium severity: require each configured tag key to
have a known, nonblank string value in the resource's observed desired tag map.
Use the same three tools and stdio transport. Policy inputs remain plan data;
the server never executes Terraform or inspects/modifies AWS.

The canonical provider is `registry.terraform.io/hashicorp/aws`. Start with this
exact supported-type list, in this order:

1. `aws_instance`
2. `aws_security_group`
3. `aws_db_instance`
4. `aws_rds_cluster`
5. `aws_s3_bucket`

Match exact provider/type metadata, not address prefixes. Include nested modules
and indexed resources. Managed create, update, either replacement order, no-op
and inventory-only resources are in scope when their desired data is available.
Data sources, deletion-only resources and other providers/types get the existing
not-applicable exclusions. `aws_rds_cluster_instance`, standalone security-group
rules, attached volumes, nested blocks and individual `*_tag` resources are not
supported by this increment, even where a provider supports their tagging.
S3 bucket tagging does not implement S3 public-access protection.

This checks the supplied plan's observed tags, not an organization's complete
tag strategy or deployed inventory. Do not validate allowed business values,
ownership identities, cost centers, tag counts in AWS, resource-name conventions,
organization tag policies or resource-specific exemptions. Do not propagate tags
between resources or interpret HCL/provider expressions, aliases, `ignore_tags`,
`ignore_changes` or environment variables. Ignored/external tags may be absent
from the plan; absence is a failure of this observed-plan requirement, not proof
that the tag is absent in AWS. Document that limitation in policy scope.

## Operator configuration

Add one repeatable **server-startup** option, `--required-tag-key`, backed by
`EvaluationSettings.required_tag_keys`. It is not an MCP argument.

- With no occurrences, use exactly `Environment`, `Owner`, `Project`.
- One or more occurrences replace the entire default list. Requiring `CostCenter`
  as well needs all four flags; no implicit append to defaults occurs.
- Require 1–50 distinct strict strings, each 1–128 ASCII characters matching
  `[A-Za-z0-9_./:=+@-]+`. Reject any case-insensitive `aws:` prefix. This is a
  deliberately narrower operator-key syntax, not a full AWS tag-key validator.
- Keys and duplicate detection are case sensitive. `Owner` and `owner` are
  distinct requirements. Do not trim, case-fold, coerce or silently deduplicate.
  Reject empty/whitespace keys, Unicode/control characters, invalid types,
  oversized lists/keys and exact duplicates. Sort valid keys lexicographically.
- Validate through the safe settings entrypoint. Invalid settings fail startup
  with the existing fixed configuration diagnostic and exit 2, before opening
  roots or probing OPA; never echo rejected option names/values or raw errors.
- Copy validated keys into an immutable service configuration. Each request uses
  one consistent snapshot; no shared adapter setting changes between calls.
- No environment-variable override, config-file loader, per-request exemption,
  policy reload or new dependency is introduced. Analysis and listing still need
  no OPA; normal startup still validates operator settings.

Server-startup example (absolute paths are placeholders):

```sh
cloud-governance-mcp --allowed-root /absolute/path/to/plans --opa-path /absolute/path/to/opa --required-tag-key Environment --required-tag-key Owner --required-tag-key Project --required-tag-key CostCenter
```

Update the CLI's existing evaluation-budget loop explicitly: a list-valued
setting must not accidentally become an integer budget option. Keep existing
options/defaults unchanged. Add the same repeatable flag to `examples/client.py`
as a server-startup forwarding option; omission lets the server supply defaults.
Arguments remain fixed executable/argument-list construction, never shell text.

## Select the authoritative tag map

Reuse the existing desired-source precedence: a change's `after` is authoritative;
inventory values are used only for inventory-only resources. Never fill missing
or null `after` from `before` or a conflicting planned inventory. Merge sensitive
metadata from change/inventory sources before projection. Missing unknown
metadata remains unverified; it does not prove that an omitted key is known absent.

Provider documentation describes `tags_all` as including provider `default_tags`,
with resource tags overriding matching defaults. Use these project rules rather
than recomputing that merge:

| Observed condition, after masks | Source and behavior |
| --- | --- |
| Root attributes sensitive/unknown | Whole projection sensitive/unknown; inspect no values and select no source. |
| Unknown metadata incomplete | Whole projection unverified; select no source. |
| Desired object unavailable | Whole projection unavailable; select no source. |
| `tags_all` exists, including `{}` or `null` | Select `tags_all`; never merge with or fall back to `tags`. |
| Any mask at/below `tags_all` despite an omitted value | Select `tags_all`; masking cannot be bypassed through fallback. |
| `tags_all` is absent with complete metadata and no mask at/below it | Select `tags`, including known missing/null cases. |

Explicit `tags_all: null` without an overriding mask means a known absent tag
map and fails; a whole unknown/sensitive mask makes it indeterminate. An empty
`tags_all` fails even if `tags` contains every required key. Fallback evaluates
only observed `tags`; it cannot infer unexported provider defaults. A finding's
path identifies which source was checked. These null/fallback semantics are
project decisions, not assertions about every provider release. Descendant masks
also override unusable null/non-object placeholders before classifying absence.

## Masking and value observations

Apply masks before inspecting values or classifying string content. Tag maps use
stable string keys; unlike inline security-group sets, known sibling keys can be
handled independently. Never align resources by list position.

- Root and whole selected-map masks withhold the entire corresponding object.
  Sensitivity wins over unknown. An omitted map with descendant masks is wholly
  sensitive/unknown (sensitive wins), not an empty or known-missing map.
- For a known map, ancestor/exact/descendant masks on a required key withhold that
  key. A malformed child mask must not cause its parent value to be read.
- Conservatively union sensitivity for each required key across both `tags` and
  `tags_all`, as well as both plan sources. Whole-map sensitivity on either copy
  withholds the selected map. This prevents an unmasked duplicate of a sensitive
  tag from producing a known-content observation. Unknown masks apply only to
  the selected map; the unused copy is not compliance evidence.
- Masks on unrelated string keys do not affect required siblings in a known map.
  An integer-index mask below the selected map has no valid key interpretation;
  withhold that map as sensitive/unknown rather than dropping the mask. A
  sensitive malformed index below the unused copy also withholds the selected
  map; an unknown mask on the unused copy remains irrelevant.
- Unknown/unverified values never become empty strings, missing keys or passes.
  Do not inspect unrequired tag values. Unrequired tag-map keys/values do not
  enter TAG observations, OPA input, reports, logs or exception diagnostics.
  The existing shared internal mask paths remain private normalization metadata;
  preserving those paths does not authorize returning their key names.

For each required key in a known map, retain only one observation:

| State | Meaning |
| --- | --- |
| `nonempty` | Strict string with at least one character after Python 3.14 `str.strip()`; discard the original and stripped strings. |
| `blank` | Strict string empty after `str.strip()`, including whitespace-only values. |
| `missing` | Key absent, with complete applicable metadata and no mask. |
| `null` | Key explicitly null, with no overriding mask. |
| `invalid_type` | Known nonstring/non-null value; never coerce numbers, booleans, arrays or objects. |
| `sensitive` / `unknown` | Applicable key mask; no value is retained or classified. |

Whitespace rules classify content only; values such as `" false "`, `"0"` and
arbitrary nonblank Unicode strings meet this first policy's content requirement.
No raw value, hash, excerpt, length or serialized invalid payload survives.
Python records observations; **Rego decides compliance and aggregates keys**.

## Strict internal contracts and architecture

Add small pure `tag_models.py` and `tag_projection.py` components, without MCP,
filesystem, OPA or AWS imports. Call projection in the existing adapter pass after
source/mask merging. Do not introduce a generic policy-plugin framework.

Advance **engine input to schema 4** when activating M3. Public reports, engine
output and catalog envelopes remain schema 1. Rego rejects old input schemas;
selected RDS graph and SSH representation/limit validation remains unchanged.

Add optional `tag_state` to normalized/projected resources and optional
`tag_configuration` to engine input. Unselected tags require both to be absent/
null. With TAG selected, configuration contains exactly the validated sorted
`required_tag_keys`; eligible resources require one of these strict variants:

- **Unresolved**: `source: "unresolved"`, one state from `sensitive`, `unknown`,
  `unverified`, `unavailable`; no entries or other payload.
- **Selected map**: `source: "tags_all" | "tags"`, one state from `sensitive`,
  `unknown`, `null`, `invalid_type`; no entries. Only source `tags` may additionally
  have `missing`, because known absence of `tags_all` triggers fallback.
- **Known map**: `source: "tags_all" | "tags"`, `state: "known"`, and exactly one
  `{key, state}` entry for every configured key, in configuration order, using
  the seven key states above. No extra/missing/duplicate keys or value payloads.

For example, a safe projection, not a public response:

```json
{
  "source": "tags_all",
  "state": "known",
  "entries": [
    {"key": "Environment", "state": "nonempty"},
    {"key": "Owner", "state": "missing"},
    {"key": "Project", "state": "unknown"}
  ]
}
```

All retained keys come from trusted startup configuration, never from enumerating
the plan's key names. Configuration is not sensitive tag evidence; it may enter
OPA and a validated finding path, but still stays out of logs/reprs. Revalidate
injected snapshots/engine graphs before serialization and OPA. Reject state/
payload mismatches, unrecognized states/sources, raw values, wrong configuration,
ineligible projections and unselected-policy data with existing safe errors.

Only project the selected policies. RDS/SSH-only calls must not inspect tag maps
or consume tag work limits. TAG-only calls build no RDS associations or SSH
observations; retain the existing unavailable RDS placeholder. Keep shared roots,
async worker boundaries, independent evaluation admission and cancellation cleanup.

Bound tag work at **50,000 required-key slots per plan**, independent of the
50-key configuration ceiling. Each eligible TAG resource consumes the configured
key count, including withheld/absent maps; count before reading/projecting its
map. Exact limit succeeds if other budgets allow; overflow returns existing
`PLAN_LIMIT_EXCEEDED` before OPA. Revalidate this work bound on injected input.
Index relevant masks once per resource; do not rescan the entire mask set for
each key or scan every resource/tag for every lookup. Keep work linear in mask
nodes plus checked key slots. Existing file/depth/resource/OPA input/output/time/
report limits remain unchanged and may reject smaller plans. Do not truncate.

## Rego decisions and deterministic aggregation

Add packaged production `rego/tags.rego` with a fixed TAG dispatch arm alongside
RDS/SSH. Use OPA 1.21.2 and the **existing capabilities file unchanged**; state
comparison and iteration need no additional built-ins. Keep network/runtime/
remote-schema denial, fixed query/paths, stripped child environment and bounded
process cleanup. Evaluate every selected resource/policy pair in **one OPA call**.

After existing data/deletion/provider/type exclusions:

1. A selected missing/null map fails: it has no required values.
2. A known map fails if any required key is `missing`, `blank` or `null`, even
   when another required key is uncertain or invalid. Choose the first failing
   key in sorted configuration order. Missing maps use a map-level path instead.
3. Without a proved failure, a known map is indeterminate if any required key is
   `sensitive`, `unknown` or `invalid_type`. Choose state priority in that order,
   then the first key in configuration order within that state.
4. A known map passes only when every required key is `nonempty`.
5. Other whole-map/root states are indeterminate. No missing/undefined policy
   result or empty/invalid configuration can establish a vacuous pass.

Return **one check per resource/TAG pair**. Multiple bad tags yield one finding
pointing to the deterministic selected key; this increment does not enumerate
every bad key in one response. No value is echoed. A known map with only an
invalid-typed required value is indeterminate, whereas known null/blank/absence
is a violation. This preserves malformed-input uncertainty without hiding a
separate proved missing/empty-tag failure.

## Catalog, reason codes and safe paths

Activate exactly these IDs in lexicographic order: AWS-RDS-001 v1.1.0 (high),
AWS-SG-001 v1.0.0 (high), AWS-TAG-001 v1.0.0 (**medium**). Keep existing per-ID
metadata/reason sets unchanged. TAG required paths are `[["tags_all"], ["tags"]]`.
Its title is `Mandatory resource tags`; description/scope explain defaults,
startup overrides, fallback, supported types and observed-plan limitations.

Extend strict metadata contracts per ID, not through permissive global unions:
TAG has five supported types, medium severity and
`required_configuration: ["required_tag_keys"]`; RDS/SSH keep their exact three
types, high severity and empty configuration requirements. Here the TAG entry
names the setting the evaluator consumes; startup defaults satisfy it without
explicit flags. Listing must explain that distinction, list the default names
in static metadata, and never expose this server's configured override values.
Listing still takes `{}`, needs no plan/OPA and reads only packaged metadata.

Update metadata, listing, scope and finding severity/type constraints together
(`policy_definitions.py`, catalog/listing/evaluation models and reporting). A
valid severity/type from another policy must not satisfy TAG's per-ID contract,
nor may TAG's medium severity broaden an RDS/SSH contract. Preserve old explicit
selection report fields and fixed explanations; only default combined reports
gain the new policy/checks after activation.

TAG has exactly **28 reason templates**: the three existing shared exclusion
reasons, four unresolved reasons (`TAG_SENSITIVE`, `TAG_UNKNOWN`, `TAG_UNVERIFIED`,
`TAG_UNAVAILABLE`), and these source-specific families:

| Suffix | Outcome | Catalog base path / validated check path |
| --- | --- | --- |
| `COMPLIANT` | pass | Map prefix / exact same prefix. |
| `KEY_MISSING` | fail | Map prefix / prefix plus selected configured key. |
| `KEY_EMPTY` | fail (`blank` or `null`) | Map prefix / prefix plus selected configured key. |
| `KEY_SENSITIVE` | indeterminate | Map prefix / prefix plus selected configured key. |
| `KEY_UNKNOWN` | indeterminate | Map prefix / prefix plus selected configured key. |
| `KEY_INVALID_TYPE` | indeterminate | Map prefix / prefix plus selected configured key. |
| `MAP_NULL` | fail | Map prefix / exact same prefix. |
| `MAP_SENSITIVE` | indeterminate | Map prefix / exact same prefix. |
| `MAP_UNKNOWN` | indeterminate | Map prefix / exact same prefix. |
| `MAP_INVALID_TYPE` | indeterminate | Map prefix / exact same prefix. |

Apply every table suffix to `TAG_ALL_` (prefix `["tags_all"]`) and
`TAG_RESOURCE_` (prefix `["tags"]`). Add `TAG_RESOURCE_MAP_MISSING`, fail, with
path `["tags"]`. There is no `TAG_ALL_MAP_MISSING`. Shared exclusions and four
unresolved reasons have exact root path `[]`. Thus 20 + 1 + 4 + 3 = 28 TAG
templates; the global unique reason set becomes **81** (56 existing plus 25 new).

This deliberately extends the existing fixed-path contract **only for TAG key
reasons**. Catalog templates retain a fixed map base path and static prose.
OPA may append exactly one configured key for key reasons. The engine validates
the complete batch, source/base, path length, exact configured key membership,
matching projected key state and reason/key applicability before
trusting output. Reject plan-derived/unconfigured keys, extra indices/segments,
wrong fields, cross-policy reasons/outcomes and malformed/omitted/duplicate checks.
Do not generally permit arbitrary descendant paths or reimplement aggregation
as a Python policy evaluator. Structural reason/state guards complement real
Rego tests; Rego remains the decision engine.

For TAG key reasons only, reporting copies that already-validated check path,
rather than discarding it for the catalog base. Other policies/map/root reasons
keep exact catalog paths. Fixed messages identify the problem without string
interpolation, for example `A configured required tag is missing.` with
`["tags_all", "Owner"]`. Remediation says to set a nonblank value for the tag
identified by that path. Invalid values/keys never enter explanations or errors.
The report does not expose an additional configuration field or every failing
key; operators retain their startup configuration for reproducibility.

## Tool selection, counts and error behavior

Tool names/arguments are unchanged. Omission selects all three enabled policies
after activation. Explicit one/two/three-ID selections are sorted; null, empty,
duplicate, unknown, nonstring and more-than-three selections fail with fixed
`INVALID_POLICY_SELECTION` before plan access. TAG settings are server-owned;
an MCP `required_tag_keys` argument remains invalid. No client root or plan field
can override them. Share the compiled ID allowlist and verify it against the
catalog without import-time/event-loop asset reads.

Resource buckets count the union of the selected types once. Expected checks
remain observed resources multiplied by selected policies, including exclusions.
S3 becomes a candidate when TAG is selected solely because tagging is supported.
No tag propagation to RDS members or security-group rules occurs. For a complete
synthetic plan containing one encrypted RDS instance, one open inline SSH group
and one S3 bucket, let all three have complete known nonblank required tags:

| Selection | Resources | Candidates | Unsupported | Checks | Pass | Fail | N/A |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RDS only | 3 | 1 | 2 | 3 | 1 | 0 | 2 |
| SSH only | 3 | 1 | 2 | 3 | 0 | 1 | 2 |
| TAG only | 3 | 3 | 0 | 3 | 3 | 0 | 0 |
| RDS + SSH | 3 | 2 | 1 | 6 | 1 | 1 | 4 |
| All three | 3 | 3 | 0 | 9 | 4 | 1 | 4 |

Known failure takes precedence over indeterminate compliance; partial plan
coverage cannot establish an overall pass. Empty/deleted/unsupported-only scopes
remain not applicable under existing semantics. Engine failures stay atomic:
zero trusted checks/findings across all selected policies. Missing OPA still
does not disable analysis or listing. No new error code or raised byte/time
budget is needed. Existing one/two-policy counts and public analysis goldens
remain unchanged under explicit old-policy selection.

## Examples and manual testing

Create synthetic fixtures only during implementation: `tags_compliant.json`,
`tags_missing_owner.json`, `tags_empty_project.json`, `tags_unknown_owner.json`,
`tags_provider_defaults.json`, `tags_custom_keys.json` and
`mixed_rds_ssh_tags.json`. Cover explicit `tags_all`, fallback and provider-default
observations without claiming the fixtures were generated by Terraform. Add
illustrative HCL under `examples/terraform/tags/`; do not run it. Save actual
SDK stdio reports only after execution, documenting explicit policy selections.
Do not overwrite existing mixed-plan fixtures just to make new defaults pass.

Calls using the implemented synthetic fixtures:

```json
{"plan_path": "tags_missing_owner.json", "policy_ids": ["AWS-TAG-001"]}
```

Expect one TAG finding for the resource with reason `TAG_ALL_KEY_MISSING`, path
`["tags_all", "Owner"]`, and no tag values. The unknown-owner fixture is
indeterminate, not a missing-tag failure. The provider-default fixture passes
with complete `tags_all` even if resource-only `tags` omits the defaults.

```json
{"plan_path": "mixed_rds_ssh_tags.json"}
```

Expect the nine-check accounting example. Then select RDS + SSH explicitly to
reproduce the six-check baseline. Test a server launched with all four required
keys against a fixture lacking `CostCenter`; changing a tool argument must not
relax the requirement. Publish a walkthrough with exact default/override
commands, saved reports, uncertainty/fallback limitations and four live host
prompts (listing, default TAG failure, unknown TAG, combined selection).
Separate fresh automated stdio traces from observed/user-reported Codex calls;
an older process may need reloading, but it does not block drafting.

## Acceptance criteria

These are acceptance criteria; [the acceptance record](../tags-acceptance.md)
maps them to executed evidence and outstanding platform/host observations. Use fake identifiers and secret
sentinels; require neither AWS credentials nor Terraform. Pure tests need no OPA.
Real Rego/service/stdio tests require the pinned binary and cannot be skipped as
a substitute for verification.

| Case | Required coverage |
| --- | --- |
| TG-01 | Exact five-type/canonical-provider scope, nested/indexed addresses, data/deletion/other-provider/unsupported exclusions; members/rules/nested blocks are not silently taggable. |
| TG-02 | Defaults exactly Environment/Owner/Project; explicit override replaces, order canonicalizes, case-sensitive distinct keys work, duplicates reject and no mutable-default/request cross-talk occurs. |
| TG-03 | Configuration exact/over 50-key and 128-character bounds, invalid types/Unicode/whitespace/reserved prefixes and CLI missing values/abbreviations yield fixed startup errors without values/field leaks or root/OPA access. |
| TG-04 | Each key present/nonblank passes; empty/whitespace/null and missing keys fail; case mismatch does not satisfy a key; nonblank Unicode and string zero/false pass; numeric/bool/object/array required values are indeterminate without coercion. |
| TG-05 | Known tags_all, provider-default observations, resource override observations, conflicting/empty/null tags_all, fallback-only tags and both maps absent have the specified authoritative-source outcomes. No HCL/env merge or AWS lookup occurs. |
| TG-06 | Unknown/sensitive/null placeholders and descendant masks on absent tags_all never trigger fallback; unknown metadata absence is unverified; raw missing/null after never falls back to inventory/before. |
| TG-07 | Root/map/key/descendant and malformed integer mask paths, source-mask union, cross-copy sensitivity, unrelated-key masks, exact key matching and hidden duplicate values preserve privacy/uncertainty. Known sibling map keys remain independently usable. |
| TG-08 | Several violations select first failing key; fail beats uncertain/invalid siblings; no fail selects sensitive then unknown then invalid type, with lexicographic tie breaking; all-withheld maps never pass. |
| TG-09 | Both replacement orders/create/update/no-op, inventory-only, deletion and conflicting change/inventory payloads use existing authoritative desired-source semantics and coverage warnings. |
| TG-10 | Strict schema 4/config/projection variants reject old schemas, extra raw values, missing/duplicate/foreign keys, wrong source/state/order/cardinality, empty config, ineligible projections and unselected data; selected RDS/SSH graph validation remains effective. |
| TG-11 | Exactly three listed/evaluable IDs, exact per-ID versions/types/severity/config requirements/reason sets, sorted metadata and unchanged empty listing input. Cross-ID mixtures, corrupt/incomplete catalog and invalid path bases fail safely; listing needs no OPA/plan access. |
| TG-12 | All selection subsets/orders/default, malformed/null/duplicate/unknown/oversized selections and attempted config overrides through tool input have fixed errors before file access; schemas still expose three read-only tools. |
| TG-13 | All five accounting rows, candidate union across overlapping types, one TAG check/finding despite several bad keys, N/A cross-pairs and exactly one real OPA invocation match expected counts. |
| TG-14 | Dynamic TAG paths name only a configured key under the selected field; exact map/root paths and old-policy paths remain enforced. Reject unconfigured plan-derived key names, wrong states/bases/extra segments/indices, cross-policy codes and missing/duplicate checks atomically. |
| TG-15 | Pure TAG projections/reprs, captured real OPA input and both SDK output channels/logs contain no required/unrequired sensitive or unmarked tag values, tag-map keys outside config, full maps, validation input or subprocess stderr. Shared internal mask paths never reach OPA/public channels. Fixed explanations are unchanged by hostile plan strings. |
| TG-16 | Explicit RDS/SSH-only calls never invoke TAG parsing/work checks; TAG-only never constructs RDS/SSH projections; old reports and analysis golden match under explicit selection. Shared adapter settings are not mutated. |
| TG-17 | Fixed key-slot limit exactly/over, injected overflow, large maps/mask sets, ignored unrequired values and existing byte/depth/resource/runtime/admission/cancellation bounds run off the event loop; overflow precedes OPA and reports are never truncated. |
| TG-18 | Real OPA strict/format/test, runner/service truth table and combined dispatch pass using unchanged restricted capabilities. Network/runtime/schema-fetch/environment denial, timeout/overflow/terminate/reap regressions remain effective. |
| TG-19 | Missing/incompatible OPA, undefined/invalid output and malformed TAG batches remain errors with zero trusted RDS/SSH/TAG findings. Empty/partial/deleted/unsupported scopes preserve existing execution/compliance semantics. |
| TG-20 | SDK memory/stdio × auto/legacy exercise matching text/structured success/error outputs, default/custom startup settings, dynamic safe paths and independent analysis/listing without OPA. Required local socket fixture is executed, not skipped. |
| TG-21 | Seven synthetic fixtures, illustrative HCL, real saved reports, exact client/server override commands and walkthrough/acceptance documentation agree; automated/live host evidence and platform limitations are distinguished. |
| TG-22 | Source/wheel assets and fresh isolated installed auto/legacy stdio outside checkout support three policies and custom startup keys; no test Rego, OPA binary, future adapter or new dependency enters the wheel. Full and documented OPA-free checks are recorded accurately. |

## Small implementation tasks

The user authorized implementation and M3a–M3e are implemented. The table
preserves the independently testable sequence, including prospective assets
before activation. No additional approval gate is implied
between authorized tasks. Keep prospective assets test-only until activation.

| Task | Depends on | Deliverable and verification |
| --- | --- | --- |
| M3a: Contracts/configuration | Reviewed spec and implementation authorization | Strict required-key settings, pure TAG variants/schema 4 and prospective per-ID/path contracts. TG-02–TG-03/TG-10–TG-12 pure tests; production catalog/defaults remain two-policy. |
| M3b: Masked projection | M3a | Source selection, cross-copy sensitivity, required-key observations and incremental mask/work bounds. TG-01/TG-04–TG-10/TG-15–TG-17 without OPA/AWS. |
| M3c: Rego and path validation | M3b | Real TAG aggregation, prospective three-policy dispatcher/catalog, bounded dynamic-path validation and report rendering. TG-04–TG-08/TG-13–TG-15/TG-18–TG-19 through actual restricted OPA. |
| M3d: Activate and expose | M3c | Atomically wire schema/projection/assets/selection/medium metadata, safe startup flag and example-client forwarding. TG-11–TG-20 across SDK modes; old explicit-selection regressions pass. |
| M3e: Examples and acceptance | M3d | Seven fixture/report pairs, illustrative HCL, walkthrough, TG-01–TG-22 evidence and current status. Full Python/Rego/Ruff/lock/dependency/source/wheel/installed checks; record live host observations separately. |

Write comments/docstrings with each implementation task. Keep `uv.lock`, Python
3.14+, MCP SDK 2.3.0, OPA 1.21.2 and the documented non-editable workflow.
Update the OPA-free test selection when new real-evaluation modules are added.
Drafting used documentation consistency and diff checks. Implementation now
has real runtime/distribution evidence in the acceptance record. Do not add
AWS connectivity, S3 protection, CI, Docker, future capabilities or remote changes.

## Official references and interpretation

Consulted 2026-10-22. Provider/format facts inform this design; supported scope,
fallback/null rules, key syntax/defaults, privacy observations, deterministic
selection and work ceilings are explicit project choices for review.

- [HashiCorp AWS resource tagging](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/guides/resource-tagging.html.markdown): taggable resources, provider defaults and ignored/external tag limitations.
- [AWS provider configuration](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/index.html.markdown#default_tags-configuration-block): default tags and ignore-tags behavior; M3 does not read provider credentials, configuration or environment variables.
- Resource support: [EC2 instance](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/instance.html.markdown), [security group](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/security_group.html.markdown), [DB instance](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/db_instance.html.markdown), [RDS cluster](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/rds_cluster.html.markdown), [S3 bucket](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/s3_bucket.html.markdown): the five types expose top-level tags/tags_all; nested resources are separate scope.
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format): desired values and separate unknown/sensitive metadata; values alone cannot establish known absence.
- [OPA capabilities](https://www.openpolicyagent.org/docs/operations#capabilities) and [policy testing](https://www.openpolicyagent.org/docs/policy-testing): preserve restricted capabilities and require actual Rego execution, not a Python replacement.
- [Official MCP Python SDK 2.3.0 low-level server](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/advanced/low-level-server.md): retain explicit schemas/validation, matching structured/text content and stdio. No SDK migration or new tool is proposed.
