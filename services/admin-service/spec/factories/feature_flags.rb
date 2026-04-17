FactoryBot.define do
  factory :feature_flag do
    sequence(:name) { |n| "feature_#{n}" }
    description { Faker::Lorem.sentence }
    enabled { false }
    rollout_percentage { 0 }
    target_users { [] }
    target_groups { [] }

    trait :enabled do
      enabled { true }
      rollout_percentage { 100 }
    end

    trait :partial_rollout do
      enabled { true }
      rollout_percentage { 50 }
    end

    trait :expired do
      enabled { true }
      expires_at { 1.day.ago }
    end
  end
end
