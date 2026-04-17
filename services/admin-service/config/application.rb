require_relative "boot"
require "rails/all"

Bundler.require(*Rails.groups)

module AdminService
  class Application < Rails::Application
    config.load_defaults 7.1
    config.api_only = false # ActiveAdmin needs full Rails stack
    config.active_job.queue_adapter = :sidekiq
    config.log_formatter = ::Logger::Formatter.new
    config.time_zone = "UTC"

    # Structured JSON logging
    config.lograge.enabled = true
    config.lograge.formatter = Lograge::Formatters::Json.new
    config.lograge.custom_payload do |controller|
      {
        service: "admin-service",
        host: Socket.gethostname
      }
    end
  end
end
