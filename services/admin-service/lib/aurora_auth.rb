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

  # Static password used to seed database.yml at boot. When IAM auth is enabled
  # the real per-connection credential is a short-lived RDS IAM token injected
  # by config/initializers/aurora_iam_auth.rb (a boot-time token would expire
  # ~15 minutes later and break every new pool connection), so the value here is
  # only meaningful for the default, password-based revert path.
  def static_password
    ENV.fetch('DATABASE_PASSWORD', 'otterworks')
  end

  # SSL mode passed to libpq. On the default password path this stays "prefer"
  # (the prior behaviour). When IAM auth is enabled the password is a short-lived
  # token, so default to "require" to avoid a silent plaintext downgrade; still
  # overridable via DB_SSLMODE (e.g. "verify-full").
  def sslmode
    ENV.fetch('DB_SSLMODE', iam_auth_enabled? ? 'require' : 'prefer')
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
