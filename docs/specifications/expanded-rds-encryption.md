# Specification 004: expand RDS encryption coverage

Status: approved; M1 runtime implemented and locally verified. Existing Codex
connection reload smoke test remains pending; see [acceptance evidence](../rds-acceptance.md).
Updated: 2026-10-21.

This specification defines M1 in the [implementation plan](../implementation-plan.md).
It refines AWS-RDS-001 and FR-05–FR-10 plus the existing confidentiality, bounded
execution and read-only requirements in [requirements](../requirements.md).
Specifications [001](analyze-terraform-plan.md),
[002](evaluate-terraform-policies.md) and [003](list-policies.md) remain the
baseline, with the explicit policy/projection changes below superseding their
standalone-only restrictions when M1 is implemented.

The user has completed hands-on calls to all three tools through Codex. Further
manual familiarization is not a prerequisite for this drafting increment.

## Goal and scope

Answer: **Does the plan establish storage encryption for supported RDS instances
and clusters, including cluster members whose association can be established?**

Keep all three MCP tools and their inputs. Expand the single high-severity policy
**AWS-RDS-001 from version 1.0.0 to 1.1.0**:

| Canonical HashiCorp AWS resource | Proposed behavior |
| --- | --- |
| `aws_db_instance` | Preserve the existing standalone-instance behavior and defensive `cluster_identifier` guard. |
| `aws_rds_cluster` | Check its own desired `storage_encrypted` boolean. Cover the cluster resource representation used for Aurora and RDS Multi-AZ DB clusters. |
| `aws_rds_cluster_instance` | Resolve a unique same-plan cluster conservatively, then check that cluster's desired encryption. Never treat this member as a standalone instance. |

Support only `registry.terraform.io/hashicorp/aws`; data sources and deletion-only
resources retain their existing not-applicable checks. Other resource types,
including `aws_rds_global_cluster`, remain unsupported. No new policy ID, tool,
transport, operator setting, dependency, AWS access or Terraform execution is
introduced. SSH, tags, S3, live cluster discovery, KMS-key governance, replica and
snapshot lineage, and arbitrary Terraform expression evaluation are outside M1.

The rule requires a strict, known `storage_encrypted=true` in the relevant desired
plan object. False is a policy violation; missing/null/unknown/sensitive or invalid
values remain indeterminate. This is an explicit plan-evidence requirement, not
a claim about AWS defaults or deployed encryption. Do not infer values from engine
mode, current date, service defaults, snapshots, keys or a member's computed copy.

## Domain decisions and known limitation

HashiCorp models Aurora members as `aws_rds_cluster_instance`, distinct from
`aws_db_instance`. A member's `storage_encrypted` is an exported attribute; the
cluster is the authority for this policy. The existing nonempty
`aws_db_instance.cluster_identifier` guard is retained for compatibility and
defensive interpretation of synthetic/unexpected input, not advertised as a
documented AWS-provider argument. It does not gain inheritance in M1.

An identifier alone is insufficient to establish AWS account/Region context.
For inheritance, require known identifiers and compatible RDS ARNs in desired
values, as specified below. This avoids guessing provider alias, account or
resource-level Region equivalence from the canonical provider source.

**Limitation:** freshly created clusters/members often have unknown computed
ARNs or association identifiers. Those member checks remain indeterminate even
when the observed cluster's own encryption check passes. M1 does not infer a link
from a `configuration.expressions.*.references` entry: references describe
dependencies, not the complete expression, so a dependency need not be the final
identifier value. A later association increment can address additional proof
sources; it must not silently weaken this contract.

## Shared normalization and transient linkage data

Reuse the contained loader, exact-address merge, source precedence and typed mask
union. Evaluation normalizes once and reads the file once. Analysis continues to
discard provider values and must not initialize the catalog, association resolver
or OPA. Resource addresses remain opaque, including nested modules and instance
keys; never parse them to derive AWS identities or link candidates.

Extend only evaluation's opt-in projection:

1. Merge identities and sensitive/unknown masks for every observed resource.
2. Classify direct encryption and collect minimal, masked linkage inputs from the
   authoritative desired object for supported, managed, non-deleted resources.
