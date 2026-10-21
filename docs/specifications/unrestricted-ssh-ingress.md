# Specification 005: unrestricted SSH ingress

Status: approved and implemented on 2026-10-21; M2a–M2e have automated evidence
in [the acceptance record](../ssh-acceptance.md). Live Codex reload verification
is recorded separately.
Updated: 2026-10-21.

This specification defines M2 in the [implementation plan](../implementation-plan.md).
It adds the second governance policy to the existing three-tool server, following
the analysis, evaluation, listing and expanded RDS increments. The user reviewed and approved this specification for implementation, and reported
that the MCP worked in their hands-on test. Another
familiarization session is not a prerequisite for drafting or reviewing M2.

This increment activates **AWS-RDS-001 v1.1.0 and AWS-SG-001 v1.0.0** after
staged implementation and verification. Python 3.14+, MCP SDK 2.3.0, OPA 1.21.2,
stdio, uv, Pydantic, pytest and Ruff remain the supported stack. No dependencies
were added and no remote publication occurred.

## Outcome and boundaries

Add **AWS-SG-001 v1.0.0**, high severity: detect an observed desired ingress rule
that allows direct TCP port 22 from an individual world-wide IPv4 or IPv6 CIDR.
The policy also catches all-protocol permissions. It checks these canonical
`registry.terraform.io/hashicorp/aws` resource representations:

| Resource | Consumed desired structure | Scope |
| --- | --- | --- |
| `aws_security_group` | `ingress` array of rule objects | Aggregate the observed inline ingress rules into one resource check. |
| `aws_security_group_rule` | `type`, `protocol`, ports and source fields | Check known `type: "ingress"`; known `egress` is not applicable. |
| `aws_vpc_security_group_ingress_rule` | `ip_protocol`, ports and source fields | Ingress is established by the resource type. |

All existing managed desired actions are supported, including both replacement
orders and no-op. Data sources, pure deletions and other provider/type pairs
receive explicit not-applicable checks. `aws_vpc_security_group_egress_rule`,
default security group resources and other representations are not added to the
policy's supported-type list.

The same `analyze_terraform_plan`, `evaluate_terraform_policies` and
`list_policies` tools remain. No new transport, tool, operator setting, policy
configuration, third-party dependency or external service is introduced.
RDS encryption and association outcomes remain unchanged when selecting RDS alone.

This is a bounded plan policy, not a determination of effective reachability.
Do not inspect AWS, execute Terraform, fetch prefix lists, follow security-group
references, join rule resources to group resources, or infer routes, listeners,
network ACLs, account defaults, provider aliases or deployed state. Do not combine
multiple narrower CIDRs into a world-wide range. For example, two `/1` entries
are outside this first policy's aggregate-coverage analysis. A nonzero prefix is
not a claim that its addresses are private or trusted. Other administrative ports,
CIDR allowlists, bastion requirements, tags, S3, Docker and CI remain later work.

## Required attributes and normalization

Use the authoritative change `after` after exact-address source merging. Missing
or null `after` never falls back to `before` or planned inventory. Inventory-only
resources and omitted unknown metadata remain unverified. Retain generic
identities/actions and existing mask semantics. Analysis still discards all values
and never constructs the SSH projection.

Resource-specific field mapping:

| Concept | Inline rule | Legacy standalone | Modern standalone |
| --- | --- | --- | --- |
| Direction | Ingress by collection | `type` | Ingress by resource type |
| Protocol | `protocol` | `protocol` | `ip_protocol` |
| Port range | `from_port`, `to_port` | Same | Same |
| IPv4 sources | `cidr_blocks` array | Same | `cidr_ipv4` scalar |
| IPv6 sources | `ipv6_cidr_blocks` array | Same | `cidr_ipv6` scalar |
| Prefix-list presence | `prefix_list_ids` | Same | `prefix_list_id` |
| Group-reference presence | `security_groups`, `self` | `source_security_group_id`, `self` | `referenced_security_group_id` |

Do not consume group target IDs, names, descriptions, tags, ARNs, account/Region,
egress blocks or other attributes for this policy. A rule can be checked without
its containing security group being present in the same plan. Resource addresses
and module/index metadata stay opaque; they never substitute for rule fields.

