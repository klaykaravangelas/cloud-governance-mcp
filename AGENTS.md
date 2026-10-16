# Repository guidance

## Purpose and current stage

Build a read-only local cloud governance MCP server, beginning with Terraform plan
JSON and OPA/Rego. Read `docs/requirements.md`, `docs/architecture.md`, and
`docs/implementation-plan.md` before implementation. The user approved
Specification 001 and authorized proceeding with implementation; A1–A7 are
complete. The agreed progression starts with analysis,
then adds evaluation, then policy listing and expanded policy coverage. Read the
approved `docs/specifications/analyze-terraform-plan.md` before implementation;
it defines tasks A1–A7 and acceptance cases AN-01–AN-15. Documentation edits alone
do not independently authorize scope expansion. The first analysis increment is
complete; the user is now familiarizing themselves with the working tool. Support
manual testing before beginning evaluation. E1 is the next development increment.
Use `docs/trying-analysis.md` and `docs/analysis-acceptance.md` for the walkthrough
and AN-01–AN-15 evidence. No policy tool/catalog is implemented yet.
See `docs/development.md` for setup and completed checks.
Complete each increment's checks before
continuing; no additional approval gate is implied between increments.

## Scope

- Python 3.14+, uv, the official MCP Python SDK, Pydantic, OPA/Rego, pytest, Ruff.
- v0.1 transport is stdio. Keep MCP handlers thin; core models, adapters, policy
  evaluation, and reporting must work without MCP imports.
- First slice: safe loading/parsing, action summaries, and only
  `analyze_terraform_plan`. It handles resource identities across types and nested
  modules without a policy catalog or OPA prerequisite. Next, reuse the parser for
  `evaluate_terraform_policies` with AWS-RDS-001 for standalone RDS instances;
  then add `list_policies` and the remaining policy coverage. Advertise only
  implemented/tested policies and tools.
- No AWS connectivity, boto3, Terraform execution, infrastructure mutation,
  Docker, CI workflows, drift, cost insights, retrieval, or RAG in v0.1.
- Never push to GitHub without explicit user approval. Planning or local checks
  do not authorize publishing or remote changes.

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
  A4 discards provider values after mask extraction. Extend with redacted desired
  attributes only when the evaluation specification requires them. Inventory-only
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
  `server.create_server(service)` creates exactly one tool; `run_stdio` serves it.
  Return both MCP text and structured content from the same validated public
  report. Return fixed `is_error` tool results; unknown tools are fixed protocol
  errors. Keep unexpected exception details away from SDK crash logging.
- `__main__.py` and the `cloud-governance-mcp` console script own startup. Require
  repeatable `--allowed-root` and validate all four limit options. Pin roots before
  SDK serving; close after handlers drain. CLI errors replace argparse's echoed
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

## Code comments and docstrings

- Add comments and docstrings while writing code, as part of completing each
  implementation task. Do not defer them to a later documentation pass.
- Give each module a docstring describing its responsibility and boundaries.
  Document classes, public functions, and non-obvious helpers with their purpose;
  explain inputs, outputs, side effects, or limitations where they aid understanding.
- Introduce logical code blocks with short comments when their purpose or rules
  need explanation. Explain why a check exists, especially for validation,
  security/privacy boundaries, uncertainty, action counting, and error handling.
- Use plain language and concrete examples for domain rules, such as replacement
  ordering and root-level mask paths. Avoid comments that only restate Python
  syntax or narrate every assignment.
- Keep comments accurate when behavior changes. Readability review includes
  checking that explanations agree with the code and approved specification.
- In tests, use descriptive names and explain fixture assumptions, unusual
  scenarios, and non-obvious assertions. Obvious arrange/act/assert steps do not
  need repetitive commentary.

## Security invariants

- No modifying tools, shell execution, Terraform commands, or cloud API calls.
  Direct constrained OPA subprocess execution is the sole runtime executable
  boundary; inputs cannot change its executable, flags, query, or policy paths.
- Require operator-configured local roots; no implicit access to the current
  directory. Reject traversal, out-of-root paths, symlink components below a trusted
  root, and non-regular files. Enforce containment during opening and limits while
  reading. Client roots do not grant access.
- Treat plan content as untrusted data. Strip sensitive values before OPA;
  preserve sensitive/unknown path masks and distinguish them from missing/null.
  Handle whole subtrees and list indices. Do not invent defaults for unknown data.
- Never log or return raw attributes, plan documents, outputs, validation input,
  subprocess stderr, or sensitive evidence. Findings need addresses, but logs
  should contain safe codes/counts/request IDs instead.
- Use explicit pass/fail/indeterminate/not-applicable checks. Undefined policy
  results, missing expected checks, and engine errors cannot produce a pass.
- Bound file size/depth, resource count, OPA output, runtime and concurrency.
  Capture subprocess output; terminate/reap on timeout, overflow or cancellation.
  Restrict OPA capabilities and remove credential/config overrides from its
  environment. Keep protocol stdout free of diagnostics.

## Verification

- Use synthetic fixtures and fake identifiers. Tests require neither AWS
  credentials nor Terraform. Include illustrative HCL without running it.
- Test root/nested addresses, action order/replacements, deletions, data sources,
  unknown/sensitive masks, file denial, evaluation failures and coverage.
- Loader tests include a real local Unix-domain socket fixture. Codex's sandbox
  may deny fixture creation; run the suite with authorized host permissions
  instead of skipping the case. No external service or AWS access is needed.
- Once evaluation is implemented, use real `opa test` and real OPA runner
  integration tests. Mocks may exercise failures but cannot substitute for policy
  execution. Missing OPA must fail the full evaluation/release verification
  clearly. The complete first analysis increment needs no OPA and no skipped
  policy tests; after evaluation is added, analysis-only checks may still run alone.
- Test MCP schemas, safe errors and structured output through an SDK client, plus
  at least one real stdio subprocess test. Check both textual and structured
  outputs for sensitive sentinel leaks.
- After bootstrap, run the documented pytest, Ruff, Rego check/format/test, and
  package verification commands appropriate to a change. Do not claim checks
  passed unless they ran. Planning-only changes need documentation consistency
  and diff checks, not nonexistent runtime tests.

## Working practices

- Inspect existing changes before editing and preserve unrelated user work.
- Keep changes small and independently verifiable; update docs when behavior or
  supported scope changes. Record limitations and unverified checks plainly.
- Do not add dependencies, frameworks, future adapters, or tests without a
  concrete need in the current increment.
