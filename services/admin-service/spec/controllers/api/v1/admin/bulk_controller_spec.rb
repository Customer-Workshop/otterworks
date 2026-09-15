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

    it 'lets a super admin update roles in bulk' do
      post :users, params: { operation: 'update_role', user_ids: user_ids, role: 'editor' }
      expect(response).to have_http_status(:ok)
      expect(users.map { |u| u.reload.role }.uniq).to eq(['editor'])
    end

    it 'forbids non-super-admins from updating roles in bulk' do
      set_jwt_env(request, role: 'admin')
      post :users, params: { operation: 'update_role', user_ids: user_ids, role: 'super_admin' }
      expect(response).to have_http_status(:forbidden)
      expect(users.map { |u| u.reload.role }.uniq).to eq(['viewer'])
    end

    it 'forbids a caller from changing their own role in bulk' do
      set_jwt_env(request, user_id: users.first.id, role: 'super_admin')
      post :users, params: { operation: 'update_role', user_ids: user_ids, role: 'editor' }
      expect(response).to have_http_status(:forbidden)
      expect(users.map { |u| u.reload.role }.uniq).to eq(['viewer'])
    end
  end
end
