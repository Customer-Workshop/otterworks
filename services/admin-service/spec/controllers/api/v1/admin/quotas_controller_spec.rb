require 'rails_helper'

RSpec.describe Api::V1::Admin::QuotasController do
  before { set_jwt_env(request) }

  let(:user_id) { SecureRandom.uuid }
  let!(:quota) { create(:storage_quota, user_id: user_id) }

  describe 'GET #show' do
    it 'returns the storage quota for a user' do
      get :show, params: { user_id: user_id }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['user_id']).to eq(user_id)
      expect(body['tier']).to eq('free')
    end

    it 'returns 404 for unknown user' do
      get :show, params: { user_id: SecureRandom.uuid }
      expect(response).to have_http_status(:not_found)
    end
  end

  describe 'PUT #update' do
    it 'updates the quota' do
      put :update, params: { user_id: user_id, quota: { tier: 'pro', quota_bytes: 214_748_364_800 } }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['tier']).to eq('pro')
    end

    it 'returns errors for invalid params' do
      put :update, params: { user_id: user_id, quota: { tier: 'invalid' } }
      expect(response).to have_http_status(:unprocessable_entity)
    end
  end

  describe 'object-level authorization' do
    context 'when the caller owns the quota' do
      before { set_jwt_env(request, user_id: user_id, role: 'viewer') }

      it 'allows reading it' do
        get :show, params: { user_id: user_id }
        expect(response).to have_http_status(:ok)
      end

      it 'allows updating it' do
        put :update, params: { user_id: user_id, quota: { tier: 'pro' } }
        expect(response).to have_http_status(:ok)
      end
    end

    context 'when the caller is a different authenticated user' do
      before { set_jwt_env(request, user_id: SecureRandom.uuid, role: 'viewer') }

      it 'rejects reading another user quota' do
        get :show, params: { user_id: user_id }
        expect(response).to have_http_status(:forbidden)
      end

      it 'rejects updating another user quota' do
        put :update, params: { user_id: user_id, quota: { tier: 'enterprise' } }
        expect(response).to have_http_status(:forbidden)
        expect(quota.reload.tier).to eq('free')
      end
    end

    context 'when the caller has no identity' do
      before do
        request.env['jwt.user_id'] = nil
        request.env['jwt.user_role'] = nil
      end

      it 'rejects the request as unauthenticated' do
        get :show, params: { user_id: user_id }
        expect(response).to have_http_status(:unauthorized)
      end
    end

    context 'when the caller is an admin' do
      before { set_jwt_env(request, user_id: SecureRandom.uuid, role: 'admin') }

      it 'allows updating any user quota' do
        put :update, params: { user_id: user_id, quota: { tier: 'pro' } }
        expect(response).to have_http_status(:ok)
      end
    end
  end
end
