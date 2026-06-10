class AdminSettingsService
  AUTO_INVESTIGATE_KEY = 'admin:auto_investigate'.freeze

  class << self
    def auto_investigate_enabled?
      redis = RedisConnection.new_client
      val = redis.get(AUTO_INVESTIGATE_KEY)
      val.nil? ? true : val == 'true'
    rescue StandardError => e
      Rails.logger.error("Failed to read auto_investigate setting: #{e.message}")
      true # fail-open to preserve existing behavior
    ensure
      redis&.close
    end

    def set_auto_investigate(enabled)
      redis = RedisConnection.new_client
      redis.set(AUTO_INVESTIGATE_KEY, enabled.to_s)
    rescue StandardError => e
      Rails.logger.error("Failed to set auto_investigate setting: #{e.message}")
      raise
    ensure
      redis&.close
    end
  end
end
