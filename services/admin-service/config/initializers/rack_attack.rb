Rack::Attack.throttle('api/ip', limit: 300, period: 5.minutes) do |req|
  req.ip if req.path.start_with?('/api/')
end

Rack::Attack.throttle('api/bulk', limit: 10, period: 1.minute) do |req|
  req.ip if req.path.include?('/bulk/')
end

Rack::Attack.throttled_responder = lambda do |_env|
  body = {
    error: {
      code: 'RATE_LIMIT_EXCEEDED',
      message: 'Rate limit exceeded',
      status: 429
    }
  }
  [429, { 'Content-Type' => 'application/json' }, [body.to_json]]
end
