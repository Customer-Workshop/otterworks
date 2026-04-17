class HealthController < ActionController::API
  def show
    db_ok = database_healthy?
    status = db_ok ? 'healthy' : 'degraded'

    render json: {
      status: status,
      service: 'admin-service',
      version: ENV.fetch('APP_VERSION', '1.0.0'),
      timestamp: Time.current.iso8601,
      database: db_ok ? 'connected' : 'disconnected'
    }, status: db_ok ? :ok : :service_unavailable
  end

  def metrics
    render plain: prometheus_metrics, content_type: 'text/plain'
  end

  private

  def database_healthy?
    ActiveRecord::Base.connection.execute('SELECT 1')
    true
  rescue StandardError
    false
  end

  def prometheus_metrics
    <<~METRICS
      # HELP admin_service_up Admin Service is running
      # TYPE admin_service_up gauge
      admin_service_up 1
      # HELP admin_users_total Total number of admin users
      # TYPE admin_users_total gauge
      admin_users_total #{begin
        AdminUser.count
      rescue StandardError
        0
      end}
      # HELP admin_users_active Active admin users
      # TYPE admin_users_active gauge
      admin_users_active #{begin
        AdminUser.active.count
      rescue StandardError
        0
      end}
      # HELP admin_feature_flags_total Total feature flags
      # TYPE admin_feature_flags_total gauge
      admin_feature_flags_total #{begin
        FeatureFlag.count
      rescue StandardError
        0
      end}
      # HELP admin_feature_flags_enabled Enabled feature flags
      # TYPE admin_feature_flags_enabled gauge
      admin_feature_flags_enabled #{begin
        FeatureFlag.enabled.count
      rescue StandardError
        0
      end}
    METRICS
  end
end
