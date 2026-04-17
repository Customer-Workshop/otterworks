class CreateStorageQuotas < ActiveRecord::Migration[7.1]
  def change
    create_table :storage_quotas, id: :uuid do |t|
      t.uuid :user_id, null: false
      t.bigint :quota_bytes, null: false, default: 5_368_709_120 # 5 GB
      t.bigint :used_bytes, null: false, default: 0
      t.string :tier, null: false, default: "free"
      t.timestamps
    end

    add_index :storage_quotas, :user_id, unique: true
    add_index :storage_quotas, :tier
  end
end
