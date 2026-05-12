class Incident < ApplicationRecord
  SEVERITIES = %w[low medium high critical].freeze
  STATUSES = %w[open investigating resolved closed].freeze
  AFFECTED_SERVICES = %w[
    api-gateway auth-service file-service document-service
    collab-service notification-service search-service
    analytics-service admin-service audit-service report-service
  ].freeze

  validates :title, presence: true, length: { maximum: 255 }
  validates :description, presence: true
  validates :severity, presence: true, inclusion: { in: SEVERITIES }
  validates :status, presence: true, inclusion: { in: STATUSES }
  validates :affected_service, inclusion: { in: AFFECTED_SERVICES }, allow_blank: true

  scope :by_status, ->(status) { where(status: status) }
  scope :by_severity, ->(severity) { where(severity: severity) }
  scope :active, -> { where(status: %w[open investigating]) }

  def investigate!
    update!(status: 'investigating')
  end

  def resolve!
    update!(status: 'resolved', resolved_at: Time.current)
  end

  def close!
    update!(status: 'closed')
  end

  def active?
    %w[open investigating].include?(status)
  end

  def has_devin_session?
    devin_session_id.present?
  end
end