After proving a legacy rule is egress, skip port/source parsing and carry a
value-free unavailable rule placeholder with its known direction. This supplies
the required single entry without spending source work on an excluded rule.

### Protocol and port parsing

Only known strings are protocol inputs. Map exact lowercase AWS protocol names
`tcp`, `udp`, `icmp`, `icmpv6` to numbers 6, 17, 1, 58. Accept canonical decimal
strings `"0"` through `"255"` and `"-1"`. The documented legacy
`aws_security_group_rule.protocol: "all"` alias maps to -1; inline and modern
`"all"` remain invalid. Reject numeric JSON values, booleans, whitespace, mixed
case, leading-zero numbers and unrecognized names rather than guessing.

Known TCP endpoints must be strict integers, each 0–65,535, with
`from_port <= to_port`. A string, boolean, reversed range or out-of-range value
is invalid. Missing/null endpoints remain distinct uncertain states. Do not
invent port defaults. Protocol -1 includes every port regardless of omitted,
masked or unusual endpoints; known non-TCP protocols do not establish direct
TCP SSH exposure. ICMP type/code values are not interpreted as TCP ports.

These are parsing/representation rules. Python must not compute the policy's
port-22 inclusion predicate or the final compliance result.

### Source parsing and scope

For each known unmasked CIDR, use Python's standard-library `ipaddress` parser
with host-bit normalization (`strict=False`). Require a bounded nonblank string
with one slash and an ASCII decimal prefix length in the appropriate family
range. Reject zones, whitespace, address-only inputs, dotted netmasks, incorrect
families and malformed values. Do not use `is_private` or `is_global`.

Discard the address itself immediately after validation. Retain only the family
(4 or 6) and prefix length (0–32 or 0–128). Rego decides whether prefix length 0
is world-wide. This handles alternate valid IPv6 spellings and noncanonical host
bits safely, rather than relying on literal string equality with `::/0` or
`0.0.0.0/0`. No raw CIDR, normalized network address, source-group ID or prefix-list
ID may enter the snapshot, OPA, a repr, public output or logs.

Optional source fields that are missing/null/explicitly empty represent
`absent` only when desired-state unknown metadata is complete and no overlapping
mask applies. This is an explicit optional-field rule, not a fallback for unknown
data. Marked unknown/sensitive optional fields are never treated as absent.
Nonempty group/prefix references must be known bounded valid identity strings;
retain presence states only, not their contents. `self` retains a known boolean
or an absence/uncertainty state.

Known self/group references do not themselves mean internet-wide access.
Unknown CIDR fields still block proving that no world CIDR exists. Prefix-list
contents are outside scope: a present prefix list keeps a potentially relevant
SSH check indeterminate unless another known source proves a violation. A known
non-SSH protocol/port can independently establish a pass without resolving that
list. No source configured at all is indeterminate for a potentially relevant
rule; do not infer a valid private source or a no-op provider behavior.

Do not reproduce all provider mutual-exclusion validation. For this policy,
an independently known world CIDR remains exposure evidence even if an additional
source is unknown or malformed. Uncertain/malformed entries cannot erase a known
violation, and cannot provide evidence of a safe source.

## Uncertainty and collection safety

Use strict known-value/uncertain-state variants. Uncertain variants carry no
provider value. Required observations distinguish `sensitive`, `unknown`,
`unverified`, `unavailable`, `missing`, `null` and `invalid_type`. Sensitivity
precedes unknown masks, incomplete unknown metadata, absent desired state and
ordinary value observations. Whole-resource and ancestor masks cover descendants;
a descendant mask on an expected scalar also blocks reading that scalar.
Masks on irrelevant fields such as descriptions/tags do not block a rule check.

`aws_security_group.ingress` is an unordered provider collection, even though
plan JSON encodes it as an array. Never align change and inventory elements by
array index, address, description or provider ID. Conservatively promote any
consumed sensitive mask under `ingress` from either source to sensitivity of the
entire inline ingress collection. This can make a group indeterminate despite an
apparently known sibling rule: the collection is withheld before witness
evaluation. Explain this deliberate privacy/coverage tradeoff in the walkthrough.
Unrelated ingress description masks do not require this promotion.

