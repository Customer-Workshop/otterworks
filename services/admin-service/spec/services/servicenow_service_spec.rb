require 'rails_helper'

RSpec.describe ServicenowService do
  let(:instance_url) { 'https://dev12345.service-now.com' }
  let(:sys_id) { 'abc123def456' }

  before do
    allow(ENV).to receive(:fetch).and_call_original
    allow(ENV).to receive(:fetch).with('SNOW_INSTANCE_URL').and_return(instance_url)
    allow(ENV).to receive(:fetch).with('SNOW_API_USER').and_return('snow_user')
    allow(ENV).to receive(:fetch).with('SNOW_API_PASSWORD').and_return('snow_pass')
  end

  describe '.update_work_notes' do
    it 'sends correct PATCH payload' do
      stub = stub_request(:patch, "#{instance_url}/api/now/table/incident/#{sys_id}")
             .with(
               body: { work_notes: 'Test note' }.to_json,
               headers: { 'Content-Type' => 'application/json', 'Accept' => 'application/json' }
             )
             .to_return(status: 200, body: { result: {} }.to_json, headers: { 'Content-Type' => 'application/json' })

      described_class.update_work_notes(sys_id: sys_id, notes: 'Test note')
      expect(stub).to have_been_requested
    end

    it 'handles auth failure gracefully' do
      stub_request(:patch, "#{instance_url}/api/now/table/incident/#{sys_id}")
        .to_return(status: 401, body: 'Unauthorized')

      result = described_class.update_work_notes(sys_id: sys_id, notes: 'Test')
      expect(result).to be_nil
    end

    it 'handles network errors gracefully' do
      stub_request(:patch, "#{instance_url}/api/now/table/incident/#{sys_id}")
        .to_raise(Errno::ECONNREFUSED)

      result = described_class.update_work_notes(sys_id: sys_id, notes: 'Test')
      expect(result).to be_nil
    end
  end

  describe '.update_state' do
    it 'sends correct PATCH payload with state field' do
      stub = stub_request(:patch, "#{instance_url}/api/now/table/incident/#{sys_id}")
             .with(
               body: { state: '6', work_notes: 'Resolved' }.to_json
             )
             .to_return(status: 200, body: { result: {} }.to_json, headers: { 'Content-Type' => 'application/json' })

      described_class.update_state(sys_id: sys_id, state: '6', work_notes: 'Resolved')
      expect(stub).to have_been_requested
    end

    it 'omits work_notes when nil' do
      stub = stub_request(:patch, "#{instance_url}/api/now/table/incident/#{sys_id}")
             .with(body: { state: '2' }.to_json)
             .to_return(status: 200, body: { result: {} }.to_json, headers: { 'Content-Type' => 'application/json' })

      described_class.update_state(sys_id: sys_id, state: '2')
      expect(stub).to have_been_requested
    end
  end

  describe '.get_incident' do
    it 'returns parsed incident data' do
      incident_data = { 'number' => 'INC001', 'state' => '1' }
      stub_request(:get, "#{instance_url}/api/now/table/incident/#{sys_id}")
        .to_return(status: 200, body: { result: incident_data }.to_json, headers: { 'Content-Type' => 'application/json' })

      result = described_class.get_incident(sys_id: sys_id)
      expect(result).to eq(incident_data)
    end

    it 'handles auth failure gracefully' do
      stub_request(:get, "#{instance_url}/api/now/table/incident/#{sys_id}")
        .to_return(status: 401, body: 'Unauthorized')

      result = described_class.get_incident(sys_id: sys_id)
      expect(result).to be_nil
    end

    it 'handles network errors gracefully' do
      stub_request(:get, "#{instance_url}/api/now/table/incident/#{sys_id}")
        .to_raise(Errno::ECONNREFUSED)

      result = described_class.get_incident(sys_id: sys_id)
      expect(result).to be_nil
    end
  end
end
