class CreateAuditLogs < ActiveRecord::Migration[7.1]
  def change
    create_table :audit_logs, id: :uuid do |t|
      t.uuid :actor_id
      t.string :actor_email
      t.string :action, null: false
      t.string :resource_type, null: false
      t.uuid :resource_id
      t.jsonb :changes_made, default: {}
      t.string :ip_address
      t.string :user_agent
      t.timestamps
    end

    add_index :audit_logs, :actor_id
    add_index :audit_logs, :action
    add_index :audit_logs, %i[resource_type resource_id]
    add_index :audit_logs, :created_at
  end
end
