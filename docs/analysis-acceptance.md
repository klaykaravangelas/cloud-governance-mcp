# Analysis increment acceptance evidence

Verified 2026-10-16 on macOS arm64, Python 3.14.7. Tasks A1–A7 complete
[Specification 001](specifications/analyze-terraform-plan.md). This is the first
analysis increment toward v0.1, not the complete three-tool governance MVP.
The [hands-on walkthrough](trying-analysis.md) is ready for local use.

## Scope and result

Exactly one MCP tool is implemented: `analyze_terraform_plan`. It reads a bounded
JSON plan from an explicitly allowed directory and returns a deterministic public
report. It makes no compliance decision, runs no Terraform, OPA, shell or AWS
operations, and applies no changes. The external SDK clients used for examples
and tests launch the server process; the server itself starts no child processes.

The verified stack is uv 0.12.18, MCP SDK 2.3.0, Pydantic 2.14.1, AnyIO 4.15.1,
pytest 9.1.1, Ruff 0.17.1, and application version 0.1.0.dev0. `uv.lock` fixes
dependency versions and `.python-version` selects the tested interpreter.

## Specification traceability

Each row is verified through the listed automated tests and the distribution
checks below. Links identify the files containing the named cases; parameterized
tests exercise both successful and failing boundaries.

| ID | Evidence | Result |
| --- | --- | --- |
| AN-01 | [Package imports](../tests/test_package.py), [CLI startup/help/EOF](../tests/test_cli.py), and independent wheel install/stdio execution. | Quiet installed imports, explicit roots, safe startup failures, and stdio work without OPA. |
| AN-02 | `test_mixed_plan_counts_each_merged_resource_once` in [analysis tests](../tests/test_analysis.py); [SDK fixture calls](../tests/test_server.py); [walkthrough saved-report comparison](../tests/test_walkthrough.py). | Total 7, changing 4, all seven action buckets 1, managed 6/data 1, unreported warning count 1. |
| AN-03 | `test_replacement_order_is_preserved_without_inflating_create_delete` in [analysis tests](../tests/test_analysis.py); ordered-action cases in [adapter tests](../tests/test_terraform_adapter.py). | Both replacement orders preserved; one replace count, no extra create/delete counts. |
| AN-04 | Mixed/nested fixture and `test_opaque_instance_keys_and_moved_metadata` in [adapter tests](../tests/test_terraform_adapter.py). | Recursive modules, numeric index 0, string keys with dots/quotes, provider identity and moved addresses retained. |
| AN-05 | Source provenance, duplicate module/resource tests, cross-source conflicts and inventory-only uncertainty in [adapter tests](../tests/test_terraform_adapter.py). | Exact-address merge without double counting; change-only delete retained; unreported actions remain explicit. |
| AN-06 | Empty/additive plans in [adapter tests](../tests/test_terraform_adapter.py); empty coverage/zero buckets in [analysis tests](../tests/test_analysis.py); empty SDK/stdio reports. | Both minimal envelopes accepted; available complete inventories have no warnings; missing inventories/completeness produce warnings; state/arbitrary documents fail. |
| AN-07 | Partial fixture, import metadata/count and fixed warning tests in [adapter tests](../tests/test_terraform_adapter.py); [service](../tests/test_service.py) and [SDK](../tests/test_server.py) partial reports. | Fixed sorted coverage warnings/counts; excluded payloads do not inflate resource totals or appear in output. |
| AN-08 | [Input contracts](../tests/unit/test_inputs.py), invalid version/shape/action/deposed cases in [adapter tests](../tests/test_terraform_adapter.py), [SDK bad arguments](../tests/test_server.py), and [raw pre-handler errors](../tests/test_stdio.py). | Strict arguments and fixed application/protocol errors; additive fields ignored. |
| AN-09 | [File-boundary tests](../tests/unit/test_files.py): relative/absolute paths, sibling prefixes, symlinks, real special files and controlled component/FIFO swaps; [real stdio denied path](../tests/test_stdio.py). | Descriptor containment enforced, special files rejected without blocking, no symlink escape. |
| AN-10 | Exact byte/depth limits and strict JSON in [loader tests](../tests/unit/test_files.py); source/union/identity limits in [adapter tests](../tests/test_terraform_adapter.py); exact UTF-8 report budget in [service tests](../tests/test_service.py). | At-limit success and over-limit errors; no truncated report or guessed counts. |
| AN-11 | [Mask tests](../tests/test_normalization.py), mask/sentinel adapter cases, [public projection tests](../tests/test_analysis.py), [SDK/stdio privacy tests](../tests/test_server.py), and [walkthrough errors](../tests/test_walkthrough.py). | Typed object/list/root masks retained internally; uncertainty remains explicit; attribute sentinels/masks absent from public channels, errors and captured logs. |
| AN-12 | Source-order permutations in [adapter tests](../tests/test_terraform_adapter.py); deterministic independent reports in [analysis tests](../tests/test_analysis.py); [report contract invariants](../tests/unit/test_models.py). | Sorted stable identities/type keys, correct partition sums/changing count, zero buckets present, mutable snapshots cannot change returned reports. |
| AN-13 | [SDK discovery/schemas/annotations](../tests/test_server.py), validated matching text/structured reports, fixed known-tool errors, and [raw SDK pre-handler failures](../tests/test_stdio.py). | Exactly one tool; strict input/output contracts; safe `isError` results; no success payload on failures. |
| AN-14 | [Real SDK stdio](../tests/test_stdio.py), console/module launches outside checkout, raw initialization/JSON-RPC transcript, and independent fresh-wheel subprocess verification. | Modern auto and legacy initialization modes work; denied/invalid calls recover; protocol-only stdout, quiet stderr and clean EOF exit. |
| AN-15 | [Service cancellation/failure/admission tests](../tests/test_service.py), [SDK overlap/cancellation](../tests/test_server.py), and [descriptor cleanup tests](../tests/unit/test_files.py). | Immediate `SERVER_BUSY`, no analysis queue, real descriptor cleanup, cancellation propagated after worker completion, subsequent calls succeed. |

