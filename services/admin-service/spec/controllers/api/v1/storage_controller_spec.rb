require 'rails_helper'

RSpec.describe Api::V1::StorageController do
  let(:user_id) { SecureRandom.uuid }

  before { set_jwt_env(request, user_id: user_id) }

  describe 'GET #quota' do
    it "returns the current user's quota" do
      create(:storage_quota, user_id: user_id, tier: 'free',
                             quota_bytes: 5_368_709_120, used_bytes: 4_831_838_208) # 90%

      get :quota

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['user_id']).to eq(user_id)
      expect(body['tier']).to eq('free')
      expect(body['usage_percentage']).to be >= 90
    end

    it 'evaluates usage against the tier quota_bytes (per-tier)' do
      create(:storage_quota, :pro, user_id: user_id, used_bytes: 150_000_000_000) # 150GB of 200GB

      get :quota

      body = JSON.parse(response.body)
      expect(body['tier']).to eq('pro')
      expect(body['quota_bytes']).to eq(214_748_364_800)
      expect(body['usage_percentage']).to be < 90 # 150/200 = 75%, respects pro quota
    end

    it 'returns a free-tier default when the user has no quota row' do
      get :quota

      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['tier']).to eq('free')
      expect(body['quota_bytes']).to eq(StorageQuota::TIER_LIMITS.fetch('free'))
      expect(body['used_bytes']).to eq(0)
      expect(body['usage_percentage']).to eq(0)
    end

    it "does not return another user's quota" do
      other_id = SecureRandom.uuid
      create(:storage_quota, :over_quota, user_id: other_id)

      get :quota

      body = JSON.parse(response.body)
      # Caller has no row of their own -> free-tier default, never the other user's row.
      expect(body['used_bytes']).to eq(0)
      expect(body['over_quota']).to eq(false)
    end
  end
end
