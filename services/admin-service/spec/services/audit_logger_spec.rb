require 'rails_helper'

RSpec.describe AuditLogger do
  describe '.log' do
    let(:user_id) { SecureRandom.uuid }
    let(:user_email) { 'admin@otterworks.com' }
    let(:mock_request) do
      instance_double(ActionDispatch::Request,
                      env: { 'jwt.user_id' => user_id, 'jwt.user_email' => user_email },
                      remote_ip: '127.0.0.1',
                      user_agent: 'RSpec Test Agent')
    end

    it 'creates an AuditLog record with correct attributes' do
      expect {
        described_class.log(
          action: 'user.updated',
          resource_type: 'AdminUser',
          resource_id: SecureRandom.uuid,
          request: mock_request,
          changes_made: { role: 'admin' }
        )
      }.to change(AuditLog, :count).by(1)

      log = AuditLog.last
      expect(log.action).to eq('user.updated')
      expect(log.resource_type).to eq('AdminUser')
      expect(log.ip_address).to eq('127.0.0.1')
      expect(log.user_agent).to eq('RSpec Test Agent')
    end

    it 'extracts actor_id from request env' do
      described_class.log(
        action: 'user.created',
        resource_type: 'AdminUser',
        request: mock_request
      )
      expect(AuditLog.last.actor_id).to eq(user_id)
    end

    it 'extracts actor_email from request env' do
      described_class.log(
        action: 'user.created',
        resource_type: 'AdminUser',
        request: mock_request
      )
      expect(AuditLog.last.actor_email).to eq(user_email)
    end

    it 'does not raise on error (rescues and logs)' do
      allow(AuditLog).to receive(:record!).and_raise(StandardError.new('DB error'))
      expect(Rails.logger).to receive(:error).with(/Failed to record audit log/)

      expect {
        described_class.log(
          action: 'user.created',
          resource_type: 'AdminUser',
          request: mock_request
        )
      }.not_to raise_error
    end

    it 'works with nil request' do
      expect {
        described_class.log(
          action: 'user.created',
          resource_type: 'AdminUser',
          request: nil,
          actor_id: user_id,
          actor_email: user_email
        )
      }.to change(AuditLog, :count).by(1)

      log = AuditLog.last
      expect(log.actor_id).to eq(user_id)
      expect(log.ip_address).to be_nil
    end
  end
end
