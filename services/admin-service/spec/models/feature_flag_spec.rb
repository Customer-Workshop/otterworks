require 'rails_helper'

RSpec.describe FeatureFlag do
  describe 'validations' do
    subject { build(:feature_flag) }

    it { is_expected.to validate_presence_of(:name) }
    it { is_expected.to validate_uniqueness_of(:name) }

    it { is_expected.to validate_numericality_of(:rollout_percentage).only_integer }

    it 'requires snake_case name' do
      flag = build(:feature_flag, name: 'Invalid Name')
      expect(flag).not_to be_valid
      expect(flag.errors[:name]).to include('must be snake_case')
    end
  end

  describe 'scopes' do
    let!(:enabled_flag) { create(:feature_flag, :enabled) }
    let!(:disabled_flag) { create(:feature_flag) }

    describe '.enabled' do
      it 'returns only enabled flags' do
        expect(described_class.enabled).to include(enabled_flag)
        expect(described_class.enabled).not_to include(disabled_flag)
      end
    end

    describe '.disabled' do
      it 'returns only disabled flags' do
        expect(described_class.disabled).to include(disabled_flag)
        expect(described_class.disabled).not_to include(enabled_flag)
      end
    end
  end

  describe '#expired?' do
    it 'returns true when flag has expired' do
      flag = build(:feature_flag, :expired)
      expect(flag).to be_expired
    end

    it 'returns false when flag has not expired' do
      flag = build(:feature_flag, expires_at: 1.day.from_now)
      expect(flag).not_to be_expired
    end

    it 'returns false when no expiry set' do
      flag = build(:feature_flag, expires_at: nil)
      expect(flag).not_to be_expired
    end
  end

  describe '#enabled_for_user?' do
    let(:user_id) { SecureRandom.uuid }

    it 'returns false when disabled' do
      flag = build(:feature_flag, enabled: false)
      expect(flag.enabled_for_user?(user_id)).to be false
    end

    it 'returns true when user is in target_users' do
      flag = build(:feature_flag, :enabled, target_users: [user_id])
      expect(flag.enabled_for_user?(user_id)).to be true
    end

    it 'returns true when rollout is 100%' do
      flag = build(:feature_flag, :enabled, rollout_percentage: 100)
      expect(flag.enabled_for_user?(user_id)).to be true
    end
  end
end
