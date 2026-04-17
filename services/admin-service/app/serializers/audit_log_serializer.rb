class AuditLogSerializer < ActiveModel::Serializer
  attributes :id, :actor_id, :actor_email, :action, :resource_type,
             :resource_id, :changes_made, :ip_address, :user_agent, :created_at
end
