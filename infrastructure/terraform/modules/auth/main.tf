# Cognito user pool for OtterWorks authentication

resource "aws_cognito_user_pool" "main" {
  name = "${var.project}-users-${var.environment}"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  schema {
    name                     = "email"
    attribute_data_type      = "String"
    required                 = true
    mutable                  = true
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                     = "display_name"
    attribute_data_type      = "String"
    required                 = false
    mutable                  = true
    string_attribute_constraints {
      min_length = 1
      max_length = 100
    }
  }

  tags = {
    Service = "auth-service"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project}-web-client"
  user_pool_id = aws_cognito_user_pool.main.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  access_token_validity  = 1  # hours
  refresh_token_validity = 30 # days
  id_token_validity      = 1  # hours
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

variable "environment" { type = string }
variable "project" { type = string }
