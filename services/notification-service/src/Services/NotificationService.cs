using OtterWorks.NotificationService.Models;

namespace OtterWorks.NotificationService.Services;

public class NotificationService : INotificationService
{
    private readonly INotificationRepository _repository;
    private readonly ILogger<NotificationService> _logger;

    public NotificationService(
        INotificationRepository repository,
        ILogger<NotificationService> logger)
    {
        _repository = repository;
        _logger = logger;
    }

    public async Task ProcessEventAsync(SqsNotificationMessage sqsEvent)
    {
        var targetUserId = ResolveTargetUserId(sqsEvent);
        if (string.IsNullOrWhiteSpace(targetUserId))
        {
            _logger.LogWarning("No target user for event: {EventType}", sqsEvent.EventType);
            return;
        }

        var preferences = await _repository.GetPreferencesAsync(targetUserId);
        List<DeliveryChannel> enabledChannels;
        if (preferences.Channels.TryGetValue(sqsEvent.EventType, out var channels))
        {
            enabledChannels = channels;
        }
        else
        {
            var defaults = new NotificationPreference { UserId = targetUserId };
            enabledChannels = defaults.Channels.TryGetValue(sqsEvent.EventType, out var defaultChannels)
                ? defaultChannels
                : new List<DeliveryChannel> { DeliveryChannel.IN_APP };
        }

        var rendered = NotificationTemplates.Render(sqsEvent);
        var deliveredVia = new List<string>();

        if (enabledChannels.Contains(DeliveryChannel.IN_APP))
        {
            deliveredVia.Add("in_app");
        }

        if (enabledChannels.Contains(DeliveryChannel.EMAIL))
        {
            deliveredVia.Add("email");
        }

        var notification = new Notification
        {
            Id = Guid.NewGuid().ToString(),
            UserId = targetUserId,
            Type = sqsEvent.EventType,
            Title = rendered.Title,
            Message = rendered.Message,
            ResourceId = ResolveResourceId(sqsEvent),
            ResourceType = ResolveResourceType(sqsEvent),
            ActorId = string.IsNullOrEmpty(sqsEvent.ActorId) ? sqsEvent.OwnerId : sqsEvent.ActorId,
            Read = false,
            DeliveredVia = deliveredVia,
            CreatedAt = DateTime.UtcNow.ToString("O"),
        };

        await _repository.SaveNotificationAsync(notification);
        _logger.LogInformation("Stored notification {Id} for user {UserId}", notification.Id, targetUserId);

        if (enabledChannels.Contains(DeliveryChannel.PUSH))
        {
            deliveredVia.Add("push");
            await _repository.SaveNotificationAsync(new Notification
            {
                Id = notification.Id,
                UserId = notification.UserId,
                Type = notification.Type,
                Title = notification.Title,
                Message = notification.Message,
                ResourceId = notification.ResourceId,
                ResourceType = notification.ResourceType,
                ActorId = notification.ActorId,
                Read = notification.Read,
                DeliveredVia = deliveredVia,
                CreatedAt = notification.CreatedAt,
            });
        }

        _logger.LogInformation(
            "Processed {EventType} for user {UserId} via {Channels}",
            sqsEvent.EventType, targetUserId, string.Join(", ", deliveredVia));
    }

    public Task<(List<Notification> Notifications, int Total)> GetNotificationsAsync(string userId, int page, int pageSize) =>
        _repository.GetNotificationsByUserIdAsync(userId, page, pageSize);

    public Task<int> GetUnreadCountAsync(string userId) =>
        _repository.GetUnreadCountAsync(userId);

    public Task<bool> MarkAsReadAsync(string notificationId) =>
        _repository.MarkAsReadAsync(notificationId);

    public Task<int> MarkAllAsReadAsync(string userId) =>
        _repository.MarkAllAsReadAsync(userId);

    public Task<bool> DeleteNotificationAsync(string notificationId) =>
        _repository.DeleteNotificationAsync(notificationId);

    public Task<Notification?> GetNotificationByIdAsync(string id) =>
        _repository.GetNotificationByIdAsync(id);

    public Task<NotificationPreference> GetPreferencesAsync(string userId) =>
        _repository.GetPreferencesAsync(userId);

    public async Task UpdatePreferencesAsync(string userId, string eventType, List<DeliveryChannel> channels)
    {
        var current = await _repository.GetPreferencesAsync(userId);
        var updatedChannels = new Dictionary<string, List<DeliveryChannel>>(current.Channels)
        {
            [eventType] = channels,
        };

        await _repository.SavePreferencesAsync(new NotificationPreference
        {
            UserId = userId,
            Channels = updatedChannels,
        });
    }

    public static string ResolveTargetUserId(SqsNotificationMessage sqsEvent)
    {
        return sqsEvent.EventType switch
        {
            "file_shared" => sqsEvent.SharedWithUserId,
            "comment_added" => string.IsNullOrEmpty(sqsEvent.UserId) ? sqsEvent.OwnerId : sqsEvent.UserId,
            "document_edited" => string.IsNullOrEmpty(sqsEvent.UserId) ? sqsEvent.OwnerId : sqsEvent.UserId,
            "user_mentioned" => string.IsNullOrEmpty(sqsEvent.MentionedUserId) ? sqsEvent.UserId : sqsEvent.MentionedUserId,
            _ => sqsEvent.UserId,
        };
    }

    public static string ResolveResourceId(SqsNotificationMessage sqsEvent)
    {
        return sqsEvent.EventType switch
        {
            "file_shared" => sqsEvent.FileId,
            "comment_added" => string.IsNullOrEmpty(sqsEvent.CommentId) ? sqsEvent.DocumentId : sqsEvent.CommentId,
            "document_edited" => sqsEvent.DocumentId,
            "user_mentioned" => sqsEvent.DocumentId,
            _ => string.Empty,
        };
    }

    public static string ResolveResourceType(SqsNotificationMessage sqsEvent)
    {
        return sqsEvent.EventType switch
        {
            "file_shared" => "file",
            "comment_added" => "comment",
            "document_edited" => "document",
            "user_mentioned" => "document",
            _ => "unknown",
        };
    }
}
