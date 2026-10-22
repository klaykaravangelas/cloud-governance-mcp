# Specification 007: S3 public-access protection

Status: specification and implementation authorized together on 2026-10-22; M4a–M4e implemented.
See [acceptance evidence](../s3-acceptance.md).
Updated: 2026-10-22.

## Outcome and scope

Implement M4 as **AWS-S3-001 v1.0.0**, high severity, using the existing three
stdio tools. Exact provider: `registry.terraform.io/hashicorp/aws`. Exact types,
in order: `aws_s3_bucket`, `aws_s3_bucket_public_access_block`.
Managed create/update/replacement/no-op/inventory resources are eligible.
Data sources, deletion-only resources and unsupported providers/types retain the
existing not-applicable reasons. No AWS connectivity or Terraform execution.

This is a requirement for observed bucket-level protection in the supplied plan,
not a determination of effective public reachability. Do not inspect arbitrary
bucket policies, ACLs, access points, directory buckets, account/organization
settings, provider defaults or live AWS. Missing block resources do not prove
that deployed buckets are public. No account-level protection is inferred.

## Flags and outcomes

Evaluate these flags in this fixed order:

1. `block_public_acls`
2. `ignore_public_acls`
3. `block_public_policy`
4. `restrict_public_buckets`

Each scalar observation is either a strict known boolean, or sensitive, unknown,
unverified, unavailable, missing, null or invalid_type. Apply merged masks before
reading values, including root and descendant masks on scalar fields. Reuse
change-after precedence; never fall back to before/inventory for a change.

Rego owns the decision: any independently known false flag fails, even with
uncertain siblings; all four known true flags pass. Otherwise indeterminate.
For multiple false flags choose the first in the fixed order. Otherwise choose
sensitive, unknown, unverified, unavailable, missing, null, invalid_type in that
priority, then flag order. Missing/null flags are indeterminate, never provider
defaults. Output one check per selected-policy/resource pair.

A direct block check evaluates its flags regardless of whether its target bucket
is present or known. A bucket check inherits flags only through a proved link.
Unknown bucket linkage cannot inherit a failure from an unproved block.

## Conservative association

Association uses only independently known nonempty strings in desired `bucket`
attributes on both types. Retain these transiently for exact equality; no trimming,
coercion, address parsing or expression evaluation. Root/attribute sensitivity,
unknowns, missing metadata and absent/null/invalid values retain uncertainty.
A string must be at most 2,048 characters and free of controls/surrogates.

A bucket resolves only if:

- Its name occurs on exactly one eligible bucket and exactly one eligible block.
- No eligible bucket or block has an unresolved name that could conceal a duplicate.
- Both resources have the same known `provider_config_key` in configuration
  metadata, proving the same provider configuration rather than assuming aliases
  or partitions are interchangeable. Different or absent keys are context_unverified.

Index exact names/counts once; unknown-name blockers are global and conservative.
Never exclude possible duplicates because provider keys differ: aliases can still
refer to the same real context. Deleted/data/other-provider objects do not enter
these indexes. Multiple known matches are ambiguous; no matching block is
not_found. Missing and ambiguous associations are indeterminate. A partially
known graph must never manufacture a pass.

Read only configuration module/resource identity and provider_config_key metadata.
Map unindexed module contexts using the explicit configuration tree plus resource
mode/type/name and normalized explicit module membership. When module metadata is
absent, root membership additionally requires exact equality to the opaque
configuration resource address; absence alone never implies root. Resource addresses
remain opaque. Indexed module contexts that cannot be mapped without interpreting
addresses remain context_unverified; indexed resources in a proved unindexed
module can use their explicit type/name metadata. Configuration dependencies and
references do not prove value equality, including computed creation-time names.
No fallback to them is supported. Bound configuration depth and total entries by
the adapter's existing max_depth/max_resources, and composed contexts to 2,048 characters; malformed consumed metadata fails
with the existing safe INVALID_PLAN, excess work with PLAN_LIMIT_EXCEEDED.
Unselected S3/analysis/listing do not consume this configuration metadata.

Raw bucket names/provider keys/configuration never enter the returned snapshot,
OPA input, public results, logs or exception messages. Only fixed knowledge
states and a resolved Terraform block address survive. Public paths are fixed
catalog paths: direct flag failures/uncertainty identify that flag; inherited
bucket results identify `bucket`. Explanations distinguish inherited protection
from direct settings and never interpolate raw names.

## Contracts and integration

Add pure S3 models/projection/output provenance guards. Keep normalization and
provider observations separate from Rego aggregation. Reuse loader/admission/
process cleanup and byte/time limits. No dependency, tool, transport, executable,
CLI setting or capability addition is required. Four flags per eligible block
and linear indexes stay bounded by existing resource limits.

