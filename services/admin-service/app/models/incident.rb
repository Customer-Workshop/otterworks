class Incident < ApplicationRecord
  SEVERITIES = %w[low medium high critical].freeze
  STATUSES = %w[open investigating resolved closed].freeze
  SOURCES = %w[manual servicenow grafana].freeze
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
  validates :snow_ticket_number, uniqueness: true, allow_blank: true
  validates :source, inclusion: { in: SOURCES }

  scope :by_status, ->(status) { where(status: status) }
  scope :by_severity, ->(severity) { where(severity: severity) }
  scope :active, -> { where(status: %w[open investigating]) }
  TERMINAL_DEVIN_STATUSES = %w[stopped finished failed poll_expired].freeze

  scope :snow_linked_active, lambda {
    where.not(snow_ticket_number: nil)
         .where.not(devin_session_id: nil)
         .active
         .where.not(devin_session_status: TERMINAL_DEVIN_STATUSES)
  }
  scope :from_servicenow, -> { where(source: 'servicenow') }

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
