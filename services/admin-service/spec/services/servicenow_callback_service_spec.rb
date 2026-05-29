require 'rails_helper'

RSpec.describe ServicenowCallbackService do
  let(:incident) do
    create(:incident, :servicenow,
           servicenow_sys_id: 'test-sys-id',
           servicenow_number: 'INC0010001',
           devin_session_url: 'https://app.devin.ai/sessions/abc')
  end

  describe '.post_work_note' do
    context 'when ServiceNow credentials are configured' do
      before do
        ENV['SERVICENOW_INSTANCE_URL'] = 'https://test.service-now.com'
        ENV['SERVICENOW_USERNAME'] = 'admin'
        ENV['SERVICENOW_PASSWORD'] = 'password'
      end

      after do
        ENV.delete('SERVICENOW_INSTANCE_URL')
        ENV.delete('SERVICENOW_USERNAME')
        ENV.delete('SERVICENOW_PASSWORD')
      end

      it 'posts a work note to ServiceNow' do
        stub = stub_request(:patch, "https://test.service-now.com/api/now/table/incident/test-sys-id")
          .with(body: hash_including('work_notes' => 'Test note'))
          .to_return(status: 200, body: '{}')

        described_class.post_work_note(incident: incident, message: 'Test note')

        expect(stub).to have_been_requested
      end

      it 'handles ServiceNow API errors gracefully' do
        stub_request(:patch, "https://test.service-now.com/api/now/table/incident/test-sys-id")
          .to_return(status: 500, body: 'Internal Server Error')

        expect {
          described_class.post_work_note(incident: incident, message: 'Test note')
        }.not_to raise_error
      end
    end

    context 'when ServiceNow credentials are not configured' do
      before do
        ENV.delete('SERVICENOW_INSTANCE_URL')
        ENV.delete('SERVICENOW_USERNAME')
        ENV.delete('SERVICENOW_PASSWORD')
      end

      it 'skips the callback' do
        result = described_class.post_work_note(incident: incident, message: 'Test note')
        expect(result).to be_nil
      end
    end

    context 'when incident has no servicenow_sys_id' do
      let(:manual_incident) { create(:incident) }

      it 'skips the callback' do
        ENV['SERVICENOW_INSTANCE_URL'] = 'https://test.service-now.com'
        ENV['SERVICENOW_USERNAME'] = 'admin'
        ENV['SERVICENOW_PASSWORD'] = 'password'

        result = described_class.post_work_note(incident: manual_incident, message: 'Test note')
        expect(result).to be_nil

        ENV.delete('SERVICENOW_INSTANCE_URL')
        ENV.delete('SERVICENOW_USERNAME')
        ENV.delete('SERVICENOW_PASSWORD')
      end
    end
  end

  describe '.resolve_incident' do
    before do
      ENV['SERVICENOW_INSTANCE_URL'] = 'https://test.service-now.com'
      ENV['SERVICENOW_USERNAME'] = 'admin'
      ENV['SERVICENOW_PASSWORD'] = 'password'
    end

    after do
      ENV.delete('SERVICENOW_INSTANCE_URL')
      ENV.delete('SERVICENOW_USERNAME')
      ENV.delete('SERVICENOW_PASSWORD')
    end

    it 'resolves the ServiceNow incident with work notes' do
      stub = stub_request(:patch, "https://test.service-now.com/api/now/table/incident/test-sys-id")
        .with(body: hash_including(
          'state' => '6',
          'close_code' => 'Solved (Permanently)'
        ))
        .to_return(status: 200, body: '{}')

      described_class.resolve_incident(
        incident: incident,
        pr_url: 'https://github.com/org/repo/pull/1',
        summary: 'Fixed the bug'
      )

      expect(stub).to have_been_requested
    end
  end

  describe '.post_update' do
    before do
      ENV['SERVICENOW_INSTANCE_URL'] = 'https://test.service-now.com'
      ENV['SERVICENOW_USERNAME'] = 'admin'
      ENV['SERVICENOW_PASSWORD'] = 'password'
    end

    after do
      ENV.delete('SERVICENOW_INSTANCE_URL')
      ENV.delete('SERVICENOW_USERNAME')
      ENV.delete('SERVICENOW_PASSWORD')
    end

    it 'posts a status update to ServiceNow' do
      stub = stub_request(:patch, "https://test.service-now.com/api/now/table/incident/test-sys-id")
        .with(body: hash_including('work_notes'))
        .to_return(status: 200, body: '{}')

      described_class.post_update(
        incident: incident,
        status: 'investigating',
        session_url: 'https://app.devin.ai/sessions/abc'
      )

      expect(stub).to have_been_requested
    end
  end

  describe 'connection error handling' do
    before do
      ENV['SERVICENOW_INSTANCE_URL'] = 'https://test.service-now.com'
      ENV['SERVICENOW_USERNAME'] = 'admin'
      ENV['SERVICENOW_PASSWORD'] = 'password'
    end

    after do
      ENV.delete('SERVICENOW_INSTANCE_URL')
      ENV.delete('SERVICENOW_USERNAME')
      ENV.delete('SERVICENOW_PASSWORD')
    end

    it 'handles network errors gracefully' do
      stub_request(:patch, "https://test.service-now.com/api/now/table/incident/test-sys-id")
        .to_raise(Errno::ECONNREFUSED)

      expect {
        described_class.post_work_note(incident: incident, message: 'Test')
      }.not_to raise_error
    end
  end
end
