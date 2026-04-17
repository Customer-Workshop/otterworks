class AnnouncementSerializer < ActiveModel::Serializer
  attributes :id, :title, :body, :severity, :status, :target_audience,
             :starts_at, :ends_at, :created_by, :active, :created_at, :updated_at

  def active
    object.active?
  end
end
