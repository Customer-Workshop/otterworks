FactoryBot.define do
  factory :incident do
    title { Faker::Lorem.sentence }
    description { Faker::Lorem.paragraph }
    severity { 'medium' }
    status { 'open' }
    affected_service { 'api-gateway' }

    trait :with_snow do
      snow_ticket_number { "INC#{Faker::Number.unique.number(digits: 7)}" }
      snow_sys_id { SecureRandom.hex(16) }
      snow_instance_url { 'https://dev12345.service-now.com' }
    end

    trait :investigating do
      status { 'investigating' }
    end

    trait :with_devin_session do
      investigating
      devin_session_id { SecureRandom.uuid }
      devin_session_url { "https://app.devin.ai/sessions/#{SecureRandom.uuid}" }
      devin_session_status { 'running' }
    end

    trait :snow_linked_active do
      with_snow
      with_devin_session
    end

    trait :resolved do
      status { 'resolved' }
      resolved_at { Time.current }
    end
  end
end
