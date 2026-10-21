# Expanded RDS encryption acceptance record

This is the M1 checkpoint. [SSH acceptance](ssh-acceptance.md) records the current
two-policy runtime and later verification; select RDS explicitly to reproduce the
reports here.

Specification 004 was approved for implementation. Verified locally on
2026-10-21, macOS arm64, Python 3.14.7, MCP SDK 2.3.0 and OPA 1.21.2.
M1a–M1d are implemented; M1e has one outstanding live Codex reload check described
below. Linux execution remains unverified. No AWS or Terraform commands were run.

## Executed checks

- Full Python suite: **826 passed, no skips**, including the real local Unix
  socket fixture with host permissions, real OPA and MCP auto/legacy stdio.
- OPA-free documented selection: **731 passed, no skips**, with
  `CLOUD_GOVERNANCE_OPA=/not/installed/opa`; pure graph/adapter, analysis and
  listing checks did not require an evaluator.
- Real Rego: **13/13 passed**; strict compilation and formatting passed with the
  existing restricted capabilities. Network/runtime/schema-fetch denial tests
  remain in the Python suite.
- Ruff lint and formatting, `uv lock --check`, locked non-editable environment
  check and dependency consistency passed. No dependency or capability was added.
- Final wheel inspection matched all 29 production Python/policy asset files to
  current source and excluded development assets. Source inspection verified
  current specifications, acceptance, tests, fixtures, reports, HCL, lock and guidance.
- Source and wheel builds passed. Separate external environments installed the
  wheel and built/installed the source archive with exact runtime dependencies
  exported from `uv.lock`. Both passed dependency consistency and real stdio
  outside the checkout, in auto/legacy modes: three tools, v1.1 listing, unchanged
  analysis golden, all three cluster reports and out-of-root denial. Imports
  resolve to each environment's own site-packages. Source installation was
  offline; the initial wheel dependency installation needed network because local
  cache metadata was incomplete. Evaluation itself used no network.
- Saved reports were captured from real SDK stdio requests, not authored by hand.
  Golden tests compare current output in both legacy/modern coverage and fresh
  subprocesses. Public tool inputs and report envelope versions remain unchanged;
  catalog values/reason enums expand as specified, and engine input is 2.

