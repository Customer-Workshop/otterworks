module Api
  module V1
    module Admin
      # Receives Grafana Unified Alerting webhook payloads and converts them
      # into Incident records with an auto-triggered Devin session.
      #
      # Grafana POST body shape:
      #   {
      #     "receiver": "otterworks-webhook",
      #     "status": "firing" | "resolved",
      #     "alerts": [
      #       {
      #         "status": "firing" | "resolved",
      #         "labels": { "alertname": "...", "severity": "...", "affected_service": "..." },
      #         "annotations": { "summary": "...", "description": "..." },
      #         "startsAt": "2024-01-01T00:00:00Z"
      #       }
      #     ]
      #   }
      class AlertsController < ApplicationController
        before_action :verify_alert_secret

        SEVERITY_MAP = {
          'critical' => 'critical',
          'high'     => 'high',
          'warning'  => 'medium',
          'info'     => 'low',
        }.freeze

        MAX_ALERTS_PER_REQUEST = 50
        MAX_TITLE_LENGTH       = 255
        MAX_TEXT_LENGTH        = 2_000
        MAX_LABEL_LENGTH       = 100

        # POST /api/v1/admin/alerts/ingest
        def ingest
          alerts = params[:alerts]
          unless alerts.is_a?(Array)
            return render json: { error: 'Missing alerts array' }, status: :bad_request
          end
          if alerts.size > MAX_ALERTS_PER_REQUEST
            return render json: { error: "Too many alerts (max #{MAX_ALERTS_PER_REQUEST})" }, status: :unprocessable_entity
          end

          processed = alerts.map { |alert| process_alert(alert) }.compact

          render json: { received: alerts.size, processed: processed.size, incidents: processed }
        end

        private

        def process_alert(alert)
          return nil unless hash_like?(alert)

          status           = alert[:status].to_s
          labels           = hash_like?(alert[:labels]) ? alert[:labels] : {}
          annotations      = hash_like?(alert[:annotations]) ? alert[:annotations] : {}
          alert_name       = sanitize_text(labels[:alertname], MAX_LABEL_LENGTH)
          affected_service = sanitize_text(labels[:affected_service], MAX_LABEL_LENGTH).presence ||
                             sanitize_text(labels[:service], MAX_LABEL_LENGTH).presence
          severity         = SEVERITY_MAP.fetch(labels[:severity].to_s, 'medium')
          summary          = sanitize_text(annotations[:summary], MAX_TITLE_LENGTH)
          description      = sanitize_text(annotations[:description], MAX_TEXT_LENGTH).presence || summary

          if status == 'resolved'
            resolve_incident(affected_service, alert_name)
            return nil
          end

          return nil unless status == 'firing'
          return nil if affected_service.blank?

          # Deduplicate: skip if an active incident for this service already exists
          existing = Incident.where(affected_service: affected_service)
                             .where(status: %w[open investigating])
                             .first
          if existing
            Rails.logger.info("Alert #{alert_name} skipped — incident #{existing.id} already open for #{affected_service}")
            return { skipped: true, incident_id: existing.id, reason: 'duplicate' }
          end

          auto_investigate = AdminSettingsService.auto_investigate_enabled?

          incident = Incident.create!(
            title:            summary.presence || "#{alert_name}: #{affected_service} alert firing",
            description:      build_description(alert_name, description, labels, annotations),
            severity:         severity,
            status:           auto_investigate ? 'investigating' : 'open',
            affected_service: affected_service,
            reporter_id:      nil, # system-generated
          )

          session_result = nil
          if auto_investigate
            session_result = DevinSessionService.create_session(incident: incident)
          else
            Rails.logger.info("Auto-investigate disabled — skipping Devin session for incident #{incident.id}")
          end

          if session_result
            incident.update!(
              devin_session_id:     session_result[:session_id],
              devin_session_url:    session_result[:url],
              devin_session_status: 'running',
            )
          end

          Rails.logger.info("Incident #{incident.id} created from alert #{alert_name}, devin=#{session_result.present?}")

          { incident_id: incident.id, alert: alert_name, devin_session: session_result.present? }
        rescue ActiveRecord::RecordInvalid => e
          Rails.logger.error("Failed to create incident from alert #{alert_name}: #{e.message}")
          nil
        end

        def resolve_incident(affected_service, alert_name)
          return if affected_service.blank?

          incident = Incident.where(affected_service: affected_service)
                             .where(status: %w[open investigating])
                             .first
          return unless incident

          incident.resolve!
          Rails.logger.info("Incident #{incident.id} auto-resolved by Grafana alert #{alert_name}")
        rescue Incident::InvalidTransitionError => e
          Rails.logger.warn("Could not auto-resolve incident #{incident.id} for alert #{alert_name}: #{e.message}")
        end

        def build_description(alert_name, base_description, labels, annotations)
          parts = [base_description]
          parts << "**Alert**: #{alert_name}" if alert_name.present?
          runbook = sanitize_text(annotations[:runbook_url], MAX_TEXT_LENGTH)
          parts << "**Runbook**: #{runbook}" if runbook.present?
          parts << "**Source**: Grafana Unified Alerting (auto-generated incident)"
          parts.join("\n\n")
        end

        def hash_like?(value)
          value.is_a?(Hash) || value.is_a?(ActionController::Parameters)
        end

        # Collapses control characters/newlines to single spaces and bounds
        # length so alert text can't inject structure into incident records
        # or the Devin session prompt built from them.
        def sanitize_text(value, max_length)
          value.to_s.gsub(/[[:cntrl:]]+/, ' ').squish.truncate(max_length, omission: '')
        end

        def verify_alert_secret
          expected = ENV.fetch('ALERT_WEBHOOK_SECRET', nil).to_s
          if expected.empty?
            Rails.logger.error('ALERT_WEBHOOK_SECRET is not configured — rejecting alert webhook')
            return render json: { error: 'Alert webhook not configured' }, status: :service_unavailable
          end

          # Accept either X-Alert-Secret header or Authorization: Bearer <secret>
          # (Grafana webhook contact points send the token as a Bearer header)
          provided = request.headers['X-Alert-Secret'].presence ||
                     request.headers['Authorization'].to_s.delete_prefix('Bearer ').presence
          return if ActiveSupport::SecurityUtils.secure_compare(provided.to_s, expected)

          render json: { error: 'Unauthorized' }, status: :unauthorized
        end
      end
    end
  end
end
