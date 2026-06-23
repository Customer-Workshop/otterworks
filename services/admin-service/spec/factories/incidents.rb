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
  end
end
