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

# All protocols include SSH. Port fields are deliberately omitted for -1.
resource "aws_vpc_security_group_ingress_rule" "example" {
  security_group_id = var.security_group_id
  cidr_ipv6         = "::/0"
  ip_protocol       = "-1"
}
