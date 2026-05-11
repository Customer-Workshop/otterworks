using OtterWorks.NotificationService.Models;

namespace OtterWorks.NotificationService.Services;

public interface INotificationService
{
    Task ProcessEventAsync(SqsNotificationMessage sqsEvent);
    Task<(List<Notification> Notifications, int Total)> GetNotificationsAsync(string userId, int page, int pageSize);
    Task<int> GetUnreadCountAsync(string userId);
    Task<bool> MarkAsReadAsync(string notificationId);
    Task<int> MarkAllAsReadAsync(string userId);
    Task<bool> DeleteNotificationAsync(string notificationId);
    Task<Notification?> GetNotificationByIdAsync(string id);
    Task<NotificationPreference> GetPreferencesAsync(string userId);
    Task UpdatePreferencesAsync(string userId, string eventType, List<DeliveryChannel> channels);
}
