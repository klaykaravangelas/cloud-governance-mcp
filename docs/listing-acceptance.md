# Policy listing acceptance evidence

The user authorized Specification 003 implementation on 2026-10-19. L1a–L1d add
`list_policies` as the third MCP tool. It exposes only **AWS-RDS-001 v1.0.0** from
the existing evaluator catalog, covering standalone RDS instances. No new policy,
Python dependency, OPA execution behavior or analysis/evaluation response field
was introduced. The catalog now explicitly records `required_configuration: []`.

This is the historical L1 checkpoint. Specification 004 expands AWS-RDS-001 to
v1.1.0 and updates the saved catalog/evaluation reports. See
[RDS evidence](rds-acceptance.md) for that checkpoint and
[SSH evidence](ssh-acceptance.md) for current two-policy coverage; the original
counts/scope below describe L1.

## Executed verification

Verified on macOS arm64, Python 3.14.7, pinned MCP SDK 2.3.0 and OPA 1.21.2:

- Full Python regression suite: **702 passed, no skips**, in 29.64 seconds.
  This adds 59 cases to the previous 643-test checkpoint.
- OPA-independent analysis/listing plus pure evaluation contracts: **628 passed**
  in 21.19 seconds with `CLOUD_GOVERNANCE_OPA=/not/installed/opa`, excluding the
  four documented real-evaluation test modules.
- Real OPA strict compilation, formatting and **7/7 Rego tests** passed.
- Ruff lint and formatting passed; 65 Python files were checked for formatting.
- uv lock, non-editable environment and installed dependency checks passed;
  `uv.lock` and project dependency declarations are unchanged.
- Source/wheel builds passed. A fresh external environment installed the wheel
  with exact runtime dependencies exported from the existing lockfile, offline.
  Its imports resolve to its own site-packages rather than the checkout.
- Independent real stdio calls from outside the checkout passed in SDK auto and
  legacy modes: three-tool discovery, listing with no OPA configured, analysis,
  and listed-ID selection for encrypted/unencrypted real OPA outcomes.
- Both modes of the extracted source archive's example client reproduced the
  saved listing JSON against that installed wheel. A misleading current-directory
  catalog did not override packaged metadata.
- The wheel contains production catalog/capability/Rego assets and listing
  modules, without tests, examples, docs, test policies or bundled OPA. The source
  archive includes the listing specification, walkthrough, saved response, tests,
  fixtures and test Rego.

Commands follow [development setup](development.md) and
[the evaluation checks](trying-evaluation.md#5-verify-locally), using
`--locked --no-editable` and uv cache under
`/private/tmp/cloud-governance-mcp-uv-cache`. The full and OPA-independent suites
used authorized host permissions for the existing real Unix socket fixture;
that case was not skipped. No credentials, Terraform execution, network service
or infrastructure mutation was needed.

## Acceptance traceability

| Case | Evidence |
| --- | --- |
| LP-01 | `test_listing_mcp.py`: exact three-tool names, Pydantic schemas and all four read-only annotations. Existing `test_server.py` still verifies analysis-only injection. |
| LP-02 | SDK empty/no-argument calls return validated identical text/structured content. `test_stdio.py` additionally sends raw omitted, null and empty-object arguments. Saved example output matches in both modes. |
| LP-03 | Core and SDK tests reject extra fields; raw stdio rejects arrays/scalars with fixed protocol diagnostics. Rejected sentinel keys/values are absent from responses and logs. |
| LP-04 | `test_listing.py` compares every public field with the selected internal policy. Evaluation SDK tests use the ID returned by listing; metadata is projected from the shared catalog. |
| LP-05 | Catalog mutation cases reject other IDs, cluster coverage, disabled entries, nonempty configuration requirements and incomplete reasons. The sole response documents standalone scope. |
| LP-06 | SDK tests cover unconfigured, missing and synthetic unsupported OPA paths, forbid subprocess/probe/plan/adapter/evaluation calls and check the synthetic executable was untouched. Real stdio listing also runs without OPA. |
| LP-07 | Actual packaged-loader error-path tests cover missing files, UTF-8 errors, duplicate keys, malformed/oversized JSON, wrong schema and missing configuration requirements. All map to the fixed asset error. |
| LP-08 | Projection tests compare the exact public/internal field difference and verify independent copies. Isolated subprocess imports are quiet, perform no asset reads and do not import MCP. |
| LP-09 | Repeated reports agree; duplicate IDs/internal fields fail public validation. SDK tests sanitize invalid injected reports, unexpected exceptions and mutated exception text. |
| LP-10 | Non-ASCII metadata proves UTF-8 byte measurement. Smaller test-only limits exercise exact-boundary success, one-byte-over failure and recovery; production limit is asserted as 65,536 bytes. |
| LP-11 | Worker thread observation, immediate busy responses, native/repeated/AnyIO cancellation, cleanup/recovery and cancelled worker failures are tested. Concurrent SDK analysis and evaluation reach their independent services during blocked listing. |
| LP-12 | Auto/legacy real stdio outside checkout verifies listing, safe-error recovery and subsequent analysis; raw protocol tests check stdout and secret omission. |
| LP-13 | Real OPA SDK and independent wheel tests select the listed policy ID and preserve known pass/fail/indeterminate/not-applicable results. Existing analysis and evaluation goldens pass unchanged. |
| LP-14 | Walkthrough subprocess tests compare `--list-policies` with `examples/reports/policy-list.json` in both modes. Independent source/wheel inspection and extracted-source examples verify packaged operation and asset boundaries. |

## Scope and limitations

The [walkthrough](trying-listing.md) is ready for manual testing. Listing describes
bundled rules; it does not certify a plan or verify OPA installation/health. It
still needs normal server startup with an explicit allowed root. Errors never
become successful empty lists, and output is never truncated.

Only macOS arm64 execution is verified here; Linux remains unverified. Plans are
synthetic, and no live-account or Terraform-generated compatibility campaign is
claimed. Worker threads cannot be forcibly stopped; cancellation joins cleanup.
Full v0.1 remains incomplete until expanded RDS, SSH, tags and S3 coverage land in
separately scoped increments. No GitHub push is included in this implementation.
