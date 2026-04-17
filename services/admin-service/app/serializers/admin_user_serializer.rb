class AdminUserSerializer < ActiveModel::Serializer
  attributes :id, :email, :display_name, :role, :status, :avatar_url,
             :metadata, :last_login_at, :suspended_at, :suspended_reason,
             :created_at, :updated_at

  has_one :storage_quota, serializer: StorageQuotaSerializer, if: -> { instance_options[:include_quota] }
end
