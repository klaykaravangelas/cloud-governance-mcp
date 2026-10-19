# OPA runtime setup

Evaluation targets **OPA 1.21.2**, Rego v1. Analysis requires no OPA. The binary
is a separate local dependency, not a Python package or global installation.
Runtime configuration must use its absolute path; no automatic PATH lookup or
download occurs in the server. A missing evaluator must not disable analysis.

## Versioned artifacts and checksums

Source: [immutable official release](https://github.com/open-policy-agent/opa/releases/tag/v1.21.2)
and its [release metadata](https://api.github.com/repos/open-policy-agent/opa/releases/tags/v1.21.2),
checked 2026-10-19. These SHA-256 digests are from the release asset metadata:

| Platform | Asset | SHA-256 |
| --- | --- | --- |
| macOS arm64 | `opa_darwin_arm64_static` | `e358121f0d96a41103499d878184e493cc5ab10956f98e835089b9de0ac2de62` |
| macOS amd64 | `opa_darwin_amd64` | `4bd9627845899723add7d2dae1bdf97407b2c56fc8d4d15895c6de9c3aa64fec` |
| Linux arm64 | `opa_linux_arm64_static` | `ed13bb8647b8a81e1f11741dd18babe02aced7a304314bd6bf8007793b6d4ff1` |
| Linux amd64 | `opa_linux_amd64_static` | `830ab11f61ffec760b5e19db0d7ad02bf037e13f5ef4d665faeaf17632177527` |

Only macOS arm64 execution is verified locally. Published artifacts for other
platforms are documented for reproducible installation, not claimed as tested.
The secure file loader still fails safely on unsupported platforms.

## Install locally

From the repository root, the following example is for macOS arm64. For another
platform choose its exact asset and digest from the table. Downloads require
network access; evaluation of local fixtures does not.

```sh
mkdir -p .tools/opa/1.21.2
curl --fail --location https://github.com/open-policy-agent/opa/releases/download/v1.21.2/opa_darwin_arm64_static --output .tools/opa/1.21.2/opa
printf '%s  %s\n' 'e358121f0d96a41103499d878184e493cc5ab10956f98e835089b9de0ac2de62' '.tools/opa/1.21.2/opa' | shasum -a 256 --check
```

Continue only when checksum verification succeeds:

```sh
chmod +x .tools/opa/1.21.2/opa
.tools/opa/1.21.2/opa version
```

On Linux use `sha256sum --check` instead of `shasum -a 256 --check` if needed.
The expected version is `1.21.2`; a different installed version is rejected.
The `.tools/` directory is ignored by Git. Do not commit or distribute the binary
in the Python wheel. Production uses the same explicitly configured runtime pin.

The server trusts this operator-installed executable and packaged policies.
Capabilities constrain policy language features, not an executable replaced by
the machine administrator. Do not point it at an untrusted program.
