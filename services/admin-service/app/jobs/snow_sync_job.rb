class SnowSyncJob < ApplicationJob
  queue_as :default

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
    session = DevinSessionService.get_session(session_id: incident.devin_session_id)
    return unless session

    new_status = session[:status]
    return if new_status == incident.devin_session_status

    incident.update!(devin_session_status: new_status)
    sys_id = incident.snow_sys_id

    case new_status
    when 'stopped'
      ServicenowService.update_state(
        sys_id:     sys_id,
        state:      '6',
        work_notes: 'Devin session completed investigation. Incident auto-resolved by OtterWorks.'
      )
      incident.resolve!
    when 'blocked'
      ServicenowService.update_state(
        sys_id:     sys_id,
        state:      '3',
        work_notes: "Devin session blocked \u2014 needs human input. Session: #{incident.devin_session_url}"
      )
    when 'failed'
      ServicenowService.update_work_notes(
        sys_id: sys_id,
        notes:  "Devin session failed \u2014 manual investigation required. Session: #{incident.devin_session_url}"
      )
    else
      ServicenowService.update_work_notes(
        sys_id: sys_id,
        notes:  "Devin session status: #{new_status}"
      )
    end
  rescue StandardError => e
    Rails.logger.error("SnowSyncJob failed for incident #{incident.id}: #{e.message}")
  end
end