3. Build bounded cluster indexes, resolve member associations and attach only
   value-free states plus an optional existing Terraform cluster address.
4. Discard all transient strings/indexes before returning `ResourceSnapshot`.

`resource_changes.change.after` remains authoritative; inventory is used only
when no change entry exists. Missing/null `after` never falls back to `before` or
an inventory copy. Never use old ARNs/identifiers/encryption from `before` to
recover a deletion or replacement link. Both replacement orderings assess the
new desired object once.

The only extra transient attribute paths are `cluster_identifier`, `arn` and
`region`. Retain `storage_encrypted` only as the existing strict known boolean or
value-free uncertainty state. Evaluate root/ancestor/descendant masks before any
string parsing or lookup. Sensitivity takes precedence over unknown, incomplete
unknown metadata, unavailable desired objects, then observed values/types.

Linkage strings must be strict, nonempty, bounded text using the existing
`IdentityText` ceiling and control/surrogate restrictions; no trimming, case
folding, interpolation, ARN-to-name fallback or type coercion. ARN parsing checks
the structural RDS form `arn:<partition>:rds:<region>:<12-digit-account>:<kind>:<name>`:

- Accept the explicit partitions `aws`, `aws-cn` and `aws-us-gov`.
- Region must be a nonempty ASCII lowercase letter/digit/hyphen token of at most
  64 characters. This checks syntax, not current Region availability.
- Kind is `cluster` for cluster resources and `db` for members. Name is nonempty
  and contains no additional colon. A cluster ARN's name must equal its known
  `cluster_identifier` exactly.
- If desired `region` is a known nonempty string, it must equal the ARN Region.
  Missing/null `region` may use the known ARN as evidence; a masked, unknown,
  incomplete, invalid or conflicting Region cannot establish linkage context.

Parsing establishes consistency of plan evidence, not authenticity or live AWS
existence. Raw ARNs, identifiers, account numbers, Regions, provider configuration
expressions and matching keys must never appear in returned snapshots, OPA input,
public results, logs, exceptions or debug representations. Fields on transient
helper objects use `repr=False`; safe failure mapping remains mandatory.

## Association algorithm

Consider only canonical-provider, managed, non-deleted `aws_rds_cluster` targets.
Direct cluster encryption does not require an identifier or ARN; incomplete
linkage metadata must not prevent checking its own known encryption boolean.

For an eligible member with known, unmasked linkage inputs, construct a transient
lookup key `(partition, account, region, cluster_identifier)` from its own DB ARN
and desired cluster identifier. A target needs a matching cluster identifier and
cluster-ARN context. Do not use the member ARN's resource name as a cluster name.

Resolve only when exactly one eligible target has that complete key and no other
eligible target could match because of uncertain linkage fields. A target can
be excluded from a potential match only by a known unequal identifier or known
unequal ARN context. Missing, sensitive, unknown, invalid or contradictory target
fields are not proof of inequality. Track uncertain-key blockers so an incomplete
target cannot be silently omitted while another target produces a pass.
If known fields contradict one another, invalidate the affected lookup key rather
than using either conflicting value as evidence to exclude that target.

- One exact target with no potential blocker: `resolved`, retaining its address.
- Multiple exact targets: `ambiguous`; never choose by input/address order.
- A possible target with incomplete context/key: `context_unverified`, including
  one exact match plus an uncertain potential duplicate.
- No exact or possible target: `not_found`. This also covers an absent target or
  a target present only as a deletion, without consulting its old attributes.

Other member states are `sensitive`, `unknown`, `unverified`, `unavailable`,
`missing`, `null` and `invalid_type`. Classify sensitive/unknown over the consumed
linkage fields before looking at values; incomplete unknown metadata is
`unverified`, and absent desired objects are `unavailable`. Then classify a
missing/null cluster identifier separately; a known empty/wrong-type identifier
is `invalid_type`. Missing/null ARN is `context_unverified`; malformed ARN or a
known Region conflict is `invalid_type`. All unresolved states are indeterminate.

Use hash indexes and uncertainty summaries bounded by `max_resources` for O(n)
expected association work and O(n) auxiliary storage. Do not scan all clusters for
every member or construct all possible pairs. Keep the existing input-byte/depth/
resource and executor/cancellation limits; no new queue or CLI budget is added.

