class CreateAnnouncements < ActiveRecord::Migration[7.1]
  def change
    create_table :announcements, id: :uuid do |t|
      t.string :title, null: false
      t.text :body, null: false
      t.string :severity, null: false, default: "info"
      t.string :status, null: false, default: "draft"
      t.jsonb :target_audience, default: {}
      t.datetime :starts_at
      t.datetime :ends_at
      t.uuid :created_by
      t.timestamps
    end

    add_index :announcements, :status
    add_index :announcements, :severity
    add_index :announcements, %i[starts_at ends_at]
  end
end
