require 'rails_helper'

RSpec.describe Api::V1::Admin::ConfigController do
  let!(:config) { create(:system_config, value: 'old_value') }

  shared_examples 'forbidden' do
    it 'rejects reads with 403' do
      get :index
      expect(response).to have_http_status(:forbidden)
      expect(response.parsed_body['error']).to eq('Forbidden')
    end

    it 'rejects writes with 403 and leaves data untouched' do
      put :update, params: { id: config.id, config: { value: 'new_value' } }
      expect(response).to have_http_status(:forbidden)
      expect(config.reload.value).to eq('old_value')
    end
  end

  context 'with a non-admin role' do
    before { set_jwt_env(request, role: 'USER') }

    it_behaves_like 'forbidden'
  end

  context 'with a viewer role' do
    before { set_jwt_env(request, role: 'viewer') }

    it_behaves_like 'forbidden'
  end

  context 'with no role claim' do
    before { set_jwt_env(request, role: nil) }

    it_behaves_like 'forbidden'
  end

  context 'with an admin role' do
    before { set_jwt_env(request, role: 'admin') }

    it 'allows access' do
      get :index
      expect(response).to have_http_status(:ok)
    end
  end

  context 'with an ADMIN entry in a roles array claim' do
    before do
      set_jwt_env(request, role: nil)
      request.env['jwt.payload'] = { 'roles' => %w[USER ADMIN] }
    end

    it 'allows access' do
      get :index
      expect(response).to have_http_status(:ok)
    end
  end

  context 'with only USER in a roles array claim' do
    before do
      set_jwt_env(request, role: nil)
      request.env['jwt.payload'] = { 'roles' => %w[USER] }
    end

    it_behaves_like 'forbidden'
  end
end
