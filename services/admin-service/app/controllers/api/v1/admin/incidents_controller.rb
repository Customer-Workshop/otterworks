module Api
  module V1
    module Admin
      class IncidentsController < ApplicationController
        before_action :set_incident, only: %i[show trigger_session]

        # GET /api/v1/admin/incidents
        def index
          scope = Incident.all
          scope = scope.by_status(params[:status]) if params[:status].present?
          scope = scope.by_severity(params[:severity]) if params[:severity].present?
          scope = scope.active if params[:active] == 'true'
          scope = scope.order(created_at: :desc)

          result = paginate(scope)

          render json: {
            incidents: ActiveModelSerializers::SerializableResource.new(result[:records]),
            total: result[:total],
            page: result[:page],
            per_page: result[:per_page]
          }
        end

        # GET /api/v1/admin/incidents/:id
        def show
          # Refresh Devin session status if session exists and incident is active
          if @incident.has_devin_session? && @incident.active?
            session_info = DevinSessionService.get_session(session_id: @incident.devin_session_id)
            if session_info
              @incident.update(
                devin_session_status: session_info[:status],
                devin_session_url: session_info[:url] || @incident.devin_session_url
              )
            end
          end

          render json: @incident, serializer: IncidentSerializer
        end

        # POST /api/v1/admin/incidents
        def create
          incident = Incident.new(incident_params)
          incident.reporter_id = current_user_id
          incident.status = 'investigating'

          if incident.save
            # Trigger Devin session
            session_result = DevinSessionService.create_session(incident: incident)

            if session_result
              incident.update(
                devin_session_id: session_result[:session_id],
                devin_session_url: session_result[:url],
                devin_session_status: 'running'
              )
            end

            AuditLogger.log(
              action: 'incident.created',
              resource_type: 'Incident',
              resource_id: incident.id,
              request: request,
              changes_made: incident.attributes.merge(devin_session_created: session_result.present?)
            )

            render json: incident, serializer: IncidentSerializer, status: :created
          else
            render json: { error: 'Validation failed', details: incident.errors.full_messages },
                   status: :unprocessable_entity
          end
        end

        # POST /api/v1/admin/incidents/:id/trigger_session
        def trigger_session
          if @incident.devin_session_id.present?
            return render json: { error: 'Incident already has a Devin session' }, status: :unprocessable_entity
          end

          session_result = DevinSessionService.create_session(incident: @incident)

          if session_result
            @incident.update(
              devin_session_id: session_result[:session_id],
              devin_session_url: session_result[:url],
              devin_session_status: 'running'
            )
            render json: @incident, serializer: IncidentSerializer
          else
            render json: { error: 'Failed to create Devin session' }, status: :service_unavailable
          end
        end

        private

        def set_incident
          @incident = Incident.find(params[:id]) # nosemgrep: ruby.rails.security.brakeman.check-unscoped-find.check-unscoped-find
        end

        def incident_params
          params.require(:incident).permit(:title, :description, :severity, :affected_service)
        end
      end
    end
  end
end
