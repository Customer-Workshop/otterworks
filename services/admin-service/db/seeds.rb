# Seed development data for admin service

# System configs
SystemConfig.find_or_create_by!(key: 'max_upload_size_mb') do |config|
  config.value = '100'
  config.value_type = 'integer'
  config.description = 'Maximum file upload size in megabytes'
end

SystemConfig.find_or_create_by!(key: 'maintenance_mode') do |config|
  config.value = 'false'
  config.value_type = 'boolean'
  config.description = 'Enable maintenance mode for the platform'
end

SystemConfig.find_or_create_by!(key: 'default_storage_quota_gb') do |config|
  config.value = '5'
  config.value_type = 'integer'
  config.description = 'Default storage quota for new users in GB'
end

SystemConfig.find_or_create_by!(key: 'session_timeout_minutes') do |config|
  config.value = '30'
  config.value_type = 'integer'
  config.description = 'Session timeout in minutes'
end

# Feature flags
FeatureFlag.find_or_create_by!(name: 'dark_mode') do |flag|
  flag.description = 'Enable dark mode UI theme'
  flag.enabled = true
  flag.rollout_percentage = 100
end

FeatureFlag.find_or_create_by!(name: 'collaborative_editing') do |flag|
  flag.description = 'Real-time collaborative document editing'
  flag.enabled = true
  flag.rollout_percentage = 80
end

FeatureFlag.find_or_create_by!(name: 'ai_suggestions') do |flag|
  flag.description = 'AI-powered writing suggestions (Operation Kelp Forest)'
  flag.enabled = false
  flag.rollout_percentage = 0
end

FeatureFlag.find_or_create_by!(name: 'otter_storage_v2') do |flag|
  flag.description = 'Multi-tier storage lifecycle management (RFC-001)'
  flag.enabled = true
  flag.rollout_percentage = 100
end

FeatureFlag.find_or_create_by!(name: 'tidal_pool_cache') do |flag|
  flag.description = 'Distributed caching layer for read-heavy endpoints (RFC-005)'
  flag.enabled = false
  flag.rollout_percentage = 0
end

FeatureFlag.find_or_create_by!(name: 'river_basin_events') do |flag|
  flag.description = 'SNS/SQS event-driven inter-service communication (RFC-003)'
  flag.enabled = true
  flag.rollout_percentage = 100
end

FeatureFlag.find_or_create_by!(name: 'dam_builder_rate_limit') do |flag|
  flag.description = 'Sliding window rate limiter for API gateway (RFC-004)'
  flag.enabled = false
  flag.rollout_percentage = 0
end

FeatureFlag.find_or_create_by!(name: 'predator_alert_mfa') do |flag|
  flag.description = 'Mandatory MFA for all admin accounts'
  flag.enabled = false
  flag.rollout_percentage = 0
end

FeatureFlag.find_or_create_by!(name: 'kelp_forest_search') do |flag|
  flag.description = 'Advanced full-text search with filters and facets'
  flag.enabled = true
  flag.rollout_percentage = 50
end

# Additional system configs
SystemConfig.find_or_create_by!(key: 'max_collab_participants') do |config|
  config.value = '25'
  config.value_type = 'integer'
  config.description = 'Maximum simultaneous collaborators on a single document'
end

SystemConfig.find_or_create_by!(key: 'file_versioning_max_versions') do |config|
  config.value = '50'
  config.value_type = 'integer'
  config.description = 'Maximum number of file versions to retain before auto-pruning'
end

SystemConfig.find_or_create_by!(key: 'crdt_flush_interval_ms') do |config|
  config.value = '500'
  config.value_type = 'integer'
  config.description = 'Interval for flushing CRDT state from Redis to PostgreSQL'
end

SystemConfig.find_or_create_by!(key: 'trash_retention_days') do |config|
  config.value = '30'
  config.value_type = 'integer'
  config.description = 'Days before permanently deleting trashed files'
end

SystemConfig.find_or_create_by!(key: 'audit_log_retention_days') do |config|
  config.value = '365'
  config.value_type = 'integer'
  config.description = 'Audit event retention period for compliance (SOC2)'
end

SystemConfig.find_or_create_by!(key: 'oncall_rotation_team') do |config|
  config.value = 'Tide Watchers'
  config.value_type = 'string'
  config.description = 'Current primary on-call team'
end

Rails.logger.debug 'Seed data loaded successfully - The holt is stocked!'
