# Requirements and acceptance criteria

Status: analysis, evaluation, listing, expanded RDS and SSH ingress implemented; tags and S3 remain planned.
Updated: 2026-10-21.

## Purpose and scope

Provide AI assistants with deterministic, structured explanations of proposed
infrastructure changes and governance violations. v0.1 reads existing Terraform
plan JSON locally and evaluates bundled Rego policies. It does not generate plans,
run Terraform, connect to AWS, or change infrastructure.

The complete v0.1 scope below is delivered through three tool increments: analysis,
policy evaluation, then policy listing. Expand policy coverage afterward. The first
analysis specification is [approved](specifications/analyze-terraform-plan.md).
Bootstrap, typed contracts, contained file loading, Terraform normalization, and
the analysis service/summaries and MCP stdio interface are complete. A7 adds the
[client walkthrough](trying-analysis.md) and [acceptance evidence](analysis-acceptance.md).
Evaluation implements standalone RDS, cluster and conservative member encryption,
and unrestricted SSH ingress. Listing exposes both policies. The complete
four-family v0.1 MVP remains in progress.

[Specification 002](specifications/evaluate-terraform-policies.md) defines the implemented
first evaluation increment and EV-01–EV-24 acceptance cases. See
[evidence](evaluation-acceptance.md). Specification 004 extends that original
standalone scope; Specification 005 adds SSH. Tags and S3 remain planned.

[Specification 003](specifications/list-policies.md) defines the implemented
listing response, catalog-only execution and LP-01–LP-14 acceptance cases. See
[listing evidence](listing-acceptance.md).

[Specification 004](specifications/expanded-rds-encryption.md) is approved and
implemented locally, with M1a–M1e and RD-01–RD-22. It adds AWS-RDS-001 v1.1.0 for direct
cluster checks and conservative `aws_rds_cluster_instance` inheritance using known
same-plan identifiers/ARN context. Unresolved or computed relationships stay
indeterminate. See [RDS acceptance evidence](rds-acceptance.md), including the
existing Codex connection's pending reload smoke test.

[Specification 005](specifications/unrestricted-ssh-ingress.md) implements M2:
AWS-SG-001, three Terraform rule representations, minimal masked network
projection and two-policy selection/accounting. See [SSH acceptance](ssh-acceptance.md)
for SG-01–SG-25 evidence. Relevant uncertainty
must remain explicit, while an independently proved safe predicate can rule out
this specific exposure. Prefix lists and effective network reachability are not
inferred. Earlier user-reported MCP testing and the pending live SSH reload check
are recorded separately from automated stdio verification.

## Tool responsibilities and progression

| Order | Tool | Question answered | Dependency |
| --- | --- | --- | --- |
| 1 | `analyze_terraform_plan` | What infrastructure changes are proposed? | Safe file loading, Terraform parsing/normalization, and action summaries. No OPA. |
| 2 | `evaluate_terraform_policies` | Does the proposed infrastructure satisfy the selected governance rules? | Reuses the same loader/parser, then adds a policy catalog, OPA/Rego, and compliance reports. |
| 3 | `list_policies` | Which governance rules are available, and what do they check? | Reads the implemented catalog introduced with evaluation. No OPA process is needed for listing. |

Evaluation consumes the shared normalized plan directly; it does not call the
analysis MCP tool or parse its human-facing summary. Analysis makes no compliance
claims, and listing does not evaluate a plan.

