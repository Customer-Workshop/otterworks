require 'rails_helper'

RSpec.describe Incident do
  describe 'validations' do
    it { is_expected.to validate_presence_of(:title) }
    it { is_expected.to validate_length_of(:title).is_at_most(255) }
    it { is_expected.to validate_presence_of(:description) }
    it { is_expected.to validate_presence_of(:severity) }
    it { is_expected.to validate_inclusion_of(:severity).in_array(described_class::SEVERITIES) }
    it { is_expected.to validate_presence_of(:status) }
    it { is_expected.to validate_inclusion_of(:status).in_array(described_class::STATUSES) }
  end

  describe 'scopes' do
    let!(:open_incident) do
      Incident.create!(title: 'Open', description: 'desc', severity: 'high', status: 'open')
    end
    let!(:resolved_incident) do
      Incident.create!(title: 'Resolved', description: 'desc', severity: 'low', status: 'resolved')
    end

    describe '.active' do
      it 'returns open and investigating incidents' do
        expect(described_class.active).to include(open_incident)
        expect(described_class.active).not_to include(resolved_incident)
      end
    end

    describe '.by_status' do
      it 'filters by status' do
        expect(described_class.by_status('open')).to include(open_incident)
        expect(described_class.by_status('open')).not_to include(resolved_incident)
      end
    end

    describe '.by_severity' do
      it 'filters by severity' do
        expect(described_class.by_severity('high')).to include(open_incident)
        expect(described_class.by_severity('high')).not_to include(resolved_incident)
      end
    end
  end

  describe '#investigate!' do
    let(:incident) { Incident.create!(title: 'Test', description: 'desc', severity: 'high', status: 'open') }

    it 'changes status to investigating' do
      incident.investigate!
      expect(incident.reload.status).to eq('investigating')
    end
  end

  describe '#resolve!' do
    let(:incident) { Incident.create!(title: 'Test', description: 'desc', severity: 'high', status: 'investigating') }

    it 'changes status to resolved and sets resolved_at' do
      incident.resolve!
      expect(incident.reload.status).to eq('resolved')
      expect(incident.resolved_at).to be_present
    end
  end

  describe '#close!' do
    let(:incident) { Incident.create!(title: 'Test', description: 'desc', severity: 'high', status: 'resolved') }

    it 'changes status to closed' do
      incident.close!
      expect(incident.reload.status).to eq('closed')
    end
  end

  describe '#active?' do
    it 'returns true for open incidents' do
      incident = Incident.new(status: 'open')
      expect(incident.active?).to be true
    end

    it 'returns false for resolved incidents' do
      incident = Incident.new(status: 'resolved')
      expect(incident.active?).to be false
    end
  end

  describe '#has_devin_session?' do
    it 'returns true when devin_session_id is set' do
      incident = Incident.new(devin_session_id: 'sess-123')
      expect(incident.has_devin_session?).to be true
    end

    it 'returns false when devin_session_id is nil' do
      incident = Incident.new(devin_session_id: nil)
      expect(incident.has_devin_session?).to be false
    end
  end
end
