class ApplicationController < ActionController::API
  before_action :set_request_metadata

  rescue_from StandardError do |e|
    Rails.logger.error("Unhandled error: #{e.message}")
    render_error(code: 'INTERNAL_ERROR', message: 'Internal server error', status: :internal_server_error)
  end

  rescue_from ActiveRecord::RecordNotFound do
    render_error(code: 'NOT_FOUND', message: 'Resource not found', status: :not_found)
  end

  rescue_from ActiveRecord::RecordInvalid do |e|
    message = [e.message, e.record.errors.full_messages.to_sentence].reject(&:blank?).join(': ')
    render_error(code: 'VALIDATION_ERROR', message: message, status: :unprocessable_entity)
  end

  rescue_from ActionController::ParameterMissing do |e|
    render_error(code: 'BAD_REQUEST', message: "Missing parameter: #{e.param}", status: :bad_request)
  end

  def route_not_found
    render_error(code: 'NOT_FOUND', message: 'Route not found', status: :not_found)
  end

  private

  def current_user_id
    request.env['jwt.user_id']
  end

  def current_user_email
    request.env['jwt.user_email']
  end

  def current_user_role
    request.env['jwt.user_role']
  end

  def set_request_metadata
    @request_metadata = {
      ip_address: request.remote_ip,
      user_agent: request.user_agent
    }
  end

  def paginate(scope)
    page = [(params[:page] || 1).to_i, 1].max
    per_page = [(params[:per_page] || 20).to_i, 100].min.clamp(1, 100)
    total = scope.count

    records = scope.offset((page - 1) * per_page).limit(per_page)

    response.headers['X-Total-Count'] = total.to_s
    response.headers['X-Page'] = page.to_s
    response.headers['X-Per-Page'] = per_page.to_s

    { records: records, total: total, page: page, per_page: per_page }
  end

  def render_error(code:, message:, status:)
    status_code = Rack::Utils.status_code(status)
    render json: {
      error: {
        code: code,
        message: message,
        status: status_code
      }
    }, status: status
  end
end
