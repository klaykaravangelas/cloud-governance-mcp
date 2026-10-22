# Project status

Updated: 2026-10-22. This file summarizes progress and approved work; contributor
rules belong in [AGENTS.md](../AGENTS.md), and design details belong in the linked
specifications and architecture.

## Implemented scope

The local read-only stdio server exposes `analyze_terraform_plan`,
`evaluate_terraform_policies` and `list_policies`. Its selectable policies are
AWS-RDS-001 v1.1.0 for standalone RDS instances, clusters and conservatively
resolved cluster members, and AWS-SG-001 v1.0.0 for unrestricted SSH ingress in
inline, legacy and modern rule representations, plus AWS-TAG-001 v1.0.0
(medium) for required tags on five explicit types, and AWS-S3-001 v1.0.0 (high)
for bucket-level public-access protection. Omission selects all four.
TAG defaults are Environment/Owner/Project with startup overrides. Analysis/listing need no OPA; evaluation uses pinned
OPA 1.21.2. No AWS connectivity or Terraform execution is implemented.

| Increment | Status and evidence |
| --- | --- |
| Specification 001 / A1–A7: analysis | Approved and implemented; [acceptance](analysis-acceptance.md). |
| Specification 002 / E1–E5: evaluation | Approved and implemented; [historical acceptance](evaluation-acceptance.md). |
| Specification 003 / L1a–L1d: listing | Approved and implemented; [historical acceptance](listing-acceptance.md). |
| Specification 004 / M1: expanded RDS | Runtime implemented; [acceptance](rds-acceptance.md) records automated evidence, successful user-reported testing and this chat's separate stale-connection observation. |
| Specification 005 / M2: SSH ingress | Approved and implemented; [acceptance](ssh-acceptance.md) maps SG-01–SG-25 to automated evidence and records the separate pending live host reload. |
| Specification 006 / M3: mandatory tags | Approved and implemented on 2026-10-22; [TAG acceptance](tags-acceptance.md) maps TG-01–TG-22 and records the separate live-host reload check. |
| Specification 007 / M4: S3 protection | Specification and implementation authorized together; [S3 acceptance](s3-acceptance.md) maps S3-01–S3-20. |

## Active work

M4 is implemented: four block flags, conservative known-name/provider-context
bucket association, and four-policy integration. Follow the
[S3 walkthrough](trying-s3.md) for individual and combined calls.
The user has completed hands-on MCP testing of earlier work;
another familiarization session is not a prerequisite. A live new-version check in a
reloaded Codex connection remains separate from fresh subprocess evidence. On
2026-10-22 this chat's existing connection returned POLICY_ASSETS_INVALID and
still advertised the old two-policy schema; a targeted restart control is not
exposed here. Fresh stdio connections use the new catalog successfully.

## Next milestones

Next, consolidate complete v0.1 verification (M5): requirement-level traceability,
release-readiness documentation and the complete three-tool workflow. Docker/CI remain v0.2; AWS
inspection remains v0.3. See the [roadmap](roadmap.md) and
[implementation plan](implementation-plan.md) for history and task sequencing.

The current runtime verification checkpoint is 1,371 Python tests and 46
Rego tests on macOS arm64; see [development](development.md). Linux execution and
a live/generated-plan compatibility campaign remain unverified. No GitHub push
or remote publication is authorized by specification approval.