Unknown masks originate from the authoritative change and can retain their
documented after-array positions. Any unknown index or collection portion not
represented by a usable after value must survive as uncertainty; never zip masks
and values to their shorter length. Missing/ambiguous collection shape becomes
an uncertain collection, not an empty array. A usable known sibling rule can
still prove a violation when other rules are unknown.

Treat CIDR arrays conservatively too: a sensitive mask on a consumed array or
element hides that whole family array before parsing, avoiding cross-source
ordering assumptions. An independently known world CIDR in the other family can
still establish a violation. Unknown change masks may preserve known sibling
CIDRs, but unknown tails, masked scalar descendants and conflicting shapes must
not be dropped. Reference collections retain presence/uncertainty only, so
their order is immaterial. M2 does not add a Terraform set-element matcher.

An explicit known empty inline ingress array is a pass within the observed
inline scope. Missing, null, invalid, wholly unknown or sensitive ingress is
indeterminate. A standalone rule collection elsewhere in the plan does not fill
an unavailable inline array or duplicate its rules into the group check.

## Rego decision rules

Keep compliance in real Rego. Define the predicates below over the sanitized
projection with three logical states: proved true, proved false, unresolved.

1. Apply data-source, deletion and unsupported-provider/type exclusions first.
2. For legacy resources, known egress is not applicable. Missing, masked or
   invalid direction is indeterminate before assessing the rule. Modern resources
   and inline blocks have direction fixed by their representation.
3. `allows_ssh` is true for protocol -1, or protocol 6 with a known valid range
   containing 22. It is false for a known non-TCP protocol or known TCP range
   excluding 22. Otherwise it is unresolved.
4. `world_source` is true when any independently known IPv4/IPv6 source has prefix
   length 0. It is false only when all consumed CIDR source fields are known
   absent/nonzero-prefix, prefix-list presence is known absent, and at least one
   valid source exists (CIDR, self or group reference). Otherwise it is unresolved.
5. A rule fails when both predicates are true. It passes when either predicate
   is proved false, even if the other is unresolved. Otherwise it is indeterminate.

For an inline group, fail if any usable rule fails; otherwise indeterminate if
the collection or any rule is unresolved; otherwise pass. A whole-collection
mask prevents any rule from being usable. Empty known arrays pass as described
above. This is evaluation of direct observed permissions, not a general network
reachability claim or full Terraform schema validator.

| Example | Result |
| --- | --- |
| TCP 22–22 with IPv4 or IPv6 prefix 0 | fail |
| TCP 20–23 with a world CIDR | fail |
| Protocol -1 with a world CIDR and omitted ports | fail |
| TCP 443–443 with world CIDR | pass |
| Known UDP 22–22 with world CIDR | pass |
| TCP 22 with only known nonzero-prefix CIDRs or a group/self reference | pass |
| TCP 22 with prefix-list presence and no known world CIDR | indeterminate |
| Unknown protocol and a known world CIDR | indeterminate |
| Unknown protocol with a complete known non-world source set | pass |
| One proved violating inline rule plus an unknown rule | fail |
| Known nonviolating rules plus an unresolved rule | indeterminate |
| Wholly sensitive consumed inline collection | indeterminate |

## Internal contracts and architecture

Add a small pure `ssh_projection.py` and strict SSH-specific contracts, for
example `ssh_models.py`, without MCP imports. Extend the existing evaluation-only
adapter pass after source merging. Keep `rds_associations.py` and RDS projections
separate and unchanged in meaning. Do not introduce a general plugin registry,
dynamic policy imports, provider SDK or expression evaluator.

Add an optional `ssh_state` to internal `NormalizedResource` and
`ProjectedResource`, hidden from reprs. Eligible network resources must carry
the correct representation when SSH is selected; unrelated/deleted/data/
wrong-provider resources and requests without SSH carry no SSH projection. Inline
collections allow zero or more entries; legacy/modern projections require exactly
one rule entry, and their direction states must agree with the representation.
The public `ResourceAnalysis`/`PlanAnalysis` stay unchanged.

