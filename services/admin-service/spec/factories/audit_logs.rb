FactoryBot.define do
  factory :audit_log do
    actor_id { SecureRandom.uuid }
    actor_email { Faker::Internet.email }
    action { 'user.updated' }
    resource_type { 'AdminUser' }
    resource_id { SecureRandom.uuid }
    changes_made { { role: 'admin' } }
    ip_address { Faker::Internet.ip_v4_address }
    user_agent { 'RSpec Test Agent' }
  end
end