## Functional requirements

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| FR-01 | Serve tools through the official MCP Python SDK over stdio. | An SDK client initializes, lists tools and their schemas, and calls a tool in a subprocess test. Stdout contains protocol messages only. |
| FR-02 | Accept Terraform plan JSON by local path. | A bounded nonempty `plan_path` string resolves to a regular JSON file under an operator-configured root. Invalid JSON, state JSON, unsupported format majors, and malformed required structures produce safe errors. Tools never run `terraform show`. |
| FR-03 | Parse resource changes throughout the plan. | Root and nested-module addresses, indexed instances, provider identity, resource mode/type, and ordered actions are preserved. Both replacement orderings are recognized; deletion is not mistaken for a missing desired object. |
| FR-04 | Expose `analyze_terraform_plan(plan_path)`. | Return resource identities/actions, counts by action/type, replacements counted once, total observed resources, and coverage warnings without attribute values. Include create, update, delete, replacement, no-op, and read cases. |
| FR-05 | Expose `evaluate_terraform_policies(plan_path, policy_ids?)`. | Apply all enabled policies by default or a nonempty bounded selection of known IDs. Return validated results with resource address, policy ID, severity, explanation, remediation, and coverage. Unknown IDs are input errors. Findings are deterministic. |
| FR-06 | Expose `list_policies()`. | With no arguments, return implemented policy IDs, versions, titles, descriptions, severity, supported providers/types, required paths, scope and policy-specific configuration requirements from the same catalog used for evaluation. Invoke no OPA process and read no plan. Planned policies are not listed as available. See Specification 003 for the response and safe failures. |
| FR-07 | Evaluate with real OPA/Rego. | Python invokes a configured OPA executable with a fixed query and trusted policy assets. Tests execute Rego with OPA; a Python substitute cannot satisfy acceptance. |
| FR-08 | Separate policy decisions from execution failures. | Policy outcomes are `pass`, `fail`, `indeterminate`, or `not_applicable`. Missing OPA, timeout, compilation/runtime errors, undefined entrypoint, and invalid output are evaluation errors, never compliance passes. |
| FR-09 | Preserve uncertainty and sensitivity. | Unknown and sensitive subtrees retain path metadata, including list indices and whole-subtree markers. Redacted or unknown inputs never become `false`, an empty collection, or a positive compliance result. |
| FR-10 | Report bounded coverage. | Report selected policies, per-outcome counts, skipped/deleted/data resources, unsupported resource types, and indeterminate checks. Empty findings alone do not imply a compliant plan. |

## Initial policy catalog

IDs and severity below are proposed project conventions. These checks assess the
provided plan, not the security of a deployed AWS account.

| Policy ID | Severity | v0.1 behavior and scope |
| --- | --- | --- |
| AWS-SG-001 | high | Implemented in Specification 005: flag inbound TCP port 22/ranges or all-protocol rules with an individual world-wide IPv4/IPv6 CIDR. Cover inline `aws_security_group.ingress`, legacy `aws_security_group_rule` ingress and modern `aws_vpc_security_group_ingress_rule`. Known egress is not applicable; known non-SSH permissions or complete known non-world sources pass within this rule's scope. Relevant unresolved inputs/prefix lists are indeterminate unless another known predicate resolves the rule. No CIDR-union or live reachability analysis. |
| AWS-TAG-001 | medium | Require nonempty string values for operator-configured tag keys; proposed defaults are `Environment`, `Owner`, and `Project`, case sensitive. Start with an explicit taggable-type list: `aws_instance`, `aws_security_group`, `aws_db_instance`, `aws_rds_cluster`, and `aws_s3_bucket`. Use known `tags_all` where available, otherwise `tags`; unknown or sensitive required values are indeterminate. Do not demand tags on every AWS resource type. |
| AWS-RDS-001 | high | Implemented v1.1.0: require explicit known `storage_encrypted=true` on standalone `aws_db_instance` and direct `aws_rds_cluster`. Known false fails; missing, unknown or sensitive values are indeterminate. `aws_rds_cluster_instance` inherits only through a unique same-plan cluster with known matching identifier/ARN context. Its computed encryption copy is ignored. Unresolved associations remain indeterminate. |
| AWS-S3-001 | high | Check all four public-access-block flags on `aws_s3_bucket_public_access_block`: `block_public_acls`, `ignore_public_acls`, `block_public_policy`, and `restrict_public_buckets`. Any known false fails; all known true pass. For `aws_s3_bucket`, require a provable association with a block resource in the plan; unresolved or absent associations are indeterminate with an explicit coverage reason. Do not infer live defaults or account-level settings. This does not analyze arbitrary bucket policies or ACLs. |

For each implemented policy, acceptance requires compliant, violating,
non-applicable, missing-value, unknown-value, and sensitive-value cases. Add nested
module and alternate resource representation cases where the policy supports them.
Do not claim unsupported representations are covered.