Resolve selection before normalization and pass it into the per-call projection
path. Do not mutate shared adapter configuration between requests. RDS-only
requests must neither parse SSH attributes nor apply SSH work ceilings; SSH-only
requests must not build RDS associations. Retain the current unavailable RDS
placeholder for resources outside the selected RDS projection. In schema 3,
enforce RDS-specific graph scope only when RDS is selected; otherwise require
those placeholders and no resolved RDS links. This preserves RDS-only behavior
and prevents unselected policy data/limits from affecting another policy.

Use internal **EvaluationInput schema 3** to make the additional projection and
two-policy dispatch explicit. Rego rejects schemas 1/2; engine output, public
analysis/evaluation/listing reports and catalog envelopes remain schema 1. Keep
RDS graph eligibility validation when that policy is selected. Unknown states,
extra fields, values attached to uncertain variants, wrong representation/type
pairs and malformed numeric payloads must be rejected before OPA. Enforce CIDR
family/prefix bounds against the containing source family. Revalidate
mutable/injected inputs too.

The normalized SSH structure must contain only:

- Representation `inline`, `legacy` or `modern`; a direction state; and a strict
  rule-collection union (`known` with items, or an uncertain state with no items).
- Each rule is either an uncertain state with no payload, or `known` with a
  protocol state, port-range state and source observations.
- A known protocol carries only its numeric value (-1 or 0–255); a known port
  range carries only two validated integers. Uncertain variants carry neither.
- IPv4/IPv6 arrays carry known family/prefix-length pairs or value-free uncertain
  entries; optional arrays can be `absent`. Modern scalar CIDRs normalize into
  this same per-family collection shape. Unknown collection portions must remain
  represented or conservatively make the collection uncertain.
- Prefix-list/group-reference states carry only `present`, `absent` or one of
  the seven uncertainty states. Self-reference observations carry a boolean only
  when known. Source membership strings never survive parsing.

No Python projection field may contain `allows_ssh`, `world_source`, `compliant`,
an outcome or a precomputed Rego reason. Protocol numbers, ports and prefix
lengths are a new explicit engine-input allowlist, not new public evidence.
The internal representation must retain enough uncertainty to implement the
truth table without treating an undefined expression as a negative observation.

The fixed Rego entrypoint `data.cloud_governance.report` dispatches by exact
selected policy ID to the RDS or SSH rule. Evaluate all selected pairs in **one
OPA invocation**. An unknown policy, undefined reason, missing/duplicate check,
inapplicable reason family, wrong outcome/path or invalid output is an atomic
evaluation error, not a partial success or pass.

For SSH port comparisons, propose adding only the deterministic **`lte`** built-in
to the existing capabilities allowlist. Extract its supported declaration from
OPA 1.21.2 during implementation. Equality, comprehensions and fixed reason
priority avoid requiring CIDR/network built-ins, count/min/sort, regex or string
conversion inside OPA. Keep `allow_net: []`, restricted child environment, fixed
executable/query/assets and all network/runtime/schema-fetch denial tests. Any
further capability needs a demonstrated use and updated acceptance evidence.

### Work and size budgets

Keep existing file/depth/resource, OPA input/output/runtime, public-response and
admission limits. No default byte budget is increased and no response is
truncated. Run network projection and all validation/serialization off-loop.

Introduce fixed evaluation-only ceilings of **10,000 projected SSH rules per
plan** and **50,000 consumed source entries per plan**, shared across resources.
Each standalone rule and each inline entry/uncertain placeholder consumes a rule
slot. CIDR/reference entries, their unknown-mask slots and scalar source slots
consume source work before allocation/parsing; do not duplicate mask/value slots
or expand unknown arrays speculatively. Wholly withheld collections consume no
payload allocations. Check bounds incrementally and return existing fixed
`PLAN_LIMIT_EXCEEDED` before OPA when exceeded. Analysis does not apply these
evaluation-only ceilings. Existing OPA input limits can reject a projected plan
even below these work ceilings.

Normalization and Rego aggregation must avoid rule-pair scans. Use linear passes
over resources/rules/source entries plus the existing bounded RDS indexes and a
fixed two-policy dispatch. Retain one independent evaluation admission slot, no
queue, shielded worker cleanup and termination/reaping on subprocess cancellation.

## Two-policy catalog and selection

Publish exactly two enabled bundled entries only at activation:

