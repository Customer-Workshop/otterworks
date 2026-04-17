FactoryBot.define do
  factory :announcement do
    title { Faker::Lorem.sentence(word_count: 5) }
    body { Faker::Lorem.paragraph }
    severity { 'info' }
    status { 'draft' }
    target_audience { {} }

    trait :published do
      status { 'published' }
      starts_at { 1.day.ago }
      ends_at { 1.week.from_now }
    end

    trait :archived do
      status { 'archived' }
    end

    trait :critical do
      severity { 'critical' }
    end

    trait :expired do
      status { 'published' }
      starts_at { 2.weeks.ago }
      ends_at { 1.day.ago }
    end
  end
end
