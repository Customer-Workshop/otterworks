require 'rails_helper'

RSpec.describe MetricsAggregator do
  before do
    create_list(:admin_user, 3)
    create(:admin_user, :suspended)
  end

  describe '.summary' do
    it 'returns a hash with required keys' do
      result = described_class.summary
      expect(result).to have_key(:timestamp)
      expect(result).to have_key(:users)
      expect(result).to have_key(:storage)
      expect(result).to have_key(:features)
      expect(result).to have_key(:announcements)
      expect(result).to have_key(:audit)
    end
  end

  describe '.user_metrics' do
    it 'counts total users' do
      result = described_class.user_metrics
      expect(result[:total]).to eq(AdminUser.count)
    end

    it 'counts active users' do
      result = described_class.user_metrics
      expect(result[:active]).to eq(AdminUser.active.count)
    end

    it 'counts suspended users' do
      result = described_class.user_metrics
      expect(result[:suspended]).to eq(AdminUser.suspended.count)
    end

    it 'groups users by role' do
      result = described_class.user_metrics
      expect(result[:by_role]).to be_a(Hash)
    end
  end

  describe '.storage_metrics' do
    it 'returns storage summary' do
      result = described_class.storage_metrics
      expect(result).to have_key(:total_allocated_bytes)
      expect(result).to have_key(:total_used_bytes)
      expect(result).to have_key(:average_usage_percent)
      expect(result).to have_key(:users_over_quota)
    end
  end

  describe '.feature_metrics' do
    before { create(:feature_flag) }

    it 'returns feature flag counts' do
      result = described_class.feature_metrics
      expect(result[:total]).to be >= 1
      expect(result).to have_key(:enabled)
      expect(result).to have_key(:disabled)
    end
  end

  describe '.announcement_metrics' do
    it 'returns announcement counts' do
      result = described_class.announcement_metrics
      expect(result).to have_key(:total)
      expect(result).to have_key(:active)
      expect(result).to have_key(:by_severity)
    end
  end

  describe '.audit_metrics' do
    it 'returns audit event counts' do
      result = described_class.audit_metrics
      expect(result).to have_key(:total_events)
      expect(result).to have_key(:events_today)
      expect(result).to have_key(:events_this_week)
    end
  end
end
