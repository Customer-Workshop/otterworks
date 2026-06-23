require 'rails_helper'

RSpec.describe Api::V1::Admin::SettingsController do
  before { set_jwt_env(request) }

  before do
    allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(true)
    allow(AdminSettingsService).to receive(:set_auto_investigate)
  end

  describe 'GET #auto_investigate' do
    it 'returns JSON with enabled boolean' do
      get :auto_investigate
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['enabled']).to be true
    end

    it 'returns false when auto_investigate is disabled' do
      allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(false)

      get :auto_investigate
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['enabled']).to be false
    end
  end

  describe 'PUT #update_auto_investigate' do
    it 'sets enabled to true and returns updated value' do
      put :update_auto_investigate, params: { enabled: true }
      expect(response).to have_http_status(:ok)
      expect(AdminSettingsService).to have_received(:set_auto_investigate).with(true)
      body = JSON.parse(response.body)
      expect(body['enabled']).to be true
    end

    it 'sets enabled to false and returns updated value' do
      allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(false)

      put :update_auto_investigate, params: { enabled: false }
      expect(response).to have_http_status(:ok)
      expect(AdminSettingsService).to have_received(:set_auto_investigate).with(false)
      body = JSON.parse(response.body)
      expect(body['enabled']).to be false
    end

    it 'returns 400 when enabled param is missing' do
      put :update_auto_investigate, params: {}
      expect(response).to have_http_status(:bad_request)
      body = JSON.parse(response.body)
      expect(body['error']).to include('Missing required parameter')
    end
  end
end
