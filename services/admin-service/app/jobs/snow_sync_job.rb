class SnowSyncJob < ApplicationJob
  queue_as :default

  TERMINAL_STATES = %w[stopped finished failed].freeze
  MAX_POLL_DURATION = 24.hours

  def perform
    incidents = Incident.snow_linked_active.to_a
    return if incidents.empty?

    incidents.each { |incident| sync_incident(incident) }

    if Incident.snow_linked_active.exists?
      self.class.set(wait: 30.seconds).perform_later
    end
  end

  private

  def sync_incident(incident)
    if poll_expired?(incident)
      Rails.logger.warn("SnowSyncJob: max poll duration exceeded for incident #{incident.id}, stopping sync")
      ServicenowService.update_work_notes(
        sys_id: incident.snow_sys_id,
        notes:  "OtterWorks: polling stopped after #{MAX_POLL_DURATION / 1.hour}h — check Devin session manually: #{incident.devin_session_url}",
        instance_url: incident.snow_instance_url
      )
      incident.update!(devin_session_status: 'poll_expired')
      return
    end

    session = DevinSessionService.get_session(session_id: incident.devin_session_id)
    return unless session

    new_status = session[:status]
    return if new_status == incident.devin_session_status

    incident.update!(devin_session_status: new_status)
    sys_id = incident.snow_sys_id

    case new_status
    when 'stopped', 'finished'
      ServicenowService.update_state(
        sys_id:     sys_id,
        state:      '6',
        work_notes: 'Devin session completed investigation. Incident auto-resolved by OtterWorks.',
        instance_url: incident.snow_instance_url
      )
      incident.resolve!
    when 'blocked'
      ServicenowService.update_work_notes(
        sys_id: sys_id,
        notes:  "Devin session blocked — needs human input. Session: #{incident.devin_session_url}",
        instance_url: incident.snow_instance_url
      )
    when 'failed'
      ServicenowService.update_work_notes(
        sys_id: sys_id,
        notes:  "Devin session failed — manual investigation required. Session: #{incident.devin_session_url}",
        instance_url: incident.snow_instance_url
      )
    else
      ServicenowService.update_work_notes(
        sys_id: sys_id,
        notes:  "Devin session status: #{new_status}",
        instance_url: incident.snow_instance_url
      )
    end
  rescue StandardError => e
    Rails.logger.error("SnowSyncJob failed for incident #{incident.id}: #{e.message}")
  end

  def poll_expired?(incident)
    incident.created_at < MAX_POLL_DURATION.ago
  end
end
