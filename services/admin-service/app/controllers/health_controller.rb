class HealthController < ActionController::API
  def show
    render json: { status: "healthy", service: "admin-service" }
  end

  def metrics
    render plain: <<~METRICS
      # HELP admin_service_up Admin Service is running
      # TYPE admin_service_up gauge
      admin_service_up 1
    METRICS
  end
end
