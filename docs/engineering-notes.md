# Engineering notes

Detailed implementation contracts and compatibility decisions live here so
`AGENTS.md` can remain focused on durable contributor guidance. Read the relevant
specification before changing these boundaries; the specification defines the
accepted behavior. Historical task labels below identify where decisions arose.

## Current SSH and multi-policy contracts

Specification 005 advances engine input to schema 3; engine output, catalog and
public reports remain schema 1. `contracts.py` supplies the strict shared model
base, `ssh_models.py` defines value-free observations, and `ssh_projection.py`
parses only selected SSH inputs. `policy_definitions.py` supplies fixed IDs and
strict per-ID metadata checks without import-time I/O.

Omitted selection chooses both policies. RDS-only calls never inspect SSH values
or work ceilings; SSH-only calls never build RDS associations. Candidate resources
are the selected-type union, while checks cover every selected policy/resource
pair. Each request still uses one OPA evaluation and atomic batch validation.

SSH collection masking cannot align unordered inline rules across sources by
position: consumed sensitivity withholds the collection. Unknown/missing values
are preserved as states. Raw CIDRs and reference IDs never reach OPA. Rego owns
the three-valued exposure predicate; `lte` is the only added capability. Fixed
10,000-rule/50,000-source-entry ceilings complement unchanged byte/time budgets.
See [Specification 005](specifications/unrestricted-ssh-ingress.md) and
[SSH acceptance](ssh-acceptance.md) for complete contracts and evidence.

## Implementation conventions

- Use a `src/cloud_governance_mcp/` layout, type annotations, small cohesive
  components, constructor/function dependency injection, and strict boundary
  validation. Preserve provider attributes in the internal model.
- A2 implements `models.py`, `config.py`, and `errors.py` without MCP imports.
  Public `ResourceAnalysis` contains identities/actions only; internal
  `NormalizedResource` wraps it with mask paths and uncertainty metadata.
  Settings validate root syntax/order and limits; A3's `RestrictedPlanLoader`
  checks directories and uses pinned root descriptors with no-follow component
  opens. Use it as a context manager and never log its raw JSON output. It is
  synchronous; the later async service must dispatch it off the event loop.
  A4's `TerraformPlanAdapter.normalize` validates Terraform and merges resources
  by exact address; `normalization.py` extracts/canonicalizes typed mask paths.
  Addresses are opaque; obtain module membership from explicit metadata/the tree.
  Analysis discards provider values after mask extraction. Evaluation opts into
  the required RDS projection during that same normalization pass, after source
  mask union; it retains only a known encryption boolean and value-free states. Inventory-only
  actions stay unreported; absent unknown masks remain incomplete internally.
  Reuse safe entrypoints
  for input/settings. Never expose raw Pydantic errors: hiding input values does
  not hide rejected field names or make `errors()` safe for public output.
- A5's `analysis.summarize(snapshot)` computes the public `PlanAnalysis` without
  internal masks. `AnalysisService(settings, loader=...)` coordinates the full
  pipeline through `await service.analyze(plan_path)`. Keep one service instance
  per server and inject a loader using the same settings; the caller owns its
  root-descriptor lifetime. The API targets asyncio/AnyIO's asyncio backend.
- Service admission is nonblocking: one active analysis, no analysis wait queue.
  All file/JSON/adapter/summary/UTF-8 size work runs in an executor thread. Wait
  for worker cleanup before releasing admission on cancellation, then propagate
  cancellation. Shield cleanup against AnyIO scope and repeated native task
  cancellation. Return worker failures as safe codes: Python 3.14 shield callbacks
  may log exceptions even after retrieval. Never let raw worker failures reach
  those callbacks. Unexpected failures log only a fixed code and request ID.
- `max_analysis_bytes` measures the complete compact UTF-8 `PlanAnalysis` JSON,
  including nulls and zero buckets, before returning it. Protocol envelopes and
  formatting are outside this budget. Never truncate. SDK text must serialize
  only the same public report; no transport may read internal masks/raw plans.
