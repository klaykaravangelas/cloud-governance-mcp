# Illustrative identities for the analysis adapter. No cloud provider is needed.
# The JSON fixtures are hand-authored independently; tests never execute HCL.
terraform {
  required_version = ">= 1.4.0"
}

resource "terraform_data" "root" {
  input = "synthetic-root"
}

module "child" {
  source = "./modules/child"
}
