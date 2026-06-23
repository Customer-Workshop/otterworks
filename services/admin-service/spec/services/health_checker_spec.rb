require 'rails_helper'

RSpec.describe HealthChecker do
  let(:mock_http) { instance_double(Net::HTTP) }
  let(:mock_response_200) { instance_double(Net::HTTPResponse, code: '200') }
  let(:mock_response_500) { instance_double(Net::HTTPResponse, code: '500') }

  before do
    allow(Net::HTTP).to receive(:new).and_return(mock_http)
    allow(mock_http).to receive(:open_timeout=)
    allow(mock_http).to receive(:read_timeout=)
  end

  describe '.check_all' do
    before do
      allow(mock_http).to receive(:get).and_return(mock_response_200)
      allow(ActiveRecord::Base.connection).to receive(:execute).with('SELECT 1')
      mock_redis = instance_double(Redis)
      allow(Redis).to receive(:new).and_return(mock_redis)
      allow(mock_redis).to receive(:ping).and_return('PONG')
      allow(mock_redis).to receive(:close)
    end

    it 'returns hash with status, timestamp, services, database, redis keys' do
      result = described_class.check_all
      expect(result).to have_key(:status)
      expect(result).to have_key(:timestamp)
      expect(result).to have_key(:services)
      expect(result).to have_key(:database)
      expect(result).to have_key(:redis)
    end

    it 'returns healthy when all services are healthy' do
      result = described_class.check_all
      expect(result[:status]).to eq('healthy')
    end

    context 'when a service is unhealthy' do
      before do
        call_count = 0
        allow(mock_http).to receive(:get) do
          call_count += 1
          call_count == 1 ? mock_response_500 : mock_response_200
        end
      end

      it 'returns degraded overall status' do
        result = described_class.check_all
        expect(result[:status]).to eq('degraded')
      end
    end
  end

  describe '.check_service' do
    it 'returns healthy status on 200 response' do
      allow(mock_http).to receive(:get).and_return(mock_response_200)
      result = described_class.check_service('auth-service')
      expect(result.status).to eq('healthy')
    end

    it 'returns unhealthy status on non-200 response' do
      allow(mock_http).to receive(:get).and_return(mock_response_500)
      result = described_class.check_service('auth-service')
      expect(result.status).to eq('unhealthy')
    end

    it 'returns unhealthy status on connection error' do
      allow(mock_http).to receive(:get).and_raise(Errno::ECONNREFUSED)
      result = described_class.check_service('auth-service')
      expect(result.status).to eq('unhealthy')
      expect(result.message).to be_present
    end

    it 'returns unknown when no port configured' do
      allow(ENV).to receive(:fetch).and_call_original
      allow(ENV).to receive(:fetch).with('UNKNOWN_SERVICE_HOST', 'unknown-service').and_return('unknown-service')
      allow(ENV).to receive(:fetch).with('UNKNOWN_SERVICE_PORT', nil).and_return(nil)
      result = described_class.check_service('unknown-service')
      expect(result.status).to eq('unknown')
      expect(result.message).to eq('No endpoint configured')
    end

    it 'measures latency_ms' do
      allow(mock_http).to receive(:get).and_return(mock_response_200)
      result = described_class.check_service('auth-service')
      expect(result.latency_ms).to be_a(Float)
      expect(result.latency_ms).to be >= 0
    end
  end

  describe '.check_database' do
    it 'returns healthy when DB responds' do
      allow(ActiveRecord::Base.connection).to receive(:execute).with('SELECT 1')
      result = described_class.check_database
      expect(result[:status]).to eq('healthy')
      expect(result[:latency_ms]).to be_a(Float)
    end

    it 'returns unhealthy on DB error' do
      allow(ActiveRecord::Base.connection).to receive(:execute).and_raise(ActiveRecord::ConnectionNotEstablished.new('connection error'))
      result = described_class.check_database
      expect(result[:status]).to eq('unhealthy')
      expect(result[:message]).to be_present
    end
  end

  describe '.check_redis' do
    it 'returns healthy when Redis responds' do
      mock_redis = instance_double(Redis)
      allow(Redis).to receive(:new).and_return(mock_redis)
      allow(mock_redis).to receive(:ping).and_return('PONG')
      allow(mock_redis).to receive(:close)
      result = described_class.check_redis
      expect(result[:status]).to eq('healthy')
      expect(result[:latency_ms]).to be_a(Float)
    end

    it 'returns unhealthy on Redis error' do
      allow(Redis).to receive(:new).and_raise(Redis::CannotConnectError.new('connection refused'))
      result = described_class.check_redis
      expect(result[:status]).to eq('unhealthy')
      expect(result[:message]).to be_present
    end
  end
end
