require 'net/http'
require 'json'
require 'uri'

class ServicenowCallbackService
  class << self
    def post_work_note(incident:, message:)
      return unless callable?(incident)

      update_incident(incident, work_notes: message)
    end

    def resolve_incident(incident:, pr_url: nil, summary: nil)
      return unless callable?(incident)

      work_note = "Devin AI Remediation Complete\n"
      work_note += "PR: #{pr_url}\n" if pr_url
      work_note += "Summary: #{summary}\n" if summary
      work_note += "Session: #{incident.devin_session_url}" if incident.devin_session_url

      update_incident(
        incident,
        work_notes: work_note,
        state: '6',
        close_code: 'Solved (Permanently)',
        close_notes: "Auto-resolved by Devin AI. #{pr_url ? "PR: #{pr_url}" : ''}"
      )
    end

    def post_update(incident:, status:, pr_url: nil, session_url: nil, summary: nil)
      return unless callable?(incident)

      work_note = "Devin AI Update — Status: #{status}\n"
      work_note += "PR: #{pr_url}\n" if pr_url
      work_note += "Session: #{session_url}\n" if session_url
      work_note += "Details: #{summary}" if summary

      update_incident(incident, work_notes: work_note)
    end

    private

    def callable?(incident)
      return false unless incident.servicenow_sys_id.present?

      instance_url = servicenow_instance_url(incident)
      credentials_present = ENV['SERVICENOW_INSTANCE_URL'].present? || instance_url.present?
      username_present = ENV['SERVICENOW_USERNAME'].present?
      password_present = ENV['SERVICENOW_PASSWORD'].present?

      unless credentials_present && username_present && password_present
        Rails.logger.info(
          "ServiceNow callback skipped for incident #{incident.id}: " \
          "missing credentials (instance=#{credentials_present}, user=#{username_present}, pass=#{password_present})"
        )
        return false
      end

      true
    end

    def servicenow_instance_url(incident)
      incident.servicenow_instance_url.presence || ENV.fetch('SERVICENOW_INSTANCE_URL', nil)
    end

    def update_incident(incident, fields)
      base_url = servicenow_instance_url(incident)
      return unless base_url

      uri = URI("#{base_url.chomp('/')}/api/now/table/incident/#{incident.servicenow_sys_id}")
      request = Net::HTTP::Patch.new(uri)
      request['Content-Type'] = 'application/json'
      request['Accept'] = 'application/json'
      request.basic_auth(
        ENV.fetch('SERVICENOW_USERNAME'),
        ENV.fetch('SERVICENOW_PASSWORD')
      )
      request.body = fields.to_json

      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = uri.scheme == 'https'
      http.open_timeout = 10
      http.read_timeout = 15

      response = http.request(request)

      unless response.is_a?(Net::HTTPSuccess)
        Rails.logger.error(
          "ServiceNow callback failed for #{incident.servicenow_number}: " \
          "#{response.code} #{response.body}"
        )
      end

      response
    rescue StandardError => e
      Rails.logger.error("ServiceNow callback error: #{e.message}")
      nil
    end
  end
end
