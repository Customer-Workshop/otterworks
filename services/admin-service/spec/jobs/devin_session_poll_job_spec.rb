require 'rails_helper'

RSpec.describe DevinSessionPollJob, type: :job do
  describe '#perform' do
    it 'completes without errors' do
      expect { described_class.perform_now }.not_to raise_error
    end

    it 'logs a no-op message' do
      expect(Rails.logger).to receive(:info).with(/no-op/)
      described_class.perform_now
    end
  end
end
