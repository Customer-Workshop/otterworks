class StorageQuota < ApplicationRecord
  TIERS = %w[free basic pro enterprise].freeze
  TIER_LIMITS = {
    'free' => 5.gigabytes,
    'basic' => 50.gigabytes,
    'pro' => 200.gigabytes,
    'enterprise' => 1.terabyte
  }.freeze

  validates :user_id, presence: true, uniqueness: true
  validates :quota_bytes, presence: true, numericality: { greater_than: 0 }
  validates :used_bytes, presence: true, numericality: { greater_than_or_equal_to: 0 }
  validates :tier, presence: true, inclusion: { in: TIERS }

  scope :over_quota, -> { where('used_bytes >= quota_bytes') }
  scope :by_tier, ->(tier) { where(tier: tier) }

  def usage_percentage
    return 0 if quota_bytes.zero?

    ((used_bytes.to_f / quota_bytes) * 100).round(2)
  end

  def over_quota?
    used_bytes >= quota_bytes
  end

  def remaining_bytes
    [quota_bytes - used_bytes, 0].max
  end
end