## Internal projection and Rego contract

Extend `DesiredStateProjection` with a strict discriminated `association`:

| Variant | Fields |
| --- | --- |
| Direct check | `state: "not_required"`; no target address. Existing standalone scope/encryption states remain valid. Clusters use the new `scope: "cluster"` literal without the standalone guard. |
| Resolved member | `state: "resolved"`, `cluster_address: IdentityText`. |
| Unresolved member | `state` from the unresolved states above; no target address. |

Members use the new `scope: "cluster_member"` literal; their association state
determines whether inheritance is available. The member's own `encryption` is
`unavailable`: do not retain or consult its
computed `storage_encrypted`, including when it disagrees with the cluster.
No unresolved variant may carry a guessed address. The projected input validator
requires every resolved address to name an eligible cluster in that same input;
self-links, dangling links, data/deleted targets and other provider/type targets
are invalid internal input, not compliance outcomes.

Bump the internal **EvaluationInput schema to `"2"`** for this projection. Public
analysis, evaluation and listing envelope versions stay `"1"`; public finding
reason enums and policy metadata expand intentionally. EngineReport remains
schema `"1"` because its check envelope is unchanged. Rego must explicitly require
input schema 2 after activation; unsupported/undefined engine results remain
atomic evaluation errors under Specification 002.

Python resolves relationships and validates shape; **Rego makes compliance
decisions**. Rego indexes the projected resources by address and looks up a
resolved member's cluster encryption. Do not compute pass/fail in the adapter or
copy a Python compliance result to members.

Decision precedence remains data source, deletion, unsupported provider/type,
scope/association uncertainty, then encryption. Clusters use the same encryption
truth table as standalone instances. Resolved members use the target's projected
encryption states. A local known member value cannot override the target, and
unresolved members cannot fall back to their computed copy.

Keep the 16 existing reason templates for their existing applicable cases and
add exactly these catalog-controlled families:

| Codes | Outcome and public attribute path |
| --- | --- |
| `RDS_CLUSTER_LINK_SENSITIVE`, `RDS_CLUSTER_LINK_UNKNOWN`, `RDS_CLUSTER_LINK_UNVERIFIED`, `RDS_CLUSTER_LINK_UNAVAILABLE`, `RDS_CLUSTER_LINK_MISSING`, `RDS_CLUSTER_LINK_NULL`, `RDS_CLUSTER_LINK_INVALID_TYPE`, `RDS_CLUSTER_LINK_CONTEXT_UNVERIFIED`, `RDS_CLUSTER_LINK_NOT_FOUND`, `RDS_CLUSTER_LINK_AMBIGUOUS` | `indeterminate`, `["cluster_identifier"]`; explain the fixed association limitation, without values or candidate addresses. |
| `RDS_CLUSTER_ENCRYPTION_ENABLED` | `pass`, `["cluster_identifier"]`; the resolved cluster has explicit known encryption enabled. |
| `RDS_CLUSTER_ENCRYPTION_DISABLED` | `fail`, `["cluster_identifier"]`; explain that the associated cluster explicitly fails the encryption requirement. |
| `RDS_CLUSTER_ENCRYPTION_SENSITIVE`, `RDS_CLUSTER_ENCRYPTION_UNKNOWN`, `RDS_CLUSTER_ENCRYPTION_UNVERIFIED`, `RDS_CLUSTER_ENCRYPTION_UNAVAILABLE`, `RDS_CLUSTER_ENCRYPTION_MISSING`, `RDS_CLUSTER_ENCRYPTION_NULL`, `RDS_CLUSTER_ENCRYPTION_INVALID_TYPE` | `indeterminate`, `["cluster_identifier"]`; explain why the associated cluster's encryption could not be established. |

Direct-resource encryption reasons keep `["storage_encrypted"]`. A member finding
points to its relationship field; remediation says to inspect/configure the
associated cluster's encryption, not set the member's computed attribute. Text
comes from the catalog and never interpolates ARNs, identifiers or plan values.

