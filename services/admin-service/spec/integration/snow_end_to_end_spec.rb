require 'rails_helper'

RSpec.describe 'ServiceNow end-to-end workflow', type: :request do
  let(:webhook_secret) { 'test-snow-secret-e2e' }
  let(:snow_headers) { { 'X-Snow-Secret' => webhook_secret } }
  let(:snow_instance) { 'https://dev99999.service-now.com' }
  let(:devin_session_id) { SecureRandom.uuid }
  let(:devin_session_url) { "https://app.devin.ai/sessions/#{devin_session_id}" }

  before do
    allow(ENV).to receive(:fetch).and_call_original
    allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return(webhook_secret)
    allow(ENV).to receive(:fetch).with('SNOW_INSTANCE_URL').and_return(snow_instance)
    allow(ENV).to receive(:fetch).with('SNOW_API_USER', nil).and_return('admin')
    allow(ENV).to receive(:fetch).with('SNOW_API_PASSWORD', nil).and_return('password')
    allow(ENV).to receive(:fetch).with('SNOW_API_USER').and_return('admin')
    allow(ENV).to receive(:fetch).with('SNOW_API_PASSWORD').and_return('password')

    allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(true)

    allow(DevinSessionService).to receive(:create_session).and_return({
      session_id: devin_session_id,
      url: devin_session_url
    })

    allow(DevinSessionService).to receive(:get_session).and_return({ status: 'running' })

    stub_request(:patch, %r{#{Regexp.escape(snow_instance)}/api/now/table/incident/})
      .to_return(status: 200, body: '{}', headers: { 'Content-Type' => 'application/json' })
  end

  describe 'Step 1: ServiceNow ticket ingestion creates incident and launches Devin' do
    it 'creates an incident from a nested SNOW webhook payload and launches Devin session' do
      post '/api/v1/admin/snow/ingest', params: {
        incident: {
          number: 'INC0099001',
          sys_id: 'abc123def456',
          description: 'Production API returning 500 errors on /api/orders',
          short_description: 'API 500 errors',
          priority: '1',
          affected_service: 'api-gateway',
          caller_id: 'john.doe',
          instance_url: snow_instance
        }
      }, as: :json, headers: snow_headers

      expect(response).to have_http_status(:created)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('created')
      expect(body['devin_session']).to be_present
      expect(body['devin_session']['id']).to eq(devin_session_id)

      incident = Incident.find(body['incident_id'])
      expect(incident.source).to eq('servicenow')
      expect(incident.snow_ticket_number).to eq('INC0099001')
      expect(incident.snow_sys_id).to eq('abc123def456')
      expect(incident.snow_instance_url).to eq(snow_instance)
      expect(incident.status).to eq('investigating')
      expect(incident.severity).to eq('critical')
      expect(incident.devin_session_id).to eq(devin_session_id)
      expect(incident.devin_session_status).to eq('running')
    end
  end

  describe 'Step 2: Deduplication prevents duplicate incidents' do
    it 'rejects a duplicate snow ticket number' do
      create(:incident, :with_snow, snow_ticket_number: 'INC0099002', snow_sys_id: 'dup111')

      post '/api/v1/admin/snow/ingest', params: {
        incident: {
          number: 'INC0099002',
          sys_id: 'dup222',
          description: 'Duplicate ticket'
        }
      }, as: :json, headers: snow_headers

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('duplicate')
    end
  end

  describe 'Step 3: SnowSyncJob polls Devin and syncs status to ServiceNow' do
    let!(:incident) do
      create(:incident, :snow_linked_active,
             snow_ticket_number: 'INC0099003',
             snow_sys_id: 'sync123',
             snow_instance_url: snow_instance)
    end

    it 'detects finished state, resolves incident, and updates ServiceNow' do
      allow(DevinSessionService).to receive(:get_session)
        .with(session_id: incident.devin_session_id)
        .and_return({ status: 'finished' })

      SnowSyncJob.perform_now

      incident.reload
      expect(incident.devin_session_status).to eq('finished')
      expect(incident.status).to eq('resolved')
      expect(Incident.snow_linked_active).not_to include(incident)
    end

    it 'keeps polling when Devin is blocked and posts work note' do
      allow(DevinSessionService).to receive(:get_session)
        .with(session_id: incident.devin_session_id)
        .and_return({ status: 'blocked' })

      SnowSyncJob.perform_now

      incident.reload
      expect(incident.devin_session_status).to eq('blocked')
      expect(incident.status).to eq('investigating')
      expect(Incident.snow_linked_active).to include(incident)
    end

    it 'stops polling after poll_expired and removes from active scope' do
      incident.update!(created_at: 25.hours.ago)

      SnowSyncJob.perform_now

      incident.reload
      expect(incident.devin_session_status).to eq('poll_expired')
      expect(Incident.snow_linked_active).not_to include(incident)
    end
  end

  describe 'Step 4: ServiceNow resolve callback closes incident' do
    let!(:incident) do
      create(:incident, :investigating,
             snow_ticket_number: 'INC0099004',
             snow_sys_id: 'resolve456')
    end

    it 'resolves the incident when SNOW sends resolve callback' do
      post '/api/v1/admin/snow/resolve', params: {
        incident: {
          number: 'INC0099004',
          state: '6'
        }
      }, as: :json, headers: snow_headers

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('resolved')

      incident.reload
      expect(incident.status).to eq('resolved')
    end
  end

  describe 'Step 5: Security — empty secret rejects all requests' do
    before do
      allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return(nil)
    end

    it 'returns 401 when webhook secret is not configured' do
      post '/api/v1/admin/snow/ingest', params: {
        incident: { number: 'INC0099005', sys_id: 'sec123', description: 'test' }
      }, as: :json

      expect(response).to have_http_status(:unauthorized)
      expect(JSON.parse(response.body)['error']).to include('not configured')
    end
  end

  describe 'Step 6: Security — wrong secret rejected' do
    it 'returns 401 with wrong secret' do
      post '/api/v1/admin/snow/ingest', params: {
        incident: { number: 'INC0099006', sys_id: 'sec456', description: 'test' }
      }, as: :json, headers: { 'X-Snow-Secret' => 'wrong-secret' }

      expect(response).to have_http_status(:unauthorized)
    end
  end

  describe 'Step 7: Multi-instance — per-incident URL used in ServiceNow calls' do
    it 'uses the per-incident instance_url when calling ServiceNow' do
      custom_instance = 'https://custom-instance.service-now.com'
      stub_request(:patch, %r{#{Regexp.escape(custom_instance)}/api/now/table/incident/})
        .to_return(status: 200, body: '{}', headers: { 'Content-Type' => 'application/json' })

      post '/api/v1/admin/snow/ingest', params: {
        incident: {
          number: 'INC0099007',
          sys_id: 'multi123',
          description: 'Multi-instance test',
          instance_url: custom_instance
        }
      }, as: :json, headers: snow_headers

      expect(response).to have_http_status(:created)
      incident = Incident.find_by(snow_ticket_number: 'INC0099007')
      expect(incident.snow_instance_url).to eq(custom_instance)

      expect(WebMock).to have_requested(:patch,
        "#{custom_instance}/api/now/table/incident/multi123")
        .at_least_once
    end
  end
end
