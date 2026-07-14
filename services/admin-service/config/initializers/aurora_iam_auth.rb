# frozen_string_literal: true

# RDS IAM authentication tokens are valid for only ~15 minutes. ActiveRecord
# evaluates database.yml (and therefore the password) once at boot, so any
# physical connection the pool opens later (pool growth, reaping, reconnect)
# would reuse a stale token and fail to authenticate. Inject a fresh token into
# the connection parameters each time the PostgreSQL adapter opens a raw
# connection so every physical connection authenticates with a current token.
#
# Only active when Aurora IAM auth is enabled; the default password-based path
# is left untouched for revert.
if AuroraAuth.iam_auth_enabled?
  require 'active_record/connection_adapters/postgresql_adapter'

  module AuroraIamPasswordRefresh
    def new_client(conn_params)
      super(conn_params.merge(password: AuroraAuth.generate_auth_token))
    end
  end

  ActiveRecord::ConnectionAdapters::PostgreSQLAdapter.singleton_class.prepend(
    AuroraIamPasswordRefresh
  )
end
