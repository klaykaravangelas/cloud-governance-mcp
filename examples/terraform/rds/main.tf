# Illustrative only: tests use synthetic JSON and never execute Terraform.
# Supply real networking and credentials separately if studying this example;
# this project does not create infrastructure or generate a plan automatically.
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

variable "subnet_ids" {
  description = "Existing DB subnets in separate availability zones."
  type        = list(string)
}

variable "storage_encrypted" {
  description = "Explicit cluster encryption; false illustrates a violation."
  type        = bool
  default     = true
}

resource "aws_db_subnet_group" "example" {
  subnet_ids = var.subnet_ids
}

resource "aws_rds_cluster" "example" {
  cluster_identifier          = "governance-example"
  engine                      = "aurora-postgresql"
  master_username             = "example_admin"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.example.name
  storage_encrypted          = var.storage_encrypted
}

resource "aws_rds_cluster_instance" "member" {
  count              = 2
  identifier         = "governance-example-${count.index}"
  cluster_identifier = aws_rds_cluster.example.id
  instance_class     = "db.r6g.large"
  engine             = aws_rds_cluster.example.engine

  # Encryption is inherited from cluster storage, not configured on this member.
  # New-resource ARNs are commonly unknown, so initial member checks can remain
  # indeterminate despite a passing cluster check. References do not prove links.
}
