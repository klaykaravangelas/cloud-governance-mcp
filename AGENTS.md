# Repository guidance

## Purpose

Build a read-only cloud governance MCP server using Terraform plan JSON and
bundled OPA/Rego policies. Keep the MCP interface separate from the governance
engine.

## Project documentation

- [Project status](docs/project-status.md): implemented scope, approved work and
  links to acceptance evidence. Keep progress/history out of this file.
- [Requirements](docs/requirements.md), [architecture](docs/architecture.md) and
  [implementation plan](docs/implementation-plan.md): read before implementation.
- [Specifications](docs/specifications/): use the approved specification for the
  current increment, its tasks and acceptance criteria.
- [Development](docs/development.md), [engineering notes](docs/engineering-notes.md)
  and [OPA setup](docs/opa-setup.md): setup, detailed contracts and compatibility.

## Working practices and scope

- Inspect existing changes before editing; preserve unrelated user work.
- Work in small, independently verifiable increments within the approved scope.
  Planning documents do not independently authorize implementation. Complete
  each task's relevant checks before continuing; no extra approval gate is implied
  between authorized tasks.
- Keep the README centered on the project vision. Label implemented and planned
  capabilities accurately; update status/evidence in the project documents.
- Add dependencies, abstractions and tests only for a concrete current need.
- v0.1 uses stdio. Do not add AWS connectivity, Terraform execution, infrastructure
  mutation, Docker, CI workflows, drift, costs or retrieval/RAG under this scope.
- Never push, publish or change remote resources without explicit user approval.

## Code organization and conventions

- Use the `src/cloud_governance_mcp/` layout, type annotations, small cohesive
  components and constructor/function dependency injection.
- Keep MCP handlers thin. Core models, adapters, evaluation and reporting must
  work without MCP imports. Module imports must be quiet and perform no I/O.
- Validate inputs strictly at boundaries. Use the established safe validation
  entrypoints; never return raw Pydantic errors, rejected field names or values.
- Treat Terraform addresses as opaque identities. Derive module membership from
  explicit metadata/the tree and preserve uncertainty instead of guessing defaults.
- Keep provider-specific parsing/projection separate from Rego compliance
  decisions. Share policy metadata and fixed explanation templates through the
  packaged catalog; expose only implemented and verified coverage.
- Use the pinned official SDK's public APIs. Keep text and structured tool output
  derived from the same validated public report. Preserve safe error mapping and
  read-only annotations.
- Run blocking I/O, parsing, projection and serialization off the event loop.
  Preserve independent nonblocking admission, cancellation-safe cleanup and
  caller-owned loader lifetime. See engineering notes for precise contracts.

## Comments and docstrings

- Write comments/docstrings with the code, not in a later documentation pass.
- Give each module a responsibility/boundary docstring. Document public classes
  and functions, and non-obvious helpers where purpose or constraints need context.
- Explain why security checks, uncertainty handling, counting and error boundaries
  exist. Introduce non-obvious logical blocks with short, plain-language comments.
- Avoid narrating obvious syntax. Keep explanations accurate as behavior changes.
- Use descriptive test names; explain unusual fixtures and non-obvious assertions
  without repetitive arrange/act/assert commentary.

## Security invariants

- All server tools are read-only. No shell, Terraform commands or cloud API calls.
  Direct constrained OPA execution is the sole runtime executable boundary;
  requests cannot choose its executable, flags, query or policy paths.
- Require operator-configured roots. Use the restricted loader/context manager;
  reject traversal, symlink components, out-of-root paths and non-regular files.
  Enforce containment during opening and limits while reading. Client roots grant
  no access. Fail safely on unsupported secure-file platforms.
- Treat plan content as untrusted. Apply sensitive/unknown masks before reading
  policy values, including root/subtree/list paths. Retain only the specified
  minimal projection; never log raw plans, attributes, validation details,
  subprocess diagnostics or sensitive evidence. Logs use safe codes/request IDs.
- Preserve pass/fail/indeterminate/not-applicable outcomes. Missing expected
  checks, undefined policy output and engine failures can never yield a pass.
  Validate complete policy/resource batches and fail atomically on engine errors.
- Bound input/depth/resource/work/output/runtime/concurrency. Never truncate a
  successful report. Terminate/reap owned OPA processes on timeout, overflow and
  cancellation; shield worker cleanup before releasing admission.
- Load packaged production policies/catalog/capabilities only. Keep test Rego
  separate, restrict capabilities and remove credential/config overrides from
  the child environment. Stdout belongs exclusively to the MCP protocol.

## Development and verification

- Python 3.14+ and uv with `uv.lock` are required. Install in the project
  environment, not globally. Use `uv sync --locked --no-editable` and
  `uv run --locked --no-editable ...`; see development notes for the macOS .pth
  issue. Do not add PYTHONPATH/test-path workarounds or weaken the package smoke test.
- Use synthetic plans/fake identifiers and illustrative HCL; tests must not need
  AWS credentials or execute Terraform. Keep pure analysis/listing/adapter checks
  runnable without OPA.
- Full evaluation checks require the pinned real OPA. Mocks cover failures but
  cannot replace policy execution. Missing OPA must fail full verification clearly.
- Test SDK auto/legacy modes and real stdio outside the checkout. Check both
  output channels/logs for sentinel leaks and preserve containment/process tests.
- The local Unix socket fixture may require authorized host permissions; run it
  there rather than skipping it.
- Run appropriate pytest, Ruff lint/format, Rego strict/format/test, lock/dependency
  and source/wheel/installed-operation checks from development documentation.
  Planning-only edits need documentation consistency and diff checks.
- Record executed evidence and unverified limitations accurately. Do not claim
  tests passed unless they ran or turn historical counts into current results.
