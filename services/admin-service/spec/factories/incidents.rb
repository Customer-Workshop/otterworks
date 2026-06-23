FactoryBot.define do
  factory :incident do
    title { Faker::Lorem.sentence(word_count: 5) }
    description { Faker::Lorem.paragraph }
    severity { 'medium' }
    status { 'open' }
    affected_service { 'file-service' }
    reporter_id { SecureRandom.uuid }

    trait :investigating do
      status { 'investigating' }
    end

    trait :resolved do
      status { 'resolved' }
      resolved_at { Time.current }
    end

    trait :closed do
      status { 'closed' }
      resolved_at { 1.hour.ago }
      closed_at { Time.current }
    end

    trait :critical do
      severity { 'critical' }
    end

    trait :with_devin_session do
      devin_session_id { "session-#{SecureRandom.hex(8)}" }
      devin_session_url { "https://app.devin.ai/sessions/#{SecureRandom.hex(8)}" }
      devin_session_status { 'running' }
    end
  end
end
