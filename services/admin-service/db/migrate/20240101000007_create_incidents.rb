class CreateIncidents < ActiveRecord::Migration[7.1]
  def change
    create_table :incidents, id: :uuid do |t|
      t.string :title, null: false
      t.text :description, null: false
      t.string :severity, null: false, default: "medium"
      t.string :status, null: false, default: "open"
      t.string :affected_service
      t.string :devin_session_id
      t.string :devin_session_url
      t.string :devin_session_status
      t.uuid :reporter_id
      t.datetime :resolved_at
      t.timestamps
    end

    add_index :incidents, :status
    add_index :incidents, :severity
    add_index :incidents, :affected_service
    add_index :incidents, :devin_session_id, unique: true
  end
end