Validate exact reason membership and each allowed resource/association/reason
combination, not merely a reason-count constant. Preserve one check for every
selected-policy/resource pair, exhaustive batch validation, fixed errors and
atomic engine failure behavior. A resolved target must not disappear from Rego's
lookup and silently drop a member check.

## Reporting, listing and compatibility

The catalog continues to contain one enabled policy with no policy-specific
configuration requirements. After M1 passes its checks, publish:

```json
{
  "policy_id": "AWS-RDS-001",
  "policy_version": "1.1.0",
  "title": "RDS storage encryption",
  "description": "Require explicit storage encryption for supported AWS RDS instances and clusters, including resolvable cluster members.",
  "severity": "high",
  "supported_provider_names": ["registry.terraform.io/hashicorp/aws"],
  "supported_resource_types": ["aws_db_instance", "aws_rds_cluster", "aws_rds_cluster_instance"],
  "required_paths": [["storage_encrypted"], ["cluster_identifier"], ["arn"], ["region"]],
  "scope_description": "Standalone RDS instances and RDS clusters; Aurora members inherit only from a unique same-plan cluster with known matching identifier and AWS ARN context. Unresolved associations are indeterminate; service defaults and live state are not inferred.",
  "required_configuration": []
}
```

This is the public policy entry, not the complete PolicyList envelope or internal
catalog document. `required_paths` is the union of fields consumed across types;
an instance's direct check does not require every linkage field. Listing still
reads no plan and never probes OPA. Update strict version/type/path guards in the
catalog and listing contracts together; advertised schemas must accept the
actual expanded metadata and checks. Do not add a generic policy/version registry.

Keep tool inputs, policy selection, read-only hints, errors, byte budgets and
matching text/structured outputs unchanged. Existing analysis results remain
identical. Standalone evaluation outcomes remain identical; their policy-scope
metadata intentionally reports 1.1.0 and expanded support. Regenerate saved
evaluation/listing reports only for these documented changes; preserve historical
acceptance evidence as checkpoint records.

Supported non-deleted managed resources of all three types count as candidates,
including unresolved members. Data/deleted/unsupported buckets remain disjoint.
One cluster with two members yields three policy checks, not one unique-cluster
check. Cluster and member failures are separate resource findings; counts do not
represent unique root causes. Reuse compliance precedence: verified failures win,
uncertainty blocks pass, partial input blocks an overall pass, and no applicable
resources cannot pass. Link uncertainty is a compliance check, not an engine error.

## Worked case

Consider two unchanged synthetic resources with complete unknown metadata:

| Address | Relevant known desired values |
| --- | --- |
| `aws_rds_cluster.example` | `cluster_identifier="demo-cluster"`, `arn="arn:aws:rds:us-east-1:111122223333:cluster:demo-cluster"`, `storage_encrypted=false` |
| `aws_rds_cluster_instance.member` | `cluster_identifier="demo-cluster"`, `arn="arn:aws:rds:us-east-1:111122223333:db:demo-member"`; its computed encryption copy is ignored. |

The matching key resolves the member to `aws_rds_cluster.example`; only that
Terraform address crosses the engine boundary. Rego returns a direct failure for
the cluster and an inherited failure for the member. The complete public report
has two resources, two candidates, two expected/evaluated/applicable checks, two
failures, no errors and compliance `fail`. This is an explanation of expected
behavior, not a new fixture already present in the repository.

If cluster encryption is true, both checks pass. If the member ARN is unknown,
the cluster can pass while the member is indeterminate and the overall result is
indeterminate. If another possible cluster has masked linkage data, do not pick
the otherwise known target. If no cluster is present, a member's known computed
`storage_encrypted=true` still cannot establish this policy's inherited check.

## Acceptance cases

Use synthetic plans/fake AWS identifiers and illustrative HCL without executing
Terraform. Real OPA is required for Rego and end-to-end evaluation checks. Core
normalization, association and listing tests remain runnable without OPA/AWS.

