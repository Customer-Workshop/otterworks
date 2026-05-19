require 'rails_helper'

RSpec.describe DevinSessionService do
  describe '.create_session' do
    let(:incident) do
      Incident.create!(
        title: 'Search down', description: 'Search not returning results',
        severity: 'high', status: 'open', affected_service: 'search-service'
      )
    end

    context 'when API credentials are missing' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return(nil)
      end

      it 'returns nil' do
        expect(described_class.create_session(incident: incident)).to be_nil
      end
    end

    context 'when API credentials are set' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return('test-key')
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return('org-123')
      end

      it 'creates a session and returns session info' do
        stub_request(:post, %r{api\.devin\.ai/v3/organizations/org-123/sessions})
          .to_return(status: 200, body: { session_id: 'sess-abc', url: 'https://devin.ai/sessions/abc' }.to_json)

        result = described_class.create_session(incident: incident)
        expect(result[:session_id]).to eq('sess-abc')
        expect(result[:url]).to eq('https://devin.ai/sessions/abc')
      end

      it 'returns nil on API error' do
        stub_request(:post, %r{api\.devin\.ai/v3/organizations/org-123/sessions})
          .to_return(status: 500, body: 'Internal Server Error')

        result = described_class.create_session(incident: incident)
        expect(result).to be_nil
      end
    end
  end

  describe '.get_session' do
    context 'when credentials are missing' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return(nil)
      end

      it 'returns nil' do
        expect(described_class.get_session(session_id: 'sess-1')).to be_nil
      end
    end

    context 'when credentials are set' do
      before do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('DEVIN_API_KEY', nil).and_return('test-key')
        allow(ENV).to receive(:fetch).with('DEVIN_ORG_ID', nil).and_return('org-123')
      end

      it 'returns session status' do
        stub_request(:get, %r{api\.devin\.ai/v3/organizations/org-123/sessions/sess-1})
          .to_return(status: 200, body: { status: 'running', url: 'https://devin.ai/sessions/1' }.to_json)

        result = described_class.get_session(session_id: 'sess-1')
        expect(result[:status]).to eq('running')
      end
    end
  end
end
