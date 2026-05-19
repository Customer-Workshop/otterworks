require 'rails_helper'

RSpec.describe AdminSettingsService do
  let(:redis_mock) { instance_double(Redis) }

  before do
    allow(Redis).to receive(:new).and_return(redis_mock)
    allow(redis_mock).to receive(:close)
  end

  describe '.auto_investigate_enabled?' do
    it 'returns true when key is not set (default behavior)' do
      allow(redis_mock).to receive(:get).with(described_class::AUTO_INVESTIGATE_KEY).and_return(nil)
      expect(described_class.auto_investigate_enabled?).to be true
    end

    it 'returns true when key is "true"' do
      allow(redis_mock).to receive(:get).with(described_class::AUTO_INVESTIGATE_KEY).and_return('true')
      expect(described_class.auto_investigate_enabled?).to be true
    end

    it 'returns false when key is "false"' do
      allow(redis_mock).to receive(:get).with(described_class::AUTO_INVESTIGATE_KEY).and_return('false')
      expect(described_class.auto_investigate_enabled?).to be false
    end

    it 'returns true on Redis connection error (fail-open)' do
      allow(redis_mock).to receive(:get).and_raise(Redis::CannotConnectError)
      expect(described_class.auto_investigate_enabled?).to be true
    end
  end

  describe '.set_auto_investigate' do
    it 'writes the setting to Redis' do
      allow(redis_mock).to receive(:set)
      described_class.set_auto_investigate(true)
      expect(redis_mock).to have_received(:set).with(described_class::AUTO_INVESTIGATE_KEY, 'true')
    end

    it 'raises on Redis error' do
      allow(redis_mock).to receive(:set).and_raise(Redis::CannotConnectError)
      expect { described_class.set_auto_investigate(false) }.to raise_error(Redis::CannotConnectError)
    end
  end
end
