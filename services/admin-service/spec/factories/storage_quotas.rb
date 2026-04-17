FactoryBot.define do
  factory :storage_quota do
    user_id { SecureRandom.uuid }
    quota_bytes { 5_368_709_120 } # 5 GB
    used_bytes { 1_073_741_824 } # 1 GB
    tier { 'free' }

    trait :over_quota do
      used_bytes { 6_000_000_000 }
    end

    trait :pro do
      tier { 'pro' }
      quota_bytes { 214_748_364_800 } # 200 GB
    end

    trait :enterprise do
      tier { 'enterprise' }
      quota_bytes { 1_099_511_627_776 } # 1 TB
    end
  end
end
