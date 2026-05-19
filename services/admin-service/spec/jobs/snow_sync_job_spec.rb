require 'rails_helper'

RSpec.describe SnowSyncJob do
  before do
    allow(ServicenowService).to receive(:update_work_notes).and_return({})
    allow(ServicenowService).to receive(:update_state).and_return({})
    allow(described_class).to receive_message_chain(:set, :perform_later) # rubocop:disable RSpec/MessageChain
  end

  describe '#perform' do
    context 'when Devin status changes to stopped' do
      let!(:incident) { create(:incident, :snow_linked_active) }

      before do
        allow(DevinSessionService).to receive(:get_session)
          .with(session_id: incident.devin_session_id)
          .and_return({ status: 'stopped', url: incident.devin_session_url })
      end

      it 'updates SNOW ticket state to 6 and resolves incident' do
        described_class.perform_now

        expect(incident.reload.devin_session_status).to eq('stopped')
        expect(incident.reload.status).to eq('resolved')
        expect(ServicenowService).to have_received(:update_state).with(
          sys_id: incident.snow_sys_id,
          state: '6',
          work_notes: 'Devin session completed investigation. Incident auto-resolved by OtterWorks.'
        )
      end
    end

    context 'when Devin status changes to blocked' do
      let!(:incident) { create(:incident, :snow_linked_active) }

      before do
        allow(DevinSessionService).to receive(:get_session)
          .with(session_id: incident.devin_session_id)
          .and_return({ status: 'blocked', url: incident.devin_session_url })
      end

      it 'updates SNOW ticket state to 3' do
        described_class.perform_now

        expect(incident.reload.devin_session_status).to eq('blocked')
        expect(ServicenowService).to have_received(:update_state).with(
          sys_id: incident.snow_sys_id,
          state: '3',
          work_notes: "Devin session blocked \u2014 needs human input. Session: #{incident.devin_session_url}"
        )
      end
    end

    context 'when Devin status changes to failed' do
      let!(:incident) { create(:incident, :snow_linked_active) }

      before do
        allow(DevinSessionService).to receive(:get_session)
          .with(session_id: incident.devin_session_id)
          .and_return({ status: 'failed', url: incident.devin_session_url })
      end

      it 'posts work_note but does not change SNOW state' do
        described_class.perform_now

        expect(incident.reload.devin_session_status).to eq('failed')
        expect(ServicenowService).to have_received(:update_work_notes).with(
          sys_id: incident.snow_sys_id,
          notes: "Devin session failed \u2014 manual investigation required. Session: #{incident.devin_session_url}"
        )
        expect(ServicenowService).not_to have_received(:update_state)
      end
    end

    context 'when active incidents remain' do
      let!(:incident) { create(:incident, :snow_linked_active) }

      before do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'running', url: incident.devin_session_url })
      end

      it 're-enqueues itself' do
        expect(described_class).to receive_message_chain(:set, :perform_later) # rubocop:disable RSpec/MessageChain

        described_class.perform_now
      end
    end

    context 'when no active incidents remain' do
      let!(:incident) { create(:incident, :snow_linked_active) }

      before do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'stopped', url: incident.devin_session_url })
      end

      it 'does not re-enqueue itself' do
        expect(described_class).not_to receive(:set)

        described_class.perform_now
      end
    end

    context 'when there are no snow-linked active incidents' do
      it 'returns without processing' do
        expect(DevinSessionService).not_to receive(:get_session)

        described_class.perform_now
      end
    end

    context 'when Devin status has not changed' do
      let!(:incident) { create(:incident, :snow_linked_active) }

      before do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'running', url: incident.devin_session_url })
      end

      it 'does not update ServiceNow' do
        described_class.perform_now

        expect(ServicenowService).not_to have_received(:update_work_notes)
        expect(ServicenowService).not_to have_received(:update_state)
      end
    end
  end
end
