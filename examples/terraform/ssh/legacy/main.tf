# Illustrative configuration only; tests never execute Terraform.
# Keep these three examples separate rather than mixing rule management on a group.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "security_group_id" {
  type = string
}

# Legacy representation, supported for inspecting existing Terraform plans.
# The documentation range illustrates a non-world source, not a trusted network.
resource "aws_security_group_rule" "example" {
  type              = "ingress"
  security_group_id = var.security_group_id
  protocol          = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_blocks       = ["192.0.2.0/24"]
}
