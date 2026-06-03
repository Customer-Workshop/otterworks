# Deprecated: Session status tracking is now handled by the Devin Automation
# playbook, which posts work notes and resolves incidents directly in
# ServiceNow. The DevinCallbackController also remains available as a
# fallback for sessions that POST status updates to the admin-service.
#
# This polling job is retained as a no-op placeholder so any existing
# Sidekiq schedule references don't raise NameError. It can be safely
# deleted once the sidekiq_schedule.yml entry is removed.
class DevinSessionPollJob < ApplicationJob
  queue_as :default

  def perform
    Rails.logger.info(
      'DevinSessionPollJob: no-op — session lifecycle is now managed by ' \
      'Devin Automations playbook and DevinCallbackController'
    )
  end
end
