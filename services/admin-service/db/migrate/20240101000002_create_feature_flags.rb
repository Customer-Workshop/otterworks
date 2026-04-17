class CreateFeatureFlags < ActiveRecord::Migration[7.1]
  def change
    create_table :feature_flags, id: :uuid do |t|
      t.string :name, null: false
      t.string :description
      t.boolean :enabled, null: false, default: false
      t.jsonb :target_users, default: []
      t.jsonb :target_groups, default: []
      t.integer :rollout_percentage, default: 0
      t.datetime :expires_at
      t.timestamps
    end

    add_index :feature_flags, :name, unique: true
    add_index :feature_flags, :enabled
  end
end
