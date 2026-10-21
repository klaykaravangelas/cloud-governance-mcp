# Development setup and verification

Current stage: Specifications 001–005 provide analysis, evaluation, listing,
expanded RDS and SSH ingress coverage. See [current SSH evidence](ssh-acceptance.md),
the [SSH walkthrough](trying-ssh.md) and [M1 evidence](rds-acceptance.md).
Earlier sections below preserve historical checkpoint counts.
See [evaluation evidence](evaluation-acceptance.md), [OPA setup](opa-setup.md) and
[the evaluation walkthrough](trying-evaluation.md). The A1–A7 notes below record
the original analysis increments and their historical check counts.

Task A1 completed 2026-10-16 after approval of
[Specification 001](specifications/analyze-terraform-plan.md). Bootstrap creates
the installable package and development environment. A2 analysis contracts,
A3 contained file loading, A4 Terraform normalization, and A5 analysis
service/summaries are also complete. A6 exposes analysis through MCP stdio;
A7 completes [the client walkthrough](trying-analysis.md) and
[acceptance evidence](analysis-acceptance.md). The first analysis increment is
ready for user familiarization.

## Set up

Install uv, then run from the repository:

```sh
uv sync --locked --no-editable
```

uv reads `.python-version` (3.14.7) and installs the project and development
dependencies in `.venv`. Activation is optional: `uv run` selects that environment.
Use `--no-editable` on both sync and run for the verified workflow. This installs
the package normally, avoiding the local macOS `.pth` issue described below.
The configured uv cache keys rebuild the package when Python source files,
`pyproject.toml`, or `README.md` change, so tests use the current packaged code.
The `src/` layout and installed-package tests prevent accidental imports from the
repository working directory. Keep `uv.lock` with the source; use `--locked` to
reject an out-of-date lockfile rather than silently change it.

Runtime dependencies are the official `mcp` distribution, Pydantic, and AnyIO.
A5 declares AnyIO directly for shielded cancellation cleanup; it was already
installed through the SDK, so no additional packages were needed. Development
dependencies are pytest and Ruff. AnyIO also supplies the async pytest plugin;
the service tests select its asyncio backend explicitly.
No OPA, Terraform, or AWS setup is required for this increment.

## Tested versions

| Component | Version verified on macOS arm64 |
| --- | --- |
| Python | 3.14.7 |
| uv | 0.12.18 |
| MCP Python SDK | 2.3.0 |
| Pydantic | 2.14.1 |
| AnyIO | 4.15.1 |
| pytest | 9.1.1 |
| Ruff | 0.17.1 |
| uv build backend used by the installed uv | 0.12.18 |
| Project package | 0.1.0.dev0 |

The installed SDK exports `mcp.server.MCPServer`, matching the
[official v2.3.0 documentation](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/whats-new.md).
The smoke test imports it and Pydantic in an isolated Python subprocess; no server
is constructed or started by the application package.

## Local checks

```sh
uv run --locked --no-editable pytest
uv run --locked --no-editable ruff check .
uv run --locked --no-editable ruff format --check .
uv lock --check
uv sync --locked --no-editable --check
uv pip check --python .venv/bin/python
uv build
```

Bootstrap results: one package smoke test passed, Ruff lint/format passed, the
lockfile/environment checks passed, and dependencies were consistent. The smoke
test imports the installed package, its distribution metadata, `MCPServer`, and
Pydantic from a temporary working directory with Python isolated mode enabled.
It checks that imports exit successfully without stdout/stderr or server startup.
Analysis acceptance cases AN-01–AN-15 are not complete at this stage.

## Analysis contracts (A2)

At A2, the suite had **131 passing tests**. It covers strict input/settings
validation, identity and instance-key preservation, both replacement orders,
mask path types and inventory uncertainty, count/resource consistency, fixed
warning text and coverage status, JSON/schema round trips, and safe public errors.
A second installed-package test verifies that core contract imports are quiet and
do not load MCP. No additional dependencies were installed for A2.