Advance only internal engine input schema from 4 to 5. Public report, engine
output, catalog and listing envelopes remain 1. Attach S3 projection only when
selected and eligible. A bucket projection holds an unresolved state or resolved
block address; a block projection holds exactly four ordered observations.
Strict graph validation rejects wrong/missing/extra projections, dangling links,
wrong-type/provider/deleted/data targets, shared targets and contradictory representations.

Register the fourth policy in strict per-ID metadata, catalog, listing, fixed OPA
asset loading and dispatch. Omitted selection selects all four, sorted by ID.
Explicit historical selections retain their previous results. Count candidates
as a resource union; expected checks remain selected policies × all resources.
No missing/duplicate/unexpected check or invalid reason/path/state may be accepted;
engine errors fail the entire batch and return zero completed checks/findings.

Reason families: S3_BLOCK_* direct results, S3_BUCKET_* inherited flag results,
and S3_LINK_* unresolved bucket associations, plus existing common exclusions.
Fixed catalog templates own severity, outcomes, paths and prose. Python validates
reason provenance/state and graph structure; Rego decides boolean aggregation.

## Independently verifiable tasks

| Task | Deliverable | Relevant verification |
| --- | --- | --- |
| M4a | Specification, strict observations and conservative transient association | Pure contract/projection, masks, source precedence, configuration/context and work-limit tests. |
| M4b | Rego policy and fixed reason catalog | Pinned real OPA strict/fmt/test; complete flag state/priority/link inheritance cases. |
| M4c | Four-policy engine and tool integration | All 15 nonempty selection subsets, default/reversed selection, accounting, atomic errors, SDK auto/legacy and real stdio privacy. |
| M4d | Synthetic fixtures, illustrative HCL, saved reports and walkthrough | Real stdio golden comparisons, links/docs consistency and hands-on commands. |
| M4e | Acceptance evidence and distributions | Full pytest, OPA-free subset, Ruff, lock/dependencies, source/wheel and fresh installed stdio outside checkout. |

No extra confirmation gate applies between these authorized tasks. M5 complete
v0.1 acceptance remains a separate roadmap milestone; this increment must still
run all regression checks relevant to the new policy.

## Acceptance criteria

| ID | Acceptance criterion |
| --- | --- |
| S3-01 | Exact type/provider/action scope; data/delete/unsupported exclusions. |
| S3-02 | Each false flag fails; all four true pass; strict booleans only. |
| S3-03 | Every uncertain flag state is explicit and cannot pass. |
| S3-04 | Known failure precedes uncertainty; priorities and paths deterministic. |
| S3-05 | Root/ancestor/descendant and merged cross-source masks applied before reads. |
| S3-06 | Change after wins; unavailable/missing metadata never falls back or passes. |
| S3-07 | Unique known names and identical provider context resolve independent of resource order. |
| S3-08 | Absent/multiple/hidden names, context mismatches and computed references remain indeterminate. |
| S3-09 | Nested/indexed identities remain opaque; supported tree context and unsupported contexts explicit. |
| S3-10 | Duplicate/unknown blocks or buckets prevent unsafe inheritance; deleted targets ignored. |
| S3-11 | S3-only input contains no raw bucket names, provider keys, sensitive sentinels or unrelated values. |
| S3-12 | Schema 5 graph rejects missing/extra/wrong/dangling projections and links. |
| S3-13 | Catalog/listing expose exact fourth metadata; all default/explicit selections are complete. |
| S3-14 | Complete atomic output validation rejects missing checks, wrong paths/reasons/targets. |
| S3-15 | Configuration depth/count and existing byte/resource/process/concurrency limits preserved. |
| S3-16 | Analysis/listing and unselected projection remain independent of S3 parsing/OPA. |
| S3-17 | Both SDK modes and real stdio return identical text/structured safe output. |
| S3-18 | Fixtures/HCL/walkthrough distinguish protection settings from effective public reachability. |
| S3-19 | Real OPA and full regression checks execute; no missing-runtime skip replaces evidence. |
| S3-20 | Fresh source/wheel installation includes only production policies; all three tools work outside checkout. |

## Official references checked for this increment

- [AWS provider public-access-block resource](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/s3_bucket_public_access_block.html.markdown): four boolean settings and bucket argument. Explicitly provided plan values are checked; provider defaults are not synthesized.
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format): desired values, unknown/sensitive metadata, configuration provider keys and expression dependencies.
- [OPA Rego language](https://www.openpolicyagent.org/docs/policy-language): undefined values cannot stand in for complete results; use pinned Rego v1 and existing restricted capabilities.
- [Official MCP low-level server](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/): retain the pinned SDK's existing public transport API; no new handler is required.

These sources inform format interpretation. Conservative association, scope and
uncertainty priorities above are project decisions, not claims of live AWS state.
