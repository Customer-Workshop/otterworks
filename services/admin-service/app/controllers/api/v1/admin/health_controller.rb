module Api
  module V1
    module Admin
      class HealthController < ApplicationController
        # GET /api/v1/admin/health/services
        def services
          result = HealthChecker.check_all
          status = result[:status] == 'healthy' ? :ok : :service_unavailable

          render json: result, status: status
        end
      end
    end
  end
end