- Use current official MCP SDK and OPA documentation for decisions. Check the
  installed/pinned SDK generation; bootstrap locks MCP 2.3.0. A6 uses its public
  low-level `mcp.server.Server`, not the `MCPServer` decorator layer: explicit
  Pydantic schemas/validation avoid input-bearing SDK argument errors/logs.
  `server.create_server(analysis, evaluation, listing)` creates three tools; an analysis-only
  injection remains supported for isolated tests. `run_stdio` serves them.
  Return both MCP text and structured content from the same validated public
  report. Return fixed `is_error` tool results; unknown tools are fixed protocol
  errors. Keep unexpected exception details away from SDK crash logging.
- `__main__.py` and the `cloud-governance-mcp` console script own startup. Require
  repeatable `--allowed-root` and validate all four limit options. Pin roots before
  SDK serving; close after handlers drain. Evaluation has separate settings,
  one independent active slot/no queue, lazy bounded version verification and no
  implicit executable. Missing OPA never disables analysis. See the evaluation
  specification for the additional CLI budgets and fixed error/report mapping. CLI errors replace argparse's echoed
  inputs with fixed diagnostics. SDK debug logging is disabled; stdout belongs to
  MCP. Module imports must remain quiet and must not open roots/start a server.
- Use SDK `Client` tests in auto and legacy modes. Current auto mode uses modern
  MCP; legacy mode exercises initialize/JSON-RPC streams. Use actual stdio tests
  outside the checkout as well. SDK field names in Python are snake_case; wire
  aliases are camelCase (for example `is_error` / `isError`). Do not mix v1/v2 APIs
  or depend on private SDK internals to bypass validation.
- `examples/client.py` is an external example client, not a server tool. It
  launches the fixed server module with the same Python environment and explicitly
  supplies the fixture root by default. The server still has no default root.
  Its default public response is saved in `examples/reports/mixed-analysis.json`
  and checked by walkthrough subprocess tests. Keep commands/output examples
  accurate; no client commands may run Terraform or apply changes automatically.
- Pin reproducible Python dependencies with `uv.lock`. Add and document the
  supported OPA binary version when evaluation is introduced; analysis must work
  without OPA. Verify Python 3.14 compatibility rather than lowering the requested
  version silently.
- The verified local workflow uses `uv sync --locked --no-editable` and
  `uv run --locked --no-editable ...`: macOS hidden `.pth` flags recur in this
  environment and break editable imports. Keep the smoke test unchanged; do not
  add `PYTHONPATH` or test-path workarounds. uv cache keys track Python source,
  README, and project metadata so regular installs rebuild after changes.
- Dependency installation belongs to A1 after specification review, not drafting.
  Install into the uv-managed project environment rather than globally. Analysis
  needs the official MCP SDK and Pydantic plus test/lint tools, with no OPA,
  Terraform, or AWS prerequisite. The first secure-open implementation targets
  macOS/Linux and must fail safely on unsupported platforms.
- Package production Rego/catalog/capabilities as application assets. Test-only
  policies belong outside runtime assets. Do not load arbitrary working-directory
  policies or user-provided Rego.
- Keep IDs, metadata, and explanations consistent through one policy catalog.
  Structured findings use stable reason codes and safe message templates.
- Listing uses `PolicyListingService` with lazy package-only catalog loading,
  independent nonblocking admission and cancellation-safe worker cleanup. Its
  complete compact UTF-8 report is capped at 65,536 bytes; it never loads plans
  or probes OPA. Publish only `ListedPolicy` fields, including explicit empty
  `required_configuration` for AWS-RDS-001, without internal reason templates.
- M1's evaluation-only adapter path calls `project_rds_resources` after complete
  source merging/mask union. Match transient known cluster identifiers and RDS
  ARN context with linear exact/incomplete-key indexes; possible unknown targets
  block a unique link unless independently known unequal dimensions exclude them.
  Never retain raw matching strings in snapshots, reprs, OPA or reports. Member
  encryption copies are ignored. Only a resolved Terraform address and safe
  association state survive. `aws_db_instance` keeps its original scope guard.
  M1 introduced engine input schema 2 (superseded by M2 schema 3); engine/public report schemas remain
  1. Keep exact catalog reason semantics and per-resource reason applicability
  validation. No expression-reference fallback, live defaults or AWS lookups.

