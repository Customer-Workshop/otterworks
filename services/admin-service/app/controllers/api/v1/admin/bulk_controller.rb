module Api
  module V1
    module Admin
      class BulkController < ApplicationController
        # POST /api/v1/admin/bulk/users
        def users
          operation = params.require(:operation)
          user_ids = params.require(:user_ids)

          unless user_ids.is_a?(Array) && user_ids.any?
            return render json: { error: 'user_ids must be a non-empty array' }, status: :bad_request
          end

          result = BulkOperationsService.process(
            operation: operation,
            user_ids: user_ids,
            params: bulk_params,
            request: request
          )

          render json: {
            operation: operation,
            success_count: result.success_count,
            failure_count: result.failure_count,
            errors: result.errors
          }, status: result.failure_count.zero? ? :ok : :multi_status
        end

        private

        def bulk_params
          params.permit(:reason, :role).to_h.symbolize_keys
        end
      end
    end
  end
end
