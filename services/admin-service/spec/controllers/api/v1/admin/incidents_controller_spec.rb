require 'rails_helper'

RSpec.describe Api::V1::Admin::IncidentsController do
  before do
    set_jwt_env(request)
    allow(DevinSessionService).to receive(:create_session).and_return({ session_id: 'test-123', url: 'https://example.com' })
    allow(DevinSessionService).to receive(:get_session).and_return({ status: 'running', url: 'https://example.com' })
    allow(AuditLogger).to receive(:log)
  end

  describe 'GET #index' do
    let!(:open_incident) { create(:incident, status: 'open', severity: 'high') }
    let!(:investigating_incident) { create(:incident, :investigating, severity: 'medium') }
    let!(:resolved_incident) { create(:incident, :resolved, severity: 'low') }

    it 'returns all incidents' do
      get :index
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['incidents'].length).to eq(3)
    end

    it 'filters by status' do
      get :index, params: { status: 'open' }
      body = JSON.parse(response.body)
      expect(body['incidents'].length).to eq(1)
      expect(body['incidents'].first['status']).to eq('open')
    end

    it 'filters by severity' do
      get :index, params: { severity: 'high' }
      body = JSON.parse(response.body)
      expect(body['incidents'].length).to eq(1)
      expect(body['incidents'].first['severity']).to eq('high')
    end

    it 'filters active only' do
      get :index, params: { active: 'true' }
      body = JSON.parse(response.body)
      expect(body['incidents'].length).to eq(2)
      statuses = body['incidents'].map { |i| i['status'] }
      expect(statuses).to match_array(%w[open investigating])
    end

    it 'paginates results' do
      get :index, params: { page: 1, per_page: 2 }
      body = JSON.parse(response.body)
      expect(body['incidents'].length).to eq(2)
      expect(body['total']).to eq(3)
      expect(body['page']).to eq(1)
      expect(body['per_page']).to eq(2)
    end
  end

  describe 'GET #show' do
    let(:incident) { create(:incident) }

    it 'returns the incident with serialized data' do
      get :show, params: { id: incident.id }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['id']).to eq(incident.id)
      expect(body['title']).to eq(incident.title)
      expect(body['severity']).to eq(incident.severity)
      expect(body['status']).to eq(incident.status)
    end

    context 'when incident has an active devin session' do
      let(:incident) { create(:incident, :investigating, :with_devin_session) }

      it 'refreshes the devin session status' do
        get :show, params: { id: incident.id }
        expect(DevinSessionService).to have_received(:get_session).with(session_id: incident.devin_session_id)
        expect(response).to have_http_status(:ok)
      end
    end
  end

  describe 'POST #create' do
    let(:valid_params) do
      {
        incident: {
          title: 'Service outage',
          description: 'The file service is down',
          severity: 'high',
          affected_service: 'file-service'
        }
      }
    end

    it 'creates an incident with valid params' do
      expect do
        post :create, params: valid_params
      end.to change(Incident, :count).by(1)
      expect(response).to have_http_status(:created)
      body = JSON.parse(response.body)
      expect(body['title']).to eq('Service outage')
      expect(body['status']).to eq('investigating')
    end

    it 'triggers DevinSessionService on creation' do
      post :create, params: valid_params
      expect(DevinSessionService).to have_received(:create_session)
    end

    it 'returns 422 with invalid params' do
      post :create, params: { incident: { title: '', description: '' } }
      expect(response).to have_http_status(:unprocessable_entity)
      body = JSON.parse(response.body)
      expect(body['error']).to eq('Validation failed')
    end
  end

  describe 'PATCH #update' do
    let(:incident) { create(:incident, :investigating) }

    it 'transitions investigating to resolved' do
      patch :update, params: { id: incident.id, incident: { status: 'resolved' } }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('resolved')
    end

    it 'returns 422 for invalid transitions' do
      open_incident = create(:incident, status: 'open')
      patch :update, params: { id: open_incident.id, incident: { status: 'closed' } }
      expect(response).to have_http_status(:unprocessable_entity)
      body = JSON.parse(response.body)
      expect(body['error']).to eq('Invalid status transition')
    end
  end

  describe 'DELETE #destroy' do
    let!(:incident) { create(:incident) }

    it 'deletes the incident' do
      expect do
        delete :destroy, params: { id: incident.id }
      end.to change(Incident, :count).by(-1)
      expect(response).to have_http_status(:no_content)
    end

    context 'when incident has an active devin session' do
      let!(:incident) { create(:incident, :with_devin_session) }

      it 'returns 409 conflict' do
        expect do
          delete :destroy, params: { id: incident.id }
        end.not_to change(Incident, :count)
        expect(response).to have_http_status(:conflict)
        body = JSON.parse(response.body)
        expect(body['error']).to eq('Cannot delete incident with an active Devin session')
      end
    end
  end

  describe 'POST #trigger_session' do
    let(:incident) { create(:incident) }

    it 'creates a devin session' do
      post :trigger_session, params: { id: incident.id }
      expect(response).to have_http_status(:ok)
      expect(DevinSessionService).to have_received(:create_session).with(incident: incident)
      body = JSON.parse(response.body)
      expect(body['devin_session_id']).to eq('test-123')
    end

    context 'when incident already has a session' do
      let(:incident) { create(:incident, :with_devin_session) }

      it 'returns 422' do
        post :trigger_session, params: { id: incident.id }
        expect(response).to have_http_status(:unprocessable_entity)
        body = JSON.parse(response.body)
        expect(body['error']).to eq('Incident already has a Devin session')
      end
    end
  end
end
