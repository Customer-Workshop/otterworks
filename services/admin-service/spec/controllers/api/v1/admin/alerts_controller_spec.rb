require 'rails_helper'

RSpec.describe Api::V1::Admin::AlertsController do
  before do
    allow(DevinSessionService).to receive(:create_session).and_return({ session_id: 'test-123', url: 'https://example.com' })
    allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(true)
  end

  def valid_firing_payload(overrides = {})
    {
      alerts: [
        {
          status: 'firing',
          labels: {
            alertname: 'HighErrorRate',
            severity: 'critical',
            affected_service: 'file-service'
          },
          annotations: {
            summary: 'Error rate above threshold',
            description: 'File service error rate is above 5%'
          }
        }.deep_merge(overrides)
      ]
    }
  end

  describe 'POST #ingest' do
    context 'authentication' do
      it 'returns 401 when secret is configured but not provided' do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('ALERT_WEBHOOK_SECRET', nil).and_return('my-secret')

        post :ingest, params: valid_firing_payload
        expect(response).to have_http_status(:unauthorized)
      end

      it 'allows requests when secret is not configured' do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('ALERT_WEBHOOK_SECRET', nil).and_return(nil)

        post :ingest, params: valid_firing_payload
        expect(response).to have_http_status(:ok)
      end

      it 'allows requests when correct secret is provided via header' do
        allow(ENV).to receive(:fetch).and_call_original
        allow(ENV).to receive(:fetch).with('ALERT_WEBHOOK_SECRET', nil).and_return('my-secret')

        request.headers['X-Alert-Secret'] = 'my-secret'
        post :ingest, params: valid_firing_payload
        expect(response).to have_http_status(:ok)
      end
    end

    context 'missing alerts array' do
      it 'returns 400 when alerts param is missing' do
        post :ingest, params: { receiver: 'test' }
        expect(response).to have_http_status(:bad_request)
        body = JSON.parse(response.body)
        expect(body['error']).to eq('Missing alerts array')
      end
    end

    context 'firing alert creates incident' do
      it 'creates an Incident record' do
        expect {
          post :ingest, params: valid_firing_payload
        }.to change(Incident, :count).by(1)

        expect(response).to have_http_status(:ok)
        body = JSON.parse(response.body)
        expect(body['processed']).to eq(1)

        incident = Incident.last
        expect(incident.title).to eq('Error rate above threshold')
        expect(incident.affected_service).to eq('file-service')
        expect(incident.severity).to eq('critical')
        expect(incident.status).to eq('investigating')
      end
    end

    context 'deduplication' do
      it 'skips second alert when active incident exists for same service' do
        create(:incident, affected_service: 'file-service', status: 'open')

        expect {
          post :ingest, params: valid_firing_payload
        }.not_to change(Incident, :count)

        body = JSON.parse(response.body)
        expect(body['incidents'].first['skipped']).to be true
        expect(body['incidents'].first['reason']).to eq('duplicate')
      end
    end

    context 'resolved alert' do
      it 'closes matching open incident' do
        incident = create(:incident, affected_service: 'file-service', status: 'open')

        post :ingest, params: {
          alerts: [
            {
              status: 'resolved',
              labels: { alertname: 'HighErrorRate', affected_service: 'file-service' },
              annotations: { summary: 'Resolved' }
            }
          ]
        }

        expect(response).to have_http_status(:ok)
        expect(incident.reload.status).to eq('resolved')
      end
    end

    context 'severity mapping' do
      {
        'critical' => 'critical',
        'high'     => 'high',
        'warning'  => 'medium',
        'info'     => 'low'
      }.each do |grafana_severity, expected_severity|
        it "maps Grafana severity '#{grafana_severity}' to '#{expected_severity}'" do
          post :ingest, params: valid_firing_payload(labels: { severity: grafana_severity })

          incident = Incident.last
          expect(incident.severity).to eq(expected_severity)
        end
      end
    end

    context 'auto-investigate disabled' do
      before do
        allow(AdminSettingsService).to receive(:auto_investigate_enabled?).and_return(false)
      end

      it 'sets incident status to open instead of investigating' do
        post :ingest, params: valid_firing_payload
        incident = Incident.last
        expect(incident.status).to eq('open')
      end

      it 'does not create a Devin session' do
        post :ingest, params: valid_firing_payload
        expect(DevinSessionService).not_to have_received(:create_session)
      end
    end

    context 'missing affected_service' do
      it 'skips the alert' do
        payload = {
          alerts: [
            {
              status: 'firing',
              labels: { alertname: 'SomeAlert', severity: 'warning' },
              annotations: { summary: 'No service' }
            }
          ]
        }

        expect {
          post :ingest, params: payload
        }.not_to change(Incident, :count)

        body = JSON.parse(response.body)
        expect(body['processed']).to eq(0)
      end
    end
  end
end