## Security and operational requirements

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| SEC-01 | Read-only operation. | No write/apply/remediation tools, Terraform execution, AWS clients, or AWS credential requirements. |
| SEC-02 | File containment configured by the operator. | No configured root means startup failure. Reject traversal, paths outside roots, symlink components below the trusted root, directories, and special files. Use descriptor-anchored opening to avoid check/open races; test denied paths and symlinks. MCP client roots cannot expand access. |
| SEC-03 | No arbitrary command execution. | No tool input accepts commands, executable paths, Rego queries, policy files, or OPA flags. OPA runs directly with an argument list and no shell; startup configuration is trusted. |
| SEC-04 | Restrict policy side effects. | Load packaged policies only. A tested OPA capabilities file excludes network and runtime/environment built-ins; evaluations need no network. Plan strings are data, never executable expressions or instructions. |
| SEC-05 | Protect sensitive plan data. | Strip marked sensitive values before OPA. Do not echo raw plans, attributes, outputs, secrets, subprocess stderr, or Pydantic validation input. Use catalog-controlled explanation templates, safe field paths, and identity-only summaries. Test with sentinel secrets. Unmarked attributes are also excluded from responses and logs. |
| SEC-06 | Bound resource consumption. | Proposed startup defaults: 10 MiB plan input, 10,000 normalized resources, 2 MiB OPA output, 5-second OPA evaluation timeout and 10-second process deadline. Bound JSON nesting and request queue; terminate/reap on timeout, cancellation, or output overflow. Limits are tested and documented. |
| SEC-07 | Validate configuration and contracts. | Pydantic validates settings, inputs, normalized envelopes, policy outputs, and reports. Do not coerce strings into encryption booleans. Additive provider attributes remain extensible internally. |

Resource addresses can themselves contain operator-chosen instance keys. Responses
must include addresses to identify findings; logs should use request IDs and counts
instead. The JSON file is sensitive even when Terraform marks only some values.

## Testing and quality requirements

Tests must run without AWS credentials or a Terraform installation. Include:

- Synthetic JSON fixtures for compliant, violating, mixed, nested-module,
  replacement, delete-only, data-only, empty, malformed, unknown, and sensitive plans.
- Example `.tf` configurations with fake identifiers and no secrets, clearly marked
  illustrative; generating or applying a plan is not a test prerequisite.
- Unit tests for file containment, format validation, action parsing, normalization,
  redaction, policy selection, and report aggregation.
- Rego tests through `opa test`, plus pytest integration tests of the actual OPA
  runner and its failure handling. Mocks exercise failure paths only.
- MCP schema/behavior tests and a real stdio test covering initialization, tool
  discovery, analysis, structured output, and clean shutdown. Extend the tests with
  evaluation and listing as those tools are added.
- Ruff checks and formatting. The first analysis increment's complete verification
  requires no OPA. Once evaluation is implemented, full evaluation/release
  verification must fail clearly if OPA is unavailable; analysis-only checks may
  continue to run independently.

## First vertical slice acceptance

[Specification 001](specifications/analyze-terraform-plan.md) defines the detailed
input/output contracts, error cases, fixtures, and acceptance tests for this scope:

- Initialize Python 3.14+ and uv, launch stdio, and expose only
  `analyze_terraform_plan(plan_path)`.
- Safely load a permitted synthetic plan and parse resource identities/actions
  across resource types, root/nested modules, and indexed instances. Recursively
  merge planned-value inventory with resource changes without double counting.
- Return deterministic identity/action summaries and counts covering create,
  update, delete, both replacement orderings, no-op, and data-source read cases.
  Flag incomplete/unsupported input coverage without implying compliance.
- Validate the plan envelope/format and preserve unknown/sensitive masks in the
  internal representation. Return no attribute, variable, or output values.
- Exercise file containment/limits, safe errors, secret non-disclosure, parser and
  summary unit tests, SDK schema/behavior tests, and a real stdio test.
- Verify the installed package outside the repository. All checks run without AWS
  credentials, Terraform, or OPA. No evaluation tool, policy catalog, Rego assets,
  or compliance report is required for this increment.

This slice covers FR-01 through FR-04, the parsing/masking portion of FR-09, and
the applicable input, file, confidentiality, and resource-limit security criteria.
OPA-specific and compliance-reporting criteria apply when evaluation is added.

## Following increments

The tested loader/parser now supports `evaluate_terraform_policies` with one RDS
encryption policy, real OPA tests, a catalog, capabilities, runtime limits and
structured findings. `list_policies` now exposes that same catalog. Next
incrementally complete the four v0.1 policy families. See
[the implementation plan](implementation-plan.md) for task boundaries.

## Out of scope for v0.1

AWS/boto3 connectivity, cloud mutation, remote transport/authentication, Docker,
GitHub Actions workflows, cross-account discovery, drift, costs, documentation
retrieval, RAG, custom uploaded policies, and remote policy bundles. GitHub Actions
is the intended automation platform starting in v0.2; local checks cover v0.1.
