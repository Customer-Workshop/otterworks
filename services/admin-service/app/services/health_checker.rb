class HealthChecker
  SERVICES = %w[auth-service file-service document-service collab-service notification-service search-service
                analytics-service audit-service].freeze

  ServiceStatus = Struct.new(:name, :status, :latency_ms, :message, keyword_init: true)

  def self.check_all
    services = SERVICES.map { |name| check_service(name) }
    overall = services.all? { |s| s.status == 'healthy' } ? 'healthy' : 'degraded'

    {
      status: overall,
      timestamp: Time.current.iso8601,
      services: services.map { |s| { name: s.name, status: s.status, latency_ms: s.latency_ms, message: s.message } },
      database: check_database,
      redis: check_redis
    }
  end

  def self.check_service(name)
    host = ENV.fetch("#{name.tr('-', '_').upcase}_HOST", name)
    port = ENV.fetch("#{name.tr('-', '_').upcase}_PORT", nil)
    url = "http://#{host}:#{port}/health" if port.present?

    start_time = Process.clock_gettime(Process::CLOCK_MONOTONIC)

    if url.present?
      uri = URI.parse(url)
      http = Net::HTTP.new(uri.host, uri.port)
      http.open_timeout = 2
      http.read_timeout = 2
      response = http.get(uri.path)
      latency = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time) * 1000).round(1)

      ServiceStatus.new(name: name, status: response.code == '200' ? 'healthy' : 'unhealthy', latency_ms: latency)
    else
      ServiceStatus.new(name: name, status: 'unknown', latency_ms: 0, message: 'No endpoint configured')
    end
  rescue StandardError => e
    latency = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time) * 1000).round(1)
    ServiceStatus.new(name: name, status: 'unhealthy', latency_ms: latency, message: e.message)
  end

  def self.check_database
    start_time = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    ActiveRecord::Base.connection.execute('SELECT 1')
    latency = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time) * 1000).round(1)
    { status: 'healthy', latency_ms: latency }
  rescue StandardError => e
    { status: 'unhealthy', message: e.message }
  end

  def self.check_redis
    start_time = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    redis_url = ENV.fetch('REDIS_URL', 'redis://localhost:6379/0')
    redis = Redis.new(url: redis_url, timeout: 2)
    redis.ping
    latency = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time) * 1000).round(1)
    { status: 'healthy', latency_ms: latency }
  rescue StandardError => e
    { status: 'unhealthy', message: e.message }
  end
end
