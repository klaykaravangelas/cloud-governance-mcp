# Roadmap

Status: all three tools and four initial policy families implemented through M4.
M5 complete v0.1 acceptance consolidation remains next; live-host reload checks
remain separate from fresh installed stdio evidence.
Updated: 2026-10-22. Milestones describe scope and completion criteria, not calendar
commitments or extra approval gates. Server implementation follows
architecture/specification review and user direction, then proceeds through small
verified increments.

| Milestone | Deliverables | Exit criteria |
| --- | --- | --- |
| Planning | Requirements, architecture, roadmap, repository guidance, and implementation plan aligned to analysis -> evaluation -> listing. | Documentation consistently identifies analysis as the first working slice. |
| First specification (approved) | [Specification 001](specifications/analyze-terraform-plan.md): detailed `analyze_terraform_plan` input/output contracts, counting/merge rules, security/error behavior, fixture scenarios, and acceptance cases. | User reviewed and approved; analysis scope is concrete and independently testable. |
| Package bootstrap A1 (complete) | Python 3.14.7 uv environment/lockfile, official MCP/Pydantic dependencies, package scaffold, pytest/Ruff setup. | Quiet package import, lint/format, lock/environment/dependency checks, source/wheel builds and independent wheel installation passed. |
| Analysis contracts A2 (complete) | Strict settings/input, identity/action and mask/snapshot models, public analysis schema, safe errors/warnings. | 131 contract/import tests and Ruff checks passed without AWS, Terraform, or OPA. |
| Contained loading A3 (complete) | Pinned directory roots, no-follow regular-file reads, byte/depth bounds, strict UTF-8 JSON, safe errors and descriptor cleanup. | At A3, 191 tests passed, including 60 loader cases and deterministic component/FIFO swaps. Tested on macOS. |
| Terraform normalization A4 (complete) | Format/envelope validation, nested inventory merge, identities/actions, masks, coverage warnings, synthetic plans and illustrative HCL. | At A4, 369 tests passed, including 178 new mask/adapter/pipeline cases; Ruff and distribution checks passed. |
| Analysis service A5 (complete) | Public action/type/mode summaries, async pipeline, output byte limits, nonblocking admission, safe errors and cancellation cleanup. | At A5, 427 tests passed, including 58 new summary/service cases; Ruff and distribution checks passed. |
| MCP interface A6 (complete) | One analysis tool with strict schemas/read-only hints, safe text/structured responses and errors, required roots/limit CLI options, console/module entrypoints and stdio lifecycle. | At A6, 511 tests passed, including 84 new SDK/CLI/stdio cases in auto/legacy modes. Real subprocesses, Ruff and installed-wheel checks passed. |
| Verification/documentation A7 (complete) | Hands-on guide, standalone SDK client, saved report, acceptance evidence, source docs/lock inclusion and independent installed-wheel stdio checks. | 521 tests pass, including 10 walkthrough cases; lint/format, packaging and lock/environment/dependency checks pass. User familiarization is next. |
| First working slice: analysis (complete, toward v0.1) | Python/uv package, stdio server, only `analyze_terraform_plan`, safe loader/parser, generic resource/action summaries, synthetic plans and illustrative HCL. | AN-01–AN-15 pass on the verified macOS environment; see [acceptance evidence](analysis-acceptance.md). No AWS credentials, Terraform or OPA needed. |
| Second specification (implemented) | [Specification 002](specifications/evaluate-terraform-policies.md): one RDS policy, evaluation contracts, safe OPA execution, reports, E1–E5 and EV-01–EV-24. | User authorized implementation; see [evaluation evidence](evaluation-acceptance.md). |
| Second increment: evaluation (complete) | Follow Specification 002; reuse the parser, add `evaluate_terraform_policies`, standalone RDS encryption Rego, policy catalog, constrained OPA runner and compliance reports. | EV-01–EV-24 and real OPA/stdio tests pass; analysis still works without OPA. |
| Third specification (implemented) | [Specification 003](specifications/list-policies.md): listing metadata, empty input, catalog-only service, safe failures, L1a–L1d and LP-01–LP-14. | User authorized implementation; see [listing evidence](listing-acceptance.md). |
| Third increment: policy listing (complete) | L1a–L1d use the existing evaluator catalog, with client walkthrough and acceptance evidence. | Three tools are discoverable; metadata matches evaluation, planned policies are excluded, and listing works without invoking OPA or reading plans. |
| Fourth specification (approved; runtime implemented) | [Specification 004](specifications/expanded-rds-encryption.md): AWS-RDS-001 v1.1.0, cluster encryption, known-value/context association rules, M1a–M1e and RD-01–RD-22. | User authorized implementation; see [RDS evidence](rds-acceptance.md). |
| M1: expanded RDS coverage (runtime implemented) | Direct `aws_rds_cluster` checks and conservative inheritance for `aws_rds_cluster_instance`; retain standalone behavior and three tools. | Automated Python/Rego/stdio checks pass; existing Codex connection must reload before its final host smoke check. |
| Fifth specification (implemented) | [Specification 005](specifications/unrestricted-ssh-ingress.md): AWS-SG-001, three Terraform rule formats, masked network projection, two-policy integration, M2a–M2e and SG-01–SG-25. | User approved implementation; [SSH evidence](ssh-acceptance.md) records scope, uncertainty, privacy and two-policy accounting. |
| M2: SSH ingress (implemented) | World-wide direct SSH exposure, scoped findings, both-policy selection/listing and representative examples. | SG-01–SG-25 have Python/Rego/stdio/package evidence; live Codex SSH reload check remains separately pending. |
| Sixth specification (implemented) | [Specification 006](specifications/mandatory-resource-tags.md): AWS-TAG-001, default Environment/Owner/Project keys, startup overrides, five taggable types, masked observations and three-policy integration. | User authorized implementation; [TAG evidence](tags-acceptance.md) records source/mask rules, privacy, safe paths, counts and verification. |
| M3: mandatory tags (implemented) | M3a–M3e implement the reviewed specification through the existing tools, with synthetic examples and real acceptance evidence. | TG-01–TG-22 have local/installed-package evidence; no new OPA capabilities, dependency or cloud access. Live-host reload remains separately pending. |
| Seventh specification / M4: S3 protection (implemented) | [Specification 007](specifications/s3-public-access-protection.md): four block flags, conservative bucket links, minimal observations and four-policy dispatch. | [S3 evidence](s3-acceptance.md) maps S3-01–S3-20; M5 acceptance consolidation remains next. |
| v0.1: complete local Terraform MVP | Expand from the first RDS policy to all four policy families; retain the three tools, nested-module/action summaries, structured findings/coverage, examples and local verification commands. | All v0.1 acceptance criteria in `requirements.md` pass, packaged assets work outside the repository, and documented limitations match tested policy coverage. |
| v0.2: packaging and contributor workflow | Docker packaging, expanded governance policies, GitHub Actions CI/CD, improved documentation/examples. | Container runs read-only with constrained mounted plans; CI executes Python/Rego checks with pinned runtimes. Release publishing remains explicitly controlled. |
| v0.3: AWS inspection | boto3 adapter, AWS discovery, cross-account support, mocked AWS integration tests. | Read-only AWS snapshots flow through the shared model; mocked tests require no credentials. Permissions and session boundaries are documented before any live testing. |
| v0.4+ (exploratory) | Drift analysis, Terraform module documentation retrieval, infrastructure cost and operational insights, optional RAG. | Each capability receives a separate design, data-boundary review, acceptance criteria, and tests before implementation. |

Docker, CI workflows, AWS connectivity, cross-account operations, drift, costs,
retrieval, and RAG are not implementation tasks in the v0.1 plan. The architecture
permits future adapters without creating speculative implementations now.

No GitHub pushes, remote publication, or infrastructure changes are authorized by
this roadmap.
