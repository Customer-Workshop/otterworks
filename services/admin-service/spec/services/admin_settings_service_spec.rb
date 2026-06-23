require 'rails_helper'

RSpec.describe AdminSettingsService do
  let(:mock_redis) { instance_double(Redis) }

  before do
    allow(Redis).to receive(:new).and_return(mock_redis)
    allow(mock_redis).to receive(:close)
  end

  describe '.auto_investigate_enabled?' do
    it 'returns true by default when key is not in Redis' do
      allow(mock_redis).to receive(:get).with('admin:auto_investigate').and_return(nil)
      expect(described_class.auto_investigate_enabled?).to be true
    end

    it 'returns true when Redis value is "true"' do
      allow(mock_redis).to receive(:get).with('admin:auto_investigate').and_return('true')
      expect(described_class.auto_investigate_enabled?).to be true
    end

    it 'returns false when Redis value is "false"' do
      allow(mock_redis).to receive(:get).with('admin:auto_investigate').and_return('false')
      expect(described_class.auto_investigate_enabled?).to be false
    end

    it 'returns true on Redis connection error (fail-open)' do
      allow(mock_redis).to receive(:get).and_raise(Redis::CannotConnectError)
      expect(described_class.auto_investigate_enabled?).to be true
    end
  end

  describe '.set_auto_investigate' do
    it 'sets value in Redis' do
      allow(mock_redis).to receive(:set)
      described_class.set_auto_investigate(true)
      expect(mock_redis).to have_received(:set).with('admin:auto_investigate', 'true')
    end

    it 'raises on Redis connection error' do
      allow(mock_redis).to receive(:set).and_raise(Redis::CannotConnectError)
      expect { described_class.set_auto_investigate(true) }.to raise_error(Redis::CannotConnectError)
    end
  end
end
