require 'net/http'
require 'json'
require 'uri'

class ServicenowService
  class << self
    def update_work_notes(sys_id:, notes:)
      patch_incident(sys_id, { work_notes: notes })
    end

    def update_state(sys_id:, state:, work_notes: nil)
      body = { state: state }
      body[:work_notes] = work_notes if work_notes.present?
      patch_incident(sys_id, body)
    end

    def get_incident(sys_id:)
      uri = URI("#{instance_url}/api/now/table/incident/#{sys_id}")
      request = Net::HTTP::Get.new(uri)
      apply_headers(request)

      response = make_request(uri, request)
      return nil unless response

      JSON.parse(response.body).dig('result')
    rescue StandardError => e
      Rails.logger.error("ServiceNow get_incident failed: #{e.message}")
      nil
    end

    private

    def patch_incident(sys_id, body)
      uri = URI("#{instance_url}/api/now/table/incident/#{sys_id}")
      request = Net::HTTP::Patch.new(uri)
      apply_headers(request)
      request.body = body.to_json

      response = make_request(uri, request)
      return nil unless response

      JSON.parse(response.body).dig('result')
    rescue StandardError => e
      Rails.logger.error("ServiceNow patch_incident failed: #{e.message}")
      nil
    end

    def apply_headers(request)
      request['Content-Type'] = 'application/json'
      request['Accept'] = 'application/json'
      request.basic_auth(api_user, api_password)
    end

    def make_request(uri, request)
      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = uri.scheme == 'https'
      http.open_timeout = 10
      http.read_timeout = 30

      response = http.request(request)

      unless response.is_a?(Net::HTTPSuccess)
        Rails.logger.error("ServiceNow API returned #{response.code}: #{response.body}")
        return nil
      end

      response
    end

    def instance_url
      ENV.fetch('SNOW_INSTANCE_URL')
    end

    def api_user
      ENV.fetch('SNOW_API_USER')
    end

    def api_password
      ENV.fetch('SNOW_API_PASSWORD')
    end
  end
end
