module Api
  module V1
    module Admin
      class SnowController < ApplicationController
        before_action :verify_snow_secret

        PRIORITY_MAP = {
          '1' => 'critical',
          '2' => 'high',
          '3' => 'medium',
          '4' => 'low',
          '5' => 'low'
        }.freeze

        # POST /api/v1/admin/snow/ingest
        def ingest
          number      = params[:number].to_s.presence
          sys_id      = params[:sys_id].to_s.presence
          state       = params[:state].to_s
          description = params[:description].to_s.presence || params[:short_description].to_s.presence

          unless number && sys_id && description
            return render json: { error: 'Missing required fields (number, sys_id, description)' },
                          status: :bad_request
          end

          # Resolve/close if SNOW ticket is already resolved (6) or closed (7)
          if %w[6 7].include?(state)
            existing = Incident.find_by(snow_ticket_number: number)
            if existing&.active?
              existing.resolve!
              Rails.logger.info("Incident #{existing.id} resolved via SNOW state #{state}")
            end
            return render json: { status: 'resolved', incident_id: existing&.id }
          end

          # Deduplicate by snow_ticket_number
          existing = Incident.find_by(snow_ticket_number: number)
          if existing
            return render json: { status: 'duplicate', incident_id: existing.id }
          end

          short_desc       = params[:short_description].to_s.presence
          priority         = params[:priority].to_s
          affected_service = params[:affected_service].to_s.presence
          caller_id        = params[:caller_id].to_s.presence
          severity         = PRIORITY_MAP.fetch(priority, 'medium')

          auto_investigate = AdminSettingsService.auto_investigate_enabled?

          incident = Incident.create!(
            title:               short_desc || "SNOW #{number}",
            description:         build_description(number, description, affected_service, caller_id),
            severity:            severity,
            status:              auto_investigate ? 'investigating' : 'open',
            affected_service:    normalize_service(affected_service),
            snow_ticket_number:  number,
            snow_sys_id:         sys_id,
            reporter_id:         nil
          )

          session_result = nil
          if auto_investigate
            session_result = DevinSessionService.create_session(incident: incident)
          end

          if session_result
            incident.update!(
              devin_session_id:     session_result[:session_id],
              devin_session_url:    session_result[:url],
              devin_session_status: 'running'
            )

            ServicenowService.update_work_notes(
              sys_id: sys_id,
              notes:  "Devin AI session launched: #{session_result[:url]}"
            )
            ServicenowService.update_state(
              sys_id:     sys_id,
              state:      '2',
              work_notes: 'OtterWorks auto-investigation in progress'
            )
          end

          SnowSyncJob.set(wait: 30.seconds).perform_later if incident.active? && session_result

          Rails.logger.info("SNOW incident #{incident.id} created from ticket #{number}, devin=#{session_result.present?}")

          render json: {
            status:        'created',
            incident_id:   incident.id,
            devin_session: session_result.present? ? { id: session_result[:session_id], url: session_result[:url] } : nil
          }
        rescue ActiveRecord::RecordInvalid => e
          Rails.logger.error("Failed to create incident from SNOW ticket #{number}: #{e.message}")
          render json: { error: e.message }, status: :unprocessable_entity
        end

        private

        def verify_snow_secret
          expected = ENV.fetch('SNOW_WEBHOOK_SECRET', nil)
          return if expected.nil?

          provided = request.headers['X-Snow-Secret'].to_s
          return if ActiveSupport::SecurityUtils.secure_compare(provided, expected)

          render json: { error: 'Unauthorized' }, status: :unauthorized
        end

        def build_description(number, description, affected_service, caller_id)
          parts = [description]
          parts << "**ServiceNow Ticket**: #{number}"
          parts << "**Affected Service**: #{affected_service}" if affected_service.present?
          parts << "**Caller**: #{caller_id}" if caller_id.present?
          parts << '**Source**: ServiceNow webhook (auto-generated incident)'
          parts.join("\n\n")
        end

        def normalize_service(service_name)
          return nil if service_name.blank?

          Incident::AFFECTED_SERVICES.find { |s| s.casecmp?(service_name) }
        end
      end
    end
  end
end