Use the commands in [development](development.md),
[evaluation verification](trying-evaluation.md#5-verify-locally) and the
[cluster walkthrough](trying-rds-clusters.md). Full verification requires real
OPA; pure analysis/listing/adapter checks require neither OPA nor AWS.

## Requirement evidence

| Cases | Evidence |
| --- | --- |
| RD-01 | Existing `test_evaluation_contracts.py`, `test_evaluation_service.py` and unchanged analysis golden; `test_rds_pipeline.py` verifies byte-equivalent public analysis and unchanged source data. |
| RD-02–RD-03 | `test_rds_evaluation.py` checks strict direct cluster booleans and invalid/missing states across representative engine strings and nested/indexed addresses; no linkage is required for a direct check. |
| RD-04 | `test_rds_associations.py`, `test_rds_pipeline.py` and existing contracts cover root/attribute/descendant masks, source union, priority and incomplete metadata. |
| RD-05–RD-06 | `rds_m1_test.rego` covers every inherited encryption state and contradictory member copies. Real service tests count three passes/failures; member remediation targets the cluster. |
| RD-07–RD-09 | Pure association cases cover every link state, malformed/missing/masked fields, supported partitions, account/Region mismatch, duplicate keys in reversed order and all incomplete-key blocker combinations. |
| RD-10 | Association/pipeline tests exclude deleted/data/wrong-provider/type targets and prevent fallback to `before` or misleading expression references. |
| RD-11 | Pipeline tests prove change precedence against conflicting inventory for encryption and link fields across create/update/no-op and both replacement orders. Association tests cover absent/null desired state and incomplete masks. |
| RD-12 | Nested/indexed real service addresses are graph keys; matching uses fake desired identifiers/ARNs, not address/name parsing or member ARN resource names. |
| RD-13 | A 10,000-resource pure adapter test counts one linkage extraction per cluster/member and resolves 5,000 unique links. Existing service worker, resource/byte/depth limits, admission and cancellation tests pass. |
| RD-14 | Pipeline and SDK/stdio tests assert unmarked identifier/ARN/account/Region strings are absent from snapshot/repr/OPA projection, text/structured output and logs. Existing sentinel error/failure tests pass. |
| RD-15 | Graph tests reject old schema, duplicate/dangling/self/deleted/data/wrong-provider/type/scope targets and extra association fields. Engine tests reject complete batches with inapplicable reasons; existing malformed/undefined/missing/duplicate output tests pass. |
| RD-16 | Cluster plus two members yields exactly three evaluated checks. Existing partial/empty/data/deletion/unsupported coverage tests and real state-matrix Rego tests pass. |
| RD-17 | Shared catalog/listing tests assert v1.1.0, exactly three supported types and empty configuration. Catalog tests enforce exact 35-reason membership, outcomes and paths. |
| RD-18–RD-20 | Existing regression suites plus `test_rds_evaluation.py` exercise memory/real stdio in auto/legacy modes, unchanged three-tool discovery, safe errors, both output channels, real OPA and existing containment/process/capability boundaries. |
| RD-21 | Synthetic fixtures, illustrative HCL and real saved pass/fail/unknown-ARN reports are complete and tested. Live Codex reload smoke remains pending; see below. |
| RD-22 | Source/wheel builds and two independent installations passed. Both use packaged production assets and run auto/legacy stdio outside checkout; source carries docs/tests/examples while the wheel excludes them. |

## Codex connection observation and remaining check

The actual connected Codex tool `list_policies` was called after the local
package upgrade. It returned fixed `POLICY_ASSETS_INVALID`, rather than metadata:
the already-running server retains v1.0 model definitions while reading updated
v1.1 catalog assets. Fresh SDK stdio subprocesses return v1.1.0 and evaluate all
three cluster fixtures correctly. This is a safe rejection, not a compliance
pass, and is not counted as a successful new-version Codex smoke test.

On 2026-10-21, during the Specification 005 drafting request, the user reported
that the MCP worked when they used it. Record that as successful user-reported
hands-on use, separately from automated traces: exact tool results/counts were
not pasted into this chat. This observer's `list_policies` call still returned
`POLICY_ASSETS_INVALID`. That does not invalidate the user's working session or
require another familiarization session before M2 specification work.

The user authorized a restart if needed. The available Codex CLI exposes no
targeted restart subcommand, and this chat exposes no server-restart control;
no process was killed or configuration rewritten as a workaround. A host restart
control can refresh this observer's connection when available. The user report
does not substitute for an observed transcript of the exact checks below.

Reconnect/restart the configured `cloud-governance-mcp` server in Codex, then
perform actual tool calls (not shell JSON inspection):

1. `list_policies`: AWS-RDS-001 v1.1.0; three resource types.
2. Evaluate `cluster_encrypted.json`: complete/pass; three passed checks.
3. Evaluate `cluster_unencrypted.json`: complete/fail; three failed checks.
4. Evaluate `cluster_unknown_arn.json`: complete/indeterminate; one pass and two
   indeterminate member links.

Record those observed calls before closing M1e/RD-21. No live process was killed,
global Codex configuration changed or GitHub publication performed by this work.

## Scope and limitations

Known unique identifier plus matching partition/account/Region evidence is
required for inheritance. Unknown creation-time ARNs, possible uncertain
duplicates, missing targets and ambiguous links cannot pass. Optional Region
may be absent/null when ARN context is known, but masked Region blocks linkage.
Configuration references are not value proof. Member computed encryption copies
are ignored. Direct cluster encryption does not require link evidence.

The `aws_db_instance` defensive association guard retains its original
indeterminate behavior. Global clusters, SSH, tags and S3 policies remain outside
this increment. No live AWS/provider compatibility campaign or Linux execution
is claimed. Synthetic no-op fixtures deliberately contain contradictory member
copies to test authority; the illustrative HCL is separate and never executed.
