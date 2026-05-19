require 'rails_helper'

RSpec.describe AuditLogger do
  describe '.log' do
    let(:user) { create(:admin_user) }

    it 'creates an audit log entry' do
      expect {
        described_class.log(
          action: 'user_updated',
          resource_type: 'AdminUser',
          resource_id: user.id,
          actor_id: 'admin-1',
          actor_email: 'admin@test.com'
        )
      }.to change(AuditLog, :count).by(1)
    end

    it 'extracts actor from request env' do
      user_uuid = SecureRandom.uuid
      request = double('request',
        env: { 'jwt.user_id' => user_uuid, 'jwt.user_email' => 'jwt@test.com' },
        remote_ip: '127.0.0.1',
        user_agent: 'test-agent'
      )

      described_class.log(
        action: 'config_updated',
        resource_type: 'SystemConfig',
        request: request
      )

      log = AuditLog.last
      expect(log.actor_id).to eq(user_uuid)
      expect(log.actor_email).to eq('jwt@test.com')
    end

    it 'does not raise on failure' do
      allow(AuditLog).to receive(:record!).and_raise(StandardError, 'DB error')
      expect {
        described_class.log(action: 'test', resource_type: 'Test')
      }.not_to raise_error
    end
  end
end
