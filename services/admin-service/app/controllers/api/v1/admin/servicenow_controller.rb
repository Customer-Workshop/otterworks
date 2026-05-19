module Api
  module V1
    module Admin
      # Receives inbound webhook payloads from ServiceNow Business Rules.
      # Creates an OtterWorks Incident and auto-triggers a Devin session
      # for AI-driven bug remediation.
      #
      # ServiceNow POST body shape (set up via Outbound REST Message):
      #   {
      #     "source": "servicenow",
      #     "incident": {
      #       "sys_id":            "abc123...",
      #       "number":            "INC0010042",
      #       "short_description": "File upload returns 500",
      #       "description":       "Users report...",
      #       "priority":          "1",
      #       "category":          "Software",
      #       "subcategory":       "Operating System",
      #       "assignment_group":  "Platform Engineering",
      #       "assigned_to":       "Jane Doe",
      #       "caller_id":         "John Smith",
      #       "cmdb_ci":           "file-service",
      #       "state":             "1",
      #       "sys_created_on":    "2026-05-18 22:00:00"
      #     }
      #   }
      class ServicenowController < ApplicationController
        before_action :verify_servicenow_secret

        PRIORITY_MAP = {
          '1' => 'critical',
          '2' => 'high',
          '3' => 'medium',
          '4' => 'low',
          '5' => 'low'
        }.freeze

        SERVICE_ALIAS_MAP = {
          'file-service'         => 'file-service',
          'document-service'     => 'document-service',
          'auth-service'         => 'auth-service',
          'collab-service'       => 'collab-service',
          'api-gateway'          => 'api-gateway',
          'notification-service' => 'notification-service',
          'search-service'       => 'search-service',
          'analytics-service'    => 'analytics-service',
          'admin-service'        => 'admin-service',
          'audit-service'        => 'audit-service',
          'report-service'       => 'report-service'
        }.freeze

        # POST /api/v1/admin/servicenow/ingest
        def ingest
          snow = params[:incident]
          unless snow.is_a?(ActionController::Parameters) || snow.is_a?(Hash)
            return render json: { error: 'Missing incident object' }, status: :bad_request
          end

          sys_id = snow[:sys_id].to_s
          number = snow[:number].to_s

          if sys_id.blank?
            return render json: { error: 'Missing sys_id' }, status: :bad_request
          end

          existing = Incident.find_by(servicenow_sys_id: sys_id)
          if existing
            return render json: {
              skipped: true,
              incident_id: existing.id,
              reason: 'duplicate',
              message: "Incident already exists for ServiceNow #{number}"
            }, status: :ok
          end

          affected_service = resolve_service(snow[:cmdb_ci].to_s, snow[:category].to_s, snow[:short_description].to_s)
          severity = PRIORITY_MAP.fetch(snow[:priority].to_s, 'medium')
          auto_investigate = AdminSettingsService.auto_investigate_enabled?

          incident = Incident.create!(
            title: snow[:short_description].to_s.presence || "ServiceNow #{number}",
            description: build_description(snow),
            severity: severity,
            status: auto_investigate ? 'investigating' : 'open',
            affected_service: affected_service,
            reporter_id: nil,
            source: 'servicenow',
            servicenow_sys_id: sys_id,
            servicenow_number: number,
            servicenow_instance_url: snow[:instance_url].to_s.presence
          )

          session_result = nil
          if auto_investigate
            session_result = DevinSessionService.create_session(incident: incident)
          else
            Rails.logger.info("Auto-investigate disabled — skipping Devin session for ServiceNow incident #{number}")
          end

          if session_result
            incident.update!(
              devin_session_id: session_result[:session_id],
              devin_session_url: session_result[:url],
              devin_session_status: 'running'
            )

            ServicenowCallbackService.post_work_note(
              incident: incident,
              message: "Devin AI remediation session started.\nSession: #{session_result[:url]}"
            )
          end

          AuditLogger.log(
            action: 'incident.created_from_servicenow',
            resource_type: 'Incident',
            resource_id: incident.id,
            request: request,
            changes_made: {
              servicenow_number: number,
              servicenow_sys_id: sys_id,
              devin_session_created: session_result.present?
            }
          )

          Rails.logger.info(
            "Incident #{incident.id} created from ServiceNow #{number}, devin=#{session_result.present?}"
          )

          render json: {
            incident_id: incident.id,
            servicenow_number: number,
            devin_session: session_result.present?,
            devin_session_url: session_result&.dig(:url)
          }, status: :created
        end

        # POST /api/v1/admin/servicenow/resolve
        def resolve
          sys_id = params[:sys_id].to_s
          if sys_id.blank?
            return render json: { error: 'Missing sys_id' }, status: :bad_request
          end

          incident = Incident.find_by(servicenow_sys_id: sys_id)
          unless incident
            return render json: { error: 'Incident not found' }, status: :not_found
          end

          pr_url = params[:pr_url].to_s.presence
          summary = params[:summary].to_s.presence || 'Resolved via Devin AI automated remediation'

          incident.resolve!
          incident.update!(devin_session_status: 'completed')

          ServicenowCallbackService.resolve_incident(
            incident: incident,
            pr_url: pr_url,
            summary: summary
          )

          render json: { incident_id: incident.id, status: 'resolved' }
        end

        private

        def resolve_service(cmdb_ci, category, short_description)
          normalized = cmdb_ci.to_s.downcase.strip
          return SERVICE_ALIAS_MAP[normalized] if SERVICE_ALIAS_MAP.key?(normalized)

          combined = "#{category} #{short_description}".downcase
          SERVICE_ALIAS_MAP.each_key do |svc|
            return svc if combined.include?(svc.gsub('-', ' ')) || combined.include?(svc)
          end

          nil
        end

        def build_description(snow)
          parts = []
          parts << snow[:description].to_s if snow[:description].to_s.present?
          parts << "**ServiceNow Ticket**: #{snow[:number]}"
          parts << "**Priority**: #{snow[:priority]}"
          parts << "**Category**: #{snow[:category]}" if snow[:category].to_s.present?
          parts << "**Subcategory**: #{snow[:subcategory]}" if snow[:subcategory].to_s.present?
          parts << "**Assignment Group**: #{snow[:assignment_group]}" if snow[:assignment_group].to_s.present?
          parts << "**Assigned To**: #{snow[:assigned_to]}" if snow[:assigned_to].to_s.present?
          parts << "**Caller**: #{snow[:caller_id]}" if snow[:caller_id].to_s.present?
          parts << "**CI**: #{snow[:cmdb_ci]}" if snow[:cmdb_ci].to_s.present?
          parts << "**Source**: ServiceNow Business Rule (auto-generated incident)"
          parts.join("\n\n")
        end

        def verify_servicenow_secret
          expected = ENV.fetch('SERVICENOW_WEBHOOK_SECRET', nil)
          return if expected.nil?

          provided = request.headers['X-ServiceNow-Secret'].presence ||
                     request.headers['Authorization'].to_s.delete_prefix('Bearer ').presence
          return if provided == expected

          render json: { error: 'Unauthorized' }, status: :unauthorized
        end
      end
    end
  end
end
