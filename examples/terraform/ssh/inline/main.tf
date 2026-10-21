# Illustrative configuration only; tests never execute Terraform.
# Keep these three examples separate rather than mixing rule management on a group.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "vpc_id" {
  type = string
}

resource "aws_security_group" "example" {
  name   = "governance-ssh-inline-example"
  vpc_id = var.vpc_id

  # A world-wide TCP interval including SSH illustrates a policy violation.
  ingress {
    protocol    = "tcp"
    from_port   = 20
    to_port     = 23
    cidr_blocks = ["0.0.0.0/0"]
  }
}
