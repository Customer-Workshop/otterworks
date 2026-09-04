require 'rails_helper'

RSpec.describe Api::V1::Admin::IncidentsController do
  let(:reporter_id) { SecureRandom.uuid }
  let!(:incident) { create(:incident, reporter_id: reporter_id) }

  describe 'object-level authorization' do
    context 'when the caller reported the incident' do
      before { set_jwt_env(request, user_id: reporter_id, role: 'viewer') }

      it 'allows reading it' do
        get :show, params: { id: incident.id }
        expect(response).to have_http_status(:ok)
      end

      it 'allows transitioning it' do
        put :update, params: { id: incident.id, incident: { status: 'investigating' } }
        expect(response).to have_http_status(:ok)
      end

      it 'allows deleting it' do
        expect do
          delete :destroy, params: { id: incident.id }
        end.to change(Incident, :count).by(-1)
      end
    end

    context 'when the caller is a different authenticated user' do
      before { set_jwt_env(request, user_id: SecureRandom.uuid, role: 'viewer') }

      it 'rejects reading it' do
        get :show, params: { id: incident.id }
        expect(response).to have_http_status(:forbidden)
      end

      it 'rejects transitioning it' do
        put :update, params: { id: incident.id, incident: { status: 'investigating' } }
        expect(response).to have_http_status(:forbidden)
        expect(incident.reload.status).to eq('open')
      end

      it 'rejects deleting it' do
        expect do
          delete :destroy, params: { id: incident.id }
        end.not_to change(Incident, :count)
        expect(response).to have_http_status(:forbidden)
      end

      it 'rejects triggering a Devin session on it' do
        post :trigger_session, params: { id: incident.id }
        expect(response).to have_http_status(:forbidden)
      end

      it 'rejects acting on a system-reported incident' do
        system_incident = create(:incident, :system_reported)
        get :show, params: { id: system_incident.id }
        expect(response).to have_http_status(:forbidden)
      end
    end

    context 'when the caller has no identity' do
      before do
        request.env['jwt.user_id'] = nil
        request.env['jwt.user_role'] = nil
      end

      it 'rejects the request as unauthenticated' do
        get :show, params: { id: incident.id }
        expect(response).to have_http_status(:unauthorized)
      end
    end

    context 'when the caller is an admin' do
      before { set_jwt_env(request, user_id: SecureRandom.uuid, role: 'admin') }

      it 'allows reading another reporter\'s incident' do
        get :show, params: { id: incident.id }
        expect(response).to have_http_status(:ok)
      end
    end

    context 'when identity comes from the gateway-injected X-User-ID header' do
      before { request.headers['X-User-ID'] = reporter_id }

      it 'allows the owner' do
        get :show, params: { id: incident.id }
        expect(response).to have_http_status(:ok)
      end
    end
  end
end
