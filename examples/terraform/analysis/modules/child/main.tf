# Count and for_each identities must retain their numeric/string instance keys.
resource "terraform_data" "counted" {
  count = 2
  input = "synthetic-${count.index}"
}

resource "terraform_data" "keyed" {
  for_each = toset(["a.b", "quoted\"key"])
  input    = each.key
}
