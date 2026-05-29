require 'rails_helper'

RSpec.describe DevinSessionPollJob, type: :job do
  describe '#perform' do
    context 'with running sessions' do
      let!(:running_incident) do
        create(:incident, :investigating, :with_devin_session,
               devin_session_status: 'running')
      end

      it 'polls the Devin API for session status' do
        allow(DevinSessionService).to receive(:get_session)
          .with(session_id: running_incident.devin_session_id)
          .and_return({ status: 'running', url: running_incident.devin_session_url })

        described_class.perform_now

        expect(DevinSessionService).to have_received(:get_session)
      end

      it 'updates incident when session completes' do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'finished', url: running_incident.devin_session_url })

        described_class.perform_now

        running_incident.reload
        expect(running_incident.devin_session_status).to eq('finished')
        expect(running_incident.status).to eq('resolved')
        expect(running_incident.resolved_at).to be_present
      end

      it 'does not auto-resolve on failed status' do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'failed', url: running_incident.devin_session_url })

        described_class.perform_now

        running_incident.reload
        expect(running_incident.devin_session_status).to eq('failed')
        expect(running_incident.status).to eq('investigating')
      end
    end

    context 'with servicenow-sourced incident' do
      let!(:snow_incident) do
        create(:incident, :servicenow, :investigating, :with_devin_session,
               devin_session_status: 'running')
      end

      it 'triggers ServiceNow callback on completion' do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'finished', url: snow_incident.devin_session_url })
        allow(ServicenowCallbackService).to receive(:resolve_incident)

        described_class.perform_now

        expect(ServicenowCallbackService).to have_received(:resolve_incident)
          .with(hash_including(incident: snow_incident))
      end

      it 'posts failure update to ServiceNow on errored status' do
        allow(DevinSessionService).to receive(:get_session)
          .and_return({ status: 'errored', url: snow_incident.devin_session_url })
        allow(ServicenowCallbackService).to receive(:post_update)

        described_class.perform_now

        expect(ServicenowCallbackService).to have_received(:post_update)
          .with(hash_including(incident: snow_incident))
      end
    end

    context 'with no running sessions' do
      it 'completes without errors' do
        expect { described_class.perform_now }.not_to raise_error
      end
    end

    context 'when API call fails for one incident' do
      let!(:incident1) do
        create(:incident, :investigating, :with_devin_session, devin_session_status: 'running')
      end
      let!(:incident2) do
        create(:incident, :investigating, :with_devin_session, devin_session_status: 'running')
      end

      it 'continues processing other incidents' do
        call_count = 0
        allow(DevinSessionService).to receive(:get_session) do
          call_count += 1
          raise StandardError, 'API timeout' if call_count == 1

          { status: 'finished', url: 'https://app.devin.ai/sessions/x' }
        end

        expect { described_class.perform_now }.not_to raise_error
      end
    end
  end
end
