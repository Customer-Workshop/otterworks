require 'rails_helper'

RSpec.describe Api::V1::Admin::BulkController do
  before { set_jwt_env(request) }

  describe 'POST #users' do
    let!(:users) { create_list(:admin_user, 3) }
    let(:user_ids) { users.map(&:id) }

    it 'suspends multiple users' do
      post :users, params: { operation: 'suspend', user_ids: user_ids, reason: 'Policy' }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['success_count']).to eq(3)
      expect(body['failure_count']).to eq(0)
    end

    it 'activates multiple users' do
      users.each(&:suspend!)
      post :users, params: { operation: 'activate', user_ids: user_ids }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['success_count']).to eq(3)
    end

    it 'returns multi_status when some users not found' do
      post :users, params: { operation: 'suspend', user_ids: user_ids + [SecureRandom.uuid] }
      expect(response).to have_http_status(:multi_status)
      body = JSON.parse(response.body)
      expect(body['failure_count']).to eq(1)
    end

    it 'returns bad_request for empty user_ids' do
      post :users, params: { operation: 'suspend', user_ids: [] }
      expect(response).to have_http_status(:bad_request)
    end
  end

  describe 'object-level authorization' do
    let(:caller_user) { create(:admin_user) }

    context 'when a non-admin targets only itself' do
      before { set_jwt_env(request, user_id: caller_user.id, role: 'viewer') }

      it 'allows the operation' do
        post :users, params: { operation: 'suspend', user_ids: [caller_user.id] }
        expect(response).to have_http_status(:ok)
      end
    end

    context 'when a non-admin targets other users' do
      before { set_jwt_env(request, user_id: caller_user.id, role: 'viewer') }

      it 'rejects the operation' do
        other = create(:admin_user)
        post :users, params: { operation: 'suspend', user_ids: [caller_user.id, other.id] }
        expect(response).to have_http_status(:forbidden)
        expect(other.reload.status).to eq('active')
      end
    end

    context 'when the caller has no identity' do
      before do
        request.env['jwt.user_id'] = nil
        request.env['jwt.user_role'] = nil
      end

      it 'rejects the request as unauthenticated' do
        post :users, params: { operation: 'suspend', user_ids: [caller_user.id] }
        expect(response).to have_http_status(:unauthorized)
      end
    end
  end
end
