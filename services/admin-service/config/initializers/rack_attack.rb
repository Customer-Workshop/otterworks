Rack::Attack.throttle('api/ip', limit: 300, period: 5.minutes) do |req|
  req.ip if req.path.start_with?('/api/')
end

Rack::Attack.throttle('api/bulk', limit: 10, period: 1.minute) do |req|
  req.ip if req.path.include?('/bulk/')
end

Rack::Attack.throttled_responder = lambda do |_env|
  [429, { 'Content-Type' => 'application/json' }, [{ error: 'Rate limit exceeded' }.to_json]]
end
