class StorageQuotaSerializer < ActiveModel::Serializer
  attributes :id, :user_id, :quota_bytes, :used_bytes, :tier,
             :usage_percentage, :over_quota, :remaining_bytes,
             :created_at, :updated_at

  delegate :usage_percentage, to: :object

  def over_quota
    object.over_quota?
  end

  delegate :remaining_bytes, to: :object
end
