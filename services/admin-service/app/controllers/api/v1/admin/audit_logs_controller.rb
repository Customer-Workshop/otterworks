module Api
  module V1
    module Admin
      class AuditLogsController < ApplicationController
        # GET /api/v1/admin/audit-logs
        def index
          result = paginate(filtered_scope)

          render json: {
            audit_logs: ActiveModelSerializers::SerializableResource.new(result[:records]),
            total: result[:total],
            page: result[:page],
            per_page: result[:per_page]
          }
        end

        # GET /api/v1/admin/audit-logs/:id
        def show
          audit_log = AuditLog.find(params[:id])
          render json: audit_log, serializer: AuditLogSerializer
        end

        private

        def filtered_scope
          scope = AuditLog.recent
          scope = scope.by_action(params[:action_type]) if params[:action_type].present?
          scope = scope.by_resource(params[:resource_type], params[:resource_id]) if params[:resource_type].present?
          scope = scope.by_actor(params[:actor_id]) if params[:actor_id].present?
          apply_time_filters(scope)
        end

        def apply_time_filters(scope)
          scope = scope.since(Time.zone.parse(params[:since])) if params[:since].present?
          scope = scope.where('created_at <= ?', Time.zone.parse(params[:until])) if params[:until].present?
          scope
        end
      end
    end
  end
end
