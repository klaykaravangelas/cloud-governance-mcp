# Illustrative input only. The server reads saved plan JSON and never runs HCL.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "example" {
  bucket = "replace-with-a-unique-example-bucket"
  tags = {
    Environment = "dev"
    Owner       = "platform"
    Project     = "governance"
  }
}

# A new bucket's computed id may remain unknown in a plan. The block flags can
# pass directly while bucket inheritance remains indeterminate until names match.
resource "aws_s3_bucket_public_access_block" "protection" {
  bucket                  = aws_s3_bucket.example.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
