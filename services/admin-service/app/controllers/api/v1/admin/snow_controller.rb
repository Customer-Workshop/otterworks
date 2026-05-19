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
          snow     = incident_params
          number   = snow[:number].to_s.presence
          sys_id   = snow[:sys_id].to_s.presence
          description = snow[:description].to_s.presence || snow[:short_description].to_s.presence

          unless number && sys_id && description
            return render json: { error: 'Missing required fields (number, sys_id, description)' },
                          status: :bad_request
          end

          # Deduplicate by snow_ticket_number
          existing = Incident.find_by(snow_ticket_number: number)
          if existing
            return render json: { status: 'duplicate', incident_id: existing.id }
          end

          short_desc       = snow[:short_description].to_s.presence
          priority         = snow[:priority].to_s
          affected_service = snow[:affected_service].to_s.presence
          caller_id        = snow[:caller_id].to_s.presence
          instance_url     = snow[:instance_url].to_s.presence
          severity         = PRIORITY_MAP.fetch(priority, 'medium')

          auto_investigate = AdminSettingsService.auto_investigate_enabled?

          incident = Incident.create!(
            title:               short_desc || "SNOW #{number}",
            description:         build_description(number, description, affected_service, caller_id),
            severity:            severity,
            status:              'open',
            affected_service:    normalize_service(affected_service),
            source:              'servicenow',
            snow_ticket_number:  number,
            snow_sys_id:         sys_id,
            snow_instance_url:   instance_url,
            reporter_id:         nil
          )

          session_result = nil
          if auto_investigate
            session_result = DevinSessionService.create_session(incident: incident)
          end

          if session_result
            incident.update!(
              status:               'investigating',
              devin_session_id:     session_result[:session_id],
              devin_session_url:    session_result[:url],
              devin_session_status: 'running'
            )

            ServicenowService.update_work_notes(
              sys_id: sys_id,
              notes:  "Devin AI session launched: #{session_result[:url]}",
              instance_url: instance_url
            )
            ServicenowService.update_state(
              sys_id:     sys_id,
              state:      '2',
              work_notes: 'OtterWorks auto-investigation in progress',
              instance_url: instance_url
            )
          end

          SnowSyncJob.set(wait: 30.seconds).perform_later if incident.active? && session_result

          AuditLogger.log(
            action: 'incident.created_from_snow',
            resource_type: 'Incident',
            resource_id: incident.id,
            request: request,
            changes_made: {
              snow_ticket_number: number,
              snow_sys_id: sys_id,
              devin_session_created: session_result.present?
            }
          )

          Rails.logger.info("SNOW incident #{incident.id} created from ticket #{number}, devin=#{session_result.present?}")

          render json: {
            status:        'created',
            incident_id:   incident.id,
            devin_session: session_result.present? ? { id: session_result[:session_id], url: session_result[:url] } : nil
          }
        rescue ActiveRecord::RecordInvalid => e
          Rails.logger.error("Failed to create incident from SNOW ticket: #{e.message}")
          render json: { error: e.message }, status: :unprocessable_entity
        end

        # POST /api/v1/admin/snow/resolve
        def resolve
          snow   = resolve_params
          number = snow[:number].to_s.presence
          sys_id = snow[:sys_id].to_s.presence
          state  = snow[:state].to_s

          unless number || sys_id
            return render json: { error: 'Missing required field: number or sys_id' }, status: :bad_request
          end

          existing = if number
                       Incident.find_by(snow_ticket_number: number)
                     else
                       Incident.find_by(snow_sys_id: sys_id)
                     end

          if existing&.active?
            existing.resolve!
            Rails.logger.info("Incident #{existing.id} resolved via SNOW state #{state}")

            AuditLogger.log(
              action: 'incident.resolved_from_snow',
              resource_type: 'Incident',
              resource_id: existing.id,
              request: request,
              changes_made: { snow_state: state }
            )
          end

          render json: { status: 'resolved', incident_id: existing&.id }
        end

        private

        def incident_params
          params.require(:incident).permit(
            :number, :sys_id, :description, :short_description,
            :state, :priority, :affected_service, :caller_id, :instance_url
          )
        end

        def resolve_params
          params.require(:incident).permit(:number, :sys_id, :state)
        end

        def verify_snow_secret
          expected = ENV.fetch('SNOW_WEBHOOK_SECRET', nil).to_s
          if expected.blank?
            return render json: { error: 'Webhook secret not configured' }, status: :unauthorized
          end

          provided = request.headers['X-Snow-Secret'].to_s
          unless ActiveSupport::SecurityUtils.secure_compare(expected, provided)
            return render json: { error: 'Unauthorized' }, status: :unauthorized
          end
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
