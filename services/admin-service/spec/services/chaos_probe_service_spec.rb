require 'rails_helper'

RSpec.describe ChaosProbeService do
  describe '.fire_probe' do
    it 'builds GET request for simple configs' do
      config = described_class::SERVICE_PROBES['search-service']
      mock_http = instance_double(Net::HTTP)
      allow(Net::HTTP).to receive(:new).and_return(mock_http)
      allow(mock_http).to receive(:open_timeout=)
      allow(mock_http).to receive(:read_timeout=)
      allow(mock_http).to receive(:request).and_return(instance_double(Net::HTTPResponse, code: '200'))

      described_class.fire_probe(config)

      expect(mock_http).to have_received(:request) do |req|
        expect(req).to be_a(Net::HTTP::Get)
        expect(req['X-User-ID']).to eq('chaos-probe')
      end
    end
  end

  describe '.build_multipart_request' do
    it 'creates proper multipart body with boundary' do
      uri = URI.parse('http://file-service:8082/api/v1/files/upload')
      req = described_class.build_multipart_request(uri)

      expect(req).to be_a(Net::HTTP::Post)
      expect(req['Content-Type']).to match(%r{multipart/form-data; boundary=chaos-probe-})
      expect(req.body).to include('Content-Disposition: form-data; name="file"; filename="probe.txt"')
      expect(req.body).to include('chaos probe')
    end
  end

  describe '.build_sqs_request' do
    it 'creates proper SQS SendMessage body with malformed timestamp' do
      uri = URI.parse('http://localstack:4566/000000000000/otterworks-notifications')
      req = described_class.build_sqs_request(uri)

      expect(req).to be_a(Net::HTTP::Post)
      expect(req['Content-Type']).to eq('application/x-www-form-urlencoded')

      body_params = URI.decode_www_form(req.body).to_h
      expect(body_params['Action']).to eq('SendMessage')
      expect(body_params['Version']).to eq('2012-11-05')

      message = JSON.parse(body_params['MessageBody'])
      expect(message['eventType']).to eq('file_shared')
      expect(message['timestamp']).to be_a(Integer)
    end
  end

  describe '.start' do
    it 'returns nil for unknown service' do
      result = described_class.start(service: 'nonexistent-service', redis_key: 'chaos:nonexistent:test')
      expect(result).to be_nil
    end
  end
end