| ID | Version | Severity | Types |
| --- | --- | --- | --- |
| AWS-RDS-001 | 1.1.0 | high | Existing three RDS types, existing 35 reasons and requirements. |
| AWS-SG-001 | 1.0.0 | high | The three network types above; no policy-specific configuration. |

SSH metadata: title **Unrestricted SSH ingress**; description **Detect observed
ingress rules permitting direct TCP SSH from an individual world-wide IPv4 or
IPv6 CIDR.** Its scope description must state the observed-inline/rule scope,
prefix-list uncertainty, no live reachability analysis and no CIDR-union analysis.
Its `required_configuration` is explicitly `[]`. Its ordered `required_paths`
are the union across supported representations, not a claim that every resource
needs every field:

```json
[
  ["ingress"], ["type"], ["protocol"], ["ip_protocol"],
  ["from_port"], ["to_port"], ["cidr_blocks"], ["ipv6_cidr_blocks"],
  ["cidr_ipv4"], ["cidr_ipv6"], ["prefix_list_ids"], ["prefix_list_id"],
  ["self"], ["security_groups"], ["source_security_group_id"],
  ["referenced_security_group_id"]
]
```

Replace single-policy Literal/list-size assumptions with strict **per-ID**
metadata contracts and a small fixed implemented-ID allowlist. Validate version,
provider/type lists, configuration, paths and exact reason membership/semantics
for each ID. Never validate reasons only by total count or accept an RDS reason
for an SSH check because it exists in the global enum. Do not make arbitrary
catalog entries or user-supplied Rego selectable.

`list_policies()` returns both public projections in policy-ID order, with its
existing 65,536-byte cap and independent service lifecycle. It still reads no
plan and probes no OPA. Missing/corrupt either policy asset invalidates the
catalog; it cannot silently list a reduced policy set as success.

`evaluate_terraform_policies(plan_path, policy_ids?)` keeps its argument names:

- Omission selects all enabled catalog IDs, sorted: RDS then SSH after activation.
- An explicit array accepts one or both exact IDs in either order; normalize
  valid selection order. Null, empty arrays, duplicates, more than two IDs,
  nonstrings and unknown IDs remain fixed `INVALID_POLICY_SELECTION` errors.
- Resolve and verify selection before file access. Input validation must not
  open catalog files on import or on the event loop. A shared compiled ID
  allowlist may supply the strict model's default, provided catalog validation
  proves that it equals the complete enabled set. Avoid independent hardcoded
  defaults in handlers, services and clients, or advertising nullable selection.
- A selection error never becomes an engine error report or empty success.

The changed omission default is intentional user-visible behavior. Document
`policy_ids: ["AWS-RDS-001"]` for an RDS-only comparison. Keep SDK auto/legacy,
read-only annotations, matching text/structured content and safe errors.

Tool calls using the implemented synthetic fixtures:

```json
{"plan_path": "mixed_rds_ssh.json"}
```

```json
{"plan_path": "mixed_rds_ssh.json", "policy_ids": ["AWS-SG-001"]}
```

```json
{"plan_path": "mixed_rds_ssh.json", "policy_ids": ["AWS-SG-001", "AWS-RDS-001"]}
```

The first and third select the same sorted pair. The existing example client's
repeatable `--policy-id` can supply either/both IDs; no new CLI flag is needed.

## Reasons, findings and accounting

Emit **one check per selected policy/resource pair**, including exclusions. An
inline group with several violating rules produces one SSH failed check and one
resource finding. Do not explode findings per CIDR/rule or join standalone rules
back into group findings. Such resources can describe related exposure; counts
are resource-policy checks, not independent root causes.

Retain the 35 RDS reasons unchanged. SSH has exactly **24** catalog templates:

