class FeatureFlag < ApplicationRecord
  validates :name, presence: true, uniqueness: true,
                   format: { with: /\A[a-z][a-z0-9_]*\z/, message: 'must be snake_case' }
  validates :rollout_percentage, numericality: {
    only_integer: true,
    greater_than_or_equal_to: 0,
    less_than_or_equal_to: 100
  }

  scope :enabled, -> { where(enabled: true) }
  scope :disabled, -> { where(enabled: false) }
  scope :active, -> { where('expires_at IS NULL OR expires_at > ?', Time.current) }

  def expired?
    expires_at.present? && expires_at < Time.current
  end

  def enabled_for_user?(user_id)
    return false unless enabled
    return false if expired?
    return true if target_users.include?(user_id)
    return true if rollout_percentage == 100

    rollout_percentage.positive? && (user_id.hash % 100) < rollout_percentage
  end
end
