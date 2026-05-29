require 'rails_helper'

RSpec.describe Api::V1::Admin::DevinCallbackController, type: :request do
  describe 'POST /api/v1/admin/devin/callback' do
    let!(:incident) do
      create(:incident, :investigating, :with_devin_session)
    end

    context 'with a completed session' do
      it 'resolves the incident' do
        post '/api/v1/admin/devin/callback',
             params: { session_id: incident.devin_session_id, status: 'finished' },
             as: :json

        expect(response).to have_http_status(:ok)

        incident.reload
        expect(incident.devin_session_status).to eq('finished')
        expect(incident.status).to eq('resolved')
        expect(incident.resolved_at).to be_present
      end
    end

    context 'with a failed session' do
      it 'updates session status but does not resolve' do
        post '/api/v1/admin/devin/callback',
             params: { session_id: incident.devin_session_id, status: 'failed' },
             as: :json

        expect(response).to have_http_status(:ok)

        incident.reload
        expect(incident.devin_session_status).to eq('failed')
        expect(incident.status).to eq('investigating')
      end
    end

    context 'with a servicenow-sourced incident' do
      let!(:snow_incident) do
        create(:incident, :servicenow, :investigating, :with_devin_session)
      end

      it 'triggers ServiceNow callback on completion' do
        allow(ServicenowCallbackService).to receive(:resolve_incident)

        post '/api/v1/admin/devin/callback',
             params: {
               session_id: snow_incident.devin_session_id,
               status: 'finished',
               pr_url: 'https://github.com/org/repo/pull/99'
             },
             as: :json

        expect(response).to have_http_status(:ok)
        expect(ServicenowCallbackService).to have_received(:resolve_incident)
      end

      it 'posts failure update to ServiceNow on errored status' do
        allow(ServicenowCallbackService).to receive(:post_update)

        post '/api/v1/admin/devin/callback',
             params: { session_id: snow_incident.devin_session_id, status: 'errored' },
             as: :json

        expect(response).to have_http_status(:ok)
        expect(ServicenowCallbackService).to have_received(:post_update)
      end
    end

    context 'with missing session_id' do
      it 'returns 400' do
        post '/api/v1/admin/devin/callback', params: { status: 'finished' }, as: :json

        expect(response).to have_http_status(:bad_request)
      end
    end

    context 'with non-existent session_id' do
      it 'returns 404' do
        post '/api/v1/admin/devin/callback',
             params: { session_id: 'nonexistent', status: 'finished' },
             as: :json

        expect(response).to have_http_status(:not_found)
      end
    end

    it 'does not require JWT authentication' do
      post '/api/v1/admin/devin/callback',
           params: { session_id: incident.devin_session_id, status: 'finished' },
           as: :json

      expect(response).not_to have_http_status(:unauthorized)
    end
  end
end
