require 'net/http'

# Generates synthetic traffic to chaos-affected services so that Prometheus
# metrics accumulate and Grafana alerts fire without needing real user traffic.
#
# When chaos is triggered, a background thread pings the affected endpoint
# every few seconds until the Redis chaos key expires or is manually reset.
class ChaosProbeService
  PROBE_INTERVAL = 5 # seconds between probe requests
  PROBE_BATCH    = 3 # requests per interval (enough for rate() to register)

  SERVICE_PROBES = {
    'search-service' => {
      url: 'http://search-service:8087/api/v1/search/suggest?q=test',
      headers: { 'X-User-ID' => 'chaos-probe' },
    },
    'file-service' => {
      url: 'http://file-service:8082/api/v1/files/upload',
      method: :post,
      headers: { 'X-User-ID' => 'chaos-probe', 'Content-Type' => 'application/json' },
      body: '{"filename":"probe.txt"}',
    },
    'notification-service' => {
      url: 'http://notification-service:8086/health',
      headers: {},
    },
  }.freeze

  # Starts a background probe thread for the given service.
  # The thread self-terminates when the Redis key no longer exists.
  def self.start(service:, redis_key:)
    probe_config = SERVICE_PROBES[service]
    return unless probe_config

    Thread.new do
      Thread.current.report_on_exception = true
      Rails.logger.info("[ChaosProbe] Started for #{service}")
      redis = Redis.new(
        url: ENV.fetch('REDIS_URL', "redis://#{ENV.fetch('REDIS_HOST', 'localhost')}:#{ENV.fetch('REDIS_PORT', '6379')}/0"),
        timeout: 2
      )

      iterations = 0
      loop do
        break unless redis.exists?(redis_key)

        PROBE_BATCH.times { fire_probe(probe_config) }
        iterations += 1
        sleep PROBE_INTERVAL
      end

      Rails.logger.info("[ChaosProbe] Stopped for #{service} after #{iterations} iterations")
    rescue StandardError => e
      Rails.logger.error("[ChaosProbe] Thread error for #{service}: #{e.class} - #{e.message}")
    ensure
      redis&.close
    end
  end

  def self.fire_probe(config)
    uri = URI.parse(config[:url])
    http = Net::HTTP.new(uri.host, uri.port)
    http.open_timeout = 3
    http.read_timeout = 3

    request = if config[:method] == :post
                req = Net::HTTP::Post.new(uri.request_uri)
                req.body = config[:body] if config[:body]
                req
              else
                Net::HTTP::Get.new(uri.request_uri)
              end

    config[:headers]&.each { |k, v| request[k] = v }
    http.request(request)
  rescue StandardError
    nil
  end
end