| ID | Case and required evidence |
| --- | --- |
| RD-01 | Existing standalone true/false/missing/null/invalid/unknown/sensitive cases and the defensive nonempty cluster guard preserve their outcomes; analysis inputs/reports are unchanged. |
| RD-02 | Direct cluster true/false cases produce pass/fail with canonical provider scope, across Aurora/Multi-AZ representative shapes and root/nested/indexed addresses. Missing linkage metadata does not block a direct encryption check. |
| RD-03 | Cluster missing/null/string/number/container encryption yields the appropriate indeterminate reason; only strict booleans decide. No service/engine-mode/key default is invented. |
| RD-04 | Root/attribute/descendant sensitivity and unknown masks, source mask union and incomplete unknown metadata block encryption/linkage knowledge before parsing or matching. Cover strings as well as booleans. |
| RD-05 | Known member identifier and compatible valid RDS ARN context uniquely resolve an observed cluster; true/false and every uncertain target-encryption state propagate through real Rego. |
| RD-06 | Member computed encryption is ignored for resolved and unresolved cases, including values contradicting its target. Remediation points to the cluster, never to configuring a computed member field. |
| RD-07 | Missing/null/empty/wrong-type/unknown/sensitive member identifiers, missing/malformed/unknown/sensitive ARNs and incomplete metadata produce documented value-free link states. |
| RD-08 | Account, Region and partition mismatches never link by name alone. Known Region/ARN conflicts block linkage; absent Region may use a known ARN, but unknown/sensitive Region cannot. No provider alias/context guess is made. |
| RD-09 | Multiple exact cluster keys are ambiguous regardless of input order. An uncertain possible duplicate blocks resolution; a provably unequal known key does not. Test all uncertainty-summary combinations. |
| RD-10 | Missing/external/data/wrong-provider/wrong-type/deleted targets never supply inheritance. Unknown or misleading configuration references do not resolve a member; no old/before values are used. |
| RD-11 | Change `after` wins over conflicting planned inventory for identifiers, ARNs and encryption; absent/null `after` cannot fall back. Test both replacement orders, no-op/update/create and inventory-only unverified cases. |
| RD-12 | Nested/indexed modules and identical names at different addresses are handled as opaque identities. Fake names/addresses cannot substitute for identifiers, and member ARN names are not treated as cluster IDs. |
| RD-13 | Entire normalization/association pipeline remains off-loop and bounded. A large synthetic graph exercises linear-index work without pair products; existing input/depth/resource/output limits and cancellation/admission tests still pass. |
| RD-14 | Snapshots, OPA input, both MCP output channels, logs and captured failures contain no raw identifier/ARN/account/Region sentinels, even for unmarked fields. Only existing resource addresses and fixed state codes may survive linkage. |
| RD-15 | Input schema 2 validates resolved-target eligibility and forbids state/address mismatches, dangling/self/deleted targets and extra payload fields. Unsupported/undefined/missing/duplicate/inappropriate Rego results remain safe atomic errors. |
| RD-16 | Exactly one check per resource/policy pair survives every state. Cluster plus two members counts three checks; partial, empty, deletion/data-only and unsupported-only plans preserve existing coverage/compliance semantics. |
| RD-17 | `list_policies` and evaluation agree on AWS-RDS-001 v1.1.0, three supported types, required paths, empty configuration requirements and limitations. No SSH/tags/S3/global-cluster policy is advertised. |
| RD-18 | SDK auto/legacy and real stdio tests discover exactly the same three tools, accept unchanged arguments and return matching validated text/structured content; inherited findings are successful execution, engine failures are errors. |
| RD-19 | Real OPA strict check, format, unit and runner/service tests cover resolved/unresolved graphs. Missing OPA fails full verification clearly; analysis/listing and pure adapter tests retain no OPA prerequisite. |
| RD-20 | Existing root-containment, safe-input/error, capabilities/environment, timeout/output-overflow and cleanup checks pass. Linking adds no plan-controlled executable/query/path or network capability. |
| RD-21 | Updated example reports and illustrative HCL explain known associations and the common unknown-ARN creation limitation. Codex smoke prompts exercise cluster pass/fail/uncertainty; record observed tool calls, not just model prose. |
| RD-22 | Wheel/source assets and installed operation outside checkout pass with the new catalog/Rego/input contract; no test-only policies, future adapter or dependency is shipped. Record macOS/Linux execution evidence separately. |

