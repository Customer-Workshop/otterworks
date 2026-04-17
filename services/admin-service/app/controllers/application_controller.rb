class ApplicationController < ActionController::API
  # TODO: Add JWT authentication for admin endpoints
  # before_action :authenticate_admin!

  rescue_from StandardError do |e|
    Rails.logger.error("Unhandled error: #{e.message}")
    render json: { error: "Internal server error" }, status: :internal_server_error
  end

  rescue_from ActiveRecord::RecordNotFound do |e|
    render json: { error: "Resource not found" }, status: :not_found
  end
end
