class CreateAdminUsers < ActiveRecord::Migration[7.1]
  def change
    create_table :admin_users, id: :uuid do |t|
      t.string :email, null: false
      t.string :display_name, null: false
      t.string :role, null: false, default: "viewer"
      t.string :status, null: false, default: "active"
      t.string :avatar_url
      t.jsonb :metadata, default: {}
      t.datetime :last_login_at
      t.datetime :suspended_at
      t.string :suspended_reason
      t.timestamps
    end

    add_index :admin_users, :email, unique: true
    add_index :admin_users, :status
    add_index :admin_users, :role
  end
end