## Implementation tasks

The user approved this specification and authorized implementation. The table
records the implementation sequence; M1a–M1d are complete. M1e's automated,
documentation and packaging work is complete, with live Codex reload testing
recorded separately rather than claimed as passing.
Complete relevant checks before advancing through these small M1 tasks:

| Task | Depends on | Deliverable and checks |
| --- | --- | --- |
| M1a: Define expanded contracts | L1; implementation authorized after review | Specify strict association variants, input schema 2, prospective v1.1 metadata/reasons and synthetic test builders. Contract checks cover RD-01, RD-07, RD-15 and RD-17 without changing advertised production coverage. |
| M1b: Normalize and resolve associations | M1a | Pure bounded `rds_associations.py`, minimal masked transient inputs and two-pass evaluation projection. Verify RD-02–RD-04 and RD-07–RD-14, including uncertain-key blockers and cleanup. Analysis stays independent. |
| M1c: Extend and verify Rego | M1b | Cluster direct checks, address-indexed member inheritance and exact reason applicability; validate graph input and exhaustive output. Use test-only proposed metadata until activation. Real OPA covers RD-03–RD-10 and RD-15–RD-16/RD-19. |
| M1d: Activate evaluation and catalog | M1c | Wire the verified projection/input/Rego contract and publish v1.1.0 metadata/strict listing schemas together. Verify unchanged tool inputs, reports/counts and safe failures through auto/legacy/stdio, RD-01/RD-16–RD-20. |
| M1e: Examples, documentation and acceptance | M1d | Save real reports, add illustrative HCL and fixture notes, refresh public scope/limitations, perform Codex smoke testing and installed source/wheel checks. Record RD-01–RD-22 traceability and executed checks. |

During M1a–M1c, keep advertised production coverage at v1.0.0; prospective metadata
and test-only policies must not become user-selectable assets. Activate the new
runtime and metadata together only after the supporting checks pass. This is an
increment boundary, not a request for a generic feature-flag/version framework.

Use current locked, non-editable commands from [development](../development.md)
and [evaluation verification](../trying-evaluation.md#5-verify-locally). Keep
Python 3.14+, MCP 2.3.0, OPA 1.21.2 and restricted capabilities. Any necessary
built-in addition requires a concrete use, a minimal deterministic capability
change and updated denial tests; do not enable network/runtime introspection.
Add comments/docstrings with each task. Drafting needs documentation consistency,
example/count checks and `git diff --check`; it installs no dependencies and runs
no new runtime tests. Do not mark proposed acceptance cases executed yet.

## Official references and interpretation

Consulted 2026-10-21; documentation facts and project decisions are distinguished:

- [HashiCorp cluster resource](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/rds_cluster.html.markdown): cluster resource scope and the `storage_encrypted` field. M1's strict desired-plan boolean requirement is our policy, not inferred provider defaults.
- [HashiCorp cluster-instance resource](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/rds_cluster_instance.html.markdown): member resource, required cluster identifier and exported encryption/ARN attributes. Cluster-authoritative checking with no computed-copy fallback is our conservative choice.
- [HashiCorp standalone DB instance](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/db_instance.html.markdown): separate instance resource; its documented arguments do not include `cluster_identifier`.
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format): separate values/unknown masks and configuration dependency references. Treating references as insufficient proof of an exact computed identifier is our design decision.
- [AWS Aurora encryption](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Overview.Encryption.html): instances share cluster storage encryption; AWS documents default encryption for new clusters. This server neither infers those defaults nor verifies live state.
- [AWS RDS ARN structure](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Tagging.ARN.Constructing.html): RDS identifiers include Region/account/resource context. Requiring compatible known ARN context and blocking uncertain duplicates is our association-safety decision.
- [OPA policy testing](https://www.openpolicyagent.org/docs/policy-testing) and [MCP SDK 2.3.0 low-level API](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/advanced/low-level-server.md): retain real Rego testing and existing explicit SDK handlers/schemas.

Provider docs are current upstream references, not a claim of a Terraform-generated
plan compatibility campaign or support for every provider version. No provider,
Terraform, AWS credential or new runtime is installed while drafting this spec.
