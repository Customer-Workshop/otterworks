require 'rails_helper'

RSpec.describe Api::V1::Admin::SnowController do
  let(:webhook_secret) { 'test-snow-secret' }

  before do
    set_jwt_env(request)
    allow(ENV).to receive(:fetch).and_call_original
    allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return(webhook_secret)
    request.headers['X-Snow-Secret'] = webhook_secret
    allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(true)
    allow(DevinSessionService).to receive(:create_session).and_return(
      { session_id: 'dev-123', url: 'https://app.devin.ai/sessions/dev-123' }
    )
    allow(ServicenowService).to receive(:update_work_notes).and_return({})
    allow(ServicenowService).to receive(:update_state).and_return({})
    allow(SnowSyncJob).to receive_message_chain(:set, :perform_later) # rubocop:disable RSpec/MessageChain
    allow(AuditLogger).to receive(:log)
  end

  let(:valid_params) do
    {
      incident: {
        number: 'INC0010001',
        short_description: 'Auth service returning 500',
        description: 'Users cannot login, auth-service returning 500 errors',
        priority: '1',
        affected_service: 'auth-service',
        sys_id: 'abc123def456',
        state: '1',
        caller_id: 'admin',
        instance_url: 'https://dev99999.service-now.com'
      }
    }
  end

  describe 'POST #ingest' do
    it 'creates an incident from a valid SNOW payload' do
      expect do
        post :ingest, params: valid_params
      end.to change(Incident, :count).by(1)

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('created')
      expect(body['incident_id']).to be_present
      expect(body['devin_session']).to be_present
    end

    it 'sets source to servicenow on the created incident' do
      post :ingest, params: valid_params
      incident = Incident.last
      expect(incident.source).to eq('servicenow')
    end

    it 'stores snow_instance_url on the incident' do
      post :ingest, params: valid_params
      incident = Incident.last
      expect(incident.snow_instance_url).to eq('https://dev99999.service-now.com')
    end

    it 'maps SNOW priority 1 to critical severity' do
      post :ingest, params: valid_params
      incident = Incident.last
      expect(incident.severity).to eq('critical')
    end

    it 'maps SNOW priority 2 to high severity' do
      post :ingest, params: { incident: valid_params[:incident].merge(priority: '2') }
      incident = Incident.last
      expect(incident.severity).to eq('high')
    end

    it 'maps SNOW priority 3 to medium severity' do
      post :ingest, params: { incident: valid_params[:incident].merge(priority: '3') }
      incident = Incident.last
      expect(incident.severity).to eq('medium')
    end

    it 'maps SNOW priority 4/5 to low severity' do
      post :ingest, params: { incident: valid_params[:incident].merge(priority: '4') }
      incident = Incident.last
      expect(incident.severity).to eq('low')
    end

    it 'deduplicates by snow_ticket_number' do
      create(:incident, :with_snow, snow_ticket_number: 'INC0010001')

      expect do
        post :ingest, params: valid_params
      end.not_to change(Incident, :count)

      body = JSON.parse(response.body)
      expect(body['status']).to eq('duplicate')
    end

    it 'returns bad_request when required fields are missing' do
      post :ingest, params: { incident: { number: 'INC0010001' } }
      expect(response).to have_http_status(:bad_request)
    end

    it 'returns bad_request when incident key is missing entirely' do
      post :ingest, params: { number: 'INC0010001' }
      expect(response).to have_http_status(:bad_request)
    end

    it 'posts Devin session URL back to SNOW as work_note with instance_url' do
      post :ingest, params: valid_params

      expect(ServicenowService).to have_received(:update_work_notes).with(
        sys_id: 'abc123def456',
        notes: 'Devin AI session launched: https://app.devin.ai/sessions/dev-123',
        instance_url: 'https://dev99999.service-now.com'
      )
    end

    it 'updates SNOW ticket state to 2 (In Progress) when Devin session launches' do
      post :ingest, params: valid_params

      expect(ServicenowService).to have_received(:update_state).with(
        sys_id: 'abc123def456',
        state: '2',
        work_notes: 'OtterWorks auto-investigation in progress',
        instance_url: 'https://dev99999.service-now.com'
      )
    end

    it 'enqueues SnowSyncJob after creating incident with session' do
      post :ingest, params: valid_params
      expect(SnowSyncJob).to have_received(:set).with(wait: 30.seconds)
    end

    it 'stores snow_ticket_number and snow_sys_id on the incident' do
      post :ingest, params: valid_params
      incident = Incident.last
      expect(incident.snow_ticket_number).to eq('INC0010001')
      expect(incident.snow_sys_id).to eq('abc123def456')
    end

    it 'logs an audit entry for ingest' do
      post :ingest, params: valid_params
      expect(AuditLogger).to have_received(:log).with(
        hash_including(
          action: 'incident.created_from_snow',
          resource_type: 'Incident'
        )
      )
    end

    context 'when auto_investigate is disabled' do
      before { allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(false) }

      it 'creates incident with open status and no Devin session' do
        post :ingest, params: valid_params
        incident = Incident.last
        expect(incident.status).to eq('open')
        expect(incident.devin_session_id).to be_nil
      end
    end

    context 'when Devin session creation fails' do
      before { allow(DevinSessionService).to receive(:create_session).and_return(nil) }

      it 'keeps incident as open and does not enqueue sync job' do
        post :ingest, params: valid_params
        incident = Incident.last
        expect(incident.status).to eq('open')
        expect(incident.devin_session_id).to be_nil
        expect(ServicenowService).not_to have_received(:update_work_notes)
        expect(ServicenowService).not_to have_received(:update_state)
      end
    end
  end

  describe 'POST #resolve' do
    let!(:incident) { create(:incident, :with_snow, snow_ticket_number: 'INC0010001') }

    it 'resolves existing incident by ticket number' do
      post :resolve, params: { incident: { number: 'INC0010001', state: '6' } }

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('resolved')
      expect(incident.reload.status).to eq('resolved')
    end

    it 'resolves existing incident by sys_id' do
      post :resolve, params: { incident: { sys_id: incident.snow_sys_id, state: '7' } }

      expect(response).to have_http_status(:ok)
      expect(incident.reload.status).to eq('resolved')
    end

    it 'returns bad_request when neither number nor sys_id provided' do
      post :resolve, params: { incident: { state: '6' } }
      expect(response).to have_http_status(:bad_request)
    end

    it 'returns ok with nil incident_id when incident not found' do
      post :resolve, params: { incident: { number: 'INC9999999', state: '6' } }

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['incident_id']).to be_nil
    end

    it 'logs an audit entry for resolve' do
      post :resolve, params: { incident: { number: 'INC0010001', state: '6' } }
      expect(AuditLogger).to have_received(:log).with(
        hash_including(
          action: 'incident.resolved_from_snow',
          resource_type: 'Incident'
        )
      )
    end
  end

  describe 'authentication' do
    it 'returns 401 when X-Snow-Secret is invalid' do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return('correct-secret')
      request.headers['X-Snow-Secret'] = 'wrong-secret'

      post :ingest, params: valid_params
      expect(response).to have_http_status(:unauthorized)
    end

    it 'returns 401 when SNOW_WEBHOOK_SECRET is not configured (empty)' do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return(nil)

      post :ingest, params: valid_params
      expect(response).to have_http_status(:unauthorized)
      body = JSON.parse(response.body)
      expect(body['error']).to eq('Webhook secret not configured')
    end

    it 'returns 401 when SNOW_WEBHOOK_SECRET is blank string' do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return('')

      post :ingest, params: valid_params
      expect(response).to have_http_status(:unauthorized)
    end
  end
end
