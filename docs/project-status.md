# Project status

Updated: 2026-10-21. This file summarizes progress and approved work; contributor
rules belong in [AGENTS.md](../AGENTS.md), and design details belong in the linked
specifications and architecture.

## Implemented scope

The local read-only stdio server exposes `analyze_terraform_plan`,
`evaluate_terraform_policies` and `list_policies`. Its selectable policies are
AWS-RDS-001 v1.1.0 for standalone RDS instances, clusters and conservatively
resolved cluster members, and AWS-SG-001 v1.0.0 for unrestricted SSH ingress in
inline, legacy and modern rule representations. Analysis/listing need no OPA; evaluation uses pinned
OPA 1.21.2. No AWS connectivity or Terraform execution is implemented.

| Increment | Status and evidence |
| --- | --- |
| Specification 001 / A1–A7: analysis | Approved and implemented; [acceptance](analysis-acceptance.md). |
| Specification 002 / E1–E5: evaluation | Approved and implemented; [historical acceptance](evaluation-acceptance.md). |
| Specification 003 / L1a–L1d: listing | Approved and implemented; [historical acceptance](listing-acceptance.md). |
| Specification 004 / M1: expanded RDS | Runtime implemented; [acceptance](rds-acceptance.md) records automated evidence, successful user-reported testing and this chat's separate stale-connection observation. |
| Specification 005 / M2: SSH ingress | Approved and implemented; [acceptance](ssh-acceptance.md) maps SG-01–SG-25 to automated evidence and records the separate pending live host reload. |

## Active work

M2 is implemented with strict SSH contracts, masked projection, real Rego,
two-policy selection/catalog/reporting and examples. Omitted selection now checks
both policies. The user has completed hands-on MCP testing of earlier work;
another familiarization session is not a prerequisite. A live SSH check in a
reloaded Codex connection remains separate from fresh subprocess evidence.

## Next milestones

After M2, draft separate specifications for mandatory tags (M3), S3 public-access
protection (M4) and complete v0.1 verification (M5). Docker/CI remain v0.2; AWS
inspection remains v0.3. See the [roadmap](roadmap.md) and
[implementation plan](implementation-plan.md) for history and task sequencing.

The current runtime verification checkpoint is 1,009 Python tests and 29
Rego tests on macOS arm64; see [development](development.md). Linux execution and
a live/generated-plan compatibility campaign remain unverified. No GitHub push
or remote publication is authorized by specification approval.
