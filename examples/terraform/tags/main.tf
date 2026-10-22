# Illustrative only: tests use synthetic JSON and never execute Terraform.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      Environment = "development"
      Project     = "governance-demo"
    }
  }
}

# tags_all includes these provider defaults plus the resource's Owner tag.
resource "aws_s3_bucket" "example" {
  bucket = "cloud-governance-tags-example-change-me"
  tags = {
    Owner = "example-team"
  }
}
