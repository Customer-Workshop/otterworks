# frozen_string_literal: true

# Aurora IAM authentication + TLS helpers for the ActiveRecord connection layer.
#
# Additive by design: when DB_IAM_AUTH_ENABLED is not "true" (the default) the
# database password and SSL mode resolve exactly as before, so the existing RDS
# PostgreSQL wiring stays in place for revert. When enabled, the password is a
# short-lived RDS IAM auth token and TLS is negotiated against Aurora.
module AuroraAuth
  module_function

  def iam_auth_enabled?
    ENV.fetch('DB_IAM_AUTH_ENABLED', 'false').casecmp('true').zero?
  end

  # Password used by database.yml. Static password unless IAM auth is enabled,
  # in which case a fresh RDS IAM token is generated (valid ~15 minutes).
  def database_password
    return ENV.fetch('DATABASE_PASSWORD', 'otterworks') unless iam_auth_enabled?

    generate_auth_token
  end

  # SSL mode passed to libpq. Defaults to "prefer" (the libpq default) so the
  # current behaviour is preserved; override with DB_SSLMODE (e.g. "require",
  # "verify-full") when talking to Aurora.
  def sslmode
    ENV.fetch('DB_SSLMODE', 'prefer')
  end

  def generate_auth_token
    require 'aws-sdk-rds'
    region = ENV['DB_IAM_REGION'] || ENV['AWS_REGION'] || 'us-east-1'
    generator = Aws::RDS::AuthTokenGenerator.new(
      credentials: Aws::CredentialProviderChain.new.resolve
    )
    generator.auth_token(
      region: region,
      endpoint: "#{ENV.fetch('DATABASE_HOST', 'localhost')}:#{ENV.fetch('DATABASE_PORT', 5432)}",
      user_name: ENV.fetch('DATABASE_USER', 'otterworks')
    )
  end
end