| Codes | Outcome | Attribute path |
| --- | --- | --- |
| Existing common `DATA_SOURCE_SKIPPED`, `DELETED_RESOURCE_SKIPPED`, `RESOURCE_NOT_SUPPORTED` | not_applicable | `[]` |
| `SSH_EGRESS_SKIPPED` | not_applicable; legacy known egress only | `["type"]` |
| `SSH_INLINE_UNRESTRICTED_INGRESS`, `SSH_RULE_UNRESTRICTED_INGRESS` | fail | Inline `["ingress"]`; standalone `[]` |
| `SSH_INLINE_NO_UNRESTRICTED_INGRESS`, `SSH_RULE_NO_UNRESTRICTED_INGRESS` | pass within documented scope | Inline `["ingress"]`; standalone `[]` |
| `SSH_INLINE_{SENSITIVE,UNKNOWN,UNVERIFIED,UNAVAILABLE,MISSING,NULL,INVALID_TYPE,PREFIX_LIST_UNRESOLVED}` | indeterminate | `["ingress"]` |
| `SSH_RULE_{SENSITIVE,UNKNOWN,UNVERIFIED,UNAVAILABLE,MISSING,NULL,INVALID_TYPE,PREFIX_LIST_UNRESOLVED}` | indeterminate | `[]` |

Braces denote the exact eight expanded suffixes, not literal reason codes.
For unresolved checks, select the first **necessary unresolved observation** in
this fixed priority: sensitive, unknown, unverified, unavailable, missing, null,
invalid_type, prefix_list_unresolved. Ignore uncertainties made irrelevant by a
proved false predicate. A proved violation precedes unresolved sibling rules.
Rego must not rely on array iteration order to choose a reason.

A complete but empty source configuration maps to the missing-input reason;
invalid observations and unknown possible sources retain their own states rather
than being reclassified as empty. Known prefix-list presence with unresolved
contents uses the prefix-list reason when no higher-priority necessary
uncertainty remains.

Use fixed value-free explanations. Failure prose states that an observed rule
permits unrestricted SSH; remediation recommends restricting the source or
removing the permission. Pass prose is limited to this policy's observed scope.
Uncertainty prose states the corresponding fixed limitation. Do not interpolate
CIDRs, protocol/port values, reference IDs, descriptions, matching witnesses,
mask paths or candidate addresses. Inline findings use the whole ingress path;
they do not expose/rely on provider-set element ordering.

Preserve the public summary shape and disjoint resource buckets:

- `resources_observed` counts each normalized address once.
- Data sources and deletions are skipped first, as today.
- `candidate_resources` is the union of resources in **any selected policy's**
  supported provider/type scope, counted once. Direction/value uncertainty does
  not remove a candidate; a legacy egress resource can be a candidate but have a
  not-applicable SSH check.
- `unsupported_resources` counts resources supported by none of the selected
  policies after data/deletion exclusions.
- Expected checks = resources observed × selected policy count. Per-outcome
  counts are counts of checks, not resource buckets; opposite-policy checks can
  be not applicable for otherwise supported resources.

For a complete plan with one encrypted RDS resource, one world-open SSH rule and
one unsupported S3 bucket, selection accounting must be:

| Selection | Resources | Candidates | Unsupported | Expected/evaluated | Pass | Fail | N/A |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RDS only | 3 | 1 | 2 | 3 | 1 | 0 | 2 |
| SSH only | 3 | 1 | 2 | 3 | 0 | 1 | 2 |
| Both / omitted | 3 | 2 | 1 | 6 | 1 | 1 | 4 |

Both-policy compliance is fail here. Preserve fail-before-indeterminate status,
partial-plan warnings, empty/unsupported-only not-applicable semantics and atomic
engine failures. On any engine failure, all expected checks for both selected
policies are unevaluated; return no trusted findings from either policy.

## Acceptance cases

These are acceptance criteria; [the acceptance record](../ssh-acceptance.md) maps
them to executed evidence and outstanding host/platform observations. Use fake synthetic plans,
illustrative HCL without executing Terraform, real OPA tests and SDK subprocesses.

