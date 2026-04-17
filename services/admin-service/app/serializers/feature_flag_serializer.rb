class FeatureFlagSerializer < ActiveModel::Serializer
  attributes :id, :name, :description, :enabled, :target_users, :target_groups,
             :rollout_percentage, :expires_at, :expired, :created_at, :updated_at

  def expired
    object.expired?
  end
end
