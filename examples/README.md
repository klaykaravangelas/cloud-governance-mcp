# Examples and sample data

The example client uses the synthetic JSON fixtures under `tests/fixtures/plans`.
Those resource identities are hand-authored test data; the HCL here does not
generate them and no cloud resources have been created.

| Location | Role |
| --- | --- |
| [client.py](client.py) | MCP client that starts our stdio server, discovers both tools, and calls analysis or explicit evaluation. |
| [Input plans](../tests/fixtures/plans/README.md) | Synthetic Terraform plan JSON used by the client and automated tests. The default is [mixed_nested.json](../tests/fixtures/plans/mixed_nested.json). |
| [reports/mixed-analysis.json](reports/mixed-analysis.json) | Saved public output of the default client command. |
| [Encrypted RDS report](reports/encrypted-rds-evaluation.json) / [unencrypted RDS report](reports/unencrypted-rds-evaluation.json) | Actual full outputs from evaluating the synthetic RDS fixtures with pinned OPA. |
| [terraform/analysis/main.tf](terraform/analysis/main.tf) | Separate illustrative HCL using built-in `terraform_data` resources, with root and indexed child-module identities. It is not executed by the tests. |

From the repository root:

```sh
uv run --locked --no-editable python examples/client.py --list-tools
uv run --locked --no-editable python examples/client.py
```

The server launch CLI (`cloud-governance-mcp`) waits for MCP messages.
`client.py` sends those messages for terminal testing. An MCP host can replace
this example client and launch the same server command itself.

For personal exported JSON plans, use the ignored `local-plans/` directory in
your checkout and explicitly authorize it with `--allowed-root`. The server has
no default root and reads no plan until a tool call requests it. See the
[walkthrough](../docs/trying-analysis.md) for setup, expected results and errors.
See [evaluation](../docs/trying-evaluation.md) for OPA setup and policy commands.
