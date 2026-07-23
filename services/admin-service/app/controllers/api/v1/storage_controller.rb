module Api
  module V1
    # User-facing storage endpoints. Unlike Api::V1::Admin::QuotasController (which
    # looks up an arbitrary user by id), this returns the quota for the *current*
    # authenticated user, resolved from the JWT the API gateway forwards.
    class StorageController < ApplicationController
      # GET /api/v1/storage/quota
      # Returns the signed-in user's storage quota. Users without a persisted row
      # (e.g. newly registered) get a non-persisted free-tier default so the client
      # can render safely without a banner (0% usage) and without erroring.
      def quota
        record = StorageQuota.find_by(user_id: current_user_id) || default_quota
        render json: record, serializer: StorageQuotaSerializer
      end

      private

      def default_quota
        StorageQuota.new(
          user_id: current_user_id,
          quota_bytes: StorageQuota::TIER_LIMITS.fetch('free'),
          used_bytes: 0,
          tier: 'free'
        )
      end
    end
  end
end
