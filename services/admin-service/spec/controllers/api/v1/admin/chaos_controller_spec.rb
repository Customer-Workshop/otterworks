require 'rails_helper'

RSpec.describe Api::V1::Admin::ChaosController do
  let(:mock_redis) do
    instance_double(Redis,
                    setex: true,
                    keys: ['chaos:search-service:suggest_500'],
                    del: 1,
                    exists?: true)
  end

  before do
    allow(Redis).to receive(:new).and_return(mock_redis)
    allow(ChaosProbeService).to receive(:start)
  end

  describe 'secret verification' do
    context 'when CHAOS_SECRET is configured' do
      before { allow(ENV).to receive(:fetch).and_call_original }
      before { allow(ENV).to receive(:fetch).with('CHAOS_SECRET', nil).and_return('my-secret') }

      it 'returns 401 when X-Chaos-Secret header is missing' do
        post :trigger, params: { service: 'search-service', scenario: 'suggest_500' }
        expect(response).to have_http_status(:unauthorized)
        body = JSON.parse(response.body)
        expect(body['error']).to eq('Unauthorized')
      end

      it 'returns 401 when X-Chaos-Secret header is wrong' do
        request.headers['X-Chaos-Secret'] = 'wrong-secret'
        post :trigger, params: { service: 'search-service', scenario: 'suggest_500' }
        expect(response).to have_http_status(:unauthorized)
      end

      it 'allows request when X-Chaos-Secret header matches' do
        request.headers['X-Chaos-Secret'] = 'my-secret'
        post :trigger, params: { service: 'search-service', scenario: 'suggest_500' }
        expect(response).not_to have_http_status(:unauthorized)
      end
    end

    context 'when CHAOS_SECRET is not configured (dev mode)' do
      before { allow(ENV).to receive(:fetch).and_call_original }
      before { allow(ENV).to receive(:fetch).with('CHAOS_SECRET', nil).and_return(nil) }

      it 'allows request without any secret header' do
        post :trigger, params: { service: 'search-service', scenario: 'suggest_500' }
        expect(response).not_to have_http_status(:unauthorized)
      end
    end
  end

  describe 'POST #trigger' do
    before do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('CHAOS_SECRET', nil).and_return(nil)
    end

    context 'with a valid service/scenario combination' do
      it 'sets Redis key and returns chaos_active' do
        post :trigger, params: { service: 'search-service', scenario: 'suggest_500' }
        expect(response).to have_http_status(:ok)
        body = JSON.parse(response.body)
        expect(body['status']).to eq('chaos_active')
        expect(body['key']).to eq('chaos:search-service:suggest_500')
        expect(body['expires_in']).to eq(600)
        expect(mock_redis).to have_received(:setex).with('chaos:search-service:suggest_500', 600, '1')
        expect(ChaosProbeService).to have_received(:start).with(service: 'search-service', redis_key: 'chaos:search-service:suggest_500')
      end
    end

    context 'with an invalid service/scenario combination' do
      it 'returns 422 with valid scenarios listed' do
        post :trigger, params: { service: 'search-service', scenario: 'bad_scenario' }
        expect(response).to have_http_status(:unprocessable_entity)
        body = JSON.parse(response.body)
        expect(body['error']).to eq('Invalid service/scenario combination')
        expect(body['valid']).to be_a(Hash)
        expect(body['valid']['search-service']).to eq('suggest_500')
      end
    end
  end

  describe 'DELETE #reset' do
    before do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('CHAOS_SECRET', nil).and_return(nil)
    end

    it 'clears chaos keys and resolves open incidents' do
      open_incident = create(:incident, affected_service: 'search-service', status: 'open')
      investigating_incident = create(:incident, affected_service: 'file-service', status: 'investigating')

      delete :reset
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body['status']).to eq('reset')
      expect(body['cleared']).to eq(['chaos:search-service:suggest_500'])
      expect(mock_redis).to have_received(:keys).with('chaos:*')
      expect(mock_redis).to have_received(:del).with('chaos:search-service:suggest_500')

      open_incident.reload
      investigating_incident.reload
      expect(open_incident.status).to eq('resolved')
      expect(investigating_incident.status).to eq('resolved')
    end
  end
end
