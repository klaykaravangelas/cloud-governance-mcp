# Connect Codex over stdio

Codex can launch this project's installed server directly as a local stdio
process. Codex supplies the MCP client; `examples/client.py` remains a separate
testing example and is not part of this connection.

## Prepare and register

From the repository directory:

```sh
uv sync --locked --no-editable
codex mcp add cloud-governance-mcp -- \
  "$PWD/.venv/bin/cloud-governance-mcp" \
  --allowed-root "$PWD/tests/fixtures/plans" \
  --opa-path "$PWD/.tools/opa/1.21.2/opa"
codex mcp get cloud-governance-mcp
```

Evaluation needs the pinned binary from [OPA setup](opa-setup.md). Omitting
`--opa-path` still allows analysis and policy listing, while evaluation returns a
safe configuration error. This project uses the regular, non-editable install so
the executable works independently of Codex's working directory. After source
changes, repeat `uv sync --locked --no-editable` and restart the MCP server.

The registration command writes a named entry in your user-level
`~/.codex/config.toml`, shared by local Codex clients. Its command and arguments
are absolute paths specific to your checkout. Moving or recreating the checkout
requires updating those paths. User configuration stays outside this repository;
the command above is the reproducible setup recipe.

Initially, the only allowed plan directory is `tests/fixtures/plans`. Relative
tool paths resolve there, including when Codex works in another project. For your
own plans, update the server's arguments with an explicit absolute directory;
repeat `--allowed-root` to authorize additional directories. The server retains
its read-only, containment, sensitivity and output-limit boundaries. Connecting
the server does not grant access to arbitrary local files.

## Reload and try it

Open the desktop app's Settings → MCP servers, find `cloud-governance-mcp` and
restart it. If an existing conversation still does not expose its tools, start a
new local conversation after reloading. In the CLI, start a new Codex session and
use `/mcp` to inspect connected servers. `codex mcp get` confirms saved settings;
it does not itself prove a live connection.

Ask Codex to use the **cloud-governance-mcp tools** for these requests:

1. “List the available governance policies.” Expect AWS-RDS-001 v1.1.0 and
   AWS-S3-001 and AWS-SG-001 v1.0.0 high severity, plus AWS-TAG-001 v1.0.0 medium, with their implemented scope.
2. “Analyze `mixed_nested.json`.” Expect seven resources, four managed changes
   and partial coverage.
3. “Evaluate `unencrypted_rds.json` using AWS-RDS-001.” Expect one encryption
   finding for `aws_db_instance.example`; evaluation succeeds and compliance fails.
4. “Evaluate `encrypted_rds.json` using AWS-RDS-001.” Expect compliance to pass within the policy's
   supported scope.
5. “Evaluate `unknown_sensitive.json` and explain what could not be established.”
   Expect explicit uncertainty without sensitive values.
6. “Evaluate `cluster_encrypted.json`, `cluster_unencrypted.json` and
   `cluster_unknown_arn.json` using only AWS-RDS-001.” Expect three passes, three failures, then one
   pass plus two indeterminate member checks. See [cluster examples](trying-rds-clusters.md).

For SSH testing, follow the [SSH host prompts](trying-ssh.md#test-directly-through-codex).
For TAG and all-policy testing, follow the [tags host prompts](trying-tags.md#test-through-an-mcp-host).
TAG defaults need no new host flags. To override them, add repeated
`--required-tag-key` startup arguments; the first replaces the default list.

After an upgrade, an already-running server can retain old model definitions
while reading newly installed catalog assets. A safe `POLICY_ASSETS_INVALID`
response in that situation requires restarting the configured MCP process and
verifying `list_policies` returns all four current policy IDs/versions; reinstalling alone does not reload it.

These are synthetic fixtures, requiring neither AWS credentials nor Terraform.
Confirm Codex actually calls the MCP tool instead of reading JSON through a shell.
The server processes tools on demand; no separate terminal server or HTTP port is
needed. The available functions are `analyze_terraform_plan`,
`evaluate_terraform_policies` and `list_policies`.

## Check or remove the registration

```sh
codex mcp get cloud-governance-mcp
```

To disconnect the server later:

```sh
codex mcp remove cloud-governance-mcp
```

Removal deletes the named Codex registration, not the project or its examples.
If startup fails, check the executable, its installed environment, the existing
allowed directory and the saved absolute paths. After fixing them, restart the
connection. Keep stdout reserved for MCP; never add startup prints to the server.

## Verification and reference

Verified 2026-10-19 on macOS arm64: the exact absolute console-script launch from
outside the checkout completed an SDK stdio handshake, discovered all three
tools, listed the RDS rule, analyzed seven mixed-plan resources and evaluated the
unencrypted fixture with the real configured OPA binary. This establishes server
and launch-command compatibility. Local registration via `codex mcp add`
succeeded, and `codex mcp get --json` confirmed an enabled stdio entry with the
expected command/arguments. Both SDK auto and legacy modes then connected using
the saved configuration, with encrypted-pass and sensitive/unknown-indeterminate
evaluation results. An active Codex conversation must separately reload its MCP
connection before the tools are available there; a live Codex model tool call is
not claimed by these SDK checks.

The [official OpenAI MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
documents stdio command registration, shared local configuration and connection
reload. No server implementation or additional dependency is needed for this
integration.
