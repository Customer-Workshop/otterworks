require 'rails_helper'

RSpec.describe JwtAuthenticator do
  let(:downstream) { ->(env) { [200, {}, [env.slice('jwt.user_id', 'jwt.user_role', 'jwt.user_roles').to_json]] } }
  let(:middleware) { described_class.new(downstream) }

  def call_with(token)
    status, _headers, body = middleware.call(Rack::MockRequest.env_for('/api/v1/admin/users',
                                                                       'HTTP_AUTHORIZATION' => "Bearer #{token}"))
    [status, JSON.parse(body.first)]
  end

  it 'exposes the auth-service roles array claim' do
    status, env = call_with(jwt_token(user_id: 'u-1', role: nil, roles: %w[OWNER USER]))

    expect(status).to eq(200)
    expect(env['jwt.user_id']).to eq('u-1')
    expect(env['jwt.user_role']).to be_nil
    expect(env['jwt.user_roles']).to eq(%w[OWNER USER])
  end

  it 'exposes an empty roles array when the claim is absent' do
    _status, env = call_with(jwt_token(role: 'super_admin'))

    expect(env['jwt.user_role']).to eq('super_admin')
    expect(env['jwt.user_roles']).to eq([])
  end

  it 'rejects requests without a valid token' do
    status, _headers, _body = middleware.call(Rack::MockRequest.env_for('/api/v1/admin/users'))

    expect(status).to eq(401)
  end
end
