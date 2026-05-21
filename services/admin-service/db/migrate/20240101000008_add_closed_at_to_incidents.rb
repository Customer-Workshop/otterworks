class AddClosedAtToIncidents < ActiveRecord::Migration[7.1]
  def change
    add_column :incidents, :closed_at, :datetime
  end
end
