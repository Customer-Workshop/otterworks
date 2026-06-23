require 'rails_helper'

RSpec.describe Incident do
  describe 'validations' do
    subject { build(:incident) }

    it { is_expected.to validate_presence_of(:title) }
    it { is_expected.to validate_length_of(:title).is_at_most(255) }
    it { is_expected.to validate_presence_of(:description) }
    it { is_expected.to validate_presence_of(:severity) }
    it { is_expected.to validate_inclusion_of(:severity).in_array(Incident::SEVERITIES) }
    it { is_expected.to validate_presence_of(:status) }
    it { is_expected.to validate_inclusion_of(:status).in_array(Incident::STATUSES) }

    it 'allows blank affected_service' do
      incident = build(:incident, affected_service: '')
      expect(incident).to be_valid
    end

    it 'validates affected_service inclusion when present' do
      incident = build(:incident, affected_service: 'nonexistent-service')
      expect(incident).not_to be_valid
      expect(incident.errors[:affected_service]).to be_present
    end
  end

  describe 'scopes' do
    let!(:open_incident) { create(:incident, status: 'open') }
    let!(:investigating_incident) { create(:incident, :investigating) }
    let!(:resolved_incident) { create(:incident, :resolved) }
    let!(:critical_incident) { create(:incident, :critical) }
    let!(:low_incident) { create(:incident, severity: 'low') }

    describe '.by_status' do
      it 'returns incidents with the given status' do
        expect(described_class.by_status('open')).to include(open_incident)
        expect(described_class.by_status('open')).not_to include(investigating_incident)
      end
    end

    describe '.by_severity' do
      it 'returns incidents with the given severity' do
        expect(described_class.by_severity('critical')).to include(critical_incident)
        expect(described_class.by_severity('critical')).not_to include(low_incident)
      end
    end

    describe '.active' do
      it 'returns only open and investigating incidents' do
        expect(described_class.active).to include(open_incident, investigating_incident)
        expect(described_class.active).not_to include(resolved_incident)
      end
    end
  end

  describe 'state transitions' do
    describe '#investigate!' do
      it 'transitions from open to investigating' do
        incident = create(:incident, status: 'open')
        incident.investigate!
        expect(incident.reload.status).to eq('investigating')
      end

      it 'raises error when transitioning from resolved to investigating' do
        incident = create(:incident, :resolved)
        expect { incident.investigate! }.to raise_error(Incident::InvalidTransitionError)
      end
    end

    describe '#resolve!' do
      it 'transitions from investigating to resolved' do
        incident = create(:incident, :investigating)
        incident.resolve!
        expect(incident.reload.status).to eq('resolved')
        expect(incident.resolved_at).to be_present
      end

      it 'transitions from open to resolved' do
        incident = create(:incident, status: 'open')
        incident.resolve!
        expect(incident.reload.status).to eq('resolved')
      end

      it 'raises error when transitioning from closed to resolved' do
        incident = create(:incident, :closed)
        expect { incident.resolve! }.to raise_error(Incident::InvalidTransitionError)
      end
    end

    describe '#close!' do
      it 'transitions from resolved to closed' do
        incident = create(:incident, :resolved)
        incident.close!
        expect(incident.reload.status).to eq('closed')
        expect(incident.closed_at).to be_present
      end

      it 'raises error when transitioning from open to closed' do
        incident = create(:incident, status: 'open')
        expect { incident.close! }.to raise_error(Incident::InvalidTransitionError)
      end
    end

    describe '#can_transition_to?' do
      it 'returns true for valid transitions' do
        incident = build(:incident, status: 'open')
        expect(incident.can_transition_to?('investigating')).to be true
        expect(incident.can_transition_to?('resolved')).to be true
      end

      it 'returns false for invalid transitions' do
        incident = build(:incident, status: 'open')
        expect(incident.can_transition_to?('closed')).to be false
      end

      it 'returns false for all transitions from closed' do
        incident = build(:incident, :closed)
        expect(incident.can_transition_to?('open')).to be false
        expect(incident.can_transition_to?('investigating')).to be false
        expect(incident.can_transition_to?('resolved')).to be false
      end
    end
  end

  describe 'helper methods' do
    describe '#active?' do
      it 'returns true for open incidents' do
        expect(build(:incident, status: 'open')).to be_active
      end

      it 'returns true for investigating incidents' do
        expect(build(:incident, :investigating)).to be_active
      end

      it 'returns false for resolved incidents' do
        expect(build(:incident, :resolved)).not_to be_active
      end

      it 'returns false for closed incidents' do
        expect(build(:incident, :closed)).not_to be_active
      end
    end

    describe '#has_devin_session?' do
      it 'returns true when devin_session_id is present' do
        incident = build(:incident, :with_devin_session)
        expect(incident.has_devin_session?).to be true
      end

      it 'returns false when devin_session_id is nil' do
        incident = build(:incident)
        expect(incident.has_devin_session?).to be false
      end
    end

    describe '#has_active_devin_session?' do
      it 'returns true when session_id is present and status is running' do
        incident = build(:incident, :with_devin_session)
        expect(incident.has_active_devin_session?).to be true
      end

      it 'returns false when session_id is present but status is not running' do
        incident = build(:incident, :with_devin_session, devin_session_status: 'completed')
        expect(incident.has_active_devin_session?).to be false
      end

      it 'returns false when session_id is nil' do
        incident = build(:incident)
        expect(incident.has_active_devin_session?).to be false
      end
    end
  end

  describe 'InvalidTransitionError' do
    it 'is a StandardError' do
      expect(Incident::InvalidTransitionError.superclass).to eq(StandardError)
    end

    it 'includes a descriptive message' do
      incident = create(:incident, :closed)
      expect { incident.resolve! }.to raise_error(
        Incident::InvalidTransitionError,
        "Cannot transition from 'closed' to 'resolved'"
      )
    end
  end
end
