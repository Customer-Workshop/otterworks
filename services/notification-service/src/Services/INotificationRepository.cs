using OtterWorks.NotificationService.Models;

namespace OtterWorks.NotificationService.Services;

public interface INotificationRepository
{
    Task SaveNotificationAsync(Notification notification);
    Task<Notification?> GetNotificationByIdAsync(string id);
    Task<(List<Notification> Notifications, int Total)> GetNotificationsByUserIdAsync(string userId, int page = 1, int pageSize = 20);
    Task<int> GetUnreadCountAsync(string userId);
    Task<bool> MarkAsReadAsync(string id);
    Task<int> MarkAllAsReadAsync(string userId);
    Task<bool> DeleteNotificationAsync(string id);
    Task<NotificationPreference> GetPreferencesAsync(string userId);
    Task SavePreferencesAsync(NotificationPreference preference);
}
