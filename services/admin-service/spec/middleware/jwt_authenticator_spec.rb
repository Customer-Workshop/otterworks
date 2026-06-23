require 'rails_helper'

RSpec.describe JwtAuthenticator do
  let(:app) { ->(env) { [200, env, ['OK']] } }
  let(:middleware) { described_class.new(app) }

  def make_env(path: '/api/v1/admin/users', headers: {})
    env = Rack::MockRequest.env_for(path)
    headers.each { |k, v| env["HTTP_#{k.upcase.tr('-', '_')}"] = v }
    env
  end

  describe 'excluded paths' do
    %w[/health /metrics /api/v1/admin/alerts/ingest /api/v1/admin/chaos].each do |excluded_path|
      it "passes through for #{excluded_path}" do
        env = make_env(path: excluded_path)
        status, _, = middleware.call(env)
        expect(status).to eq(200)
      end
    end
  end

  describe 'authentication' do
    it 'returns 401 when no Authorization header present' do
      env = make_env
      status, _, body = middleware.call(env)
      expect(status).to eq(401)
      parsed = JSON.parse(body.first)
      expect(parsed['error']).to eq('Missing authorization token')
    end

    it 'returns 401 when token is invalid' do
      env = make_env(headers: { 'Authorization' => 'Bearer invalid.token.here' })
      status, _, body = middleware.call(env)
      expect(status).to eq(401)
      parsed = JSON.parse(body.first)
      expect(parsed['error']).to eq('Invalid or expired token')
    end

    it 'returns 401 when token is expired' do
      secret = Rails.application.secrets.jwt_secret
      payload = { sub: SecureRandom.uuid, email: 'test@otterworks.com', role: 'admin', exp: 1.hour.ago.to_i }
      expired_token = JWT.encode(payload, secret, 'HS256')

      env = make_env(headers: { 'Authorization' => "Bearer #{expired_token}" })
      status, _, body = middleware.call(env)
      expect(status).to eq(401)
      parsed = JSON.parse(body.first)
      expect(parsed['error']).to eq('Invalid or expired token')
    end

    it 'sets jwt.user_id, jwt.user_email, jwt.user_role in env on valid token' do
      user_id = SecureRandom.uuid
      secret = Rails.application.secrets.jwt_secret
      payload = { sub: user_id, email: 'admin@otterworks.com', role: 'super_admin', exp: 24.hours.from_now.to_i }
      token = JWT.encode(payload, secret, 'HS256')

      env = make_env(headers: { 'Authorization' => "Bearer #{token}" })
      status, response_env, = middleware.call(env)
      expect(status).to eq(200)
      expect(response_env['jwt.user_id']).to eq(user_id)
      expect(response_env['jwt.user_email']).to eq('admin@otterworks.com')
      expect(response_env['jwt.user_role']).to eq('super_admin')
    end

    it 'extracts token from "Bearer <token>" format' do
      secret = Rails.application.secrets.jwt_secret
      payload = { sub: SecureRandom.uuid, email: 'test@otterworks.com', role: 'admin', exp: 24.hours.from_now.to_i }
      token = JWT.encode(payload, secret, 'HS256')

      env = make_env(headers: { 'Authorization' => "Bearer #{token}" })
      status, _, = middleware.call(env)
      expect(status).to eq(200)
    end
  end
end
