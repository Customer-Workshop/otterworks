require 'rails_helper'

RSpec.describe Api::V1::Admin::UsersController do
  before { set_jwt_env(request) }

  describe 'GET #index' do
    let!(:users) { create_list(:admin_user, 3) }

    it 'returns paginated user list' do
      get :index
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['users'].length).to eq(3)
      expect(body['total']).to eq(3)
    end

    it 'filters by role' do
      create(:admin_user, :admin)
      get :index, params: { role: 'admin' }
      body = JSON.parse(response.body)
      expect(body['users'].all? { |u| u['role'] == 'admin' }).to be true
    end

    it 'filters by status' do
      create(:admin_user, :suspended)
      get :index, params: { status: 'suspended' }
      body = JSON.parse(response.body)
      expect(body['users'].all? { |u| u['status'] == 'suspended' }).to be true
    end

    it 'searches by query' do
      user = create(:admin_user, email: 'searchable@test.com')
      get :index, params: { q: 'searchable' }
      body = JSON.parse(response.body)
      expect(body['users'].any? { |u| u['id'] == user.id }).to be true
    end
  end

  describe 'GET #show' do
    let(:user) { create(:admin_user) }

    it 'returns user details' do
      get :show, params: { id: user.id }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['id']).to eq(user.id)
      expect(body['email']).to eq(user.email)
    end

    it 'returns 404 for missing user' do
      get :show, params: { id: SecureRandom.uuid }
      expect(response).to have_http_status(:not_found)
    end
  end

  describe 'PUT #update' do
    let(:user) { create(:admin_user) }

    it 'updates user attributes' do
      put :update, params: { id: user.id, user: { display_name: 'New Name' } }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['display_name']).to eq('New Name')
    end

    it 'returns errors for invalid params' do
      put :update, params: { id: user.id, user: { email: 'not-an-email' } }
      expect(response).to have_http_status(:unprocessable_entity)
    end

    it 'ignores role in the update payload' do
      put :update, params: { id: user.id, user: { display_name: 'New Name', role: 'super_admin' } }
      expect(response).to have_http_status(:ok)
      expect(user.reload.role).to eq('viewer')
    end

    it 'does not let a caller promote their own account via update' do
      set_jwt_env(request, user_id: user.id, role: 'viewer')
      put :update, params: { id: user.id, user: { role: 'super_admin' } }
      expect(response).to have_http_status(:ok)
      expect(user.reload.role).to eq('viewer')
    end
  end

  describe 'PUT #update_role' do
    let(:user) { create(:admin_user) }

    it 'lets a super admin change another user\'s role' do
      put :update_role, params: { id: user.id, role: 'editor' }
      expect(response).to have_http_status(:ok)
      expect(JSON.parse(response.body)['role']).to eq('editor')
      expect(user.reload.role).to eq('editor')
    end

    it 'rejects an invalid role' do
      put :update_role, params: { id: user.id, role: 'invalid_role' }
      expect(response).to have_http_status(:unprocessable_entity)
      expect(user.reload.role).to eq('viewer')
    end

    it 'returns 400 when role is missing' do
      put :update_role, params: { id: user.id }
      expect(response).to have_http_status(:bad_request)
    end

    %w[admin editor viewer].each do |caller_role|
      it "forbids a #{caller_role} from changing roles" do
        set_jwt_env(request, role: caller_role)
        put :update_role, params: { id: user.id, role: 'super_admin' }
        expect(response).to have_http_status(:forbidden)
        expect(user.reload.role).to eq('viewer')
      end
    end

    it 'forbids a caller from changing their own role' do
      set_jwt_env(request, user_id: user.id, role: 'super_admin')
      put :update_role, params: { id: user.id, role: 'viewer' }
      expect(response).to have_http_status(:forbidden)
    end
  end

  describe 'DELETE #destroy' do
    let(:user) { create(:admin_user) }

    it 'soft-deletes the user' do
      delete :destroy, params: { id: user.id }
      expect(response).to have_http_status(:no_content)
      expect(user.reload.status).to eq('deleted')
    end
  end

  describe 'PUT #suspend' do
    let(:user) { create(:admin_user) }

    it 'suspends the user' do
      put :suspend, params: { id: user.id, reason: 'Policy violation' }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('suspended')
    end
  end

  describe 'PUT #activate' do
    let(:user) { create(:admin_user, :suspended) }

    it 'activates the user' do
      put :activate, params: { id: user.id }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('active')
    end
  end
end