`models.py` owns Pydantic contracts; `config.py` validates operator settings without
filesystem access; `errors.py` owns fixed codes/messages. The public resource
shape excludes internal mask metadata. Settings preserve root order and validate
absolute-path syntax; A3's loader checks directories, opens descriptors, and
enforces containment. The contracts alone do not read or analyze a Terraform file.

Input/settings callers use `validate_analysis_input` and
`validate_analysis_settings` to translate raw validation exceptions into safe
application errors. Pydantic input hiding is defense in depth; `errors()` and
rejected extra-field names must never be returned or logged directly. Later
adapter/service/transport boundaries must translate their internal failures too.

The report models reject inconsistent summaries but do not compute them. The
actual summary builder is implemented in A5. Contract checks cover portions of the analysis
acceptance matrix; they do not establish file containment or MCP tool behavior.

## Contained JSON loader (A3)

`files.py` now implements `RestrictedPlanLoader`. Use its context manager to close
the roots pinned at startup:

```python
from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.files import RestrictedPlanLoader

settings = AnalysisSettings(allowed_roots=["/absolute/path/to/allowed"])
with RestrictedPlanLoader(settings) as loader:
    document = loader.read_plan("plans/example.json")
    # Internal sensitive JSON: pass to the adapter, never print/log it.
```

Supply an existing directory and completed plan file in place of the example
paths. The loader reads JSON objects; A4's adapter performs Terraform
envelope/format/resource validation. The API is synchronous and will run off the event loop in the later
async service. Admission/concurrency control belongs to that service, not this
file component.

Roots are resolved once as trusted operator configuration. Each root's directory
descriptor stays open until `close()` or context exit. Relative paths always use
the first root. Absolute paths match configured or canonical root aliases by
components, with the most specific match winning. Request paths are never resolved
through symlinks. Any `..` component or symlink below the selected root is denied,
including symlinks targeting another file inside it.

Descriptor-relative no-follow opens and checks of the opened inode prevent a
component swap from redirecting reads through a link. Known directories, devices,
FIFOs, sockets and missing files are rejected as unavailable. Nonblocking file
opens also prevent a file-to-FIFO race from hanging the loader. Only regular-file
descriptors are read. Root/per-read descriptors close on failures and interrupted
reads; closing the loader is idempotent and blocks future calls safely.

The loader enforces the settings' byte/depth budgets. It reads no more than the
byte limit plus one, handles short/growing reads, and scans container depth before
recursive JSON decoding. JSON must be UTF-8 without a BOM, duplicate keys,
non-finite constants, or numeric overflow. Syntax failures return fixed application
errors without parser excerpts, filenames, or plan values. Resource counts are
bounded by A4's adapter; A5's service enforces response-size limits.

At A3, the suite had **191 passing tests**, including **60 loader cases** covering
real filesystem containment, special files, controlled path swaps, byte/depth
boundaries, strict decoding, startup errors, and descriptor cleanup. The package
import test now includes the loader and still confirms no MCP dependency is loaded
by core imports. No dependencies were added in A3. Verified on macOS arm64; the
implementation checks Linux primitives but has not been executed on Linux here.

The real Unix-domain socket fixture is local filesystem setup, with no external
service. The Codex sandbox blocked its creation, so the complete passing suite
was run with authorized host permissions. Use that execution context if sandbox
socket restrictions prevent the fixture; do not skip it or weaken the test.

