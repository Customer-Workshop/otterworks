module ObjectAuthorization
  extend ActiveSupport::Concern

  ADMIN_ROLES = %w[super_admin admin service].freeze

  private

  def admin_caller?
    ADMIN_ROLES.include?(current_user_role.to_s)
  end

  def require_caller!
    return true if current_user_id.present?

    render json: { error: 'Unauthenticated' }, status: :unauthorized
    false
  end

  def require_admin!
    return unless require_caller!
    return if admin_caller?

    render json: { error: 'Forbidden' }, status: :forbidden
  end

  # Allows the caller identified by X-User-ID (or the JWT subject) when it owns the
  # resource, and any admin/internal service role otherwise.
  def authorize_owner!(owner_id)
    return unless require_caller!
    return if admin_caller?
    return if owner_id.present? && owner_id.to_s == current_user_id.to_s

    render json: { error: 'Forbidden' }, status: :forbidden
  end
end
