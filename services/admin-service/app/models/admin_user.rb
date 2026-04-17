class AdminUser < ApplicationRecord
  ROLES = %w[super_admin admin editor viewer].freeze
  STATUSES = %w[active suspended deleted].freeze

  has_one :storage_quota, foreign_key: :user_id, primary_key: :id, dependent: :destroy, inverse_of: false

  validates :email, presence: true, uniqueness: true,
                    format: { with: URI::MailTo::EMAIL_REGEXP }
  validates :display_name, presence: true, length: { maximum: 255 }
  validates :role, presence: true, inclusion: { in: ROLES }
  validates :status, presence: true, inclusion: { in: STATUSES }

  scope :active, -> { where(status: 'active') }
  scope :suspended, -> { where(status: 'suspended') }
  scope :by_role, ->(role) { where(role: role) }
  scope :search, lambda { |query|
    where('email ILIKE :q OR display_name ILIKE :q', q: "%#{sanitize_sql_like(query)}%")
  }

  def suspend!(reason: nil)
    update!(status: 'suspended', suspended_at: Time.current, suspended_reason: reason)
  end

  def activate!
    update!(status: 'active', suspended_at: nil, suspended_reason: nil)
  end

  def soft_delete!
    update!(status: 'deleted')
  end

  def active?
    status == 'active'
  end

  def suspended?
    status == 'suspended'
  end
end
