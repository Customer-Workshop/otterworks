class AddSnowFieldsToIncidents < ActiveRecord::Migration[7.1]
  def change
    add_column :incidents, :snow_ticket_number, :string
    add_column :incidents, :snow_sys_id, :string
    add_column :incidents, :snow_instance_url, :string

    add_index :incidents, :snow_ticket_number, unique: true, where: 'snow_ticket_number IS NOT NULL'
  end
end
