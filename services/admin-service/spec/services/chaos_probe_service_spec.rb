require 'rails_helper'

RSpec.describe ChaosProbeService do
  describe 'SERVICE_PROBES' do
    it 'includes known services' do
      expect(described_class::SERVICE_PROBES).to have_key('search-service')
      expect(described_class::SERVICE_PROBES).to have_key('file-service')
      expect(described_class::SERVICE_PROBES).to have_key('notification-service')
      expect(described_class::SERVICE_PROBES).to have_key('document-service')
    end
  end

  describe '.start' do
    it 'returns nil for unknown service' do
      expect(described_class.start(service: 'nonexistent', redis_key: 'key')).to be_nil
    end
  end

  describe '.fire_probe' do
    it 'sends a GET request by default' do
      stub_request(:get, 'http://search-service:8087/api/v1/search/suggest?q=test')
        .to_return(status: 200)

      config = described_class::SERVICE_PROBES['search-service']
      described_class.fire_probe(config)

      expect(WebMock).to have_requested(:get, 'http://search-service:8087/api/v1/search/suggest?q=test')
    end

    it 'does not raise on connection error' do
      stub_request(:get, 'http://nonexistent:9999/health')
        .to_raise(Errno::ECONNREFUSED)

      config = {
        url: 'http://nonexistent:9999/health',
        headers: {},
      }
      expect { described_class.fire_probe(config) }.not_to raise_error
    end
  end

  describe '.build_multipart_request' do
    it 'creates a POST request with multipart body' do
      uri = URI.parse('http://file-service:8082/api/v1/files/upload')
      request = described_class.build_multipart_request(uri)
      expect(request).to be_a(Net::HTTP::Post)
      expect(request['Content-Type']).to include('multipart/form-data')
    end
  end
end
