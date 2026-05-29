class DevinSessionPollJob < ApplicationJob
  queue_as :default

  TERMINAL_STATUSES = %w[finished completed stopped failed errored].freeze

  def perform
    incidents = Incident.where(devin_session_status: 'running')
                        .where.not(devin_session_id: nil)

    Rails.logger.info("DevinSessionPollJob: checking #{incidents.count} running session(s)")

    incidents.find_each do |incident|
      poll_session(incident)
    rescue StandardError => e
      Rails.logger.error("DevinSessionPollJob: error polling incident #{incident.id}: #{e.message}")
    end
  end

  private

  def poll_session(incident)
    session_info = DevinSessionService.get_session(session_id: incident.devin_session_id)
    return unless session_info

    new_status = session_info[:status].to_s.downcase
    return if new_status == incident.devin_session_status

    Rails.logger.info(
      "DevinSessionPollJob: incident #{incident.id} session status changed " \
      "#{incident.devin_session_status} → #{new_status}"
    )

    incident.update!(devin_session_status: new_status)

    if completed_status?(new_status)
      handle_completion(incident, session_info)
    elsif failed_status?(new_status)
      handle_failure(incident, new_status)
    end
  end

  def completed_status?(status)
    %w[finished completed stopped].include?(status)
  end

  def failed_status?(status)
    %w[failed errored].include?(status)
  end

  def handle_completion(incident, session_info)
    incident.resolve! unless incident.status == 'resolved'
    IncidentEventPublisher.incident_resolved(incident)
    IncidentEventPublisher.devin_session_completed(incident)

    return unless incident.source == 'servicenow'

    ServicenowCallbackService.resolve_incident(
      incident: incident,
      summary: 'Devin AI session completed successfully'
    )
  end

  def handle_failure(incident, status)
    return unless incident.source == 'servicenow'

    ServicenowCallbackService.post_update(
      incident: incident,
      status: "Devin session #{status}",
      session_url: incident.devin_session_url,
      summary: "The automated remediation session ended with status: #{status}"
    )
  end
end