| ID | Required evidence |
| --- | --- |
| SG-01 | Exact canonical provider/type scope for all three representations; data/deletion/wrong-provider/type and legacy egress exclusions, including precedence. |
| SG-02 | IPv4 and IPv6 world CIDRs fail for TCP 22 and ranges containing 22 in each representation; numeric protocol string 6 and supported aliases work. |
| SG-03 | Protocol -1 and legacy all fail with world sources despite absent/irrelevant ports; inline/modern all, booleans/numeric JSON and malformed protocols do not become known TCP or safe non-TCP. |
| SG-04 | Known non-TCP and known non-SSH TCP ranges pass; strict port bounds/order reject coercions, booleans, strings and invalid ranges. Unknown required protocol/range stays unresolved. |
| SG-05 | Nonzero prefixes, self/group references and explicit empty ingress behave as specified. No configured source, absent/null/invalid ingress and unresolved prefix lists cannot silently pass a relevant rule. |
| SG-06 | CIDR family validation, expanded IPv6, host-bit normalization, malformed CIDRs, prefix bounds, zones and address-only/dotted-mask inputs follow the contract; raw addresses never survive. |
| SG-07 | Root, attribute, list-index and scalar-descendant sensitive/unknown masks precede parsing; incomplete unknown metadata and inventory-only resources remain unverified. Irrelevant masks do not block checks. |
| SG-08 | Reordered inventory/change inline sets and CIDR lists cannot leak sensitive values. Sensitive consumed collections are conservatively withheld; unknown tails/omitted values cannot be lost through zip/truncation. |
| SG-09 | Inline aggregation returns one check: multiple violations, known violation plus unknown, safe plus unknown and empty array. Necessary uncertainty priority is deterministic under rule/source permutations. |
| SG-10 | Short-circuit truth table: known safe source can exclude exposure with unknown protocol; non-SSH permission can pass with unknown sources; known world/SSH evidence survives unrelated unknown or invalid entries. |
| SG-11 | Authoritative after beats conflicting inventory; missing/null after and deletions never use before/inventory. Cover create/update/no-op/read, both replacement orders and inventory-only entries. |
| SG-12 | Nested/indexed/quoted-module addresses stay opaque. Separate rule resources need no group lookup; standalone/inline representations are not joined or deduplicated by raw group ID. |
| SG-13 | Snapshots/reprs, actual OPA stdin, logs, captured failures and both MCP channels exclude marked/unmarked CIDR, reference, description and secret sentinels. Only allowlisted numeric/presence observations enter OPA. |
| SG-14 | Input schema 3 and strict SSH variants reject old schemas, extra payload, known/uncertain mismatches, standalone rule-count/direction and representation/provider/type errors. Selected RDS graph rejection cases still pass; unselected projections require placeholders/no links. |
| SG-15 | Undefined/malformed/missing/duplicate/cross-policy checks and wrong reason/outcome/path produce atomic safe errors; no partial RDS result survives a broken SSH batch. |
| SG-16 | Omitted/explicit one/both/reversed selection works; null/empty/duplicate/unknown/nonstring/oversized selection fails before file I/O. No asset I/O occurs in input validation/imports. |
| SG-17 | Listing and evaluation agree on exactly two IDs, per-ID versions/types/reasons, sorted output and empty policy configuration; wrong versions/reasons and incomplete catalog assets are rejected. Listing still needs no OPA or plan access. |
| SG-18 | The three-resource accounting example matches all three selections. Multiple inline violations remain one check; candidate union and N/A cross-policy pairs do not double-count resources. |
| SG-19 | Empty, partial, unsupported-only, egress-only, data/deletion-only, mixed failure/uncertainty and engine-failure plans preserve complete expected-check and compliance semantics. |
| SG-20 | RDS-only outcomes, listing independence and byte-identical public analysis golden remain unchanged. Unselected SSH fields/ceilings cannot affect RDS-only requests, and SSH-only requests build no RDS associations. Default combined reports document their intentional additional checks. |
| SG-21 | SDK auto/legacy, in-memory and real stdio discover the same three tools with updated selection/output schemas, matching text/structured results and safe failures. |
| SG-22 | Real OPA strict check/format/test and runner/service integration exercise all representations and both-policy dispatch under restricted capabilities. lte is the only planned capability addition; denial/environment/timeout/overflow/reap tests remain effective. |
| SG-23 | Rule/source ceilings and byte budgets pass at/within boundaries and fail safely above them. Large synthetic graphs demonstrate bounded linear projection/aggregation; off-loop/admission/native/AnyIO cancellation regressions pass. |
| SG-24 | Synthetic fixtures, illustrative separate HCL examples and real saved reports cover SSH pass/fail/uncertainty plus both-policy selection. Updated hands-on Codex prompts have observed/user-reported evidence distinguished from automated traces. |
| SG-25 | Wheel/source inclusion and fresh installed auto/legacy stdio outside checkout work with two policies, no test Rego/OPA binary/future adapters in the wheel and no new dependency. Record tested platforms explicitly. |

