require 'rails_helper'

RSpec.describe HealthChecker do
  describe '.check_service' do
    it 'returns healthy for a 200 response' do
      stub_request(:get, 'http://auth-service:8081/health').to_return(status: 200)

      result = described_class.check_service('auth-service')
      expect(result.status).to eq('healthy')
      expect(result.name).to eq('auth-service')
      expect(result.latency_ms).to be >= 0
    end

    it 'returns unhealthy for a 500 response' do
      stub_request(:get, 'http://auth-service:8081/health').to_return(status: 500)

      result = described_class.check_service('auth-service')
      expect(result.status).to eq('unhealthy')
    end

    it 'returns unhealthy on connection error' do
      stub_request(:get, 'http://auth-service:8081/health').to_timeout

      result = described_class.check_service('auth-service')
      expect(result.status).to eq('unhealthy')
      expect(result.message).to be_present
    end
  end

  describe '.check_all' do
    before do
      described_class::SERVICES.each do |service|
        port = described_class::DEFAULT_PORTS[service]
        stub_request(:get, "http://#{service}:#{port}/health").to_return(status: 200)
      end
      allow(ActiveRecord::Base.connection).to receive(:execute).and_return(true)

      redis_mock = instance_double(Redis)
      allow(Redis).to receive(:new).and_return(redis_mock)
      allow(redis_mock).to receive(:ping).and_return('PONG')
      allow(redis_mock).to receive(:close)
    end

    it 'returns a health summary' do
      result = described_class.check_all
      expect(result[:status]).to eq('healthy')
      expect(result[:services]).to be_an(Array)
      expect(result[:services].length).to eq(described_class::SERVICES.length)
      expect(result[:database][:status]).to eq('healthy')
      expect(result[:redis][:status]).to eq('healthy')
    end
  end

  describe '.check_database' do
    it 'returns healthy when DB is accessible' do
      allow(ActiveRecord::Base.connection).to receive(:execute).and_return(true)
      result = described_class.check_database
      expect(result[:status]).to eq('healthy')
    end

    it 'returns unhealthy when DB is down' do
      allow(ActiveRecord::Base.connection).to receive(:execute).and_raise(ActiveRecord::ConnectionNotEstablished)
      result = described_class.check_database
      expect(result[:status]).to eq('unhealthy')
    end
  end
end