Unsupported platforms or missing secure-open capabilities fail startup with
`UnsupportedPlatformError`; invalid configured directories use `ConfigurationError`.
Callers should supply stable files: directory descriptors pin target objects, not
an atomic content snapshot of a file being rewritten in place. These boundaries
follow the approved specification. Official API references:
[Python os](https://docs.python.org/3.14/library/os.html#os.open) and
[Python json](https://docs.python.org/3.14/library/json.html#json.load).

## Terraform adapter (A4)

`adapters/terraform.py` implements the pure `TerraformPlanAdapter`; mask helpers
live in `normalization.py`. The adapter accepts decoded objects from the loader,
validates the consumed Terraform envelope and identities, then merges changes
with recursively visited planned inventory by exact address. It has no filesystem
access, MCP imports, provider schemas, Terraform execution, or policy engine.

For example, use the repository's synthetic mixed plan with an explicit root:

```python
from pathlib import Path

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.files import RestrictedPlanLoader

settings = AnalysisSettings(allowed_roots=[str(Path("tests/fixtures/plans").resolve())])
adapter = TerraformPlanAdapter(
    max_resources=settings.max_resources,
    max_depth=settings.max_json_depth,
)
with RestrictedPlanLoader(settings) as loader:
    snapshot = adapter.normalize(loader.read_plan("mixed_nested.json"))

# Seven identities/actions are available to the later summary builder.
assert len(snapshot.resources) == 7
```

Run this from the checkout in the uv environment. This is a core API example;
the public `PlanAnalysis` is available through A5's service below; the MCP command
is available through A6's entrypoint below.
Do not print the loader's document or log identity/mask strings. Resource addresses
remain opaque: module membership comes from explicit fields or the inventory
tree, including nested modules with quoted instance keys.

`ResourceSnapshot` retains resource identities/actions, source provenance, fixed
coverage warnings, and internal typed mask paths. It discards all before/after,
inventory, variable, output, and other attribute values. Sensitive masks are
unioned conservatively across sources; an ancestor path covers its descendants,
and `[]` covers the whole resource. Unknown masks stay separate; an absent
`after_unknown` or inventory-only entry leaves unknown metadata incomplete.
The public resource projection contains neither masks nor attribute values.

Change actions preserve both replacement orderings. Change-only deletions remain
visible; inventory-only entries use `unreported`, never an inferred no-op.
Duplicates, identity conflicts, invalid consumed shapes, unsupported actions and
deposed objects fail safely. Resource/string/depth limits produce no truncated
snapshot. Coverage gaps produce sorted fixed warnings, not compliance decisions.

At A4, the suite had **369 passing tests**: the prior 191 plus **178 new cases**
for masks, adapter behavior and real loader-to-adapter integration. Tests include
the seven-category mixed plan, nested/indexed resources, both replacement orders,
source conflicts/duplicates, empty/partial plans, warning counts, limits, strict
types, and secret omission from serialized snapshots, errors and captured logs.
Core imports remain quiet and independent of MCP. Ruff lint/format and source/wheel
checks pass. No dependencies were added for A4.

The [fixture inventory](../tests/fixtures/plans/README.md) explains each synthetic
JSON file. Contrasting RDS encryption values are prepared for later evaluation;
A4 makes no compliance judgment. Illustrative HCL under
`examples/terraform/analysis` uses the built-in `terraform_data` resource to show
root, module, count and for_each identities. It is not a fixture generator and was
not executed. The adapter's Terraform structures follow the
[official JSON format reference](https://developer.hashicorp.com/terraform/internals/json-format);
limits, warnings, and accepted-feature boundaries follow Specification 001.

## Analysis service and summaries (A5)

`analysis.summarize(snapshot)` calculates a validated public `PlanAnalysis`:
one count per merged resource, all seven action buckets (including zeros), sorted
type counts, managed/data counts, and the number of changing managed resources.
A replacement contributes one to `replace`; data sources never increase managed
changes. Resources are sorted by address. Coverage warnings produce `partial`
status, including inventory-only actions; an available complete empty plan has
zero counts and `complete` status. This status makes no compliance claim.

`AnalysisService` combines the restricted loader, adapter and builder. Use the
same settings for loader and service, and keep the loader open while awaiting
requests. For example, from the checkout in the uv environment:

```python
import asyncio
from pathlib import Path

from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.files import RestrictedPlanLoader
from cloud_governance_mcp.service import AnalysisService


async def main():
    settings = AnalysisSettings(
        allowed_roots=[str(Path("tests/fixtures/plans").resolve())]
    )
    with RestrictedPlanLoader(settings) as loader:
        service = AnalysisService(settings, loader=loader)
        return await service.analyze("mixed_nested.json")


report = asyncio.run(main())
assert report.summary.total_resources == 7
assert report.summary.changing_resources == 4
assert report.analysis_status == "partial"
```

The mixed fixture's summary is:

```json
{
  "total_resources": 7,
  "changing_resources": 4,
  "by_action": {
    "create": 1, "update": 1, "delete": 1, "replace": 1,
    "no_op": 1, "read": 1, "unreported": 1
  },
  "by_type": {
    "aws_ami": 1, "aws_db_instance": 1, "aws_instance": 2,
    "aws_s3_bucket": 1, "aws_security_group": 1, "google_storage_bucket": 1
  },
  "by_mode": {"managed": 6, "data": 1}
}
```

The complete report also contains public resources and fixed warnings. Its
`CHANGE_ACTIONS_UNREPORTED` warning has count 1, explaining partial status. Masks,
attribute values, raw paths and compliance findings are absent. If text output
is needed, serialize only this safe object with `report.model_dump_json()`.

The service validates path arguments before file access. One instance admits one
analysis; overlapping requests get `SERVER_BUSY` immediately, without a pending
analysis queue. A6 keeps one instance per server. File/JSON,
normalization, summary and serialization-size work all run in an executor thread
so the event loop stays responsive. This service supports asyncio and AnyIO's
asyncio backend; Trio is not implemented.

`max_analysis_bytes` bounds the full compact UTF-8 encoding from
`PlanAnalysis.model_dump_json()`, including nulls/zero buckets. A result exactly at
the limit succeeds; one byte over returns `ANALYSIS_LIMIT_EXCEEDED`. The service
never truncates a response. This limit excludes MCP protocol framing and pretty
printing, which belong to A6's transport behavior.

Cancellation waits for the active worker to finish and close per-read descriptors,
then propagates cancellation and releases admission without returning a report.
Both repeated native task cancellation and AnyIO scope cancellation are tested.
Threads cannot be forcibly stopped, so cancellation can wait for a slow filesystem
read. The caller retains ownership of the loader's pinned root descriptors and
closes them after active calls have completed.

Known failures retain fixed catalog codes. Unexpected failures become
`INTERNAL_ERROR` and log only a fixed code plus a generated request ID, with no
exception text or traceback. Workers return failures as codes rather than raising
them through executor futures; this avoids Python 3.14's logging of exceptions
from cancelled shielded futures. Implementation decisions were checked against
the installed Python 3.14.7 implementation, the
[Python asyncio documentation](https://docs.python.org/3.14/library/asyncio-task.html#shielding-from-cancellation),
and [AnyIO cancellation documentation](https://anyio.readthedocs.io/en/stable/cancellation.html#shielding).

At A5, the suite had **427 passing tests**, including **58 new summary/service
cases**. They verify mixed and replacement counts, empty/partial coverage,
determinism, independent public projections, secret/mask omission, input/output
limits, safe failures and recovery, execution off the event loop, no queued
overlap (also across event loops), and cancellation with real descriptor cleanup.
The full suite includes the existing local socket fixture and passed with host
permissions. Ruff checks and source/wheel verification pass. A fresh wheel install
also runs the service outside the checkout, without importing MCP in the core.
No Terraform, AWS, OPA, or runtime child processes are involved. A6 adds SDK tool
discovery and real stdio tests.

## MCP interface and stdio (A6)

After `uv sync --locked --no-editable`, launch from the checkout with an existing
absolute root. For the synthetic examples:

```sh
uv run --locked --no-editable cloud-governance-mcp --allowed-root "$PWD/tests/fixtures/plans"
```

The equivalent module entrypoint is:

```sh
uv run --locked --no-editable python -m cloud_governance_mcp --allowed-root "$PWD/tests/fixtures/plans"
```

These commands start a stdio server waiting for MCP input. An MCP host should
launch it as a subprocess, then call `analyze_terraform_plan` with, for example,
`{"plan_path": "mixed_nested.json"}`. No banner or analysis is printed on startup;
stdout is reserved for protocol frames. Closing stdin shuts down cleanly. Imports
of `server` and `__main__` are quiet and start no server. The final host/client
walkthrough is available in [Try Terraform plan analysis](trying-analysis.md).

Only `analyze_terraform_plan` is discoverable. It publishes the exact Pydantic
input/output schemas and read-only, non-destructive, idempotent, closed-world
annotations. Its successful text is compact `PlanAnalysis` JSON and its structured
content is the same object. Neither contains raw plan attributes or internal
masks. Partial coverage is a successful report with warnings, not a tool error.

The operator supplies configuration on startup; tool callers supply only
`plan_path`. Roots are pinned before stdio starts. Relative plan paths use the
first root, and request paths are never expanded/unquoted. Client roots do not
grant access. Repeat `--allowed-root` to configure additional trusted directories.

| Option | Default / requirement |
| --- | --- |
| `--allowed-root` | Required existing absolute directory; repeatable in priority order. |
| `--max-plan-bytes` | 10,485,760; positive integer. |
| `--max-json-depth` | 128; positive integer. |
| `--max-resources` | 10,000; positive integer. |
| `--max-analysis-bytes` | 4,194,304; positive integer. |
| `--help` / `--version` | Print CLI information and exit successfully without requiring roots. |

Bad configuration exits with status 2 and a fixed stderr diagnostic, without
echoing the supplied path, flag or value. Unsupported secure-file platforms also
exit with status 2 and a fixed explanation. Unexpected startup failures exit 1
with a fixed `INTERNAL_ERROR` log and request ID; an interrupt exits 130.
Application and SDK debug logs are disabled by the CLI; diagnostics go to stderr.
macOS is verified here; Linux execution remains to be performed on Linux.

`server.create_server(service)` uses the SDK's public low-level `Server` with
constructor handlers. This is a deliberate choice: the `MCPServer` decorator
path can echo rejected validation inputs/field names, while its default argument
model ignores extras. Our handler validates against `AnalyzeTerraformPlanInput`
and returns fixed catalog-controlled errors before those convenience-layer paths
are involved. No private SDK overrides or provisional middleware are used.
Schemas are generated from the same core models that validate inputs/reports.
The pinned SDK is still the official `mcp` 2.3.0 package; no dependencies were
added for A6. The SDK's high-level class remains available and covered by the
bootstrap import test.

Known-tool failures return `isError=true`, one fixed text message and no structured
success payload. Unexpected service/result/serialization failures are caught
before SDK crash logging and expose only `INTERNAL_ERROR`; logs contain a fixed
code/request ID, without exception text/tracebacks. Unknown tools receive a fixed
`INVALID_PARAMS` protocol error. Malformed protocol parameters remain SDK-managed:
raw-frame tests confirm pre-handler failures contain no Pydantic excerpts or
rejected values. MCP Python properties use snake_case (`is_error`,
`structured_content`); the wire uses `isError` and `structuredContent`.

Tests use SDK `Client` in both `auto` (modern 2026-07-28) and `legacy`
(initialize-based 2025-11-25) modes. They cover discovery/schemas/annotations,
matching text/structured results, all representative fixture reports, fixed
argument/service failures, output/resource limits, and overlapping calls.
Cancellation reaches the service and drains a real open file before admitting
another call. The direct in-process client joins that handler during cancellation;
legacy request cancellation can finish at the client before server cleanup ends.

Real stdio tests launch both installed entrypoints outside the checkout using
SDK clients. A raw JSON-RPC transcript additionally verifies initialization,
pre-handler malformed arguments, tool errors, malformed-frame recovery,
protocol-only stdout, empty stderr and clean EOF exit. At A6, the suite had
**511 passing tests**, including **84 new SDK/CLI/stdio cases**. Full execution
includes the existing socket fixture and passed with host permissions; Ruff,
lock/environment/dependency checks and source/wheel builds pass. A fresh wheel
installation also serves real stdio outside the checkout. AWS credentials,
Terraform, OPA, network services and application child processes are unnecessary.

Implementation was checked against the installed SDK and current official
[low-level server documentation](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/),
[structured output documentation](https://py.sdk.modelcontextprotocol.io/servers/structured-output/),
[SDK v2.3.0 migration notes](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/migration.md),
and [MCP tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## First analysis increment completion (A7)

The [hands-on guide](trying-analysis.md) and `examples/client.py` provide an
executable first session. The example launches the fixed server module via the
same Python interpreter, lists tools and prints a public report, or returns a
nonzero status with safe text for errors. It never reads raw plan files. Its
default fixture root is explicit server configuration; the server still has no
default root. No AI model or API key is needed for the example client.

The saved `examples/reports/mixed-analysis.json` was obtained from the real stdio
client. It contains seven resources, four managed changes and one unreported
warning. `tests/test_walkthrough.py` checks it in both auto/legacy modes from an
unrelated working directory, plus discovery, other sample plans and safe errors.
No server tool or runtime dependency was added for A7.

The full suite has **521 passing tests**, including **10 new walkthrough cases**,
with no skips. Ruff, lock/environment/dependency checks, source/wheel builds and
fresh installed-wheel stdio verification pass. Versions remain the table above.
The [acceptance record](analysis-acceptance.md) maps all AN-01–AN-15 cases to
concrete tests, records independent distribution checks, and separates the
analysis scope from future policy requirements and unverified platforms.

## Distribution verification

`uv build` creates a source distribution and builds its wheel under ignored
`dist/`. The native [uv backend](https://docs.astral.sh/uv/concepts/build-backend/)
uses `src/cloud_governance_mcp` as the module root. Package files, including future
data assets placed under that module, follow its inclusion rules. Tests are
included in the source distribution alongside examples, saved reports, docs,
`AGENTS.md`, `.python-version` and `uv.lock`. These source/development assets are
excluded from the wheel. Production policy assets are now packaged with the
application; no placeholder future adapters are included.

The bootstrap wheel was installed with its runtime dependencies into a separate
temporary virtual environment outside the repository. Imports and distribution
metadata were verified there, including that the imported application lives in
that environment's site-packages. Dependency consistency was checked with
`uv pip check`. The wheel contains the Apache license and application package,
without tests or documentation folders.

To repeat installation verification, use a fresh external environment and an
absolute path to the wheel built by `uv build`:

```sh
uv venv --python 3.14.7 /tmp/cloud-governance-wheel-check
uv pip install --python /tmp/cloud-governance-wheel-check/bin/python /absolute/path/to/cloud_governance_mcp-0.1.0.dev0-py3-none-any.whl
```

From a directory outside the checkout, run that environment's Python with `-I`
and import `cloud_governance_mcp`, `MCPServer` from `mcp.server`, and Pydantic.
Use an unused temporary directory for each verification; these are development
commands, not application functionality.

## Observed macOS editable-install issue

During bootstrap, the new `.venv`'s `.pth` files had the macOS hidden flag set.
Python ignored them, so the editable application import failed. Clearing the
flags restored imports in that command but the flags recurred in subsequent
commands. That correction was not durable in this environment.

The verified workflow uses uv's supported regular installation mode instead:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable pytest
```

This avoids the application's `.pth` file without changing import paths or
weakening tests. Include the flag on subsequent uv sync/run commands; omitting it
reverts the project to editable installation. On an unaffected development
environment, default editable installs remain available by omitting the flag.
The independent wheel installation also passed verification. No application or
test code clears filesystem flags.

## Policy evaluation (E1–E5)

Verified 2026-10-19: 643 Python tests (no skips), 7 real Rego tests, Ruff lint/format
and uv lock/environment/dependency checks pass. Python dependencies remain locked
without additions. OPA 1.21.2 is an explicitly configured local executable,
checksum-verified on macOS arm64; see [setup](opa-setup.md). Runtime assets live
inside the package and are included by uv_build; test Rego stays under tests.

At E5 the server advertised analysis and evaluation even without OPA configuration;
L1 now adds catalog-only listing as its third tool.
Analysis remains independent; evaluation returns a safe configuration error report
after reading a valid plan if no evaluator was supplied. Add `--opa-path` to the
host's startup arguments. The six evaluation budgets and exact defaults are in
[Specification 002](specifications/evaluate-terraform-policies.md#runtime-selection-configuration-and-limits)
and `--help`; all are operator-only. Each tool admits one active request without
a queue, independently. The OPA child receives only locale variables and is
terminated/killed/reaped on failure, overflow, timeout or cancellation.

See [the walkthrough](trying-evaluation.md) for the two-policy-outcome comparison,
exact checks, analysis-only test selection and host process settings, and
[the acceptance record](evaluation-acceptance.md) for EV-01–EV-24 evidence and
platform/scope limitations.

## Policy listing (L1a–L1d)

Specification 003 adds `list_policies` from the evaluator's packaged catalog,
without new dependencies or OPA/plan access. The catalog explicitly records empty
policy-specific configuration requirements for AWS-RDS-001. Internal reasons stay
private; existing analysis/evaluation report contracts and Rego decisions remain
unchanged. The listing service uses a separate one-request slot, an executor for
catalog/projection/UTF-8 size work, a 65,536-byte public report limit and protected
worker cleanup on cancellation. No new CLI configuration is required.

Verified on 2026-10-19: **702 Python tests, no skips**, **7 Rego tests**, Ruff
lint/format and locked dependency checks. See the
[listing acceptance record](listing-acceptance.md) for installed-package checks and
LP-01–LP-14 evidence. Use the [listing walkthrough](trying-listing.md) or run:

```sh
uv run --locked --no-editable python examples/client.py --list-policies
uv run --locked --no-editable python examples/client.py --list-policies --legacy
```

The saved response is `examples/reports/policy-list.json`. `--list-tools` continues
to discover MCP functions, whereas `--list-policies` discovers governance rules.
All three tools are now exposed. Specification 004 expands RDS coverage below.

## Expanded RDS encryption (M1)

Approved Specification 004 adds AWS-RDS-001 v1.1.0 for standalone instances,
direct clusters and conservative cluster-member inheritance. `rds_associations.py`
uses transient masked identifiers/ARN context and linear indexes, keeping only
safe states and a resolved Terraform address. Member encryption copies are ignored;
OPA owns the decision using the target's projected encryption. The graph input
is schema 2, while public/engine report envelopes remain schema 1. No dependencies,
CLI options, capabilities or tool inputs changed.

Verified 2026-10-21: **826 Python tests, no skips**, **13 real Rego tests**,
Ruff, locked environment/dependency checks and source/wheel builds. See the
[acceptance record](rds-acceptance.md) for installed checks and the existing
Codex process's pending reconnect smoke test. The three new fixture/report pairs
show pass, fail and unknown-ARN uncertainty; they require no AWS credentials or
Terraform execution. Follow the [cluster walkthrough](trying-rds-clusters.md).

## SSH ingress and two-policy evaluation (M2)

Approved Specification 005 adds AWS-SG-001 v1.0.0 while keeping AWS-RDS-001
v1.1.0. Omission now selects both IDs; use explicit selection for historical
RDS-only report comparisons. `ssh_models.py` and `ssh_projection.py` provide
strict masked observations for inline, legacy and modern rules. Rego owns
exposure decisions. Engine input is schema 3, while public/engine output and
catalog envelopes remain schema 1. No dependency, tool or CLI setting was added.

Verified 2026-10-21 on macOS arm64: **1,009 Python tests, no skips**, **29 real
Rego tests**, Ruff lint/format (88 files), strict Rego/format, uv lock/environment/
dependency checks and source/wheel builds passed. The documented OPA-free subset
passed **857 tests** with `CLOUD_GOVERNANCE_OPA=/not/installed/opa`. Host permissions
allowed the required local Unix socket case; no AWS credentials or Terraform were
needed. See [verification commands](trying-evaluation.md#5-verify-locally).

Separate fresh wheel/source installations outside the checkout passed SDK
auto/legacy stdio checks with isolated imports, console/module entrypoints, both
policies, analysis, eight saved report comparisons, the policy-selection matrix
and containment denial. Production files/assets matched source byte-for-byte;
test Rego and the OPA binary stayed out of the wheel. Details and SG-01–SG-25
traceability are in [SSH acceptance](ssh-acceptance.md). Follow the
[SSH walkthrough](trying-ssh.md) for manual calls. Live Codex SSH reload testing
and Linux execution remain separately unverified.
