require 'rails_helper'

RSpec.describe Announcement do
  describe 'validations' do
    it { is_expected.to validate_presence_of(:title) }
    it { is_expected.to validate_length_of(:title).is_at_most(255) }
    it { is_expected.to validate_presence_of(:body) }
    it { is_expected.to validate_presence_of(:severity) }
    it { is_expected.to validate_inclusion_of(:severity).in_array(described_class::SEVERITIES) }
    it { is_expected.to validate_presence_of(:status) }
    it { is_expected.to validate_inclusion_of(:status).in_array(described_class::STATUSES) }

    it 'validates ends_at is after starts_at' do
      announcement = build(:announcement, starts_at: 1.day.from_now, ends_at: 1.day.ago)
      expect(announcement).not_to be_valid
      expect(announcement.errors[:ends_at]).to include('must be after starts_at')
    end
  end

  describe 'scopes' do
    let!(:published) { create(:announcement, :published) }
    let!(:draft) { create(:announcement) }
    let!(:expired) { create(:announcement, :expired) }

    describe '.published' do
      it 'returns only published announcements' do
        expect(described_class.published).to include(published, expired)
        expect(described_class.published).not_to include(draft)
      end
    end

    describe '.active' do
      it 'returns only active published announcements' do
        expect(described_class.active).to include(published)
        expect(described_class.active).not_to include(draft, expired)
      end
    end
  end

  describe '#publish!' do
    let(:announcement) { create(:announcement) }

    it 'publishes the announcement' do
      announcement.publish!
      expect(announcement.status).to eq('published')
    end
  end

  describe '#archive!' do
    let(:announcement) { create(:announcement, :published) }

    it 'archives the announcement' do
      announcement.archive!
      expect(announcement.status).to eq('archived')
    end
  end

  describe '#active?' do
    it 'returns true for active published announcement' do
      announcement = build(:announcement, :published)
      expect(announcement).to be_active
    end

    it 'returns false for draft' do
      announcement = build(:announcement)
      expect(announcement).not_to be_active
    end
  end
end
