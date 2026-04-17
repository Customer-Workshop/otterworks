FactoryBot.define do
  factory :admin_user do
    email { Faker::Internet.unique.email }
    display_name { Faker::Name.name }
    role { 'viewer' }
    status { 'active' }
    metadata { {} }

    trait :super_admin do
      role { 'super_admin' }
    end

    trait :admin do
      role { 'admin' }
    end

    trait :editor do
      role { 'editor' }
    end

    trait :suspended do
      status { 'suspended' }
      suspended_at { Time.current }
      suspended_reason { 'Policy violation' }
    end

    trait :deleted do
      status { 'deleted' }
    end
  end
end
