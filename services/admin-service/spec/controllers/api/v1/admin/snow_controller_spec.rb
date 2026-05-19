require 'rails_helper'

RSpec.describe Api::V1::Admin::SnowController do
  before do
    set_jwt_env(request)
    allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(true)
    allow(DevinSessionService).to receive(:create_session).and_return(
      { session_id: 'dev-123', url: 'https://app.devin.ai/sessions/dev-123' }
    )
    allow(ServicenowService).to receive(:update_work_notes).and_return({})
    allow(ServicenowService).to receive(:update_state).and_return({})
    allow(SnowSyncJob).to receive_message_chain(:set, :perform_later) # rubocop:disable RSpec/MessageChain
  end

  let(:valid_params) do
    {
      number: 'INC0010001',
      short_description: 'Auth service returning 500',
      description: 'Users cannot login, auth-service returning 500 errors',
      priority: '1',
      affected_service: 'auth-service',
      sys_id: 'abc123def456',
      state: '1',
      caller_id: 'admin'
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

    it 'maps SNOW priority 1 to critical severity' do
      post :ingest, params: valid_params.merge(priority: '1')
      incident = Incident.last
      expect(incident.severity).to eq('critical')
    end

    it 'maps SNOW priority 2 to high severity' do
      post :ingest, params: valid_params.merge(priority: '2')
      incident = Incident.last
      expect(incident.severity).to eq('high')
    end

    it 'maps SNOW priority 3 to medium severity' do
      post :ingest, params: valid_params.merge(priority: '3')
      incident = Incident.last
      expect(incident.severity).to eq('medium')
    end

    it 'maps SNOW priority 4/5 to low severity' do
      post :ingest, params: valid_params.merge(priority: '4')
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

    it 'resolves existing incident when SNOW state is 6' do
      incident = create(:incident, :with_snow, snow_ticket_number: 'INC0010001')

      post :ingest, params: valid_params.merge(state: '6')

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('resolved')
      expect(incident.reload.status).to eq('resolved')
    end

    it 'resolves existing incident when SNOW state is 7' do
      incident = create(:incident, :with_snow, snow_ticket_number: 'INC0010001')

      post :ingest, params: valid_params.merge(state: '7')

      expect(incident.reload.status).to eq('resolved')
    end

    it 'returns bad_request when required fields are missing' do
      post :ingest, params: { number: 'INC0010001' }
      expect(response).to have_http_status(:bad_request)
    end

    it 'posts Devin session URL back to SNOW as work_note' do
      post :ingest, params: valid_params

      expect(ServicenowService).to have_received(:update_work_notes).with(
        sys_id: 'abc123def456',
        notes: 'Devin AI session launched: https://app.devin.ai/sessions/dev-123'
      )
    end

    it 'updates SNOW ticket state to 2 (In Progress) when Devin session launches' do
      post :ingest, params: valid_params

      expect(ServicenowService).to have_received(:update_state).with(
        sys_id: 'abc123def456',
        state: '2',
        work_notes: 'OtterWorks auto-investigation in progress'
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

    context 'when auto_investigate is disabled' do
      before { allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(false) }

      it 'creates incident with open status and no Devin session' do
        post :ingest, params: valid_params
        incident = Incident.last
        expect(incident.status).to eq('open')
        expect(incident.devin_session_id).to be_nil
      end
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

    it 'allows request when SNOW_WEBHOOK_SECRET is not configured' do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('SNOW_WEBHOOK_SECRET', nil).and_return(nil)

      post :ingest, params: valid_params
      expect(response).to have_http_status(:ok)
    end
  end
end
