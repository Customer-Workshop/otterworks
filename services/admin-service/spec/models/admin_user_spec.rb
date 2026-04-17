require 'rails_helper'

RSpec.describe AdminUser do
  describe 'validations' do
    subject { build(:admin_user) }

    it { is_expected.to validate_presence_of(:email) }
    it { is_expected.to validate_uniqueness_of(:email) }
    it { is_expected.to validate_presence_of(:display_name) }
    it { is_expected.to validate_length_of(:display_name).is_at_most(255) }
    it { is_expected.to validate_presence_of(:role) }
    it { is_expected.to validate_inclusion_of(:role).in_array(described_class::ROLES) }
    it { is_expected.to validate_presence_of(:status) }
    it { is_expected.to validate_inclusion_of(:status).in_array(described_class::STATUSES) }
  end

  describe 'scopes' do
    let!(:active_user) { create(:admin_user, status: 'active') }
    let!(:suspended_user) { create(:admin_user, :suspended) }
    let!(:admin_user) { create(:admin_user, :admin) }

    describe '.active' do
      it 'returns only active users' do
        expect(described_class.active).to include(active_user, admin_user)
        expect(described_class.active).not_to include(suspended_user)
      end
    end

    describe '.suspended' do
      it 'returns only suspended users' do
        expect(described_class.suspended).to include(suspended_user)
        expect(described_class.suspended).not_to include(active_user)
      end
    end

    describe '.by_role' do
      it 'returns users with the given role' do
        expect(described_class.by_role('admin')).to include(admin_user)
        expect(described_class.by_role('admin')).not_to include(active_user)
      end
    end

    describe '.search' do
      it 'searches by email' do
        expect(described_class.search(active_user.email[0..5])).to include(active_user)
      end
    end
  end

  describe '#suspend!' do
    let(:user) { create(:admin_user) }

    it 'suspends the user with a reason' do
      user.suspend!(reason: 'Violation')
      expect(user.status).to eq('suspended')
      expect(user.suspended_at).to be_present
      expect(user.suspended_reason).to eq('Violation')
    end
  end

  describe '#activate!' do
    let(:user) { create(:admin_user, :suspended) }

    it 'reactivates the user' do
      user.activate!
      expect(user.status).to eq('active')
      expect(user.suspended_at).to be_nil
      expect(user.suspended_reason).to be_nil
    end
  end

  describe '#soft_delete!' do
    let(:user) { create(:admin_user) }

    it 'marks user as deleted' do
      user.soft_delete!
      expect(user.status).to eq('deleted')
    end
  end
end
