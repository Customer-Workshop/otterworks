require 'rails_helper'

RSpec.describe DevinSessionService do
  let(:incident) { create(:incident) }

  describe '.create_session' do
    context 'when DEVIN_API_KEY is not set' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return(nil)
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return('org-123')
      end

      it 'returns nil' do
        expect(described_class.create_session(incident: incident)).to be_nil
      end
    end

    context 'when DEVIN_ORG_ID is not set' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return('key-123')
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return(nil)
      end

      it 'returns nil' do
        expect(described_class.create_session(incident: incident)).to be_nil
      end
    end

    context 'when credentials are set' do
      let(:mock_http) { instance_double(Net::HTTP) }
      let(:success_body) { { 'session_id' => 'sess-abc', 'url' => 'https://app.devin.ai/sessions/sess-abc' }.to_json }
      let(:success_response) { instance_double(Net::HTTPSuccess, body: success_body, code: '200') }

      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return('key-123')
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return('org-123')
        allow(Net::HTTP).to receive(:new).and_return(mock_http)
        allow(mock_http).to receive(:use_ssl=)
        allow(mock_http).to receive(:open_timeout=)
        allow(mock_http).to receive(:read_timeout=)
      end

      it 'makes HTTP POST to correct URL with correct headers' do
        allow(mock_http).to receive(:request) do |req|
          expect(req).to be_a(Net::HTTP::Post)
          expect(req.path).to eq('/v3/organizations/org-123/sessions')
          expect(req['Authorization']).to eq('Bearer key-123')
          expect(req['Content-Type']).to eq('application/json')
          success_response
        end
        allow(success_response).to receive(:is_a?).with(Net::HTTPSuccess).and_return(true)

        described_class.create_session(incident: incident)
      end

      it 'returns session_id and url on success' do
        allow(mock_http).to receive(:request).and_return(success_response)
        allow(success_response).to receive(:is_a?).with(Net::HTTPSuccess).and_return(true)

        result = described_class.create_session(incident: incident)
        expect(result[:session_id]).to eq('sess-abc')
        expect(result[:url]).to eq('https://app.devin.ai/sessions/sess-abc')
      end

      it 'returns nil on HTTP error' do
        error_response = instance_double(Net::HTTPServerError, body: 'Internal Server Error', code: '500')
        allow(error_response).to receive(:is_a?).with(Net::HTTPSuccess).and_return(false)
        allow(mock_http).to receive(:request).and_return(error_response)

        expect(described_class.create_session(incident: incident)).to be_nil
      end

      it 'returns nil on network exception' do
        allow(mock_http).to receive(:request).and_raise(Errno::ECONNREFUSED)

        expect(described_class.create_session(incident: incident)).to be_nil
      end
    end
  end

  describe '.get_session' do
    context 'when credentials are missing' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return(nil)
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return(nil)
      end

      it 'returns nil' do
        expect(described_class.get_session(session_id: 'sess-abc')).to be_nil
      end
    end

    context 'when credentials are set' do
      let(:mock_http) { instance_double(Net::HTTP) }

      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return('key-123')
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return('org-123')
        allow(Net::HTTP).to receive(:new).and_return(mock_http)
        allow(mock_http).to receive(:use_ssl=)
        allow(mock_http).to receive(:open_timeout=)
        allow(mock_http).to receive(:read_timeout=)
      end

      it 'returns status and url on success' do
        success_body = { 'status' => 'running', 'url' => 'https://app.devin.ai/sessions/sess-abc' }.to_json
        success_response = instance_double(Net::HTTPSuccess, body: success_body, code: '200')
        allow(success_response).to receive(:is_a?).with(Net::HTTPSuccess).and_return(true)
        allow(mock_http).to receive(:request).and_return(success_response)

        result = described_class.get_session(session_id: 'sess-abc')
        expect(result[:status]).to eq('running')
        expect(result[:url]).to eq('https://app.devin.ai/sessions/sess-abc')
      end

      it 'returns nil on failure' do
        error_response = instance_double(Net::HTTPServerError, body: 'Error', code: '500')
        allow(error_response).to receive(:is_a?).with(Net::HTTPSuccess).and_return(false)
        allow(mock_http).to receive(:request).and_return(error_response)

        expect(described_class.get_session(session_id: 'sess-abc')).to be_nil
      end
    end
  end
end
