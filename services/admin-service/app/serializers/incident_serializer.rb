class IncidentSerializer < ActiveModel::Serializer
  attributes :id, :title, :description, :severity, :status, :affected_service,
             :devin_session_id, :devin_session_url, :devin_session_status,
             :reporter_id, :resolved_at, :active,
             :snow_ticket_number, :snow_sys_id,
             :created_at, :updated_at

  def active
    object.active?
  end
end
