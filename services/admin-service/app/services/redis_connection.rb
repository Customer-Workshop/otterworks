class RedisConnection
  DEFAULT_TIMEOUT = 2

  def self.url
    ENV.fetch('REDIS_URL', "redis://#{ENV.fetch('REDIS_HOST', 'localhost')}:#{ENV.fetch('REDIS_PORT', '6379')}/0")
  end

  def self.new_client(timeout: DEFAULT_TIMEOUT)
    Redis.new(url: url, timeout: timeout)
  end
end
