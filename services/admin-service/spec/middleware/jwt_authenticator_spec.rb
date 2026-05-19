require 'rails_helper'

RSpec.describe JwtAuthenticator do
  let(:app) { ->(env) { [200, {}, ['OK']] } }
  let(:middleware) { described_class.new(app) }

  describe '#call' do
    it 'allows requests to /health without auth' do
      env = Rack::MockRequest.env_for('/health')
      status, _headers, _body = middleware.call(env)
      expect(status).to eq(200)
    end

    it 'allows requests to /metrics without auth' do
      env = Rack::MockRequest.env_for('/metrics')
      status, _headers, _body = middleware.call(env)
      expect(status).to eq(200)
    end

    it 'allows requests to /api/v1/admin/alerts/ingest without auth' do
      env = Rack::MockRequest.env_for('/api/v1/admin/alerts/ingest')
      status, _headers, _body = middleware.call(env)
      expect(status).to eq(200)
    end

    it 'allows requests to /api/v1/admin/chaos without auth' do
      env = Rack::MockRequest.env_for('/api/v1/admin/chaos')
      status, _headers, _body = middleware.call(env)
      expect(status).to eq(200)
    end

    it 'returns 401 when no authorization header is present' do
      env = Rack::MockRequest.env_for('/api/v1/admin/users')
      status, headers, body = middleware.call(env)
      expect(status).to eq(401)
      parsed = JSON.parse(body.first)
      expect(parsed['error']).to include('Missing')
    end

    it 'returns 401 for invalid token' do
      env = Rack::MockRequest.env_for('/api/v1/admin/users',
        'HTTP_AUTHORIZATION' => 'Bearer invalid-token')
      status, headers, body = middleware.call(env)
      expect(status).to eq(401)
      parsed = JSON.parse(body.first)
      expect(parsed['error']).to include('Invalid')
    end

    it 'passes through with a valid token and sets env values' do
      token = jwt_token(user_id: 'user-1', email: 'test@test.com', role: 'admin')
      env = Rack::MockRequest.env_for('/api/v1/admin/users',
        'HTTP_AUTHORIZATION' => "Bearer #{token}")

      status, _headers, _body = middleware.call(env)
      expect(status).to eq(200)
      expect(env['jwt.user_id']).to eq('user-1')
      expect(env['jwt.user_email']).to eq('test@test.com')
      expect(env['jwt.user_role']).to eq('admin')
    end
  end
end
