require 'rails_helper'

RSpec.describe MetricsAggregator do
  describe '.summary' do
    it 'returns hash with all expected keys' do
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
    before do
      create(:admin_user, status: 'active')
      create(:admin_user, :suspended)
      create(:admin_user, status: 'active', role: 'admin')
    end

    it 'returns correct counts' do
      result = described_class.user_metrics
      expect(result[:total]).to eq(3)
      expect(result[:active]).to eq(2)
      expect(result[:suspended]).to eq(1)
      expect(result[:by_role]).to be_a(Hash)
      expect(result[:recent_signups]).to eq(3)
    end
  end

  describe '.storage_metrics' do
    before do
      create(:storage_quota, quota_bytes: 10_000, used_bytes: 5_000, tier: 'free')
      create(:storage_quota, :over_quota, tier: 'free')
    end

    it 'returns usage data' do
      result = described_class.storage_metrics
      expect(result[:total_allocated_bytes]).to be > 0
      expect(result[:total_used_bytes]).to be > 0
      expect(result[:average_usage_percent]).to be_a(Numeric)
      expect(result[:users_over_quota]).to eq(1)
      expect(result[:by_tier]).to be_a(Hash)
    end
  end

  describe '.feature_metrics' do
    before do
      create(:feature_flag, :enabled)
      create(:feature_flag)
    end

    it 'returns enabled/disabled counts' do
      result = described_class.feature_metrics
      expect(result[:total]).to eq(2)
      expect(result[:enabled]).to eq(1)
      expect(result[:disabled]).to eq(1)
    end
  end

  describe '.announcement_metrics' do
    before do
      create(:announcement, :published)
      create(:announcement)
    end

    it 'returns active count' do
      result = described_class.announcement_metrics
      expect(result[:total]).to eq(2)
      expect(result[:active]).to eq(1)
      expect(result[:by_severity]).to be_a(Hash)
    end
  end

  describe '.audit_metrics' do
    before do
      create(:audit_log, created_at: Time.current)
      create(:audit_log, created_at: 2.days.ago)
    end

    it 'returns event counts' do
      result = described_class.audit_metrics
      expect(result[:total_events]).to eq(2)
      expect(result[:events_today]).to eq(1)
      expect(result[:events_this_week]).to eq(2)
      expect(result[:top_actions]).to be_a(Hash)
    end
  end

  describe '.calculate_average_usage (via .storage_metrics)' do
    it 'returns 0 when no quotas exist' do
      result = described_class.storage_metrics
      expect(result[:average_usage_percent]).to eq(0)
    end
  end
end