## Small implementation tasks

The user approved implementation and M2a–M2e are implemented. The table preserves
the staged sequence and its checks, including the temporary prospective-assets
boundary before M2d. See the acceptance record for final evidence and the
separate pending live-host check.

| Task | Dependency | Deliverable and verification |
| --- | --- | --- |
| M2a: Define two-policy and SSH contracts | L1/M1; reviewed specification and implementation authorization | Strict SSH variants/schema 3, selection semantics, per-ID catalog contracts and prospective synthetic builders. SG-13–SG-18/SG-20 contract tests. Keep served coverage/defaults at RDS-only. |
| M2b: Project all three rule formats | M2a | Pure masked SSH projection, transient CIDR/reference parsing, conservative set-mask handling and incremental work limits. Verify SG-01–SG-13/SG-23 without OPA or AWS. |
| M2c: Implement and verify Rego | M2b | SSH truth table/aggregation, two-policy dispatcher and minimal lte capability. Use test-only prospective catalog/Rego until activation. Real OPA verifies SG-02–SG-10/SG-14–SG-15/SG-18–SG-19/SG-22. |
| M2d: Activate both policies and reporting | M2c | Atomically wire schema 3/projection/dispatcher, two catalog/listing entries, omitted-selection default and resource-union counts. Verify full SDK/stdio matrix, exhaustive errors and RDS-only regression, SG-14–SG-23. |
| M2e: Examples and acceptance | M2d | Real saved reports, separate illustrative HCL per representation, fixture notes, selection/limitations walkthrough, docs/status and SG-01–SG-25 acceptance record. Full Python/Rego/lint/lock/installed package checks and host evidence, SG-24–SG-25. |

Prospective definitions may live in tests during M2a–M2c; they must not become
selectable production assets or alter live omission defaults before activation.
This is an increment boundary, not a feature-flag framework. Package only
production policies; keep test rules under tests. Add comments/docstrings as each
task is implemented. Keep the locked non-editable workflow and require real OPA
for full evaluation verification; update the documented OPA-free test selection.

Documentation consistency, example/count/reason checks and `git diff --check`
complement the executed runtime/installed-package checks. No dependency was
added. No push, infrastructure mutation, cloud access or future capability is authorized.

## Official references and interpretation

Consulted 2026-10-21. Resource fields/API semantics are documentation facts;
scope, uncertainty rules, privacy projections and work limits are project choices.

- [HashiCorp inline security groups](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/security_group.html.markdown): inline representation and provider guidance favoring modern standalone rules. M2 supports existing forms without recommending mixed management of one group.
- [HashiCorp legacy rules](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/security_group_rule.html.markdown): direction/source fields and the legacy all-protocol alias. Coverage includes this existing representation; new HCL examples should clearly label it legacy.
- [HashiCorp modern ingress rules](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/vpc_security_group_ingress_rule.html.markdown): scalar source fields and ip_protocol. M2 makes no rule-to-group association inference.
- [AWS IpPermission](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html): protocol numbers, TCP port ranges and all-protocol semantics. The policy is limited to direct TCP SSH, not arbitrary encapsulation/reachability.
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format): desired values, unknown/sensitive metadata and array representation. Conservative cross-source set handling and no omitted-array pass are project safety decisions.
- [Python ipaddress](https://docs.python.org/3.14/library/ipaddress.html): standard-library network parsing. Prefix-only projection and constrained accepted text syntax minimize retained data; Rego still decides compliance.
- [OPA comparison built-ins](https://www.openpolicyagent.org/docs/policy-reference/builtins/comparison), [capabilities](https://www.openpolicyagent.org/docs/operations#capabilities) and [policy testing](https://www.openpolicyagent.org/docs/policy-testing): constrain the proposed lte addition and retain actual policy execution.
- [MCP Python SDK 2.3.0 low-level server](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/advanced/low-level-server.md): keep the current explicit schemas/handlers and stdio implementation; no SDK migration is proposed.

Current upstream provider documentation is not evidence of a live-account or
Terraform-generated plan compatibility campaign. Missing or ambiguous provider
representations remain explicit uncertainty or unsupported scope.