This covers FR-01–FR-04, the parsing/mask portion of FR-09, and the analysis
portions of SEC-01, SEC-02, SEC-03, SEC-05, SEC-06 and SEC-07 in
[requirements](requirements.md). OPA side effects, encryption checks, policy
outcomes and evaluation-process deadlines belong to the evaluation increment;
they are not marked satisfied by these analysis tests.

## Verification commands and recorded results

Run from the checkout after `uv sync --locked --no-editable`:

```sh
uv run --locked --no-editable pytest
uv run --locked --no-editable ruff check .
uv run --locked --no-editable ruff format --check .
uv lock --check
uv sync --locked --no-editable --check
uv pip check --python .venv/bin/python
uv build
```

Results: **521 tests passed, none skipped**, including 10 new walkthrough cases.
Ruff lint/format, lock/environment/dependency consistency, source/wheel builds,
documentation links, JSON examples and saved-report validation passed. The
walkthrough commands were also run through real MCP stdio. The Codex execution
environment used an explicit cache under `/private/tmp` and offline resolution
for installed packages; the commands above use uv's normal cache location.

The full suite needs host permissions in this environment because its real local
Unix-domain socket fixture cannot bind inside the Codex sandbox. It does not
connect to an external service. The passing full run used host permissions;
the socket test was not skipped or replaced with a mock.

## Distribution verification

The wheel contains application modules, metadata, console entrypoint and license;
it excludes tests, fixtures, examples, documentation and policy placeholders.
The source distribution additionally includes tests/fixtures, examples/client,
the saved report, documentation, repository guidance, `.python-version` and
`uv.lock`, so the walkthrough and verification material travel with the source.

The built wheel was installed with its runtime dependencies into a fresh uv
environment outside the checkout. From a separate working directory, its Python
in isolated mode imported the application from that environment and used the
official SDK to launch that environment's console server. Both auto and legacy
clients discovered the single tool, validated the mixed and sensitive sample
reports, checked denied/invalid errors, and shut down without unexpected stderr.
The server's executable search path was empty, proving no Terraform/OPA binary
was needed. Dependency consistency passed in the independent environment.

To repeat with a new temporary environment (choose unused paths):

```sh
uv build
uv venv --python 3.14.7 /tmp/cloud-governance-wheel-check
uv pip install --python /tmp/cloud-governance-wheel-check/bin/python /absolute/path/to/repo/dist/cloud_governance_mcp-0.1.0.dev0-py3-none-any.whl
cd /tmp
/tmp/cloud-governance-wheel-check/bin/python -I /absolute/path/to/repo/examples/client.py --allowed-root /absolute/path/to/repo/tests/fixtures/plans
```

That example client launches the server from its own Python environment. Repeat
with `--legacy`, `--list-tools`, and `--plan-path malformed.json`; the malformed
case should exit 1 with `INVALID_PLAN` on stderr. These are development/client
commands, not operations exposed by the server.

## Boundaries and remaining work

- Executed on macOS arm64. Linux secure-open support is implemented but has not
  been run on Linux here. Unsupported secure-file platforms fail startup.
- Runtime is Python 3.14+ with the versions above actually tested; no claim is
  made about untested future dependency/interpreter versions.
- Fixtures are synthetic. No live-account inspection or Terraform-generated plan
  compatibility campaign was performed. The HCL examples were not executed.
- Cancellation joins a synchronous worker; it cannot forcibly stop a slow
  filesystem read. Pinned roots do not make file contents an atomic snapshot:
  provide completed, stable files.
- Identities can contain operator-chosen keys and are intentionally returned.
  Attribute values and mask paths are not returned. Analysis completeness does
  not establish compliance, deployment state, or whether a plan can apply.
- No policy tool/catalog, Rego/OPA integration, AWS adapter, HTTP transport,
  Docker, CI workflow or publishing is included. Full v0.1 remains planned.

The next development increment defines evaluation contracts/catalog and a
redacted desired-state projection before adding one real Rego policy. User
familiarization can proceed now through [the walkthrough](trying-analysis.md).
