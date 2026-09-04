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
      put :update, params: { id: user.id, user: { role: 'invalid_role' } }
      expect(response).to have_http_status(:unprocessable_entity)
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

  describe 'object-level authorization' do
    let(:target) { create(:admin_user, role: 'viewer') }

    context 'when the caller is the subject of the record' do
      before { set_jwt_env(request, user_id: target.id, role: 'viewer') }

      it 'allows reading their own record' do
        get :show, params: { id: target.id }
        expect(response).to have_http_status(:ok)
      end

      it 'ignores a role change attempted by a non-admin' do
        put :update, params: { id: target.id, user: { display_name: 'Renamed', role: 'super_admin' } }
        expect(response).to have_http_status(:ok)
        expect(target.reload.display_name).to eq('Renamed')
        expect(target.role).to eq('viewer')
      end
    end

    context 'when the caller is a different authenticated user' do
      before { set_jwt_env(request, user_id: SecureRandom.uuid, role: 'viewer') }

      it 'rejects reading the record' do
        get :show, params: { id: target.id }
        expect(response).to have_http_status(:forbidden)
      end

      it 'rejects updating the record' do
        put :update, params: { id: target.id, user: { display_name: 'Hijacked' } }
        expect(response).to have_http_status(:forbidden)
      end

      it 'rejects deleting the record' do
        delete :destroy, params: { id: target.id }
        expect(response).to have_http_status(:forbidden)
        expect(target.reload.status).to eq('active')
      end

      it 'rejects suspending the record even for itself' do
        set_jwt_env(request, user_id: target.id, role: 'viewer')
        put :suspend, params: { id: target.id }
        expect(response).to have_http_status(:forbidden)
      end
    end

    context 'when the caller has no identity' do
      before do
        request.env['jwt.user_id'] = nil
        request.env['jwt.user_role'] = nil
      end

      it 'rejects the request as unauthenticated' do
        get :show, params: { id: target.id }
        expect(response).to have_http_status(:unauthorized)
      end
    end

    context 'when the caller is an admin' do
      before { set_jwt_env(request, user_id: SecureRandom.uuid, role: 'admin') }

      it 'allows updating any user, including their role' do
        put :update, params: { id: target.id, user: { role: 'editor' } }
        expect(response).to have_http_status(:ok)
        expect(target.reload.role).to eq('editor')
      end

      it 'allows suspending any user' do
        put :suspend, params: { id: target.id }
        expect(response).to have_http_status(:ok)
      end
    end
  end
end
